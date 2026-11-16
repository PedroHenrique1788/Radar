"""Real media plus editorial safety rules; no claim of real-game validation."""
from copy import deepcopy
from dataclasses import asdict,replace
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import wave

import numpy as np
import pytest

from radar.audio_prepare import AudioTreatment,measurements,prepare_audio
from radar.checkpoints import signature
from radar.filmcraft import create_preedit_project
from radar.media import probe,run,executable,extract_audio,Cancelled
from radar.model import Media
from radar.preedit import PreEdit,PreEditOptions,Suggestion,detect,track_layout
from radar.preedit_pipeline import analyze_preedit
from radar.profiles import AnalysisOptions
from radar.projects import save_project,load_project


def synthetic(duration=120):
    m=Media('original.mkv',duration,160,90,25,'h264',0,[{'index':1,'title':'Microfone'},{'index':2,'title':'Jogo'},{'index':3,'title':'Mix'}],0,source_id='synthetic')
    sounds={k:[{'t':i,'db':-100.,'peak_db':-100.} for i in range(duration)] for k in (1,2,3)}
    visual=[{'t':i,'change':0.} for i in range(duration)]
    return m,track_layout(m),sounds,visual


def test_microphone_silence_preserves_two_minute_cutscene_with_game_sound():
    m,tracks,sounds,visual=synthetic()
    for k in (2,3):
        for p in sounds[k]:p['db']=-24.
    edit=detect(m,tracks,sounds,visual,[])
    assert edit.suggestions and all(s.classification=='keep' for s in edit.suggestions)
    assert edit.proposed_duration==120 and edit.kept()==[(0.,120)]
    assert not next(t for t in tracks if t['role']=='mix')['export']


def test_suggestions_never_remove_until_accepted_and_reject_undo_redo_restore_source():
    m,tracks,sounds,visual=synthetic();edit=detect(m,tracks,sounds,visual,[])
    s=edit.suggestions[0];assert s.classification=='remove' and edit.proposed_duration==120
    edit.edit(s.id,decision='rejected');assert edit.proposed_duration==120
    edit.edit(s.id,decision='accepted');assert edit.proposed_duration==pytest.approx(6.)
    assert edit.kept()==[(0.,3.),(117.,120)]
    assert edit.undo() and edit.proposed_duration==120
    assert edit.redo() and edit.proposed_duration==6
    edit.edit(s.id,decision='pending');assert edit.proposed_duration==120
    assert PreEdit.from_record(edit.record()).record()==edit.record()
    edit.undo();edit.edit(s.id,decision='rejected');assert not edit.redo()


@pytest.mark.parametrize('mode',['conservative','balanced','dynamic','mark'])
def test_presets_never_auto_cut_and_mark_cannot_accept_removal(mode):
    m,tracks,sounds,visual=synthetic();edit=detect(m,tracks,sounds,visual,[],PreEditOptions.preset(mode))
    assert edit.proposed_duration==120
    if mode=='mark':
        with pytest.raises(ValueError,match='marcar'):edit.edit(1,decision='accepted')
        assert edit.proposed_duration==120 and not edit.history


def test_no_audio_missing_game_visual_activity_and_unknown_evidence_require_review():
    m,tracks,sounds,visual=synthetic()
    cases=[([],{},visual),([tracks[0]],{1:sounds[1]},visual),(tracks,sounds,[]),
           (tracks,sounds,[{'t':i,'change':.05} for i in range(120)])]
    for t,a,v in cases:
        edit=detect(m,t,a,v,[])
        assert edit.suggestions and all(s.classification=='review' for s in edit.suggestions)
        assert edit.proposed_duration==120


def test_short_breaths_and_pause_followed_by_reaction_preserve_context():
    m,tracks,sounds,visual=synthetic(40)
    for k in sounds:
        for p in sounds[k]:p['db']=-20. if p['t']<10 or p['t']>=13 else -100.
    assert not detect(m,tracks,sounds,visual,[]).suggestions
    m,tracks,sounds,visual=synthetic(40)
    speech=[{'start':35.,'end':39.,'text':'Consegui!','words':[]}]
    edit=detect(m,tracks,sounds,visual,speech)
    assert all(s.end<=32 or s.classification=='keep' for s in edit.suggestions)


def test_adaptive_threshold_never_marks_constant_audible_game_as_silence():
    for db in (-44.,-30.,-12.):
        m,tracks,sounds,visual=synthetic()
        for k in (2,3):
            for p in sounds[k]:p['db']=db
        assert all(s.classification=='keep' for s in detect(m,tracks,sounds,visual,[]).suggestions)


