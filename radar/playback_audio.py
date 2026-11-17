"""Small native PCM output for the embedded preview (no new Python dependency).

Only signed 16-bit interleaved PCM is accepted. ``write`` runs on the decoder
worker and blocks at a small queue limit; ``position`` is the consumed audio
clock. Controls can be called from the Tk thread. No Tk objects cross threads.
"""
import ctypes as C
import ctypes.util
import errno
import os
import threading
import time


class AudioOutputError(RuntimeError):
    pass


class PauseUnavailable(AudioOutputError):
    """The device was stopped; restart decoding at ``position`` to resume."""
    def __init__(self,position):
        self.position=position
        super().__init__('Este dispositivo não oferece pausa nativa. Reinicie a reprodução no cursor preservado.')


class AudioOutputStopped(AudioOutputError):
    pass


_U32=C.c_uint32
_UPTR=C.c_size_t


class _WaveFormat(C.Structure):
    _pack_=1
    _fields_=[('tag',C.c_uint16),('channels',C.c_uint16),('rate',_U32),
              ('bytes_per_second',_U32),('block_align',C.c_uint16),
              ('bits',C.c_uint16),('extra',C.c_uint16)]


class _WaveHeader(C.Structure):
    pass


_WaveHeader._fields_=[('data',C.c_void_p),('length',_U32),('recorded',_U32),
                      ('user',_UPTR),('flags',_U32),('loops',_U32),
                      ('next',C.POINTER(_WaveHeader)),('reserved',_UPTR)]


class _TimeValue(C.Union):
    _fields_=[('samples',_U32),('milliseconds',_U32),('bytes',_U32),('padding',C.c_ubyte*8)]


class _MMTime(C.Structure):
    _fields_=[('kind',_U32),('value',_TimeValue)]


# If a device refuses to release a prepared native buffer, retain its storage
# rather than free memory still owned by the driver. This is an exceptional
# shutdown path, never the normal lifecycle.
_retained=[]


def _stopped(stop):
    return bool(stop is not None and stop.is_set())


def _wait(stop):
    if stop is None:time.sleep(.005)
    else:stop.wait(.005)


