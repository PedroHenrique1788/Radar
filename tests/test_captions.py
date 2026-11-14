"""Editable captions: original/Short timing, cache reuse and real libass pixels."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import time
import wave

import numpy as np
import pytest

from radar.captions import (CaptionStyle,EFFECTS,generate_track,entries_for_cut,
    update_cue,set_style,set_words,style_for,validate_track)
from radar.caption_preview import frame as preview_frame
from radar.checkpoints import CheckpointStore,signature
from radar.export import export_clip,export_srt,export_ass,export_clips
from radar.media import run,probe,executable,extract_audio
from radar.model import Cut
from radar.profiles import AnalysisOptions
from radar.projects import save_project,load_project
from radar.render import RenderOptions


def clip(a=2.4,b=5.4):return Cut(1,a,b,55,'Cefas Gamer','Teste')


def speech():
    return [{'start':2.6,'end':4.4,'text':'CEFAS RADAR TESTE','words':[
        {'start':2.6,'end':3.2,'word':'CEFAS'},
        {'start':3.2,'end':3.8,'word':'RADAR'},
        {'start':3.8,'end':4.4,'word':'TESTE'}]}]


@pytest.fixture(scope='module')
def movie(tmp_path_factory):
    path=tmp_path_factory.mktemp('caption-media')/'partida com espaços.mp4'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i','color=black:s=320x180:r=25:d=8',
         '-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=8',
         '-f','lavfi','-i','sine=frequency=880:sample_rate=16000:duration=8',
         '-filter_complex',"[1:a]volume='if(between(t,3,4),1,0.001)':eval=frame[a]",
         '-map','0:v','-map','[a]','-map','2:a','-c:v','libx264','-c:a','aac',path])
    return path


def pixels(path,t,tmp_path):
    raw=tmp_path/f'pixels-{time.time_ns()}.rgb'
    run([executable('ffmpeg'),'-v','error','-ss',t,'-i',path,'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo',raw])
    info=json.loads(run([executable('ffprobe'),'-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',path]))['streams'][0]
    return np.frombuffer(raw.read_bytes(),dtype=np.uint8).reshape(info['height'],info['width'],3)


def test_track_reuses_words_without_mutating_whisper_and_rebases_short(tmp_path):
    original=speech();saved=deepcopy(original);c=clip();c.captions=generate_track(c,original)
    assert original==saved
    assert c.captions['cues'][0]['words']==saved[0]['words']
    srt=export_srt(c,original,tmp_path/'short.srt').read_text(encoding='utf-8')
    assert '00:00:00,200 --> 00:00:02,000' in srt
    changed=replace(c,start=3.4)
    entries=entries_for_cut(changed)
    assert entries[0]['start']==3.4 and entries[0]['text']=='RADAR TESTE'
    assert entries[0]['words'][0]['start']==3.4
    trimmed=export_srt(changed,original,tmp_path/'trimmed.srt').read_text(encoding='utf-8')
    assert '00:00:00,000 --> 00:00:01,000' in trimmed and 'CEFAS' not in trimmed
    assert original==saved and c.captions['cues'][0]['start']==2.6


def test_manual_text_and_timing_preserve_only_known_word_alignment():
    track=generate_track(clip(),speech());saved=deepcopy(track)
    corrected=update_cue(track,1,text='CEFAS GAMER TESTE',start=2.7,end=4.5)
    assert corrected['cues'][0]['words'][1]['word']=='GAMER'
    assert corrected['cues'][0]['words'][0]['start']==pytest.approx(2.7)
    assert track==saved
    changed=update_cue(corrected,1,text='CEFAS GAMER',start=2.7,end=4.5)
    assert changed['cues'][0]['words']==[]  # no proportional invented times
    synced=set_words(changed,1,[{'word':'CEFAS','start':2.8,'end':3.2},{'word':'GAMER','start':3.3,'end':4.1}])
    assert len(synced['cues'][0]['words'])==2
    with pytest.raises(ValueError,match='ordem'):
        set_words(changed,1,[{'word':'CEFAS','start':2.8,'end':3.6},{'word':'GAMER','start':3.3,'end':4.1}])


@pytest.mark.parametrize('bad',[
    {'size':float('nan')},{'color':'red'},{'font':r'Arial,{\pos(0,0)}'},
    {'effect':'unsupported'},{'x':-1},{'shadow':20},{'bold':'yes'},
])
def test_invalid_style_is_rejected_before_rendering(bad):
    with pytest.raises(ValueError):CaptionStyle.from_record(bad)


def test_global_individual_styles_and_disable_keep_editable_data(tmp_path):
    c=clip();c.captions=generate_track(c,speech())
    c.captions=set_style(c.captions,CaptionStyle(effect='pop'),1)
    c.captions=set_style(c.captions,CaptionStyle(effect='karaoke',color='#FFF000'))
    assert style_for(c.captions).effect=='karaoke'
    assert style_for(c.captions,c.captions['cues'][0]).effect=='pop'
    saved=deepcopy(c.captions);c.captions['enabled']=False
    assert entries_for_cut(c)==[]
    assert export_srt(c,[],tmp_path/'disabled.srt').is_file()
    assert 'Dialogue:' in export_ass(c,[],tmp_path/'disabled.ass').read_text(encoding='utf-8')
    assert c.captions['cues']==saved['cues']


def test_project_roundtrip_keeps_original_and_edited_tracks_and_reads_v1(movie,tmp_path):
    c=clip();data=speech();c.captions=generate_track(c,data)
    c.captions=update_cue(c.captions,1,text='CEFAS GAMER TESTE',start=2.6,end=4.4)
    c.captions=set_style(c.captions,CaptionStyle(effect='highlight',font='DejaVu Sans',size=80),1)
    path=save_project(tmp_path/'caption.radar.json',probe(movie),[c],data)
    loaded=load_project(path)
    assert loaded['cuts'][0].captions==c.captions and loaded['speech']==data
    old=json.loads(path.read_text(encoding='utf-8'));old['payload']['version']=1
    for row in old['payload']['cuts']:row.pop('captions')
    old['sha256']=signature(old['payload'])
    legacy=tmp_path/'old.radar.json';legacy.write_text(json.dumps(old),encoding='utf-8')
    assert load_project(legacy)['cuts'][0].captions=={}


def test_ass_exports_effects_custom_style_and_literal_text_without_override_injection(tmp_path):
    c=clip();c.captions=generate_track(c,[{'start':2.6,'end':4.4,'text':r'{\an8} teste','words':[]}])
    c.captions=set_style(c.captions,CaptionStyle(effect='pop',font='Arial',size=90,color='#AABBCC',x=.2,y=.7,outline=3,shadow=2))
    text=export_ass(c,[],tmp_path/'style.ass',width=720,height=1280).read_text(encoding='utf-8')
    assert '0:00:00.20,0:00:02.00' in text and '&H00CCBBAA' in text
    assert r'\pos(144.00,896.00)' in text and r'\t(0,120,' in text
    assert r'{\an8}' not in text and '｛＼an8｝' in text
    assert r'{\an8}' in export_srt(c,[],tmp_path/'literal.srt').read_text(encoding='utf-8')


def test_cached_full_analysis_is_used_without_whisper_or_audio_extraction(movie,tmp_path,monkeypatch):
    from radar import pipeline,caption_transcription as service
    def transcribe(items,model,cancel,progress,**kw):
        for item in items:kw['checkpoint'](item['index'],speech())
    monkeypatch.setattr(pipeline,'transcribe',transcribe)
    opts=AnalysisOptions(visual=False,batch_seconds=16)
    media,_,_,_=pipeline.analyze(movie,minimum=1,maximum=5,model='tiny',options=opts,cache_dir=tmp_path/'cache')
    manifest=CheckpointStore(movie,tmp_path/'cache').manifest_path.read_bytes()
    def unexpected(*a,**kw):raise AssertionError('Reprocessou uma transcrição válida')
    monkeypatch.setattr(service,'transcribe',unexpected);monkeypatch.setattr(service,'extract_audio',unexpected)
    result=service.transcribe_cut(media,clip(),model='tiny',options=opts,cache_dir=tmp_path/'cache')
    assert result[0]['words']==speech()[0]['words']
    assert CheckpointStore(movie,tmp_path/'cache').manifest_path.read_bytes()==manifest
    # Cached silence is valid, not a missing transcript.
    store=CheckpointStore(movie,tmp_path/'cache');key=store.manifest['stages']['transcription']['key']
    store.save('transcription',key,[],0)
    assert service.transcribe_cut(media,clip(),options=opts,cache_dir=tmp_path/'cache')==[]


def test_only_short_audio_is_transcribed_and_repeated_request_uses_cache(movie,tmp_path,monkeypatch):
    from radar import caption_transcription as service
    extracted=[];decoded=[];actual=service.extract_audio
    def extract(*a,**kw):extracted.append((kw['start'],kw['duration']));return actual(*a,**kw)
    def transcribe(items,model,cancel,progress,**kw):
        decoded.extend((item['start'],item['duration']) for item in items)
        for item in items:kw['checkpoint'](item['index'],speech())
    monkeypatch.setattr(service,'extract_audio',extract);monkeypatch.setattr(service,'transcribe',transcribe)
    media=probe(movie);kwargs={'cache_dir':tmp_path/'cache','options':AnalysisOptions()}
    first=service.transcribe_cut(media,clip(),**kwargs)
    assert extracted==[(2.4,pytest.approx(3.))] and decoded==extracted
    assert service.transcribe_cut(media,clip(),**kwargs)==first and len(decoded)==1
    service.transcribe_cut(media,clip(1.4,5.4),**kwargs)
    assert extracted[-1]==(1.4,pytest.approx(1.))  # only the newly exposed second


@pytest.mark.parametrize('effect',list(EFFECTS))
def test_real_mp4_styles_and_cursor_preview_are_synchronized(movie,tmp_path,effect):
    media=probe(movie);c=clip();c.captions=generate_track(c,speech())
    c.captions=set_style(c.captions,CaptionStyle(effect=effect,size=110,highlight='#22FF55',y=.6,outline=0,shadow=0))
    out=export_clip(media,c,tmp_path/f'{effect}.mp4',render_options=RenderOptions(preset='leve'))
    result=probe(out)
    assert result.duration==pytest.approx(3.,abs=.05) and len(result.audio)==2
    before=pixels(out,.04,tmp_path);active=pixels(out,.44,tmp_path)
    assert np.max(before)<20 and np.count_nonzero(np.max(active,axis=2)>150)>50
    image=preview_frame(media,c,RenderOptions(),[],.44,tmp_path/'cursor.png')
    # Preview renders at the same clip-relative PTS as the exported video.
    preview=pixels(image,0,tmp_path)
    assert np.mean(np.abs(preview.astype(float)-active.astype(float)))<4
    if effect=='highlight':
        green=lambda x:(x[:,:,1]>160)&(x[:,:,0]<100)&(x[:,:,2]<160)
        x1=np.where(green(active))[1].mean();x2=np.where(green(pixels(out,1.04,tmp_path)))[1].mean()
        assert x2>x1+30
    if effect=='karaoke':
        green=lambda x:np.count_nonzero((x[:,:,1]>160)&(x[:,:,0]<100)&(x[:,:,2]<160))
        assert green(pixels(out,.68,tmp_path))>green(pixels(out,.28,tmp_path))+30
    if effect=='pop':
        box=lambda x:np.ptp(np.where(np.min(x,axis=2)>170)[1])
        assert box(pixels(out,.32,tmp_path))>box(pixels(out,.24,tmp_path))


def test_mp4_preserves_aac_packets_and_pcm_alignment(movie,tmp_path):
    media=probe(movie);c=clip();c.captions=generate_track(c,speech())
    out=export_clip(media,c,tmp_path/'preserved.mp4')
    def hashes(path):
        data=json.loads(run([executable('ffprobe'),'-v','error','-select_streams','a:0','-show_packets','-show_data_hash','sha256','-of','json',path]))
        return [p['data_hash'] for p in data['packets']]
    original=hashes(movie);copied=hashes(out)
    assert len(copied)>30 and all(h in original for h in copied)
    def pcm(media,path,**kwargs):
        extract_audio(media,path,track=str(media.audio[0]['index']),**kwargs)
        with wave.open(str(path),'rb') as stream:return np.frombuffer(stream.readframes(stream.getnframes()),dtype='<i2')
    expected=pcm(media,tmp_path/'expected.wav',start=c.start,duration=c.duration)
    actual=pcm(probe(out),tmp_path/'actual.wav')
    count=min(len(expected),len(actual))
    assert np.max(np.abs(actual[:count].astype(int)-expected[:count].astype(int)))<=1


@pytest.mark.parametrize('codec,output_codec',[('pcm_s16le','alac'),('aac','aac')])
def test_nonzero_origin_delayed_audio_preserves_quality_and_sync(tmp_path,codec,output_codec):
    source=tmp_path/'offset.mkv'
    run([executable('ffmpeg'),'-v','error','-copyts','-f','lavfi','-i','color=black:s=160x90:r=25:d=6',
         '-itsoffset','1','-f','lavfi','-i','sine=frequency=440:duration=5',
         '-map','0:v','-map','1:a','-c:v','libx264','-c:a',codec,'-output_ts_offset','5',source])
    media=probe(source);c=clip(.4,3.2);c.captions=generate_track(c,[{'start':1.2,'end':2.4,'text':'fala sincronizada','words':[]}])
    out=export_clip(media,c,tmp_path/'lossless.mp4')
    info=probe(out);assert info.audio[0]['codec']==output_codec
    audio=tmp_path/'audio.wav';extract_audio(info,audio)
    with wave.open(str(audio),'rb') as stream:x=np.frombuffer(stream.readframes(stream.getnframes()),dtype='<i2')
    assert np.max(np.abs(x[:6000]))<5 and np.sqrt(np.mean(x[16000:20000].astype(float)**2))>100
    assert np.max(pixels(out,.2,tmp_path))<20 and np.max(pixels(out,1.1,tmp_path))>180
    image=preview_frame(media,c,RenderOptions(),[],1.1,tmp_path/'origin.png')
    assert np.mean(np.abs(pixels(image,0,tmp_path).astype(float)-pixels(out,1.1,tmp_path).astype(float)))<4


def test_changed_caption_invalidates_export_queue_without_overwriting_old_mp4(movie,tmp_path):
    c=clip();c.captions=generate_track(c,speech());media=probe(movie)
    kw={'cache_dir':tmp_path/'cache'}
    first=export_clips(media,[c],tmp_path/'clips',**kw)[0];saved=first.read_bytes()
    assert export_clips(media,[c],tmp_path/'clips',**kw)==[first]
    c.captions=update_cue(c.captions,1,text='CEFAS GAMER TESTE',start=2.6,end=4.4)
    second=export_clips(media,[c],tmp_path/'clips',**kw)[0]
    assert second!=first and first.read_bytes()==saved


def test_caption_disable_really_removes_burned_pixels_but_retains_style(movie,tmp_path):
    c=clip();c.captions=generate_track(c,speech());saved=deepcopy(c.captions)
    c.captions['enabled']=False
    # Track toggle takes precedence over the old burn checkbox.
    out=export_clip(probe(movie),c,tmp_path/'without.mp4',render_options=RenderOptions(burn_subtitles=True))
    assert np.max(pixels(out,.44,tmp_path))<20
    assert c.captions['cues']==saved['cues'] and c.captions['style']==saved['style']


@pytest.mark.parametrize('codec,fmt',[('pcm_s32le','s32le'),('pcm_f32le','f32le')])
def test_high_precision_audio_is_not_quantized_to_24_bit(codec,fmt,tmp_path):
    source=tmp_path/'precision.mkv'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i','color=black:s=160x90:r=25:d=3',
         '-f','lavfi','-i','aevalsrc=0.123456789*sin(2*PI*440*t):s=48000:d=3',
         '-map','0:v','-map','1:a','-c:v','libx264','-c:a',codec,source])
    media=probe(source);c=clip(.4,2.4);c.captions=generate_track(c,[{'start':.8,'end':1.8,'text':'teste','words':[]}])
    output=export_clip(media,c,tmp_path/'precision.mp4')
    assert probe(output).audio[0]['codec']==codec
    def raw(path,target,start,duration):
        run([executable('ffmpeg'),'-v','error','-i',path,'-ss',start,'-t',duration,'-map','0:a:0','-c:a',codec,'-f',fmt,target])
        return target.read_bytes()
    assert raw(source,tmp_path/'source.raw',.4,1.8)==raw(output,tmp_path/'output.raw',0,1.8)


def test_caption_preview_cache_is_separate_from_whisper_and_sensitive_to_text(movie,tmp_path):
    from radar.caption_preview import preview_key
    media=probe(movie);c=clip();c.captions=generate_track(c,speech())
    key=preview_key(media,c,RenderOptions(),.44)
    c.captions=update_cue(c.captions,1,text='CEFAS GAMER TESTE',start=2.6,end=4.4)
    assert preview_key(media,c,RenderOptions(),.44)!=key
    assert preview_key(media,c,RenderOptions(),.4)!=preview_key(media,c,RenderOptions(),.44)


def test_mixed_audio_tracks_copy_aac_and_encode_pcm_losslessly(movie,tmp_path):
    source=tmp_path/'mixed.mkv'
    run([executable('ffmpeg'),'-v','error','-i',movie,'-map','0','-c:v','copy','-c:a:0','copy','-c:a:1','pcm_s16le',source])
    c=clip();c.captions=generate_track(c,speech())
    output=export_clip(probe(source),c,tmp_path/'mixed.mp4')
    assert [a['codec'] for a in probe(output).audio]==['aac','alac']
    def hashes(path):
        record=json.loads(run([executable('ffprobe'),'-v','error','-select_streams','a:0','-show_packets','-show_data_hash','sha256','-of','json',path]))
        return [p['data_hash'] for p in record['packets']]
    assert all(h in hashes(source) for h in hashes(output))


def test_missing_libass_keeps_sidecar_exports_available(movie,tmp_path,monkeypatch):
    from radar import render
    monkeypatch.setattr(render,'_has_subtitles',lambda *a:False)
    c=clip();c.captions=generate_track(c,speech())
    with pytest.raises(RuntimeError,match='libass'):export_clip(probe(movie),c,tmp_path/'missing.mp4')
    assert not (tmp_path/'missing.mp4').exists()
    assert export_ass(c,[],tmp_path/'portable.ass').is_file()
    assert export_srt(c,[],tmp_path/'portable.srt').is_file()


@pytest.fixture
def gui_cleanup(monkeypatch):
    yield
    monkeypatch.undo()
    import gc
    gc.collect()


@pytest.mark.skipif(os.name!='nt' and not os.environ.get('DISPLAY'),reason='Requer display X11')
def test_caption_editor_real_flow_text_style_presets_preview_exports_project(movie,tmp_path,monkeypatch,gui_cleanup):
    from radar.gui import App
    from radar import desktop_captions as desktop,gui
    from radar.settings import read_settings
    monkeypatch.chdir(tmp_path);app=App();errors=[]
    monkeypatch.setattr(app,'error',lambda exc:errors.append(str(exc)))
    monkeypatch.setattr(gui.messagebox,'showinfo',lambda *a,**kw:None)
    monkeypatch.setattr(gui.messagebox,'showwarning',lambda *a,**kw:None)
    def unexpected(*a,**kw):raise AssertionError('Whisper repetido ao editar uma transcrição existente')
    monkeypatch.setattr(desktop,'transcribe_cut',unexpected)
    def finish():
        deadline=time.monotonic()+30
        while app.busy and time.monotonic()<deadline:app.update();time.sleep(.02)
        app.update();assert not app.busy and not errors,errors
    files={kind:tmp_path/f'gui.{kind}' for kind in ('srt','ass','mp4','radar.json')}
    monkeypatch.setattr(gui.filedialog,'asksaveasfilename',lambda **kw:str(files[kw['defaultextension'].lstrip('.')]))
    try:
        app.loaded(probe(movie));app.cuts=[clip(),replace(clip(5.5,7.5),id=2)]
        app.speech=speech();app.refresh();app.table.selection_set('1');app.show_page('captions');app.update()
        assert app.caption_picker.current()==0
        app.geometry('1000x620');app.update()
        for widget in (app.caption_picker,app.caption_preview_canvas,app.caption_table,app.caption_tabs):
            assert widget.winfo_rootx()+widget.winfo_width()<=app.winfo_rootx()+app.winfo_width()
            assert widget.winfo_rooty()+widget.winfo_height()<=app.winfo_rooty()+app.winfo_height()
        app.caption_generate();finish()
        assert app.cuts[0].captions and app._caption_image.width()>0
        app.caption_tabs.select(1);app.update()
        style_page=app.caption_tabs.nametowidget(app.caption_tabs.tabs()[1])
        style_entry=next(w for row in style_page.content.winfo_children() for w in row.winfo_children() if isinstance(w,gui.ttk.Entry))
        style_entry.event_generate('<MouseWheel>',delta=-120);app.update()
        assert style_page.canvas.yview()[0]>0
        app.caption_tabs.select(0);app.update()
        assert app.caption_start.get()=='00:00:00.200'
        app.caption_text.delete('1.0','end');app.caption_text.insert('1.0','CEFAS GAMER TESTE')
        app.caption_start.set('0.240');app.caption_end.set('2.040')
        app.caption_apply_text();finish()
        cue=app.cuts[0].captions['cues'][0]
        assert cue['text']=='CEFAS GAMER TESTE' and cue['start']==pytest.approx(2.64)
        app.caption_effect.set(EFFECTS['karaoke']);app.caption_style_vars['size'].set('90')
        app.caption_apply_style(True);finish()
        assert style_for(app.cuts[0].captions).effect=='karaoke'
        app.caption_effect.set(EFFECTS['pop']);app.caption_apply_style();finish()
        assert style_for(app.cuts[0].captions,cue).effect=='karaoke'  # prior snapshot remains immutable
        assert style_for(app.cuts[0].captions,app.cuts[0].captions['cues'][0]).effect=='pop'
        monkeypatch.setattr(desktop.simpledialog,'askstring',lambda *a,**kw:'Cefas Azul')
        app.caption_save_preset()
        assert read_settings()['caption_presets']['Cefas Azul']['effect']=='pop'
        app.caption_cursor.set(.44);app.caption_request_preview();finish()
        assert 'GAMER' in app.caption_active.get() or 'CEFAS' in app.caption_active.get()
        # Save applies numeric times typed in the word dialog, including when
        # the user has not pressed its separate per-word Apply button.
        app.caption_words();app.update()
        dialog=next(w for w in app.winfo_children() if isinstance(w,gui.tk.Toplevel))
        def descendants(widget):
            for child in widget.winfo_children():yield child;yield from descendants(child)
        widgets=list(descendants(dialog));inputs=[w for w in widgets if isinstance(w,gui.ttk.Entry)]
        inputs[0].delete(0,'end');inputs[0].insert(0,'0.250')
        inputs[1].delete(0,'end');inputs[1].insert(0,'0.750')
        next(w for w in widgets if isinstance(w,gui.ttk.Button) and w.cget('text')=='Salvar sincronização').invoke()
        finish();assert app.cuts[0].captions['cues'][0]['words'][0]['start']==pytest.approx(2.65)
        app.caption_export('srt');app.caption_export('ass');app.caption_export('mp4');finish()
        assert 'CEFAS GAMER TESTE' in files['srt'].read_text(encoding='utf-8')
        assert r'\t(0,120,' in files['ass'].read_text(encoding='utf-8')
        assert len(probe(files['mp4']).audio)==2
        # Saving flushes unapplied text as well as style edits.
        app.caption_text.delete('1.0','end');app.caption_text.insert('1.0','CEFAS RADAR NOVO')
        app.save_studio_project();finish()
        app.open_studio_project(str(files['radar.json']));finish()
        assert app.cuts[0].captions['cues'][0]['text']=='CEFAS RADAR NOVO'
        assert app.speech==speech()
        app.show_page('captions');app.caption_enabled.set(False);app.caption_toggle();finish()
        assert not app.cuts[0].captions['enabled'] and app.cuts[0].captions['cues']
        app.caption_select_cut(2);assert app.table.selection()==('2',)
        app.caption_add();assert len(app.cuts[1].captions['cues'])==1
        app.caption_delete();finish();assert app.cuts[1].captions['cues']==[]
    finally:app.close()


@pytest.mark.skipif(os.name!='nt' and not os.environ.get('DISPLAY'),reason='Requer display X11')
def test_caption_editor_invalid_buffer_is_atomic_and_never_discarded_on_navigation(movie,tmp_path,monkeypatch,gui_cleanup):
    from radar.gui import App
    monkeypatch.chdir(tmp_path);app=App();errors=[]
    monkeypatch.setattr(app,'error',lambda exc:errors.append(str(exc)))
    try:
        app.loaded(probe(movie));c=clip();c.captions=generate_track(c,speech());app.cuts=[c]
        app.refresh();app.table.selection_set('1');app.show_page('captions');app.update()
        saved=deepcopy(c.captions)
        app.caption_text.delete('1.0','end');app.caption_text.insert('1.0','outra fala')
        app.caption_style_vars['size'].set('invalid')
        app.show_page('review')
        assert app.current_page=='captions' and errors and c.captions==saved
        assert app.caption_text.get('1.0','end-1c')=='outra fala'
        app.caption_style_vars['size'].set('72');app.show_page('review')
        assert app.current_page=='review' and c.captions['cues'][0]['text']=='outra fala'
        assert c.captions['cues'][0]['words']==[]
    finally:app.close()
