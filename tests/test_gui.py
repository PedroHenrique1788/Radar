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
    monkeypatch.chdir(tmp_path)
    app = App()
    app.use_radar_only()
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
    app.use_radar_only()
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


@pytest.fixture
def hybrid(tmp_path,monkeypatch):
    import time
    from types import SimpleNamespace
    from radar.gui import App
    from radar.model import Media,Cut
    from radar import gui
    from radar.gemini import cut_record,record_signature
    monkeypatch.chdir(tmp_path)
    app=App();errors=[];calls=[];analyses=[];failures=[];model_failures=[]
    monkeypatch.setattr(app,'error',lambda e:errors.append(str(e)))
    key='fake-session-key-for-ui-test'
    class Client:
        def __init__(self,k):assert k==key
        def list_models(self,cancel=None):
            if model_failures:raise model_failures.pop(0)
            return ['gemini-test-flash']
        def review(self,media,cuts,speech,model,search,cancel):
            calls.append((list(cuts),model,search))
            if failures:raise failures.pop(0)
            records=[cut_record(c,speech) for c in cuts]
            return {'model':model,'created_at':'test','reviews':[{'id':c.id,'nota_editorial':20 if c.id==1 else 95,'titulo':f'Sugestão IA {c.id}',
                'justificativa':'Fala com contexto','sugestao_edicao':'Corte no desfecho','limitacoes':'Não vi o vídeo'} for c in cuts],
                'input_signatures':{str(r['id']):record_signature(r) for r in records},
                'sources':[],'search_requested':search,'search_confirmed':False}
    monkeypatch.setattr(gui,'GeminiClient',Client)
    monkeypatch.setattr(gui.messagebox,'showwarning',lambda *a:None)
    m=Media('/tmp/no-media.mp4',100,160,90,25,'h264',0,[],0)
    cuts=[Cut(1,10,30,90,'Título local 1','Motivo local'),Cut(2,40,60,45,'Título local 2','Motivo local')]
    speech=[{'start':12,'end':15,'text':'Fala para revisão','words':[]},
            {'start':42,'end':45,'text':'Outra fala com desfecho','words':[]}]
    def analyze(*args,**kwargs):
        analyses.append(args)
        return m,cuts[:args[2]],list(speech),[]
    monkeypatch.setattr(gui,'analyze',analyze)
    def finish():
        deadline=time.monotonic()+5
        while app.busy and time.monotonic()<deadline:
            app.update();time.sleep(.02)
        assert not app.busy
        app.update()
        assert not errors,errors
    def enable():
        app.gemini_key_input.set(key)
        app.connect_gemini();finish()
        monkeypatch.setattr(gui.messagebox,'askyesno',lambda *a:True)
        app.enable_gemini()
        assert app.workflow_mode=='gemini'
    yield SimpleNamespace(app=app,errors=errors,calls=calls,analyses=analyses,failures=failures,model_failures=model_failures,
                          media=m,cuts=cuts,speech=speech,key=key,finish=finish,enable=enable)
    app.close()


def test_local_startup_and_gemini_automatic_review_is_opt_in(hybrid,monkeypatch,tmp_path):
    from radar import gui
    app=hybrid.app
    assert app.current_page=='video' and app.model.get()=='off'
    app.show_page('video')
    assert app.current_page=='video' and not app._nav_buttons['video'].instate(['disabled'])
    app.loaded(hybrid.media);app.count.set('1');app.analyze();hybrid.finish()
    assert len(hybrid.analyses)==1 and not hybrid.calls and app.workflow_mode=='radar'
    app.gemini_key_input.set(hybrid.key)
    app.enable_gemini()
    assert hybrid.errors and app.workflow_mode=='radar'
    hybrid.errors.clear()
    app.connect_gemini();hybrid.finish()
    assert app.gemini_model.get()=='gemini-test-flash' and not hybrid.calls
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda *a:False)
    app.enable_gemini()
    assert app.workflow_mode=='radar' and not hybrid.calls
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda *a:True)
    app.enable_gemini()
    assert app.current_page=='analysis' and app.model.get()=='tiny' and not hybrid.calls
    assert hybrid.key not in (tmp_path/'temporarios/settings.json').read_text(encoding='utf-8')


