"""Executed by the frozen EXE on Windows; exercises bundled native dependencies."""
from pathlib import Path
import tempfile
import os
import errno
from unittest.mock import patch


def smoke():
    from radar.media import run, executable, probe
    from radar.pipeline import analyze
    from radar.export import export_clip, export_report, export_transcript
    from radar.model import Cut
    from radar.gui import App
    from radar.runtime import resolve_model
    from faster_whisper import WhisperModel
    import opentimelineio as otio

    tools = {name: executable(name) for name in ('ffmpeg', 'ffprobe', 'ffplay')}
    for path in tools.values():
        run([path, '-version'])
    app = App()
    app.update()
    app.close()
    with tempfile.TemporaryDirectory(prefix='radar-installed-smoke-') as tmp:
        tmp = Path(tmp)
        video = tmp / 'original.mp4'
        run([tools['ffmpeg'], '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=160x90:r=25:d=3',
             '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3', '-c:v', 'libx264', '-c:a', 'aac', video])
        media, cuts, speech, warnings = analyze(video, minimum=1, maximum=2, model='off', cache_dir=tmp/'cache')
        with patch('radar.pipeline.extract_audio',side_effect=AssertionError('Extração repetida após checkpoint')),\
             patch('radar.pipeline.sound_features',side_effect=AssertionError('Áudio repetido após checkpoint')),\
             patch('radar.pipeline.visual_features',side_effect=AssertionError('Imagem repetida após checkpoint')):
            resumed=analyze(video,minimum=1,maximum=2,model='off',cache_dir=tmp/'cache')
        assert [(c.start,c.end) for c in resumed[1]]==[(c.start,c.end) for c in cuts]
        assert media.source_id and resumed[0].source_id==media.source_id
        output = export_clip(media, Cut(1,.4,2.4,50,'Teste','Teste'), tmp/'corte.mp4')
        assert abs(probe(output).duration - 2) < .05
        with patch('radar.export.os.link', side_effect=OSError(errno.ENOTSUP,'Hard links not supported')):
            portable=export_clip(media, Cut(2,.4,2.4,50,'Teste','Teste'), tmp/'portable.mp4')
        assert abs(probe(portable).duration-2)<.05
        filmcraft_result=filmcraft_roundtrip(media,tmp/'projects') if os.environ.get('FILMCRAFT_CLI') else None
        export_report(media, cuts, tmp/'report.json')
        # Validate the packaged model/runtime/VAD and a real Portuguese speech sample offline.
        model_path = resolve_model('tiny')
        assert Path(model_path).is_dir(), 'Modelo tiny não incluído'
        model = WhisperModel(model_path, device='cpu', compute_type='int8', cpu_threads=2, local_files_only=True)
        silence = tmp/'silence.wav'
        run([tools['ffmpeg'],'-v','error','-f','lavfi','-i','anullsrc=r=16000:cl=mono','-t','1',silence])
        segments,_ = model.transcribe(str(silence), language='pt', vad_filter=True, beam_size=1)
        assert not list(segments), 'Silêncio gerou fala'
        from radar.runtime import bundled_root
        spoken = bundled_root()/'validation'/'fala-portugues.wav'
        assert spoken.is_file()
        segments,_ = model.transcribe(str(spoken), language='pt', beam_size=1, word_timestamps=True)
        segments=list(segments)
        text=' '.join(s.text for s in segments).lower()
        assert 'teste' in text and ('vídeo' in text or 'video' in text), text
        import wave
        with wave.open(str(spoken)) as wav:
            duration=wav.getnframes()/wav.getframerate()
        speech=[{'start':s.start,'end':s.end,'text':s.text,'words':[
            {'start':w.start,'end':w.end,'word':w.word} for w in (s.words or [])]} for s in segments]
        transcript_file=export_transcript(Cut(3,0,duration,50,'Fala de teste','Teste'),speech,tmp/'transcricao.txt')
        assert 'teste' in transcript_file.read_text(encoding='utf-8').lower()
        assert '00:00:00.000' in transcript_file.read_text(encoding='utf-8')
        del model
        # Phase 2 must work inside the real frozen app, not only in Python tests:
        # analyze a silent video using the bundled Portuguese recording at +2.5s.
        from radar.profiles import AnalysisOptions
        external_video=tmp/'external-source.mp4'
        run([tools['ffmpeg'],'-v','error','-f','lavfi','-i',
             f'color=blue:s=160x90:r=25:d={duration+3.5}','-c:v','libx264',external_video])
        external_media,external_cuts,external_speech,_=analyze(external_video,minimum=1,maximum=60,model='tiny',
            cache_dir=tmp/'external-cache',options=AnalysisOptions(external_audio=str(spoken),external_offset=2.5,
                                                                 visual=False,phrases='teste;vídeo'))
        assert external_speech and external_cuts
        assert min(s['start'] for s in external_speech)>=2.5
        assert all(w['start']>=2.5 for s in external_speech for w in s.get('words',[]))
        assert not external_media.audio and external_media.analysis_audio['offset']==2.5
        external_words=' '.join(s['text'] for s in external_speech).lower()
        assert 'teste' in external_words,external_words
        external_text=export_transcript(external_cuts[0],external_speech,tmp/'external-transcript.txt')
        exported_words=external_text.read_text(encoding='utf-8').lower()
        assert 'teste' in exported_words,exported_words
        assert len(otio.schema.Timeline().tracks)==0
        studio_result=studio_roundtrip(media,tmp/'studio')
        caption_result=caption_roundtrip(media,tmp/'captions')
        workspace_result=workspace_roundtrip(media,tmp/'workspace')
        import gc
        gc.collect()
        gemini_result=gemini_offline_smoke(tmp)
    return {'tools': tools, 'gui': True, 'media_export': True, 'whisper_int8': True,
            'silence_vad': True, 'portuguese_transcript': text, 'otio': True,
            'portable_export':True, 'transcript_txt':True,'checkpoint_resume':True,'local_cpu_without_api':True,
            'external_audio_sync':True,'speech_context':True,
            'studio':studio_result,'captions':caption_result,'workspace':workspace_result,'filmcraft':filmcraft_result, 'gemini_contract':gemini_result, 'gemini_live_api':False}


