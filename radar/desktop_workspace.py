"""Dashboard, visual clip library and activity, sharing the existing desktop flow."""
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import shutil
import time
import tkinter as tk
from tkinter import ttk

from .library import find_cuts,thumbnail
from .model import Cut
from .checkpoints import signature


class WorkspaceDesktop:
    def init_workspace(self):
        self.library_query=tk.StringVar();self.library_filter=tk.StringVar(value='Todos');self.library_order=tk.StringVar(value='Por tempo')
        self.library_info=tk.StringVar(value='Nenhum clipe neste projeto. Importe um vídeo e analise ou crie um corte manual.')
        self.library_selected=set();self._library_page=0;self._library_page_size=6
        self._library_buttons=[];self._library_cards={};self._library_vars={};self._library_images={};self._library_after=None
        self._workspace_operation='';self._activity_rows=[];self._activity_last=0.;self._disk_last=0.
        self._workspace_indeterminate=False
        self.dashboard_stats={k:tk.StringVar(value='0') for k in ('cuts','approved','favorites','captions')}
        self.dashboard_source=tk.StringVar(value='Seu próximo Short começa aqui.')
        self.dashboard_model=tk.StringVar(value='CPU local · transcrição opcional')
        self.workspace_cpu=tk.StringVar(value='CPU: aguardando');self.workspace_ram=tk.StringVar(value='RAM: aguardando')
        self.workspace_disk=tk.StringVar(value='Armazenamento: aguardando');self.workspace_task=tk.StringVar(value='Nenhuma tarefa em execução')
        self.workspace_progress=tk.DoubleVar(value=0.)
        self.workspace_library_label=tk.StringVar(value='0 clipes');self.workspace_selection=tk.StringVar(value='Nenhum selecionado')

    def bind_workspace(self):
        for var in (self.library_query,self.library_filter,self.library_order):var.trace_add('write',self.schedule_library)
        for sequence,command in [('<Control-i>',self.choose),('<Control-o>',self.open_studio_project),
                                 ('<Control-s>',self.save_studio_project),('<Control-Shift-S>',lambda:self.save_studio_project(True)),
                                 ('<Control-f>',self.focus_library_search),('<Alt-Key-1>',lambda:self.show_page('dashboard')),
                                 ('<Alt-Key-2>',lambda:self.show_page('library')),('<Alt-Key-3>',lambda:self.show_page('review')),
                                 ('<Alt-Key-4>',lambda:self.show_page('captions'))]:
            def invoke(event,action=command):action();return 'break'
            self.bind(sequence,invoke,add='+')

    def focus_library_search(self):
        self.show_page('library');self.library_search.focus_set();self.library_search.selection_range(0,'end')

    def schedule_library(self,*_):
        self._library_page=0
        if self._library_after is not None:self.after_cancel(self._library_after)
        self._library_after=self.after(180,self.refresh_library)

    def reset_workspace_media(self):
        self.library_selected.clear();self._library_page=0;self._library_images.clear()
        self.library_query.set('');self.library_filter.set('Todos')

    def library_stamp(self,cut):
        try:options=self.rendering_for_export();options.burn_subtitles=False
        except (ValueError,TypeError):return None
        return signature([self.media.source_id or self.media.path,cut.start,cut.end,cut.framing,options.record()])

    def refresh_workspace(self):
        if not hasattr(self,'dashboard_projects'):return
        counts={'cuts':len(self.cuts),'approved':sum(c.review_state=='approved' for c in self.cuts),
                'favorites':sum(c.favorite for c in self.cuts),'captions':sum(bool(c.captions.get('cues')) for c in self.cuts)}
        for key,value in counts.items():self.dashboard_stats[key].set(str(value))
        self.workspace_library_label.set(f'{len(self.cuts)} clipes')
        self.dashboard_source.set(Path(self.media.path).name if self.media else 'Seu próximo Short começa aqui.')
        self.dashboard_model.set(('Radar + Gemini' if self.workflow_mode=='gemini' else 'Radar local em CPU')+' · Whisper '+self.model.get())
        selected=self.dashboard_projects.selection();self.dashboard_projects.delete(*self.dashboard_projects.get_children())
        for i,path in enumerate(self.recent_projects):
            file=Path(path)
            self.dashboard_projects.insert('','end',iid=str(i),values=(file.name,'Disponível' if file.is_file() else 'Arquivo não encontrado'))
        if selected and self.dashboard_projects.exists(selected[0]):self.dashboard_projects.selection_set(selected[0])
        if self.current_page=='library':self.refresh_library()
        self.refresh_workspace_jobs()

    def dashboard_open_recent(self,event=None):
        if self.busy:return
        selected=self.dashboard_projects.selection()
        if not selected:return self.error('Selecione um projeto recente ou use Abrir projeto.')
        path=Path(self.recent_projects[int(selected[0])])
        if not path.is_file():return self.error('O arquivo do projeto não está neste local. Use Abrir projeto para localizar seu .radar.json.')
        self.open_studio_project(str(path))

    def refresh_workspace_jobs(self):
        if not hasattr(self,'workspace_jobs'):return
        selected=self.workspace_jobs.selection();self.workspace_jobs.delete(*self.workspace_jobs.get_children())
        for item in self.jobs_table.get_children():
            self.workspace_jobs.insert('','end',iid=item,values=self.jobs_table.item(item,'values'))
        if selected and self.workspace_jobs.exists(selected[0]):self.workspace_jobs.selection_set(selected[0])

    def workspace_open_job(self,event=None):
        if self.busy:return
        selected=self.workspace_jobs.selection()
        if not selected:return self.error('Selecione um trabalho na lista para conferir o original e retomar.')
        self.jobs_table.selection_set(selected);self.open_recent_analysis()

    def workspace_event(self,text,*,progress=False):
        if not hasattr(self,'activity_table'):return
        now=time.monotonic()
        if progress and now-self._activity_last<1:return
        text=' '.join(str(text).split())[:400]
        if not text or self._activity_rows and self._activity_rows[-1][1]==text:return
        self._activity_last=now;clock=datetime.now().strftime('%H:%M:%S')
        self._activity_rows.append((clock,text));self._activity_rows=self._activity_rows[-150:]
        self.activity_table.insert('','end',values=(clock,text))
        rows=self.activity_table.get_children()
        if len(rows)>150:self.activity_table.delete(*rows[:-150])
        self.activity_table.yview_moveto(1)
        self.dashboard_activity.set(text)

    def update_workspace_runtime(self,snapshot):
        cpu=snapshot.get('cpu_percent');ram=snapshot.get('ram_bytes')
        self.workspace_cpu.set('CPU Radar: '+(f'{cpu:.0f}%' if cpu is not None else 'n/d'))
        self.workspace_ram.set('RAM Radar: '+(f'{ram/1024**2:.0f} MB' if ram is not None else 'n/d'))
        operation=self._workspace_operation or 'Nenhuma tarefa em execução'
        if self.busy:operation=('Pausado · ' if snapshot.get('paused') else '')+snapshot['stage']
        self.workspace_task.set(operation)
        total=snapshot.get('total');done=snapshot.get('done',0.)
        indeterminate=self.busy and total is None
        if indeterminate!=self._workspace_indeterminate:
            self._workspace_indeterminate=indeterminate
            self.workspace_bar.stop();self.workspace_bar.configure(mode='indeterminate' if indeterminate else 'determinate')
            if indeterminate:self.workspace_bar.start(20)
        self.workspace_progress.set(min(100,100*done/total) if self.busy and total else 0.)
        now=time.monotonic()
        if now-self._disk_last>5:
            self._disk_last=now
            try:self.workspace_disk.set(f'Disco livre: {shutil.disk_usage(Path("temporarios").resolve()).free/1024**3:.1f} GB')
            except OSError:self.workspace_disk.set('Disco livre: n/d')

    def refresh_library(self):
        if self._library_after is not None:self.after_cancel(self._library_after);self._library_after=None
        if self._closing or not hasattr(self,'library_grid'):return
        from .workspace_ui import draw_library
        reviews={}
        for cut in self.cuts:
            if cut.id in self.ai_reviews:
                review=self._valid_ai(cut)
                if review:reviews[cut.id]=review
        rows=find_cuts(self.cuts,self.library_query.get(),self.library_filter.get(),self.library_order.get(),reviews)
        self.library_selected.intersection_update(c.id for c in self.cuts)
        pages=max(1,(len(rows)+self._library_page_size-1)//self._library_page_size)
        self._library_page=max(0,min(self._library_page,pages-1))
        self._library_pages=pages
        visible=rows[self._library_page*self._library_page_size:(self._library_page+1)*self._library_page_size]
        self._library_visible=visible
        draw_library(self,visible,reviews)
        self.library_info.set(f'{len(rows)} de {len(self.cuts)} clipes · página {self._library_page+1}/{pages}' if self.cuts else 'Nenhum clipe neste projeto. Importe um vídeo e analise ou crie um corte manual.')
        self.library_prev.configure(state='normal' if self._library_page>0 and not self.busy else 'disabled')
        self.library_next.configure(state='normal' if self._library_page+1<pages and not self.busy else 'disabled')
        self.sync_library_controls()

    def library_page(self,delta):
        if self.busy:return
        self._library_page+=delta;self.refresh_library()

    def library_select(self,ident):
        if self._library_vars[ident].get():self.library_selected.add(ident)
        else:self.library_selected.discard(ident)
        self.sync_library_controls()

    def library_select_page(self):
        if self.busy:return
        ids={c.id for c in self._library_visible}
        if ids<=self.library_selected:self.library_selected-=ids
        else:self.library_selected|=ids
        for ident,var in self._library_vars.items():var.set(ident in self.library_selected)
        self.sync_library_controls()

    def sync_library_controls(self):
        if not hasattr(self,'library_grid'):return
        self.workspace_selection.set(f'{len(self.library_selected)} selecionados' if self.library_selected else 'Nenhum selecionado')
        for button in self._library_buttons:
            if button.winfo_exists():button.configure(state='disabled' if self.busy else 'normal')
        self.library_export_button.configure(state='normal' if self.library_selected and not self.busy else 'disabled')
        self.library_thumbnail_button.configure(state='normal' if getattr(self,'_library_visible',[]) and not self.busy else 'disabled')
        self.library_prev.configure(state='normal' if self._library_page>0 and not self.busy else 'disabled')
        self.library_next.configure(state='normal' if self._library_page+1<getattr(self,'_library_pages',1) and not self.busy else 'disabled')

    def library_target(self,ident,action='review'):
        if self.busy:return
        try:
            self.flush_captions()
            if not any(c.id==ident for c in self.cuts):raise ValueError('Este clipe não existe mais no projeto.')
            if not self.table.exists(str(ident)):self.review_filter.set('Todos');self.refresh()
            self.table.selection_set(str(ident));self.show_detail()
            if action=='favorite':self.toggle_favorite();self.refresh_library()
            elif action=='mp4':self.export_video()
            else:self.show_page(action)
        except ValueError as exc:self.error(exc)

    def library_export_selected(self):
        if self.busy:return
        ids={c.id for c in self.cuts}&self.library_selected
        if not ids:return self.error('Marque os clipes que deseja exportar.')
        if any(not self.table.exists(str(i)) for i in ids):self.review_filter.set('Todos');self.refresh()
        self.table.selection_set([str(i) for i in sorted(ids)]);self.export_batch()

    def library_thumbnails(self):
        if self.busy or not self.media:return
        media=self.media;cuts=[Cut(**asdict(c)) for c in getattr(self,'_library_visible',[])]
        if not cuts:return
        try:options=self.rendering_for_export()
        except (ValueError,TypeError) as exc:return self.error(exc)
        stamps={c.id:self.library_stamp(c) for c in cuts}
        folder=Path(self.preview_dir.name)/'library'
        def build():
            outputs={}
            for i,cut in enumerate(cuts):
                outputs[cut.id]=thumbnail(media,cut,options,folder,self.cancel)
                self.cancel.report('Miniaturas',i+1,len(cuts),'quadros')
                self.events.put(('progress',(100*(i+1)/len(cuts),f'Miniaturas: {i+1}/{len(cuts)} quadros')))
            return outputs
        def done(outputs):
            if not self.media or self.media.path!=media.path:return
            for cut in cuts:
                current=next((c for c in self.cuts if c.id==cut.id),None)
                if current and self.library_stamp(current)==stamps[cut.id]:self._library_images[cut.id]={'file':str(outputs[cut.id]),'stamp':stamps[cut.id]}
            self.refresh_library();self.notify('Miniaturas prontas. Cada clipe usou somente um quadro, sem nova transcrição.')
        self.work(build,done,message='Carregando quadros dos clipes desta página…')
