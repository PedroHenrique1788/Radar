import csv
import json
import os
from pathlib import Path
import tempfile
from .media import executable, run, check_cancel, probe
from .model import timestamp


def safe_destination(path, source=None, overwrite=False):
    path = Path(path).resolve()
    if source and path == Path(source).resolve():
        raise ValueError('Não é permitido sobrescrever o vídeo original.')
    if path.exists() and (not overwrite or not path.is_file()):
        raise FileExistsError('O destino já existe. Escolha outro nome para preservar o arquivo.')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def export_clip(media, cut, path, cancel=None, overwrite=False):
    cut.validate(media.duration)
    path = safe_destination(path, media.path, overwrite)
    absolute_start, absolute_end = media.origin + cut.start, media.origin + cut.end
    filters = [f'[0:{media.video_index}]trim=start={absolute_start}:end={absolute_end},setpts=PTS-({absolute_start})/TB,pad=ceil(iw/2)*2:ceil(ih/2)*2[v]']
    args = [executable('ffmpeg'), '-v', 'error', '-nostdin', '-n', '-copyts']
    # Seek near the cut, retaining original PTS; do not decode hours of footage
    # just to export a late Short. Absolute seeking also handles nonzero origins.
    normal_origin = abs(media.origin) < 1e-6 and all(a['start_time'] >= 0 for a in media.audio)
    seek = max(0, cut.start - 2) if normal_origin else 0
    if seek > 0:
        args += ['-seek_timestamp', '1', '-ss', seek]
    args += ['-i', media.path]
    for i, a in enumerate(media.audio):
        filters.append(f"[0:{a['index']}]atrim=start={absolute_start}:end={absolute_end},asetpts=PTS-({absolute_start})/TB,aresample=async=1:first_pts=0,apad,atrim=duration={cut.duration}[a{i}]")
    args += ['-filter_complex', ';'.join(filters), '-map', '[v]']
    for i in range(len(media.audio)):
        args += ['-map', f'[a{i}]']
    # Re-encode: trim on presentation timestamps, never keyframe-only stream copy.
    args += ['-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p', '-fps_mode', 'vfr',
             '-c:a', 'aac', '-movflags', '+faststart', '-t', cut.duration]
    fd, tmp = tempfile.mkstemp(suffix='.mp4', dir=path.parent)
    os.close(fd)
    Path(tmp).unlink()
    try:
        run(args + [tmp], cancel)
        try:
            probe(tmp)
        except (ValueError, RuntimeError) as exc:
            raise RuntimeError('FFmpeg não gerou vídeo no intervalo escolhido. Revise os limites do corte.') from exc
        publish_file(Path(tmp), path, cancel, overwrite)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return path



def publish_file(temporary, destination, cancel=None, overwrite=False):
    """Preserve no-clobber semantics on exFAT/FAT32/network shares too."""
    check_cancel(cancel)
    if overwrite:
        os.replace(temporary, destination)
        return
    try:
        os.link(temporary, destination)
        return
    except FileExistsError:
        raise
    except OSError:
        pass  # The filesystem may not implement hard links.
    created = False
    try:
        with Path(destination).open('xb') as out, Path(temporary).open('rb') as source:
            created = True
            while True:
                check_cancel(cancel)
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    except BaseException:
        if created:
            Path(destination).unlink(missing_ok=True)
        raise

def export_report(media, cuts, path):
    path = safe_destination(path, media.path)
    records = [c.record(media) for c in cuts]
    with path.open('x', encoding='utf-8-sig' if path.suffix.lower() == '.csv' else 'utf-8', newline='') as f:
        if path.suffix.lower() == '.csv':
            fields = ['id', 'title', 'start_time', 'end_time', 'duration', 'score', 'category', 'reason', 'transcript', 'editing']
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            # Prevent spreadsheet formulas when transcript/title start with = + - @.
            for record in records:
                writer.writerow({k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v) for k, v in record.items()})
        else:
            json.dump({'source': media.path, 'time_reference': 'seconds from first original video frame',
                       'notice': 'Pontuação heurística; não é probabilidade de viralização.', 'cuts': records}, f, ensure_ascii=False, indent=2)
    return path


def export_srt(cut, speech, path):
    path = safe_destination(path)
    lines = []
    for seg in speech:
        if seg['end'] <= cut.start or seg['start'] >= cut.end:
            continue
        words = [w for w in seg.get('words', []) if w['end'] > cut.start and w['start'] < cut.end]
        text = ''.join(w['word'] for w in words).strip() if seg.get('words') else seg['text']
        if not text:
            continue
        start, end = max(0, seg['start'] - cut.start), min(cut.duration, seg['end'] - cut.start)
        lines.append(f'{len(lines)+1}\n{timestamp(start).replace(".", ",")} --> {timestamp(end).replace(".", ",")}\n{text}\n')
    if not lines:
        raise ValueError('Não há fala transcrita neste intervalo.')
    path.write_text('\n'.join(lines), encoding='utf-8')
    return path