def workspace_roundtrip(media,folder):
    """The new dashboard/library must operate inside the frozen desktop too."""
    import time
    from radar.gui import App
    from radar.model import Cut
    folder.mkdir();previous=Path.cwd();app=None;errors=[]
    try:
        os.chdir(folder);app=App();app.error=lambda exc:errors.append(str(exc))
        assert app.current_page=='dashboard'
        app.loaded(media);app.cuts=[Cut(1,.4,2.4,0,'Clipe no pacote','Teste funcional',manual=True,favorite=True)]
        app.refresh();app.show_page('library');app.update()
        app.library_thumbnails()
        deadline=time.monotonic()+30
        while (app.busy or app._library_after is not None) and time.monotonic()<deadline:app.update();time.sleep(.02)
        assert not app.busy and not errors,errors
        assert set(app._library_cards)=={1} and 1 in app._library_photo_images
        app.library_select_page();assert app.library_selected=={1}
        app.library_target(1,'review');assert app.current_page=='review'
        app.library_target(1,'captions');assert app.current_page=='captions' and app._caption_cut_id==1
        app.show_page('dashboard');app.update();assert app.dashboard_stats['favorites'].get()=='1'
        app.show_page('jobs');app.update();assert app.activity_table.get_children()
    finally:
        if app is not None:app.close()
        os.chdir(previous)
    return {'dashboard':True,'real_thumbnail':True,'library_selection':True,'editor_navigation':True,'caption_navigation':True,'activity':True}


