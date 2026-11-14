import csv
import json
import os
import re
from pathlib import Path
import tempfile
from .media import executable, run, check_cancel, probe,Cancelled
from .model import timestamp
from .checkpoints import CheckpointStore,StageError,signature,source_identity
from .control import ExecutionControl,current_control
from .render import RenderOptions,PRESETS,video_filters,write_ass,for_cut,require_libass
from .captions import entries_for_cut,generate_track


def verify_source(media):
    if media.source_id and signature(source_identity(media.path))!=media.source_id:
        raise ValueError('O arquivo original mudou desde a análise. Analise novamente antes de exportar estes limites.')


def safe_destination(path, source=None, overwrite=False):
    path = Path(path).resolve()
    if source and path == Path(source).resolve():
        raise ValueError('Não é permitido sobrescrever o vídeo original.')
    if path.exists() and (not overwrite or not path.is_file()):
        raise FileExistsError('O destino já existe. Escolha outro nome para preservar o arquivo.')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def preserved_audio_codec(audio):
    if audio.get('codec') in ('aac','mp3','alac','opus','flac','ac3','eac3'):return 'copy'
    sample=audio.get('sample_format','')
    if sample.startswith('flt'):return 'pcm_f32le'
    if sample.startswith('dbl'):return 'pcm_f64le'
    if sample.startswith('s64'):return 'pcm_s64le'
    if sample.startswith('s32') and not 0<audio.get('bits',0)<=24:return 'pcm_s32le'
    return 'alac'


def export_clip(media, cut, path, cancel=None, overwrite=False,progress=None,*,render_options=None,speech=None,preview_size=None):
    verify_source(media)
    cut.validate(media.duration)
    rendering=for_cut(render_options,cut)
    if cut.captions:
        from .captions import validate_track
        validate_track(cut.captions,media.duration)
    burn=cut.captions['enabled'] if cut.captions else rendering.burn_subtitles
    entries=effective_subtitle_entries(cut,speech or []) if burn else []
    if burn and not entries:
        if cut.captions:raise ValueError('As legendas estão ativadas, mas este Short não tem blocos no intervalo. Gere/adicione legendas ou desative-as no Estúdio de Legendas.')
        raise ValueError('Ative uma transcrição com tiny/base e confira as falas antes de gravar legendas neste corte.')
    if burn:require_libass()
    path = safe_destination(path, media.path, overwrite)
    absolute_start, absolute_end = media.origin + cut.start, media.origin + cut.end
    size=None
    if preview_size is not None:
        w,h=rendering.dimensions(media);ratio=min(1,preview_size/max(w,h))
        size=max(2,round(w*ratio/2)*2),max(2,round(h*ratio/2)*2)
    filters = [f'[0:{media.video_index}]trim=start={absolute_start}:end={absolute_end},setpts=PTS-({absolute_start})/TB[base]',
               video_filters('[base]',media,rendering,subtitles=burn,size_override=size)]
    args = [executable('ffmpeg'), '-v', 'error', '-nostdin', '-n', '-copyts']
    # Seek near the cut, retaining original PTS; do not decode hours of footage
    # just to export a late Short. Absolute seeking also handles nonzero origins.
    normal_origin = abs(media.origin) < 1e-6 and all(a['start_time'] >= 0 for a in media.audio)
    seek = max(0, cut.start - 2) if normal_origin else 0
    if seek > 0:
        args += ['-seek_timestamp', '1', '-ss', seek]
    args += ['-i', media.path]
    preserve_audio=bool(cut.captions and cut.captions.get('preserve_audio',True))
    audio=media.audio
    if preserve_audio and any('sample_format' not in a for a in audio):audio=probe(media.path,cancel).audio
    codecs=[preserved_audio_codec(a) if preserve_audio else 'aac' for a in audio]
    if 'copy' in codecs:
        # A separate seeked input preserves encoded packets. Timestamp offset
        # and the MP4 edit list retain leading silence and AAC priming samples.
        args+=['-seek_timestamp','1','-ss',absolute_start,'-itsoffset',-absolute_start,'-i',media.path]
    for i,a in enumerate(audio):
        if codecs[i]=='copy':continue
        filters.append(f"[0:{a['index']}]atrim=start={absolute_start}:end={absolute_end},asetpts=PTS-({absolute_start})/TB,aresample=async=1:first_pts=0,apad,atrim=duration={cut.duration}[a{i}]")
    args += ['-filter_complex', ';'.join(filters), '-map', '[v]']
    for i,a in enumerate(audio):
        args += ['-map', f'1:{a["index"]}' if codecs[i]=='copy' else f'[a{i}]']
    # Re-encode: trim on presentation timestamps, never keyframe-only stream copy.
    quality,speed=PRESETS[rendering.preset]
    args += ['-c:v', 'libx264', '-preset', speed, '-crf', quality, '-pix_fmt', 'yuv420p', '-fps_mode', 'vfr',
             '-movflags', '+faststart', '-t', cut.duration]
    for i,codec in enumerate(codecs):
        args += [f'-c:a:{i}',codec]
        if codec=='alac':args += [f'-sample_fmt:a:{i}','s32p']
    fd, tmp = tempfile.mkstemp(suffix='.mp4', dir=path.parent)
    os.close(fd)
    Path(tmp).unlink()
    try:
        with tempfile.TemporaryDirectory(prefix='radar-render-') as workdir:
            if burn:write_ass(Path(workdir)/'captions.ass',entries,cut,*rendering.dimensions(media))
            run(args + [tmp],cancel,progress=progress,duration=cut.duration,cwd=workdir)
        try:
            probe(tmp)
        except (ValueError, RuntimeError) as exc:
            raise RuntimeError('FFmpeg não gerou vídeo no intervalo escolhido. Revise os limites do corte.') from exc
        publish_file(Path(tmp), path, cancel, overwrite)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return path



