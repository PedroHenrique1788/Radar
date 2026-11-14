"""Studio actions integrated into the existing desktop, without AI calls."""
from dataclasses import asdict
from pathlib import Path
import re
import tkinter as tk
from tkinter import filedialog

from .model import Cut,timestamp,parse_time
from .media import align_bounds,run,executable,check_cancel
from .render import RenderOptions,MODES,video_filters,for_cut
from .projects import save_project,load_project
from .waveform import build_waveform
from .export import transcript_entries
from .settings import save_settings

STATES={'Pendente':'pending','Aprovado':'approved','Descartado':'rejected'}


class StudioDesktop:
    def init_studio(self,prefs):
        try:options=RenderOptions.from_record(prefs.get('render_options'))
        except ValueError:options=RenderOptions()
        self.render_vars={k:(tk.BooleanVar(value=v) if isinstance(v,bool) else tk.StringVar(value=str(v))) for k,v in options.record().items()}
        self.render_mode_label=tk.StringVar(value=MODES[options.mode])
        self._preset_crop=(options.crop_x,options.crop_y)
        self.project_path=None;self.project_dirty=False
        self.project_title=tk.StringVar(value='')
        self.project_status=tk.StringVar(value='Projeto ainda não salvo')
        self.project_status.trace_add('write',self.refresh_project_header)
        self.review_filter=tk.StringVar(value='Todos')
        self.review_label=tk.StringVar(value='Pendente');self.edit_title=tk.StringVar();self.edit_notes=tk.StringVar()
        self.cursor_time=tk.StringVar(value='00:00:00.000')
        self.wave_status=tk.StringVar(value='Ondas do áudio original (mix). Use Carregar ondas para a janela visível.')
        self._seek_after=None;self._studio_seek_value=0.
        recent=prefs.get('recent_projects',[])
        self.recent_projects=[p for p in recent if isinstance(p,str)][:8] if isinstance(recent,list) else []

    def refresh_project_header(self,*_):
        if getattr(self,'current_page',None)=='review':self.page_subtitle.set(self.project_status.get())

    def rendering_from_ui(self):
        values={k:v.get() for k,v in self.render_vars.items()}
        values['mode']=next((key for key,label in MODES.items() if label==self.render_mode_label.get()),values['mode'])
        values['resolution']=int(values['resolution'])
        for name in ('crop_x','crop_y'):values[name]=float(str(values[name]).replace(',','.'))
        return RenderOptions.from_record(values)

    def apply_rendering(self,options):
        options=RenderOptions.from_record(options)
        for k,v in options.record().items():self.render_vars[k].set(v)
        self.render_mode_label.set(MODES[options.mode])
        self._preset_crop=(options.crop_x,options.crop_y)

    def rendering_for_export(self):
        options=self.rendering_from_ui()
        options.crop_x,options.crop_y=self._preset_crop
        return options

    def save_rendering(self):
        if self.busy:return
        try:
            options=self.rendering_from_ui();save_settings({'render_options':options.record()})
            self._preset_crop=(options.crop_x,options.crop_y)
            self.studio_changed();self.notify('Preset de exportação salvo. Confira o enquadramento na prévia antes de exportar.')
        except (ValueError,TypeError) as exc:self.error(exc)

    def studio_loaded(self,media):
        if self._seek_after is not None:self.after_cancel(self._seek_after);self._seek_after=None
        self.timeline.set_media(media.duration)
        self.project_path=None;self.project_dirty=False;self.project_title.set(Path(media.path).stem)
        self.project_status.set('Projeto ainda não salvo');self.review_filter.set('Todos')
        self.cut_start.set(timestamp(0));self.cut_end.set(timestamp(min(30.,media.duration)))
        self.cursor_time.set(timestamp(0));self._studio_seek_value=0.
        self.preview_label.configure(image='',text='Selecione um corte ou mova o cursor na timeline.')
        self.timeline_preview.configure(image='',text='Prévia')
        self._preview_image=None;self._mini_image=None;self._shown_preview_key=None
        self.edit_title.set('');self.edit_notes.set('')
        self.wave_status.set('Ondas do áudio original (mix). Carregue somente a janela que deseja revisar.')

    def studio_changed(self):
        self.project_dirty=True
        self.project_status.set((Path(self.project_path).name if self.project_path else 'Projeto ainda não salvo')+' • alterações por salvar')

    def timeline_select(self,cut_id):
        if self.busy:return
        if not self.table.exists(str(cut_id)):
            self.review_filter.set('Todos');self.refresh()
        if self.table.exists(str(cut_id)):
            self.table.selection_set(str(cut_id));self.table.see(str(cut_id));self.show_detail()

    def timeline_range(self,a,b):
        self.cut_start.set(timestamp(a));self.cut_end.set(timestamp(b))

    def timeline_seek(self,t):
        self._studio_seek_value=t;self.cursor_time.set(timestamp(t))
        if self._seek_after is not None:self.after_cancel(self._seek_after)
        self._seek_after=self.after(350,self._seek_frame)

    def _seek_frame(self):
        self._seek_after=None
        if not self.busy and not self._closing and self.current_page=='review':self.studio_preview_frame(self._studio_seek_value)

    def mark_cursor(self,start):
        if not self.media or self.busy:return
        a,b=self.timeline.range;t=self.timeline.cursor
        if start:a=t;b=max(b,min(self.media.duration,t+1.))
        else:b=t;a=min(a,max(0.,t-1.))
        self.timeline.set_range(a,b)

    def create_manual_cut(self):
        if not self.media:return self.error('Selecione um vídeo para criar um corte manual.')
        if self.busy:return
        try:
            if len(self.cuts)>=2000:raise ValueError('Limite de 2000 cortes neste projeto.')
            a,b=parse_time(self.cut_start.get()),parse_time(self.cut_end.get())
            Cut(1,a,b,0,'','').validate(self.media.duration)
            title=self.edit_title.get().strip()[:200] or 'Corte manual'
            def done(bounds):
                cut=Cut(max((c.id for c in self.cuts),default=0)+1,*bounds,0,title,
                        'Intervalo escolhido por você e alinhado aos quadros originais; sem pontuação automática.',manual=True)
                cut.transcript=' '.join(e['text'] for e in transcript_entries(cut,self.speech)[0])
                self.cuts.append(cut);self.review_filter.set('Todos');self.studio_changed();self.refresh()
                self.table.selection_set(str(cut.id));self.show_detail()
                self.notify('Corte manual criado. Salve o projeto para preservar esta revisão.')
            self.work(lambda:align_bounds(self.media,a,b,self.cancel),done,message='Criando corte manual nos quadros originais…')
        except (ValueError,TypeError) as exc:self.error(exc)

    def toggle_favorite(self):
        if self.busy:return
        try:
            selected=self.selected();value=not all(c.favorite for c in selected)
            for cut in selected:cut.favorite=value
            self.studio_changed();self.refresh()
        except ValueError as exc:self.error(exc)

    def apply_review(self):
        if self.busy:return
        try:
            cut=self.selected(True)[0]
            cut.title=self.edit_title.get().strip()[:200] or cut.title
            cut.editing=self.edit_notes.get().strip()[:2000]
            cut.review_state=STATES[self.review_label.get()]
            cut.user_edited=True
            self.studio_changed();self.refresh();self.table.selection_set(str(cut.id));self.show_detail()
        except (ValueError,KeyError) as exc:self.error(exc)

    def remove_manual_cut(self):
        if self.busy:return
        try:
            cut=self.selected(True)[0]
            if not cut.manual:raise ValueError('Para uma sugestão automática, marque Descartado. Este botão remove somente cortes manuais.')
            self.cuts=[c for c in self.cuts if c.id!=cut.id];self.studio_changed();self.refresh();self.show_detail()
        except ValueError as exc:self.error(exc)

    def apply_framing(self):
        if self.busy:return
        try:
            cut=self.selected(True)[0];options=self.rendering_from_ui()
            cut.framing={'crop_x':options.crop_x,'crop_y':options.crop_y}
            self.studio_changed();self.notify('Posição de recorte salva neste corte; usada na exportação vertical com recorte.')
        except (ValueError,TypeError) as exc:self.error(exc)

    def load_waveform(self):
        if self.busy or not self.media:return
        media=self.media;a,b=self.timeline.view
        def done(data):
            if self.media.path!=media.path:return
            self.timeline.waveform=data;self.timeline.draw()
            self.wave_status.set(f'Ondas reais do original: {timestamp(data["start"])} a {timestamp(data["end"])} • {len(data["peaks"])} barras. Recarregue após ampliar para mais detalhe.' if data['audio'] else 'Vídeo sem áudio: a timeline mostra silêncio.')
        self.work(lambda:build_waveform(media,self.cancel,lambda n,msg:self.events.put(('progress',(n,msg))),start=a,end=b),done,
                  message='Lendo ondas do áudio original em lotes limitados…')

    def studio_preview_frame(self,t=None):
        if self.busy or not self.media:return
        try:
            media=self.media
            cut=self.selected(True)[0] if self.table.selection() else None
            t=(cut.start if cut else self.timeline.cursor) if t is None else t
            t=min(max(0.,t),max(0.,media.duration-1/media.fps))
            options=self.rendering_from_ui()
            width=max(160,self.preview_label.winfo_width()-16);height=max(90,self.preview_label.winfo_height()-10)
            output=Path(self.preview_dir.name)/f'frame-{len(list(Path(self.preview_dir.name).iterdir()))}.png'
            def extract():
                absolute=media.origin+t
                cmd=[executable('ffmpeg'),'-v','error','-nostdin','-y','-copyts']
                if abs(media.origin)<1e-6 and t>2:cmd+=['-seek_timestamp','1','-ss',t-2]
                filters=[f'[0:{media.video_index}]trim=start={absolute},setpts=PTS-({absolute})/TB[base]',
                         video_filters('[base]',media,options,output='framed'),
                         f'[framed]scale={width}:{height}:force_original_aspect_ratio=decrease[preview]']
                run(cmd+['-i',media.path,'-filter_complex',';'.join(filters),'-map','[preview]','-frames:v','1',output],self.cancel,timeout=30)
                return output
            def done(path):
                if self.media.path!=media.path:return
                self._preview_image=tk.PhotoImage(master=self,file=str(path))
                self.preview_label.configure(image=self._preview_image,text='')
                factor=max(1,(self._preview_image.width()+95)//96,(self._preview_image.height()+49)//50)
                self._mini_image=self._preview_image.subsample(factor,factor)
                self.timeline_preview.configure(image=self._mini_image,text='')
                self.notify(f'Quadro em {timestamp(t)} • {MODES[options.mode]}. Reproduzir mostra o clipe com áudio e legendas configuradas.')
            self.work(extract,done,message='Carregando quadro e enquadramento da timeline…')
        except (ValueError,TypeError) as exc:self.error(exc)

    def _remember_project(self,path):
        self.recent_projects=[str(path),*[p for p in self.recent_projects if p!=str(path)]][:8]
        save_settings({'recent_projects':self.recent_projects})
        self.project_picker['values']=self.recent_projects

    def save_studio_project(self,save_as=False):
        if self.busy:return
        if not self.media:return self.error('Selecione um vídeo para salvar o projeto.')
        try:
            self.flush_captions()
            Path('projetos').mkdir(exist_ok=True)
            target=self.project_path if self.project_path and not save_as else filedialog.asksaveasfilename(
                title='Salvar projeto do Radar',defaultextension='.radar.json',initialdir=str(Path('projetos').resolve()),
                initialfile=re.sub(r'[^\w.-]+','_',self.project_title.get())[:80]+'.radar.json',filetypes=[('Projeto Radar','*.radar.json')])
            if not target:return
            if self.project_path and Path(target).resolve()!=Path(self.project_path).resolve() and Path(target).exists():
                raise FileExistsError('Escolha outro nome para preservar o projeto existente.')
            analysis=self.options_from_ui();render=self.rendering_for_export();title=self.project_title.get()
            media=self.media;cuts=[Cut(**asdict(c)) for c in self.cuts];speech=self.speech
            request={'model':self.model.get(),'track':'mix' if self.track.current()==0 else str(media.audio[self.track.current()-1]['index']),
                     'count':int(self.count.get()),'minimum':float(self.minimum.get()),'maximum':float(self.maximum.get())}
            def done(path):
                self.project_path=str(path);self.project_dirty=False;self.project_status.set(Path(path).name+' • salvo')
                self._remember_project(path);self.notify(f'Projeto salvo: {path}')
            self.work(lambda:save_project(target,media,cuts,speech,analysis=analysis,render=render,title=title,
                      overwrite=bool(self.project_path and Path(target).resolve()==Path(self.project_path).resolve()),cancel=self.cancel,request=request),done,
                      message='Salvando cortes, falas, favoritos e configurações…')
        except (ValueError,OSError) as exc:self.error(exc)

    def open_studio_project(self,path=None):
        if self.busy:return
        path=path or filedialog.askopenfilename(title='Abrir projeto Radar',filetypes=[('Projeto Radar','*.radar.json')],initialdir=str(Path('projetos').resolve()))
        if not path:return
        def done(data):
            self.loaded(data['media']);self.apply_options(data['analysis']);self.apply_rendering(data['render'])
            request=data.get('request') or {}
            if request.get('model') in ('off','tiny','base','small'):self.model.set(request['model'])
            for key,var in [('count',self.count),('minimum',self.minimum),('maximum',self.maximum)]:
                if key in request:var.set(str(request[key]))
            track=request.get('track','mix');self.track.current(0 if track=='mix' else next((i+1 for i,a in enumerate(self.media.audio) if str(a['index'])==str(track)),0))
            self.cuts=data['cuts'];self.speech=data['speech'];self.project_path=data['path'];self.project_title.set(data['title'])
            self.project_dirty=False;self.project_status.set(Path(self.project_path).name+' • salvo')
            self._remember_project(data['path']);self.refresh();self.show_page('review')
            if self.cuts:self.table.selection_set(str(self.cuts[0].id));self.show_detail()
            self.notify('Projeto reaberto sem repetir análise ou chamar uma API.')
        def failed(exc):
            if isinstance(exc,FileNotFoundError):
                original=filedialog.askopenfilename(title='Localizar vídeo original deste projeto',filetypes=[('Vídeo','*.mp4 *.mkv *.mov *.avi'),('Todos','*.*')])
                if original:self.work(lambda:load_project(path,self.cancel,source_override=original),done,message='Conferindo o vídeo localizado…')
                else:self.error(exc)
            else:self.error(exc)
        self.work(lambda:load_project(path,self.cancel),done,message='Conferindo original e abrindo projeto…',failed=failed)
