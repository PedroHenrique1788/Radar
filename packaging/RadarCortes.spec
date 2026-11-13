# Build from repository root: python -m PyInstaller packaging/RadarCortes.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
binaries, datas, hiddenimports = [], [], ['packaging_smoke']
for package in ('numpy', 'faster_whisper', 'ctranslate2', 'av', 'tokenizers',
                'onnxruntime', 'huggingface_hub', 'opentimelineio','psutil'):
    data, binary, hidden = collect_all(package)
    datas += data
    binaries += binary
    hiddenimports += hidden
for folder in ('ffmpeg', 'models', 'licenses', 'validation'):
    datas.append((str(root/'bundle'/folder), folder))
for dll in (root/'bundle'/'vc-runtime').glob('*.dll'):
    binaries.append((str(dll), '.'))
datas.append((str(root/'README.md'), '.'))
a = Analysis([str(root/'packaging'/'desktop_entry.py')],
    pathex=[str(root), str(root/'packaging')], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, excludes=['pytest', 'IPython', 'matplotlib'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='RadarCortes',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='RadarCortes')
