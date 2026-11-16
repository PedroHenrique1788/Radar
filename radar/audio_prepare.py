"""Measurement, advice and explicit sidecar processing are separate operations."""
from dataclasses import asdict,dataclass
import math
from pathlib import Path
import tempfile

from .export import safe_destination,publish_file,verify_source
from .media import executable,run,check_cancel
from .preedit import number


def measurements(points):
    if not points:return {'available':False}
    peak=max(p['peak_db'] for p in points)
    rms=10*math.log10(max(1e-12,sum(10**(p['db']/10) for p in points)/len(points)))
    return {'available':True,'rms_dbfs':round(rms,2),'peak_dbfs':round(peak,2),
            'possible_clipped_seconds':sum(p['peak_db']>=-.1 for p in points),
            'suggested_gain_db':round(max(-24.,min(12.,-6.-peak)),2),
            'note':'RMS/peak de análise mono 16 kHz; não é LUFS. Picos próximos de 0 dBFS sugerem revisão, não provam distorção.'}


@dataclass
class AudioTreatment:
    gain_db: float=0.
    compressor: bool=False
    normalize: bool=False
    gate: bool=False
    threshold_db: float=-18.
    ratio: float=2.
    gate_db: float=-55.
    target_lufs: float=-16.

    def filters(self):
        for k,lo,hi in [('gain_db',-24,12),('threshold_db',-40,-3),('ratio',1,6),('gate_db',-80,-35),('target_lufs',-24,-12)]:
            if not number(getattr(self,k),lo,hi):raise ValueError(f'Tratamento de áudio inválido: {k}.')
        if not all(isinstance(getattr(self,k),bool) for k in ('compressor','normalize','gate')):raise ValueError('Ativação de filtro inválida.')
        filters=[f'volume={self.gain_db}dB']
        if self.gate:filters.append(f'agate=threshold={10**(self.gate_db/20)}:ratio=2:attack=20:release=300')
        if self.compressor:filters.append(f'acompressor=threshold={10**(self.threshold_db/20)}:ratio={self.ratio}:attack=20:release=250:makeup=1')
        if self.normalize:filters.append(f'loudnorm=I={self.target_lufs}:TP=-2:LRA=11')
        return ','.join(filters)


def prepare_audio(media,index,path,treatment=None,cancel=None,progress=lambda *a:None):
    """Explicit full-track copy; never replaces media or raw FilmCraft sidecars."""
    from .checkpoints import atomic_json
    treatment=treatment or AudioTreatment();filters=treatment.filters()
    verify_source(media)
    if index not in [a['index'] for a in media.audio]:raise ValueError('Faixa de áudio inexistente.')
    target=safe_destination(path,media.path)
    if target.suffix.lower()!='.wav':raise ValueError('Escolha WAV para a cópia de áudio tratada.')
    metadata=safe_destination(target.with_suffix('.treatment.json'),media.path)
    # All work is staged; failure never removes an earlier user output.
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='audio-treatment-',dir=target.parent) as tmp:
        tmp=Path(tmp);processed=tmp/'processed.wav'
        command=[executable('ffmpeg'),'-v','error','-nostdin','-n','-copyts','-i',media.path,'-map',f'0:{index}',
                 '-af',f'asetpts=PTS-({media.origin})/TB,aresample=48000:async=1:first_pts=0,apad,{filters}',
                 '-t',media.duration,'-ar','48000','-ac','2','-c:a','pcm_s16le','-rf64','auto',processed]
        run(command,cancel,progress=lambda s:progress(100*s/media.duration,f'Áudio tratado: {s:.1f}/{media.duration:.1f} s'),duration=media.duration)
        check_cancel(cancel);verify_source(media)
        report={'source':media.path,'source_id':media.source_id,'track':index,'origin':media.origin,'duration':media.duration,
                'treatment':asdict(treatment),'filters':filters,'output':str(target),
                'note':'Cópia opcional estéreo PCM48; importar manualmente no editor, evitando tocar junto com a mesma faixa original. Compare ouvindo antes/depois.'}
        atomic_json(tmp/'report.json',report)
        publish_file(processed,target,cancel)
        # If metadata publication fails, keep the finished audio rather than
        # delete a file another process may already be using.
        publish_file(tmp/'report.json',metadata,cancel)
    return target