def caption_roundtrip(media,folder):
    """Exercise editable caption UI and all libass effects in the installed EXE."""
    import time
    from radar.captions import generate_track,CaptionStyle,set_style,update_cue
    from radar.caption_preview import frame
    from radar.export import export_clip,export_ass,export_srt
    from radar.media import probe,run,executable
    from radar.model import Cut
    from radar.render import RenderOptions
    from radar.projects import save_project,load_project
    from radar.gui import App
    folder.mkdir()
    cut=Cut(1,.4,2.4,0,'Legendas no pacote','Teste funcional',manual=True)
    speech=[{'start':.8,'end':1.8,'text':'CEFAS RADAR','words':[
        {'start':.8,'end':1.2,'word':'CEFAS'},{'start':1.2,'end':1.8,'word':'RADAR'}]}]
    cut.captions=generate_track(cut,speech)
    cut.captions=update_cue(cut.captions,1,text='CEFAS GAMER',start=.8,end=1.8)
    for effect in ('classic','highlight','pop','karaoke'):
        cut.captions=set_style(cut.captions,CaptionStyle(effect=effect,size=64))
        output=export_clip(media,cut,folder/f'{effect}.mp4',render_options=RenderOptions(preset='leve'))
        assert abs(probe(output).duration-2)<.05 and len(probe(output).audio)==len(media.audio)
    ass=export_ass(cut,speech,folder/'caption.ass',width=160,height=90)
    assert '\\kf' in ass.read_text(encoding='utf-8')
    srt=export_srt(cut,speech,folder/'caption.srt')
    assert '00:00:00,400 --> 00:00:01,400' in srt.read_text(encoding='utf-8')
    frame(media,cut,RenderOptions(),speech,.6,folder/'cursor.png')
    assert (folder/'cursor.png').stat().st_size>100
    project=save_project(folder/'caption.radar.json',media,[cut],speech)
    assert load_project(project)['cuts'][0].captions==cut.captions
    previous=Path.cwd();profile=folder/'profile';profile.mkdir();app=None;errors=[]
    try:
        os.chdir(profile);app=App();app.error=lambda e:errors.append(str(e))
        app.loaded(media);app.cuts=[cut];app.speech=speech;app.refresh();app.table.selection_set('1')
        app.show_page('captions');app.update()
        assert app._caption_cut_id==1 and app.caption_table.get_children()==('1',)
        app.caption_text.delete('1.0','end');app.caption_text.insert('1.0','CEFAS RADAR')
        app.caption_effect.set('Pop/Zoom');app.caption_apply_style()
        deadline=time.monotonic()+30
        while app.busy and time.monotonic()<deadline:app.update();time.sleep(.02)
        assert not app.busy and not errors,errors
        assert cut.captions['cues'][0]['text']=='CEFAS RADAR'
        assert cut.captions['cues'][0]['style']['effect']=='pop'
        assert app._caption_image.width()>0
    finally:
        if app is not None:app.close()
        os.chdir(previous)
    return {'four_cpu_styles':True,'editable_text':True,'word_timestamps':True,'short_offset':True,
            'srt_ass_mp4':True,'project_roundtrip':True,'synced_preview_gui':True,'audio_tracks_preserved':True}


def studio_roundtrip(media,folder):
    """Real render, persistence and interactive editing from inside the package."""
    import time
    from radar.export import export_clip
    from radar.media import probe
    from radar.model import Cut
    from radar.render import RenderOptions
    from radar.projects import save_project,load_project
    from radar.waveform import build_waveform
    from radar.gui import App
    folder.mkdir()
    cut=Cut(1,.4,2.4,0,'Corte manual','Teste funcional',favorite=True,review_state='approved',manual=True,
            framing={'crop_x':.3,'crop_y':.5})
    speech=[{'start':.8,'end':1.5,'text':'CEFAS RADAR','words':[
        {'start':.8,'end':1.1,'word':'CEFAS'},{'start':1.1,'end':1.5,'word':'RADAR'}]}]
    opts=RenderOptions(mode='vertical_crop',preset='leve',burn_subtitles=True)
    vertical=export_clip(media,cut,folder/'vertical.mp4',render_options=opts,speech=speech)
    rendered=probe(vertical)
    assert (rendered.width,rendered.height)==(720,1280) and abs(rendered.duration-2)<.05
    assert len(rendered.audio)==len(media.audio)
    project=save_project(folder/'studio.radar.json',media,[cut],speech,render=opts)
    loaded=load_project(project)
    assert loaded['cuts'][0].favorite and loaded['cuts'][0].manual and loaded['render'].burn_subtitles
    wave=build_waveform(media,bins=64,cache_dir=folder/'cache')
    assert wave['audio'] and any(wave['peaks'])
    previous=Path.cwd();profile=folder/'profile';profile.mkdir();app=None
    try:
        os.chdir(profile);app=App();app.loaded(media);app.show_page('review');app.studio_tabs.select(1)
        app.cut_start.set('00:00:00.400');app.cut_end.set('00:00:02.400');app.edit_title.set('Corte no pacote')
        app.create_manual_cut()
        deadline=time.monotonic()+20
        while app.busy and time.monotonic()<deadline:app.update();time.sleep(.02)
        assert not app.busy and app.cuts and app.cuts[0].manual
        app.toggle_favorite();assert app.cuts[0].favorite
        app.timeline.zoom(.5);assert app.timeline.view[1]-app.timeline.view[0]<media.duration
        app.open_studio_project(str(project))
        deadline=time.monotonic()+20
        while app.busy and time.monotonic()<deadline:app.update();time.sleep(.02)
        assert not app.busy and app.cuts[0].manual and app.cuts[0].favorite and app.rendering_from_ui().burn_subtitles
    finally:
        if app is not None:app.close()
        os.chdir(previous)
    return {'vertical_720x1280':True,'burned_subtitles':True,'original_audio_preserved':True,
            'project_roundtrip':True,'real_waveform':True,'manual_cut_gui':True,'favorite_gui':True,'timeline_zoom':True}


