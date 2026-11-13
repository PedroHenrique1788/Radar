"""Explainable local salience, indexed by time instead of rescanning the movie."""
import bisect
import numpy as np
from .model import Cut,timestamp
from .profiles import AnalysisOptions
from .media import check_cancel
from .intelligence import SpeechIndex,PhraseMatcher,speech_evidence,context_bounds
from .audio_source import audio_role


def generate(media,sound,visual,speech,count=10,minimum=15.,maximum=60.,*,options=None,cancel=None,progress=lambda *a:None):
    if not 1<=count<=20 or not 1<=minimum<=maximum<=600:
        raise ValueError('Use 1–20 sugestões e durações entre 1 e 600 s, mínima ≤ máxima.')
    if media.duration<minimum:return []
    opts=AnalysisOptions.from_record(options)
    sound=sorted(sound if opts.audio else [],key=lambda p:p['t'])
    visual=sorted(visual if opts.visual else [],key=lambda p:p['t'])
    speech=sorted(speech,key=lambda p:p['start'])
    role=media.analysis_audio.get('role') or audio_role(media,'mix',opts)
    evidence=speech_evidence(sound,speech,role,opts.phrases,cancel)
    evidence_starts=[e['start'] for e in evidence]
    longest_evidence=max((e['end']-e['start'] for e in evidence),default=0.)
    speech_index=SpeechIndex(speech)
    matcher=PhraseMatcher(opts.phrases)
    available={'gancho_fala':bool(speech),'fala_completa':bool(speech),
               'variação_sonora':bool(sound),'atividade_visual':bool(visual),
               'reação_vocal':bool(sound) and (role=='microphone' or bool(speech)),
               'ritmo_fala':sum(e['rate'] is not None for e in evidence)>=2,
               'continuidade':bool(speech)}
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
    contexts={}
    for e in evidence:
        if max(e['hook'],e['vocal'],e['rhythm'],e['continuity'])>.15:
            events.setdefault(e['start'],{})['speech']=max(e['hook'],e['vocal'],e['rhythm'],e['continuity'])
            contexts[e['start']]=e
    # Rank a bounded pool before expensive boundary/context work. All sampled
    # signals still participate in event detection; this is not video truncation.
    pool=sorted(events.items(),key=lambda item:sum(item[1].values()),reverse=True)[:min(1000,max(100,count*20))]
    audio_strength=np.asarray(audio_strength,dtype=float)

    def window_max(times,values,a,b):
        lo=bisect.bisect_left(times,a);hi=bisect.bisect_right(times,b)
        return float(np.max(values[lo:hi])) if hi>lo else 0.

    candidates=[]
    for number,(t,signals) in enumerate(pool):
        check_cancel(cancel)
        event=contexts.get(t,{})
        event_end=min(media.duration,event.get('end',t))
        bounds=context_bounds(t,event_end,media,speech_index,sound,visual,minimum,maximum,opts,event.get('setup_start'),times=(st,vt))
        if bounds is None:
            progress(number+1,len(pool));continue
        start,end=bounds
        text=speech_index.text(start,end)
        near_evidence=[e for e in evidence[bisect.bisect_left(evidence_starts,start-longest_evidence):bisect.bisect_right(evidence_starts,end)] if e['end']>start and e['start']<end]
        a=window_max(st,audio_strength,start,end)
        v=window_max(vt,visual_strength,start,end)
        # Raw game audio is not proof of a creator's emotional reaction.
        if not text and v<.1:a*=.6
        matches=matcher.matches(text)
        hook=min(1.,.45+len(matches)*.18) if matches else .35 if '?' in text or '!' in text else 0.
        vocal=max((e['vocal'] for e in near_evidence),default=0.)
        if role=='microphone' and not speech:vocal=a*.65
        rhythm=max((e['rhythm'] for e in near_evidence),default=0.)
        narrative=max((e['continuity'] if e['setup_start'] is None or e['setup_start']>=start else 0. for e in near_evidence),default=0.)
        complete=min(1.,len(text.split())/20)*(.9 if text.endswith(('.', '!', '?')) else .6)
        strength={'gancho_fala':hook,'variação_sonora':a,'atividade_visual':v,
                  'fala_completa':complete,'reação_vocal':vocal,'ritmo_fala':rhythm,'continuidade':narrative}
        components={k:round(weights[k]*strength[k],1) for k in weights}
        score=round(min(100.,sum(components.values())),1)
        if score>=18:
            reason='; '.join(f'{k.replace("_"," ")}: {value:g} pontos (peso efetivo {weights[k]:.1f}%)' for k,value in components.items() if weights[k])
            if matches:reason+='; expressões: '+', '.join(matches[:8])
            if vocal>.1:reason+='; possível variação vocal no microfone (estimativa)' if role=='microphone' else '; variação sonora durante fala no mix (origem incerta)'
            if rhythm>.15:reason+='; mudança de ritmo medida por palavras/segundo'
            if any(.4<=e['pause']<=3 and e['hook'] for e in near_evidence):reason+='; pausa antes da expressão'
            if narrative>=.5:reason+='; preparação e desfecho lexicais preservados no intervalo'
            reason+='. Relevância interna estimada; contexto, emoção e eventos do jogo não confirmados.'
            title=text[:80] if text else f'Variação de sinais em {timestamp(t)}'
            candidates.append(Cut(0,start,end,score,title,reason,text,components=components))
        progress(number+1,len(pool))
    chosen=[]
    for cut in sorted(candidates,key=lambda c:(-c.score,c.start)):
        if all(max(0.,min(cut.end,c.end)-max(cut.start,c.start))/min(c.duration,cut.duration)<.35 for c in chosen):
            cut.id=len(chosen)+1;chosen.append(cut)
            if len(chosen)==count:break
    return chosen
