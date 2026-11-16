"""Conservative, explainable proposals; only human decisions remove source time."""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
import math
import re

import numpy as np

from .media import check_cancel
from .model import Cut

MODES={'conservative':'Conservador','balanced':'Equilibrado','dynamic':'Dinâmico','mark':'Somente marcar'}
PRESETS={'conservative':(12.,3.,3.),'balanced':(8.,2.,2.),'dynamic':(5.,1.,1.),'mark':(12.,3.,3.)}
STATES={'keep':'Manter','remove':'Sugerir remoção','review':'Revisar manualmente'}
DECISIONS={'pending':'Pendente','accepted':'Remoção aprovada','rejected':'Preservado por você'}


def number(value,lo,hi):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and lo<=value<=hi


@dataclass
class PreEditOptions:
    mode: str='conservative'
    min_pause: float=12.
    sensitivity: float=.5
    before: float=3.
    after: float=3.
    protect_narrative: bool=True
    intensity: float=.5

    def validate(self):
        if self.mode not in MODES or not isinstance(self.protect_narrative,bool):raise ValueError('Modo de pré-edição inválido.')
        for key,lo,hi in [('min_pause',2,300),('sensitivity',0,1),('before',0,30),('after',0,30),('intensity',0,1)]:
            if not number(getattr(self,key),lo,hi):raise ValueError(f'Parâmetro de pré-edição inválido: {key}.')
        return self

    def record(self):return asdict(self.validate())

    @classmethod
    def from_record(cls,value=None):
        if isinstance(value,cls):value=value.record()
        try:return cls(**(value or {})).validate()
        except TypeError:raise ValueError('Configuração de pré-edição incompatível.') from None

    @classmethod
    def preset(cls,mode):
        if mode not in PRESETS:raise ValueError('Preset inválido.')
        pause,before,after=PRESETS[mode]
        return cls(mode=mode,min_pause=pause,before=before,after=after)


def track_layout(media):
    rows=[]
    for audio in media.audio:
        title=audio.get('title','')
        role='microphone' if re.search(r'\b(mic|microfone|microphone|voz|voice)\b',title,re.I) else 'game' if re.search(r'\b(jogo|game|desktop)\b',title,re.I) else 'mix' if re.search(r'\b(mix|mixed|completo)\b',title,re.I) else 'unknown'
        rows.append({**deepcopy(audio),'role':role,'export':True})
    # Labels are declarations, not content recognition. Keep every source track
    # in the project while excluding a labelled mix from the initial export.
    if any(r['role']=='microphone' for r in rows) and any(r['role']=='game' for r in rows):
        for r in rows:
            if r['role']=='mix':r['export']=False
    return rows


@dataclass
class Suggestion:
    id: int
    start: float
    end: float
    classification: str
    reason: str
    confidence: float
    decision: str='pending'

    def validate(self,duration):
        if not isinstance(self.id,int) or isinstance(self.id,bool) or self.id<=0:raise ValueError('ID de sugestão inválido.')
        if not number(self.start,0,duration) or not number(self.end,0,duration) or self.end<=self.start:raise ValueError('Intervalo de pré-edição fora do original.')
        if self.classification not in STATES or self.decision not in DECISIONS or not number(self.confidence,0,1):raise ValueError('Estado ou confiança heurística inválidos.')
        if self.classification=='keep' and self.decision=='accepted':raise ValueError('Trecho protegido não pode ser aprovado para remoção.')
        if not isinstance(self.reason,str) or len(self.reason)>4000:raise ValueError('Motivo inválido.')
        return self


