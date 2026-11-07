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
        assert len(otio.schema.Timeline().tracks)==0
    return {'tools': tools, 'gui': True, 'media_export': True, 'whisper_int8': True,
            'silence_vad': True, 'portuguese_transcript': text, 'otio': True,
            'portable_export':True, 'transcript_txt':True, 'filmcraft':filmcraft_result}


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
