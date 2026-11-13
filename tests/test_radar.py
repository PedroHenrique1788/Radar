import csv
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace
import wave
import numpy as np
import pytest
from radar.model import Cut, timestamp, parse_time
from radar.media import probe, run, executable, extract_audio, align_bounds, Cancelled
from radar.export import export_clip, export_report, export_srt
from radar.pipeline import analyze
from radar.candidates import generate
from radar.signals import sound_features
from radar.transcription import transcribe
from radar.filmcraft import export_otio, create_projects, capabilities


@pytest.fixture(scope='session')
def movie(tmp_path_factory):
    root = tmp_path_factory.mktemp('media')
    p = root / 'OBS teste.mp4'
    # 36 s: quiet intro, bright scene + loud reaction at 18s, two separate OBS-like tracks.
    run([executable('ffmpeg'), '-v', 'error', '-y', '-f', 'lavfi', '-i',
         "color=c=black:s=160x90:r=25:d=36,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='gte(t,18)'",
         '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000:duration=36',
         '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=16000:duration=36',
         '-filter_complex', "[1:a]volume='if(between(t,18,21),1,0.01)':eval=frame[a]",
         '-map', '0:v', '-map', '[a]', '-map', '2:a', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac',
         '-metadata:s:a:0', 'title=Microfone', '-metadata:s:a:1', 'title=Jogo', p])
    return p


def cut(start=16., end=32.):
    return Cut(1, start, end, 60, 'Título', 'Mudança audiovisual medida')


@pytest.mark.parametrize('value,formatted', [(0,'00:00:00.000'), (1122.35,'00:18:42.350'),
    (3599.9996,'01:00:00.000'), (360000.001,'100:00:00.001')])
def test_timestamps(value, formatted):
    assert timestamp(value) == formatted
    assert abs(parse_time(formatted) - value) <= .0005


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf')])
def test_bad_times(value):
    with pytest.raises(ValueError): timestamp(value)


def test_probe_and_track_selection(movie, tmp_path):
    m = probe(movie)
    assert m.duration == pytest.approx(36, abs=.05)
    assert (m.width, m.height, m.fps) == (160, 90, 25)
    assert len(m.audio) == 2
    first, second, mixed = (tmp_path / name for name in ('one.wav', 'two.wav', 'mix.wav'))
    extract_audio(m, first, m.audio[0]['index'])
    extract_audio(m, second, m.audio[1]['index'])
    extract_audio(m, mixed)
    a, b = sound_features(first), sound_features(second)
    assert a[19]['db'] - a[5]['db'] > 25
    assert abs(b[19]['db'] - b[5]['db']) < 2
    with wave.open(str(mixed)) as w:
        assert w.getnframes() / w.getframerate() == pytest.approx(36, abs=.05)
    with pytest.raises(ValueError): extract_audio(m, tmp_path/'bad.wav', 999)