def filmcraft_roundtrip(media, folder):
    """Exercise the real external CLI from inside the frozen Python process."""
    import json
    import os
    from radar.filmcraft import capabilities, create_projects
    from radar.media import run,probe
    from radar.model import Cut
    cli=capabilities(os.environ['FILMCRAFT_CLI'])['cli']
    cuts=[Cut(i+1,a,b,50,f'Short {i+1}','Teste') for i,(a,b) in enumerate([(0,.6),(.8,1.6),(2,2.8)])]
    grouped=create_projects(media,cuts,folder,cli=cli)
    saved=grouped[0].read_bytes()
    individual=create_projects(media,cuts,folder,individual=True,cli=cli)
    assert len(grouped)==1 and len(individual)==3
    assert grouped[0].read_bytes()==saved
    for project,expected in [(grouped[0],3), *[(p,1) for p in individual]]:
        inspected=json.loads(run([cli,'--project',project,'inspect','project'],timeout=60))
        assert inspected
        data=json.loads(project.read_text(encoding='utf-8'))['project']['items']
        sequences=[item['kind']['Sequence'] for item in data.values() if 'Sequence' in item['kind']]
        assert len(sequences)==expected
        for seq in sequences:
            video=seq['video_tracks'][0]['items'][0]
            audio=seq['audio_tracks'][0]['items'][0]
            assert video['start']==audio['start']==0
            assert video['duration']==audio['duration']
            assert video['source_in']==audio['source_in']
    rendered=folder/'from-filmcraft.mp4'
    run([cli,'--project',grouped[0],'export',rendered,'--gpu-rendering','off'],timeout=120)
    assert abs(probe(rendered).duration-cuts[-1].duration)<.05
    desktop=False
    if os.environ.get('FILMCRAFT_TEST_DESKTOP')=='1':
        desktop=filmcraft_desktop(cli,grouped[0],folder)
    return {'grouped_sequences':3,'individual_projects':3,'repeated_same_folder':True,
            'native_reopen':True,'native_export':True,'desktop_open':desktop}


def filmcraft_desktop(cli, project, folder):
    import json
    import os
    import secrets
    import socket
    import time
    from radar.runtime import start_process
    from radar.media import run
    desktop=Path(cli).with_name('filmcraft.exe' if os.name=='nt' else 'filmcraft')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    token=secrets.token_hex(32)
    env={**os.environ,'FILMCRAFT_CONTROL_TOKEN':token}
    log=folder/'desktop-test.log'
    with log.open('wb') as out:
        p=start_process([desktop,'--no-recover','--control',str(port),'--data-dir',folder/'desktop-data',project],
                        stdout=out,stderr=out,env=env,cwd=str(desktop.parent))
    try:
        deadline=time.monotonic()+45
        last=''
        while time.monotonic()<deadline and p.poll() is None:
            try:
                info=json.loads(run([cli,'--bridge',f'127.0.0.1:{port}','inspect','project'],timeout=5,env=env))
                assert info['name']==project.stem
                assert len([i for i in info['root']['children'] if i.get('type')=='Sequence'])==3
                return True
            except RuntimeError as exc:
                last=str(exc)
                time.sleep(.5)
        detail=log.read_text(encoding='utf-8',errors='replace')[-5000:].replace(token,'[redacted]')
        raise RuntimeError('FilmCraft desktop não abriu o projeto no teste Windows. '+last+'\n'+detail)
    finally:
        if p.poll() is None:
            p.terminate()
            try:p.wait(timeout=10)
            except Exception:p.kill();p.wait()