class _WaveOutput:
    def __init__(self,rate,channels,latency,api=None):
        self.rate=rate;self.channels=channels;self.frame_bytes=channels*2
        self.lock=threading.RLock();self.closed=False;self.paused=False
        self.buffers=[];self.written=0;self.last_counter=0;self.wraps=0;self.last_position=0.
        self.max_frames=max(1,round(rate*latency));self.chunk_frames=max(1,min(round(rate*.04),self.max_frames))
        self.api=api if api is not None else C.WinDLL('winmm.dll')
        signatures={
            'waveOutOpen':([C.POINTER(C.c_void_p),_U32,C.POINTER(_WaveFormat),_UPTR,_UPTR,_U32],_U32),
            'waveOutPrepareHeader':([C.c_void_p,C.POINTER(_WaveHeader),_U32],_U32),
            'waveOutWrite':([C.c_void_p,C.POINTER(_WaveHeader),_U32],_U32),
            'waveOutUnprepareHeader':([C.c_void_p,C.POINTER(_WaveHeader),_U32],_U32),
            'waveOutGetPosition':([C.c_void_p,C.POINTER(_MMTime),_U32],_U32),
            'waveOutPause':([C.c_void_p],_U32),'waveOutRestart':([C.c_void_p],_U32),
            'waveOutReset':([C.c_void_p],_U32),'waveOutClose':([C.c_void_p],_U32),
            'waveOutGetErrorTextW':([_U32,C.c_wchar_p,_U32],_U32)}
        for name,(args,result) in signatures.items():
            function=getattr(self.api,name);function.argtypes=args;function.restype=result
        self.handle=C.c_void_p()
        fmt=_WaveFormat(1,channels,rate,rate*self.frame_bytes,self.frame_bytes,16,0)
        self._check(self.api.waveOutOpen(C.byref(self.handle),0xFFFFFFFF,C.byref(fmt),0,0,0),'abrir a saída de áudio')

    def _check(self,code,action):
        if code:
            message=C.create_unicode_buffer(256)
            self.api.waveOutGetErrorTextW(code,message,len(message))
            raise AudioOutputError(f'Não foi possível {action}: {message.value or "erro do dispositivo"} (WinMM {code}). Verifique a saída de som do Windows.')

    def _cleanup(self):
        remaining=[]
        for buffer,header in self.buffers:
            if header.flags&1:
                result=self.api.waveOutUnprepareHeader(self.handle,C.byref(header),C.sizeof(header))
                if result==33:remaining.append((buffer,header))
                else:self._check(result,'liberar o buffer de áudio')
            else:remaining.append((buffer,header))
        self.buffers=remaining

    def _position(self):
        if self.closed:return self.last_position
        stamp=_MMTime();stamp.kind=2  # TIME_SAMPLES, one counter per PCM frame.
        self._check(self.api.waveOutGetPosition(self.handle,C.byref(stamp),C.sizeof(stamp)),'consultar o relógio do áudio')
        raw=int(stamp.value.samples)
        # Counters are 32-bit even in a 64-bit application.
        if raw<self.last_counter and self.last_counter-raw>0x80000000:self.wraps+=1
        self.last_counter=raw
        full=raw+self.wraps*(1<<32)
        if stamp.kind==2:position=full/self.rate
        elif stamp.kind==4:position=full/(self.rate*self.frame_bytes)
        elif stamp.kind==1:position=full/1000
        else:raise AudioOutputError('O driver de áudio retornou um relógio incompatível.')
        self.last_position=max(self.last_position,min(self.written/self.rate,position))
        return self.last_position

    @property
    def position(self):
        with self.lock:return self._position()

    def write(self,data,stop_event=None):
        for offset in range(0,len(data),self.chunk_frames*self.frame_bytes):
            chunk=data[offset:offset+self.chunk_frames*self.frame_bytes];frames=len(chunk)//self.frame_bytes
            while True:
                if _stopped(stop_event):raise AudioOutputStopped('Reprodução interrompida.')
                with self.lock:
                    if self.closed:raise AudioOutputStopped('Saída de áudio fechada.')
                    self._cleanup();queued=self.written-round(self._position()*self.rate)
                    if not self.paused and queued+frames<=self.max_frames:
                        buffer=C.create_string_buffer(chunk)
                        header=_WaveHeader();header.data=C.cast(buffer,C.c_void_p);header.length=len(chunk)
                        self._check(self.api.waveOutPrepareHeader(self.handle,C.byref(header),C.sizeof(header)),'preparar o áudio')
                        try:self._check(self.api.waveOutWrite(self.handle,C.byref(header),C.sizeof(header)),'reproduzir o áudio')
                        except BaseException:
                            self.api.waveOutUnprepareHeader(self.handle,C.byref(header),C.sizeof(header));raise
                        self.buffers.append((buffer,header));self.written+=frames
                        break
                _wait(stop_event)

    def pause(self):
        with self.lock:
            if self.closed:return
            if not self.paused:
                self._check(self.api.waveOutPause(self.handle),'pausar o áudio');self.paused=True

    def resume(self):
        with self.lock:
            if self.closed:return
            if self.paused:
                self._check(self.api.waveOutRestart(self.handle),'retomar o áudio');self.paused=False

    def close(self):
        with self.lock:
            if self.closed:return
            try:self._position()
            except AudioOutputError:pass  # Device removal must still release buffers.
            try:
                self._check(self.api.waveOutReset(self.handle),'parar o áudio')
                # Reset returns all pending buffers to the application.
                for buffer,header in self.buffers:
                    self._check(self.api.waveOutUnprepareHeader(self.handle,C.byref(header),C.sizeof(header)),'liberar o áudio')
                self.buffers.clear()
                self._check(self.api.waveOutClose(self.handle),'fechar o áudio')
            except BaseException:
                _retained.append(self);self.closed=True;raise
            self.closed=True


