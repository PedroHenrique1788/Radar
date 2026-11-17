"""Real FFmpeg/libass streaming tests; audio device is a bounded clocked sink."""
from dataclasses import replace
import threading
import time

import numpy as np
import pytest

from radar.captions import generate_track
from radar.media import executable,probe,run
from radar.model import Cut
from radar.playback import PlaybackSession,preview_command
from radar.render import RenderOptions


class ClockSink:
    """Real-time, bounded device substitute that retains PCM only for assertions.

    The sink clock advances only over submitted samples and stops on pause.
    Writers block beyond 150 ms queued, like a small native output buffer.
    """
    def __init__(self,*,rate,channels):
        self.rate=rate;self.channels=channels;self.raw=[];self.written=0.
        self.started=None;self.paused_at=None;self.paused_seconds=0.;self.closed=False
        self.max_buffered=0.;self.lock=threading.RLock()

    @property
    def position(self):
        with self.lock:
            if self.started is None:return 0.
            now=self.paused_at if self.paused_at is not None else time.monotonic()
            return max(0.,min(self.written,now-self.started-self.paused_seconds))

    def write(self,raw,cancel):
        while not cancel.is_set():
            with self.lock:
                if self.started is None:self.started=time.monotonic()
                pending=self.written-self.position
                if pending<.15:
                    self.raw.append(raw);self.written+=len(raw)/(self.rate*self.channels*2)
                    self.max_buffered=max(self.max_buffered,self.written-self.position)
                    return
            cancel.wait(.003)

    def pause(self):
        with self.lock:
            if self.paused_at is None:self.paused_at=time.monotonic()

    def resume(self):
        with self.lock:
            if self.paused_at is not None:
                self.paused_seconds+=time.monotonic()-self.paused_at;self.paused_at=None

    def close(self):self.closed=True


@pytest.fixture
def sinks():
    values=[]
    def factory(**options):
        sink=ClockSink(**options);values.append(sink);return sink
    return values,factory


@pytest.fixture(scope='module')
def movie(tmp_path_factory):
    target=tmp_path_factory.mktemp('playback-source')/'OBS com offset.mkv'
    run([executable('ffmpeg'),'-v','error','-copyts','-f','lavfi','-i',
         "color=red:s=160x90:r=25:d=13,drawbox=x=0:y=0:w=iw:h=ih:color=blue:t=fill:enable='gte(t,7)'",
         '-itsoffset','1','-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=12',
         '-map','0:v','-map','1:a','-c:v','libx264','-preset','ultrafast','-c:a','pcm_s16le',
         '-metadata:s:a:0','title=Jogo','-output_ts_offset','5',target])
    return probe(target)


def cut(a=0.,b=2.):return Cut(1,a,b,0,'Prévia Cefas','Teste de vídeo/áudio real',manual=True)


def collect(session,*,timeout=20):
    frames=[];drift=[];deadline=time.monotonic()+timeout
    try:
        while time.monotonic()<deadline:
            frame=session.read_frame()
            if frame is not None:
                frames.append(frame);drift.append(session.position-frame.time)
            if session.finished:
                last=session.read_frame()
                if last is not None:frames.append(last)
                break
            time.sleep(.003)
        assert session.finished,'Player não chegou ao fim do clipe.'
        assert session.error is None,session.error
        return frames,drift
    finally:session.stop()


def pixels(frame):return np.frombuffer(frame.rgb,dtype=np.uint8).reshape(frame.height,frame.width,3)


def test_embedded_stream_runs_past_six_seconds_with_pixels_and_no_mp4(movie,tmp_path,monkeypatch):
    # A 12-second complete playback proves removal of the old 6-second cap.
    from radar import playback
    commands=[];actual=playback.start_process
    def launch(args,**options):commands.append(list(args));return actual(args,**options)
    monkeypatch.setattr(playback,'start_process',launch)
    monkeypatch.chdir(tmp_path)
    session=PlaybackSession(movie,cut(0.,12.),RenderOptions(),[],audio_track=None,max_size=160,fps=10).start()
    frames,drift=collect(session)
    assert frames and frames[-1].time>11.5 and session.position==pytest.approx(12.,abs=.08)
    assert pixels(next(f for f in frames if .2<f.time<2)).mean(axis=(0,1))[0]>180
    assert pixels(next(f for f in frames if f.time>8)).mean(axis=(0,1))[2]>180
    assert max(drift)<.3 and session.max_queued_frames<=6 and session.frames.maxsize==6
    assert commands and commands[0][-3:]==['-f','nut','pipe:1']
    assert not any(str(arg).lower().endswith('.mp4') for cmd in commands for arg in cmd)
    assert not list(tmp_path.glob('*.mp4'))
    assert session.process.poll() is not None


