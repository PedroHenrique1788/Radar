"""Local speech evidence. Cues are estimates, never emotion/event classifiers."""
import bisect
import re
import unicodedata
import numpy as np

from .media import check_cancel


def normalized(text):
    text=''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'\w+',text,flags=re.UNICODE))


class PhraseMatcher:
    def __init__(self,text):
        self.phrases=tuple(dict.fromkeys(normalized(p) for p in text.replace(';','\n').splitlines() if normalized(p)))
        self.pattern=re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(p) for p in sorted(self.phrases,key=len,reverse=True))+r')(?!\w)') if self.phrases else None

    def matches(self,text):
        return list(dict.fromkeys(self.pattern.findall(normalized(text)))) if self.pattern else []


SETUP=re.compile(r'\b(vou tentar|vamos tentar|sera que|se eu|preciso|agora vamos|vamos ver|olha isso|olha so|o plano|vou fazer)\b')
PAYOFF=re.compile(r'\b(consegui|conseguimos|finalmente|deu certo|nao deu|acabou|perdi|ganhei|vencemos|deu errado|quase morri|nao acredito)\b')


class SpeechIndex:
    def __init__(self,speech):
        self.segments=sorted(speech,key=lambda s:s['start'])
        self.starts=[s['start'] for s in self.segments]
        self.longest=max((s['end']-s['start'] for s in self.segments),default=0.)
        self.words=sorted((w for s in self.segments for w in s.get('words',[]) if w['end']>w['start']),key=lambda w:w['start'])
        self.word_starts=[w['start'] for w in self.words]
        self.longest_word=max((w['end']-w['start'] for w in self.words),default=0.)
        self.units=sorted((u for s in self.segments for u in (s.get('words') or [s])),key=lambda u:u['start'])
        self.unit_starts=[u['start'] for u in self.units]
        self.longest_unit=max((u['end']-u['start'] for u in self.units),default=0.)

    def between(self,a,b):
        return [s for s in self.segments[bisect.bisect_left(self.starts,a-self.longest):bisect.bisect_right(self.starts,b)] if s['end']>a and s['start']<b]

    def words_between(self,a,b):
        return [w for w in self.words[bisect.bisect_left(self.word_starts,a-self.longest_word):bisect.bisect_right(self.word_starts,b)] if w['end']>a and w['start']<b]

    def crossings(self,a,b):
        units=self.units[bisect.bisect_left(self.unit_starts,a-self.longest_unit):bisect.bisect_right(self.unit_starts,b)]
        return [u for u in units if u['start']<a<u['end'] or u['start']<b<u['end']]

    def text(self,a,b):
        # A boundary can fall between words in a long Whisper segment. Include
        # only the words actually inside the cut, matching TXT/SRT exports.
        text=[]
        for segment in self.between(a,b):
            if segment.get('words'):
                text.extend(w['word'].strip() for w in segment['words'] if w['start']>=a-1e-6 and w['end']<=b+1e-6)
            elif segment['start']>=a-1e-6 and segment['end']<=b+1e-6:text.append(segment['text'].strip())
        return re.sub(r'\s+([,.;:!?])',r'\1',' '.join(text)).strip()


def speech_evidence(sound,speech,role,phrases,cancel=None):
    """One bounded record per speech segment; word rate needs word timestamps."""
    matcher=PhraseMatcher(phrases)
    times=[p['t'] for p in sound]
    db=np.asarray([p['db'] for p in sound],dtype=float)
    audible=db[db>-50]
    baseline=float(np.median(audible)) if len(audible) else -50.
    spread=max(6.,float(np.std(audible))) if len(audible) else 6.
    rates=[]
    for seg in speech:
        words=seg.get('words') or []
        span=words[-1]['end']-words[0]['start'] if len(words)>=4 else 0
        rates.append(len(words)/span if span>=1 else None)
    measured=[r for r in rates if r is not None]
    typical=float(np.median(measured)) if measured else None
    evidence=[];last_setup=None;previous_end=None
    for index,seg in enumerate(speech):
        if index%100==0:check_cancel(cancel)
        start,end=seg['start'],seg['end'];text=seg['text'];plain=normalized(text)
        matches=matcher.matches(text)
        hook=min(1.,.45+.18*len(matches)) if matches else .35 if '?' in text or '!' in text else 0.
        lo=bisect.bisect_left(times,start-1);hi=bisect.bisect_right(times,end)
        points=sound[lo:hi]
        peak=max((p['db'] for p in points),default=baseline)
        intensity=min(1.,max(0.,(peak-baseline)/(2*spread)))
        dynamic=min(1.,max((p.get('dynamic_db',0.) for p in points),default=0.)/24)
        pause=max(0.,start-previous_end) if previous_end is not None else 0.
        pause_cue=.35 if .4<=pause<=3 and (hook or intensity>.2) else 0.
        # Mixed game audio is insufficient to attribute a sound to the creator.
        confidence=1. if role=='microphone' else .35
        vocal=confidence*min(1.,.7*intensity+.3*dynamic+pause_cue)
        rate=rates[index]
        rhythm=min(1.,abs(rate-typical)/max(.5,typical*.6)) if rate is not None and typical and len(measured)>=2 else 0.
        # A lexical setup/payoff is transparent evidence, not semantic understanding.
        setup=bool(SETUP.search(plain));payoff=bool(PAYOFF.search(plain))
        narrative_start=None;continuity=0.
        if payoff and last_setup and 0<=start-last_setup['end']<=60:
            narrative_start=last_setup['start'];continuity=.85
        elif payoff and previous_end is not None and 0<=pause<=2:continuity=.35
        evidence.append({'start':start,'end':end,'hook':hook,'vocal':vocal,'rhythm':rhythm,
                         'continuity':continuity,'setup_start':narrative_start,'matches':matches,
                         'pause':pause,'rate':rate,'role':role,'intensity':intensity,'dynamic':dynamic})
        if setup:last_setup=seg
        previous_end=max(previous_end or 0,end)
    return evidence


