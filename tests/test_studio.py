"""Studio verification with real FFmpeg, pixel crops, subtitles and persisted edits."""
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from radar.checkpoints import signature
from radar.control import ExecutionControl
from radar.export import export_clip,export_clips,export_srt,subtitle_entries
from radar.media import executable,probe,run,Cancelled
from radar.model import Cut
from radar.profiles import AnalysisOptions
from radar.projects import save_project,load_project
from radar.render import RenderOptions
from radar.waveform import build_waveform


@pytest.fixture(scope='module')
def source(tmp_path_factory):
    path=tmp_path_factory.mktemp('studio-media')/'partida com espaços.mp4'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i',
         'color=red:s=320x180:r=25:d=8,drawbox=x=160:y=0:w=160:h=180:color=blue:t=fill',
         '-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=8',
         '-f','lavfi','-i','sine=frequency=880:sample_rate=16000:duration=8',
         '-filter_complex',"[1:a]volume='if(between(t,3,4),1,0.001)':eval=frame[a]",
         '-map','0:v','-map','[a]','-map','2:a','-c:v','libx264','-c:a','aac',path])
    return path


def cut(a=1.,b=2.):return Cut(1,a,b,55,'Título Cefas','Teste de origem')


def frame(path,t,tmp_path):
    raw=tmp_path/f'pixels-{time.time_ns()}.rgb'
    run([executable('ffmpeg'),'-v','error','-ss',t,'-i',path,'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo',raw])
    media=probe(path)
    return np.frombuffer(raw.read_bytes(),dtype=np.uint8).reshape(media.height,media.width,3)


@pytest.mark.parametrize('mode,size',[('original',(320,180)),('landscape',(1280,720)),('vertical_crop',(720,1280)),('vertical_blur',(720,1280))])
def test_rendered_formats_have_real_dimensions_original_duration_and_all_audio(source,tmp_path,mode,size):
    media=probe(source)
    out=export_clip(media,cut(1.12,2.36),tmp_path/f'{mode}.mp4',render_options=RenderOptions(mode=mode,preset='leve'))
    result=probe(out)
    assert (result.width,result.height)==size
    assert result.duration==pytest.approx(1.24,abs=.05)
    assert len(result.audio)==2
    if mode=='vertical_blur':
        pixels=frame(out,.3,tmp_path)
        # The original horizontal red/blue image remains complete in the middle.
        assert pixels[640,50,0]>180 and pixels[640,670,2]>180


def test_individual_crop_positions_select_distinct_original_regions(source,tmp_path):
    media=probe(source);left=cut();right=replace(cut(),id=2,framing={'crop_x':1.,'crop_y':.5})
    left.framing={'crop_x':0.,'crop_y':.5}
    files=export_clips(media,[right,left],tmp_path/'clips',cache_dir=tmp_path/'cache',
                       render_options=RenderOptions(mode='vertical_crop',preset='leve'))
    red,blue=[frame(p,.3,tmp_path)[600:680,300:420].mean(axis=(0,1)) for p in files]
    assert red[0]>180 and red[2]<50
    assert blue[2]>180 and blue[0]<50


def test_burned_subtitles_are_visible_only_during_the_retained_words(source,tmp_path):
    media=probe(source);c=cut(1.,3.)
    speech=[{'start':.5,'end':3.5,'text':'fora TESTE CEFAS depois','words':[
        {'start':.5,'end':.8,'word':'fora'},{'start':1.4,'end':1.7,'word':'TESTE'},
        {'start':1.7,'end':2.,'word':'CEFAS'},{'start':3.2,'end':3.5,'word':'depois'}]}]
    out=export_clip(media,c,tmp_path/'legenda.mp4',render_options=RenderOptions(burn_subtitles=True),speech=speech)
    before,active=[frame(out,t,tmp_path) for t in (.1,.6)]
    white=lambda image:int(np.count_nonzero(np.min(image[-80:],axis=2)>180))
    assert white(before)<5 and white(active)>20
    srt=export_srt(c,speech,tmp_path/'legenda.srt').read_text(encoding='utf-8')
    assert '00:00:00,400 --> 00:00:01,000' in srt and 'TESTE CEFAS' in srt
    assert 'fora' not in srt and 'depois' not in srt


def test_caption_requests_fail_before_creating_an_empty_export(source,tmp_path):
    target=tmp_path/'bad.mp4'
    with pytest.raises(ValueError,match='transcrição'):export_clip(probe(source),cut(),target,render_options=RenderOptions(burn_subtitles=True))
    assert not target.exists()


