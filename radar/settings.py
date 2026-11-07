"""Non-secret per-user preferences; relative to the app's writable working directory."""
import json
from pathlib import Path
import os
import tempfile


def read_settings():
    try:
        data = json.loads(Path('temporarios/settings.json').read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_filmcraft(cli):
    data = read_settings()
    data['filmcraft_cli'] = str(Path(cli).resolve())
    folder = Path('temporarios')
    folder.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='settings-', suffix='.json', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        os.replace(name, folder/'settings.json')
    finally:
        Path(name).unlink(missing_ok=True)
