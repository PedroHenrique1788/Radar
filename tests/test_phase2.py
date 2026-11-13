"""Phase 2 outcomes: actual media alignment, independent resume and speech context."""
from dataclasses import replace
import csv
import json
import math
import os
from pathlib import Path
import time
import wave

import numpy as np
import pytest

from radar import pipeline
from radar.audio_source import probe_audio,extract_external
from radar.candidates import generate
from radar.checkpoints import CheckpointStore,StageError,latest_request
from radar.export import export_clip,export_report,export_transcript
from radar.intelligence import PhraseMatcher,SpeechIndex,speech_evidence
from radar.media import executable,probe,run
from radar.model import Media,Cut
from radar.profiles import AnalysisOptions,WEIGHTS
from radar.transcription import constrain_speech
from radar.transcription import transcribe
from types import SimpleNamespace


def wav(path,seconds=24,onset=6):
    rate=16000
    t=np.arange(seconds*rate)/rate
    x=np.sin(2*math.pi*440*t)*np.where((t>=onset)&(t<onset+2),.6,.001)
    with wave.open(str(path),'wb') as out:
        out.setparams((1,2,rate,0,'NONE','not compressed'))
        out.writeframes((x*32767).astype('<i2').tobytes())
    return path


def samples(path):
    with wave.open(str(path),'rb') as audio:
        assert audio.getnchannels()==1 and audio.getframerate()==16000
        return np.frombuffer(audio.readframes(audio.getnframes()),dtype='<i2').astype(float)/32768


@pytest.fixture(scope='module')
def recording(tmp_path_factory):
    root=tmp_path_factory.mktemp('phase2-media')
    video=root/'partida.mp4'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i',
         "color=black:s=160x90:r=25:d=24,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='gte(t,12)'",
         '-f','lavfi','-i','sine=frequency=880:sample_rate=16000:duration=24',
         '-f','lavfi','-i','sine=frequency=220:sample_rate=16000:duration=24',
         '-map','0:v','-map','1:a','-map','2:a','-c:v','libx264','-c:a','aac',
         '-metadata:s:a:0','title=Jogo','-metadata:s:a:1','title=Microfone',video])
    return video,wav(root/'microfone.wav')


@pytest.mark.parametrize('offset',[2.5,-2.5])
def test_external_audio_maps_sample_times_in_both_directions(recording,tmp_path,offset):
    source=probe_audio(recording[1]);out=tmp_path/'aligned.wav'
    extract_external(source,out,offset,start=0,duration=24)
    x=samples(out);onset=6+offset
    assert len(x)==24*16000
    before=x[int((onset-.4)*16000):int((onset-.1)*16000)]
    after=x[int((onset+.1)*16000):int((onset+.4)*16000)]
    assert np.sqrt(np.mean(after**2))>100*np.sqrt(np.mean(before**2))
    if offset>0:assert np.max(np.abs(x[:int(offset*16000)-10]))<1e-5
    else:assert np.max(np.abs(x[int((24+offset)*16000)+10:]))<1e-5


def test_later_batch_and_nonoverlapping_batch_keep_video_clock(recording,tmp_path):
    source=probe_audio(recording[1]);later=tmp_path/'later.wav';silence=tmp_path/'silence.wav'
    extract_external(source,later,2.5,start=8,duration=8)
    x=samples(later)
    assert np.sqrt(np.mean(x[:4000]**2))<.01
    assert np.sqrt(np.mean(x[16000:20000]**2))>.1
    extract_external(source,silence,30,start=0,duration=8)
    assert len(samples(silence))==8*16000 and not np.any(samples(silence))


def test_external_nonzero_pts_is_not_added_to_video_offset(tmp_path):
    path=tmp_path/'pts.mka'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=5',
         '-c:a','pcm_s16le','-output_ts_offset','5',path])
    source=probe_audio(path)
    assert source['origin']==pytest.approx(5,abs=.05) and source['duration']==pytest.approx(5,abs=.05)
    out=tmp_path/'aligned.wav';extract_external(source,out,2,start=0,duration=8)
    x=samples(out)
    assert np.max(np.abs(x[:30000]))<1e-5 and np.sqrt(np.mean(x[40000:45000]**2))>.01


