"""Editable subtitle tracks in original-video seconds; Whisper data stays immutable."""
from copy import deepcopy
from dataclasses import asdict,dataclass,fields
import math
import re

EFFECTS={'classic':'Clássico','highlight':'Palavra Destacada','pop':'Pop/Zoom','karaoke':'Karaokê'}
MAX_CUES=5000


@dataclass
class CaptionStyle:
    effect: str='classic'
    font: str='Arial'
    size: float=48.
    color: str='#FFFFFF'
    highlight: str='#278CFF'
    outline_color: str='#101010'
    shadow_color: str='#000000'
    outline: float=2.
    shadow: float=1.
    bold: bool=True
    x: float=.5
    y: float=.84

    def validate(self):
        if self.effect not in EFFECTS:raise ValueError('Escolha um dos quatro estilos de legenda.')
        if not isinstance(self.font,str) or not 1<=len(self.font.strip())<=80 or any(c in self.font for c in ',;{}\\\r\n'):
            raise ValueError('Nome de fonte inválido.')
        for name,low,high in [('size',12,160),('outline',0,12),('shadow',0,12),('x',0,1),('y',0,1)]:
            value=getattr(self,name)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
                raise ValueError(f'Valor inválido em {name}: use de {low} a {high}.')
        for name in ('color','highlight','outline_color','shadow_color'):
            if not isinstance(getattr(self,name),str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',getattr(self,name)):
                raise ValueError('Cores devem usar o formato #RRGGBB.')
        if not isinstance(self.bold,bool):raise ValueError('Opção de negrito inválida.')
        return self

    def record(self):self.validate();return asdict(self)

    @classmethod
    def from_record(cls,value=None):
        if isinstance(value,cls):value=value.record()
        if value is None:value={}
        if not isinstance(value,dict):raise ValueError('Estilo de legenda inválido.')
        try:return cls(**value).validate()
        except TypeError:raise ValueError('Estilo de legenda contém campos incompatíveis.') from None


def style_for(track,cue=None):
    base=CaptionStyle.from_record(track.get('style')).record()
    if cue and cue.get('style'):base.update(cue['style'])
    return CaptionStyle.from_record(base)


def _text(words):
    return re.sub(r'\s+([,.;:!?])',r'\1',' '.join(w['word'].strip() for w in words)).strip()


def _finite(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def validate_track(track,duration=None):
    if not isinstance(track,dict) or track.get('version')!=1 or track.get('time_reference')!='original':
        raise ValueError('Faixa de legendas inválida ou com referência temporal incompatível.')
    if not isinstance(track.get('enabled'),bool) or not isinstance(track.get('preserve_audio',True),bool):raise ValueError('Opções da faixa de legendas inválidas.')
    CaptionStyle.from_record(track.get('style'))
    cues=track.get('cues')
    if not isinstance(cues,list) or len(cues)>MAX_CUES:raise ValueError('Use até 5000 blocos de legenda por corte.')
    ids=set();previous=0.
    for cue in sorted(cues,key=lambda c:c.get('start',-1) if isinstance(c,dict) else -1):
        if not isinstance(cue,dict):raise ValueError('Bloco de legenda inválido.')
        ident=cue.get('id');a,b=cue.get('start'),cue.get('end')
        if isinstance(ident,bool) or not isinstance(ident,int) or ident<=0 or ident in ids:raise ValueError('Identificadores de legenda inválidos ou duplicados.')
        ids.add(ident)
        if not _finite(a) or not _finite(b) or not 0<=a<b or duration is not None and b>duration+1e-6:
            raise ValueError('Tempos de legenda inválidos ou fora do vídeo.')
        if a<previous-1e-6:raise ValueError('Há blocos de legenda sobrepostos. Ajuste início/fim antes de continuar.')
        previous=b
        if not isinstance(cue.get('text'),str) or not cue['text'].strip() or len(cue['text'])>4096:
            raise ValueError('Cada bloco precisa de texto, com até 4096 caracteres.')
        override=cue.get('style',{})
        if not isinstance(override,dict) or set(override)-{f.name for f in fields(CaptionStyle)}:raise ValueError('Estilo individual inválido.')
        style_for(track,cue)
        words=cue.get('words',[])
        if not isinstance(words,list) or len(words)>500:raise ValueError('Lista de palavras inválida.')
        last=a
        for word in words:
            if not isinstance(word,dict) or not isinstance(word.get('word'),str) or not word['word'].strip():raise ValueError('Texto de palavra inválido.')
            x,y=word.get('start'),word.get('end')
            if not _finite(x) or not _finite(y) or not a-1e-6<=x<=y<=b+1e-6 or x<last-1e-6:
                raise ValueError('Ajuste os tempos por palavra dentro do bloco, em ordem e sem sobreposição.')
            last=y
        if words and _text(words)!=' '.join(cue['text'].split()):raise ValueError('As palavras e o texto do bloco não correspondem. Sincronize as palavras após corrigir o texto.')
    return track


def generate_track(cut,speech,style=None):
    # Reuse Radar's existing grouping and indexed word lookup, without ASR.
    from .export import subtitle_entries
    from .intelligence import SpeechIndex
    index=SpeechIndex(speech);cues=[]
    for entry in subtitle_entries(cut,speech):
        a,b=entry['start'],entry['end']
        words=[{**w,'start':max(a,w['start']),'end':min(b,w['end'])} for w in index.words_between(a,b)]
        # Some models join punctuation to a separate zero-duration token. If
        # the available timed words do not match, keep an honest phrase cue.
        if _text(words)!=entry['text'] or any(w['start']<previous['end']-1e-6 for previous,w in zip(words,words[1:])):words=[]
        cue={'id':len(cues)+1,'start':a,'end':b,'text':entry['text'],'words':words,'style':{}}
        if cues and a<cues[-1]['end']:
            cue['start']=cues[-1]['end']
            cue['words']=[]
        if cue['end']>cue['start']:cues.append(cue)
    track={'version':1,'time_reference':'original','enabled':True,'preserve_audio':True,
           'style':CaptionStyle.from_record(style).record(),'cues':cues}
    return validate_track(track)


def entries_for_cut(cut,track=None,*,include_disabled=False):
    track=cut.captions if track is None else track
    validate_track(track)
    if not track['enabled'] and not include_disabled:return []
    result=[]
    for cue in sorted(track['cues'],key=lambda c:c['start']):
        a,b=max(cut.start,cue['start']),min(cut.end,cue['end'])
        if b<=a:continue
        words=[{**w,'start':max(a,w['start']),'end':min(b,w['end'])} for w in cue.get('words',[]) if w['end']>a and w['start']<b]
        # Editing a Short's bounds must never leak words from outside it.
        text=_text(words) if cue.get('words') else cue['text']
        if not text:continue
        result.append({**deepcopy(cue),'start':a,'end':b,'text':text,'words':words,
                       'cue_start':cue['start'],'style':style_for(track,cue).record()})
    return result


def update_cue(track,ident,*,text,start,end):
    result=deepcopy(track);cue=next((c for c in result['cues'] if c['id']==ident),None)
    if cue is None:raise ValueError('Selecione um bloco de legenda.')
    if not _finite(start) or not _finite(end) or not 0<=start<end:raise ValueError('Use um intervalo de legenda válido.')
    text=' '.join(text.split())
    if not text:raise ValueError('Digite o texto da legenda.')
    words=cue.get('words',[]);tokens=text.split()
    if words and len(tokens)==len(words):
        ratio=(end-start)/(cue['end']-cue['start'])
        cue['words']=[{'start':start+(w['start']-cue['start'])*ratio,
                       'end':start+(w['end']-cue['start'])*ratio,'word':token} for w,token in zip(words,tokens)]
        if _text(cue['words'])!=text:cue['words']=[]
    elif text!=cue['text']:cue['words']=[]
    elif words:
        ratio=(end-start)/(cue['end']-cue['start'])
        cue['words']=[{**w,'start':start+(w['start']-cue['start'])*ratio,'end':start+(w['end']-cue['start'])*ratio} for w in words]
    cue.update(start=start,end=end,text=text)
    result['cues'].sort(key=lambda c:c['start'])
    return validate_track(result)


def set_style(track,style,ident=None):
    result=deepcopy(track);style=CaptionStyle.from_record(style).record()
    if ident is None:result['style']=style
    else:
        cue=next((c for c in result['cues'] if c['id']==ident),None)
        if cue is None:raise ValueError('Selecione um bloco para aplicar o estilo individual.')
        cue['style']=style
    return validate_track(result)


def set_words(track,ident,words):
    result=deepcopy(track);cue=next((c for c in result['cues'] if c['id']==ident),None)
    if cue is None:raise ValueError('Selecione um bloco para sincronizar palavras.')
    cue['words']=deepcopy(words)
    return validate_track(result)
