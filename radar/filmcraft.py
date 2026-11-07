"""Official CLI + OpenTimelineIO; no mouse automation or invented native format."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import socket
from fractions import Fraction
from .export import safe_destination
from .media import run, executable


def locate_cli():
    candidates = [os.environ.get('FILMCRAFT_CLI'), shutil.which('filmcraft-cli')]
    for base in ('LOCALAPPDATA', 'ProgramFiles', 'ProgramFiles(x86)'):
        folder = os.environ.get(base)
        if folder:
            candidates.append(str(Path(folder) / ('Programs/ArtCraft/FilmCraft' if base == 'LOCALAPPDATA' else 'ArtCraft/FilmCraft') / 'filmcraft-cli.exe'))
    return next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()), None)


def capabilities(cli):
    help_text = run([cli, '--help'])
    if '--save-as' not in help_text or 'import' not in help_text:
        raise RuntimeError('Esta versão da CLI não oferece importação e --save-as.')
    # Read actual command parameter schemas before modifying a new project.
    schema = json.loads(run([cli, 'describe', 'file.import']))
    if schema.get('id') != 'file.import' or 'paths' not in str(schema.get('params')):
        raise RuntimeError('Esquema de importação incompatível.')
    settings = json.loads(run([cli, 'describe', 'sequence.settings']))
    if not all(key in str(settings.get('params')) for key in ('width', 'height', 'name', 'fps')):
        raise RuntimeError('Esquema de sequência incompatível.')
    return {'cli': cli, 'import_schema': schema, 'settings_schema': settings}


def local_control(method, params=None, port=9876):
    """Read-only connection check; editing uses isolated CLI sessions instead."""
    if method not in ('engine.commands', 'ui.inspect'):
        raise ValueError('Esta conexão só permite inspeção; crie projetos novos pela CLI.')
    token = os.environ.get('FILMCRAFT_CONTROL_TOKEN', '')
    if len(token) != 64 or any(c not in '0123456789abcdefABCDEF' for c in token):
        raise RuntimeError('Token local de controle ausente ou inválido; use a CLI headless.')
    with socket.create_connection(('127.0.0.1', port), timeout=10) as sock:
        sock.sendall((json.dumps({'id': 1, 'token': token, 'method': method, 'params': params or {}}) + '\n').encode())
        with sock.makefile('rb') as f:
            reply = json.loads(f.readline(4 * 1024 * 1024))
    if not reply.get('ok'):
        raise RuntimeError('FilmCraft recusou a inspeção. Verifique a sessão e o token local.')
    return reply['result']


def editor_audio(media, folder, prefix, cancel=None):
    """PCM sidecars preserve every OBS track, stereo layout and its source delay."""
    paths = []
    for audio in media.audio:
        path = safe_destination(Path(folder) / f"{prefix}_audio_{audio['index']}.wav", media.path)
        try:
            run([executable('ffmpeg'), '-v', 'error', '-nostdin', '-n', '-copyts', '-i', media.path,
                 '-map', f"0:{audio['index']}", '-af',
                 f'asetpts=PTS-({media.origin})/TB,aresample=48000:async=1:first_pts=0,apad',
                 '-t', media.duration, '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', path], cancel)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        paths.append(path)
    return paths


def export_otio(media, cuts, path, audio_paths=None, cancel=None):
    import opentimelineio as otio
    path = safe_destination(path, media.path)
    if audio_paths is None:
        audio_paths = editor_audio(media, path.parent, path.stem, cancel)
    timeline = otio.schema.Timeline(name=cuts[0].title if len(cuts) == 1 else path.stem)
    rate = media.fps
    refs = [(otio.schema.Track(name='Vídeo', kind=otio.schema.TrackKind.Video), Path(media.path))]
    refs += [(otio.schema.Track(name=f"Áudio OBS {a['index']}", kind=otio.schema.TrackKind.Audio), p)
             for a, p in zip(media.audio, audio_paths)]
    rt, tr = otio.opentime.RationalTime, otio.opentime.TimeRange
    for cut in cuts:
        cut.validate(media.duration)
        for track, source in refs:
            ref = otio.schema.ExternalReference(target_url=source.resolve().as_uri(),
                available_range=tr(rt(0, rate), rt(media.duration * rate, rate)))
            clip = otio.schema.Clip(name=cut.title, media_reference=ref,
                source_range=tr(rt(cut.start * rate, rate), rt(cut.duration * rate, rate)))
            clip.metadata['radar'] = {'original_start_seconds': cut.start, 'original_end_seconds': cut.end,
                                      'source': media.path, 'score': cut.score}
            track.append(clip)
    for track, _ in refs:
        timeline.tracks.append(track)
    fraction = Fraction(rate).limit_denominator(100000)
    # Documented metadata extension supported by FilmCraft's official OTIO importer.
    timeline.metadata['filmcraft'] = {'settings': {
        'width': media.width, 'height': media.height, 'frame_rate': {'num': fraction.numerator, 'den': fraction.denominator},
        'par': [1, 1], 'sample_rate': 48000, 'drop_frame': False, 'preset': 'Radar original', 'audio_master': 'Stereo',
        'preview_codec': 'ProRes 422', 'max_bit_depth': False, 'max_render_quality': False, 'working_space': 'Rec. 709'}}
    timeline.metadata['radar'] = {'warning': 'Áudios OBS em WAVs auxiliares sincronizados. Preserve os WAVs junto ao projeto. Em VFR revise limites no editor.'}
    otio.adapters.write_to_file(timeline, str(path))
    return path


def create_projects(media, cuts, folder, individual=False, cli=None, cancel=None):
    if not cuts:
        return []
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    cli = cli or locate_cli()
    if cli:
        capabilities(cli)
    audio_paths = editor_audio(media, folder, 'Radar_fonte', cancel)
    groups = [[c] for c in cuts] if individual else [cuts]
    created = []
    for i, group in enumerate(groups, 1):
        if not group:
            continue
        name = f'Short_{group[0].id:02}' if individual else 'Radar_todos'
        # A common project contains a separately named sequence for every Short.
        # Each OTIO Timeline imports as one native sequence.
        paths = []
        for cut in group:
            paths.append(export_otio(media, [cut], folder / f'{name}_corte_{cut.id:02}.otio', audio_paths, cancel))
        if cli:
            native = safe_destination(folder / f'{name}.fcproj', media.path)
            script = safe_destination(folder / f'{name}.jsonl')
            steps = []
            for cut, timeline in zip(group, paths):
                steps += [{'id': 'file.import', 'params': {'paths': [str(timeline)]}},
                          {'id': 'sequence.settings', 'params': {'width': media.width, 'height': media.height,
                           'fps': media.fps, 'name': cut.title}}]
            script.write_text('\n'.join(json.dumps(step, ensure_ascii=False) for step in steps), encoding='utf-8')
            run([cli, '--save-as', native, 'run', script], cancel)
            if not native.is_file() or not native.stat().st_size:
                raise RuntimeError('A CLI não salvou o projeto solicitado.')
            # Reopen and inspect to verify deserialization, rather than trust exit status alone.
            info = json.loads(run([cli, '--project', native, 'inspect', 'project'], cancel))
            if not info:
                raise RuntimeError('Projeto reaberto sem conteúdo.')
            created.append(native)
        else:
            created.extend(paths)
    return created


def open_project(path, cli=None):
    path = Path(path).resolve(strict=True)
    cli = cli or locate_cli()
    if cli:
        desktop = Path(cli).with_name('filmcraft.exe' if os.name == 'nt' else 'filmcraft')
        if desktop.exists():
            subprocess.Popen([str(desktop), str(path)])
            return
    if os.name == 'nt':
        os.startfile(str(path))
    else:
        raise RuntimeError('Aplicativo desktop não localizado. Abra o arquivo pelo FilmCraft.')
