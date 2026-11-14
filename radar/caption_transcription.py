"""Reuse Radar's transcript cache; decode only missing audio from this Short."""
import math
from pathlib import Path
import tempfile

from .audio_source import probe_audio,extract_external
from .checkpoints import CheckpointStore,signature
from .control import ExecutionControl
from .export import verify_source
from .media import extract_audio,check_cancel
from .profiles import AnalysisOptions
from .transcription import transcribe,constrain_speech
from .transcription_cache import tool_stamp,audio_key,speech_key


def transcribe_cut(media,cut,track='mix',model='tiny',*,options=None,cache_dir='temporarios',cancel=None,progress=lambda *a:None):
    """Return original-time segments, including cached silence as a valid hit.

    Does not change the analysis manifest/request or the original transcript.
    Full-analysis batches and caption batches share the same model/audio stamp.
    """
    verify_source(media);cut.validate(media.duration)
    if model=='off':model='tiny'
    opts=AnalysisOptions.from_record(options)
    control=cancel if isinstance(cancel,ExecutionControl) else ExecutionControl(opts,cancel)
    store=CheckpointStore(media.path,cache_dir);store.acquire()
    try:
        with control.bind():
            external=probe_audio(opts.external_audio,control) if opts.external_audio else None
            if external:store.dependencies['external_audio']=external['source']
            elif track!='mix' and int(track) not in [a['index'] for a in media.audio]:raise ValueError('Faixa de áudio inexistente.')
            if not external and not media.audio:raise ValueError('Este vídeo não tem áudio para transcrever. Você pode adicionar legendas manualmente.')
            base=audio_key(store.source_id,media,track,opts,tool_stamp('ffmpeg'),external)
            speech=speech_key(base,model,external)
            coverage=(max(0.,opts.external_offset),min(media.duration,opts.external_offset+external['duration'])) if external else (0.,media.duration)
            a,b=max(cut.start,coverage[0]),min(cut.end,coverage[1])
            if b<=a:return []
            result=[];pending=[]
            coverage_index=store.load('caption_coverage',speech) or []
            first=int(a//opts.batch_seconds);last=int(math.ceil(b/opts.batch_seconds))
            for i in range(first,last):
                check_cancel(control)
                left,right=max(a,i*opts.batch_seconds),min(b,(i+1)*opts.batch_seconds)
                existing=store.load('transcription',speech,i)
                if existing is not None:
                    result.extend(constrain_speech(existing,left,right));continue
                cursor=left
                for row in sorted(coverage_index,key=lambda r:r['start']):
                    if row['end']<=cursor or row['start']>=right:continue
                    cached=store.load('caption_transcription',row['key'])
                    if cached is None:continue
                    if row['start']>cursor:
                        pending.append((signature(['caption-speech-v1',speech,cursor,row['start']]),cursor,row['start']))
                    a0,b0=max(cursor,row['start']),min(right,row['end'])
                    result.extend(constrain_speech(cached,a0,b0));cursor=b0
                    if cursor>=right:break
                if cursor<right:
                    key=signature(['caption-speech-v1',speech,cursor,right])
                    pending.append((key,cursor,right))
            if not pending:
                progress(100,'Transcrição em cache reutilizada; Whisper não foi executado.')
                return sorted(result,key=lambda s:s['start'])
            with tempfile.TemporaryDirectory(prefix='radar-caption-audio-') as tmp:
                items=[]
                for i,(key,left,right) in enumerate(pending):
                    check_cancel(control)
                    progress(None,f'Extraindo somente o Short: lote {i+1}/{len(pending)}…')
                    file=Path(tmp)/f'{i}.wav'
                    if external:extract_external(external,file,opts.external_offset,control,start=left,duration=right-left)
                    else:extract_audio(media,file,track,control,start=left,duration=right-left)
                    items.append({'index':i,'path':file,'start':left,'duration':right-left})
                def completed(i,data):
                    key,left,right=pending[i]
                    data=constrain_speech(data,left,right)
                    store.save('caption_transcription',key,data);result.extend(data)
                    coverage_index[:]=[r for r in coverage_index if r['key']!=key]
                    coverage_index.append({'start':left,'end':right,'key':key})
                    store.save('caption_coverage',speech,coverage_index)
                transcribe(items,model,control,progress,threads=opts.threads,checkpoint=completed)
            store.validate_source()
            return sorted(result,key=lambda s:s['start'])
    finally:store.release()