def test_gemini_selects_from_extra_candidates_without_changing_original_times(hybrid):
    app=hybrid.app
    hybrid.enable()
    original=[(c.start,c.end,c.score,c.title) for c in hybrid.cuts]
    app.loaded(hybrid.media);app.count.set('1')
    app.analyze();hybrid.finish()
    assert hybrid.analyses[0][2]==2
    assert len(hybrid.calls)==1 and [c.id for c in hybrid.calls[0][0]]==[1,2]
    assert [c.id for c in app.cuts]==[2] and app.table.selection()==('2',)
    assert [(c.start,c.end,c.score,c.title) for c in hybrid.cuts]==original
    assert app._valid_ai(app.cuts[0])['nota_editorial']==95
    assert 'Sugestão IA 2' in app.table.item('2','values')
    assert app._pending_review is None and app.current_page=='review'
    assert '95' in app.ai_view.get('1.0','end')
    app.cuts[0].start=41
    assert app._valid_ai(app.cuts[0]) is None
    app.forget_gemini_key()
    assert not app._session_key and app.workflow_mode=='radar'


@pytest.mark.parametrize('status',[429,503])
def test_quota_and_service_errors_preserve_cuts_and_never_retry_automatically(hybrid,status):
    from radar.gemini import GeminiError
    import time
    app=hybrid.app
    hybrid.enable()
    hybrid.failures.append(GeminiError('Falha controlada',status=status,retry_after=120 if status==429 else 0))
    app.loaded(hybrid.media);app.count.set('1')
    app.analyze();hybrid.finish()
    assert len(hybrid.calls)==1 and app._pending_review and app.cuts[0].id==1
    assert app._failure_dialog.winfo_exists()
    if status==429:
        assert 'Limite de uso' in app.workflow_status.get()
        app.retry_gemini()
        assert len(hybrid.calls)==1 and app.resume_gemini_button.instate(['disabled'])
    app.wait_for_gemini();app.update()
    assert len(hybrid.calls)==1 and app._pending_review and not app.busy
    app._retry_at=time.monotonic()-1
    app.retry_gemini();hybrid.finish()
    assert len(hybrid.calls)==2 and len(hybrid.analyses)==1
    assert app.cuts[0].id==2 and app._pending_review is None
    assert hybrid.calls[0][1]==hybrid.calls[1][1]=='gemini-test-flash'


def test_continue_radar_keeps_best_local_cut_and_next_analysis_is_local(hybrid):
    from radar.gemini import GeminiError
    app=hybrid.app
    hybrid.enable()
    hybrid.failures.append(GeminiError('Cota',status=429,retry_after=60))
    app.loaded(hybrid.media);app.count.set('1')
    app.analyze();hybrid.finish()
    app.use_radar_only()
    assert app.workflow_mode=='radar' and [c.id for c in app.cuts]==[1]
    app.analyze();hybrid.finish()
    assert len(hybrid.calls)==1 and hybrid.analyses[-1][2]==1
    assert app._pending_review is None and app.cuts[0].score==90


def test_setup_failure_offers_explicit_local_mode(hybrid):
    from radar.gemini import GeminiError
    app=hybrid.app
    hybrid.model_failures.append(GeminiError('Chave recusada',status=403))
    app.gemini_key_input.set(hybrid.key)
    app.connect_gemini();hybrid.finish()
    assert app.workflow_mode=='radar' and app._failure_dialog.winfo_exists()
    app.use_radar_only()
    assert app.workflow_mode=='radar' and app.current_page=='video' and not hybrid.calls


def test_no_transcript_or_no_candidates_makes_no_gemini_request(hybrid):
    app=hybrid.app
    hybrid.enable()
    app.loaded(hybrid.media);hybrid.speech.clear()
    app.analyze();hybrid.finish()
    assert not hybrid.calls and app._pending_review
    assert 'Limite de uso' not in app._failure_dialog.title()
    app.use_radar_only();hybrid.cuts.clear()
    app.workflow_mode='gemini'
    app.analyze();hybrid.finish()
    assert not hybrid.calls and not app.cuts and app._pending_review is None


def test_cancelled_review_keeps_local_results(hybrid):
    from radar.media import Cancelled
    app=hybrid.app
    hybrid.enable()
    hybrid.failures.append(Cancelled())
    app.loaded(hybrid.media);app.analyze();hybrid.finish()
    assert len(hybrid.calls)==1 and app._pending_review
    app.use_radar_only()
    assert [c.id for c in app.cuts]==[1,2] and not app.busy


def test_closing_before_analysis_callback_prevents_automatic_api_call(hybrid):
    app=hybrid.app
    hybrid.enable();app.loaded(hybrid.media)
    app.busy=True
    app.events.put(('done',(app.results,(hybrid.media,hybrid.cuts,hybrid.speech,[]))))
    app._closing=True
    try:
        app.poll()
        assert not hybrid.calls and not app.busy and app._pending_review is None
    finally:app._closing=False


