"""Locations shared by source installs and the standalone Windows application."""
import os
from pathlib import Path
import sys


def bundled_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def bundled_tool(name):
    suffix = '.exe' if os.name == 'nt' else ''
    candidate = bundled_root() / 'ffmpeg' / (name + suffix)
    return str(candidate) if candidate.is_file() else None


def resolve_model(name):
    if name == 'tiny':
        local = bundled_root() / 'models' / 'tiny'
        if (local / 'model.bin').is_file():
            return str(local)
    return name


def prepare_desktop():
    """Never write caches/logs next to the installed executable."""
    if not getattr(sys, 'frozen', False):
        return Path.cwd()
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'RadarCortes'
    for folder in ('temporarios', 'resultados'):
        (base / folder).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('HF_HOME', str(base / 'modelos'))
    os.chdir(base)
    return base