def test_caption_text_cannot_move_itself_out_of_the_fixed_subtitle_area(source,tmp_path):
    speech=[{'start':1.1,'end':1.9,'text':r'{\an8} CEFAS','words':[]}]
    out=export_clip(probe(source),cut(),tmp_path/'literal.mp4',render_options=RenderOptions(burn_subtitles=True),speech=speech)
    pixels=frame(out,.4,tmp_path)
    assert np.count_nonzero(np.min(pixels[-80:],axis=2)>180)>20
    assert np.count_nonzero(np.min(pixels[:40],axis=2)>180)<5


def test_vertical_export_with_nonzero_origin_preserves_delayed_audio(tmp_path):
    original=tmp_path/'offset.mkv'
    run([executable('ffmpeg'),'-v','error','-copyts','-f','lavfi','-i','color=red:s=160x90:r=25:d=6',
         '-itsoffset','1','-f','lavfi','-i','sine=frequency=440:duration=5',
         '-map','0:v','-map','1:a','-c:v','libx264','-c:a','pcm_s16le','-output_ts_offset','5',original])
    out=export_clip(probe(original),cut(.4,3.2),tmp_path/'vertical.mp4',
                    render_options=RenderOptions(mode='vertical_crop',preset='leve'))
    result=probe(out)
    assert (result.width,result.height)==(720,1280) and result.duration==pytest.approx(2.8,abs=.05)
    from radar.media import extract_audio
    import wave
    audio=tmp_path/'audio.wav';extract_audio(result,audio)
    with wave.open(str(audio),'rb') as wav:x=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(float)
    assert np.max(np.abs(x[:6000]))<5 and np.sqrt(np.mean(x[16000:20000]**2))>100


def test_word_cues_use_real_pauses_and_never_invent_proportional_timestamps():
    speech=[{'start':0,'end':10,'text':'um dois três','words':[
        {'start':1.1,'end':1.4,'word':'um'},{'start':1.5,'end':1.8,'word':'dois'},{'start':4.2,'end':4.7,'word':'três'}]}]
    entries=subtitle_entries(cut(0,8),speech)
    assert [(e['start'],e['end']) for e in entries]==[(1.1,1.8),(4.2,4.7)]
    assert subtitle_entries(cut(2,5),[{'start':0,'end':10,'text':'frase sem palavras','words':[]}])==[]


def test_render_queue_reuses_intact_outputs_but_keeps_different_presets_separate(source,tmp_path,monkeypatch):
    import radar.export as export
    media=probe(source);folder=tmp_path/'clips';cache=tmp_path/'cache'
    opts=RenderOptions(mode='landscape',preset='leve')
    first=export_clips(media,[cut()],folder,cache_dir=cache,render_options=opts)
    original=first[0].read_bytes();actual=export.export_clip
    def unexpected(*a,**kw):raise AssertionError('Recodificou exportação íntegra sem mudar o preset')
    monkeypatch.setattr(export,'export_clip',unexpected)
    assert export_clips(media,[cut()],folder,cache_dir=cache,render_options=opts)==first
    monkeypatch.setattr(export,'export_clip',actual)
    changed=export_clips(media,[cut()],folder,cache_dir=cache,render_options=replace(opts,mode='vertical_crop'))
    assert changed[0]!=first[0] and first[0].read_bytes()==original
    assert probe(changed[0]).height==1280


def test_real_waveform_peaks_keep_source_times_and_cache_is_independent(source,tmp_path,monkeypatch):
    from radar import waveform
    media=probe(source)
    # Isolate the microphone from the mixed source for an observable quiet/loud pulse.
    mono=tmp_path/'mic.mp4'
    run([executable('ffmpeg'),'-v','error','-i',source,'-map','0:v','-map','0:a:0','-c','copy',mono])
    media=probe(mono);data=build_waveform(media,cache_dir=tmp_path/'cache')
    assert len(data['peaks'])<=2048 and data['audio']
    step=(data['end']-data['start'])/len(data['peaks'])
    loud=[p for i,p in enumerate(data['peaks']) if 3.2<i*step<3.8]
    quiet=[p for i,p in enumerate(data['peaks']) if .5<i*step<1.]
    assert max(loud)>100*max(quiet)
    def unexpected(*a,**kw):raise AssertionError('Releu o áudio de uma janela já armazenada')
    monkeypatch.setattr(waveform,'extract_audio',unexpected)
    assert build_waveform(media,cache_dir=tmp_path/'cache')==data
    monkeypatch.undo()
    zoom=build_waveform(media,start=2.,end=5.,cache_dir=tmp_path/'cache')
    assert zoom['start']==2. and zoom['end']==5. and max(zoom['peaks'])>.05


