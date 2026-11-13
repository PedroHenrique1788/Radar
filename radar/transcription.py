import os
import wave
import tempfile
from pathlib import Path
from .media import check_cancel, Cancelled
from .runtime import resolve_model


def constrain_speech(segments,start,end):
    """ASR timestamps are estimates; do not place words in padded silence."""
    result=[]
    for original in segments:
        if original['end']<=start or original['start']>=end:continue
        segment={**original,'start':max(start,original['start']),'end':min(end,original['end'])}
        if original.get('words'):
            words=[{**w,'start':max(start,w['start']),'end':min(end,w['end'])}
                   for w in original['words'] if w['end']>start and w['start']<end]
            if not words:continue
            segment['words']=words
            segment['text']=' '.join(w['word'].strip() for w in words)
        elif original['start']<start or original['end']>end:
            # Without word times, a partial sentence cannot be isolated safely.
            continue
        result.append(segment)
    return result


def transcribe(path, model_name='tiny', cancel=None, progress=lambda *a: None, model_factory=None,*,threads=None,checkpoint=None):
    """Five-minute WAV chunks bound faster-whisper's decoded audio memory."""
    check_cancel(cancel)
    progress(None,'Carregando Whisper local em CPU/int8…')
    if model_factory is None:
        from faster_whisper import WhisperModel
        model_factory = WhisperModel
    model = model_factory(resolve_model(model_name), device='cpu', compute_type='int8', cpu_threads=threads or min(4, os.cpu_count() or 2))
    segments = []
    def decode(file,offset):
        result=[]
        iterator,info=model.transcribe(str(file),language='pt',word_timestamps=True,vad_filter=True,
                                       beam_size=1,condition_on_previous_text=False)
        for seg in iterator:
            check_cancel(cancel)
            if seg.no_speech_prob>.8:continue
            result.append({'start':offset+seg.start,'end':offset+seg.end,'text':seg.text.strip(),'words':[
                {'start':offset+w.start,'end':offset+w.end,'word':w.word} for w in (seg.words or [])]})
        return result
    try:
        if isinstance(path,(list,tuple)):
            for n,item in enumerate(path):
                check_cancel(cancel)
                current=decode(item['path'],item['start'])
                if checkpoint:checkpoint(item['index'],current)
                segments.extend(current)
                progress(100*(n+1)/max(1,len(path)),f'Transcrição: {n+1}/{len(path)} lotes pendentes')
            return segments
        with tempfile.TemporaryDirectory(prefix='radar-speech-') as tmp, wave.open(str(path),'rb') as source:
            chunk_path=Path(tmp)/'speech-chunk.wav'
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
                segments.extend(decode(chunk_path,offset/rate))
                offset += len(raw) // 2
                progress(100 * offset / max(total, 1), 'Transcrevendo em CPU (português)…')
    finally:
        del model
    return segments
