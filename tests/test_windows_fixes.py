import errno
import json
import os
from pathlib import Path
import sys
import threading
import wave

import pytest

from radar import filmcraft, runtime
from radar.export import export_clip, publish_file
from radar.media import Cancelled, executable, probe, run
from radar.model import Cut


def test_export_works_when_hard_links_are_unsupported(tmp_path, monkeypatch):
    video=tmp_path/'source.mp4'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=25:d=3','-c:v','libx264',video])
    def unsupported(*a):raise OSError(errno.ENOTSUP, 'Sem suporte a hard links')
    monkeypatch.setattr(os,'link',unsupported)
    output=export_clip(probe(video),Cut(1,.4,2.4,50,'Teste','Teste'),tmp_path/'clip.mp4')
    assert probe(output).duration==pytest.approx(2,abs=.05)
    with pytest.raises(FileExistsError):
        export_clip(probe(video),Cut(1,.4,2.4,50,'Teste','Teste'),output)
    original=video.read_bytes()
    with pytest.raises(ValueError):
        export_clip(probe(video),Cut(1,.4,2.4,50,'Teste','Teste'),video,overwrite=True)
    assert video.read_bytes()==original
    output=export_clip(probe(video),Cut(1,.4,1.4,50,'Teste','Teste'),output,overwrite=True)
    assert probe(output).duration==pytest.approx(1,abs=.05)


def test_copy_fallback_never_removes_an_existing_file(tmp_path,monkeypatch):
    temp=tmp_path/'temporary';temp.write_bytes(b'new')
    target=tmp_path/'existing';target.write_bytes(b'keep')
    monkeypatch.setattr(os,'link',lambda *a: (_ for _ in ()).throw(OSError(errno.ENOTSUP,'Unsupported')))
    with pytest.raises(FileExistsError):publish_file(temp,target)
    assert target.read_bytes()==b'keep'
    cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled):publish_file(temp,tmp_path/'cancelled',cancel)
    assert not (tmp_path/'cancelled').exists()


def test_selecting_desktop_and_persisting_portable_cli(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder=tmp_path/'Portable FilmCraft'
    folder.mkdir()
    desktop=folder/'filmcraft.exe';desktop.touch()
    cli=folder/'filmcraft-cli.exe';cli.touch()
    assert filmcraft.cli_from_selection(desktop)==str(cli)
    assert filmcraft.cli_from_selection(folder)==str(cli)
    from radar.settings import save_filmcraft
    save_filmcraft(cli)
    monkeypatch.delenv('FILMCRAFT_CLI',raising=False)
    assert filmcraft.locate_cli()==str(cli)
    cli.unlink()
    monkeypatch.setattr(filmcraft.shutil,'which',lambda *a:None)
    monkeypatch.setattr(filmcraft,'registry_installations',lambda:[])
    assert filmcraft.cli_from_selection(desktop) is None


def test_external_commands_restore_original_environment(tmp_path,monkeypatch):
    root=tmp_path/'bundle';root.mkdir()
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'_MEIPASS',str(root),raising=False)
    monkeypatch.setenv('LD_LIBRARY_PATH',str(root))
    monkeypatch.setenv('LD_LIBRARY_PATH_ORIG','/original-libs')
    monkeypatch.setenv('PATH',str(root/'libs')+os.pathsep+'/system-bin')
    captured={}
    monkeypatch.setattr(runtime.subprocess,'Popen',lambda args,**opts:captured.update(opts) or object())
    runtime.start_process(['program'])
    assert captured['env']['LD_LIBRARY_PATH']=='/original-libs'
    assert str(root/'libs') not in captured['env']['PATH']
    assert os.environ['LD_LIBRARY_PATH']==str(root)


def test_failed_and_timed_out_commands_report_the_tool():
    with pytest.raises(RuntimeError,match='0x00000007'):
        run([sys.executable,'-c','import sys; sys.exit(7)'])
    with pytest.raises(RuntimeError,match='não respondeu'):
        run([sys.executable,'-c','import time; time.sleep(20)'],timeout=.2)


def test_repeated_and_individual_filmcraft_jobs(tmp_path):
    cli=os.environ.get('FILMCRAFT_CLI')
    if not cli:pytest.skip('Requer CLI FilmCraft real')
    source=tmp_path/'partida ação.mp4'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=25:d=8',
         '-f','lavfi','-i','sine=frequency=440:duration=8','-c:v','libx264','-c:a','aac',source])
    media=probe(source)
    cuts=[Cut(i+1,a,b,50,f'Short {i+1}','Teste') for i,(a,b) in enumerate([(0,2),(2.4,4.4),(5.2,7.2)])]
    folder=tmp_path/'saída de projetos'
    grouped=filmcraft.create_projects(media,cuts,folder,cli=cli)
    assert len(grouped)==1 and grouped[0].is_file()
    saved=grouped[0].read_bytes()
    individual=filmcraft.create_projects(media,cuts,folder,individual=True,cli=cli)
    assert len(individual)==3 and all(f.is_file() for f in individual)
    assert grouped[0].parent!=individual[0].parent
    assert grouped[0].read_bytes()==saved
    for project,cut in zip(individual,cuts):
        data=json.loads(project.read_text(encoding='utf-8'))['project']['items']
        seqs=[item['kind']['Sequence'] for item in data.values() if 'Sequence' in item['kind']]
        assert len(seqs)==1
        clip=seqs[0]['video_tracks'][0]['items'][0]
        assert clip['source_in']/254016000000==pytest.approx(cut.start)
        assert clip['duration']/254016000000==pytest.approx(cut.duration)
        run([cli,'--project',project,'inspect','project'])
    interchange=filmcraft.create_projects(media,cuts,folder,cli=False)
    assert len(interchange)==3 and all(f.suffix=='.otio' for f in interchange)


def test_manual_chatgpt_review_preserves_times_without_exporting_private_paths():
    from radar.model import Media
    from radar.review import review_prompt
    m=Media('/private/username/secret-gameplay.mp4',300,1920,1080,30,'h264',0,[],0)
    text=review_prompt(m,[Cut(1,90.12,115.24,55,'Olha isso','Aumento sonoro','Consegui!')])
    assert '/private/' not in text and 'secret-gameplay' not in text
    assert '00:01:30.120' in text and '00:01:55.240' in text
    assert 'cite as fontes' in text and 'não uma probabilidade' in text
