"""Comparable cold/warm local runs; sampled parent+child RSS/CPU/I/O, not promises."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import platform
import threading
import time

import psutil

from .checkpoints import source_identity
from .control import ExecutionControl
from .export import safe_destination,publish_file
from .media import probe,run,executable
from .preedit_pipeline import analyze_preedit
from .profiles import AnalysisOptions


def disk_bytes(folder):
    return sum(p.stat().st_size for p in Path(folder).rglob('*') if p.is_file())


def benchmark(path,cache,options=None):
    opts=AnalysisOptions.from_record(options);control=ExecutionControl(opts)
    peak=0;cpu={};reads={};writes={};stop=threading.Event();process=psutil.Process()
    def sample():
        nonlocal peak
        while not stop.is_set():
            rss=0
            try:family=[process,*process.children(recursive=True)]
            except psutil.Error:family=[process]
            for p in family:
                try:
                    rss+=p.memory_info().rss;t=p.cpu_times();io=p.io_counters()
                    cpu[p.pid]=t.user+t.system;reads[p.pid]=io.read_bytes;writes[p.pid]=io.write_bytes
                except psutil.Error:pass
            peak=max(peak,rss);stop.wait(.05)
    before_cpu=process.cpu_times();before_io=process.io_counters();before_disk=disk_bytes(cache)
    started=time.perf_counter();worker=threading.Thread(target=sample,daemon=True);worker.start()
    try:
        media=probe(path,control);edit=analyze_preedit(media,analysis=opts,cache_dir=cache,cancel=control)
    finally:
        elapsed=time.perf_counter()-started;stop.set();worker.join()
    return {'seconds':elapsed,'peak_rss_bytes_sampled':peak,'sample_interval_seconds':.05,
            'cpu_seconds_sampled':max(0,sum(cpu.values())-before_cpu.user-before_cpu.system),
            'read_bytes_sampled':max(0,sum(reads.values())-before_io.read_bytes),
            'write_bytes_sampled':max(0,sum(writes.values())-before_io.write_bytes),
            'cache_growth_bytes':disk_bytes(cache)-before_disk,'suggestions':len(edit.suggestions),
            'original_seconds':media.duration,'accepted_removals':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('video');parser.add_argument('--cache',required=True,help='Pasta de cache nova, não será apagada')
    parser.add_argument('--output',required=True);parser.add_argument('--batch-seconds',type=int,default=300);parser.add_argument('--threads',type=int,default=2)
    args=parser.parse_args();cache=Path(args.cache)
    if cache.exists() and any(cache.iterdir()):parser.error('Use cache vazio para separar execução fria e quente sem apagar dados existentes.')
    target=safe_destination(args.output,args.video);opts=AnalysisOptions(batch_seconds=args.batch_seconds,threads=args.threads)
    data={'source':source_identity(args.video),'platform':platform.platform(),'cpu':platform.processor(),'logical_cpus':psutil.cpu_count(),
          'ram_bytes':psutil.virtual_memory().total,'options':opts.record(),'ffmpeg':run([executable('ffmpeg'),'-version']).splitlines()[0],
          'limitations':'Amostragem pode perder subprocessos muito curtos; não mede qualidade editorial. Mesmo processo e configurações nas duas execuções.'}
    data['cold']=benchmark(args.video,cache,opts);data['warm']=benchmark(args.video,cache,opts)
    from .checkpoints import atomic_json
    import tempfile
    with tempfile.TemporaryDirectory(dir=target.parent,prefix='benchmark-') as tmp:
        stage=Path(tmp)/'report.json';atomic_json(stage,data);publish_file(stage,target)
    print(json.dumps(data,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
