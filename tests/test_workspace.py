"""Studio navigation, real thumbnails, filtering and export selection."""
from dataclasses import replace
from pathlib import Path
import os
import time

import av
import pytest

from radar.captions import generate_track,CaptionStyle,set_style
from radar.library import find_cuts,thumbnail
from radar.media import run,executable,probe
from radar.model import Cut
from radar.render import RenderOptions


def clips():
    return [Cut(1,.4,2.4,80,'Vitória azul','Teste',transcript='Conseguimos vencer',favorite=True,review_state='approved'),
            Cut(2,4,6,60,'Reação no jogo','Teste',transcript='Olha isso'),
            Cut(3,8,10,0,'Corte manual','Teste',manual=True,review_state='rejected')]


@pytest.fixture(scope='module')
def movie(tmp_path_factory):
    path=tmp_path_factory.mktemp('workspace-media')/'partida de teste.mp4'
    run([executable('ffmpeg'),'-v','error','-f','lavfi','-i',
         "color=red:s=320x180:r=25:d=12,drawbox=x=0:y=0:w=iw:h=ih:color=blue:t=fill:enable='gte(t,6)'",
         '-f','lavfi','-i','sine=frequency=440:duration=12','-c:v','libx264','-c:a','aac',path])
    return path


def test_library_searches_speech_and_titles_ignoring_accents_with_human_filters():
    rows=clips()
    assert [c.id for c in find_cuts(rows,'vitoria VENCER')]==[1]
    assert [c.id for c in find_cuts(rows,'olha')]==[2]
    assert [c.id for c in find_cuts(rows,state='Favoritos')]==[1]
    assert [c.id for c in find_cuts(rows,state='Aprovados')]==[1]
    assert [c.id for c in find_cuts(rows,state='Pendentes')]==[2]
    assert [c.id for c in find_cuts(rows,state='Descartados')]==[3]
    assert find_cuts(rows,'inexistente')==[]
    assert rows[0].title=='Vitória azul'


def test_library_ranks_real_editorial_scores_and_finds_saved_captions():
    rows=clips();rows[1].captions=generate_track(rows[1],[{'start':4.2,'end':5.8,'text':'Olha isso','words':[]}])
    assert [c.id for c in find_cuts(rows,state='Com legendas')]==[2]
    rows[1].captions['enabled']=False
    assert [c.id for c in find_cuts(rows,state='Com legendas')]==[2]
    reviews={2:{'nota_editorial':99,'titulo':'Uma jogada incrível'}}
    assert find_cuts(rows,'incrivel',reviews=reviews)==[rows[1]]
    assert [c.id for c in find_cuts(rows,order='Por potencial',reviews=reviews)]==[2,1,3]


def test_thumbnails_are_real_cut_frames_and_reuse_cache_after_caption_edits(movie,tmp_path,monkeypatch):
    import radar.library as library
    media=probe(movie);rows=clips();options=RenderOptions()
    files=[thumbnail(media,c,options,tmp_path) for c in (rows[0],rows[2])]
    colors=[]
    for file in files:
        with av.open(str(file)) as image:colors.append(next(image.decode(video=0)).to_ndarray(format='rgb24').mean(axis=(0,1)))
    assert colors[0][0]>200 and colors[0][2]<30
    assert colors[1][2]>200 and colors[1][0]<30
    original=files[0].read_bytes()
    rows[0].captions=generate_track(rows[0],[{'start':.8,'end':1.8,'text':'Nova legenda','words':[]}])
    rows[0].captions=set_style(rows[0].captions,CaptionStyle(effect='pop'))
    def unexpected(*a,**kw):raise AssertionError('Reprocessou miniatura sem mudança de vídeo/enquadramento')
    monkeypatch.setattr(library,'frame',unexpected)
    assert thumbnail(media,rows[0],options,tmp_path)==files[0] and files[0].read_bytes()==original


@pytest.fixture
def gui_cleanup(monkeypatch):
    yield
    monkeypatch.undo()
    import gc
    gc.collect()


pytestmark_gui=pytest.mark.skipif(os.name!='nt' and not os.environ.get('DISPLAY'),reason='Requer display X11')


