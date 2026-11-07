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


# PyInstaller adjusts DLL lookup for its own Python extensions. System tools must
# inherit their normal search path instead (especially the external FilmCraft).
import subprocess
import threading

_spawn_lock = threading.RLock()


def start_process(args, **options):
    with _spawn_lock:
        env = dict(options.pop('env', os.environ))
        frozen = bool(getattr(sys, 'frozen', False))
        if frozen:
            if 'LD_LIBRARY_PATH_ORIG' in env:
                env['LD_LIBRARY_PATH'] = env['LD_LIBRARY_PATH_ORIG']
            else:
                env.pop('LD_LIBRARY_PATH', None)
            root = bundled_root().resolve()
            entries = []
            for entry in env.get('PATH', '').split(os.pathsep):
                try:
                    if Path(entry).resolve().is_relative_to(root):
                        continue
                except (OSError, ValueError):
                    pass
                entries.append(entry)
            env['PATH'] = os.pathsep.join(entries)
        options.setdefault('env', env)
        options.setdefault('creationflags', getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if frozen and os.name == 'nt':
            import ctypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.GetDllDirectoryW.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
            kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
            size = kernel.GetDllDirectoryW(0, None)
            original = ctypes.create_unicode_buffer(size + 1)
            kernel.GetDllDirectoryW(len(original), original)
            if not kernel.SetDllDirectoryW(None):
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                return subprocess.Popen([str(a) for a in args], **options)
            finally:
                kernel.SetDllDirectoryW(original.value or None)
        return subprocess.Popen([str(a) for a in args], **options)
