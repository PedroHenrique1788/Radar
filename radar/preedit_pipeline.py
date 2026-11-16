"""Per-track pre-edit analysis sharing the existing bounded/checksummed cache."""
from dataclasses import asdict
import math
import os
from pathlib import Path
import shutil

from .audio_prepare import measurements
from .checkpoints import CheckpointStore,signature
from .control import ExecutionControl
from .media import probe,extract_audio,check_cancel,Cancelled
from .pipeline import _valid_audio
from .preedit import detect,track_layout,PreEditOptions
from .profiles import AnalysisOptions
from .signals import sound_features,visual_features
from .transcription_cache import audio_key,tool_stamp


def analyze_preedit(media,*,options=None,analysis=None,tracks=None,speech=None,markers=None,
                    cache_dir='temporarios',cancel=None,progress=lambda *a:None):
    opts=AnalysisOptions.from_record(analysis);settings=PreEditOptions.from_record(options)
    control=cancel if isinstance(cancel,ExecutionControl) else ExecutionControl(opts,cancel)
    store=CheckpointStore(media.path,cache_dir);store.acquire()
    try:
        with control.bind():
            check_cancel(control)
            actual=probe(media.path,control)
            if media.source_id and actual.source_id!=media.source_id:raise ValueError('O original mudou. Importe o vídeo novamente.')
            media=actual
            tracks=track_layout(media) if tracks is None else tracks
            if sorted(r['index'] for r in tracks)!=sorted(a['index'] for a in media.audio):raise ValueError('Faixas não correspondem ao original.')
            # Validate user roles before expensive decoding.
            from .preedit import PreEdit
            PreEdit(media.source_id,media.duration,tracks,settings.record()).validate()
            batches=[(i,float(a),min(opts.batch_seconds,media.duration-a)) for i,a in enumerate(range(0,math.ceil(media.duration),opts.batch_seconds))]
            total=media.duration*(len(tracks)+int(opts.visual));done=0.;sounds={};visual=[]
            stamp=tool_stamp('ffmpeg')
            def report(value,text):
                control.report('Pré-edição audiovisual',value,total,'s-faixa')
                progress(100*value/total if total else 100,text)
            for track in tracks:
                key=audio_key(store.source_id,media,str(track['index']),opts,stamp)
                sound_key=signature(['sound-envelope-v3',key]);points=[]
                for i,a,d in batches:
                    check_cancel(control)
                    data=store.load('audio',sound_key,i)
                    if data is None:
                        target=store.folder/'extract'/key/f'{i:06}.wav';target.parent.mkdir(parents=True,exist_ok=True)
                        if not _valid_audio(target,store.load('extract',key,i)):
                            if shutil.disk_usage(target.parent).free<int(d*32000)+50*1024**2:raise RuntimeError('Espaço insuficiente para o próximo lote de áudio.')
                            part=target.with_suffix('.part.wav')
                            try:
                                extract_audio(media,part,str(track['index']),control,start=a,duration=d,
                                              progress=lambda seconds:report(done+seconds,f"Faixa {track['index']}: {a+seconds:.1f}/{media.duration:.1f} s"))
                                check_cancel(control);os.replace(part,target)
                                stat=target.stat();store.save('extract',key,{'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'start':a,'duration':d},i)
                            finally:part.unlink(missing_ok=True)
                        data=sound_features(target,control,start=a)
                        store.save('audio',sound_key,data,i)
                    points.extend(data);done+=d
                    report(done,f"Faixa {track['index']}: {a+d:.1f}/{media.duration:.1f} s (lote confirmado)")
                sounds[track['index']]=points
            if opts.visual:
                key=signature(['visual-v3',store.source_id,opts.sample_fps,opts.visual_width,opts.batch_seconds,stamp,media.origin,media.duration])
                previous=None
                for i,a,d in batches:
                    check_cancel(control);data=store.load('visual',key,i)
                    if data is None:
                        data=visual_features(media,control,lambda p,text:report(done+d*p/100,text),start=a,duration=d,
                                             sample_fps=opts.sample_fps,width=opts.visual_width,previous=previous,with_state=True)
                        store.save('visual',key,data,i)
                    previous=data['last_frame'];visual.extend(data['values']);done+=d;report(done,f'Imagem: {a+d:.1f}/{media.duration:.1f} s')
            result=detect(media,tracks,sounds,visual,speech or [],settings,control,markers)
            result.audio_analysis={str(k):measurements(points) for k,points in sounds.items()}
            store.validate_source();check_cancel(control)
            # Separate from the ordinary analysis request: its resume contract is untouched.
            store.save('preedit',signature(['preedit-v1',settings.record(),tracks,speech or [],markers or [],opts.record()]),result.record())
            report(total,'Pré-edição pronta para revisar; nenhuma remoção foi aplicada.')
            return result
    except (Cancelled,KeyboardInterrupt):raise
    finally:store.release()
