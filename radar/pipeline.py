"""Existing local analysis flow, checkpointed by stage and bounded batch."""
from dataclasses import asdict
import logging
import math
import os
from pathlib import Path
import shutil
import wave
import time

from .media import probe,extract_audio,align_bounds,check_cancel,Cancelled,executable
from .signals import sound_features,visual_features
from .transcription import transcribe,constrain_speech
from .candidates import generate
from .model import Cut,Media
from .profiles import AnalysisOptions
from .control import ExecutionControl
from .checkpoints import CheckpointStore,StageError,STAGES,signature
from .runtime import resolve_model
from .audio_source import probe_audio,extract_external,audio_role
from .intelligence import SpeechIndex


def _valid_audio(path,record):
    if not isinstance(record,dict) or not path.is_file():return False
    try:
        stat=path.stat()
        with wave.open(str(path),'rb') as audio:
            return (record.get('size')==stat.st_size and record.get('mtime_ns')==stat.st_mtime_ns
                    and audio.getnchannels()==1 and audio.getsampwidth()==2 and audio.getframerate()==16000
                    and audio.getnframes()>0)
    except (OSError,wave.Error,EOFError):return False


def analyze(path,track='mix',count=10,minimum=15.,maximum=60.,model='off',
            cache_dir='temporarios',cancel=None,progress=lambda *a:None,*,options=None,requested_count=None):
    opts=AnalysisOptions.from_record(options if options is not None else cancel.options if isinstance(cancel,ExecutionControl) else None)
    if not 1<=count<=20 or not 1<=minimum<=maximum<=600:raise ValueError('Configuração de duração ou quantidade inválida.')
    if not opts.audio and not opts.visual and model=='off':raise ValueError('Ative pelo menos áudio, imagem ou transcrição.')
    control=cancel if isinstance(cancel,ExecutionControl) else ExecutionControl(opts,cancel)
    control.options=opts
    check_cancel(control)
    store=CheckpointStore(path,cache_dir)
    store.acquire()
    control.job_dir=store.folder
    stage='identify'
    warnings=[]
    optional_failed=False
    last_emit=[None,0.]

    def report(name,done=0,total=None,unit='',text='',**counts):
        control.report(STAGES[name],done,total,unit,**counts)
        percent=None if total is None else min(100,100*done/total) if total else 100
        now=time.monotonic()
        if last_emit[0]!=name or now-last_emit[1]>=.1 or total is not None and done>=total:
            progress(percent,STAGES[name]+': '+(text or (f'{done:g}/{total:g} {unit}' if total is not None else 'processando…')))
            last_emit[:]=[name,now]

    def start(name,key,total,done=0,unit='lotes'):
        nonlocal stage
        stage=name;store.start(name,key,total)
        report(name,done,total,unit,f'{done:g}/{total:g} {unit} reaproveitados' if done else '')

    def mark(name,done,total,status='running',error=None):
        store.mark(name,done,total,status,error)

    try:
        with control.bind():
            def tool_stamp(name):
                file=Path(executable(name)).resolve();stat=file.stat()
                return [str(file),stat.st_size,stat.st_mtime_ns]
            ffmpeg_stamp=tool_stamp('ffmpeg');ffprobe_stamp=tool_stamp('ffprobe')
            request={'path':str(Path(path).resolve()),'track':track,'count':count,'minimum':minimum,'maximum':maximum,
                     'model':model,'options':opts.record(),'requested_count':requested_count or count}
            store.manifest['request']=request
            key=signature(['media-v1',store.source_id,ffprobe_stamp])
            start('identify',key,1,unit='arquivo')
            metadata=store.load('identify',key)
            media=Media(**metadata) if isinstance(metadata,dict) else probe(path,control)
            media.source_id=store.source_id
            if metadata is None:store.save('identify',key,asdict(media))
            check_cancel(control)
            external=probe_audio(opts.external_audio,control) if opts.external_audio else None
            if external:
                store.dependencies['external_audio']=external['source']
                if opts.external_offset>=media.duration or opts.external_offset+external['duration']<=0:
                    raise ValueError('O áudio externo não se sobrepõe ao vídeo com este ajuste de sincronização.')
            elif track!='mix' and int(track) not in [a['index'] for a in media.audio]:raise ValueError('Faixa de áudio inexistente.')
            media.analysis_audio={'kind':'external' if external else 'video','role':audio_role(media,track,opts),
                                  'path':external['path'] if external else media.path,
                                  'source_id':external['source_id'] if external else media.source_id,
                                  'offset':opts.external_offset if external else 0.,'track':external['index'] if external else track,
                                  'export_note':'MP4 preserva somente as faixas originais do vídeo.'}
            mark('identify',1,1,'complete');report('identify',1,1,'arquivo')
            batches=[(i,offset,min(opts.batch_seconds,media.duration-offset)) for i,offset in enumerate(range(0,math.ceil(media.duration),opts.batch_seconds))]
            audio_key=signature(['external-wav-v1',external['source_id'],opts.external_offset,opts.batch_seconds,ffmpeg_stamp,media.duration]) if external else signature(['audio-wav-v2',store.source_id,track,opts.batch_seconds,ffmpeg_stamp,media.origin,media.duration])
            wavs={};extract_done=0
            needs_audio=bool(external or media.audio) and (opts.audio or model!='off')
            for i,offset,duration in batches if needs_audio else []:
                target=store.folder/'extract'/audio_key/f'{i:06}.wav'
                if _valid_audio(target,store.load('extract',audio_key,i)):
                    wavs[i]=target;extract_done+=duration
            start('extract',audio_key,media.duration if needs_audio else 0,extract_done,'s')
            for i,offset,duration in batches if needs_audio else []:
                check_cancel(control)
                if i in wavs:continue
                target=store.folder/'extract'/audio_key/f'{i:06}.wav'
                target.parent.mkdir(parents=True,exist_ok=True)
                required=int(duration*16000*2)+50*1024*1024
                if shutil.disk_usage(target.parent).free<required:raise RuntimeError('Espaço livre insuficiente para o próximo lote de áudio e sua finalização. Libere espaço e retome esta etapa.')
                temporary=target.with_suffix('.part.wav')
                try:
                    if external:
                        extract_external(external,temporary,opts.external_offset,control,start=offset,duration=duration,
                                         progress=lambda seconds:report('extract',extract_done+seconds,media.duration,'s'))
                    else:
                        extract_audio(media,temporary,track,control,start=offset,duration=duration,
                                      progress=lambda seconds:report('extract',extract_done+seconds,media.duration,'s'))
                    with wave.open(str(temporary),'rb') as audio:
                        if not audio.getnframes():raise RuntimeError('FFmpeg gerou um lote de áudio vazio.')
                    os.replace(temporary,target)
                    stat=target.stat()
                    store.save('extract',audio_key,{'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'start':offset,'duration':duration},i)
                finally:temporary.unlink(missing_ok=True)
                wavs[i]=target;extract_done+=duration
                mark('extract',extract_done,media.duration);report('extract',extract_done,media.duration,'s')
            mark('extract',extract_done,media.duration if needs_audio else 0,'complete' if needs_audio else 'skipped')

            sound_key=signature(['sound-envelope-v3',audio_key])
            sound_parts={i:store.load('audio',sound_key,i) for i,_,_ in batches if opts.audio and i in wavs}
            sound_done=sum(duration for i,_,duration in batches if sound_parts.get(i) is not None)
            start('audio',sound_key,media.duration if sound_parts else 0,sound_done,'s')
            for i,offset,duration in batches if sound_parts else []:
                check_cancel(control)
                if sound_parts.get(i) is not None:continue
                data=sound_features(wavs[i],control,start=offset,progress=lambda seconds:report('audio',sound_done+seconds,media.duration,'s'))
                store.save('audio',sound_key,data,i);sound_parts[i]=data;sound_done+=duration
                mark('audio',sound_done,media.duration);report('audio',sound_done,media.duration,'s')
            mark('audio',sound_done,media.duration if sound_parts else 0,'complete' if sound_parts else 'skipped')
            sound=[point for i in sorted(sound_parts) for point in (sound_parts[i] or [])]

            visual_key=signature(['visual-v3',store.source_id,opts.sample_fps,opts.visual_width,opts.batch_seconds,ffmpeg_stamp,media.origin,media.duration])
            visual_parts={i:store.load('visual',visual_key,i) for i,_,_ in batches if opts.visual}
            visual_done=sum(duration for i,_,duration in batches if visual_parts.get(i) is not None)
            start('visual',visual_key,media.duration if opts.visual else 0,visual_done,'s')
            previous=None
            for i,offset,duration in batches if opts.visual else []:
                check_cancel(control)
                if visual_parts.get(i) is None:
                    data=visual_features(media,control,lambda percent,text:report('visual',visual_done+duration*percent/100,media.duration,'s',text),
                                         start=offset,duration=duration,sample_fps=opts.sample_fps,width=opts.visual_width,previous=previous,with_state=True)
                    store.save('visual',visual_key,data,i);visual_parts[i]=data;visual_done+=duration
                    mark('visual',visual_done,media.duration);report('visual',visual_done,media.duration,'s')
                previous=visual_parts[i]['last_frame']
            mark('visual',visual_done,media.duration if opts.visual else 0,'complete' if opts.visual else 'skipped')
            visual=[point for i in sorted(visual_parts) for point in visual_parts[i]['values']]

            resolved=Path(resolve_model(model))
            weights_file=resolved/'model.bin'
            model_stamp=[str(resolved),weights_file.stat().st_size,weights_file.stat().st_mtime_ns] if weights_file.is_file() else model
            speech_key=signature(['speech-v4-real-coverage' if external else 'speech-v2',audio_key,model_stamp,'faster-whisper-1.2.1','pt','word_timestamps'])
            speech_start=max(0.,opts.external_offset) if external else 0.
            speech_end=min(media.duration,opts.external_offset+external['duration']) if external else media.duration
            speech_parts={i:store.load('transcription',speech_key,i) for i,_,_ in batches if model!='off' and i in wavs}
            for i in list(speech_parts):
                offset=batches[i][1];duration=batches[i][2]
                outside=external and (offset>=speech_end or offset+duration<=speech_start)
                if speech_parts[i] is None and (outside or sound_parts.get(i) is not None and not any(point['db']>-50 for point in sound_parts[i])):
                    store.save('transcription',speech_key,[],i);speech_parts[i]=[]
            pending=[]
            for i,offset,duration in batches:
                if i not in speech_parts or speech_parts[i] is not None:continue
                item={'index':i,'path':wavs[i],'start':offset,'duration':duration}
                if external:
                    a=max(offset,speech_start);b=min(offset+duration,speech_end)
                    item.update(start=a,duration=b-a,clip_start=a-offset)
                pending.append(item)
            start('transcription',speech_key,len(speech_parts),sum(v is not None for v in speech_parts.values()))
            def transcribed(index,data):
                check_cancel(control)
                data=constrain_speech(data,speech_start,speech_end)
                store.save('transcription',speech_key,data,index);speech_parts[index]=data
                completed=sum(v is not None for v in speech_parts.values())
                mark('transcription',completed,len(speech_parts));report('transcription',completed,len(speech_parts),'lotes')
            if pending:
                try:
                    transcribe(pending,model,control,lambda n,msg:progress(None,STAGES['transcription']+': '+msg),
                               threads=opts.threads,checkpoint=transcribed)
                except Cancelled:raise
                except Exception as exc:
                    logging.exception('Falha na transcrição opcional; preservando demais módulos')
                    optional_failed=True
                    warnings.append(f'Transcrição indisponível ({type(exc).__name__}). Os lotes já transcritos e os sinais locais foram preservados. Retome para tentar somente os lotes pendentes ou use o Radar sem fala.')
                    mark('transcription',sum(v is not None for v in speech_parts.values()),len(speech_parts),'failed',exc)
            elif model=='off':warnings.append('Transcrição desativada. Limites e contexto requerem revisão humana.')
            if not optional_failed:mark('transcription',len(speech_parts),len(speech_parts),'complete' if speech_parts else 'skipped')
            speech=constrain_speech([segment for i in sorted(speech_parts) for segment in (speech_parts[i] or [])],speech_start,speech_end)
            speech_index=SpeechIndex(speech)
            check_cancel(control)
            fusion_key=signature(['fusion-v3-coverage',sound_key if sound else None,visual_key if visual else None,
                                  speech_key,[(i,signature(v)) for i,v in sorted(speech_parts.items()) if v is not None]])
            start('fusion',fusion_key,1,unit='conjunto')
            fusion={'audio_points':len(sound),'visual_points':len(visual),'speech_segments':len(speech),
                    'available':{'audio':bool(sound),'visual':bool(visual),'speech':bool(speech)}}
            store.save('fusion',fusion_key,fusion)
            mark('fusion',1,1,'complete');report('fusion',1,1,'conjunto',moments=len(sound)+len(visual))

            ranking_key=signature(['ranking-v4-context',fusion_key,count,minimum,maximum,opts.weights,opts.before,opts.after,
                                   opts.phrases,media.analysis_audio['role'],ffprobe_stamp])
            start('classification',ranking_key,count,unit='sugestões')
            saved=store.load('classification',ranking_key)
            if saved is not None:
                aligned=[Cut(**row) for row in saved]
                for cut in aligned:cut.validate(media.duration)
            else:
                cuts=generate(media,sound,visual,speech,count,minimum,maximum,options=opts,cancel=control,
                              progress=lambda done,total:report('classification',done,total,'candidatos',evaluated=total))
                aligned=[]
                for index,cut in enumerate(cuts):
                    check_cancel(control)
                    bounds_key=signature(['bounds-v1',store.source_id,media.origin,media.duration,ffprobe_stamp,cut.start,cut.end])
                    bounds=store.load('bounds',bounds_key)
                    if bounds is None:
                        bounds=align_bounds(media,cut.start,cut.end,control)
                        store.save('bounds',bounds_key,bounds)
                    # A nearest-frame snap can enter a word by a few ms. Move
                    # outward and verify again on actual PTS, including VFR.
                    for _ in range(3):
                        crossing=speech_index.crossings(*bounds)
                        if not crossing:break
                        a,b=bounds
                        for unit in crossing:
                            if unit['start']<a<unit['end']:a=max(0.,unit['start']-.5/media.fps)
                            if unit['start']<b<unit['end']:b=min(media.duration,unit['end']+.5/media.fps)
                        bounds=align_bounds(media,a,b,control)
                    if speech_index.crossings(*bounds):continue
                    cut.start,cut.end=bounds
                    # Recompute text after the final frame alignment; reports,
                    # Gemini and the review panel see the same exact interval.
                    cut.transcript=speech_index.text(cut.start,cut.end)
                    if minimum-1e-6<=cut.duration<=maximum+1e-6:
                        cut.id=len(aligned)+1;aligned.append(cut)
                    mark('classification',index+1,len(cuts));report('classification',index+1,len(cuts),'limites',candidates=len(cuts))
                store.save('classification',ranking_key,[asdict(cut) for cut in aligned])
            if media.variable_fps:warnings.append('Possível taxa de quadros variável: use timestamps; números de quadro são nominais.')
            mark('classification',len(aligned),len(aligned),'complete')
            report('classification',len(aligned),len(aligned),'sugestões',candidates=len(aligned))
            store.validate_source()
            store.manifest.update(status='complete_with_warnings' if optional_failed else 'complete',result_key=ranking_key,warnings=warnings)
            store.save_manifest()
            return media,aligned,speech,warnings
    except (Cancelled,KeyboardInterrupt):
        store.interrupted('cancelled');raise
    except Exception as exc:
        store.interrupted('failed',exc)
        if isinstance(exc,StageError):raise
        raise StageError(stage,str(exc),store.folder) from exc
    finally:store.release()