def test_offset_audio_pcm_and_video_share_clock_without_drift(movie,sinks):
    values,factory=sinks
    session=PlaybackSession(movie,cut(0.,2.6),RenderOptions(),[],audio_track=movie.audio[0]['index'],
                            audio_factory=factory,max_size=160,fps=15).start()
    frames,drift=collect(session,timeout=8)
    assert frames and len(values)==1 and values[0].closed
    pcm=np.frombuffer(b''.join(values[0].raw),dtype='<i2').reshape(-1,2).astype(float)
    assert len(pcm)/48000==pytest.approx(2.6,abs=.025)
    assert np.max(np.abs(pcm[:int(.7*48000)]))<5
    assert np.sqrt(np.mean(pcm[int(1.3*48000):int(1.8*48000)]**2))>100
    assert max(drift)<.3 and session.max_queued_frames<=6
    assert values[0].max_buffered<.3


def test_midclip_seek_preserves_clip_relative_clock_and_pixels(movie,sinks):
    values,factory=sinks
    session=PlaybackSession(movie,cut(2.,10.),RenderOptions(),[],relative=5.5,
                            audio_track=movie.audio[0]['index'],audio_factory=factory,max_size=160,fps=10).start()
    frames,_=collect(session,timeout=8)
    assert frames and frames[0].time==pytest.approx(5.5,abs=.15)
    assert frames[-1].time>7.5 and session.position==pytest.approx(8.,abs=.08)
    assert all(pixels(f).mean(axis=(0,1))[2]>180 for f in frames)
    assert values[0].written==pytest.approx(2.5,abs=.025)


def test_libass_captions_and_format_are_rendered_in_actual_stream(movie):
    c=cut(2.,4.4);speech=[{'start':2.6,'end':3.6,'text':'CEFAS TESTE','words':[]}]
    c.captions=generate_track(c,speech)
    session=PlaybackSession(movie,c,RenderOptions(mode='vertical_blur'),speech,audio_track=None,max_size=320,fps=10).start()
    frames,_=collect(session,timeout=8)
    before=next(f for f in frames if .1<f.time<.5);active=next(f for f in frames if .9<f.time<1.3)
    assert before.width<before.height and before.height==320
    whites=lambda f:int(np.count_nonzero(np.min(pixels(f),axis=2)>180))
    assert whites(active)>whites(before)+10
    assert active.ppm.startswith(f'P6\n{active.width} {active.height}\n255\n'.encode())


def test_explicit_silent_monitor_never_opens_an_audio_device(movie):
    def forbidden(**options):raise AssertionError('Abriu áudio em monitoração silenciosa')
    session=PlaybackSession(movie,cut(0.,1.2),RenderOptions(),[],audio_track=None,audio_factory=forbidden,max_size=80,fps=10).start()
    frames,_=collect(session,timeout=5)
    assert frames and session.position>1.1 and session.audio is None


def test_pause_resume_freezes_audio_and_video_position(movie,sinks):
    values,factory=sinks
    session=PlaybackSession(movie,cut(1.,3.2),RenderOptions(),[],audio_track=movie.audio[0]['index'],audio_factory=factory,max_size=80,fps=10).start()
    try:
        deadline=time.monotonic()+5
        while session.position<.25 and time.monotonic()<deadline:
            session.read_frame();time.sleep(.005)
        assert session.ready and values
        frozen=session.pause();time.sleep(.25)
        assert session.position==pytest.approx(frozen,abs=.025)
        assert session.pause_event.is_set()
        session.resume();frames,_=collect(session,timeout=6)
        assert frames and session.position>2.1 and values[0].closed
    finally:session.stop()


def test_bounded_queue_cancellation_and_start_paused_do_not_leave_workers(movie):
    session=PlaybackSession(movie,cut(0.,12.),RenderOptions(),[],audio_track=None,max_size=80,fps=30)
    session.pause();session.start();time.sleep(.12)
    assert not session.ready and session.decoded_frames==0
    session.resume()
    deadline=time.monotonic()+5
    while not session.ready and time.monotonic()<deadline:time.sleep(.005)
    assert session.ready
    time.sleep(.16);assert session.position>=.12  # pre-start pause is not subtracted twice
    while session.frames.qsize()<6 and time.monotonic()<deadline:time.sleep(.005)
    assert session.frames.qsize()==6 and session.max_queued_frames<=6
    session.stop();assert not session.thread.is_alive() and session.finished
    assert session.process is not None and session.process.poll() is not None
    # A never-started, pre-cancelled session should not launch FFmpeg either.
    cancelled=PlaybackSession(movie,cut(),RenderOptions(),[],audio_track=None)
    cancelled.stop();cancelled.start();cancelled.thread.join(timeout=2)
    assert cancelled.finished and cancelled.process is None and cancelled.error is None