def test_external_offset_invalidates_only_audio_dependent_stages(recording,tmp_path,monkeypatch):
    video,mic=recording
    opts=AnalysisOptions(external_audio=str(mic),external_offset=2.5,batch_seconds=16)
    first=pipeline.analyze(video,minimum=4,maximum=12,options=opts,cache_dir=tmp_path)
    before=latest_request(video,tmp_path)
    def unexpected(*a,**kw):raise AssertionError('Repetiu imagem independente do microfone')
    monkeypatch.setattr(pipeline,'visual_features',unexpected)
    second=pipeline.analyze(video,minimum=4,maximum=12,options=replace(opts,external_offset=-2.5),cache_dir=tmp_path)
    after=latest_request(video,tmp_path)
    assert before['stages']['visual']['key']==after['stages']['visual']['key']
    assert before['stages']['extract']['key']!=after['stages']['extract']['key']
    assert first[0].analysis_audio['offset']==2.5 and second[0].analysis_audio['offset']==-2.5
    assert first[0].analysis_audio['role']=='microphone'
    store=CheckpointStore(video,tmp_path)
    key=after['stages']['audio']['key']
    points=store.load('audio',key,0)
    assert max(points,key=lambda p:p['db'])['t'] in (4,5)
    # Export still carries both original video tracks, not the separate WAV.
    out=export_clip(second[0],Cut(1,2,7,50,'Teste','Teste'),tmp_path/'cut.mp4')
    assert len(probe(out).audio)==2
    report=json.loads(export_report(second[0],second[1],tmp_path/'report.json').read_text(encoding='utf-8'))
    assert report['analysis_audio']['source_id']==probe_audio(mic)['source_id']
    assert report['analysis_audio']['offset']==-2.5
    csv_path=export_report(second[0],second[1],tmp_path/'report.csv')
    with csv_path.open(encoding='utf-8-sig',newline='') as stream:
        rows=list(csv.DictReader(stream))
    assert rows and all(float(row['analysis_audio_offset'])==-2.5 and row['analysis_audio_role']=='microphone' for row in rows)


def test_external_recording_works_with_silent_video_and_reuses_finished_chunks(recording,tmp_path,monkeypatch):
    silent=tmp_path/'silent.mp4'
    run([executable('ffmpeg'),'-v','error','-i',recording[0],'-an','-c:v','copy',silent])
    opts=AnalysisOptions(external_audio=str(recording[1]),external_offset=1,batch_seconds=16,visual=False)
    media,cuts,_,_=pipeline.analyze(silent,minimum=4,maximum=12,options=opts,cache_dir=tmp_path/'cache')
    assert not media.audio and cuts
    def unexpected(*a,**kw):raise AssertionError('Repetiu lote confirmado')
    monkeypatch.setattr(pipeline,'extract_external',unexpected)
    monkeypatch.setattr(pipeline,'sound_features',unexpected)
    resumed=pipeline.analyze(silent,minimum=4,maximum=12,options=opts,cache_dir=tmp_path/'cache')
    assert [(c.start,c.end) for c in resumed[1]]==[(c.start,c.end) for c in cuts]


def test_external_input_mutation_is_detected_during_processing(recording,tmp_path,monkeypatch):
    mic=tmp_path/'copy.wav';mic.write_bytes(recording[1].read_bytes())
    actual=pipeline.sound_features
    def changed(*a,**kw):
        result=actual(*a,**kw)
        with mic.open('ab') as out:out.write(b'changed')
        return result
    monkeypatch.setattr(pipeline,'sound_features',changed)
    with pytest.raises(StageError,match='áudio externo mudou'):
        pipeline.analyze(recording[0],minimum=4,maximum=12,options=AnalysisOptions(external_audio=str(mic)),cache_dir=tmp_path/'cache')


@pytest.mark.parametrize('offset',[24,-24,100])
def test_external_audio_without_video_overlap_is_rejected(recording,tmp_path,offset):
    with pytest.raises(StageError,match='não se sobrepõe'):
        pipeline.analyze(recording[0],options=AnalysisOptions(external_audio=str(recording[1]),external_offset=offset),cache_dir=tmp_path)