def test_export_exact_original_intervals(movie, tmp_path):
    m = probe(movie)
    c = cut(17.12, 20.68)
    out = export_clip(m, c, tmp_path / 'clip.mp4')
    result = probe(out)
    assert result.duration == pytest.approx(c.duration, abs=1/m.fps)
    assert len(result.audio) == 2
    # Compare decoded center pixels: original scene cut at 18 s must now be at 0.88 s.
    for t, expected in [(.4, 0), (1.4, 255)]:
        raw = tmp_path/f'{t}.gray'
        run([executable('ffmpeg'), '-v', 'error', '-ss', t, '-i', out, '-frames:v', 1,
             '-vf', 'scale=1:1', '-pix_fmt', 'gray', '-f', 'rawvideo', raw])
        assert abs(raw.read_bytes()[0] - expected) < 10
    audio = tmp_path/'export.wav'
    extract_audio(result, audio, result.audio[0]['index'])
    with wave.open(str(audio)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(float)
    before = np.sqrt(np.mean(x[int(.2*16000):int(.5*16000)]**2))
    after = np.sqrt(np.mean(x[int(1.2*16000):int(1.5*16000)]**2))
    assert after > 20 * before  # audio reaction aligned to scene in exported clip
    with pytest.raises(ValueError): export_clip(m,c,movie)
    with pytest.raises(FileExistsError): export_clip(m,c,out)


def test_reports_and_srt(movie, tmp_path):
    m, c = probe(movie), cut()
    p = export_report(m,[c],tmp_path/'r.json')
    row = json.loads(p.read_text(encoding='utf-8'))['cuts'][0]
    assert row['start_time']=='00:00:16.000' and row['end_time']=='00:00:32.000'
    assert row['duration']==16
    p = export_report(m,[c],tmp_path/'r.csv')
    with p.open(encoding='utf-8-sig') as f:
        assert next(csv.DictReader(f))['duration']=='16.0'
    speech=[{'start':15, 'end':18,'text':'antes dentro','words':[
        {'start':15,'end':15.5,'word':' antes'}, {'start':17,'end':18,'word':' dentro'}]}]
    srt=export_srt(c,speech,tmp_path/'r.srt').read_text(encoding='utf-8')
    assert '00:00:00,000 --> 00:00:02,000' in srt
    assert 'dentro' in srt and 'antes' not in srt
    with pytest.raises(ValueError): export_srt(c,[],tmp_path/'empty.srt')


def test_pipeline_entire_movie_and_no_speech(movie,tmp_path):
    m,cuts,speech,warnings=analyze(movie,track=1,model='off',minimum=8,maximum=16,cache_dir=tmp_path)
    assert cuts and not speech
    assert any(c.start <= 18 <= c.end for c in cuts)
    assert all(8 <= c.duration <= 16 for c in cuts)
    assert warnings
    assert all(c.components and c.reason for c in cuts)


def test_silence_and_static_not_forced(movie):
    m=probe(movie)
    assert not generate(m,[{'t':i,'db':-120,'rms':0} for i in range(36)],
                        [{'t':i,'change':0} for i in range(36)],[])


def test_transcription_failure_fallback(movie,tmp_path,monkeypatch):
    import radar.pipeline as p
    def fail(*args,**kwargs): raise RuntimeError('model failed')
    monkeypatch.setattr(p,'transcribe',fail)
    m,cuts,speech,warnings=p.analyze(movie,track=1,model='tiny',minimum=8,maximum=16,cache_dir=tmp_path)
    assert not speech and cuts and 'Transcrição indisponível' in warnings[0]
    from radar.checkpoints import latest_request
    state=latest_request(movie,tmp_path)
    assert state['stages']['transcription']['status']=='failed'
    assert state['stages']['visual']['status']=='complete' and state['stages']['audio']['status']=='complete'
    assert not list(tmp_path.glob('radar-*'))


def test_word_offsets_over_chunk_boundary(tmp_path):
    p=tmp_path/'long.wav'
    with wave.open(str(p),'wb') as w:
        w.setparams((1,2,16000,0,'NONE','not compressed'))
        w.writeframes(bytes(301*16000*2))
    class Fake:
        def __init__(self,*a,**kw): pass
        def transcribe(self,*a,**kw):
            word=SimpleNamespace(start=.1,end=.4,word=' Olá')
            seg=SimpleNamespace(start=.1,end=.4,text='Olá',words=[word],no_speech_prob=.1)
            return iter([seg]), None
    speech=transcribe(p,model_factory=Fake)
    assert speech[1]['start']==pytest.approx(300.1)
    assert speech[1]['words'][0]['end']==pytest.approx(300.4)
    assert not (tmp_path/'speech-chunk.wav').exists()


def test_no_audio_invalid_file_and_cancel(tmp_path):
    path=tmp_path/'silent.mp4'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i','color=black:s=160x90:d=2','-c:v','libx264',path])
    m,cuts,speech,w=analyze(path,minimum=1,maximum=2,cache_dir=tmp_path)
    assert not m.audio and not cuts and not speech
    bad=tmp_path/'bad.mp4'; bad.write_text('not media')
    with pytest.raises(RuntimeError): probe(bad)
    cancel=threading.Event(); cancel.set()
    with pytest.raises(Cancelled): analyze(path,minimum=1,maximum=2,cache_dir=tmp_path/'cancel',cancel=cancel)


def test_nonzero_origin_delayed_audio(tmp_path):
    path=tmp_path/'offset.mkv'
    run([executable('ffmpeg'),'-v','error','-copyts','-f','lavfi','-i','color=red:s=160x90:r=25:d=6',
         '-itsoffset','1','-f','lavfi','-i','sine=frequency=440:duration=5',
         '-map','0:v','-map','1:a','-c:v','libx264','-c:a','pcm_s16le','-output_ts_offset','5',path])
    m=probe(path)
    assert m.origin==pytest.approx(5,abs=.05)
    assert m.duration==pytest.approx(6,abs=.05)
    audio=tmp_path/'offset.wav'; extract_audio(m,audio)
    with wave.open(str(audio)) as w:
        x=np.frombuffer(w.readframes(32000),dtype='<i2').astype(float)
    assert np.max(np.abs(x[:12000])) < 5
    assert np.sqrt(np.mean(x[20000:30000]**2)) > 100
    c=cut(.4,3.2)
    out=export_clip(m,c,tmp_path/'offset-cut.mp4')
    assert probe(out).duration==pytest.approx(2.8,abs=.05)


def test_actual_frame_alignment(movie):
    m=probe(movie)
    start,end=align_bounds(m,17.133,20.691)
    assert start==pytest.approx(17.12)
    assert end==pytest.approx(20.68)


def test_otio_three_intervals(movie,tmp_path):
    import opentimelineio as otio
    m=probe(movie)
    cuts=[Cut(i+1,a,b,50,f'Short {i+1}','teste') for i,(a,b) in enumerate([(1.12,4.28),(17.12,20.68),(25.2,33.6)])]
    p=export_otio(m,cuts,tmp_path/'three.otio')
    tl=otio.adapters.read_from_file(str(p))
    assert len(tl.tracks)==3
    for track in tl.tracks:
        assert len(track)==3
        for clip,c in zip(track,cuts):
            assert clip.source_range.start_time.to_seconds()==pytest.approx(c.start)
            assert clip.source_range.duration.to_seconds()==pytest.approx(c.duration)
            assert clip.media_reference.target_url==movie.as_uri() if track.kind == 'Video' else clip.media_reference.target_url.endswith('.wav')


def test_filmcraft_native_reopen_three_sequences(movie,tmp_path):
    cli=os.environ.get('FILMCRAFT_CLI')
    if not cli: pytest.skip('FILMCRAFT_CLI não configurada')
    m=probe(movie)
    cuts=[Cut(i+1,a,b,50,f'Short {i+1}','teste') for i,(a,b) in enumerate([(1.12,4.28),(17.12,20.68),(25.2,33.6)])]
    assert capabilities(cli)['import_schema']['id']=='file.import'
    native=create_projects(m,cuts,tmp_path/'projects',cli=cli)[0]
    info=json.loads(run([cli,'--project',native,'inspect','project']))
    (tmp_path/'inspect.json').write_text(json.dumps(info,indent=2))
    assert native.suffix=='.fcproj' and native.stat().st_size>100
    # Actual sequence content assertions use serialized native project, not a mocked API.
    text=native.read_text(encoding='utf-8')
    assert all(c.title in text for c in cuts)
    project=json.loads(text)
    (tmp_path/'native-copy.json').write_text(json.dumps(project,indent=2))

    sequences = [item['kind']['Sequence'] for item in project['project']['items'].values() if 'Sequence' in item['kind']]
    assert len(sequences) == 3
    ticks = 254016000000
    for sequence, c in zip(sequences, cuts):
        assert sequence['settings']['width'] == m.width
        assert sequence['settings']['height'] == m.height
        assert len(sequence['video_tracks']) == 1
        assert len(sequence['audio_tracks']) == 2
        for track in sequence['video_tracks'] + sequence['audio_tracks']:
            assert len(track['items']) == 1
            clip = track['items'][0]
            assert clip['source_in'] / ticks == pytest.approx(c.start, abs=.000001)
            assert clip['duration'] / ticks == pytest.approx(c.duration, abs=.000001)
            assert clip['start'] == 0
    names=[item['name'] for item in project['project']['items'].values() if 'Sequence' in item['kind']]
    assert names == [c.title for c in cuts]
    items=[item for item in project['project']['items'].values() if 'Sequence' in item['kind']]
    for item,c in zip(items,cuts):
        variant=tmp_path/f"sequence-{c.id}.fcproj"
        run([cli,'--project',native,'--save-as',variant,'exec','sequence.open',json.dumps({'item':item['id']})])
        rendered=tmp_path/f"render-{c.id}.mp4"
        run([cli,'--project',variant,'export',rendered,'--gpu-rendering','off'])
        result=probe(rendered)
        assert result.duration==pytest.approx(c.duration,abs=.05)
        assert (result.width,result.height)==(m.width,m.height)
        assert result.audio
        if c.id==2:
            for t, expected in [(.4,0),(1.4,255)]:
                raw=tmp_path/f'native-{t}.gray'
                run([executable('ffmpeg'),'-v','error','-ss',t,'-i',rendered,'-frames:v','1',
                     '-vf','scale=1:1','-pix_fmt','gray','-f','rawvideo',raw])
                assert abs(raw.read_bytes()[0]-expected)<10
            wav=tmp_path/'native-reaction.wav'
            extract_audio(result,wav)
            with wave.open(str(wav)) as w:
                x=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)
            def component(t, frequency):
                chunk=x[int(t*16000):int((t+.2)*16000)]
                return abs(np.sum(chunk*np.exp(-2j*np.pi*frequency*np.arange(len(chunk))/16000)))
            # Imported mic reaction remains at 18 - 17.12 = .88 seconds;
            # independent game track (880 Hz) remains audible on both sides.
            assert component(1.2,440) > 15 * component(.2,440)
            assert component(.2,880)>10000 and component(1.2,880)>10000



