"""Run under DISPLAY=:99 (Xvfb) or a normal Linux desktop."""
import os
import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt' and not os.environ.get('DISPLAY'), reason='Requer display X11')


def test_gui_flow(tmp_path, monkeypatch):
    from radar.gui import App
    from radar.model import Media, Cut
    from radar import gui
    app = App()
    try:
        media = Media('/tmp/source.mp4', 100, 160, 90, 25, 'h264', 0,
                      [{'index': 1, 'codec': 'aac', 'channels': 2, 'language': 'pt', 'title': 'Mic'}], 0)
        app.loaded(media)
        assert len(app.track['values']) == 2
        app.cuts = [Cut(1, 1.12, 20.28, 60, 'Teste', 'Variação sonora medida')]
        app.refresh()
        app.table.selection_set('1')
        app.show_detail()
        app.copy()
        assert '00:00:01.120' in app.clipboard_get()
        assert 'Teste' in app.detail.get('1.0', 'end')
        answers = iter(['00:00:02.000', '00:00:22.000'])
        monkeypatch.setattr(gui.simpledialog, 'askstring', lambda *a, **kw: next(answers))
        monkeypatch.setattr(gui, 'align_bounds', lambda *a: [2., 22.])
        app.adjust()
        import time
        deadline = time.monotonic() + 5
        while app.busy and time.monotonic() < deadline:
            app.update()
            time.sleep(.02)
        assert (app.cuts[0].start, app.cuts[0].end) == (2., 22.)
        app.sort('start')
        app.update()
    finally:
        app.close()