def context_bounds(t,event_end,media,index,sound,visual,minimum,maximum,options,setup_start=None,*,times=None):
    """Prefer pauses/sentence ends and coarse scene samples within hard limits."""
    desired=max(minimum,min(maximum,max(30.,options.before+options.after)))
    a=max(0.,t-options.before)
    b=min(media.duration,max(a+desired,event_end+options.after))
    if setup_start is not None and b-setup_start<=maximum:a=max(0.,setup_start-.15)
    if b-a>maximum:
        a=max(0.,min(a,t-options.before));b=min(media.duration,a+maximum)
    if b-a<minimum:a=max(0.,b-minimum)
    # Nearby boundaries are indexed; only a bounded temporal window is examined.
    near=index.between(max(0,a-3),min(media.duration,b+3))
    starts=[max(0.,s['start']-.15) for s in near if s['start']<=t]
    ends=[min(media.duration,s['end']+.15) for s in near if s['end']>=event_end]
    # A gap between segments (or words) is an observable pause, not an emotion.
    words=index.words_between(max(0,a-3),min(media.duration,b+3))
    for left,right in zip(words,words[1:]):
        if right['start']-left['end']>=.4:
            starts.append(max(0.,right['start']-.1));ends.append(min(media.duration,left['end']+.1))
    st,vt=times if times is not None else ([p['t'] for p in sound],[p['t'] for p in visual])
    for p in sound[bisect.bisect_left(st,max(0,a-2)):bisect.bisect_right(st,min(t,a+2))]:
        if p['db']<-50:starts.append(p['t']+.5)
    for p in sound[bisect.bisect_left(st,max(event_end,b-2)):bisect.bisect_right(st,min(media.duration,b+2))]:
        if p['db']<-50:ends.append(p['t']+.5)
    for p in visual[bisect.bisect_left(vt,max(0,a-2)):bisect.bisect_right(vt,min(media.duration,b+2))]:
        if p.get('possible_transition'):
            if p['t']<=t:starts.append(p['t'])
            if p['t']>=event_end:ends.append(p['t'])
    # Prefer starts/ends within 3s. A farther phrase edge is used when a proposed
    # bound crosses it, provided the whole interval still fits the hard limits.
    starts=[x for x in starts if 0<=x<=t and abs(x-a)<=3]
    ends=[x for x in ends if event_end<=x<=media.duration and abs(x-b)<=3]
    options_a=sorted(set([a,*starts]),key=lambda x:abs(x-a))
    options_b=sorted(set([b,*ends]),key=lambda x:abs(x-b))
    # Existing cut points receive a small penalty to favor a nearby real boundary.
    pairs=[(x,y) for x in options_a for y in options_b if minimum-1e-6<=y-x<=maximum+1e-6 and x<=t<=y and y>=event_end]
    if pairs:
        a,b=min(pairs,key=lambda p:abs(p[0]-a)+abs(p[1]-b)+(.8 if p[0]==a else 0)+(.8 if p[1]==b else 0))
    # Never cut inside a timed word. With no word times, treat the entire
    # transcription segment as atomic; dropping a candidate is safer than
    # pretending a hard duration limit preserves an overlong sentence.
    units=index.units;unit_starts=index.unit_starts;longest=index.longest_unit
    near_units=units[bisect.bisect_left(unit_starts,a-longest):bisect.bisect_right(unit_starts,b)]
    for unit in near_units:
        if unit['start']<a<unit['end']:a=max(0.,unit['start']-.05)
        if unit['start']<b<unit['end']:b=min(media.duration,unit['end']+.05)
    if b-a>maximum:
        # End before the word/segment that would cross the maximum duration.
        b=a+maximum
        for unit in near_units:
            if unit['start']<b<unit['end']:b=unit['start']
    if not minimum-1e-6<=b-a<=maximum+1e-6 or not a<=t<=b or b<event_end:return None
    return a,b
