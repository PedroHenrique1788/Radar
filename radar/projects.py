"""Versioned, atomic studio projects referencing originals, with no credentials."""
from dataclasses import asdict
from datetime import datetime,timezone
import json
import math
import os
from pathlib import Path

from .checkpoints import atomic_json,signature,source_identity
from .media import probe,check_cancel
from .model import Cut
from .profiles import AnalysisOptions
from .render import RenderOptions
from .render import for_cut
from .export import verify_source
from .captions import validate_track

MAX_PROJECT_BYTES=32*1024*1024


def validate_cuts(cuts,duration):
    if len(cuts)>2000:raise ValueError('Um projeto aceita até 2000 cortes.')
    ids=set()
    for cut in cuts:
        cut.validate(duration)
        if isinstance(cut.id,bool) or not isinstance(cut.id,int) or cut.id<=0 or cut.id in ids:raise ValueError('Identificadores de cortes inválidos ou duplicados.')
        ids.add(cut.id)
        if not all(isinstance(v,bool) for v in (cut.favorite,cut.manual,cut.user_edited)) or cut.review_state not in ('pending','approved','rejected'):
            raise ValueError('Classificação manual inválida.')
        for_cut(None,cut)
        if cut.captions:validate_track(cut.captions,duration)
        if isinstance(cut.score,bool) or not isinstance(cut.score,(int,float)) or not math.isfinite(cut.score) or not 0<=cut.score<=100:raise ValueError('Nota local inválida.')
        if not all(isinstance(s,str) and len(s)<=200000 for s in (cut.title,cut.reason,cut.transcript,cut.editing)):
            raise ValueError('Texto de corte inválido ou muito longo.')


def save_project(path,media,cuts,speech,*,analysis=None,render=None,title='',overwrite=False,cancel=None,request=None):
    check_cancel(cancel);verify_source(media)
    target=Path(path).resolve()
    if target==Path(media.path).resolve():raise ValueError('Não é permitido sobrescrever o vídeo original.')
    if target.suffix.lower()!='.json' or not target.name.endswith('.radar.json'):
        raise ValueError('Salve o projeto com extensão .radar.json.')
    if target.exists() and not overwrite:raise FileExistsError('O projeto já existe. Escolha outro nome ou salve uma nova versão.')
    cuts=list(cuts);validate_cuts(cuts,media.duration)
    payload={'kind':'cefas-radar-studio','version':2,'title':str(title or Path(media.path).stem)[:200],
             'saved_at':datetime.now(timezone.utc).isoformat(),'source':source_identity(media.path),
             'analysis_audio':dict(media.analysis_audio),'cuts':[asdict(c) for c in cuts],'speech':speech,
             'analysis_options':AnalysisOptions.from_record(analysis).record(),
             'render_options':RenderOptions.from_record(render).record(),
             'request':{k:v for k,v in (request or {}).items() if k in ('model','track','count','minimum','maximum')}}
    record={'payload':payload,'sha256':signature(payload)}
    if len(json.dumps(record,ensure_ascii=False).encode('utf-8'))>MAX_PROJECT_BYTES:raise ValueError('Projeto excede o limite de 32 MB. Divida a revisão em projetos menores.')
    check_cancel(cancel)
    # A no-clobber save publishes an atomic temporary project using the same
    # filesystem fallback as MP4. Explicit replacement also stays atomic.
    if overwrite:atomic_json(target,record)
    else:
        import tempfile
        from .export import publish_file
        target.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix='project-',suffix='.json',dir=target.parent)
        os.close(fd)
        try:
            atomic_json(tmp,record);publish_file(Path(tmp),target,cancel)
        finally:Path(tmp).unlink(missing_ok=True)
    return target


def load_project(path,cancel=None,*,source_override=None):
    path=Path(path).resolve(strict=True)
    if path.stat().st_size>MAX_PROJECT_BYTES:raise ValueError('Projeto excede o limite de 32 MB.')
    try:
        record=json.loads(path.read_text(encoding='utf-8-sig'));payload=record['payload']
        if record.get('sha256')!=signature(payload) or payload.get('kind')!='cefas-radar-studio' or payload.get('version') not in (1,2):
            raise ValueError('Formato, versão ou integridade do projeto inválidos.')
        source=payload['source'];actual=source_identity(source_override or source['path'])
        if source_override:
            if any(actual[k]!=source[k] for k in ('size','sample_sha256')):raise ValueError('O arquivo localizado não corresponde ao original do projeto.')
        elif actual!=source:raise ValueError('O vídeo original mudou desde que o projeto foi salvo. Revise o arquivo antes de continuar.')
        media=probe(actual['path'],cancel)
        media.analysis_audio=payload.get('analysis_audio',{})
        cuts=[Cut(**row) for row in payload['cuts']];validate_cuts(cuts,media.duration)
        speech=payload['speech']
        if not isinstance(speech,list):raise ValueError('Transcrição inválida no projeto.')
        for segment in speech:
            for unit in [segment,*(segment.get('words') or [])]:
                if not all(isinstance(unit.get(k),(int,float)) and math.isfinite(unit[k]) for k in ('start','end')) or not 0<=unit['start']<=unit['end']<=media.duration+.1:
                    raise ValueError('Horários da transcrição fora do vídeo.')
            if not isinstance(segment.get('text'),str):raise ValueError('Texto de transcrição inválido.')
            if any(not isinstance(w.get('word'),str) for w in segment.get('words',[])):raise ValueError('Palavras inválidas no projeto.')
        config=payload.get('analysis_options')
        if isinstance(config,dict):
            config=dict(config)
            if isinstance(config.get('threads'),int):config['threads']=min(config['threads'],max(1,min(16,os.cpu_count() or 1)))
        analysis=AnalysisOptions.from_record(config)
        render=RenderOptions.from_record(payload.get('render_options'))
    except FileNotFoundError:raise FileNotFoundError('Vídeo original não encontrado. Use Localizar vídeo ao abrir o projeto para reconectar o arquivo.') from None
    except (KeyError,TypeError,AttributeError,OverflowError,RecursionError):raise ValueError('O projeto contém campos inválidos ou incompatíveis.') from None
    return {'path':str(path),'title':payload.get('title',path.stem),'media':media,'cuts':cuts,'speech':speech,'analysis':analysis,'render':render,'request':payload.get('request',{})}
