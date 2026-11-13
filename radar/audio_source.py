"""Optional microphone recordings mapped explicitly onto the original timeline."""
import json
import math
import re
from pathlib import Path

from .media import executable,run
from .checkpoints import source_identity,signature
from .model import parse_time


def probe_audio(path,cancel=None):
    identity=source_identity(path)
    data=json.loads(run([executable('ffprobe'),'-v','error','-show_streams','-show_format','-of','json',identity['path']],cancel,timeout=60))
    streams=[s for s in data.get('streams',[]) if s.get('codec_type')=='audio']
    if not streams:raise ValueError('O arquivo externo não contém uma faixa de áudio.')
    audio=streams[0];origin=float(audio.get('start_time',0))
    container=data.get('format',{})
    if audio.get('duration'):duration=float(audio['duration'])
    elif audio.get('tags',{}).get('DURATION'):duration=parse_time(audio['tags']['DURATION'])-origin
    elif 'matroska' in container.get('format_name',''):duration=float(container.get('duration',0))-origin
    else:duration=float(container.get('duration',0))+float(container.get('start_time',0))-origin
    if not math.isfinite(origin) or not math.isfinite(duration) or duration<=0:
        raise ValueError('Duração do áudio externo indisponível.')
    return {'path':identity['path'],'index':audio['index'],'origin':origin,'duration':duration,
            'source':identity,'source_id':signature(identity)}


def audio_role(media,track,options):
    if options.audio_role!='auto':return options.audio_role
    if options.external_audio:return 'microphone'
    selected=media.audio if track=='mix' else [a for a in media.audio if a['index']==int(track)]
    return 'microphone' if len(selected)==1 and re.search(r'\b(microfone|microphone|mic|voz|voice)\b',selected[0].get('title',''),re.I) else 'mixed'


def extract_external(source,target,offset=0.,cancel=None,*,start=0.,duration,progress=None):
    """Video seconds = external audio seconds + offset (never shifts the video)."""
    relative=start-offset
    args=[executable('ffmpeg'),'-v','error','-nostdin','-y']
    if relative>=source['duration'] or relative+duration<=0:
        args+=['-f','lavfi','-i','anullsrc=r=16000:cl=mono','-t',duration,'-c:a','pcm_s16le',str(target)]
    else:
        absolute=source['origin']+relative
        args+=['-copyts']
        if abs(source['origin'])<1e-6 and relative>2:args+=['-seek_timestamp','1','-ss',relative-2]
        args+=['-i',source['path'],'-map',f"0:{source['index']}",'-af',
               f"atrim=start={max(source['origin'],absolute)}:end={min(source['origin']+source['duration'],absolute+duration)},asetpts=PTS-({absolute})/TB,aresample=16000:async=1:first_pts=0,apad=whole_dur={duration},atrim=duration={duration}",
               '-t',duration,'-ar','16000','-ac','1','-c:a','pcm_s16le',str(target)]
    run(args,cancel,progress=progress,duration=duration)
