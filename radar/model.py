"""Tempos em segundos relativos ao primeiro quadro de vídeo original."""
from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_HALF_UP
import math


def timestamp(seconds):
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError('Tempo deve ser finito e não negativo.')
    ms = int((Decimal(str(seconds)) * 1000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f'{h:02}:{m:02}:{s:02}.{ms:03}'


def parse_time(text):
    parts = text.strip().split(':')
    if len(parts) != 3:
        raise ValueError('Use HH:MM:SS.mmm.')
    h, m, s = int(parts[0]), int(parts[1]), float(parts[2].replace(',', '.'))
    if h < 0 or not 0 <= m < 60 or not 0 <= s < 60:
        raise ValueError('Horário inválido.')
    return h * 3600 + m * 60 + s


@dataclass
class Media:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    codec: str
    origin: float
    audio: list
    video_index: int
    variable_fps: bool = False
    source_id: str = ''
    analysis_audio: dict = field(default_factory=dict)


@dataclass
class Cut:
    id: int
    start: float
    end: float
    score: float
    title: str
    reason: str
    transcript: str = ''
    editing: str = 'Revise o contexto e as legendas antes de publicar.'
    components: dict = field(default_factory=dict)
    favorite: bool = False
    review_state: str = 'pending'
    manual: bool = False
    framing: dict = field(default_factory=dict)
    user_edited: bool = False
    captions: dict = field(default_factory=dict)

    @property
    def duration(self):
        return self.end - self.start

    @property
    def category(self):
        if self.manual:return 'Manual'
        return 'Alto potencial' if self.score >= 70 else 'Médio potencial' if self.score >= 45 else 'Baixo potencial'

    def validate(self, duration):
        if not all(math.isfinite(v) for v in (self.start, self.end)) or not 0 <= self.start < self.end <= duration + 1e-6:
            raise ValueError('Intervalo fora do vídeo ou duração inválida.')

    def record(self, media):
        self.validate(media.duration)
        return {**asdict(self), 'start_time': timestamp(self.start), 'end_time': timestamp(self.end),
                'source_id':media.source_id,'source':media.path,
                'duration': self.duration, 'category': self.category, 'fps': media.fps,
                'nominal_start_frame': round(self.start * media.fps),
                'nominal_end_frame': round(self.end * media.fps),
                'frame_note': 'Índices nominais; em VFR use os timestamps/PTS.',
                'timeline_origin_pts': media.origin}
