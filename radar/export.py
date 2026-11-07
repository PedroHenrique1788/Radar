import csv
import json
import os
from pathlib import Path
import tempfile
from .media import executable, run
from .model import timestamp


def safe_destination(path, source=None):
    path = Path(path).resolve()
    if source and path == Path(source).resolve():
        raise ValueError('Não é permitido sobrescrever o vídeo original.')
    if path.exists():
        raise FileExistsError('O destino já existe. Escolha outro nome para preservar o arquivo.')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def export_clip(media, cut, path, cancel=None):
    cut.validate(media.duration)
    path = safe_destination(path, media.path)
    filters = [f'[0:{media.video_index}]setpts=PTS-({media.origin})/TB,trim=start={cut.start}:end={cut.end},setpts=PTS-STARTPTS[v]']
    args = [executable('ffmpeg'), '-v', 'error', '-nostdin', '-n', '-copyts', '-i', media.path]
    for i, a in enumerate(media.audio):
        filters.append(f"[0:{a['index']}]asetpts=PTS-({media.origin})/TB,aresample=async=1:first_pts=0,atrim=start={cut.start}:end={cut.end},asetpts=PTS-STARTPTS[a{i}]")
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
        # Hard link is atomic and refuses an existing destination, including races.
        os.link(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return path


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