def test_external_file_without_audio_does_not_silently_use_game_audio(tmp_path):
    video=tmp_path/'no-audio.mp4'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i','color=black:s=32x18:d=1','-c:v','libx264',video])
    with pytest.raises(ValueError,match='não contém uma faixa de áudio'):probe_audio(video)


def only(key):return {name:100. if name==key else 0. for name in WEIGHTS}


def media():return Media('synthetic.mp4',180,160,90,25,'h264',0,[],0)


def test_channel_phrases_match_accents_and_whole_words_without_regex_execution():
    matcher=PhraseMatcher('É AGORA;quase morri;a+b;olha isso')
    assert matcher.matches('É agora! OLHA ISSO, quase morri.')==['e agora','olha isso','quase morri']
    assert not matcher.matches('Reagora olhar issomente')
    assert not PhraseMatcher('').matches('Olha isso!')
    speech=[{'start':40,'end':44,'text':'A batalha azul terminou','words':[]}]
    opts=AnalysisOptions(phrases='batalha azul',weights=only('gancho_fala'))
    cuts=generate(media(),[],[],speech,minimum=5,maximum=20,options=opts)
    assert cuts and cuts[0].score>50 and 'batalha azul' in cuts[0].reason
    assert not generate(media(),[],[],speech,minimum=5,maximum=20,options=replace(opts,phrases=''))


def test_changing_phrases_reranks_without_decoding_or_transcribing_again(recording,tmp_path,monkeypatch):
    def speech(items,model,cancel,progress,**kw):
        for item in items:
            rows=[{'start':6,'end':8,'text':'A batalha azul terminou','words':[]}] if item['index']==0 else []
            kw['checkpoint'](item['index'],rows)
    monkeypatch.setattr(pipeline,'transcribe',speech)
    opts=AnalysisOptions(audio=False,visual=False,phrases='batalha azul',weights=only('gancho_fala'),batch_seconds=16)
    first=pipeline.analyze(recording[0],minimum=4,maximum=12,model='tiny',options=opts,cache_dir=tmp_path)
    assert first[1] and first[2]
    def unexpected(*a,**kw):raise AssertionError('Repetiu mídia ou transcrição ao mudar expressões')
    monkeypatch.setattr(pipeline,'transcribe',unexpected);monkeypatch.setattr(pipeline,'extract_audio',unexpected)
    second=pipeline.analyze(recording[0],minimum=4,maximum=12,model='tiny',options=replace(opts,phrases='outra expressão'),cache_dir=tmp_path)
    assert second[2]==first[2] and not second[1]


def test_vocal_cue_has_lower_confidence_for_mixed_game_audio():
    sound=[{'t':i,'db':-10 if 40<=i<43 else -40,'dynamic_db':12} for i in range(180)]
    speech=[{'start':40,'end':43,'text':'aqui uma fala durante o jogo','words':[]}]
    mic=speech_evidence(sound,speech,'microphone','')
    mixed=speech_evidence(sound,speech,'mixed','')
    assert mic[0]['vocal']>mixed[0]['vocal']*2
    assert not speech_evidence(sound,[],'mixed','')
    # No ASR and no declared microphone: game noise alone cannot earn vocal points.
    cuts=generate(media(),sound,[],[],minimum=5,maximum=15)
    assert cuts and all(c.components['reação_vocal']==0 for c in cuts)


def test_rhythm_needs_timed_words_and_pause_is_reported_as_a_cue():
    def segment(start,spacing,n,text):
        return {'start':start,'end':start+spacing*n,'text':text,'words':[
            {'start':start+i*spacing,'end':start+(i+.8)*spacing,'word':'palavra'} for i in range(n)]}
    speech=[segment(10,.5,8,'Fala normal.'),segment(50,.5,8,'Mais uma frase normal.'),
            segment(54.8,.2,10,'Não acredito!')]
    evidence=speech_evidence([],speech,'microphone','não acredito')
    assert evidence[0]['rhythm']==pytest.approx(0,abs=1e-9) and evidence[-1]['rhythm']>.5
    assert evidence[-1]['pause']==pytest.approx(.8)
    cuts=generate(media(),[],[],speech,minimum=5,maximum=20,options=AnalysisOptions(weights=only('ritmo_fala')))
    assert cuts and 'palavras/segundo' in cuts[0].reason and 'pausa antes' in cuts[0].reason
    untimed=[{**s,'words':[]} for s in speech]
    assert all(e['rate'] is None and not e['rhythm'] for e in speech_evidence([],untimed,'microphone',''))


