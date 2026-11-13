# Build from repository root: python -m PyInstaller packaging/RadarCortes.spec
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
binaries, datas, hiddenimports = [], [], ['packaging_smoke']
# Some standalone Linux Python distributions keep Tcl/Tk outside ldconfig's
# paths. Include them explicitly for local frozen validation; Windows keeps
# using PyInstaller's standard Tcl/Tk hooks and the existing redistributables.
if sys.platform.startswith('linux'):
    for name in ('libtcl9.0.so','libtcl9tk9.0.so','libtcl8.6.so','libtk8.6.so'):
        library=Path(sys.base_prefix)/'lib'/name
        if library.is_file():binaries.append((str(library),'.'))
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