def test_bound_changes_and_corrupt_history_are_validated_atomically():
    edit=PreEdit('id',100,suggestions=[Suggestion(1,5,20,'remove','pause',.7),Suggestion(2,40,60,'review','?',.3)])
    original=edit.record()
    with pytest.raises(ValueError):edit.edit(1,end=50)
    assert edit.record()==original
    edit.edit(1,start=6,end=19);edit.edit(1,decision='accepted');assert edit.proposed_duration==87
    assert edit.proposed_time(30)==17 and edit.proposed_time(10)==6
    row=edit.record();row['history'][0]['before']['end']=999
    with pytest.raises(ValueError):PreEdit.from_record(row)
    row=edit.record();row['suggestions'][0]['start']=float('nan')
    with pytest.raises(ValueError):PreEdit.from_record(row)


@pytest.fixture(scope='module')
def obs(tmp_path_factory):
    path=tmp_path_factory.mktemp('preedit')/'OBS multifaixa.mkv'
    run([executable('ffmpeg'),'-v','error','-copyts','-f','lavfi','-i','color=red:s=160x90:r=25:d=36',
         '-f','lavfi','-i','anullsrc=r=16000:cl=mono','-itsoffset','1','-f','lavfi','-i','sine=frequency=880:sample_rate=16000:duration=35',
         '-filter_complex',"[2:a]volume='if(between(t,4,30),0,1)':eval=frame[g]",
         '-map','0:v','-map','1:a','-map','[g]','-t','36','-c:v','libx264','-c:a','pcm_s16le',
         '-metadata:s:a:0','title=Microfone','-metadata:s:a:1','title=Jogo','-output_ts_offset','5',path])
    return path


def test_real_multitrack_nonzero_offsets_cache_cancel_resume_and_read_only_original(obs,tmp_path,monkeypatch):
    import radar.preedit_pipeline as pipeline
    m=probe(obs);original=hashlib.sha256(obs.read_bytes()).hexdigest();assert m.origin==5 and len(m.audio)==2
    opts=AnalysisOptions(batch_seconds=16);cache=tmp_path/'cache';cancel=threading.Event();actual=pipeline.visual_features
    def stop(*args,**kw):
        data=actual(*args,**kw)
        if kw['start']==0:cancel.set()
        return data
    monkeypatch.setattr(pipeline,'visual_features',stop)
    with pytest.raises(Cancelled):analyze_preedit(m,analysis=opts,cache_dir=cache,cancel=cancel)
    starts=[]
    def resumed(*a,**kw):starts.append(kw['start']);return actual(*a,**kw)
    monkeypatch.setattr(pipeline,'visual_features',resumed)
    def unexpected(*a,**kw):raise AssertionError('Repetiu áudio já confirmado')
    monkeypatch.setattr(pipeline,'extract_audio',unexpected);monkeypatch.setattr(pipeline,'sound_features',unexpected)
    edit=analyze_preedit(m,analysis=opts,cache_dir=cache)
    assert starts==[16.,32.] and edit.suggestions and edit.proposed_duration==m.duration
    monkeypatch.setattr(pipeline,'visual_features',unexpected)
    again=analyze_preedit(m,analysis=opts,options=PreEditOptions(mode='balanced'),cache_dir=cache)
    assert again.audio_analysis==edit.audio_analysis
    assert hashlib.sha256(obs.read_bytes()).hexdigest()==original
    assert not list(cache.rglob('*.part.wav'))


def test_project_v3_history_roundtrip_and_legacy_reads(obs,tmp_path,monkeypatch):
    m=probe(obs);edit=PreEdit(m.source_id,m.duration,track_layout(m),suggestions=[Suggestion(1,10,20,'remove','pause',.7)])
    edit.edit(1,decision='accepted');edit.edit(1,start=11,end=19);edit.undo()
    path=save_project(tmp_path/'pre.radar.json',m,[],[],preedit=edit)
    loaded=load_project(path)['preedit'];assert loaded.record()==edit.record();assert loaded.redo() and loaded.proposed_duration==28
    before=path.read_bytes()
    def fail(*a,**kw):raise OSError('falha de disco')
    monkeypatch.setattr(os,'replace',fail)
    with pytest.raises(OSError):save_project(path,m,[],[],preedit=edit,overwrite=True)
    assert path.read_bytes()==before
    monkeypatch.undo()
    for version in (1,2):
        row=json.loads(before);row['payload']['version']=version;row['payload'].pop('preedit');row['sha256']=signature(row['payload'])
        legacy=tmp_path/f'old{version}.radar.json';legacy.write_text(json.dumps(row),encoding='utf-8')
        assert load_project(legacy)['preedit'] is None


