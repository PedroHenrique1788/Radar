"""Streaming features: one compact record per second, never a whole movie in RAM."""
import subprocess
import tempfile
import wave
import math
import queue
import threading
import numpy as np
from .media import executable, check_cancel,managed_process


def sound_features(path, cancel=None,start=0,progress=lambda *a:None):
    values = []
    with wave.open(str(path), 'rb') as w:
        while True:
            check_cancel(cancel)
            raw = w.readframes(w.getframerate())
            if not raw:
                break
            x = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768
            rms = float(np.sqrt(np.mean(x * x)))
            peak=float(np.max(np.abs(x)))
            values.append({'t':start+len(values),'rms':rms,'db':float(20*np.log10(max(rms,1e-6))),
                           'peak_db':float(20*np.log10(max(peak,1e-6)))})
            progress(min(w.getnframes()/w.getframerate(),len(values)))
    return values


def visual_features(media,cancel=None,progress=lambda *a:None,*,start=0,duration=None,sample_fps=1,width=64,previous=None,with_state=False):
    duration=media.duration-start if duration is None else duration
    if not 0<=start<media.duration or not 0<duration<=media.duration-start+1e-6:raise ValueError('Lote visual fora do original.')
    height=width*9//16
    absolute=media.origin+start
    cmd=[executable('ffmpeg'),'-v','error','-nostdin','-copyts']
    if abs(media.origin)<1e-6 and start>2:cmd+=['-seek_timestamp','1','-ss',start-2]
    cmd+=['-i',media.path,'-map',f'0:{media.video_index}','-vf',
          f'trim=start={absolute}:end={absolute+duration},setpts=PTS-({absolute})/TB,fps={sample_fps}:start_time=0,scale={width}:{height}',
          '-pix_fmt','gray','-f','rawvideo','-']
    values=[]
    previous=np.asarray(previous,dtype=np.float32) if previous is not None else None
    frames=queue.Queue(maxsize=2)
    stop=threading.Event()
    size=width*height
    with tempfile.TemporaryFile() as err:
        with managed_process(cmd,cancel,stdout=subprocess.PIPE,stderr=err) as p:
            def deliver(value):
                while not stop.is_set():
                    try:frames.put(value,timeout=.1);return
                    except queue.Full:pass
            def read():
                try:
                    while not stop.is_set():
                        raw=p.stdout.read(size)
                        deliver(raw)
                        if not raw:break
                except Exception as exc:deliver(exc)
            reader=threading.Thread(target=read,daemon=True);reader.start()
            try:
                index=0
                while True:
                    check_cancel(cancel)
                    try:raw=frames.get(timeout=.1)
                    except queue.Empty:continue
                    if isinstance(raw,Exception):raise RuntimeError('Falha ao ler quadros do FFmpeg.') from raw
                    if not raw:break
                    if len(raw)!=size:raise RuntimeError('Quadro visual incompleto.')
                    frame=np.frombuffer(raw,dtype=np.uint8).astype(np.float32)
                    change=0 if previous is None else float(np.mean(np.abs(frame-previous))/255)
                    t=start+index/sample_fps
                    if t<start+duration-1e-6:
                        values.append({'t':t,'change':change,'possible_transition':change>=.2,'static':change<.005})
                    previous=frame;index+=1
                    progress(min(100,100*index/max(1,math.ceil(duration*sample_fps))),f'Imagem: {index} amostras do lote')
                if p.wait():
                    err.seek(0,2);err.seek(max(0,err.tell()-6000))
                    raise RuntimeError(err.read().decode(errors='replace'))
            finally:
                stop.set()
                if p.poll() is None:p.kill()
                p.wait();p.stdout.close();reader.join(timeout=1)
    state={'values':values,'last_frame':previous.astype(np.uint8).tolist() if previous is not None else None}
    return state if with_state else values
