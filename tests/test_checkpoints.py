"""Real small media, checkpoint recovery and CPU-only resource limits."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import threading
import time

import pytest

from radar import pipeline
from radar.checkpoints import CheckpointStore,StageError,latest_request,signature
from radar.control import ExecutionControl,ResourceLimitError
from radar.export import export_clips,export_clip,export_report
from radar.media import Cancelled,executable,probe,run
from radar.model import Cut
from radar.profiles import AnalysisOptions,ECONOMY
from radar.candidates import generate
from radar.model import Media


@pytest.fixture(scope='module')
def source(tmp_path_factory):
    path=tmp_path_factory.mktemp('checkpoint-media')/'gameplay.mp4'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i',
         "color=black:s=160x90:r=25:d=36,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='gte(t,18)'",
         '-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=36',
         '-f','lavfi','-i','sine=frequency=880:sample_rate=16000:duration=36',
         '-map','0:v','-map','1:a','-map','2:a','-c:v','libx264','-c:a','aac',
         '-metadata:s:a:0','title=Microfone','-metadata:s:a:1','title=Jogo',path])
    return path


def analyze(source,cache,**kw):
    return pipeline.analyze(source,minimum=5,maximum=15,model=kw.pop('model','off'),cache_dir=cache,
                            options=kw.pop('options',AnalysisOptions(batch_seconds=16)),**kw)


def test_failed_visual_batch_resumes_only_missing_work(source,tmp_path,monkeypatch):
    actual=pipeline.visual_features
    def fail(media,*args,**kw):
        if kw['start']==16:raise RuntimeError('Falha sintética no segundo lote')
        return actual(media,*args,**kw)
    monkeypatch.setattr(pipeline,'visual_features',fail)
    with pytest.raises(StageError) as error:analyze(source,tmp_path)
    assert error.value.stage=='visual'
    state=latest_request(source,tmp_path)
    assert state['stages']['extract']['status']=='complete'
    assert state['stages']['audio']['status']=='complete'
    assert state['stages']['visual']['done']==16 and state['status']=='failed'
    def unexpected(*a,**kw):raise AssertionError('Repetiu etapa concluída')
    monkeypatch.setattr(pipeline,'extract_audio',unexpected)
    monkeypatch.setattr(pipeline,'sound_features',unexpected)
    starts=[]
    def resumed(media,*a,**kw):starts.append(kw['start']);return actual(media,*a,**kw)
    monkeypatch.setattr(pipeline,'visual_features',resumed)
    media,cuts,_,_=analyze(source,tmp_path)
    assert starts==[16,32] and cuts and any(c.start<=18<=c.end for c in cuts)
    assert latest_request(source,tmp_path)['status']=='complete'
    assert media.source_id==CheckpointStore(source,tmp_path).source_id
    assert not list(tmp_path.rglob('*.tmp')) and not list(tmp_path.rglob('*.part.wav'))


def test_cancelled_visual_batch_keeps_completed_batch_across_new_control(source,tmp_path,monkeypatch):
    actual=pipeline.visual_features;cancel=threading.Event()
    def first(media,*args,**kw):
        data=actual(media,*args,**kw)
        if kw['start']==0:cancel.set()
        return data
    monkeypatch.setattr(pipeline,'visual_features',first)
    with pytest.raises(Cancelled):analyze(source,tmp_path,cancel=cancel)
    state=latest_request(source,tmp_path)
    assert state['status']=='cancelled' and state['stages']['visual']['done']==16
    calls=[]
    def resumed(media,*a,**kw):calls.append(kw['start']);return actual(media,*a,**kw)
    monkeypatch.setattr(pipeline,'visual_features',resumed)
    assert analyze(source,tmp_path)[1]
    assert calls==[16,32]


def test_changing_transcription_or_weights_reuses_independent_audio_and_visual(source,tmp_path,monkeypatch):
    analyze(source,tmp_path)
    def unexpected(*a,**kw):raise AssertionError('Módulo independente foi repetido')
    monkeypatch.setattr(pipeline,'extract_audio',unexpected)
    monkeypatch.setattr(pipeline,'sound_features',unexpected)
    monkeypatch.setattr(pipeline,'visual_features',unexpected)
    calls=[]
    def speech(items,model,cancel,progress,**kw):
        calls.append([item['index'] for item in items])
        for item in items:
            kw['checkpoint'](item['index'],[{'start':item['start']+.2,'end':item['start']+2,'text':'Olha isso!','words':[]}])
    monkeypatch.setattr(pipeline,'transcribe',speech)
    result=analyze(source,tmp_path,model='tiny')
    assert len(calls)==1 and result[2]
    changed=AnalysisOptions(batch_seconds=16,weights={'gancho_fala':40.,'variação_sonora':10.,'atividade_visual':20.,'fala_completa':30.})
    assert analyze(source,tmp_path,model='tiny',options=changed)[2]==result[2]
    assert len(calls)==1


def test_partial_optional_transcription_resumes_only_pending_chunks(source,tmp_path,monkeypatch):
    def partial(items,model,cancel,progress,**kw):
        item=items[0]
        kw['checkpoint'](item['index'],[{'start':.2,'end':2.,'text':'Olha isso!','words':[]}])
        raise RuntimeError('Falha opcional após um lote')
    monkeypatch.setattr(pipeline,'transcribe',partial)
    first=analyze(source,tmp_path,model='tiny')
    assert first[2] and 'Transcrição indisponível' in first[3][0]
    assert latest_request(source,tmp_path)['stages']['transcription']['status']=='failed'
    seen=[]
    def resumed(items,model,cancel,progress,**kw):
        seen.extend(item['index'] for item in items)
        for item in items:kw['checkpoint'](item['index'],[{'start':item['start']+.2,'end':item['start']+2.,'text':'Consegui!','words':[]}])
    monkeypatch.setattr(pipeline,'transcribe',resumed)
    def unexpected(*a,**kw):raise AssertionError('Módulo concluído foi repetido')
    monkeypatch.setattr(pipeline,'sound_features',unexpected);monkeypatch.setattr(pipeline,'visual_features',unexpected)
    second=analyze(source,tmp_path,model='tiny')
    assert seen==[1,2] and len(second[2])==3
    assert latest_request(source,tmp_path)['stages']['transcription']['status']=='complete'


def test_corrupt_feature_cache_recomputes_only_damaged_batch(source,tmp_path,monkeypatch):
    analyze(source,tmp_path)
    store=CheckpointStore(source,tmp_path)
    key=store.manifest['stages']['visual']['key']
    path=store.location('visual',key,1)
    record=json.loads(path.read_text(encoding='utf-8'))
    record['data']['values'][0]['change']=.999
    path.write_text(json.dumps(record),encoding='utf-8')
    actual=pipeline.visual_features;calls=[]
    def repaired(media,*a,**kw):calls.append(kw['start']);return actual(media,*a,**kw)
    monkeypatch.setattr(pipeline,'visual_features',repaired)
    analyze(source,tmp_path)
    assert calls==[16]


def test_original_mutation_invalidates_resume_and_blocks_export(source,tmp_path):
    original=tmp_path/'copy.mp4';original.write_bytes(source.read_bytes())
    media=analyze(original,tmp_path/'cache')[0]
    old_id=media.source_id
    with original.open('ab') as out:out.write(b'changed')
    assert latest_request(original,tmp_path/'cache') is None
    assert CheckpointStore(original,tmp_path/'cache').source_id!=old_id
    with pytest.raises(ValueError,match='original mudou'):
        export_clip(media,Cut(1,0,2,50,'Teste','Teste'),tmp_path/'bad.mp4')
    assert not (tmp_path/'bad.mp4').exists()


def test_job_lock_refuses_another_writer(source,tmp_path):
    first=CheckpointStore(source,tmp_path);second=CheckpointStore(source,tmp_path)
    first.acquire()
    try:
        with pytest.raises(RuntimeError,match='Outra instância'):second.acquire()
    finally:first.release()
    second.acquire();second.release()


def test_queue_cancel_resume_integrity_and_user_modified_clip(source,tmp_path,monkeypatch):
    import radar.export as export
    media=probe(source);cancel=threading.Event()
    cuts=[Cut(i+1,a,b,50,f'Corte {i+1}','Teste') for i,(a,b) in enumerate([(0,2),(16,20),(30,35)])]
    folder=tmp_path/'clips';cache=tmp_path/'cache'
    def progress(n,msg):
        if msg.startswith('1/3 clipes concluídos'):cancel.set()
    with pytest.raises(Cancelled):export_clips(media,cuts,folder,cancel,cache,progress)
    existing=list(folder.glob('*.mp4'))
    assert len(existing)==1
    preserved=existing[0].read_bytes()
    actual=export.export_clip;calls=[]
    def encoded(*a,**kw):calls.append(a[1].id);return actual(*a,**kw)
    monkeypatch.setattr(export,'export_clip',encoded)
    files=export_clips(media,cuts,folder,cache_dir=cache)
    assert calls==[2,3] and existing[0].read_bytes()==preserved
    assert [probe(path).duration for path in files]==pytest.approx([2,4,5],abs=.06)
    assert all(len(probe(path).audio)==2 for path in files)
    files[0].write_bytes(b'user edited')
    calls.clear()
    repaired=export_clips(media,cuts,folder,cache_dir=cache)
    assert calls==[1] and repaired[0]!=files[0] and files[0].read_bytes()==b'user edited'


def test_long_synthetic_video_batches_have_original_times(tmp_path):
    source=tmp_path/'long-synthetic.mp4'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i',
         "color=black:s=32x18:r=1/4:d=1800,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='gte(t,900)'",
         '-c:v','libx264',source])
    progress=[]
    media,cuts,_,_=pipeline.analyze(source,minimum=15,maximum=60,cache_dir=tmp_path/'cache',
        options=AnalysisOptions(sample_fps=.25),progress=lambda n,msg:progress.append((n,msg)))
    assert media.duration==pytest.approx(1800,abs=.1)
    assert any(c.start<=900<=c.end for c in cuts)
    assert all(n is None or 0<=n<=100 for n,_ in progress)
    state=latest_request(source,tmp_path/'cache')
    assert state['stages']['visual']['done']==1800 and state['stages']['extract']['status']=='skipped'
    report=json.loads(export_report(media,cuts,tmp_path/'report.json').read_text(encoding='utf-8'))
    assert report['source_id']==media.source_id and report['cuts'][0]['source_id']==media.source_id


def test_pause_suspends_owned_subprocess_and_cancellation_releases_it(tmp_path):
    control=ExecutionControl();errors=[]
    marker=tmp_path/'counter'
    code="import pathlib,sys,time\np=pathlib.Path(sys.argv[1])\nfor n in range(500):\n p.write_text(str(n));time.sleep(.02)"
    def worker():
        try:
            with control.bind():run([sys.executable,'-c',code,marker],control,timeout=2)
        except Exception as exc:errors.append(exc)
    task=threading.Thread(target=worker);task.start()
    deadline=time.monotonic()+5
    while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
    control.pause()
    while not control.snapshot()['paused'] and time.monotonic()<deadline:time.sleep(.02)
    try:
        assert control.snapshot()['paused']
        first=marker.read_text();time.sleep(.3)
        assert marker.read_text()==first
        control.resume();time.sleep(.15)
        assert marker.read_text()!=first
    finally:control.set();task.join(timeout=5)
    assert not task.is_alive() and len(errors)==1 and isinstance(errors[0],Cancelled)
    assert not control.processes


def test_memory_budget_stops_before_spawn_and_profile_stays_cpu_only(monkeypatch):
    control=ExecutionControl(AnalysisOptions(memory_mb=128))
    monkeypatch.setattr(control,'memory_bytes',lambda:129*1024**2)
    with pytest.raises(ResourceLimitError):control.checkpoint()
    assert not control.processes and control.options.max_processes==1
    assert control.options.profile==ECONOMY
    command=ExecutionControl(AnalysisOptions(threads=1)).command(['ffmpeg','-i','input.mp4','output.mp4'])
    assert command[command.index('-threads')+1]==1 and command[-1]=='output.mp4'


def test_weights_normalize_missing_signals_and_constant_loud_game_is_not_a_highlight():
    media=Media('synthetic.mp4',120,160,90,25,'h264',0,[],0)
    cuts=generate(media,[],[{'t':i,'change':1. if i==60 else 0.} for i in range(120)],[],minimum=10,maximum=30)
    assert cuts and cuts[0].score==100
    assert cuts[0].components['atividade_visual']==100 and cuts[0].components['variação_sonora']==0
    assert 'peso efetivo 100.0%' in cuts[0].reason
    loud=[{'t':i,'db':-8.,'rms':.4} for i in range(120)]
    steady=[{'t':i,'change':.2} for i in range(120)]
    assert not generate(media,loud,steady,[])


def test_report_refreshes_transcript_after_manual_boundary_edit(source,tmp_path):
    media=probe(source)
    cut=Cut(1,2,5,50,'Teste','Limites ajustados','Texto antigo fora do intervalo')
    speech=[{'start':1,'end':6,'text':'antes dentro depois','words':[
        {'start':1,'end':1.5,'word':'antes'},{'start':3,'end':4,'word':'dentro'},{'start':5.5,'end':6,'word':'depois'}]}]
    report=export_report(media,[cut],tmp_path/'updated.json',speech=speech)
    row=json.loads(report.read_text(encoding='utf-8'))['cuts'][0]
    assert row['transcript']=='dentro' and row['start_time']=='00:00:02.000'


def test_process_limit_serializes_owned_subprocesses(monkeypatch):
    control=ExecutionControl(AnalysisOptions(max_processes=1));counts=[];errors=[]
    actual=control.register
    def registered(process):
        actual(process)
        with control.lock:counts.append(len(control.processes))
    monkeypatch.setattr(control,'register',registered)
    def worker():
        try:
            with control.bind():run([sys.executable,'-c','import time;time.sleep(.2)'],control)
        except Exception as exc:errors.append(exc)
    tasks=[threading.Thread(target=worker) for _ in range(2)]
    for task in tasks:task.start()
    for task in tasks:task.join(timeout=5)
    assert not errors and counts==[1,1] and all(not task.is_alive() for task in tasks)


@pytest.mark.parametrize('change',[{'threads':0},{'max_processes':8},{'sample_fps':100},{'sample_fps':float('nan')},
                                   {'memory_mb':64},{'batch_seconds':0},{'visual_width':1920}])
def test_invalid_resource_profiles_are_rejected(change):
    with pytest.raises(ValueError):replace(AnalysisOptions(),**change).validate()
