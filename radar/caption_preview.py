"""One libass frame at the cursor; editing never encodes the whole video."""
from pathlib import Path
import tempfile

from .checkpoints import signature
from .export import effective_subtitle_entries,verify_source
from .media import executable,run
from .render import for_cut,video_filters,write_ass,require_libass


def preview_key(media,cut,options,relative):
    from .checkpoints import source_identity
    return signature(['caption-preview-v1',source_identity(media.path),cut.start,cut.end,cut.framing,cut.captions,options.record(),round(relative,3)])


def frame(media,cut,options,speech,relative,path,cancel=None,*,max_size=640):
    verify_source(media);cut.validate(media.duration)
    options=for_cut(options,cut)
    relative=min(max(0.,float(relative)),max(0.,cut.duration-1/media.fps))
    absolute=media.origin+cut.start+relative
    w,h=options.dimensions(media);scale=min(1,max_size/max(w,h))
    preview=(max(2,round(w*scale/2)*2),max(2,round(h*scale/2)*2))
    burn=cut.captions['enabled'] if cut.captions else options.burn_subtitles
    entries=effective_subtitle_entries(cut,speech) if burn else []
    if entries:require_libass()
    # Keep clip-relative PTS until libass has sampled the animation. Reset only
    # for the final still image. Seek near the cursor, not from frame zero.
    filters=[f'[0:{media.video_index}]trim=start={absolute},setpts=PTS-({media.origin+cut.start})/TB[base]',
             video_filters('[base]',media,options,'styled',bool(entries),size_override=preview),
             '[styled]setpts=PTS-STARTPTS[image]']
    cmd=[executable('ffmpeg'),'-v','error','-nostdin','-y','-copyts']
    if absolute>media.origin+2:cmd+=['-seek_timestamp','1','-ss',absolute-2]
    path=Path(path)
    with tempfile.TemporaryDirectory(prefix='radar-caption-frame-') as work:
        if entries:write_ass(Path(work)/'captions.ass',entries,cut,w,h)
        run(cmd+['-i',media.path,'-filter_complex',';'.join(filters),'-map','[image]','-frames:v','1',path],cancel,timeout=40,cwd=work)
    return path
