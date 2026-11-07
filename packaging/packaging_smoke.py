"""Executed by the frozen EXE on Windows; exercises bundled native dependencies."""
from pathlib import Path
import tempfile


def smoke():
    from radar.media import run, executable, probe
    from radar.pipeline import analyze
    from radar.export import export_clip, export_report
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
        segments,_ = model.transcribe(str(spoken), language='pt', beam_size=1)
        text=' '.join(s.text for s in segments).lower()
        assert 'teste' in text and ('vídeo' in text or 'video' in text), text
        assert len(otio.schema.Timeline().tracks)==0
    return {'tools': tools, 'gui': True, 'media_export': True, 'whisper_int8': True,
            'silence_vad': True, 'portuguese_transcript': text, 'otio': True}
