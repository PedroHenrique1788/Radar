import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from fractions import Fraction
from contextlib import contextmanager
from .model import Media
from .runtime import bundled_tool, start_process
from .control import Cancelled,current_control
from .checkpoints import source_identity,signature


def executable(name):
    result = os.environ.get(name.upper() + '_PATH') or bundled_tool(name) or shutil.which(name)
    if not result or not Path(result).is_file():
        raise RuntimeError(f'{name} não encontrado. Instale FFmpeg e adicione sua pasta bin ao PATH.')
    return result


def check_cancel(cancel):
    if cancel and cancel.is_set():
        raise Cancelled('Operação cancelada.')
    control=current_control(cancel)
    if control:control.checkpoint()


@contextmanager
def managed_process(args,cancel=None,**options):
    control=current_control(cancel)
    acquired=False;p=None
    try:
        check_cancel(cancel)
        if control:
            while not control.slots.acquire(timeout=.1):check_cancel(cancel)
            acquired=True
            args=control.command(args)
        p=start_process(args,**options)
        if control:control.register(p)
        yield p
    finally:
        if p is not None:
            if p.poll() is None:p.kill()
            p.wait()
            if control:control.unregister(p)
        if acquired:control.slots.release()


def run(args, cancel=None, timeout=None, env=None,progress=None,duration=None,cwd=None):
    """Spool stderr/stdout to disk; never block a worker on full pipes."""
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err, tempfile.TemporaryDirectory(prefix='radar-process-') as tmp:
        check_cancel(cancel)
        control=current_control(cancel)
        clock=(lambda:control.active_time) if control else time.monotonic
        started=clock()
        args=list(args)
        progress_path=Path(tmp)/'progress.txt'
        if progress:args=[args[0],'-progress',progress_path,'-nostats',*args[1:]]
        last_progress=0.
        with managed_process(args,cancel,stdout=out,stderr=err,**({'env':env} if env is not None else {}),**({'cwd':str(cwd)} if cwd is not None else {})) as p:
            while p.poll() is None:
                check_cancel(cancel)
                if timeout is not None and clock() - started > timeout:
                    raise RuntimeError(f'{Path(args[0]).name} não respondeu em {timeout:g} segundos.')
                if progress and progress_path.exists():
                    with progress_path.open('rb') as status:
                        status.seek(max(0,progress_path.stat().st_size-4096))
                        rows=status.read().decode(errors='replace').splitlines()
                    values=[line.partition('=')[2] for line in rows if line.startswith('out_time_us=')]
                    if values:
                        try:seconds=max(0,float(values[-1])/1_000_000)
                        except ValueError:seconds=last_progress
                        seconds=min(duration,seconds) if duration is not None else seconds
                        if seconds>last_progress:last_progress=seconds;progress(seconds)
                if cancel:
                    cancel.wait(.1)
                else:
                    threading.Event().wait(.1)
            if p.returncode:
                err.seek(0, 2)
                err.seek(max(0, err.tell() - 6000))
                detail = err.read().decode('utf-8', errors='replace').strip()
                if not detail:
                    out.seek(0, 2)
                    out.seek(max(0, out.tell() - 6000))
                    detail = out.read().decode('utf-8', errors='replace').strip()
                code = f'0x{p.returncode & 0xFFFFFFFF:08X}'
                raise RuntimeError(f'{Path(args[0]).name} terminou com código {code}.\n{detail or "O programa não enviou detalhes. Verifique a instalação e suas dependências."}')
            out.seek(0)
            if progress and duration is not None:progress(duration)
            return out.read().decode('utf-8', errors='replace')


