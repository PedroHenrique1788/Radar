"""Official CLI + OpenTimelineIO; no mouse automation or invented native format."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import socket
import tempfile
from datetime import datetime
from fractions import Fraction
from .export import safe_destination
from .media import run, executable
from .runtime import start_process
from .settings import read_settings


def cli_from_selection(path):
    """Accept the desktop EXE, CLI or portable folder; never run desktop --help."""
    if not path:
        return None
    path = Path(os.path.expandvars(str(path).strip('"'))).expanduser()
    names = ('filmcraft-cli.exe', 'filmcraft-cli')
    if path.is_file() and path.name.lower() in names:
        return str(path.resolve())
    folder = path if path.is_dir() else path.parent
    for directory in (folder, folder/'bin'):
        for name in names:
            candidate = directory/name
            if candidate.is_file():
                return str(candidate.resolve())
    return None


def registry_installations():
    if os.name != 'nt':
        return []
    import winreg
    paths = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            for key, value in ((r'Software\Microsoft\Windows\CurrentVersion\App Paths\filmcraft.exe', ''),
                               (r'Software\FilmCraft', 'InstallDir')):
                try:
                    with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as opened:
                        paths.append(winreg.QueryValueEx(opened, value)[0])
                except OSError:
                    pass
    return paths


def locate_cli():
    candidates = [os.environ.get('FILMCRAFT_CLI'), read_settings().get('filmcraft_cli'),
                  shutil.which('filmcraft-cli'), *registry_installations()]
    for base in ('LOCALAPPDATA', 'ProgramFiles', 'ProgramFiles(x86)'):
        folder = os.environ.get(base)
        if folder:
            paths = ('Programs/ArtCraft/FilmCraft', 'Programs/FilmCraft', 'ArtCraft/FilmCraft', 'FilmCraft')
            candidates.extend(Path(folder)/p for p in paths)
    for candidate in candidates:
        cli = cli_from_selection(candidate)
        if cli:
            return cli
    return None


def capabilities(cli):
    cli = cli_from_selection(cli)
    if not cli:
        raise RuntimeError('filmcraft-cli não localizado. Selecione filmcraft.exe ou filmcraft-cli.exe na pasta de instalação do FilmCraft.')
    help_text = run([cli, '--help'], timeout=20)
    if '--save-as' not in help_text or 'import' not in help_text:
        raise RuntimeError('Esta versão da CLI não oferece importação e --save-as.')
    # Read actual command parameter schemas before modifying a new project.
    schema = json.loads(run([cli, 'describe', 'file.import'], timeout=20))
    if schema.get('id') != 'file.import' or 'paths' not in str(schema.get('params')):
        raise RuntimeError('Esquema de importação incompatível.')
    settings = json.loads(run([cli, 'describe', 'sequence.settings'], timeout=20))
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
                 '-t', media.duration, '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', '-rf64', 'auto', path], cancel)
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


def create_projects(media, cuts, folder, individual=False, cli=None, cancel=None, progress=lambda *a: None):
    if not cuts:
        return []
    for cut in cuts:
        cut.validate(media.duration)
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    cli = locate_cli() if cli is None else cli
    if cli:
        cli = capabilities(cli)['cli']
    # Every click creates a separate job; retrying never collides with an earlier
    # WAV or changes a user's existing project.
    folder = Path(tempfile.mkdtemp(prefix='Radar_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_', dir=folder))
    progress(5, 'Preparando faixas de áudio para o editor… Isso pode demorar em vídeos longos.')
    audio_paths = editor_audio(media, folder, 'Radar_fonte', cancel)
    groups = [[c] for c in cuts] if individual else [cuts]
    created = []
    for i, group in enumerate(groups, 1):
        if not group:
            continue
        progress(10 + 80 * (i-1)/len(groups), f'Criando projeto {i} de {len(groups)}…')
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
            try:
                run([cli, '--save-as', native, 'run', script], cancel, timeout=300)
            except RuntimeError as exc:
                raise RuntimeError(f'FilmCraft não conseguiu criar o projeto nativo. As timelines OTIO foram preservadas em:\n{folder}\n\n{exc}') from exc
            if not native.is_file() or not native.stat().st_size:
                raise RuntimeError('A CLI não salvou o projeto solicitado.')
            # Reopen and inspect to verify deserialization, rather than trust exit status alone.
            info = json.loads(run([cli, '--project', native, 'inspect', 'project'], cancel, timeout=60))
            if not info:
                raise RuntimeError('Projeto reaberto sem conteúdo.')
            status = json.loads(run([cli, '--project', native, 'exec', 'media.status'], cancel, timeout=60))
            offline = [m.get('name', '?') for m in status if m.get('status') not in ('online', 'generated')]
            if offline:
                raise RuntimeError(f'O FilmCraft não conseguiu ler estas mídias: {", ".join(offline)}. Os arquivos foram preservados em {folder}. Exporte um MP4 pelo Radar e teste sua importação no editor.')
            created.append(native)
        else:
            created.extend(paths)
    progress(100, f'Concluído: {len(created)} arquivos em {folder}')
    return created


def open_project(path, cli=None):
    path = Path(path).resolve(strict=True)
    cli = cli or locate_cli()
    if cli:
        desktop = Path(cli).with_name('filmcraft.exe' if os.name == 'nt' else 'filmcraft')
        if desktop.exists():
            start_process([str(desktop), str(path)], cwd=str(desktop.parent))
            return
    if os.name == 'nt':
        os.startfile(str(path))
    else:
        raise RuntimeError('Aplicativo desktop não localizado. Abra o arquivo pelo FilmCraft.')