@dataclass
class PreEdit:
    source_id: str
    duration: float
    tracks: list=field(default_factory=list)
    options: dict=field(default_factory=dict)
    suggestions: list=field(default_factory=list)
    markers: list=field(default_factory=list)
    audio_analysis: dict=field(default_factory=dict)
    history: list=field(default_factory=list)
    position: int=0

    def validate(self):
        if not isinstance(self.source_id,str) or not number(self.duration,.001,1e8):raise ValueError('Fonte de pré-edição inválida.')
        opts=PreEditOptions.from_record(self.options)
        if len(self.suggestions)>10000 or len(self.history)>500 or len(self.markers)>4000:raise ValueError('Pré-edição excede os limites do projeto.')
        last=0.;ids=set()
        for s in self.suggestions:
            s.validate(self.duration)
            if s.id in ids or s.start<last-1e-6:raise ValueError('Sugestões duplicadas, fora de ordem ou sobrepostas.')
            if opts.mode=='mark' and s.decision=='accepted':raise ValueError('Somente marcar não permite remoções.')
            ids.add(s.id);last=s.end
        if not isinstance(self.position,int) or isinstance(self.position,bool) or not 0<=self.position<=len(self.history):raise ValueError('Histórico inválido.')
        for h in self.history:
            if not isinstance(h,dict) or set(h)!={'id','before','after'} or h['id'] not in ids:raise ValueError('Histórico incompatível.')
            for k in ('before','after'):
                row=Suggestion(**h[k]).validate(self.duration)
                if row.id!=h['id']:raise ValueError('ID do histórico incompatível.')
        track_ids=set()
        for r in self.tracks:
            if not isinstance(r,dict) or not isinstance(r.get('index'),int) or r['index'] in track_ids or r.get('role') not in ('microphone','game','mix','unknown') or not isinstance(r.get('export'),bool):raise ValueError('Faixas da pré-edição inválidas.')
            track_ids.add(r['index'])
        for marker in self.markers:
            if not isinstance(marker,dict) or not number(marker.get('time'),0,self.duration) or marker.get('kind') not in ('important','short') or not isinstance(marker.get('label'),str):raise ValueError('Marcador inválido.')
        return self

    def record(self):
        self.validate()
        return asdict(self)

    @classmethod
    def from_record(cls,value):
        try:
            data=deepcopy(value);data['suggestions']=[Suggestion(**s) for s in data.get('suggestions',[])]
            return cls(**data).validate()
        except (TypeError,KeyError,AttributeError):raise ValueError('Pré-edição incompatível.') from None

    def edit(self,ident,*,decision=None,start=None,end=None):
        self.validate()
        row=next((s for s in self.suggestions if s.id==ident),None)
        if row is None:raise ValueError('Sugestão não encontrada.')
        before=asdict(row);after=deepcopy(before)
        for k,v in [('decision',decision),('start',start),('end',end)]:
            if v is not None:after[k]=v
        replacement=Suggestion(**after)
        index=self.suggestions.index(row);self.suggestions[index]=replacement
        try:self.validate()
        except Exception:
            self.suggestions[index]=row;raise
        if after==before:return
        self.history=self.history[:self.position]+[{'id':ident,'before':before,'after':after}]
        self.history=self.history[-500:];self.position=len(self.history)

    def _travel(self,redo):
        if redo and self.position==len(self.history) or not redo and self.position==0:return False
        i=self.position if redo else self.position-1;change=self.history[i]
        rows=deepcopy(self.suggestions);old=self.position
        self.suggestions=[Suggestion(**deepcopy(change['after' if redo else 'before'])) if s.id==change['id'] else s for s in self.suggestions]
        self.position+=1 if redo else -1
        try:self.validate()
        except Exception:self.suggestions=rows;self.position=old;raise
        return True

    def undo(self):return self._travel(False)
    def redo(self):return self._travel(True)

    def kept(self):
        self.validate();start=0.;result=[]
        for s in self.suggestions:
            if s.decision!='accepted':continue
            if s.start>start:result.append((start,s.start))
            start=s.end
        if start<self.duration:result.append((start,self.duration))
        return result

    @property
    def proposed_duration(self):return sum(b-a for a,b in self.kept())

    def cuts(self):
        return [Cut(i,a,b,0,'Pré-edição', 'Intervalo mantido após revisão humana.') for i,(a,b) in enumerate(self.kept(),1)]

    def proposed_time(self,original):
        elapsed=0.
        for a,b in self.kept():
            if original<=b:return elapsed+max(0.,original-a)
            elapsed+=b-a
        return elapsed