def probe(path,cancel=None):
    path = Path(path).resolve(strict=True)
    data = json.loads(run([executable('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path],cancel,timeout=60))
    videos = [s for s in data['streams'] if s['codec_type'] == 'video' and not s.get('disposition', {}).get('attached_pic')]
    if not videos:
        raise ValueError('O arquivo não contém vídeo.')
    v = videos[0]
    def rate(text):
        try:
            return float(Fraction(text))
        except (ValueError, ZeroDivisionError):
            return 0
    fps = rate(v.get('avg_frame_rate', '0/1')) or rate(v.get('r_frame_rate', '0/1')) or 30
    origin = float(v.get('start_time', data['format'].get('start_time', 0)))
    if v.get('duration'):
        duration = float(v['duration'])
    elif v.get('tags', {}).get('DURATION'):
        # Matroska DURATION is an absolute end timestamp, including initial PTS offset.
        from .model import parse_time
        duration = parse_time(v['tags']['DURATION']) - origin
    elif 'matroska' in data['format'].get('format_name', ''):
        duration = float(data['format']['duration']) - origin
    else:
        duration = float(data['format']['duration']) + float(data['format'].get('start_time', 0)) - origin
    if duration <= 0:
        raise ValueError('Duração do vídeo indisponível.')
    audios = [{'index': s['index'], 'codec': s.get('codec_name'), 'channels': s.get('channels'),
               'sample_format':s.get('sample_fmt',''),'bits':int(s.get('bits_per_raw_sample') or s.get('bits_per_sample') or 0),
               'language': s.get('tags', {}).get('language', ''), 'title': s.get('tags', {}).get('title', ''),
               'start_time': float(s.get('start_time', origin))} for s in data['streams'] if s['codec_type'] == 'audio']
    return Media(str(path), duration, v['width'], v['height'], fps, v.get('codec_name', '?'), origin,
                 audios, v['index'], abs(fps - rate(v.get('r_frame_rate', '0/1'))) > .01,signature(source_identity(path)))


def audio_filter(media, track='mix',start=0,duration=None):
    streams = media.audio if track == 'mix' else [a for a in media.audio if a['index'] == int(track)]
    if not streams:
        raise ValueError('Faixa de áudio inexistente.')
    filters, labels = [], []
    duration=media.duration-start if duration is None else duration
    absolute=media.origin+start
    for i, a in enumerate(streams):
        label = f'a{i}'
        filters.append(f"[0:{a['index']}]atrim=start={absolute}:end={absolute+duration},asetpts=PTS-({absolute})/TB,aresample=16000:async=1:first_pts=0,apad=whole_dur={duration},atrim=duration={duration},aformat=channel_layouts=mono[{label}]")
        labels.append(f'[{label}]')
    filters.append(''.join(labels) + (f'amix=inputs={len(labels)}:duration=longest:normalize=1' if len(labels) > 1 else 'anull') + '[out]')
    return ';'.join(filters)


def extract_audio(media, target, track='mix', cancel=None,start=0,duration=None,progress=None):
    duration=media.duration-start if duration is None else duration
    if not 0<=start<media.duration or not 0<duration<=media.duration-start+1e-6:raise ValueError('Lote de áudio fora do vídeo original.')
    args=[executable('ffmpeg'),'-v','error','-nostdin','-y','-copyts']
    if abs(media.origin)<1e-6 and start>2:args+=['-seek_timestamp','1','-ss',start-2]
    args+=['-i',media.path,'-filter_complex',audio_filter(media,track,start,duration),'-map','[out]','-t',duration,
           '-ar','16000','-ac','1','-c:a','pcm_s16le',str(target)]
    run(args,cancel,progress=progress,duration=duration)


def align_bounds(media, start, end, cancel=None):
    """Read actual presentation times near each boundary, including VFR."""
    result = []
    for t in (start, end):
        if t >= media.duration:
            result.append(media.duration)
            continue
        absolute = t + media.origin
        data = json.loads(run([executable('ffprobe'), '-v', 'error', '-select_streams', str(media.video_index),
                              '-read_intervals', f'{max(0, absolute - 2)}%{absolute + 2}', '-show_frames',
                              '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', media.path], cancel))
        times = [float(f['best_effort_timestamp_time']) - media.origin for f in data.get('frames', []) if 'best_effort_timestamp_time' in f]
        times = [v for v in times if 0 <= v <= media.duration]
        if not times:
            raise RuntimeError('Não foi possível localizar quadros no limite do corte.')
        result.append(min(times, key=lambda v: abs(v - t)))
    if result[1] <= result[0]:
        raise ValueError('Intervalo menor que um quadro.')
    return result