def test_invalid_cursor_track_and_changed_source_report_clear_errors(movie):
    for relative,track in [(-1,None),(2.,None),(0.,999)]:
        with pytest.raises(ValueError):preview_command(movie,cut(),RenderOptions(),relative,audio_track=track)
    session=PlaybackSession(replace(movie,source_id='changed'),cut(),RenderOptions(),[],audio_track=None).start()
    session.thread.join(timeout=3)
    assert session.finished and session.error and 'mudou' in session.error.lower()
    assert session.process is None


def test_audio_device_clock_loss_stops_worker_and_preserves_last_cursor(movie):
    values=[]
    class UnplugSink(ClockSink):
        unplugged=False
        @property
        def position(self):
            with self.lock:
                if self.unplugged:raise RuntimeError('Dispositivo de áudio removido')
                return super().position
    def factory(**options):
        value=UnplugSink(**options);values.append(value);return value
    session=PlaybackSession(movie,cut(0.,2.),RenderOptions(),[],audio_track=movie.audio[0]['index'],
                            audio_factory=factory,max_size=80,fps=10).start()
    try:
        deadline=time.monotonic()+5
        while session.position<.1 and not session.finished and time.monotonic()<deadline:
            session.read_frame();time.sleep(.005)
        assert values and session.ready and not session.finished
        sink=values[0]
        with sink.lock:
            before=session.position;sink.unplugged=True
            # Exercise the actual UI property access; this must not throw and
            # must stop the session even if the decoder is waiting on a queue.
            assert session.position==before
        session.thread.join(timeout=3)
        assert session.finished and not session.thread.is_alive()
        assert session.stop_event.is_set() and sink.closed
        assert 'removido' in session.error and session.position==before
        assert session.process.poll() is not None
    finally:session.stop()


def test_audio_device_close_failure_still_finishes_session(movie):
    values=[]
    class CloseErrorSink(ClockSink):
        def close(self):
            self.closed=True
            raise RuntimeError('Falha ao fechar dispositivo de áudio')
    def factory(**options):
        value=CloseErrorSink(**options);values.append(value);return value
    session=PlaybackSession(movie,cut(0.,.6),RenderOptions(),[],audio_track=movie.audio[0]['index'],
                            audio_factory=factory,max_size=80,fps=10).start()
    try:
        deadline=time.monotonic()+5
        while not session.finished and time.monotonic()<deadline:
            session.read_frame();time.sleep(.005)
        session.thread.join(timeout=1)
        assert session.finished and not session.thread.is_alive()
        assert values[0].closed and session.audio is None
        assert 'fechar dispositivo' in session.error
        assert session.process.poll() is not None
    finally:session.stop()



def test_missing_decoder_dependency_reports_error_without_leaving_player_running(movie,monkeypatch):
    import builtins
    original=builtins.__import__
    def missing(name,*args,**kwargs):
        if name=='av':raise ImportError('PyAV indisponível: DLL de teste')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',missing)
    session=PlaybackSession(movie,cut(),RenderOptions(),[],audio_track=None).start()
    session.thread.join(timeout=3)
    assert session.finished and not session.thread.is_alive() and 'PyAV indisponível' in session.error
    assert session.process is None


def test_audio_write_failure_stops_ffmpeg_before_temporary_cwd_cleanup(movie,monkeypatch):
    from radar import playback
    original_directory=playback.tempfile.TemporaryDirectory
    observations=[];outputs=[]
    class CheckedDirectory:
        def __init__(self,*args,**kwargs):
            self.delegate=original_directory(*args,**kwargs)
        def __enter__(self):return self.delegate.__enter__()
        def __exit__(self,*args):
            process=session.process
            state=(process is not None and process.poll() is not None,
                   process is not None and process.stdout.closed)
            observations.append(state)
            try:
                assert state==(True,True),'FFmpeg ou seu pipe ainda estavam abertos ao limpar o cwd temporário.'
            finally:self.delegate.__exit__(*args)
            return False
    class WriteErrorSink:
        def __init__(self,**options):self.closed=False;self.wrote=False;outputs.append(self)
        @property
        def position(self):return 0.
        def write(self,raw,cancel):
            self.wrote=True
            raise RuntimeError('Falha simulada ao escrever áudio no dispositivo')
        def close(self):self.closed=True
    monkeypatch.setattr(playback.tempfile,'TemporaryDirectory',CheckedDirectory)
    session=PlaybackSession(movie,cut(0.,3.),RenderOptions(),[],audio_track=movie.audio[0]['index'],
                            audio_factory=WriteErrorSink,max_size=80,fps=10)
    session.start()
    try:
        deadline=time.monotonic()+5
        while not session.finished and time.monotonic()<deadline:
            session.read_frame();time.sleep(.005)
        session.thread.join(timeout=1)
        assert session.finished and not session.thread.is_alive()
        assert outputs and outputs[0].wrote and outputs[0].closed
        assert observations==[(True,True)]
        assert 'escrever áudio' in session.error,'A limpeza mascarou a falha original de áudio.'
        assert session.process.poll() is not None and session.process.stdout.closed
    finally:session.stop()
