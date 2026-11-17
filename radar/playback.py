"""Bounded FFmpeg/libass stream into Tk frames, synchronized to native audio.

No full-clip MP4 or decoded movie in memory. UI calls read_frame/position only;
all demuxing and device writes happen on one cancellable worker.
"""
from dataclasses import asdict,dataclass
import math
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time

from .export import effective_subtitle_entries,verify_source
from .media import executable
from .model import Cut
from .render import for_cut,video_filters,write_ass,require_libass
from .runtime import start_process


@dataclass(frozen=True)
class PreviewFrame:
    time: float
    width: int
    height: int
    rgb: bytes

    @property
    def ppm(self):return f'P6\n{self.width} {self.height}\n255\n'.encode('ascii')+self.rgb


def preview_command(media,cut,options,relative,*,max_size=480,fps=15,audio_track=None,threads=2):
    """Use the same framing/libass as MP4; subtitles see clip-relative time."""
    options=for_cut(options,cut);cut.validate(media.duration)
    if isinstance(threads,bool) or not isinstance(threads,int) or not 1<=threads<=16:raise ValueError('Limite de threads da prévia inválido.')
    if not math.isfinite(relative) or not 0<=relative<cut.duration:raise ValueError('Cursor fora do clipe.')
    if audio_track is not None and audio_track not in [a['index'] for a in media.audio]:raise ValueError('Faixa de monitoração inexistente.')
    w,h=options.dimensions(media);scale=min(1.,max_size/max(w,h))
    size=max(2,round(w*scale/2)*2),max(2,round(h*scale/2)*2)
    absolute=media.origin+cut.start+relative;end=media.origin+cut.end
    args=[executable('ffmpeg'),'-v','error','-nostdin','-threads',str(threads),'-filter_threads','1','-filter_complex_threads','1','-copyts']
    if abs(media.origin)<1e-6 and absolute>2:args+=['-seek_timestamp','1','-ss',absolute-2]
    args+=['-i',media.path]
    filters=[f'[0:{media.video_index}]trim=start={absolute}:end={end},setpts=PTS-({media.origin+cut.start})/TB[base]',
             video_filters('[base]',media,options,'styled',False,size_override=size)]
    # The caller enables libass by substituting this graph label. Leave source
    # PTS clip-relative until AFTER subtitle animation sampling.
    filters += [f'[styled]setpts=PTS-({relative})/TB,fps={fps}:start_time=0[v]']
    if audio_track is not None:
        filters += [f'[0:{audio_track}]atrim=start={absolute}:end={end},asetpts=PTS-({absolute})/TB,aresample=48000:async=1:first_pts=0,apad,atrim=duration={cut.duration-relative},aformat=sample_fmts=s16:channel_layouts=stereo[a]']
    args+=['-filter_complex',';'.join(filters),'-map','[v]']
    if audio_track is not None:args+=['-map','[a]','-c:a','pcm_s16le','-ar','48000','-ac','2']
    args+=['-c:v','rawvideo','-pix_fmt','rgb24','-threads',str(threads),'-t',cut.duration-relative,'-flush_packets','1','-f','nut','pipe:1']
    return args,size


