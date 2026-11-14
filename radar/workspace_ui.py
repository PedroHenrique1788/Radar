"""Radar's own dashboard and clip cards, inspired by a studio workflow."""
import math
import tkinter as tk
from tkinter import ttk

from . import ui
from .library import FILTERS
from .model import timestamp


def adaptive_label(parent,**kw):
    label=ttk.Label(parent,**kw)
    label.bind('<Configure>',lambda e:label.configure(wraplength=max(140,e.width)))
    return label


def build_dashboard(app,parent):
    hero=ui.card(parent)
    adaptive_label(hero,text='Seu próximo Short, em um só lugar.',style='Hero.TLabel').pack(anchor='w',fill='x')
    adaptive_label(hero,textvariable=app.dashboard_source,style='CardMuted.TLabel').pack(fill='x',pady=(8,4))
    row=ttk.Frame(hero,style='Card.TFrame');row.pack(fill='x',pady=6)
    for text,action in [('Importar vídeo',app.choose),('Abrir projeto',app.open_studio_project)]:
        app._run_buttons.append(ui.button(row,text,action,primary=text=='Importar vídeo'))
    app.dashboard_analyze=ui.button(row,'Analisar vídeo',app.analyze)
    ttk.Label(hero,textvariable=app.dashboard_model,style='CardMuted.TLabel').pack(anchor='w',pady=4)
    stats=ttk.Frame(parent);stats.pack(fill='x',pady=(0,14))
    for i,(name,label) in enumerate([('cuts','CLIPES NO PROJETO'),('approved','APROVADOS'),('favorites','FAVORITOS'),('captions','COM LEGENDAS')]):
        stats.columnconfigure(i,weight=1,uniform='stats')
        panel=ttk.Frame(stats,style='Card.TFrame',padding=12);panel.grid(row=0,column=i,sticky='nsew',padx=(0,8 if i<3 else 0))
        ttk.Label(panel,textvariable=app.dashboard_stats[name],style='Metric.TLabel').pack(anchor='w')
        ttk.Label(panel,text=label,style='MetricLabel.TLabel',wraplength=140).pack(anchor='w',pady=(4,0))
    columns=ttk.Frame(parent);columns.pack(fill='both',expand=True);columns.columnconfigure(0,weight=6);columns.columnconfigure(1,weight=4)
    projects=ttk.Frame(columns,style='Card.TFrame',padding=14);projects.grid(row=0,column=0,sticky='nsew',padx=(0,12))
    ttk.Label(projects,text='Continue de onde parou',style='Section.TLabel').pack(anchor='w',pady=(0,10))
    app.dashboard_projects=ttk.Treeview(projects,columns=('name','state'),show='headings',height=5,selectmode='browse')
    for key,label,width in [('name','Projetos recentes',210),('state','Arquivo',120)]:
        app.dashboard_projects.heading(key,text=label);app.dashboard_projects.column(key,width=width,minwidth=80,stretch=key=='name')
    app.dashboard_projects.pack(fill='both',expand=True);app.dashboard_projects.bind('<Double-1>',app.dashboard_open_recent)
    app._run_buttons.append(ui.button(projects,'Abrir selecionado',app.dashboard_open_recent))
    activity=ttk.Frame(columns,style='Card.TFrame',padding=14);activity.grid(row=0,column=1,sticky='nsew')
    ttk.Label(activity,text='Seu estúdio agora',style='Section.TLabel').pack(anchor='w',pady=(0,10))
    for variable in (app.workspace_task,app.workspace_cpu,app.workspace_ram,app.workspace_disk):
        adaptive_label(activity,textvariable=variable,style='CardMuted.TLabel').pack(fill='x',pady=4)
    app.dashboard_activity=tk.StringVar(value='Importe um vídeo ou reabra um projeto para começar.')
    adaptive_label(activity,textvariable=app.dashboard_activity,style='CardMuted.TLabel').pack(fill='x',pady=(12,6))
    for label,page in [('Abrir biblioteca de clipes','library'),('Estúdio de Legendas','captions'),('Fila e atividade','jobs')]:
        ttk.Button(activity,text=label,command=lambda p=page:app.show_page(p)).pack(fill='x',pady=4)