def publish_file(temporary, destination, cancel=None, overwrite=False):
    """Preserve no-clobber semantics on exFAT/FAT32/network shares too."""
    check_cancel(cancel)
    if overwrite:
        os.replace(temporary, destination)
        return
    try:
        os.link(temporary, destination)
        return
    except FileExistsError:
        raise
    except OSError:
        pass  # The filesystem may not implement hard links.
    created = False
    try:
        with Path(destination).open('xb') as out, Path(temporary).open('rb') as source:
            created = True
            while True:
                check_cancel(cancel)
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    except BaseException:
        if created:
            Path(destination).unlink(missing_ok=True)
        raise

def export_report(media, cuts, path,speech=None):
    verify_source(media)
    cuts=list(cuts)
    path = safe_destination(path, media.path)
    records = [c.record(media) for c in cuts]
    if speech is not None:
        for cut,record in zip(cuts,records):record['transcript']=' '.join(entry['text'] for entry in transcript_entries(cut,speech)[0])
    with path.open('x', encoding='utf-8-sig' if path.suffix.lower() == '.csv' else 'utf-8', newline='') as f:
        if path.suffix.lower() == '.csv':
            fields = ['id', 'title', 'start_time', 'end_time', 'duration', 'score', 'category', 'reason', 'transcript', 'editing','favorite','review_state','manual','user_edited','source_id','source','analysis_audio_path','analysis_audio_offset','analysis_audio_role']
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            # Prevent spreadsheet formulas when transcript/title start with = + - @.
            for record in records:
                record.update(analysis_audio_path=media.analysis_audio.get('path',''),analysis_audio_offset=media.analysis_audio.get('offset',0),analysis_audio_role=media.analysis_audio.get('role',''))
                writer.writerow({k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v) for k, v in record.items()})
        else:
            json.dump({'source': media.path,'source_id':media.source_id,'analysis_audio':media.analysis_audio, 'time_reference': 'seconds from first original video frame',
                       'notice': 'Pontuação heurística; não é probabilidade de viralização.', 'cuts': records}, f, ensure_ascii=False, indent=2)
    return path


def _file_hash(path,cancel):
    import hashlib
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while True:
            check_cancel(cancel)
            data=stream.read(1024*1024)
            if not data:break
            digest.update(data)
    return digest.hexdigest()