def test_setup_and_payoff_preserve_sequence_and_consolidate_close_suggestions():
    speech=[{'start':20,'end':24,'text':'Vou tentar passar por esta parte difícil.','words':[]},
            {'start':30,'end':33,'text':'Não acredito que consegui!','words':[]},
            {'start':34,'end':37,'text':'Finalmente deu certo!','words':[]}]
    cuts=generate(media(),[],[],speech,minimum=10,maximum=45)
    assert len(cuts)==1
    assert cuts[0].start<=20 and cuts[0].end>=37
    assert cuts[0].components['continuidade']>0 and 'preparação e desfecho' in cuts[0].reason
    assert 'Vou tentar' in cuts[0].transcript and 'Finalmente' in cuts[0].transcript


def test_candidate_limits_keep_words_whole_including_mixed_timing_availability():
    speech=[{'start':34,'end':46,'text':'Olha isso agora finalmente consegui','words':[
        {'start':34,'end':36,'word':'Olha isso'}, {'start':40,'end':42,'word':'agora'},
        {'start':44,'end':46,'word':'finalmente consegui'}]},
        {'start':63,'end':67,'text':'Uma frase final inteira.','words':[]}]
    cuts=generate(media(),[],[],speech,minimum=10,maximum=45)
    assert cuts
    index=SpeechIndex(speech)
    assert all(not index.crossings(c.start,c.end) for c in cuts)
    assert all(10<=c.duration<=45 for c in cuts)


def test_overlong_untimed_sentence_is_not_claimed_as_complete():
    speech=[{'start':0,'end':100,'text':'Não acredito que consegui atravessar esta fase.','words':[]}]
    assert not generate(media(),[],[],speech,minimum=5,maximum=20)


def test_final_actual_frame_alignment_preserves_words_and_refreshes_transcript(recording,tmp_path,monkeypatch):
    speech=[{'start':4.999,'end':10.02,'text':'antes e fim','words':[
        {'start':4.999,'end':5.009,'word':'antes'}, {'start':7.,'end':8.,'word':'e'},
        {'start':9.999,'end':10.02,'word':'fim'}]}]
    def transcribe(items,model,cancel,progress,**kw):
        for item in items:kw['checkpoint'](item['index'],speech)
    monkeypatch.setattr(pipeline,'transcribe',transcribe)
    # Both proposed boundaries are outside words, but nearest 25fps PTS enter
    # the first/last words. The final pass must move to real PTS outside them.
    monkeypatch.setattr(pipeline,'generate',lambda *a,**kw:[Cut(1,5.011,10.03,50,'Teste','Teste','texto antigo')])
    result=pipeline.analyze(recording[0],minimum=1,maximum=12,model='tiny',cache_dir=tmp_path)
    cut=result[1][0]
    assert not SpeechIndex(speech).crossings(cut.start,cut.end)
    assert cut.transcript=='antes e fim'
    text=export_transcript(cut,result[2],tmp_path/'text.txt').read_text(encoding='utf-8')
    assert 'antes e fim' in text


def test_asr_estimates_cannot_place_words_outside_external_audio_coverage():
    speech=[{'start':2.1,'end':7.,'text':'antes palavra depois','words':[
        {'start':2.1,'end':2.3,'word':'antes'},{'start':2.4,'end':6.7,'word':'palavra'},
        {'start':6.8,'end':7.,'word':'depois'}]}]
    result=constrain_speech(speech,2.5,6.5)
    assert result[0]['start']==2.5 and result[0]['end']==6.5
    assert result[0]['text']=='palavra' and result[0]['words'][0]['start']==2.5
    assert result[0]['words'][0]['end']==6.5
    assert speech[0]['start']==2.1  # Cached/source objects are not mutated.


