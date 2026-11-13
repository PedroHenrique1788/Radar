"""Real PCM peak envelopes, read in bounded batches and cached by viewport."""
import math
from pathlib import Path
import tempfile
import wave
import numpy as np

from .checkpoints import source_identity,signature,read_json,atomic_json
from .media import extract_audio,check_cancel,executable
from .export import verify_source


def build_waveform(media,cancel=None,progress=lambda *a:None,*,start=0.,end=None,bins=2048,cache_dir='temporarios'):
    verify_source(media)
    end=media.duration if end is None else end
    if not 0<=start<end<=media.duration+1e-6 or not isinstance(bins,int) or not 16<=bins<=4096:raise ValueError('Janela ou resolução da forma de onda inválida.')
    tool=Path(executable('ffmpeg'));stat=tool.stat()
    identity=source_identity(media.path)
    key=signature(['waveform-v1',identity,start,end,bins,str(tool),stat.st_size,stat.st_mtime_ns])
    path=Path(cache_dir)/'waveforms'/f'{key}.json'
    previous=read_json(path)
    try:
        data=previous.get('data') if isinstance(previous,dict) else None
        valid=(isinstance(data,dict) and data.get('start')==start and data.get('end')==end
               and isinstance(data.get('peaks'),list) and len(data['peaks'])<=bins
               and all(isinstance(p,(int,float)) and math.isfinite(p) and 0<=p<=1 for p in data['peaks'])
               and previous.get('sha256')==signature(data))
    except (ValueError,TypeError):valid=False
    if valid:
        check_cancel(cancel);progress(100,'Ondas de áudio recuperadas do cache.');return data
    count=min(bins,max(16,math.ceil((end-start)*20)))
    peaks=np.zeros(count,dtype=np.float32)
    if media.audio:
        with tempfile.TemporaryDirectory(prefix='radar-waveform-') as tmp:
            cursor=start
            while cursor<end-1e-6:
                check_cancel(cancel);duration=min(120,end-cursor);wav=Path(tmp)/'audio.wav'
                extract_audio(media,wav,'mix',cancel,start=cursor,duration=duration,
                              progress=lambda t:progress(100*(cursor-start+t)/(end-start),'Lendo áudio original para a timeline…'))
                with wave.open(str(wav),'rb') as source:
                    rate=source.getframerate();offset=0
                    while True:
                        check_cancel(cancel);raw=source.readframes(rate)
                        if not raw:break
                        values=np.abs(np.frombuffer(raw,dtype='<i2').astype(np.float32))/32768
                        indices=np.minimum(count-1,((cursor-start+(offset+np.arange(len(values)))/rate)/(end-start)*count).astype(np.int32))
                        np.maximum.at(peaks,indices,values);offset+=len(values)
                cursor+=duration
                progress(100*(cursor-start)/(end-start),'Ondas de áudio do original: lote concluído.')
    data={'start':start,'end':end,'peaks':peaks.tolist(),'source_id':signature(identity),'audio':bool(media.audio)}
    verify_source(media);check_cancel(cancel)
    atomic_json(path,{'sha256':signature(data),'data':data})
    progress(100,'Ondas de áudio prontas.' if media.audio else 'Vídeo sem áudio: a timeline mostra silêncio.')
    return data