def test_otio_single_sequence_and_native_reopen_preserve_tracks_and_source_times(obs,tmp_path):
    import opentimelineio as otio
    m=probe(obs);edit=PreEdit(m.source_id,m.duration,track_layout(m),suggestions=[Suggestion(1,12,24,'remove','pause',.7,'accepted')])
    original=obs.read_bytes();fallback=create_preedit_project(m,edit,tmp_path,cli=False)
    timeline=otio.adapters.read_from_file(str(fallback));assert len(timeline.tracks)==3
    for track in timeline.tracks:
        assert len(track)==2 and track[1].source_range.start_time.to_seconds()==24
        assert track.duration().to_seconds()==24
    for p in fallback.parent.glob('*.wav'):
        with wave.open(str(p),'rb') as w:assert w.getnframes()/w.getframerate()==pytest.approx(m.duration,abs=.001)
    cli=os.environ.get('FILMCRAFT_CLI')
    if cli:
        native=create_preedit_project(m,edit,tmp_path,cli=cli);assert native.suffix=='.fcproj'
        inspection=json.loads((native.parent/'Inspecao_cli.json').read_text(encoding='utf-8'));assert len(inspection['video'][0]['items'])==2
        assert len([t for t in inspection['audio'] if t['items']])==2
        rendered=tmp_path/'editor.mp4';run([cli,'--project',native,'export',rendered,'--gpu-rendering','off'],timeout=120)
        assert probe(rendered).duration==pytest.approx(24,abs=.05)
        wav=tmp_path/'sync.wav';extract_audio(probe(rendered),wav)
        with wave.open(str(wav),'rb') as w:x=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)
        rms=lambda a,b:np.sqrt(np.mean(x[int(a*16000):int(b*16000)]**2))
        assert rms(.1,.6)<5 and rms(1.3,2)>100 and rms(6,8)<5 and rms(20,22)>100
    assert obs.read_bytes()==original and not list(fallback.parent.glob('*.mp4'))


def test_export_failure_keeps_previous_outputs_and_original(obs,tmp_path,monkeypatch):
    from radar import filmcraft
    m=probe(obs);edit=PreEdit(m.source_id,m.duration,track_layout(m))
    first=create_preedit_project(m,edit,tmp_path,cli=False);original=first.read_bytes()
    def fail(*a,**kw):raise RuntimeError('falha de extração')
    monkeypatch.setattr(filmcraft,'editor_audio',fail)
    with pytest.raises(RuntimeError):create_preedit_project(m,edit,tmp_path,cli=False)
    assert first.read_bytes()==original
    assert any(json.loads(p.read_text(encoding='utf-8'))['status']=='incomplete' for p in tmp_path.rglob('Estado.json'))


def test_audio_advice_and_real_optional_sidecar_do_not_change_source(obs,tmp_path):
    m=probe(obs);original=obs.read_bytes();data=measurements([{'db':-24.,'peak_db':-.05},{'db':-24.,'peak_db':-12.}])
    assert data['possible_clipped_seconds']==1 and data['suggested_gain_db']<0
    out=prepare_audio(m,m.audio[1]['index'],tmp_path/'processed.wav',AudioTreatment(gain_db=-6,compressor=True,gate=True,normalize=True))
    with wave.open(str(out),'rb') as w:assert w.getnframes()/w.getframerate()==pytest.approx(m.duration,abs=.001)
    assert out.with_suffix('.treatment.json').is_file() and obs.read_bytes()==original
    with pytest.raises(FileExistsError):prepare_audio(m,m.audio[1]['index'],out)
    with pytest.raises(ValueError):AudioTreatment(gain_db=float('inf')).filters()


@pytest.mark.skipif(os.name!='nt' and not os.environ.get('DISPLAY'),reason='Requer display')
def test_gui_analysis_decisions_undo_bounds_save_reopen_and_export(obs,tmp_path,monkeypatch):
    from radar.gui import App
    from radar.preedit_ui import filedialog,messagebox
    monkeypatch.chdir(tmp_path);app=App();errors=[]
    monkeypatch.setattr(app,'error',lambda e:errors.append(str(e)))
    monkeypatch.setattr(messagebox,'showinfo',lambda *a,**kw:None)
    monkeypatch.setattr(messagebox,'askyesno',lambda *a,**kw:True)
    def finish():
        deadline=time.monotonic()+90
        while app.busy and time.monotonic()<deadline:app.update();time.sleep(.01)
        app.update();assert not app.busy and not errors,errors
    try:
        app.loaded(probe(obs));app.open_preedit();view=app._preedit_window;view.analyze();finish()
        assert app.preedit and view.table.get_children()
        s=next(s for s in app.preedit.suggestions if s.classification=='remove');view.select(s.id)
        view.decide('accepted');assert app.preedit.proposed_duration<app.media.duration
        view.travel(False);assert app.preedit.proposed_duration==app.media.duration
        view.travel(True);view.decide('rejected');assert app.preedit.proposed_duration==app.media.duration
        view.start.set('00:00:12.000');view.end.set('00:00:20.000');view.bounds();finish()
        view.decide('accepted');assert app.preedit.proposed_duration==pytest.approx(28.)
        view.original.set(False);view.refresh();assert view.timeline.duration==28
        project=tmp_path/'gui.radar.json';monkeypatch.setattr(filedialog,'asksaveasfilename',lambda **kw:str(project))
        view.save();finish();app.open_studio_project(str(project));finish()
        assert app.preedit.proposed_duration==28 and app.preedit.history
        app.open_preedit();view=app._preedit_window
        monkeypatch.setattr(filedialog,'askdirectory',lambda **kw:str(tmp_path/'editor'))
        app.cli=os.environ.get('FILMCRAFT_CLI');view.export();finish()
        assert view.output.is_file()
    finally:
        app.close();monkeypatch.undo()
        import gc;gc.collect()