def export_clips(media,cuts,folder,cancel=None,cache_dir='temporarios',progress=lambda *a:None,options=None,*,render_options=None,speech=None):
    """Sequential MP4 queue; resume only verified, committed files, never clobber."""
    verify_source(media)
    cuts=list(cuts)
    if not cuts:raise ValueError('Selecione pelo menos um corte para a fila.')
    for cut in cuts:cut.validate(media.duration)
    cuts.sort(key=lambda cut:(cut.start,cut.end,cut.id))
    rendering=RenderOptions.from_record(render_options)
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    control=cancel if isinstance(cancel,ExecutionControl) else ExecutionControl(options,cancel)
    store=CheckpointStore(media.path,cache_dir);store.acquire()
    key=signature(['mp4-queue-v1',store.source_id,str(folder),[(c.id,c.start,c.end) for c in cuts]])
    if any(c.captions for c in cuts):
        key=signature(['mp4-queue-v3-captions',key,rendering.record(),[c.framing for c in cuts],
                       [c.captions for c in cuts],[effective_subtitle_entries(c,speech or []) for c in cuts]])
    elif rendering.record()!=RenderOptions().record():
        captions=[subtitle_entries(c,speech or []) for c in cuts] if rendering.burn_subtitles else None
        key=signature(['mp4-queue-v2-render',key,rendering.record(),[c.framing for c in cuts],captions])
    total=sum(c.duration for c in cuts);done=0.;outputs=[]
    stem=re.sub(r'[^\w.-]+','_',Path(media.path).stem)[:40] or 'gameplay'
    try:
        with control.bind():
            store.start('export',key,len(cuts))
            store.manifest['export_request']={'directory':str(folder),'cuts':[c.record(media) for c in cuts],'render_options':rendering.record()}
            store.save_manifest()
            for index,cut in enumerate(cuts):
                check_cancel(control)
                control.report('Exportação',done,total,'s',candidates=len(cuts))
                row=store.load('export',key,index)
                previous=Path(row['path']) if isinstance(row,dict) and isinstance(row.get('path'),str) else None
                progress(None,f'Conferindo clipe {index+1}/{len(cuts)} e seu checkpoint…')
                if previous is not None and previous.parent==folder and previous.is_file() and previous.stat().st_size==row.get('size') and _file_hash(previous,control)==row.get('sha256'):
                    output=previous
                else:
                    base=f'{stem}_{store.source_id[:8]}_corte_{cut.id:03}_{round(cut.start*1000):09}_{round(cut.end*1000):09}'
                    output=folder/(base+'.mp4');version=1
                    while output.exists():
                        version+=1;output=folder/f'{base}_v{version}.mp4'
                    def encoded(seconds):
                        control.report('Exportação',done+seconds,total,'s',candidates=len(cuts))
                        progress(100*(done+seconds)/total,f'Exportando clipe {index+1}/{len(cuts)}…')
                    export_clip(media,cut,output,control,progress=encoded,render_options=rendering,speech=speech)
                    progress(None,f'Validando integridade do clipe {index+1}/{len(cuts)}…')
                    store.save('export',key,{'path':str(output),'size':output.stat().st_size,'sha256':_file_hash(output,control)},index)
                outputs.append(output);done+=cut.duration
                store.mark('export',index+1,len(cuts),'complete' if index+1==len(cuts) else 'running')
                control.report('Exportação',done,total,'s',candidates=len(cuts))
                progress(100*done/total,f'{index+1}/{len(cuts)} clipes concluídos e verificados')
            store.manifest['status']='complete';store.save_manifest()
            return outputs
    except (KeyboardInterrupt,Cancelled):
        store.interrupted('cancelled');raise
    except Exception as exc:
        store.interrupted('failed',exc)
        raise StageError('export',str(exc),store.folder) from exc
    finally:store.release()


def export_srt(cut, speech, path):
    path = safe_destination(path)
    lines = []
    for entry in effective_subtitle_entries(cut,speech,include_disabled=True):
        start,end=entry['start']-cut.start,entry['end']-cut.start
        lines.append(f'{len(lines)+1}\n{timestamp(start).replace(".", ",")} --> {timestamp(end).replace(".", ",")}\n{entry["text"]}\n')
    if not lines:
        raise ValueError('Não há fala transcrita neste intervalo.')
    path.write_text('\n'.join(lines), encoding='utf-8')
    return path


