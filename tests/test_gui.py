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
            if not button.winfo_viewable():continue
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
        app.load_preview_frame();finish()
        assert app._preview_image.width()>0
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


def test_wizard_navigation_and_gemini_opt_in(tmp_path,monkeypatch):
    import time
    from radar.gui import App
    from radar.model import Media,Cut
    from radar import gui
    from radar.gemini import cut_record,record_signature
    monkeypatch.chdir(tmp_path)
    app=App();errors=[];calls=[]
    monkeypatch.setattr(app,'error',lambda e:errors.append(str(e)))
    key='fake-session-key-for-ui-test'
    class Client:
        def __init__(self,k):assert k==key
        def list_models(self,cancel=None):return ['gemini-test-flash']
        def review(self,media,cuts,speech,model,search,cancel):
            calls.append((cuts,model,search))
            records=[cut_record(c,speech) for c in cuts]
            return {'model':model,'created_at':'test','reviews':[{'id':1,'nota_editorial':77,'titulo':'Sugestão IA',
                'justificativa':'Fala com contexto','sugestao_edicao':'Corte no desfecho','limitacoes':'Não vi o vídeo'}],
                'input_signatures':{str(r['id']):record_signature(r) for r in records},
                'sources':[],'search_requested':search,'search_confirmed':False}
    monkeypatch.setattr(gui,'GeminiClient',Client)
    def finish():
        deadline=time.monotonic()+5
        while app.busy and time.monotonic()<deadline:
            app.update();time.sleep(.02)
        assert not app.busy
        app.update()
        assert not errors,errors
    try:
        assert app.current_page=='video'
        m=Media('/tmp/no-media.mp4',100,160,90,25,'h264',0,[],0)
        app.loaded(m);app.update()
        assert app.current_page=='analysis'
        c=Cut(1,10,30,45,'Título local','Motivo local')
        speech=[{'start':12,'end':15,'text':'Fala para revisão','words':[]}]
        app.results((m,[c],speech,[]));app.update()
        assert app.current_page=='review' and app.table.selection()==('1',)
        assert not app.pages['settings'].winfo_viewable()
        app.show_page('settings');app.update()
        app.gemini_key_input.set(key)
        app.connect_gemini();finish()
        assert app.gemini_model.get()=='gemini-test-flash'
        app.save_gemini_preferences()
        assert key not in (tmp_path/'temporarios/settings.json').read_text(encoding='utf-8')
        app.show_page('review')
        monkeypatch.setattr(gui.messagebox,'askyesno',lambda *a:False)
        app.review_gemini()
        assert not calls and not app.busy
        monkeypatch.setattr(gui.messagebox,'askyesno',lambda *a:True)
        app.review_gemini();finish()
        assert len(calls)==1 and app._valid_ai(c)['nota_editorial']==77
        assert (c.start,c.end,c.score,c.title)==(10,30,45,'Título local')
        assert '77' in app.ai_view.get('1.0','end')
        c.start=11
        assert app._valid_ai(c) is None
        app.forget_gemini_key()
        assert not app._session_key and not app.gemini_key_input.get()
    finally:app.close()