@pytestmark_gui
def test_dashboard_library_filters_pagination_actions_and_actual_batch_export(movie,tmp_path,monkeypatch,gui_cleanup):
    from radar.gui import App
    from radar import gui
    monkeypatch.chdir(tmp_path);app=App();errors=[]
    monkeypatch.setattr(app,'error',lambda exc:errors.append(str(exc)))
    monkeypatch.setattr(gui.messagebox,'showinfo',lambda *a,**kw:None)
    def finish():
        deadline=time.monotonic()+30
        while (app.busy or app._library_after is not None) and time.monotonic()<deadline:app.update();time.sleep(.02)
        app.update();assert not app.busy and not errors,errors
    try:
        assert app.current_page=='dashboard' and app.workflow_mode=='radar'
        app.loaded(probe(movie));app.cuts=clips()+[replace(clips()[0],id=i,title=f'Clipe {i}',favorite=False,start=8.+(i-3)*.2,end=10.+(i-3)*.2) for i in range(4,8)]
        app.refresh();app.show_page('dashboard');app.update()
        assert app.dashboard_stats['cuts'].get()=='7' and app.dashboard_stats['favorites'].get()=='1'
        app.show_page('library');finish()
        assert set(app._library_cards)==set(range(1,7))
        app._library_vars[1].set(True);app.library_select(1)
        app.library_page(1);finish();assert set(app._library_cards)=={7}
        app._library_vars[7].set(True);app.library_select(7)
        assert app.library_selected=={1,7}
        app.library_filter.set('Favoritos');finish();assert set(app._library_cards)=={1}
        assert app.library_selected=={1,7}
        app.library_query.set('vitoria');finish();assert set(app._library_cards)=={1}
        app.library_thumbnails();finish();assert 1 in app._library_photo_images
        assert any('quadros dos clipes' in message for _,message in app._activity_rows)
        assert app._activity_rows[-1][1].startswith('Concluído')
        app.library_target(1,'favorite');finish()
        assert not app.cuts[0].favorite and app.dashboard_stats['favorites'].get()=='0'
        app.library_filter.set('Todos');app.library_query.set('');finish()
        app.library_target(2,'captions');finish()
        assert app.current_page=='captions' and app._caption_cut_id==2
        app.show_page('library');finish()
        folder=tmp_path/'selecionados';folder.mkdir()
        monkeypatch.setattr(gui.filedialog,'askdirectory',lambda **kw:str(folder))
        app.review_filter.set('Pendentes');app.refresh()
        app.library_export_selected();finish()
        outputs=list(folder.glob('*.mp4'));assert len(outputs)==2
        assert all(probe(path).duration==pytest.approx(2.,abs=.05) for path in outputs)
        app.show_page('jobs');app.update();assert app.activity_table.get_children()
        assert app.workspace_jobs.get_children()  # export queue checkpoint
        app.update_runtime();assert 'GB' in app.workspace_disk.get()
        app.loaded(probe(movie));finish()
        assert not app.library_selected and not app._library_images
    finally:app.close()


@pytestmark_gui
def test_recent_projects_reopen_from_dashboard_and_library_thumbnails_invalidate_on_trim(movie,tmp_path,monkeypatch,gui_cleanup):
    from radar.gui import App
    from radar import gui
    monkeypatch.chdir(tmp_path);app=App();errors=[]
    monkeypatch.setattr(app,'error',lambda exc:errors.append(str(exc)))
    project=tmp_path/'meu.radar.json'
    monkeypatch.setattr(gui.filedialog,'asksaveasfilename',lambda **kw:str(project))
    def finish():
        deadline=time.monotonic()+30
        while (app.busy or app._library_after is not None) and time.monotonic()<deadline:app.update();time.sleep(.02)
        app.update();assert not app.busy and not errors,errors
    try:
        app.loaded(probe(movie));app.cuts=clips();app.refresh();app.show_page('library');finish()
        app.library_thumbnails();finish();assert set(app._library_photo_images)=={1,2,3}
        app.cuts[0].start=.8;app.refresh_library();assert 1 not in app._library_photo_images
        app.save_studio_project();finish()
        app.show_page('dashboard');app.dashboard_projects.selection_set('0');app.dashboard_open_recent();finish()
        assert app.current_page=='review' and app.cuts[0].start==.8
        assert app.project_path==str(project)
        app.geometry('1000x620');app.show_page('library');finish()
        assert app.library_search.winfo_rootx()+app.library_search.winfo_width()<=app.winfo_rootx()+app.winfo_width()
        for page in ('dashboard','jobs','review','captions'):
            app.show_page(page);app.update()
            for button in app._nav_buttons.values():
                assert button.winfo_rooty()+button.winfo_height()<=app.winfo_rooty()+app.winfo_height()-35
    finally:app.close()
