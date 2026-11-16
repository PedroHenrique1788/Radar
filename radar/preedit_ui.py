"""Functional pre-edit review in the existing blue Tk desktop and worker queue."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox

from .audio_prepare import AudioTreatment,prepare_audio
from .filmcraft import create_preedit_project,open_project
from .media import align_bounds
from .model import Cut,timestamp,parse_time
from .preedit import PreEdit,PreEditOptions,MODES,STATES,DECISIONS,track_layout
from .preedit_pipeline import analyze_preedit
from .timeline import Timeline
from .ui import ScrollPage

ROLES={'microphone':'Microfone','game':'Jogo','mix':'Mix','unknown':'Não identificado'}


class PreEditWindow(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.title('CefasGamer — Pré-edição');self.geometry('1080x760');self.minsize(850,650)
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.summary=tk.StringVar();self.detail=tk.StringVar(value='Selecione uma sugestão para revisar o motivo.')
        self.mode=tk.StringVar();self.original=tk.BooleanVar(value=True);self.vars={};self.track_vars={}
        self.audio_info=tk.StringVar(value='Analise a pré-edição para medir as faixas.');self.audio_index=tk.StringVar()
        self.output=None
        ttk.Label(self,text='Pré-edição não destrutiva',style='Title.TLabel').pack(anchor='w',padx=14,pady=(12,4))
        ttk.Label(self,textvariable=self.summary,wraplength=1000).pack(anchor='w',padx=14,pady=4)
        tabs=ttk.Notebook(self);tabs.pack(fill='both',expand=True,padx=12,pady=8)
        review=ttk.Frame(tabs,padding=8);settings=ScrollPage(tabs);audio=ScrollPage(tabs)
        tabs.add(review,text='Revisar sequência');tabs.add(settings,text='Detector e faixas OBS');tabs.add(audio,text='Preparar áudio (opcional)')
        self.timeline=Timeline(review,on_select=self.select,on_range=self.range_changed)
        self.timeline.pack(fill='x');self.timeline.configure(height=145)
        row=ttk.Frame(review);row.pack(fill='x',pady=4)
        ttk.Checkbutton(row,text='Visão original (desmarque para sequência pré-editada)',variable=self.original,command=self.refresh).pack(side='left')
        for label,command in [('−',lambda:self.timeline.zoom(2)),('+',lambda:self.timeline.zoom(.5)),('Tudo',self.timeline.reset_view)]:ttk.Button(row,text=label,width=5,command=command).pack(side='left',padx=2)
        self.table=ttk.Treeview(review,columns=('start','end','state','decision'),show='headings',height=7,selectmode='browse')
        for key,label,w in [('start','IN no original',145),('end','OUT no original',145),('state','Classificação',210),('decision','Sua decisão',190)]:
            self.table.heading(key,text=label);self.table.column(key,width=w,minwidth=100)
        self.table.pack(fill='both',expand=True);self.table.bind('<<TreeviewSelect>>',self.selected)
        self.table.bind('<Return>',lambda e:self.decide('accepted'));self.table.bind('<Delete>',lambda e:self.decide('rejected'))
        ttk.Label(review,textvariable=self.detail,wraplength=970,justify='left').pack(fill='x',pady=6)
        row=ttk.Frame(review);row.pack(fill='x')
        self.start=tk.StringVar(value='00:00:00.000');self.end=tk.StringVar(value='00:00:01.000')
        for label,var in [('IN original',self.start),('OUT original',self.end)]:
            ttk.Label(row,text=label).pack(side='left',padx=3);ttk.Entry(row,textvariable=var,width=17).pack(side='left')
        ttk.Button(row,text='Aplicar IN/OUT',command=self.bounds).pack(side='left',padx=5)
        row=ttk.Frame(review);row.pack(fill='x',pady=5)
        for label,command in [('Aceitar remoção',lambda:self.decide('accepted')),('Rejeitar / manter',lambda:self.decide('rejected')),('Restaurar intervalo',lambda:self.decide('pending')),('Desfazer',lambda:self.travel(False)),('Refazer',lambda:self.travel(True)),('Ouvir/ver original',self.preview)]:
            ttk.Button(row,text=label,command=command).pack(side='left',padx=2)
        self.bind('<Control-z>',lambda e:self.travel(False));self.bind('<Control-y>',lambda e:self.travel(True))
        self.build_settings(settings.content);self.build_audio(audio.content)
        footer=ttk.Frame(self,padding=10);footer.pack(fill='x')
        for label,command in [('Analisar pré-edição',self.analyze),('Salvar projeto',self.save),('Enviar pré-edição para FilmCraft',self.export),('Abrir resultado',self.open_output),('Pausar/retomar',self.pause),('Cancelar',app.cancel.set)]:
            ttk.Button(footer,text=label,command=command).pack(side='left',padx=2)
        ttk.Label(self,textvariable=app.status,wraplength=1000).pack(fill='x',padx=14,pady=(0,8))
        self.refresh()

    def close(self):
        # A running worker stores results on App, independently of this view.
        self.destroy()

    def build_settings(self,parent):
        current=PreEditOptions.from_record(self.app.preedit.options if self.app.preedit else None)
        ttk.Label(parent,text='Presets alteram regras e margens; nenhum modo remove automaticamente.',wraplength=900).pack(anchor='w',pady=8)
        self.mode.set(MODES[current.mode]);picker=ttk.Combobox(parent,textvariable=self.mode,values=list(MODES.values()),state='readonly')
        picker.pack(anchor='w');picker.bind('<<ComboboxSelected>>',self.preset)
        for key,label in [('min_pause','Pausa mínima (2–300 s)'),('sensitivity','Sensibilidade (0–1)'),('before','Margem antes do contexto seguinte (0–30 s)'),('after','Margem após contexto anterior (0–30 s)'),('intensity','Intensidade das sugestões (0–1)')]:
            var=tk.StringVar(value=str(getattr(current,key)));self.vars[key]=var
            row=ttk.Frame(parent);row.pack(fill='x',pady=4);ttk.Label(row,text=label,width=55).pack(side='left');ttk.Entry(row,textvariable=var,width=10).pack(side='left')
        self.protect=tk.BooleanVar(value=current.protect_narrative)
        ttk.Checkbutton(parent,text='Proteção narrativa: sem áudio de jogo identificado, exigir revisão',variable=self.protect).pack(anchor='w',pady=8)
        ttk.Label(parent,text='Papéis são declarações suas, não reconhecimento automático. Confira etiquetas OBS.\nMix + individuais pode duplicar áudio: marque apenas a combinação que deseja ouvir no editor.\nDesmarcar uma faixa afeta a exportação, mas ela continua protegendo conteúdo durante a análise.',wraplength=920).pack(anchor='w',pady=8)
        tracks=self.app.preedit.tracks if self.app.preedit else track_layout(self.app.media)
        for track in tracks:
            row=ttk.Frame(parent);row.pack(fill='x',pady=3)
            ttk.Label(row,text=f"Faixa {track['index']} — {track.get('title','')} ({track.get('channels','?')} canais)",width=48).pack(side='left')
            role=tk.StringVar(value=ROLES[track['role']]);enabled=tk.BooleanVar(value=track['export'])
            ttk.Combobox(row,textvariable=role,values=list(ROLES.values()),state='readonly',width=20).pack(side='left')
            ttk.Checkbutton(row,text='Enviar ao editor',variable=enabled).pack(side='left',padx=8)
            self.track_vars[track['index']]=(role,enabled)

    def build_audio(self,parent):
        ttk.Label(parent,text='Análise → sugestão → aplicação explícita numa cópia WAV. O original e a exportação padrão não recebem filtros.',wraplength=950).pack(anchor='w',pady=8)
        self.audio_index.set(str(self.app.media.audio[0]['index']) if self.app.media.audio else '')
        picker=ttk.Combobox(parent,textvariable=self.audio_index,values=[str(a['index']) for a in self.app.media.audio],state='readonly',width=12)
        picker.pack(anchor='w');picker.bind('<<ComboboxSelected>>',lambda e:self.audio_summary())
        ttk.Label(parent,textvariable=self.audio_info,wraplength=940,justify='left').pack(anchor='w',pady=10)
        self.treatment_vars={}
        for key,label,value in [('gain_db','Ganho dB (-24 a +12)',0.),('threshold_db','Compressor: limiar dB (-40 a -3)',-18.),('ratio','Compressor: razão (1–6)',2.),('gate_db','Gate: limiar dB (-80 a -35)',-55.),('target_lufs','Normalização: alvo LUFS (-24 a -12)',-16.)]:
            row=ttk.Frame(parent);row.pack(fill='x',pady=4);ttk.Label(row,text=label,width=48).pack(side='left')
            var=tk.StringVar(value=str(value));self.treatment_vars[key]=var;ttk.Entry(row,textvariable=var,width=12).pack(side='left')
        for key,label in [('compressor','Aplicar compressor'),('normalize','Aplicar loudnorm (uma passagem, revisar ouvindo)'),('gate','Aplicar gate leve (pode ocultar sons baixos)')]:
            var=tk.BooleanVar(value=False);self.treatment_vars[key]=var;ttk.Checkbutton(parent,text=label,variable=var).pack(anchor='w',pady=3)
        ttk.Button(parent,text='Criar cópia tratada para comparar',command=self.treat).pack(anchor='w',pady=10)
        ttk.Label(parent,text='Use Ouvir/ver original na revisão e abra o WAV tratado no player para comparar. Importe a cópia no FilmCraft somente se aprovada; silencie a versão original correspondente. Medições mono não validam picos de todos os canais.',wraplength=930).pack(anchor='w')
        self.treated_output=None
        ttk.Button(parent,text='Ouvir cópia tratada',command=self.listen_treated).pack(anchor='w',pady=8)

    def settings(self):
        mode=next(k for k,v in MODES.items() if v==self.mode.get())
        return PreEditOptions(mode=mode,protect_narrative=self.protect.get(),**{k:float(v.get().replace(',','.')) for k,v in self.vars.items()}).validate()

    def tracks(self):
        rows=deepcopy(self.app.preedit.tracks if self.app.preedit else track_layout(self.app.media))
        for r in rows:
            role,enabled=self.track_vars[r['index']];r['role']=next(k for k,v in ROLES.items() if v==role.get());r['export']=enabled.get()
        return rows

    def analyze(self):
        app=self.app
        if app.busy:return
        try:
            opts=self.settings();tracks=self.tracks();analysis=app.options_from_ui();speech=deepcopy(app.speech)
            if app.preedit and app.preedit.history and not messagebox.askyesno('Preservar revisão','Uma nova análise substitui as decisões desta pré-edição. Salve uma cópia antes, se necessário. Continuar?',parent=self):return
            markers=[{'time':c.start,'kind':'important' if c.favorite else 'short','label':c.title[:120]} for c in app.cuts]
            def done(result):
                app.preedit=result;app.studio_changed()
                if self.winfo_exists():self.refresh()
                app.notify('Pré-edição analisada. Revise e aceite somente as remoções desejadas; salve o projeto.')
            app.work(lambda:analyze_preedit(app.media,options=opts,analysis=analysis,tracks=tracks,speech=speech,markers=markers,cancel=app.cancel,
                                           progress=lambda n,msg:app.events.put(('progress',(n,msg)))),done,message='Analisando pré-edição por faixas e lotes…')
        except (ValueError,TypeError) as exc:app.error(exc)

    def refresh(self):
        if not self.winfo_exists():return
        edit=self.app.preedit;selected=self.table.selection();self.table.delete(*self.table.get_children())
        if edit is None:
            self.summary.set(f'Original: {timestamp(self.app.media.duration)} • Ainda sem sugestões • Original preservado')
            self.timeline.set_media(self.app.media.duration);return
        potential=sum(s.end-s.start for s in edit.suggestions if s.classification=='remove' and s.decision=='pending')
        accepted=sum(s.decision=='accepted' for s in edit.suggestions);preserved=sum(b-a for a,b in edit.kept())
        self.summary.set(f'Original {timestamp(edit.duration)} → proposta {timestamp(edit.proposed_duration)} • {len(edit.suggestions)} intervalos • {accepted} remoções aceitas\nEconomia aprovada {timestamp(edit.duration-edit.proposed_duration)} • potencial adicional {timestamp(potential)} • preservado {timestamp(preserved)} • {sum(m["kind"]=="short" for m in edit.markers)} marcadores Shorts')
        for s in edit.suggestions:self.table.insert('','end',iid=str(s.id),values=(timestamp(s.start),timestamp(s.end),STATES[s.classification],DECISIONS[s.decision]))
        self.timeline.set_media(edit.duration if self.original.get() else max(.001,edit.proposed_duration));cuts=[]
        if self.original.get():
            base=Cut(10001,0,edit.duration,0,'Manter','');base.preedit_state='keep';cuts.append(base)
            for s in edit.suggestions:
                c=Cut(s.id,s.start,s.end,0,'','');c.preedit_state=s.decision if s.decision!='pending' else s.classification;cuts.append(c)
        else:
            elapsed=0.
            for i,(a,b) in enumerate(edit.kept(),1):
                c=Cut(10000+i,elapsed,elapsed+b-a,0,'Manter','');c.preedit_state='keep';cuts.append(c);elapsed+=b-a
        self.timeline.markers=[{**m,'time':m['time'] if self.original.get() else edit.proposed_time(m['time'])} for m in edit.markers]
        self.timeline.update_cuts(cuts)
        if selected and self.table.exists(selected[0]):self.table.selection_set(selected[0]);self.selected()
        self.audio_summary()

    def select(self,ident):
        if self.table.exists(str(ident)):self.table.selection_set(str(ident));self.table.see(str(ident));self.selected()

    def chosen(self):
        if self.app.preedit is None or not self.table.selection():raise ValueError('Selecione uma sugestão para revisar.')
        return next(s for s in self.app.preedit.suggestions if str(s.id)==self.table.selection()[0])

    def selected(self,event=None):
        try:
            s=self.chosen();self.start.set(timestamp(s.start));self.end.set(timestamp(s.end))
            self.detail.set(s.reason+f' Força heurística: {s.confidence:.2f} (não é probabilidade).')
            if self.original.get():self.timeline.select_cut(Cut(s.id,s.start,s.end,0,'',''))
        except ValueError:pass

    def range_changed(self,a,b):
        if self.original.get():self.start.set(timestamp(a));self.end.set(timestamp(b))

    def changed(self):self.app.studio_changed();self.refresh()

    def decide(self,decision):
        if self.app.busy:return
        try:self.app.preedit.edit(self.chosen().id,decision=decision);self.changed()
        except (ValueError,AttributeError) as exc:self.app.error(exc)

    def travel(self,redo):
        if self.app.busy or self.app.preedit is None:return
        try:
            if self.app.preedit.redo() if redo else self.app.preedit.undo():self.changed()
        except ValueError as exc:self.app.error(exc)

    def bounds(self):
        app=self.app
        if app.busy:return
        try:
            s=self.chosen();ident=s.id;a=parse_time(self.start.get());b=parse_time(self.end.get());Cut(1,a,b,0,'','').validate(app.media.duration)
            def done(bounds):
                try:app.preedit.edit(ident,start=bounds[0],end=bounds[1]);app.studio_changed()
                except ValueError as exc:app.error(exc)
                if self.winfo_exists():self.refresh()
            app.work(lambda:align_bounds(app.media,a,b,app.cancel),done,message='Conferindo IN/OUT nos quadros originais…')
        except ValueError as exc:app.error(exc)

    def save(self):
        if self.app.busy:return
        if self.app.preedit:
            self.app.preedit.tracks=self.tracks();self.app.preedit.validate()
        self.app.save_studio_project()

    def preview(self):
        if self.app.busy:return
        try:
            from .media import executable
            from .runtime import start_process
            s=self.chosen()
            # Direct original playback, no intermediate MP4. Player clock uses
            # source-relative seek; reference editing still uses source PTS.
            start_process([executable('ffplay'),'-autoexit','-ss',str(s.start),'-t',str(s.end-s.start),self.app.media.path])
        except (ValueError,RuntimeError,OSError) as exc:self.app.error(exc)

    def export(self):
        app=self.app
        if app.busy:return
        try:
            if app.preedit is None:raise ValueError('Analise a pré-edição antes de enviar ao editor.')
            edit=PreEdit.from_record(app.preedit.record());edit.tracks=self.tracks();edit.validate()
            roles=[r['role'] for r in edit.tracks if r['export']]
            if 'mix' in roles and any(r in roles for r in ('microphone','game')):
                if not messagebox.askyesno('Combinação de áudio','Mix e faixas individuais estão selecionados. Isso pode duplicar áudio. Exportar esta combinação mesmo assim?',parent=self):return
            folder=filedialog.askdirectory(parent=self,title='Pasta para nova pré-edição FilmCraft / OTIO')
            if not folder:return
            app.preedit.tracks=deepcopy(edit.tracks);app.studio_changed()
            def done(path):
                self.output=path;app.last_output=Path(path).parent
                app.notify(f'Pré-edição criada: {path}. Use Abrir resultado; preserve o original e os WAVs.')
                if self.winfo_exists():
                    messagebox.showinfo('Pré-edição criada',f'{path}\n'+('Projeto nativo reaberto e conferido pela CLI.' if path.suffix=='.fcproj' else 'Fallback OTIO: importe a timeline no FilmCraft. Consulte Verificacao.json para limitações.'),parent=self)
            app.work(lambda:create_preedit_project(app.media,edit,folder,cli=app.cli or False,cancel=app.cancel,
                                                   progress=lambda n,msg:app.events.put(('progress',(n,msg)))),done,message='Enviando pré-edição editável ao FilmCraft…')
        except (ValueError,OSError) as exc:app.error(exc)

    def open_output(self):
        if self.output:
            try:open_project(self.output,self.app.cli)
            except (ValueError,RuntimeError,OSError) as exc:self.app.error(exc)
        else:self.app.error('Envie a pré-edição primeiro; o resultado aparecerá aqui.')

    def pause(self):
        if not self.app.busy:return
        if self.app.cancel.pause_event.is_set():self.app.cancel.resume()
        else:self.app.cancel.pause()

    def audio_summary(self):
        if self.app.preedit is None:return
        data=self.app.preedit.audio_analysis.get(self.audio_index.get(),{})
        if not data.get('available'):self.audio_info.set('Faixa sem medições disponíveis.');return
        self.audio_info.set(f"RMS mono {data['rms_dbfs']:.2f} dBFS • pico mono {data['peak_dbfs']:.2f} dBFS\nSegundos com possível clipping: {data['possible_clipped_seconds']} • sugestão de ganho: {data['suggested_gain_db']:+.2f} dB\n{data['note']}")

    def treat(self):
        app=self.app
        if app.busy:return
        try:
            values={k:v.get() if k in ('compressor','normalize','gate') else float(v.get().replace(',','.')) for k,v in self.treatment_vars.items()}
            treatment=AudioTreatment(**values);treatment.filters();index=int(self.audio_index.get())
            path=filedialog.asksaveasfilename(parent=self,title='Nova cópia WAV tratada',defaultextension='.wav',filetypes=[('WAV','*.wav')])
            if not path:return
            def done(path):self.treated_output=path;app.notify(f'Cópia tratada pronta para comparar: {path}')
            app.work(lambda:prepare_audio(app.media,index,path,treatment,app.cancel,lambda n,msg:app.events.put(('progress',(n,msg)))),done,message='Criando cópia de áudio sem alterar o original…')
        except (ValueError,OSError) as exc:app.error(exc)

    def listen_treated(self):
        if not self.treated_output:return self.app.error('Crie a cópia tratada primeiro.')
        try:
            from .runtime import start_process
            from .media import executable
            start_process([executable('ffplay'),'-autoexit','-nodisp',str(self.treated_output)])
        except (RuntimeError,OSError) as exc:self.app.error(exc)

    def preset(self,event=None):
        mode=next(k for k,v in MODES.items() if v==self.mode.get());opts=PreEditOptions.preset(mode)
        for k,v in self.vars.items():v.set(str(getattr(opts,k)))
