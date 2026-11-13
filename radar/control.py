"""Cooperative task control and limits for processes owned by the Radar."""
from contextlib import contextmanager
from contextvars import ContextVar
import math
import os
import threading
import time

import psutil

from .profiles import AnalysisOptions


class Cancelled(Exception):
    pass


class ResourceLimitError(RuntimeError):
    pass


_current=ContextVar('radar_control',default=None)


def current_control(cancel=None):
    return cancel if isinstance(cancel,ExecutionControl) else _current.get()


class ExecutionControl:
    def __init__(self,options=None,cancel=None):
        self.cancel_event=cancel if cancel is not None else threading.Event()
        self.pause_event=threading.Event()
        self.lock=threading.RLock()
        self.processes={}
        self.suspended=set()
        self._cpu_by_pid={}
        self._finished_cpu=0.
        self._last_cpu=None
        self._last_sample=None
        self._last_budget=0.
        self.job_dir=None
        self.begin(options)

    def begin(self,options=None):
        self.options=AnalysisOptions.from_record(options)
        self.slots=threading.BoundedSemaphore(self.options.max_processes)
        self.started=time.monotonic()
        self._paused_seconds=0.
        self._pause_started=None
        self.stage='Preparando'
        self._stage_started=0.
        self.done=0.;self.total=None;self.unit='';self._initial_done=0.
        self.counts={}
        self._last_budget=0.
        self._finished_active=None

    def finish(self):
        self.resume()
        self._finished_active=self.active_time

    def is_set(self):return self.cancel_event.is_set()
    def wait(self,timeout=None):return self.cancel_event.wait(timeout)

    def clear(self):
        self.cancel_event.clear()
        self.resume()

    def set(self):
        self.cancel_event.set()
        self.resume()

    def pause(self):self.pause_event.set()

    def resume(self):
        self.pause_event.clear()
        with self.lock:
            for pid in list(self.suspended):
                process=self.processes.get(pid)
                if process is not None:
                    try:process.resume()
                    except psutil.Error:pass
            self.suspended.clear()
            if self._pause_started is not None:
                self._paused_seconds+=time.monotonic()-self._pause_started
                self._pause_started=None

    @property
    def active_time(self):
        if getattr(self,'_finished_active',None) is not None:return self._finished_active
        now=time.monotonic()
        with self.lock:
            paused=self._paused_seconds+(now-self._pause_started if self._pause_started is not None else 0)
        return max(0,now-self.started-paused)

    def checkpoint(self):
        if self.is_set():raise Cancelled('Operação cancelada; lotes concluídos foram preservados.')
        if self.pause_event.is_set():
            with self.lock:
                if self._pause_started is None:self._pause_started=time.monotonic()
                for pid,process in self.processes.items():
                    if pid not in self.suspended:
                        try:process.suspend();self.suspended.add(pid)
                        except psutil.Error:pass
            while self.pause_event.is_set() and not self.is_set():self.cancel_event.wait(.1)
            self.resume()
        if self.is_set():raise Cancelled('Operação cancelada; lotes concluídos foram preservados.')
        now=time.monotonic()
        if now-self._last_budget>=.5:
            self._last_budget=now
            rss=self.memory_bytes()
            if rss is not None and rss>self.options.memory_mb*1024*1024:
                raise ResourceLimitError(f'Limite de memória da tarefa atingido ({rss/1024**2:.0f} MB; limite {self.options.memory_mb} MB). Os checkpoints foram preservados. Aumente o limite ou desative módulos opcionais antes de retomar.')

    @contextmanager
    def bind(self):
        token=_current.set(self)
        try:yield self
        finally:_current.reset(token)

    def command(self,args):
        args=list(args)
        if os.path.basename(str(args[0])).lower() not in ('ffmpeg','ffmpeg.exe'):return args
        if any(str(a) in ('-version','-help','-h','-encoders','-decoders','-filters') for a in args):return args
        return [args[0],'-threads',self.options.threads,'-filter_threads','1','-filter_complex_threads','1',
                *args[1:-1],'-threads',self.options.threads,args[-1]]

    def register(self,popen):
        try:process=psutil.Process(popen.pid)
        except psutil.Error:return
        with self.lock:self.processes[popen.pid]=process

    def unregister(self,popen):
        with self.lock:
            process=self.processes.pop(popen.pid,None)
            if process is not None and popen.pid in self.suspended:
                try:process.resume()
                except psutil.Error:pass
            self.suspended.discard(popen.pid)
            self._finished_cpu+=self._cpu_by_pid.pop(popen.pid,0.)

    def memory_bytes(self):
        try:total=psutil.Process().memory_info().rss
        except psutil.Error:return None
        with self.lock:children=list(self.processes.values())
        for child in children:
            try:total+=child.memory_info().rss
            except psutil.Error:pass
        return total

    def report(self,stage,done=0,total=None,unit='',**counts):
        with self.lock:
            if stage!=self.stage:
                self.stage=stage;self._stage_started=self.active_time;self._initial_done=done
            self.done=done;self.total=total;self.unit=unit
            self.counts.update(counts)

    def snapshot(self):
        now=time.monotonic()
        with self.lock:
            try:
                cpu=psutil.Process().cpu_times()
                total_cpu=cpu.user+cpu.system+self._finished_cpu
                for pid,child in self.processes.items():
                    try:
                        value=child.cpu_times()
                        self._cpu_by_pid[pid]=value.user+value.system
                    except psutil.Error:pass
                    total_cpu+=self._cpu_by_pid.get(pid,0)
                percent=None if self._last_cpu is None else max(0,min(100,100*(total_cpu-self._last_cpu)/max(.001,now-self._last_sample)/(os.cpu_count() or 1)))
                self._last_cpu,self._last_sample=total_cpu,now
            except psutil.Error:percent=None
            elapsed=self.active_time
            stage_elapsed=max(0,elapsed-self._stage_started)
            delta=self.done-self._initial_done
            eta=stage_elapsed*(self.total-self.done)/delta if self.total is not None and delta>=3 and stage_elapsed>=1 and self.total>=self.done else None
            return {'stage':self.stage,'done':self.done,'total':self.total,'unit':self.unit,
                    'elapsed':elapsed,'eta':eta,'ram_bytes':self.memory_bytes(),'cpu_percent':percent,
                    'paused':self._pause_started is not None,'pause_requested':self.pause_event.is_set(),**self.counts}
