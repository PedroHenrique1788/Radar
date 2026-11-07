import os
import wave
from pathlib import Path
from .media import check_cancel, Cancelled
from .runtime import resolve_model


def transcribe(path, model_name='tiny', cancel=None, progress=lambda *a: None, model_factory=None):
    """Five-minute WAV chunks bound faster-whisper's decoded audio memory."""
    if model_factory is None:
        from faster_whisper import WhisperModel
        model_factory = WhisperModel
    model = model_factory(resolve_model(model_name), device='cpu', compute_type='int8', cpu_threads=min(4, os.cpu_count() or 2))
    segments = []
    chunk_path = Path(path).with_name('speech-chunk.wav')
    try:
        with wave.open(str(path), 'rb') as source:
            rate, total = source.getframerate(), source.getnframes()
            offset = 0
            while offset < total:
                check_cancel(cancel)
                raw = source.readframes(rate * 300)
                if not raw:
                    break
                with wave.open(str(chunk_path), 'wb') as out:
                    out.setparams(source.getparams())
                    out.writeframes(raw)
                iterator, info = model.transcribe(str(chunk_path), language='pt', word_timestamps=True,
                                                 vad_filter=True, beam_size=1, condition_on_previous_text=False)
                for seg in iterator:
                    check_cancel(cancel)
                    if seg.no_speech_prob > .8:
                        continue
                    segments.append({'start': offset / rate + seg.start, 'end': offset / rate + seg.end,
                                     'text': seg.text.strip(), 'words': [
                                         {'start': offset / rate + w.start, 'end': offset / rate + w.end, 'word': w.word}
                                         for w in (seg.words or [])]})
                offset += len(raw) // 2
                progress(60 + 25 * offset / max(total, 1), 'Transcrevendo em CPU (português)…')
    finally:
        chunk_path.unlink(missing_ok=True)
    return segments