def test_variable_frame_rate_bounds_and_export(tmp_path):
    path=tmp_path/'vfr.mkv'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=25:d=5',
         '-vf',"select='if(lt(t,2),not(mod(n,2)),1)'",'-fps_mode','vfr','-c:v','libx264',path])
    m=probe(path)
    a,b=align_bounds(m,.13,3.17)
    data=json.loads(run([executable('ffprobe'),'-v','error','-select_streams','v:0','-show_frames',
        '-show_entries','frame=best_effort_timestamp_time','-of','json',path]))
    pts=[float(f['best_effort_timestamp_time'])-m.origin for f in data['frames']]
    assert a in pts and b in pts
    result=probe(export_clip(m,cut(a,b),tmp_path/'vfr-cut.mp4'))
    assert result.duration==pytest.approx(b-a,abs=.08)


def test_candidate_words_and_deduplication(movie):
    m=probe(movie)
    speech=[{'start':8,'end':14,'text':'Nossa olha como consegui!','words':[
        {'start':8,'end':9,'word':'Nossa'}, {'start':10,'end':12,'word':'olha'}, {'start':12,'end':14,'word':'consegui!'}]},
        {'start':13,'end':20,'text':'Como conseguimos isso?','words':[]}]
    cuts=generate(m,[],[],speech,minimum=8,maximum=25)
    assert cuts and len(cuts)==1
    for c in cuts:
        for seg in speech:
            for w in seg['words']:
                assert not w['start'] < c.start < w['end']
                assert not w['start'] < c.end < w['end']


def test_cache_reuses_offline_features(movie,tmp_path,monkeypatch):
    import radar.pipeline as p
    first=p.analyze(movie,track=1,model='off',minimum=8,maximum=16,cache_dir=tmp_path)
    def unexpected(*a,**kw): raise AssertionError('Features deveriam vir do cache')
    monkeypatch.setattr(p,'visual_features',unexpected)
    monkeypatch.setattr(p,'extract_audio',unexpected)
    second=p.analyze(movie,track=1,model='off',minimum=8,maximum=16,cache_dir=tmp_path)
    assert [(c.start,c.end) for c in first[1]] == [(c.start,c.end) for c in second[1]]
    assert second[3] == first[3]