def build_library(app,parent):
    tools=ui.card(parent)
    tools.columnconfigure(0,weight=1)
    ttk.Label(tools,text='Encontre o momento certo',style='Section.TLabel').grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,10))
    app.library_search=ttk.Entry(tools,textvariable=app.library_query,width=20)
    app.library_search.grid(row=1,column=0,sticky='ew',padx=(0,8))
    ttk.Combobox(tools,textvariable=app.library_filter,values=list(FILTERS),state='readonly',width=15).grid(row=1,column=1,padx=(0,8))
    ttk.Combobox(tools,textvariable=app.library_order,values=['Por tempo','Por potencial','Maior duração'],state='readonly',width=15).grid(row=1,column=2)
    ttk.Label(tools,text='Buscar por título, fala ou categoria · Ctrl+F',style='CardMuted.TLabel').grid(row=2,column=0,columnspan=3,sticky='w',pady=(5,0))
    actions=ttk.Frame(parent);actions.pack(fill='x',pady=(0,8))
    app.library_thumbnail_button=ui.button(actions,'Carregar miniaturas',app.library_thumbnails)
    app.library_select_button=ui.button(actions,'Selecionar página',app.library_select_page)
    app.library_export_button=ui.button(actions,'Exportar seleção',app.library_export_selected,True)
    ttk.Label(parent,textvariable=app.library_info,style='Muted.TLabel').pack(anchor='w',pady=(0,8))
    app.library_grid=ttk.Frame(parent);app.library_grid.pack(fill='both',expand=True)
    app._library_columns=0
    def resize(event):
        columns=2 if event.width>=650 else 1
        if columns!=app._library_columns:
            app._library_columns=columns
            app.schedule_library()
    app.library_grid.bind('<Configure>',resize)
    pager=ttk.Frame(parent);pager.pack(fill='x',pady=(8,0))
    app.library_prev=ui.button(pager,'← Anterior',lambda:app.library_page(-1))
    app.library_next=ui.button(pager,'Próxima →',lambda:app.library_page(1))
    ttk.Label(pager,textvariable=app.workspace_selection,style='Muted.TLabel').pack(side='left',padx=8)


