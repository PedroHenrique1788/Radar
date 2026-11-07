"""Fetch redistributable runtime inputs; preserve TLS and checksum verification."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODEL_REVISION = 'd90ca5fe260221311c53c58e660288d3deb8d356'
FFMPEG_BASE = 'https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/latest/'


def download(url, target):
    with urllib.request.urlopen(url, timeout=120) as source, target.open('wb') as output:
        shutil.copyfileobj(source, output)


def main():
    from huggingface_hub import snapshot_download
    bundle = ROOT / 'bundle'
    bundle.mkdir(exist_ok=True)
    shutil.copytree(ROOT/'packaging'/'validation', bundle/'validation', dirs_exist_ok=True)
    ffmpeg = bundle / 'ffmpeg'
    licenses = bundle / 'licenses'
    ffmpeg.mkdir(exist_ok=True)
    licenses.mkdir(exist_ok=True)
    archive = bundle / 'ffmpeg.zip'
    sums = bundle / 'ffmpeg-checksums.sha256'
    name = 'ffmpeg-master-latest-win64-gpl.zip'
    download(FFMPEG_BASE + name, archive)
    download(FFMPEG_BASE + 'checksums.sha256', sums)
    expected = next(line.split()[0] for line in sums.read_text().splitlines() if line.split()[-1].lstrip('*') == name)
    digest = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
    if digest != expected:
        raise RuntimeError('FFmpeg checksum mismatch; do not build with this archive.')
    with zipfile.ZipFile(archive) as z:
        # Extract only binaries and license/docs; avoid untrusted archive path traversal.
        for tool in ('ffmpeg.exe','ffprobe.exe','ffplay.exe'):
            item = next(n for n in z.namelist() if n.endswith('/bin/' + tool))
            (ffmpeg / tool).write_bytes(z.read(item))
        for item in z.namelist():
            if not item.endswith('/') and any(word in item.lower() for word in ('license', 'copying')):
                (licenses / ('ffmpeg-' + Path(item).name)).write_bytes(z.read(item))
    archive.unlink()
    snapshot_download('Systran/faster-whisper-tiny', revision=MODEL_REVISION,
                      local_dir=str(bundle/'models'/'tiny'),
                      allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.*','README.md'])
    cache = bundle/'models'/'tiny'/'.cache'
    if cache.exists():
        shutil.rmtree(cache)
    for source in (Path(sys.base_prefix)/'LICENSE.txt', Path(sys.base_prefix)/'tcl'/'tcl8.6'/'license.terms',
                   Path(sys.base_prefix)/'tcl'/'tk8.6'/'license.terms'):
        if source.exists():
            shutil.copy2(source, licenses/(source.parent.name+'-'+source.name))
    # Record licenses from installed distributions alongside all FFmpeg license files.
    import importlib.metadata
    for dist in importlib.metadata.distributions():
        for file in dist.files or []:
            if any(part.upper().startswith(('LICENSE','COPYING','NOTICE')) for part in file.parts):
                source = dist.locate_file(file)
                if source.is_file():
                    target = licenses / (dist.metadata['Name'] + '-' + source.name)
                    shutil.copy2(source, target)
    (licenses/'THIRD-PARTY.txt').write_text(
        'Includes Python, Tcl/Tk, NumPy, faster-whisper, CTranslate2, ONNX Runtime, PyAV, '
        'OpenTimelineIO and their dependencies. See accompanying license files.\n'
        'FFmpeg GPL build: https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/tag/latest\n'
        'Build recipes and source revisions: https://github.com/FFmpeg-Builds/FFmpeg-Builds\n'
        'FFmpeg source: https://git.ffmpeg.org/ffmpeg.git\n'
        'Whisper model weights (MIT): https://huggingface.co/Systran/faster-whisper-tiny/tree/' + MODEL_REVISION + '\n',
        encoding='utf-8')
    (bundle/'manifest.json').write_text(json.dumps({'model_revision':MODEL_REVISION,'ffmpeg_sha256':digest},indent=2))
    print('Verified bundle inputs prepared:', bundle)


if __name__ == '__main__':
    main()
