"""Small CPU-only analysis profiles; no generative service is required."""
from dataclasses import asdict, dataclass, field
import math
import os


ECONOMY='Modo Econômico — Lenovo MX110'
LEGACY_WEIGHTS={'gancho_fala','variação_sonora','atividade_visual','fala_completa'}
WEIGHTS={'gancho_fala':25.,'variação_sonora':15.,'atividade_visual':15.,'fala_completa':15.,
         'reação_vocal':15.,'ritmo_fala':5.,'continuidade':10.}
DEFAULT_PHRASES='meu deus\nolha isso\nque absurdo\nquase morri\nnão acredito\nconsegui\nconseguimos\ncuidado\nespera\nnossa\ncaramba\nfinalmente'


@dataclass
class AnalysisOptions:
    profile: str=ECONOMY
    threads: int=field(default_factory=lambda:min(2,os.cpu_count() or 1))
    max_processes: int=1
    memory_mb: int=1024
    sample_fps: float=.5
    visual_width: int=64
    batch_seconds: int=300
    audio: bool=True
    visual: bool=True
    before: float=5.
    after: float=10.
    weights: dict=field(default_factory=lambda:dict(WEIGHTS))
    external_audio: str=''
    external_offset: float=0.
    audio_role: str='auto'
    phrases: str=DEFAULT_PHRASES

    def validate(self):
        # Existing saved profiles keep their four chosen weights. New signals
        # receive their defaults; every available weight is then normalized.
        if isinstance(self.weights,dict) and set(self.weights)==LEGACY_WEIGHTS:
            self.weights={**WEIGHTS,**self.weights}
        if not isinstance(self.profile,str) or not 1<=len(self.profile)<=80:raise ValueError('Nome do perfil inválido.')
        if isinstance(self.threads,bool) or not isinstance(self.threads,int) or not 1<=self.threads<=max(1,min(16,os.cpu_count() or 1)):
            raise ValueError('Threads: escolha de 1 até o limite de CPUs lógicas (máximo 16).')
        if self.max_processes not in (1,2) or isinstance(self.max_processes,bool) or not isinstance(self.max_processes,int):
            raise ValueError('Limite de processos deve ser 1 ou 2. O motor executa etapas sequencialmente.')
        if not isinstance(self.memory_mb,int) or not 128<=self.memory_mb<=8192:
            raise ValueError('Limite de memória: de 128 a 8192 MB.')
        if isinstance(self.sample_fps,bool) or self.sample_fps not in (.25,.5,1.,2.):
            raise ValueError('Amostragem visual: 0,25, 0,5, 1 ou 2 quadros por segundo.')
        if self.visual_width not in (64,128,192) or not isinstance(self.batch_seconds,int) or not 16<=self.batch_seconds<=300 or self.batch_seconds%4:
            raise ValueError('Resolução: 64, 128 ou 192 pixels; lotes de 16 a 300 segundos em múltiplos de 4.')
        if not all(isinstance(v,bool) for v in (self.audio,self.visual)):
            raise ValueError('Escolha os módulos de áudio e imagem.')
        if not all(math.isfinite(v) and 0<=v<=120 for v in (self.before,self.after)):
            raise ValueError('Janelas de contexto: de 0 a 120 segundos.')
        if set(self.weights)!=set(WEIGHTS) or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0<=v<=100 for v in self.weights.values()) or not sum(self.weights.values()):
            raise ValueError('Pesos: valores de 0 a 100, com pelo menos um maior que zero.')
        if not isinstance(self.external_audio,str) or len(self.external_audio)>4096:
            raise ValueError('Caminho do áudio externo inválido.')
        if isinstance(self.external_offset,bool) or not isinstance(self.external_offset,(int,float)) or not math.isfinite(self.external_offset) or abs(self.external_offset)>86400:
            raise ValueError('Sincronização do áudio: use segundos entre -86400 e 86400.')
        if self.audio_role not in ('auto','microphone','mixed'):
            raise ValueError('Origem do áudio: auto, microphone ou mixed.')
        if not isinstance(self.phrases,str) or len(self.phrases)>8000:
            raise ValueError('Use até 8000 caracteres nas expressões personalizadas.')
        phrases=[p.strip() for p in self.phrases.replace(';','\n').splitlines() if p.strip()]
        if len(phrases)>100 or any(len(p)>80 for p in phrases):
            raise ValueError('Use até 100 expressões, com no máximo 80 caracteres cada.')
        return self

    def record(self):
        self.validate()
        return asdict(self)

    @classmethod
    def from_record(cls,value=None):
        if value is None:return cls().validate()
        if isinstance(value,cls):return cls(**value.record()).validate()
        if not isinstance(value,dict):raise ValueError('Perfil de análise inválido.')
        try:return cls(**value).validate()
        except TypeError:raise ValueError('Perfil de análise contém campos incompatíveis.') from None
