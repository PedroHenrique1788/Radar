"""Library queries and thumbnails over Radar's existing cuts and preview service."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import unicodedata

from .checkpoints import signature,source_identity
from .caption_preview import frame
from .render import RenderOptions
from .media import check_cancel


FILTERS={'Todos':None,'Favoritos':'favorite','Aprovados':'approved','Pendentes':'pending','Descartados':'rejected','Com legendas':'captions'}


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c))


def find_cuts(cuts,query='',state='Todos',order='Por tempo',reviews=None):
    if state not in FILTERS:raise ValueError('Filtro de clipes inválido.')
    reviews=reviews or {};terms=normalized(query).split();result=[]
    for cut in cuts:
        condition=FILTERS[state]
        if condition=='favorite' and not cut.favorite:continue
        if condition in ('approved','pending','rejected') and cut.review_state!=condition:continue
        if condition=='captions' and not cut.captions.get('cues'):continue
        review=reviews.get(cut.id) or {}
        text=normalized(f'{cut.id} {cut.title} {cut.transcript} {cut.category} {review.get("titulo","")}')
        if all(term in text for term in terms):result.append(cut)
    if order=='Por potencial':result.sort(key=lambda c:(reviews.get(c.id,{}).get('nota_editorial',c.score),not c.manual,-c.start),reverse=True)
    elif order=='Maior duração':result.sort(key=lambda c:(-c.duration,c.start,c.id))
    elif order=='Por tempo':result.sort(key=lambda c:(c.start,c.id))
    else:raise ValueError('Ordenação de clipes inválida.')
    return result


def thumbnail(media,cut,options,folder,cancel=None):
    options=RenderOptions.from_record(options);options.burn_subtitles=False
    captions=deepcopy(cut.captions)
    if captions:captions['enabled']=False
    clean=replace(cut,captions=captions)
    key=signature(['library-thumbnail-v1',source_identity(media.path),cut.start,cut.end,cut.framing,options.record()])
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    output=folder/f'library-{key}.png'
    check_cancel(cancel)
    if not output.is_file():frame(media,clean,options,[],min(.5,cut.duration/2),output,cancel,max_size=256)
    return output
