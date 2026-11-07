"""Streaming features: one compact record per second, never a whole movie in RAM."""
import subprocess
import tempfile
import wave
import numpy as np
from .media import executable, check_cancel


def sound_features(path, cancel=None):
    values = []
    with wave.open(str(path), 'rb') as w:
        while True:
            check_cancel(cancel)
            raw = w.readframes(w.getframerate())
            if not raw:
                break
            x = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768
            rms = float(np.sqrt(np.mean(x * x)))
            values.append({'t': len(values), 'rms': rms, 'db': float(20 * np.log10(max(rms, 1e-6)))})
    return values


def visual_features(media, cancel=None, progress=lambda *a: None):
    cmd = [executable('ffmpeg'), '-v', 'error', '-nostdin', '-i', media.path, '-map', f'0:{media.video_index}',
           '-vf', 'fps=1,scale=64:36', '-pix_fmt', 'gray', '-f', 'rawvideo', '-']
    values, previous = [], None
    with tempfile.TemporaryFile() as err:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            while True:
                check_cancel(cancel)
                raw = p.stdout.read(64 * 36)
                if not raw:
                    break
                if len(raw) != 64 * 36:
                    raise RuntimeError('Quadro visual incompleto.')
                frame = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
                change = 0 if previous is None else float(np.mean(np.abs(frame - previous)) / 255)
                values.append({'t': len(values), 'change': change})
                previous = frame
                if len(values) % 10 == 0:
                    progress(35 + 25 * min(1, len(values) / media.duration), 'Análise visual por amostragem…')
            if p.wait():
                err.seek(0)
                raise RuntimeError(err.read().decode(errors='replace'))
        finally:
            if p.poll() is None:
                p.kill()
            p.wait()
            p.stdout.close()
    return values
