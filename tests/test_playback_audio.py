"""Audio clocks and bounded native-buffer lifecycle, with explicit real null ALSA."""
import ctypes as C
import os
import threading
import time

import pytest

from radar.playback_audio import (AudioOutput,AudioOutputError,AudioOutputStopped,
    PauseUnavailable,_WaveOutput,_WaveHeader,_MMTime,_WaveFormat)


class Function:
    def __init__(self,call):self.call=call
    def __call__(self,*args):return self.call(*args)


class WaveDevice:
    """Deterministic WinMM driver boundary: tracks ownership and actual samples."""
    def __init__(self):
        self.headers=[];self.consumed=0;self.closed=False;self.paused=False;self.open_code=0;self.events=[]
        for name in ('Open','PrepareHeader','Write','UnprepareHeader','GetPosition','Pause','Restart','Reset','Close','GetErrorTextW'):
            setattr(self,'waveOut'+name,Function(getattr(self,name)))
    def Open(self,handle,device,fmt,*args):
        C.cast(handle,C.POINTER(C.c_void_p))[0]=123
        f=C.cast(fmt,C.POINTER(_WaveFormat)).contents
        assert f.rate==48000 and f.channels==2 and f.bits==16 and f.block_align==4
        return self.open_code
    def PrepareHeader(self,handle,pointer,size):self.events.append('prepare');return 0
    def Write(self,handle,pointer,size):
        self.events.append('write');self.headers.append(C.cast(pointer,C.POINTER(_WaveHeader)).contents);return 0
    def UnprepareHeader(self,handle,pointer,size):
        header=C.cast(pointer,C.POINTER(_WaveHeader)).contents
        self.events.append('unprepare')
        self.headers=[h for h in self.headers if C.addressof(h)!=C.addressof(header)]
        return 0
    def GetPosition(self,handle,pointer,size):
        stamp=C.cast(pointer,C.POINTER(_MMTime)).contents;stamp.kind=2;stamp.value.samples=self.consumed%(1<<32);return 0
    def Pause(self,handle):self.paused=True;self.events.append('pause');return 0
    def Restart(self,handle):self.paused=False;self.events.append('restart');return 0
    def Reset(self,handle):
        self.events.append('reset')
        for header in self.headers:header.flags|=1
        return 0
    def Close(self,handle):assert not self.headers;self.events.append('close');self.closed=True;return 0
    def GetErrorTextW(self,code,pointer,length):
        C.cast(pointer,C.POINTER(C.c_wchar*length)).contents.value='sem dispositivo';return 0
    def advance(self,frames):
        self.consumed+=frames
        budget=self.consumed
        for header in self.headers:
            if budget>=header.length//4:header.flags|=1;budget-=header.length//4
            else:break


def test_waveout_clock_tracks_consumed_samples_and_keeps_buffers_until_driver_done():
    api=WaveDevice();out=_WaveOutput(48000,2,.24,api=api)
    out.write(bytes(4800*4))
    assert out.position==0 and len(out.buffers)==3
    api.advance(1920);assert out.position==pytest.approx(.04)
    out.pause();assert api.paused;assert out.position==pytest.approx(.04)
    out.resume();assert not api.paused
    out.close();out.close()
    assert api.closed and not out.buffers
    assert api.events[-1]=='close' and api.events.index('reset')<api.events.index('close')
    assert out.position==pytest.approx(.04)


def test_waveout_queue_bound_and_stop_interrupt_blocked_writer():
    api=WaveDevice();out=_WaveOutput(48000,2,.08,api=api);stop=threading.Event();errors=[]
    def write():
        try:out.write(bytes(48000*4),stop)
        except BaseException as exc:errors.append(exc)
    worker=threading.Thread(target=write);worker.start()
    deadline=time.monotonic()+2
    while len(api.headers)<2 and time.monotonic()<deadline:time.sleep(.005)
    assert out.written==3840 and worker.is_alive()
    stop.set();worker.join(timeout=2)
    assert not worker.is_alive() and len(errors)==1 and isinstance(errors[0],AudioOutputStopped)
    out.close();assert not api.headers


def test_waveout_sample_counter_wrap_remains_monotonic():
    api=WaveDevice();out=_WaveOutput(48000,2,.24,api=api)
    out.written=(1<<32)+48000
    api.consumed=(1<<32)-100
    before=out.position
    api.consumed=(1<<32)+100
    assert out.position-before==pytest.approx(200/48000)
    out.close()


def test_missing_windows_device_has_clear_error_instead_of_silent_audio():
    api=WaveDevice();api.open_code=6
    with pytest.raises(AudioOutputError,match='WinMM 6'):_WaveOutput(48000,2,.24,api=api)


@pytest.mark.skipif(os.name!='posix',reason='ALSA é um backend Linux')
def test_real_alsa_null_consumption_close_and_explicit_pause_fallback():
    try:out=AudioOutput(device='null')
    except (AudioOutputError,OSError) as exc:pytest.skip(f'ALSA null indisponível: {exc}')
    try:
        out.pause();out.resume()  # Prepared output can pause before the first sample.
        out.write(bytes(4800*4));assert out.position==pytest.approx(.1,abs=.001)
        try:out.pause()
        except PauseUnavailable as exc:
            assert exc.position==pytest.approx(.1,abs=.001)
            with pytest.raises(PauseUnavailable):out.resume()
        else:out.resume()
    finally:out.close();out.close()
    assert out.position==pytest.approx(.1,abs=.001)


@pytest.mark.skipif(os.name!='posix',reason='ALSA é um backend Linux')
def test_real_missing_alsa_device_fails_explicitly():
    with pytest.raises(AudioOutputError,match='saída de áudio'):
        AudioOutput(device='radar_missing_device_for_test')


@pytest.mark.skipif(os.name!='posix',reason='ALSA é um backend Linux')
def test_cancelled_audio_never_writes_samples_and_pcm_alignment_is_checked():
    out=AudioOutput(device='null');stop=threading.Event();stop.set()
    try:
        with pytest.raises(AudioOutputStopped):out.write(bytes(1920),stop)
        assert out.position==0
        with pytest.raises(ValueError,match='alinhamento'):out.write(b'\x00')
    finally:out.close()


@pytest.mark.parametrize('options',[{'rate':0},{'rate':True},{'channels':3},{'latency':0},{'latency':float('nan')}])
def test_invalid_audio_configuration_is_rejected_before_opening_device(options):
    with pytest.raises(ValueError):AudioOutput(**options)