def draw_library(app,cuts,reviews):
    for child in app.library_grid.winfo_children():child.destroy()
    app._library_buttons=[];app._library_vars={};app._library_photo_images={};app._library_cards={}
    columns=app._library_columns or 2
    for i in range(2):app.library_grid.columnconfigure(i,weight=1 if i<columns else 0,uniform='clips' if i<columns else '',minsize=0)
    if not cuts:
        label='Nenhum clipe encontrado. Ajuste a busca ou os filtros.' if app.cuts else 'Sua biblioteca está pronta para receber clipes.\nImporte uma gameplay e analise ou crie um corte no editor.'
        ttk.Label(app.library_grid,text=label,style='Muted.TLabel',wraplength=540,padding=22).grid(row=0,column=0,columnspan=columns,sticky='w')
    for i,cut in enumerate(cuts):
        box=ttk.Frame(app.library_grid,style='LibraryCard.TFrame',padding=12)
        box.grid(row=i//columns,column=i%columns,sticky='nsew',padx=(0,10 if i%columns<columns-1 else 0),pady=(0,12))
        canvas=tk.Canvas(box,width=230,height=124,bg='#07101d',highlightthickness=0,cursor='hand2');canvas.pack(fill='x')
        canvas.bind('<Button-1>',lambda e,ident=cut.id:app.library_target(ident))
        def center(event,c=canvas):
            for item in c.find_all():
                xy=c.coords(item)
                if len(xy)==2:c.coords(item,event.width/2,xy[1])
        canvas.bind('<Configure>',center)
        record=app._library_images.get(cut.id)
        path=record['file'] if record and record['stamp']==app.library_stamp(cut) else None
        if path:
            try:
                image=tk.PhotoImage(master=app,file=path)
                ratio=min(1,230/image.width(),120/image.height());factor=max(8,math.ceil(8/ratio))
                image=image.zoom(8).subsample(factor,factor);app._library_photo_images[cut.id]=image
                canvas.create_image(115,62,image=image)
            except (tk.TclError,OSError):path=None
        if not path:
            canvas.create_text(115,48,text='▶',fill=app.accent,font=(ui.FONT,26))
            canvas.create_text(115,91,text='Clique para editar · carregue a miniatura',fill=ui.MUTED,font=(ui.FONT,9))
        ttk.Label(box,text=f'CLIPE {cut.id:02}   ·   {cut.duration:.2f} s   ·   {timestamp(cut.start)}',style='CardMuted.TLabel').pack(anchor='w',pady=(9,5))
        review=reviews.get(cut.id) or {}
        adaptive_label(box,text=review.get('titulo',cut.title),style='ClipTitle.TLabel',wraplength=270).pack(fill='x')
        state={'pending':'Pendente','approved':'Aprovado','rejected':'Descartado'}[cut.review_state]
        captions=' · Legendas '+('ativas' if cut.captions.get('enabled') else 'salvas') if cut.captions.get('cues') else ''
        score='Manual' if cut.manual else f'Local {cut.score:g}/100'
        if review:score+=f' · Gemini {review["nota_editorial"]:g}/100'
        adaptive_label(box,text=f'{state} · {score}{captions}',style='CardMuted.TLabel',wraplength=270).pack(fill='x',pady=(5,8))
        selected=tk.BooleanVar(master=app,value=cut.id in app.library_selected);app._library_vars[cut.id]=selected
        row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
        check=ttk.Checkbutton(row,text='Selecionar',variable=selected,command=lambda ident=cut.id:app.library_select(ident));check.pack(side='left');app._library_buttons.append(check)
        star=ttk.Button(row,text='★ Favorito' if cut.favorite else '☆ Favorito',style='Small.TButton',command=lambda ident=cut.id:app.library_target(ident,'favorite'));star.pack(side='right');app._library_buttons.append(star)
        row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x',pady=(4,0))
        for label,action in [('Editar','review'),('Legendas','captions'),('MP4','mp4')]:
            button=ttk.Button(row,text=label,style='Small.TButton',command=lambda ident=cut.id,a=action:app.library_target(ident,a));button.pack(side='left',padx=(0,6));app._library_buttons.append(button)
        app._library_cards[cut.id]=box


def build_jobs(app,parent):
    parent.columnconfigure(0,weight=1);parent.rowconfigure(4,weight=1)
    summary=ttk.Frame(parent,style='Card.TFrame',padding=14);summary.grid(row=0,column=0,sticky='ew',pady=(0,10))
    adaptive_label(summary,textvariable=app.workspace_task,style='Section.TLabel').pack(fill='x')
    app.workspace_bar=ttk.Progressbar(summary,variable=app.workspace_progress,maximum=100);app.workspace_bar.pack(fill='x',pady=10)
    resources=ttk.Frame(summary,style='Card.TFrame');resources.pack(fill='x')
    for variable in (app.workspace_cpu,app.workspace_ram,app.workspace_disk):ttk.Label(resources,textvariable=variable,style='CardMuted.TLabel').pack(side='left',padx=(0,18))
    row=ttk.Frame(parent);row.grid(row=1,column=0,sticky='ew',pady=(0,8))
    app.workspace_pause=ui.button(row,'Pausar',app.toggle_pause);app.workspace_pause.configure(textvariable=app.pause_text)
    ttk.Button(row,text='Cancelar tarefa',command=app.cancel.set).pack(side='left',padx=(0,8))
    app._run_buttons.append(ui.button(row,'Atualizar histórico',app.refresh_jobs))
    app._run_buttons.append(ui.button(row,'Abrir selecionado',app.workspace_open_job))
    app.workspace_jobs=ttk.Treeview(parent,columns=('source','status','stage'),show='headings',height=4,selectmode='browse')
    for key,label,width in [('source','Arquivo',260),('status','Estado do checkpoint',180),('stage','Última etapa',210)]:
        app.workspace_jobs.heading(key,text=label);app.workspace_jobs.column(key,width=width,minwidth=90)
    app.workspace_jobs.grid(row=2,column=0,sticky='ew');app.workspace_jobs.bind('<Double-1>',app.workspace_open_job)
    ttk.Label(parent,text='ATIVIDADE DESTA SESSÃO',style='Muted.TLabel').grid(row=3,column=0,sticky='w',pady=(12,6))
    pane=ttk.Frame(parent);pane.grid(row=4,column=0,sticky='nsew');pane.rowconfigure(0,weight=1);pane.columnconfigure(0,weight=1)
    app.activity_table=ttk.Treeview(pane,columns=('time','event'),show='headings',height=4)
    app.activity_table.heading('time',text='Hora');app.activity_table.column('time',width=86,minwidth=70,stretch=False)
    app.activity_table.heading('event',text='Operação / progresso');app.activity_table.column('event',width=460,minwidth=150)
    app.activity_table.grid(row=0,column=0,sticky='nsew');scroll=ttk.Scrollbar(pane,command=app.activity_table.yview);scroll.grid(row=0,column=1,sticky='ns');app.activity_table.configure(yscrollcommand=scroll.set)
    adaptive_label(parent,text='Tarefas executam em sequência. Os checkpoints permitem retomar a análise e a fila de MP4; o histórico abaixo consulta os dados já salvos.',style='Muted.TLabel').grid(row=5,column=0,sticky='ew',pady=6)
