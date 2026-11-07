"""Run under DISPLAY=:99 (Xvfb) or a normal Linux desktop."""
import os
import pytest

@pytest.fixture(autouse=True)
def collect_tk_on_main_thread(monkeypatch):
    yield
    # Tcl/Tk objects from a destroyed test window must not be finalized by
    # the next test's worker thread when it imports a large native module.
    monkeypatch.undo()
    import gc
    gc.collect()


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


def test_export_and_filmcraft_buttons(tmp_path,monkeypatch):
    import time
    from pathlib import Path
    from radar.gui import App
    from radar.model import Cut
    from radar.media import run,executable,probe
    from radar import gui
    cli=os.environ.get('FILMCRAFT_CLI')
    if not cli:pytest.skip('Requer FilmCraft real para testar os botões')
    monkeypatch.chdir(tmp_path)
    movie=tmp_path/'source.mp4'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=25:d=8',
         '-f','lavfi','-i','sine=frequency=440:duration=8','-c:v','libx264','-c:a','aac',movie])
    app=App()
    errors=[]
    notices=[]
    monkeypatch.setattr(app,'error',lambda e:errors.append(str(e)))
    monkeypatch.setattr(gui.messagebox,'showinfo',lambda *a:notices.append(a))
    monkeypatch.setattr(gui.messagebox,'showwarning',lambda *a:notices.append(a))
    def finish():
        deadline=time.monotonic()+60
        while app.busy and time.monotonic()<deadline:
            app.update()
            time.sleep(.02)
        app.update()
        assert not app.busy
        assert not errors,errors
    try:
        media=probe(movie)
        cuts=[Cut(i+1,a,b,50,f'Short {i+1}','Teste') for i,(a,b) in enumerate([(0,2),(2.4,4.4),(5.2,7.2)])]
        app.results((media,cuts,[],[]))
        assert app.table.selection()==('1',)
        app.geometry('1000x620')
        app.update()
        def buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child,gui.ttk.Button):yield child
                yield from buttons(child)
        for button in buttons(app):
            assert button.winfo_rooty()+button.winfo_height() <= app.winfo_rooty()+app.winfo_height()
            assert button.winfo_rootx()+button.winfo_width() <= app.winfo_rootx()+app.winfo_width()
        out=tmp_path/'from-button.mp4'
        text_output=tmp_path/'transcricao.txt'
        monkeypatch.setattr(gui.filedialog,'asksaveasfilename',lambda **kw:str(text_output if kw.get('defaultextension')=='.txt' else out))
        app.copy_for_chatgpt()
        assert '00:00:00.000' in app.clipboard_get()
        app.speech=[{'start':.1,'end':1.8,'text':'fala do corte','words':[{'start':.1,'end':.5,'word':'fala'}, {'start':.6,'end':.8,'word':'do'}, {'start':1.,'end':1.8,'word':'corte'}]}]
        app.transcript()
        assert 'fala do corte' in text_output.read_text(encoding='utf-8')
        app.export_video();finish()
        assert probe(out).duration==pytest.approx(2,abs=.05)
        desktop=Path(cli).with_name('filmcraft.exe' if os.name=='nt' else 'filmcraft')
        monkeypatch.setattr(gui.filedialog,'askopenfilename',lambda **kw:str(desktop))
        app.connect(True);finish()
        assert app.cli==str(Path(cli).resolve())
        target=tmp_path/'projects';target.mkdir()
        monkeypatch.setattr(gui.filedialog,'askdirectory',lambda **kw:str(target))
        app.film(False,False);finish()
        grouped=list(target.rglob('*.fcproj'))
        assert len(grouped)==1
        app.film(True,False);finish()
        assert len(list(target.rglob('*.fcproj')))==4
        opened=[]
        monkeypatch.setattr(gui.filedialog,'askopenfilename',lambda **kw:str(grouped[0]))
        import radar.filmcraft as fc
        monkeypatch.setattr(fc,'start_process',lambda args,**kw:opened.append(args))
        app.open_film()
        assert opened and str(grouped[0]) in opened[0]
    finally:
        app.close()
