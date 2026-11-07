"""PyInstaller entry point, also offering a real installed-package smoke test."""
import json
import logging
from pathlib import Path
import sys
import traceback

from radar.runtime import prepare_desktop


def main():
    folder = prepare_desktop()
    try:
        if '--self-test' in sys.argv:
            output = Path(sys.argv[sys.argv.index('--self-test') + 1]).resolve()
            try:
                from packaging_smoke import smoke
                report = smoke()
                output.write_text(json.dumps({'ok': True, **report}, indent=2), encoding='utf-8')
            except Exception:
                output.write_text(json.dumps({'ok': False, 'error': traceback.format_exc()}), encoding='utf-8')
                raise
        else:
            from radar.__main__ import main as radar_main
            radar_main()
    except Exception:
        logging.basicConfig(filename=folder / 'temporarios' / 'startup.log', level=logging.ERROR)
        logging.exception('Falha ao iniciar o Radar')
        if '--self-test' not in sys.argv:
            import tkinter.messagebox
            tkinter.messagebox.showerror('Radar de Cortes',
                f'Não foi possível iniciar. Consulte o arquivo:\n{folder / "temporarios" / "startup.log"}')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