class PlaybackSession:
    def __init__(self,media,cut,options,speech,relative=0.,*,audio_track=None,max_size=480,fps=15,audio_factory=None,threads=2):
        self.media=media;self.cut=Cut(**asdict(cut));self.options=for_cut(options,cut);self.speech=speech
        self.relative=float(relative);self.audio_track=audio_track;self.max_size=max_size;self.fps=fps
        self.audio_factory=audio_factory;self.threads=threads
        self.frames=queue.Queue(maxsize=6);self.pending=None;self.stop_event=threading.Event();self.pause_event=threading.Event()
        self.thread=None;self.process=None;self.audio=None;self.error=None;self.finished=False;self.ready=False
        self._clock_start=None;self._pause_start=None;self._paused_time=0.;self._last_position=self.relative
        self._lock=threading.RLock();self.decoded_frames=0;self.max_queued_frames=0

    def start(self):
        if self.thread is not None:raise RuntimeError('Sessão já iniciada.')
        self.thread=threading.Thread(target=self._run,name='radar-preview',daemon=True);self.thread.start();return self

    @property
    def position(self):
        with self._lock:
            if self.finished:return self._last_position
            if self.audio is not None:
                try:value=self.relative+self.audio.position
                except Exception as exc:
                    self.error=str(exc) or 'O dispositivo de áudio foi desconectado.'
                    self.stop_event.set();value=self._last_position
            elif self.audio_track is not None:return self._last_position
            elif self._clock_start is not None:
                now=self._pause_start if self._pause_start is not None else time.monotonic()
                value=self.relative+now-self._clock_start-self._paused_time
            else:return self.relative
            self._last_position=max(self._last_position,min(self.cut.duration,value))
            return self._last_position

    def pause(self):
        with self._lock:
            position=self.position
            if self.pause_event.is_set():return position
            self.pause_event.set();self._pause_start=time.monotonic()
            if self.audio is not None:
                try:self.audio.pause()
                except Exception:
                    self.stop_event.set()
                    raise
            return position

    def resume(self):
        with self._lock:
            if not self.pause_event.is_set():return
            if self.audio is not None:self.audio.resume()
            if self._pause_start is not None and self._clock_start is not None:
                self._paused_time+=time.monotonic()-max(self._pause_start,self._clock_start)
            self._pause_start=None;self.pause_event.clear()

    def _checkpoint(self):
        while self.pause_event.is_set() and not self.stop_event.is_set():self.stop_event.wait(.02)
        return not self.stop_event.is_set()

    def _clock_ready(self):
        with self._lock:
            if self._clock_start is None:self._clock_start=time.monotonic()
            self.ready=True

    def _run(self):
        process=None
        try:
            import av
            verify_source(self.media)
            args,size=preview_command(self.media,self.cut,self.options,self.relative,max_size=self.max_size,fps=self.fps,audio_track=self.audio_track,threads=self.threads)
            burn=self.cut.captions.get('enabled',False) if self.cut.captions else self.options.burn_subtitles
            entries=effective_subtitle_entries(self.cut,self.speech) if burn else []
            if entries:require_libass()
            with tempfile.TemporaryDirectory(prefix='radar-live-preview-') as work, tempfile.TemporaryFile() as err:
                if entries:
                    write_ass(Path(work)/'captions.ass',entries,self.cut,*self.options.dimensions(self.media))
                    index=args.index('-filter_complex')+1
                    args[index]=args[index].replace('[styled]setpts', '[styled]subtitles=filename=captions.ass,setpts')
                if not self._checkpoint():return
                if self.audio_track is not None:
                    factory=self.audio_factory
                    if factory is None:
                        from .playback_audio import AudioOutput
                        factory=AudioOutput
                    self.audio=factory(rate=48000,channels=2)
                process=start_process(args,stdout=subprocess.PIPE,stderr=err,cwd=work);self.process=process
                try:
                    if self.stop_event.is_set():return
                    with av.open(process.stdout,format='nut',mode='r',buffer_size=32768) as container:
                        for packet in container.demux():
                            if not self._checkpoint():break
                            for frame in packet.decode():
                                if not self._checkpoint():break
                                if isinstance(frame,av.VideoFrame):
                                    t=float(frame.pts*frame.time_base) if frame.pts is not None else self.decoded_frames/self.fps
                                    item=PreviewFrame(self.relative+max(0.,t),frame.width,frame.height,frame.to_ndarray(format='rgb24').tobytes())
                                    while self._checkpoint():
                                        try:self.frames.put(item,timeout=.03);break
                                        except queue.Full:continue
                                    self.decoded_frames+=1;self.max_queued_frames=max(self.max_queued_frames,self.frames.qsize());self._clock_ready()
                                elif self.audio is not None:
                                    raw=bytes(frame.planes[0])[:frame.samples*2*2]
                                    self.audio.write(raw,self.stop_event);self._clock_ready()
                    if not self.stop_event.is_set():
                        if not self.decoded_frames:raise RuntimeError('Nenhum quadro disponível neste intervalo. Confira os tempos e a mídia original.')
                        code=process.wait(timeout=10)
                        if code:
                            err.seek(0,2);err.seek(max(0,err.tell()-6000))
                            raise RuntimeError('Falha na prévia FFmpeg: '+err.read().decode('utf-8',errors='replace'))
                        # Drain native audio and the small video queue before EOF.
                        while not self.stop_event.is_set() and self.position<self.cut.duration-.02:
                            if not self._checkpoint():break
                            self.stop_event.wait(.01)
                finally:
                    if process.poll() is None:process.kill()
                    process.wait()
                    if process.stdout:process.stdout.close()
        except Exception as exc:
            if not self.stop_event.is_set():self.error=str(exc) or type(exc).__name__
        finally:
            with self._lock:
                try:self._last_position=self.position
                except Exception:pass
                if self.audio is not None:
                    try:self.audio.close()
                    except Exception as exc:
                        if not self.stop_event.is_set() and self.error is None:self.error=str(exc)
                    finally:self.audio=None
                self.finished=True

    def read_frame(self):
        """Take latest frame due on native audio clock; never block the Tk loop."""
        clock=self.position;chosen=None
        while True:
            if self.pending is None:
                try:self.pending=self.frames.get_nowait()
                except queue.Empty:break
            if self.pending.time>clock+.015:break
            chosen=self.pending;self.pending=None
        return chosen

    def stop(self):
        self.stop_event.set();self.pause_event.clear()
        p=self.process
        if p is not None and p.poll() is None:
            try:p.kill()
            except OSError:pass
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=2)