@pytest.mark.parametrize('vfr',[False,True])
def test_real_video_without_audio_keeps_all_time_and_otio_is_editable(tmp_path,vfr):
    path=tmp_path/'silent.mkv'
    args=[executable('ffmpeg'),'-v','error','-f','lavfi','-i','color=black:s=160x90:r=25:d=20']
    if vfr:args+=['-vf',"select='if(lt(t,10),not(mod(n,2)),1)'",'-fps_mode','vfr']
    run(args+['-c:v','libx264',path])
    m=probe(path);before=path.read_bytes();edit=analyze_preedit(m,analysis=AnalysisOptions(batch_seconds=16),cache_dir=tmp_path/'cache')
    assert edit.suggestions and all(s.classification=='review' for s in edit.suggestions)
    assert edit.proposed_duration==m.duration and not edit.tracks
    result=create_preedit_project(m,edit,tmp_path/'editor',cli=False)
    import opentimelineio as otio
    timeline=otio.adapters.read_from_file(str(result));assert len(timeline.tracks)==1
    assert timeline.duration().to_seconds()==pytest.approx(m.duration)
    assert path.read_bytes()==before


def test_failed_or_cancelled_audio_treatment_preserves_existing_files(obs,tmp_path):
    m=probe(obs);out=tmp_path/'keep.wav';out.write_bytes(b'existing user audio')
    with pytest.raises(FileExistsError):prepare_audio(m,m.audio[0]['index'],out)
    cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled):prepare_audio(m,m.audio[0]['index'],tmp_path/'cancel.wav',cancel=cancel)
    assert out.read_bytes()==b'existing user audio' and not (tmp_path/'cancel.wav').exists()


def test_disabled_audio_never_decodes_tracks_or_suggests_removal(obs,tmp_path,monkeypatch):
    import radar.preedit_pipeline as pipeline
    def unexpected(*a,**kw):raise AssertionError('Decodificou áudio desativado')
    monkeypatch.setattr(pipeline,'extract_audio',unexpected)
    edit=analyze_preedit(probe(obs),analysis=AnalysisOptions(audio=False),cache_dir=tmp_path/'cache')
    assert edit.proposed_duration==edit.duration and not any(s.classification=='remove' for s in edit.suggestions)


def test_important_marker_protects_context_without_inventing_game_event():
    m,tracks,sounds,visual=synthetic()
    edit=detect(m,tracks,sounds,visual,[],markers=[{'time':60.,'kind':'important','label':'Meu momento'}])
    assert all(s.end<=57 or s.start>=64 or s.classification=='keep' for s in edit.suggestions)


def test_relocation_keeps_preedit_source_and_tampered_source_is_rejected(obs,tmp_path):
    import shutil
    m=probe(obs);edit=PreEdit(m.source_id,m.duration,track_layout(m))
    path=save_project(tmp_path/'pre.radar.json',m,[],[],preedit=edit)
    moved=tmp_path/'relocated.mkv';shutil.copy2(obs,moved)
    loaded=load_project(path,source_override=moved)
    assert loaded['preedit'].source_id==loaded['media'].source_id and loaded['preedit'].source_id!=edit.source_id
    row=json.loads(path.read_text(encoding='utf-8'));row['payload']['preedit']['source_id']='wrong';row['sha256']=signature(row['payload'])
    path.write_text(json.dumps(row),encoding='utf-8')
    with pytest.raises(ValueError,match='fonte'):load_project(path)



def test_rf64_sidecars_validate_without_loading_whole_audio(tmp_path):
    from radar.filmcraft import verify_editor_audio
    path=tmp_path/'rf64.wav'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i','sine=frequency=880:duration=1',
         '-ar','48000','-ac','2','-c:a','pcm_s16le','-rf64','always',path])
    assert path.read_bytes()[:4]==b'RF64'
    verify_editor_audio(path,1.)
    with pytest.raises(RuntimeError):verify_editor_audio(path,2.)
