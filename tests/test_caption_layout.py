"""Caption studio format controls and continuous embedded playback on real Tk."""
import os
from pathlib import Path
import time

import pytest

from radar.captions import generate_track
from radar.media import executable,probe,run
from radar.model import Cut
from radar.projects import load_project
from radar.render import MODES

pytestmark=pytest.mark.skipif(os.name!='nt' and not os.environ.get('DISPLAY'),reason='Requer display Tk')


@pytest.fixture(scope='module')
def source(tmp_path_factory):
    path=tmp_path_factory.mktemp('caption-layout')/'jogo legendado.mkv'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i',
         "color=red:s=160x90:r=25:d=11,drawbox=x=80:y=0:w=80:h=90:color=blue:t=fill",
         '-c:v','libx264','-preset','ultrafast',path])
    return path


@pytest.fixture
def studio(source,tmp_path,monkeypatch):
    from radar.gui import App
    monkeypatch.chdir(tmp_path);app=App();errors=[]
    monkeypatch.setattr(app,'error',lambda exc:errors.append(str(exc)))
    app.loaded(probe(source));clip=Cut(1,0.,10.,0,'Vídeo Cefas','Edição local',manual=True)
    app.speech=[{'start':.5,'end':2.,'text':'CEFAS TESTE','words':[]}]
    clip.captions=generate_track(clip,app.speech);app.cuts=[clip];app.refresh()
    app.table.selection_set('1');app.show_page('captions');app.update()
    app.caption_monitor.set('Sem áudio')
    def wait(predicate,timeout=10):
        deadline=time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:
            app.update();time.sleep(.005)
        app.update();assert predicate(),'Operação Tk não atingiu o estado esperado.'
        assert not errors,errors
    def finish():wait(lambda:not app.busy)
    yield app,errors,wait,finish
    if not app._closing:app.close()
    monkeypatch.undo()
    import gc;gc.collect()


def test_format_tab_presets_crop_preview_and_project_roundtrip(studio,tmp_path,monkeypatch):
    from radar.desktop_studio import filedialog
    app,errors,wait,finish=studio
    assert 'Vídeo e layout' in [app.caption_tabs.tab(i,'text') for i in app.caption_tabs.tabs()]
    page=next(i for i in app.caption_tabs.tabs() if app.caption_tabs.tab(i,'text')=='Vídeo e layout')
    app.caption_tabs.select(page);app.geometry('1000x620');app.update()
    app.caption_layout_preset_buttons['vertical_blur'].invoke();finish()
    assert app.render_mode_label.get()==MODES['vertical_blur']
    assert app._caption_image and app._caption_image.height()>app._caption_image.width()
    app.caption_layout_preset_buttons['vertical_crop'].invoke();finish()
    app.render_vars['crop_x'].set('0,25');app.render_vars['crop_y'].set('0.75')
    assert app.caption_crop_scales['crop_x'].get()==pytest.approx(.25)
    app.caption_layout_apply_button.invoke();finish()
    assert app.cuts[0].framing=={'crop_x':.25,'crop_y':.75}
    project=tmp_path/'layout.radar.json'
    monkeypatch.setattr(filedialog,'asksaveasfilename',lambda **kw:str(project))
    app.save_studio_project();finish()
    loaded=load_project(project)
    assert loaded['cuts'][0].framing=={'crop_x':.25,'crop_y':.75}
    assert loaded['render'].mode=='vertical_crop'
    app.caption_reset_layout();finish()
    assert app.cuts[0].framing=={'crop_x':.5,'crop_y':.5}
    app.render_vars['crop_x'].set('incompleto');app.update()
    assert not errors  # typing an incomplete coordinate must not break Tcl
    app.render_vars['crop_x'].set('.5')


def test_canvas_player_passes_six_seconds_pause_resume_seek_navigation_close(studio,monkeypatch):
    import radar.desktop_captions as desktop
    app,errors,wait,finish=studio
    def forbidden(*args,**kwargs):raise AssertionError('Player recorreu à exportação MP4/FFplay externo')
    monkeypatch.setattr(desktop,'export_clip',forbidden)
    monkeypatch.setattr(desktop,'start_process',forbidden)
    app.caption_play();player=app._caption_player
    assert player is not None and not app.busy
    wait(lambda:app.caption_cursor.get()>6.2,timeout=12)
    assert app._caption_image and app._caption_image.width()>0
    assert app.caption_preview_canvas.find_all() and player.max_queued_frames<=6
    app.caption_play();frozen=player.position
    wait(lambda:player.pause_event.is_set())
    until=time.monotonic()+.2
    while time.monotonic()<until:app.update();time.sleep(.005)
    assert app.caption_cursor.get()==pytest.approx(frozen,abs=.03)
    app.caption_play();wait(lambda:app.caption_cursor.get()>frozen+.15)
    app.caption_seek('7.2');assert player.finished and not player.thread.is_alive()
    # The debounced still preview after scrubbing must not stop a new play.
    app.caption_play();seeked=app._caption_player
    wait(lambda:app.caption_cursor.get()>7.7,timeout=5)
    assert app._caption_player is seeked and seeked.relative==pytest.approx(7.2)
    app.show_page('dashboard');app.update()
    assert app._caption_player is None and seeked.finished and not seeked.thread.is_alive()
    app.show_page('captions');app.caption_monitor.set('Sem áudio');app.caption_play();closing=app._caption_player
    wait(lambda:closing.ready,timeout=5)
    app.close()
    assert closing.finished and not closing.thread.is_alive() and not errors
    assert not list(Path.cwd().glob('*.mp4'))