class _AlsaOutput:
    def __init__(self,rate,channels,latency,device='default',api=None):
        self.rate=rate;self.channels=channels;self.frame_bytes=channels*2
        self.lock=threading.RLock();self.closed=False;self.paused=False;self.restart_required=False
        self.software_pause=False;self.written=0;self.last_position=0.
        self.max_frames=max(1,round(rate*latency));self.chunk_frames=max(1,min(round(rate*.04),self.max_frames))
        library=C.util.find_library('asound')
        if api is None and not library:raise AudioOutputError('ALSA não está disponível. Instale o suporte de áudio do sistema para ouvir a prévia.')
        self.api=api if api is not None else C.CDLL(library)
        signatures={
            'snd_pcm_open':([C.POINTER(C.c_void_p),C.c_char_p,C.c_int,C.c_int],C.c_int),
            'snd_pcm_set_params':([C.c_void_p,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_int,C.c_uint],C.c_int),
            'snd_pcm_writei':([C.c_void_p,C.c_void_p,C.c_ulong],C.c_long),
            'snd_pcm_delay':([C.c_void_p,C.POINTER(C.c_long)],C.c_int),
            'snd_pcm_pause':([C.c_void_p,C.c_int],C.c_int),
            'snd_pcm_prepare':([C.c_void_p],C.c_int),'snd_pcm_drop':([C.c_void_p],C.c_int),
            'snd_pcm_recover':([C.c_void_p,C.c_int,C.c_int],C.c_int),
            'snd_pcm_close':([C.c_void_p],C.c_int),'snd_strerror':([C.c_int],C.c_char_p)}
        for name,(args,result) in signatures.items():
            function=getattr(self.api,name);function.argtypes=args;function.restype=result
        self.handle=C.c_void_p()
        self._check(self.api.snd_pcm_open(C.byref(self.handle),device.encode('utf-8'),0,1),'abrir a saída de áudio')
        try:
            # S16_LE, RW_INTERLEAVED, nonblocking output. No whole-video buffer.
            self._check(self.api.snd_pcm_set_params(self.handle,2,3,channels,rate,1,round(latency*1_000_000)),'configurar o áudio')
        except BaseException:self.api.snd_pcm_close(self.handle);self.closed=True;raise

    def _check(self,code,action):
        if code<0:
            detail=self.api.snd_strerror(code).decode('utf-8',errors='replace')
            raise AudioOutputError(f'Não foi possível {action}: {detail}. Verifique o dispositivo e o serviço de áudio do Linux.')
        return code

    def _position(self):
        if self.closed or self.restart_required:return self.last_position
        delay=C.c_long()
        result=self.api.snd_pcm_delay(self.handle,C.byref(delay))
        if result==-errno.EPIPE:
            # An underrun means the previously queued samples were consumed.
            self.last_position=max(self.last_position,self.written/self.rate)
            self._check(self.api.snd_pcm_recover(self.handle,result,1),'recuperar a saída de áudio')
            return self.last_position
        self._check(result,'consultar o relógio do áudio')
        self.last_position=max(self.last_position,min(self.written/self.rate,(self.written-max(0,delay.value))/self.rate))
        return self.last_position

    @property
    def position(self):
        with self.lock:return self._position()

    def write(self,data,stop_event=None):
        for offset in range(0,len(data),self.chunk_frames*self.frame_bytes):
            chunk=data[offset:offset+self.chunk_frames*self.frame_bytes];buffer=C.create_string_buffer(chunk)
            remaining=len(chunk)//self.frame_bytes;cursor=0
            while remaining:
                if _stopped(stop_event):raise AudioOutputStopped('Reprodução interrompida.')
                with self.lock:
                    if self.closed:raise AudioOutputStopped('Saída de áudio fechada.')
                    if self.restart_required:raise PauseUnavailable(self.last_position)
                    queued=self.written-round(self._position()*self.rate)
                    if self.paused or queued>=self.max_frames:
                        count=0
                    else:
                        allowed=min(remaining,max(1,self.max_frames-queued))
                        count=self.api.snd_pcm_writei(self.handle,C.cast(C.byref(buffer,cursor*self.frame_bytes),C.c_void_p),allowed)
                        if count==-errno.EPIPE:
                            self.last_position=max(self.last_position,self.written/self.rate)
                            self._check(self.api.snd_pcm_recover(self.handle,count,1),'recuperar a saída de áudio');count=0
                        elif count in (-errno.EAGAIN,-errno.EINTR):count=0
                        elif count<0:self._check(count,'reproduzir o áudio')
                        if count:
                            self.written+=count;cursor+=count;remaining-=count
                if not count:_wait(stop_event)

    def pause(self):
        with self.lock:
            if self.closed or self.paused:return
            position=self._position()
            if not self.written:
                self.software_pause=True;self.paused=True;return
            result=self.api.snd_pcm_pause(self.handle,1)
            if result<0:
                # Stop immediately, but never pretend that dropped queued audio
                # can be resumed. The controller must seek a fresh decoder.
                self._check(self.api.snd_pcm_drop(self.handle),'parar o áudio para pausar')
                self.last_position=position;self.restart_required=True;self.paused=True
                raise PauseUnavailable(position)
            self.paused=True

    def resume(self):
        with self.lock:
            if self.closed:return
            if self.restart_required:raise PauseUnavailable(self.last_position)
            if self.paused:
                if self.software_pause:self.software_pause=False
                else:self._check(self.api.snd_pcm_pause(self.handle,0),'retomar o áudio')
                self.paused=False

    def close(self):
        with self.lock:
            if self.closed:return
            try:
                if not self.restart_required:self._position()
            finally:
                self.api.snd_pcm_drop(self.handle)
                result=self.api.snd_pcm_close(self.handle);self.closed=True
            self._check(result,'fechar o áudio')


