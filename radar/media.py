import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from fractions import Fraction
from .model import Media
from .runtime import bundled_tool, start_process


class Cancelled(Exception):
    pass


def executable(name):
    result = os.environ.get(name.upper() + '_PATH') or bundled_tool(name) or shutil.which(name)
    if not result or not Path(result).is_file():
        raise RuntimeError(f'{name} não encontrado. Instale FFmpeg e adicione sua pasta bin ao PATH.')
    return result


def check_cancel(cancel):
    if cancel and cancel.is_set():
        raise Cancelled('Operação cancelada.')


def run(args, cancel=None, timeout=None, env=None):
    """Spool stderr/stdout to disk; never block a worker on full pipes."""
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        check_cancel(cancel)
        started = time.monotonic()
        p = start_process(args, stdout=out, stderr=err, **({'env': env} if env is not None else {}))
        try:
            while p.poll() is None:
                check_cancel(cancel)
                if timeout is not None and time.monotonic() - started > timeout:
                    raise RuntimeError(f'{Path(args[0]).name} não respondeu em {timeout:g} segundos.')
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
            return out.read().decode('utf-8', errors='replace')
        finally:
            if p.poll() is None:
                p.kill()
            p.wait()


def probe(path):
    path = Path(path).resolve(strict=True)
    data = json.loads(run([executable('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path]))
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
               'language': s.get('tags', {}).get('language', ''), 'title': s.get('tags', {}).get('title', ''),
               'start_time': float(s.get('start_time', origin))} for s in data['streams'] if s['codec_type'] == 'audio']
    return Media(str(path), duration, v['width'], v['height'], fps, v.get('codec_name', '?'), origin,
                 audios, v['index'], abs(fps - rate(v.get('r_frame_rate', '0/1'))) > .01)


def audio_filter(media, track='mix'):
    streams = media.audio if track == 'mix' else [a for a in media.audio if a['index'] == int(track)]
    if not streams:
        raise ValueError('Faixa de áudio inexistente.')
    filters, labels = [], []
    for i, a in enumerate(streams):
        label = f'a{i}'
        filters.append(f"[0:{a['index']}]asetpts=PTS-({media.origin})/TB,aresample=16000:async=1:first_pts=0, aformat=channel_layouts=mono[{label}]")
        labels.append(f'[{label}]')
    filters.append(''.join(labels) + (f'amix=inputs={len(labels)}:duration=longest:normalize=1' if len(labels) > 1 else 'anull') + '[out]')
    return ';'.join(filters)


def extract_audio(media, target, track='mix', cancel=None):
    run([executable('ffmpeg'), '-v', 'error', '-nostdin', '-y', '-copyts', '-i', media.path,
         '-filter_complex', audio_filter(media, track), '-map', '[out]', '-t', media.duration,
         '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', str(target)], cancel)


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