def gemini_offline_smoke(folder):
    # No real credential or network request is used by package validation.
    import io,json
    from radar.credentials import KeyStore
    from radar.gemini import GeminiClient
    from radar.model import Media,Cut
    key='package-smoke-fake-credential-not-a-real-api-key'
    default_client=GeminiClient(key)  # construct packaged HTTPS/TLS handlers too
    class Response:
        def open(self,request,timeout):
            assert key not in request.full_url
            assert request.get_header('X-goog-api-key')==key
            if request.get_method()=='GET':
                return io.BytesIO(json.dumps({'models':[{'name':'models/gemini-smoke-flash',
                    'supportedGenerationMethods':['generateContent']}]}).encode())
            records=json.loads(json.loads(request.data)['contents'][0]['parts'][0]['text'])['cortes']
            content={'cortes':[{'id':r['id'],'nota_editorial':70 if r['id']==1 else 95,'titulo':'Exemplo','justificativa':'Fala com contexto',
                'sugestao_edicao':'Revisar o desfecho','limitacoes':'Sem vídeo e sem pesquisa'} for r in records]}
            return io.BytesIO(json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(content)}]}}]}).encode())
    cut=Cut(1,0,20,45,'Título local','Teste','Olha como consegui terminar esta missão!')
    result=GeminiClient(key,Response()).review(Media('/not-sent.mp4',30,160,90,25,'h264',0,[],0),[cut],model='gemini-smoke-flash')
    assert result['reviews'][0]['nota_editorial']==70
    assert cut.score==45 and cut.start==0 and cut.end==20
    protected=False
    if os.name=='nt':
        store=KeyStore(folder/'test-key.dpapi')
        store.save(key)
        assert store.load()==key and key.encode() not in store.path.read_bytes()
        store.delete()
        protected=True
    automatic_gemini_smoke(folder,lambda credential:GeminiClient(credential,Response()),key)
    return {'request_response':True,'local_times_preserved':True,'windows_dpapi':protected,
            'local_without_api':True,'gemini_validation_required':True,'automatic_selection':True}


def automatic_gemini_smoke(folder,client_factory,key):
    """Exercise automatic selection inside the frozen app in an isolated profile."""
    import time
    from radar import gui
    from radar.model import Media,Cut
    previous=Path.cwd()
    profile=folder/'gui-test-profile';profile.mkdir()
    app=None
    try:
        os.chdir(profile)
        with patch('radar.gui.GeminiClient',client_factory),patch('radar.gui.messagebox.askyesno',return_value=True):
            app=gui.App()
            assert app.current_page=='dashboard' and app.workflow_mode=='radar' and app.model.get()=='off'
            def finish():
                deadline=time.monotonic()+15
                while app.busy and time.monotonic()<deadline:
                    app.update();time.sleep(.02)
                assert not app.busy,'A revisão simulada não terminou'
                app.update()
            app.gemini_key_input.set(key)
            app.connect_gemini();finish()
            app.enable_gemini()
            assert app.workflow_mode=='gemini'
            media=Media('/not-sent.mp4',100,160,90,25,'h264',0,[],0)
            cuts=[Cut(1,0,20,90,'Local 1','Teste'),Cut(2,40,60,45,'Local 2','Teste')]
            speech=[{'start':1,'end':10,'text':'Primeira fala completa.','words':[]},
                    {'start':41,'end':50,'text':'Segunda fala com desfecho.','words':[]}]
            original=[(c.start,c.end,c.score,c.title) for c in cuts]
            app.loaded(media);app._requested_count=1
            app.results((media,cuts,speech,[]));finish()
            assert [c.id for c in app.cuts]==[2],'O Gemini não participou da seleção final'
            assert [(c.start,c.end,c.score,c.title) for c in cuts]==original
            assert app._pending_review is None and app._valid_ai(app.cuts[0])['nota_editorial']==95
    finally:
        if app is not None:app.close()
        os.chdir(previous)
