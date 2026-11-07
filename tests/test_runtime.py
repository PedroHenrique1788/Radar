from pathlib import Path
import sys
from radar import runtime
from radar.media import executable


def test_installed_data_is_writable_and_separate(tmp_path, monkeypatch):
    before = Path.cwd()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path/'profile'))
    monkeypatch.delenv('HF_HOME', raising=False)
    folder = runtime.prepare_desktop()
    assert folder == tmp_path/'profile'/'RadarCortes'
    assert (folder/'temporarios').is_dir() and (folder/'resultados').is_dir()
    assert Path.cwd() == folder


def test_bundled_model_is_preferred(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    local = tmp_path/'models'/'tiny'
    local.mkdir(parents=True)
    (local/'model.bin').write_bytes(b'test')
    assert runtime.resolve_model('tiny') == str(local)
    assert runtime.resolve_model('base') == 'base'
    assert runtime.resolve_model('/custom/model') == '/custom/model'


def test_bundled_tools_and_explicit_override(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    (tmp_path/'ffmpeg').mkdir()
    name = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
    bundled = tmp_path/'ffmpeg'/name
    bundled.touch()
    monkeypatch.delenv('FFMPEG_PATH', raising=False)
    assert executable('ffmpeg') == str(bundled)
    override = tmp_path/'custom'/name
    override.parent.mkdir()
    override.touch()
    monkeypatch.setenv('FFMPEG_PATH', str(override))
    assert executable('ffmpeg') == str(override)