def test_waveform_silent_video_and_cancel_leave_no_completed_fake_cache(tmp_path):
    source=tmp_path/'silent.mp4'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i','color=black:s=32x18:d=2','-c:v','libx264',source])
    data=build_waveform(probe(source),cache_dir=tmp_path/'cache')
    assert not data['audio'] and not any(data['peaks'])
    cancelled=threading.Event();cancelled.set()
    with pytest.raises(Cancelled):build_waveform(probe(source),cancelled,cache_dir=tmp_path/'cancelled')
    assert not list((tmp_path/'cancelled').rglob('*.json'))


def test_project_roundtrip_preserves_manual_edits_favorites_speech_and_presets(source,tmp_path):
    c=replace(cut(),favorite=True,review_state='approved',manual=True,framing={'crop_x':.1,'crop_y':.8})
    speech=[{'start':1.2,'end':1.8,'text':'Olá Cefas','words':[]}]
    path=save_project(tmp_path/'Meu canal.radar.json',probe(source),[c],speech,
        analysis=AnalysisOptions(phrases='batalha azul'),render=RenderOptions(mode='vertical_blur',preset='leve'),
        request={'model':'tiny','count':5,'gemini_api_key':'fake-key-that-must-not-be-saved'})
    assert b'fake-key-that-must-not-be-saved' not in path.read_bytes()
    loaded=load_project(path)
    assert loaded['cuts']==[c] and loaded['cuts'][0].category=='Manual'
    assert loaded['speech']==speech and loaded['render'].mode=='vertical_blur'
    assert loaded['analysis'].phrases=='batalha azul' and loaded['request']['model']=='tiny'
    with pytest.raises(FileExistsError):save_project(path,probe(source),[c],speech)
    saved=path.read_bytes()
    with pytest.raises(ValueError):save_project(source,probe(source),[c],speech,overwrite=True)
    assert path.read_bytes()==saved


def test_project_detects_modified_original_and_can_relocate_identical_content(source,tmp_path):
    original=tmp_path/'original.mp4';original.write_bytes(source.read_bytes())
    path=save_project(tmp_path/'project.radar.json',probe(original),[cut()],[])
    moved=tmp_path/'moved.mp4';shutil.copy2(original,moved);original.unlink()
    with pytest.raises(FileNotFoundError,match='Localizar vídeo'):load_project(path)
    assert load_project(path,source_override=moved)['media'].path==str(moved)
    with moved.open('ab') as out:out.write(b'changed')
    with pytest.raises(ValueError,match='não corresponde'):load_project(path,source_override=moved)


def test_project_integrity_and_invalid_intervals_are_rejected(source,tmp_path):
    path=save_project(tmp_path/'project.radar.json',probe(source),[cut()],[])
    data=json.loads(path.read_text(encoding='utf-8'));data['payload']['title']='alterado'
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match='integridade'):load_project(path)
    data['payload']['cuts'][0]['end']=999;data['sha256']=signature(data['payload'])
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match='Intervalo'):load_project(path)


def test_failed_project_replacement_keeps_the_previous_valid_review(source,tmp_path,monkeypatch):
    path=save_project(tmp_path/'project.radar.json',probe(source),[cut()],[])
    original=path.read_bytes()
    def failure(*a):raise OSError('Falha sintética ao finalizar gravação')
    monkeypatch.setattr(os,'replace',failure)
    with pytest.raises(OSError):save_project(path,probe(source),[replace(cut(),favorite=True)],[],overwrite=True)
    assert path.read_bytes()==original and not load_project(path)['cuts'][0].favorite
    assert not list(tmp_path.glob('checkpoint-*.tmp'))


