"""Incremental JSON cache: atomic records per stage/batch in the existing cache."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


SCHEMA=1
STAGES={'identify':'Identificação do arquivo','extract':'Extração de áudio','audio':'Análise de áudio','visual':'Análise visual','transcription':'Transcrição opcional','fusion':'Fusão dos sinais','classification':'Classificação e limites','export':'Exportação'}


def signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def source_identity(path):
    path=Path(path).resolve(strict=True)
    stat=path.stat()
    with path.open('rb') as stream:
        head=stream.read(1024*1024)
        stream.seek(max(0,stat.st_size-1024*1024))
        tail=stream.read(1024*1024)
    return {'path':str(path),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,
            'sample_sha256':hashlib.sha256(head+tail).hexdigest()}


def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='checkpoint-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            json.dump(data,out,ensure_ascii=False,allow_nan=False)
            out.flush();os.fsync(out.fileno())
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)


def read_json(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return None


class StageError(RuntimeError):
    def __init__(self,stage,detail,job_dir):
        self.stage=stage;self.detail=str(detail);self.job_dir=Path(job_dir)
        super().__init__(f'Etapa que falhou: {STAGES.get(stage,stage)}.\n{detail}\n\nCheckpoints preservados em: {job_dir}')


class CheckpointStore:
    def __init__(self,path,cache_dir='temporarios'):
        self.source=source_identity(path)
        self.source_id=signature(self.source)
        self.folder=Path(cache_dir).resolve()/'jobs'/self.source_id
        self.folder.mkdir(parents=True,exist_ok=True)
        self.manifest_path=self.folder/'manifest.json'
        old=read_json(self.manifest_path)
        self.manifest=old if isinstance(old,dict) and old.get('schema')==SCHEMA and old.get('source')==self.source else {
            'schema':SCHEMA,'source_id':self.source_id,'source':self.source,'stages':{}}
        self.active=None
        self._lock_file=None

    def acquire(self):
        stream=(self.folder/'job.lock').open('a+b')
        try:
            if not stream.tell():stream.write(b'0');stream.flush()
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            stream.close()
            raise RuntimeError('Outra instância está processando este arquivo. Aguarde sua conclusão para usar os mesmos checkpoints.') from None
        self._lock_file=stream
        for pattern in ('checkpoint-*.tmp','*.part.wav'):
            for unfinished in self.folder.rglob(pattern):unfinished.unlink(missing_ok=True)
        latest=read_json(self.manifest_path)
        if isinstance(latest,dict) and latest.get('source')==self.source and latest.get('schema')==SCHEMA:self.manifest=latest

    def release(self):
        if self._lock_file is None:return
        try:
            self._lock_file.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self._lock_file.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self._lock_file.fileno(),fcntl.LOCK_UN)
        finally:self._lock_file.close();self._lock_file=None

    def validate_source(self):
        if source_identity(self.source['path'])!=self.source:
            raise RuntimeError('O original mudou durante o processamento. Selecione o arquivo novamente; seus checkpoints anteriores permanecem separados.')

    def save_manifest(self):
        self.manifest['updated_at']=time.time()
        atomic_json(self.manifest_path,self.manifest)

    def start(self,stage,key,total):
        self.active=stage
        self.manifest['status']='running'
        self.manifest['current_stage']=stage
        self.manifest['stages'][stage]={'key':key,'status':'running','done':0,'total':total}
        self.save_manifest()

    def mark(self,stage,done,total,status='running',error=None):
        row=self.manifest['stages'].setdefault(stage,{})
        row.update(done=done,total=total,status=status)
        if error:row['error']=str(error)[:6000]
        else:row.pop('error',None)
        self.save_manifest()

    def location(self,stage,key,index=0):
        return self.folder/stage/key/f'{index:06}.json'

    def load(self,stage,key,index=0):
        record=read_json(self.location(stage,key,index))
        if not isinstance(record,dict) or record.get('schema')!=SCHEMA or record.get('key')!=key:return None
        data=record.get('data')
        try:valid=record.get('sha256')==signature(data)
        except (ValueError,TypeError):valid=False
        return data if valid else None

    def save(self,stage,key,data,index=0):
        self.validate_source()
        atomic_json(self.location(stage,key,index),{'schema':SCHEMA,'key':key,'sha256':signature(data),'data':data})

    def interrupted(self,status,error=None):
        self.manifest['status']=status
        if self.active:
            self.manifest['stages'].setdefault(self.active,{})['status']=status
            if error:self.manifest['stages'][self.active]['error']=str(error)[:6000]
        self.save_manifest()


def latest_request(path,cache_dir='temporarios'):
    try:
        identity=source_identity(path)
        record=read_json(Path(cache_dir)/'jobs'/signature(identity)/'manifest.json')
        return record if isinstance(record,dict) and record.get('schema')==SCHEMA and record.get('source')==identity else None
    except OSError:return None


def recent_jobs(cache_dir='temporarios',limit=8):
    folder=Path(cache_dir)/'jobs'
    if not folder.is_dir():return []
    results=[]
    paths=sorted(folder.glob('*/manifest.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True)[:limit]
    for item in paths:
        row=read_json(item)
        if isinstance(row,dict) and row.get('schema')==SCHEMA:results.append(row)
    return sorted(results,key=lambda r:r.get('updated_at',0),reverse=True)[:limit]