def detect(media,tracks,sounds,visual,speech,options=None,cancel=None,markers=None):
    """Second bins, full-track protection and contextual margins. Not semantic VAD."""
    opts=PreEditOptions.from_record(options);duration=media.duration;n=math.ceil(duration)
    levels={};thresholds={}
    for r in tracks:
        check_cancel(cancel)
        points=sounds.get(r['index'],[]);db=np.full(n,np.nan)
        for p in points:
            i=int(p['t'])
            if 0<=i<n and number(p.get('db'),-200,20):db[i]=p['db']
        known=db[np.isfinite(db)]
        threshold=min(-45.,max(-72.,float(np.percentile(known,90))-30.+12*opts.sensitivity)) if len(known) else -60.
        levels[r['index']]=db;thresholds[r['index']]=threshold
    mic=[r['index'] for r in tracks if r['role']=='microphone'];game=[r['index'] for r in tracks if r['role'] in ('game','mix')]
    # Use microphone pauses as opportunities, but NEVER as removal evidence.
    candidates=mic or list(levels)
    quiet=np.ones(n,dtype=bool) if candidates else np.ones(n,dtype=bool)
    for idx in candidates:quiet &= levels[idx]<=thresholds[idx]
    movement=np.full(n,np.nan)
    for v in visual:
        i=int(v['t'])
        if 0<=i<n:movement[i]=max(0.,v['change']) if np.isnan(movement[i]) else max(movement[i],v['change'])
    # A sample represents only its own second; missing bins stay uncertain.
    if visual:
        times=sorted(v['t'] for v in visual)
        step=float(np.median(np.diff(times))) if len(times)>1 else 1.
        if 1<step<=4:
            for i in range(1,n):
                if np.isnan(movement[i]) and i%max(1,round(step))!=0:movement[i]=movement[i-1]
    protected=np.zeros(n,dtype=bool)
    for s in speech:
        a=max(0,math.floor(s['start']-opts.before));b=min(n,math.ceil(s['end']+opts.after))
        protected[a:b]=True
    for marker in markers or []:
        if marker.get('kind')=='important':
            a=max(0,math.floor(marker['time']-opts.before));b=min(n,math.ceil(marker['time']+opts.after+1))
            protected[a:b]=True
    # Classify each bin before grouping: a silent mic can span both a voiced
    # cutscene and a genuinely quiet loading screen. A single long mic run must
    # not hide internal evidence changes.
    all_known=np.ones(n,dtype=bool) if levels else np.zeros(n,dtype=bool)
    all_quiet=np.ones(n,dtype=bool) if levels else np.zeros(n,dtype=bool)
    audible_game=np.zeros(n,dtype=bool)
    for k,x in levels.items():
        all_known &= np.isfinite(x);all_quiet &= x<=thresholds[k]
        if k in game:audible_game |= x>thresholds[k]
    static=np.isfinite(movement) & (movement<(.003 if opts.mode=='conservative' else .005 if opts.mode in ('balanced','mark') else .008))
    labels=np.full(n,2,dtype=np.uint8)  # 0 keep, 1 removal opportunity, 2 review
    labels[all_known & all_quiet & static & (bool(game) or not opts.protect_narrative)]=1
    labels[audible_game | protected]=0
    rows=[];i=0
    required=opts.min_pause*(1.5-.5*opts.intensity)
    while i<n:
        if i%200==0:check_cancel(cancel)
        if not quiet[i]:i+=1;continue
        a=i;label=labels[i]
        while i<n and quiet[i] and labels[i]==label:i+=1
        b=min(duration,float(i))
        if b-a<required:continue
        left=a+opts.after;right=b-opts.before
        if right-left<1:continue
        if label==0:
            classification='keep';reason='Fala/contexto, marcador importante ou áudio do jogo/mix ativo: preservar possível diálogo, cutscene ou exploração.';confidence=.8
        elif label==1:
            classification='remove';reason='Pausa longa, todas as faixas acusticamente baixas e imagem amostrada estática; revise narrativa antes de aceitar.';confidence=.7
            if not game:
                reason='Pausa audiovisual com proteção narrativa desativada por você; áudio do jogo não confirmado.';confidence=.5
        else:
            classification='review';reason='Evidência incompleta, imagem ativa ou áudio do jogo não identificado. Manter até revisão manual.';confidence=.3
        if len(rows)>=10000:raise ValueError('Mais de 10000 pausas: aumente a duração mínima ou divida o projeto.')
        rows.append(Suggestion(len(rows)+1,float(left),float(right),classification,reason,confidence))
    return PreEdit(media.source_id,duration,deepcopy(tracks),opts.record(),rows,deepcopy(markers or [])).validate()