def test_asr_decodes_real_coverage_without_padding_and_restores_video_offset(recording,tmp_path):
    aligned=tmp_path/'aligned.wav'
    extract_external(probe_audio(recording[1]),aligned,2.5,start=0,duration=28)
    inspected=[]
    class Model:
        def __init__(self,*a,**kw):assert kw['device']=='cpu' and kw['compute_type']=='int8'
        def transcribe(self,path,**kw):
            x=samples(path);inspected.append(len(x))
            assert len(x)==24*16000 and np.max(np.abs(x[:1000]))>0  # No artificial prefix.
            assert np.sqrt(np.mean(x[6*16000:7*16000]**2))>.1
            word=SimpleNamespace(start=.2,end=.5,word=' teste')
            seg=SimpleNamespace(start=.2,end=.5,text='teste',words=[word],no_speech_prob=.1)
            return iter([seg]),None
    result=transcribe([{'index':0,'path':aligned,'clip_start':2.5,'duration':24,'start':2.5}],model_factory=Model)
    assert inspected==[24*16000] and result[0]['start']==pytest.approx(2.7)
    assert result[0]['words'][0]['end']==pytest.approx(3.)


def test_pipeline_does_not_transcribe_batches_outside_real_microphone_coverage(recording,tmp_path,monkeypatch):
    seen=[]
    def speech(items,model,cancel,progress,**kw):
        seen.extend(items)
        for item in items:
            kw['checkpoint'](item['index'],[{'start':item['start']+.2,'end':item['start']+1.,'text':'Consegui!','words':[]}])
    monkeypatch.setattr(pipeline,'transcribe',speech)
    opts=AnalysisOptions(external_audio=str(recording[1]),external_offset=20,batch_seconds=16,audio=False,visual=False)
    result=pipeline.analyze(recording[0],minimum=1,maximum=8,model='tiny',options=opts,cache_dir=tmp_path)
    assert len(seen)==1 and seen[0]['index']==1
    assert seen[0]['start']==20 and seen[0]['clip_start']==4 and seen[0]['duration']==4
    assert result[2] and result[2][0]['start']==pytest.approx(20.2)


def test_custom_phrases_are_validated_and_legacy_profile_weights_migrate():
    legacy={k:v for k,v in WEIGHTS.items() if k in ('gancho_fala','variação_sonora','atividade_visual','fala_completa')}
    record=AnalysisOptions().record();record['weights']=legacy
    loaded=AnalysisOptions.from_record(record)
    assert set(loaded.weights)==set(WEIGHTS) and loaded.weights['gancho_fala']==legacy['gancho_fala']
    for change in ({'phrases':'a'*81},{'external_offset':float('nan')},{'audio_role':'emotion'},{'phrases':'\n'.join(str(i) for i in range(101))}):
        with pytest.raises(ValueError):replace(loaded,**change).validate()


@pytest.fixture
def gui_cleanup(monkeypatch):
    yield
    monkeypatch.undo()
    import gc
    gc.collect()


@pytest.mark.skipif(os.name!='nt' and not os.environ.get('DISPLAY'),reason='Requer display X11')
def test_gui_external_audio_expressions_and_recent_job_restore(recording,tmp_path,monkeypatch,gui_cleanup):
    from radar.gui import App
    from radar.desktop_analysis import filedialog
    monkeypatch.chdir(tmp_path)
    app=App();errors=[]
    monkeypatch.setattr(app,'error',lambda exc:errors.append(str(exc)))
    monkeypatch.setattr(filedialog,'askopenfilename',lambda **kw:str(recording[1]))
    try:
        app.loaded(probe(recording[0]));app.choose_external_audio()
        app.option_vars['external_offset'].set('2,5')
        app.model.set('off');app.minimum.set('4');app.maximum.set('12')
        app.phrase_editor.delete('1.0','end');app.phrase_editor.insert('1.0','BATALHA AZUL\nconsegui')
        app.phrase_edited();app.update()
        assert app.options_from_ui().external_offset==2.5
        assert app.options_from_ui().phrases=='BATALHA AZUL\nconsegui'
        app.analyze()
        deadline=time.monotonic()+30
        while app.busy and time.monotonic()<deadline:app.update();time.sleep(.02)
        assert not app.busy and not errors and app.current_page=='review'
        assert app.media.analysis_audio['offset']==2.5
        app.loaded(probe(recording[0]))
        assert app.option_vars['external_audio'].get()==str(recording[1])
        assert app.options_from_ui().external_offset==2.5
        app.clear_external_audio()
        assert not app.options_from_ui().external_audio
    finally:
        app.close()