class AudioOutput:
    """Native signed16 PCM output; opening a missing device raises a clear error.

    ``latency`` bounds queued audio. Linux callers may choose an ALSA device;
    tests use its real ``null`` device explicitly rather than silently muting.
    """
    def __init__(self,rate=48000,channels=2,*,latency=.24,device=None):
        if isinstance(rate,bool) or not isinstance(rate,int) or not 8000<=rate<=192000:raise ValueError('Taxa de áudio inválida.')
        if isinstance(channels,bool) or channels not in (1,2):raise ValueError('Use áudio mono ou estéreo.')
        if isinstance(latency,bool) or not isinstance(latency,(int,float)) or not .04<=latency<=.5:raise ValueError('Latência de áudio inválida.')
        self.rate=rate;self.channels=channels
        if os.name=='nt':
            if device is not None:raise ValueError('A saída Windows usa o dispositivo de som padrão.')
            self._backend=_WaveOutput(rate,channels,latency)
        elif os.name=='posix':self._backend=_AlsaOutput(rate,channels,latency,device=device or 'default')
        else:raise AudioOutputError('Este sistema não oferece uma saída de áudio compatível com a prévia.')

    @property
    def position(self):return self._backend.position

    def write(self,data,stop_event=None):
        if not isinstance(data,(bytes,bytearray,memoryview)):raise ValueError('O áudio deve ser PCM em bytes.')
        if len(data)%(self.channels*2):raise ValueError('PCM incompleto: tamanho fora do alinhamento das amostras.')
        self._backend.write(bytes(data),stop_event)

    def pause(self):return self._backend.pause()
    def resume(self):return self._backend.resume()
    def close(self):return self._backend.close()
