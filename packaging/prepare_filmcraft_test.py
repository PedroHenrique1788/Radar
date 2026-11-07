"""Fetch the official Windows editor for CI only; not redistributed with Radar."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import shutil
import sys
import urllib.request
import zipfile

base='https://github.com/storytold/filmcraft/releases/download/v0.18.0/'
name='filmcraft-0.18.0-windows-x64-portable.zip'
root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
checksums=urllib.request.urlopen(base+'SHA256SUMS.txt').read().decode()
expected=next(line.split()[0] for line in checksums.splitlines() if line.split()[-1].lstrip('*')==name)
archive=root/name
with urllib.request.urlopen(base+name) as src,archive.open('wb') as out:
    shutil.copyfileobj(src,out)
with archive.open('rb') as f:
    assert hashlib.file_digest(f,'sha256').hexdigest()==expected,'FilmCraft checksum mismatch'
with zipfile.ZipFile(archive) as z:
    for item in z.namelist():
        p=PurePosixPath(item.replace('\\','/'))
        if p.is_absolute() or '..' in p.parts or ':' in item:
            raise RuntimeError('Unsafe archive member')
    z.extractall(root)
cli=next(root.rglob('filmcraft-cli.exe')).resolve()
print(cli)
if len(sys.argv)>2:
    with Path(sys.argv[2]).open('a',encoding='utf-8') as f:
        f.write(f'FILMCRAFT_CLI={cli}\nFILMCRAFT_TEST_DESKTOP=1\n')