def effective_subtitle_entries(cut,speech,*,include_disabled=False):
    return entries_for_cut(cut,include_disabled=include_disabled) if cut.captions else subtitle_entries(cut,speech)


def export_ass(cut,speech,path,*,width=720,height=1280):
    entries=entries_for_cut(cut,cut.captions or generate_track(cut,speech),include_disabled=True)
    if not entries:raise ValueError('Não há legendas neste intervalo. Gere ou adicione um bloco no Estúdio de Legendas.')
    path=safe_destination(path)
    # Generate into a temporary file, then publish with no-clobber semantics.
    with tempfile.TemporaryDirectory(prefix='radar-ass-') as tmp:
        file=write_ass(Path(tmp)/'captions.ass',entries,cut,width,height)
        publish_file(file,path)
    return path


def subtitle_entries(cut,speech):
    """Short readable cues using word times, never proportional invented times."""
    result=[]
    for segment in speech:
        if segment['end']<=cut.start or segment['start']>=cut.end:continue
        words=segment.get('words')
        if not words:
            result.extend(transcript_entries(cut,[segment])[0]);continue
        group=[];length=0
        def flush():
            if not group:return
            text=re.sub(r'\s+([,.;:!?])',r'\1',' '.join(w['word'].strip() for w in group))
            result.append({'start':max(cut.start,group[0]['start']),'end':min(cut.end,group[-1]['end']),'text':text})
        for word in words:
            if word['end']<=cut.start or word['start']>=cut.end or not word['word'].strip():continue
            if group and (length+len(word['word'])>60 or word['end']-group[0]['start']>4. or word['start']-group[-1]['end']>.65):
                flush();group=[];length=0
            group.append(word);length+=len(word['word'])+1
        flush()
    return sorted(result,key=lambda e:e['start'])


def transcript_entries(cut, speech):
    """Select original-time words, never stale candidate text after an edit."""
    entries=[]
    omitted=0
    partial_words=False
    for segment in speech:
        if segment['end'] <= cut.start or segment['start'] >= cut.end:
            continue
        if segment.get('words'):
            words=[w for w in segment['words'] if w['end'] > cut.start and w['start'] < cut.end]
            if not words:
                continue
            text=' '.join(w['word'].strip() for w in words).strip()
            text=re.sub(r'\s+([,.;:!?])', r'\1', text)
            start=max(cut.start,min(w['start'] for w in words))
            end=min(cut.end,max(w['end'] for w in words))
            partial_words |= any(w['start'] < cut.start or w['end'] > cut.end for w in words)
        elif segment['start'] >= cut.start and segment['end'] <= cut.end:
            start,end,text=segment['start'],segment['end'],segment['text'].strip()
        else:
            # Without word times, including the whole sentence could leak speech
            # from outside the requested cut. Explain the omission instead.
            omitted+=1
            continue
        if text and end > start:
            entries.append({'start':start,'end':end,'text':text})
    return entries,omitted,partial_words


def export_transcript(cut, speech, path):
    cut.validate(cut.end)
    entries,omitted,partial=transcript_entries(cut,speech)
    if not entries:
        if omitted:
            raise ValueError('Há fala sobreposta ao corte, mas faltam tempos por palavra para isolá-la. Amplie os limites ou refaça a transcrição com timestamps por palavra.')
        raise ValueError('Este corte não tem fala transcrita. Analise o vídeo com tiny, base ou small antes de exportar a transcrição.')
    path=safe_destination(path)
    lines=[f'Corte {cut.id:02} — {cut.title}',
           f'Início no original: {timestamp(cut.start)}', f'Fim no original: {timestamp(cut.end)}',
           f'Duração: {cut.duration:.3f} segundos', 'Horários abaixo relativos ao vídeo original.', '']
    if omitted:
        lines.append('Observação: segmentos que cruzam os limites e não têm tempos por palavra foram omitidos.')
    if partial:
        lines.append('Observação: há palavras parcialmente sobrepostas aos limites. Revise o áudio nas bordas do corte.')
    lines += [f"[{timestamp(e['start'])} --> {timestamp(e['end'])}] {e['text']}" for e in entries]
    with path.open('x',encoding='utf-8') as out:
        out.write('\n'.join(lines)+'\n')
    return path