def test_export_from_saved_project_cli_does_not_run_analysis(source,tmp_path):
    project=save_project(tmp_path/'project.radar.json',probe(source),[replace(cut(),favorite=True,review_state='approved')],[],
                         render=RenderOptions(mode='landscape',preset='leve'))
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])}
    result=subprocess.run([sys.executable,'-m','radar','--project',str(project),'--only-favorites','--only-approved',
                           '--export-dir',str(tmp_path/'clips'),'--output',str(tmp_path/'result.json')],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    assert 'Transcrição opcional' not in result.stdout
    assert probe(next((tmp_path/'clips').glob('*.mp4'))).width==1280
    assert json.loads((tmp_path/'result.json').read_text(encoding='utf-8'))['cuts'][0]['favorite']


@pytest.fixture
def gui_cleanup(monkeypatch):
    yield
    monkeypatch.undo()
    import gc
    gc.collect()


@pytest.mark.skipif(os.name!='nt' and not os.environ.get('DISPLAY'),reason='Requer display X11')
def test_timeline_manual_cut_favorite_save_reopen_and_reanalysis_keep_edits(source,tmp_path,monkeypatch,gui_cleanup):
    from radar.gui import App
    from radar.desktop_studio import filedialog
    monkeypatch.chdir(tmp_path);app=App();errors=[]
    monkeypatch.setattr(app,'error',lambda exc:errors.append(str(exc)))
    project=tmp_path/'studio.radar.json'
    monkeypatch.setattr(filedialog,'asksaveasfilename',lambda **kw:str(project))
    def finish():
        deadline=time.monotonic()+30
        while app.busy and time.monotonic()<deadline:app.update();time.sleep(.02)
        app.update();assert not app.busy and not errors,errors
    try:
        app.loaded(probe(source));app.show_page('review');app.studio_tabs.select(1);app.update()
        # Actual shift-drag interaction stages a source interval before a manual cut.
        timeline=app.timeline
        timeline.press(SimpleNamespace(x=timeline.x_at(1.),y=45,state=1))
        timeline.motion(SimpleNamespace(x=timeline.x_at(3.),y=45,state=1))
        timeline.release(SimpleNamespace(x=timeline.x_at(3.),y=45,state=1))
        app.edit_title.set('Meu momento');app.create_manual_cut();finish()
        assert len(app.cuts)==1 and app.cuts[0].manual and app.cuts[0].start==pytest.approx(1.,abs=.05)
        manual_id=app.cuts[0].id
        assert app.project_dirty and 'por salvar' in app.page_subtitle.get()
        app.toggle_favorite();app.review_label.set('Aprovado');app.apply_review()
        app.render_mode_label.set('Vertical 9:16 — recorte');app.render_vars['crop_x'].set('0,1');app.apply_framing()
        app.load_waveform();finish()
        assert timeline.waveform and timeline.waveform['peaks']
        app.studio_preview_frame(2.);finish()
        assert app._preview_image.width()>0 and app._mini_image.width()<=96 and app._mini_image.height()<=50
        timeline.zoom(.5);assert timeline.view[1]-timeline.view[0]<app.media.duration
        timeline.pan('moveto','.5');assert timeline.view[0]>0
        app.save_studio_project();finish()
        assert project.is_file()
        assert not app.project_dirty and 'salvo' in app.page_subtitle.get()
        app.cuts=[];app.open_studio_project(str(project));finish()
        c=app.cuts[0]
        assert c.favorite and c.review_state=='approved' and c.framing['crop_x']==.1
        app.results((app.media,[Cut(manual_id,4.,6.,70,'Automático','Teste')],[],[]))
        assert len(app.cuts)==2 and next(c for c in app.cuts if c.manual).id==manual_id
        assert len({c.id for c in app.cuts})==2
        automatic=next(c for c in app.cuts if not c.manual)
        app.table.selection_set(str(automatic.id));app.show_detail()
        app.edit_title.set('Título revisado por mim');app.edit_notes.set('Minha observação');app.apply_review()
        app.results((app.media,[replace(automatic,title='Título novo do detector',editing='nova sugestão',score=80,user_edited=False)],[],[]))
        kept=next(c for c in app.cuts if not c.manual)
        assert kept.title=='Título revisado por mim' and kept.editing=='Minha observação' and kept.score==80
        app.review_filter.set('Favoritos');app.refresh()
        assert app.table.get_children()==(str(manual_id),)
        app.geometry('1000x620');app.review_tabs.select(3);app.studio_tabs.select(1);app.update()
        def buttons(widget):
            from tkinter import ttk
            for child in widget.winfo_children():
                if isinstance(child,ttk.Button):yield child
                yield from buttons(child)
        for button in buttons(app):
            if not button.winfo_viewable():continue
            assert button.winfo_rootx()+button.winfo_width()<=app.winfo_rootx()+app.winfo_width()
            assert button.winfo_rooty()+button.winfo_height()<=app.winfo_rooty()+app.winfo_height()
    finally:app.close()