@pytest.mark.parametrize('field,value',[('gemini_key_input','fake-other-key'),('gemini_model','gemini-other'),('gemini_search',True)])
def test_changed_key_model_or_search_requires_new_setup_before_automatic_send(hybrid,field,value):
    app=hybrid.app
    hybrid.enable();app.loaded(hybrid.media)
    getattr(app,field).set(value)
    app.analyze()
    assert app.workflow_mode=='radar' and app.current_page=='settings'
    assert not hybrid.analyses and not hybrid.calls


def test_manual_review_can_still_be_declined_in_local_mode(hybrid,monkeypatch):
    from radar import gui
    app=hybrid.app
    app.use_radar_only();app.gemini_key_input.set(hybrid.key)
    app.connect_gemini();hybrid.finish()
    app.results((hybrid.media,hybrid.cuts,hybrid.speech,[]))
    app.table.selection_set(app.table.get_children())
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda *a:False)
    app.review_gemini()
    assert not hybrid.calls and not app.busy
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda *a:True)
    app.review_gemini();hybrid.finish()
    assert len(hybrid.calls)==1 and app.cuts[0].id==2


def test_pause_button_keeps_ui_responsive_and_cancel_stops_worker(hybrid,monkeypatch):
    import time
    from radar import gui
    app=hybrid.app
    def slow(*args,**kw):
        for n in range(300):
            kw['cancel'].checkpoint()
            kw['cancel'].report('Teste de lotes',n,300,'lotes')
            time.sleep(.01)
        return hybrid.media,hybrid.cuts,hybrid.speech,[]
    monkeypatch.setattr(gui,'analyze',slow)
    app.loaded(hybrid.media);app.analyze()
    app.pause_button.invoke()
    deadline=time.monotonic()+3
    while not app.cancel.snapshot()['paused'] and time.monotonic()<deadline:app.update();time.sleep(.02)
    assert app.cancel.snapshot()['paused']
    done=app.cancel.snapshot()['done']
    app.channel.set('Interface responsiva');app.update();time.sleep(.1)
    assert app.cancel.snapshot()['done']==done and app.channel.get()=='Interface responsiva'
    app.pause_button.invoke()
    app.cancel.set();hybrid.finish()
    assert not app.busy and 'cancelada' in app.resume_info.get().lower()


def test_gui_real_failure_resume_and_reopen(tmp_path,monkeypatch):
    import time
    from radar.gui import App
    from radar.media import executable,run,probe
    from radar import pipeline,gui
    monkeypatch.chdir(tmp_path)
    video=tmp_path/'original.mp4'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i',"color=black:s=128x72:r=10:d=24,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='gte(t,18)'",
         '-f','lavfi','-i','sine=frequency=440:duration=24','-c:v','libx264','-c:a','aac',video])
    monkeypatch.setattr(gui.messagebox,'showwarning',lambda *a:None)
    actual=pipeline.visual_features
    def fail(media,*a,**kw):
        if kw['start']==16:raise RuntimeError('Falha de lote para validar o botão de retomada')
        return actual(media,*a,**kw)
    monkeypatch.setattr(pipeline,'visual_features',fail)
    app=App();old=None;errors=[]
    monkeypatch.setattr(app,'error',lambda e:errors.append(str(e)))
    def finish(window):
        deadline=time.monotonic()+30
        while window.busy and time.monotonic()<deadline:window.update();time.sleep(.02)
        assert not window.busy and not errors,errors
        window.update()
    try:
        app.loaded(probe(video));app.option_vars['batch_seconds'].set('16')
        app.minimum.set('3');app.maximum.set('8');app.analyze();finish(app)
        assert app._analysis_error_dialog.winfo_exists() and app._has_resume
        assert 'Análise visual' in app.resume_info.get()
        app.skip_failed_module('visual');finish(app)
        assert app.current_page=='review' and not app.option_vars['visual'].get()
        app.option_vars['visual'].set(True)
        monkeypatch.setattr(pipeline,'visual_features',actual)
        app.resume_analysis_button.invoke();finish(app)
        assert app.current_page=='review' and app.cuts and not app._analysis_error_dialog
        app.close();old=app
        app=App()
        monkeypatch.setattr(app,'error',lambda e:errors.append(str(e)))
        app.loaded(probe(video))
        assert app.option_vars['batch_seconds'].get()=='16' and app._has_resume
        def unexpected(*a,**kw):raise AssertionError('Reabertura repetiu etapa já concluída')
        monkeypatch.setattr(pipeline,'visual_features',unexpected);monkeypatch.setattr(pipeline,'extract_audio',unexpected)
        app.resume_analysis();finish(app)
        assert app.cuts and app.current_page=='review' and app.jobs_table.get_children()
    finally:app.close()
