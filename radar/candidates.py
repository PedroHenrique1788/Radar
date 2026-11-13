"""Explainable local salience, indexed by time instead of rescanning the movie."""
import bisect
import re
import numpy as np
from .model import Cut,timestamp
from .profiles import AnalysisOptions
from .media import check_cancel

HOOKS=re.compile(r'\b(meu deus|olha isso|que absurdo|quase morri|olha|como|por que|porque|quê|não acredito|consegui|conseguimos|cuidado|espera|agora|nossa|caramba|mano|quase|finalmente)\b',re.I)


def generate(media,sound,visual,speech,count=10,minimum=15.,maximum=60.,*,options=None,cancel=None,progress=lambda *a:None):
    if not 1<=count<=20 or not 1<=minimum<=maximum<=600:
        raise ValueError('Use 1–20 sugestões e durações entre 1 e 600 s, mínima ≤ máxima.')
    if media.duration<minimum:return []
    opts=AnalysisOptions.from_record(options)
    sound=sorted(sound if opts.audio else [],key=lambda p:p['t'])
    visual=sorted(visual if opts.visual else [],key=lambda p:p['t'])
    speech=sorted(speech,key=lambda p:p['start'])
    available={'gancho_fala':bool(speech),'fala_completa':bool(speech),
               'variação_sonora':bool(sound),'atividade_visual':bool(visual)}
    total=sum(opts.weights[k] for k in opts.weights if available[k])
    if not total:
        if not any(available.values()):return []
        raise ValueError('Os pesos dos sinais disponíveis somam zero. Ative outro módulo ou ajuste os pesos.')
    weights={k:100*opts.weights[k]/total if available[k] else 0 for k in opts.weights}
    db=np.asarray([s['db'] for s in sound],dtype=float)
    baseline=float(np.median(db)) if len(db) else -60.
    spread=max(6.,float(np.std(db))) if len(db) else 6.
    st=[s['t'] for s in sound];audio_strength=[]
    events={}
    for index,s in enumerate(sound):
        if index%200==0:check_cancel(cancel)
        local=float(np.mean(db[max(0,index-3):index])) if index else baseline
        strength=min(1.,max(0.,(s['db']-max(baseline,local))/(2*spread))) if s['db']>-45 else 0.
        if local<-50 and s['db']>-35:strength=max(strength,.5)
        audio_strength.append(strength)
        if strength>.15:events.setdefault(s['t'],{})['audio']=strength
    changes=np.asarray([v['change'] for v in visual],dtype=float)
    visual_baseline=float(np.median(changes)) if len(changes) else 0.
    visual_spread=max(.02,float(np.std(changes))*2) if len(changes) else .02
    vt=[v['t'] for v in visual]
    visual_strength=np.clip((changes-visual_baseline)/visual_spread,0,1)
    for index,v in enumerate(visual):
        if index%200==0:check_cancel(cancel)
        if v['change']>.03 and visual_strength[index]>.15:
            events.setdefault(v['t'],{})['visual']=float(visual_strength[index])
    for seg in speech:
        hook=len(HOOKS.findall(seg['text']))
        if hook or '?' in seg['text'] or '!' in seg['text']:
            events.setdefault(seg['start'],{})['speech']=min(1.,.4+hook*.2)
    # Rank a bounded pool before expensive boundary/context work. All sampled
    # signals still participate in event detection; this is not video truncation.
    pool=sorted(events.items(),key=lambda item:sum(item[1].values()),reverse=True)[:min(1000,max(100,count*20))]
    starts=[s['start'] for s in speech]
    longest=max((s['end']-s['start'] for s in speech),default=0)
    words=sorted((w for s in speech for w in s.get('words',[])),key=lambda w:w['start'])
    word_starts=[w['start'] for w in words]
    longest_word=max((w['end']-w['start'] for w in words),default=0)
    audio_strength=np.asarray(audio_strength,dtype=float)

    def window_max(times,values,a,b):
        lo=bisect.bisect_left(times,a);hi=bisect.bisect_right(times,b)
        return float(np.max(values[lo:hi])) if hi>lo else 0.

    candidates=[]
    for index,(t,signals) in enumerate(pool):
        check_cancel(cancel)
        start=max(0.,t-opts.before)
        end=min(media.duration,start+min(maximum,max(minimum,30.,opts.before+opts.after)))
        near=speech[bisect.bisect_left(starts,start-longest):bisect.bisect_right(starts,end)]
        near=[s for s in near if s['end']>start and s['start']<end]
        if near:
            start=max(0.,min(start,near[0]['start']-.15))
            end=min(media.duration,max(end,max(s['end'] for s in near)+.15))
        if end-start>maximum:
            start=max(start,min(t-opts.before,end-maximum))
            end=min(media.duration,start+maximum)
        if end-start<minimum:start=max(0.,end-minimum)
        for w in words[bisect.bisect_left(word_starts,start-longest_word):bisect.bisect_right(word_starts,end)]:
            if w['start']<start<w['end']:start=max(0.,w['start']-.05)
            if w['start']<end<w['end']:end=min(media.duration,w['end']+.05)
        if end-start>maximum:
            end=start+maximum
            overlapping=words[bisect.bisect_left(word_starts,end-longest_word):bisect.bisect_right(word_starts,end)]
            for w in overlapping:
                if w['start']<end<w['end']:end=w['start']
        if not minimum-1e-6<=end-start<=maximum+1e-6 or not start<=t<=end:continue
        text=' '.join(s['text'] for s in near if s['start']>=start and s['end']<=end)
        a=window_max(st,audio_strength,start,end)
        v=window_max(vt,visual_strength,start,end)
        # Raw game audio is not proof of a creator's emotional reaction.
        if not text and v<.1:a*=.6
        hook=min(1.,.4+len(HOOKS.findall(text))*.2) if HOOKS.search(text) or '?' in text or '!' in text else 0.
        strength={'gancho_fala':hook,'variação_sonora':a,'atividade_visual':v,
                  'fala_completa':min(1.,len(text.split())/35)}
        components={k:round(weights[k]*strength[k],1) for k in weights}
        score=round(min(100.,sum(components.values())),1)
        if score>=18:
            reason='; '.join(f'{k.replace("_"," ")}: {value:g} pontos (peso efetivo {weights[k]:.1f}%)' for k,value in components.items() if weights[k])
            reason+='. Relevância interna estimada; contexto, emoção e eventos do jogo não confirmados.'
            title=text[:80] if text else f'Variação de sinais em {timestamp(t)}'
            candidates.append(Cut(0,start,end,score,title,reason,text,components=components))
        progress(index+1,len(pool))
    chosen=[]
    for cut in sorted(candidates,key=lambda c:(-c.score,c.start)):
        if all(max(0.,min(cut.end,c.end)-max(cut.start,c.start))/min(c.duration,cut.duration)<.35 for c in chosen):
            cut.id=len(chosen)+1;chosen.append(cut)
            if len(chosen)==count:break
    return chosen
