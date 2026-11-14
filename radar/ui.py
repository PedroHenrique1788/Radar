"""CefasGamer desktop presentation, kept separate from media operations."""
import math
import tkinter as tk
from tkinter import ttk, font as tkfont

BLUE='#278cff'
BG='#0a101b'
PANEL='#111e30'
SIDE='#0c1523'
TEXT='#edf4ff'
MUTED='#93a8c4'
BORDER='#263951'
FONT='Segoe UI'


class ScrollPage(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.canvas=tk.Canvas(self,bg=BG,highlightthickness=0)
        scrollbar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y')
        self.canvas.pack(side='left',fill='both',expand=True)
        self.content=ttk.Frame(self.canvas,padding=(4,2,14,16))
        item=self.canvas.create_window((0,0),window=self.content,anchor='nw')
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(item,width=e.width))
        self.content.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.bind('<MouseWheel>',self.wheel)
        self.canvas.bind('<MouseWheel>',self.wheel)
        self.canvas.bind('<Button-4>',lambda e:self.canvas.yview_scroll(-3,'units'))
        self.canvas.bind('<Button-5>',lambda e:self.canvas.yview_scroll(3,'units'))
    def wheel(self,event):
        self.canvas.yview_scroll(-int(event.delta/120),'units')


def theme(app):
    accent=app.accent
    rgb=[int(accent[i:i+2],16)/255 for i in (1,3,5)]
    foreground='#08101b' if .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]>.65 else '#ffffff'
    style=ttk.Style(app)
    style.theme_use('clam')
    style.configure('.',font=(FONT,10),background=BG,foreground=TEXT)
    style.configure('TFrame',background=BG)
    style.configure('Card.TFrame',background=PANEL)
    style.configure('Side.TFrame',background=SIDE)
    style.configure('TLabel',background=BG,foreground=TEXT)
    style.configure('Card.TLabel',background=PANEL)
    style.configure('Muted.TLabel',background=BG,foreground=MUTED)
    style.configure('CardMuted.TLabel',background=PANEL,foreground=MUTED)
    style.configure('Title.TLabel',font=(FONT,23,'bold'))
    style.configure('Section.TLabel',background=PANEL,font=(FONT,12,'bold'))
    style.configure('Brand.TLabel',background=SIDE,font=(FONT,14,'bold'))
    style.configure('BrandSmall.TLabel',background=SIDE,foreground=MUTED,font=(FONT,9))
    style.configure('Hero.TLabel',background=PANEL,font=(FONT,21,'bold'))
    style.configure('Metric.TLabel',background=PANEL,font=(FONT,25,'bold'))
    style.configure('MetricLabel.TLabel',background=PANEL,foreground=MUTED,font=(FONT,9))
    style.configure('ClipTitle.TLabel',background=PANEL,font=(FONT,11,'bold'))
    style.configure('LibraryCard.TFrame',background=PANEL,bordercolor=BORDER,borderwidth=1,relief='solid')
    style.configure('TButton',background='#1d3049',foreground=TEXT,borderwidth=0,padding=(12,8),relief='flat')
    style.map('TButton',background=[('active','#2b4463'),('disabled','#142033')],foreground=[('disabled','#71829a')])
    style.configure('Primary.TButton',background=accent,foreground=foreground,font=(FONT,10,'bold'))
    style.configure('Small.TButton',padding=(5,3),font=(FONT,9))
    style.map('Primary.TButton',background=[('active',accent),('disabled','#233852')],foreground=[('disabled','#71829a')])
    style.configure('Nav.TButton',background=SIDE,anchor='w',padding=(10,7))
    style.configure('NavActive.TButton',background='#163a60',foreground='#ffffff',anchor='w',padding=(10,7),font=(FONT,10,'bold'))
    style.map('NavActive.TButton',background=[('active','#204d78')])
    style.configure('TEntry',fieldbackground='#0a1525',foreground=TEXT,insertcolor=TEXT,bordercolor=BORDER,padding=6)
    style.configure('TCombobox',fieldbackground='#0a1525',background='#1d3049',foreground=TEXT,padding=5,arrowsize=14)
    style.map('TCombobox',fieldbackground=[('readonly','#0a1525')],foreground=[('readonly',TEXT)],selectbackground=[('readonly','#0a1525')])
    style.configure('TCheckbutton',background=PANEL,foreground=TEXT,padding=(0,5))
    style.map('TCheckbutton',background=[('active',PANEL)])
    style.configure('TRadiobutton',background=PANEL,foreground=TEXT,padding=(0,5))
    style.map('TRadiobutton',background=[('active',PANEL)])
    style.configure('TNotebook',background=PANEL,borderwidth=0)
    style.configure('TNotebook.Tab',background='#192d46',padding=(10,7))
    style.map('TNotebook.Tab',background=[('selected','#244c78')])
    style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=40,borderwidth=0,font=(FONT,10))
    style.layout('Treeview',[('Treeview.treearea',{'sticky':'nswe'})])
    style.configure('Vertical.TScrollbar',background='#24364d',troughcolor='#0b1525',bordercolor=PANEL,arrowcolor=MUTED,lightcolor=PANEL,darkcolor=PANEL)
    style.map('Treeview',background=[('selected','#194c80')],foreground=[('selected','#ffffff')])
    style.configure('Treeview.Heading',background='#1a2e47',foreground=MUTED,font=(FONT,9,'bold'),padding=(5,10))
    style.configure('Caption.Treeview',rowheight=30)
    style.configure('Horizontal.TProgressbar',background=accent,troughcolor='#15263e',borderwidth=0)
    app.configure(bg=BG)
    app.option_add('*TCombobox*Listbox.background','#102039')
    app.option_add('*TCombobox*Listbox.foreground',TEXT)
    for widget in getattr(app,'_text_widgets',[]):
        widget.configure(bg='#0b1627',fg=TEXT,insertbackground=TEXT,selectbackground='#245689')
    for page in getattr(app,'pages',{}).values():
        if isinstance(page,ScrollPage):page.canvas.configure(bg=BG)


def card(parent,title=None):
    box=ttk.Frame(parent,style='Card.TFrame',padding=18)
    box.pack(fill='x',pady=(0,14))
    if title:ttk.Label(box,text=title,style='Section.TLabel').pack(anchor='w',pady=(0,10))
    return box


def description(parent,text,width=680):
    label=ttk.Label(parent,text=text,style='CardMuted.TLabel',wraplength=width,justify='left')
    label.pack(anchor='w',fill='x',pady=(0,10))
    label.bind('<Configure>',lambda e:label.configure(wraplength=max(160,e.width)))
    return label


def button(parent,text,command,primary=False,side='left',**kw):
    b=ttk.Button(parent,text=text,command=command,style='Primary.TButton' if primary else 'TButton',**kw)
    b.pack(side=side,padx=(0,8),pady=4)
    return b


def text_panel(app,parent,height=7):
    frame=ttk.Frame(parent,style='Card.TFrame')
    frame.pack(fill='both',expand=True)
    box=tk.Text(frame,wrap='word',height=height,width=1,relief='flat',padx=12,pady=10,font=(FONT,10),state='disabled')
    scroll=ttk.Scrollbar(frame,orient='vertical',command=box.yview)
    box.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right',fill='y')
    box.pack(side='left',fill='both',expand=True)
    app._text_widgets.append(box)
    return box


def build(app):
    global FONT
    families={f.casefold():f for f in tkfont.families(app)}
    FONT=next((families[n] for n in ('segoe ui','dejavu sans','liberation sans','nimbus sans l','helvetica') if n in families),'TkDefaultFont')
    app._text_widgets=[]
    app._nav_buttons={}
    app._cut_buttons=[]
    app._run_buttons=[]
    app._config_buttons=[]
    footer=ttk.Frame(app,padding=(18,10))
    footer.pack(side='bottom',fill='x')
    app.progress=ttk.Progressbar(footer,maximum=100,length=130)
    app.progress.pack(side='left',padx=(0,12))
    ttk.Label(footer,textvariable=app.status,style='Muted.TLabel',wraplength=720).pack(side='left',fill='x',expand=True)
    ttk.Button(footer,text='Cancelar',command=app.cancel.set).pack(side='right',padx=(10,0))
    shell=ttk.Frame(app)
    shell.pack(fill='both',expand=True)
    sidebar=ttk.Frame(shell,style='Side.TFrame',width=204,padding=(12,16))
    sidebar.pack(side='left',fill='y')
    sidebar.pack_propagate(False)
    app.logo_label=tk.Label(sidebar,text='CG',font=(FONT,24,'bold'),bg=app.accent,fg='white',width=4,height=1)
    app.logo_label.pack(anchor='w',pady=(0,8))
    app.brand_label=ttk.Label(sidebar,textvariable=app.channel,style='Brand.TLabel',wraplength=156)
    app.brand_label.pack(anchor='w')
    ttk.Label(sidebar,text='RADAR DE CORTES',style='BrandSmall.TLabel').pack(anchor='w',pady=(3,14))
    for key,label in [('dashboard','Painel'),('video','Importar vídeo'),('analysis','Análise'),('library','Biblioteca de clipes'),('review','Editor de clipes'),('captions','Estúdio de Legendas'),('jobs','Fila e atividade'),('export','Exportar')]:
        b=ttk.Button(sidebar,text=label,style='Nav.TButton',command=lambda k=key:app.show_page(k))
        b.pack(fill='x',pady=2)
        app._nav_buttons[key]=b
    ttk.Label(sidebar,text='Seu conteúdo.\nSua edição.',style='BrandSmall.TLabel').pack(side='bottom',anchor='w',pady=(16,0))
    b=ttk.Button(sidebar,text='Preferências',style='Nav.TButton',command=lambda:app.show_page('settings'))
    b.pack(side='bottom',fill='x',pady=4)
    app._nav_buttons['settings']=b
    main=ttk.Frame(shell,padding=(22,18,18,0))
    main.pack(side='left',fill='both',expand=True)
    header=ttk.Frame(main)
    header.pack(fill='x',pady=(0,16))
    ttk.Label(header,textvariable=app.page_title,style='Title.TLabel').pack(anchor='w')
    ttk.Label(header,textvariable=app.page_subtitle,style='Muted.TLabel',wraplength=760).pack(anchor='w',pady=(5,0))
    app.page_host=ttk.Frame(main)
    app.page_host.pack(fill='both',expand=True)
    app.page_host.rowconfigure(0,weight=1)
    app.page_host.columnconfigure(0,weight=1)
    app.pages={}
    for name in ('dashboard','video','analysis','library','review','captions','jobs','export','settings'):
        page=ttk.Frame(app.page_host) if name in ('review','captions','jobs') else ScrollPage(app.page_host)
        page.grid(row=0,column=0,sticky='nsew')
        app.pages[name]=page
    build_video(app,app.pages['video'].content)
    build_analysis(app,app.pages['analysis'].content)
    build_review(app,app.pages['review'])
    from .workspace_ui import build_dashboard,build_library,build_jobs
    build_dashboard(app,app.pages['dashboard'].content)
    build_library(app,app.pages['library'].content)
    build_jobs(app,app.pages['jobs'])
    from .caption_ui import build as build_captions
    build_captions(app,app.pages['captions'])
    build_export(app,app.pages['export'].content)
    build_settings(app,app.pages['settings'].content)
    theme(app)


def build_video(app,parent):
    box=card(parent)
    ttk.Label(box,text='Comece com a sua gravação',style='Hero.TLabel').pack(anchor='w',pady=(0,10))
    description(box,'Escolha um vídeo do computador. O Radar percorre a gravação e sugere trechos para você revisar.')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x',pady=10)
    app._run_buttons.append(button(row,'Selecionar vídeo',app.choose,True))
    ttk.Entry(box,textvariable=app.path,state='readonly').pack(fill='x',pady=(5,12))
    description(box,'MP4 • MKV • MOV • AVI | Análise local em CPU. A revisão com Gemini é opcional.')
    box=card(parent,'Arquivo selecionado')
    ttk.Label(box,textvariable=app.info,style='Card.TLabel',wraplength=700,justify='left').pack(anchor='w',fill='x')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x',pady=(12,0))
    app.next_analysis=button(row,'Continuar para análise →',lambda:app.show_page('analysis'),True)
    app.studio_open_button=button(row,'Abrir estúdio sem analisar',lambda:(app.show_page('review'),app.studio_tabs.select(1)))
    box=card(parent,'Um fluxo simples')
    description(box,'1. Selecione o vídeo   →   2. Analise   →   3. Revise os cortes   →   4. Exporte\n\nOs horários sempre se referem ao vídeo original. Você decide os limites e o que vai publicar.')
    box=card(parent,'Análises recentes e retomada')
    app.jobs_table=ttk.Treeview(box,columns=('source','status','stage'),show='headings',height=3)
    for key,label in [('source','Gameplay'),('status','Estado'),('stage','Última etapa')]:
        app.jobs_table.heading(key,text=label);app.jobs_table.column(key,width=180,minwidth=80)
    app.jobs_table.pack(fill='x',pady=(0,8))
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    app._run_buttons.append(button(row,'Abrir análise selecionada',app.open_recent_analysis))
    description(box,'O original e as configurações são conferidos antes de reutilizar os lotes. Arquivos de cache antigos são preservados.')
    box=card(parent,'Projetos do estúdio')
    description(box,'Salve cortes manuais, favoritos, falas, classificação e enquadramento. O projeto referencia o vídeo original; não inclui uma cópia dele.')
    ttk.Entry(box,textvariable=app.project_title).pack(fill='x',pady=(0,6))
    ttk.Label(box,textvariable=app.project_status,style='CardMuted.TLabel',wraplength=650).pack(anchor='w',pady=(0,8))
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    for text,command in [('Abrir projeto',app.open_studio_project),('Salvar projeto',app.save_studio_project),('Salvar como…',lambda:app.save_studio_project(True))]:
        app._run_buttons.append(button(row,text,command))
    app.project_picker=ttk.Combobox(box,values=app.recent_projects,state='readonly')
    app.project_picker.pack(fill='x',pady=(8,5))
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    app._run_buttons.append(button(row,'Abrir projeto recente',lambda:app.open_studio_project(app.project_picker.get())))


def build_analysis(app,parent):
    box=card(parent,'Motor local em CPU • Gemini opcional')
    ttk.Label(box,textvariable=app.workflow_status,style='CardMuted.TLabel',wraplength=650).pack(anchor='w',fill='x',pady=(0,8))
    description(box,'Áudio e imagem funcionam sem API ou modelo generativo. Whisper pode acrescentar fala local; Gemini pode revisar os candidatos quando ativado por você.')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    button(row,'Somente Radar (sem API)',app.use_radar_only)
    button(row,'Configurações e Gemini',lambda:app.show_page('settings'))
    box=card(parent,'Execução e checkpoints')
    ttk.Label(box,textvariable=app.execution_info,style='CardMuted.TLabel',wraplength=680,justify='left').pack(anchor='w',fill='x',pady=(0,10))
    ttk.Label(box,textvariable=app.resume_info,style='CardMuted.TLabel',wraplength=680,justify='left').pack(anchor='w',fill='x',pady=(0,8))
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    app._run_buttons.append(button(row,'Analisar vídeo',app.analyze,True))
    app.pause_button=button(row,'Pausar',app.toggle_pause)
    app.pause_button.configure(textvariable=app.pause_text)
    app.resume_analysis_button=button(row,'Retomar análise',app.resume_analysis)
    description(box,'Percentuais são da etapa atual, calculados por segundos, amostras, lotes ou candidatos concluídos. A estimativa de tempo só aparece com dados suficientes. Pausas são confirmadas nos limites das unidades de trabalho.')
    box=card(parent,'Áudio e transcrição')
    description(box,'Em gravações do OBS, escolha o microfone para analisar as falas ou use o mix completo.')
    ttk.Label(box,text='Faixa de áudio',style='Card.TLabel').pack(anchor='w')
    app.track=ttk.Combobox(box,state='readonly',width=40)
    app.track.pack(fill='x',pady=(5,12))
    ttk.Label(box,text='Modelo de fala',style='Card.TLabel').pack(anchor='w')
    app.model=ttk.Combobox(box,values=['tiny','base','small','off'],state='readonly',width=18)
    app.model.set(app.whisper_default);app.model.pack(anchor='w',pady=(5,10))
    description(box,'tiny: leve e incluído no instalador. base/small: mais lentos e podem exigir download. off: somente sinais de áudio e imagem.')
    description(box,'Com tiny/base, a Fase 2 também mede ritmo, procura expressões e preserva preparação/desfecho quando os sinais permitem. O resultado continua sujeito à revisão.')
    box=card(parent,'Microfone separado e sincronização')
    description(box,'Opcional: escolha uma gravação separada do microfone. Ela substitui a faixa do vídeo somente na análise e na transcrição. Os MP4 mantêm as faixas originais do vídeo.')
    ttk.Entry(box,textvariable=app.option_vars['external_audio'],state='readonly').pack(fill='x',pady=(0,8))
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    app._run_buttons.append(button(row,'Escolher áudio externo',app.choose_external_audio))
    app._run_buttons.append(button(row,'Usar áudio do vídeo',app.clear_external_audio))
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x',pady=(8,8))
    ttk.Label(row,text='Início do áudio no vídeo (segundos)',style='Card.TLabel').pack(side='left',padx=(0,10))
    ttk.Entry(row,textvariable=app.option_vars['external_offset'],width=12).pack(side='left')
    description(box,'Exemplo: +2,5 se o início do microfone corresponde a 00:00:02.500 do vídeo; -2,5 se o microfone começou 2,5 s antes. O ajuste é manual, não corrige deriva entre relógios.')
    description(box,'Origem do áudio para estimar a confiança das variações vocais:')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    for label,value in [('Automático','auto'),('Microfone separado','microphone'),('Áudio misturado','mixed')]:
        ttk.Radiobutton(row,text=label,variable=app.option_vars['audio_role'],value=value).pack(side='left',padx=(0,12))
    description(box,'Automático prefere uma faixa identificada como microfone; o arquivo externo é presumido como microfone. No mix, a origem de um som permanece incerta.')
    box=card(parent,'Como você quer os cortes?')
    for label,var in [('Sugestões (1 a 20)',app.count),('Duração mínima (segundos)',app.minimum),('Duração máxima (segundos)',app.maximum)]:
        row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x',pady=4)
        ttk.Label(row,text=label,style='Card.TLabel',width=28).pack(side='left')
        ttk.Entry(row,textvariable=var,width=10).pack(side='left')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x',pady=(14,0))
    app._run_buttons.append(button(row,'Analisar vídeo',app.analyze,True))
    description(box,'O potencial é uma heurística, não uma promessa de viralização. Podem existir menos sugestões do que o limite solicitado.')


def build_review(app,parent):
    parent.columnconfigure(0,weight=6,minsize=270)
    parent.columnconfigure(1,weight=5,minsize=300)
    parent.rowconfigure(0,weight=1)
    left=ttk.Frame(parent,style='Card.TFrame',padding=12)
    left.grid(row=0,column=0,sticky='nsew',padx=(0,12),pady=(0,10))
    left.rowconfigure(3,weight=1);left.columnconfigure(0,weight=1)
    preview=ttk.Frame(left,style='Card.TFrame',height=220)
    preview.grid(row=0,column=0,columnspan=2,sticky='ew',pady=(0,10))
    preview.pack_propagate(False)
    parent.bind('<Configure>',lambda e:preview.configure(height=max(180,min(300,int(e.height*.48)))))
    app.studio_tabs=ttk.Notebook(preview);app.studio_tabs.pack(fill='both',expand=True)
    image_tab=ttk.Frame(app.studio_tabs);timeline_tab=ttk.Frame(app.studio_tabs)
    app.studio_tabs.add(image_tab,text='Prévia');app.studio_tabs.add(timeline_tab,text='Timeline')
    app.preview_label=tk.Label(image_tab,text='Prévia do vídeo\nSelecione um corte e clique aqui para ver o enquadramento.',bg='#08111f',fg=MUTED,font=(FONT,11),wraplength=300)
    app.preview_label.pack(fill='both',expand=True)
    app.preview_label.configure(cursor='hand2')
    app.preview_label.bind('<Button-1>',lambda e:app.load_preview_frame())
    row=ttk.Frame(timeline_tab);row.pack(fill='x')
    from .timeline import Timeline
    app.timeline=Timeline(timeline_tab,on_seek=app.timeline_seek,on_select=app.timeline_select,on_range=app.timeline_range)
    for text,command,width in [('−',lambda:app.timeline.zoom(2),2),('+',lambda:app.timeline.zoom(.5),2),
                               ('Tudo',lambda:app.timeline.reset_view(),4),('IN',lambda:app.mark_cursor(True),2),
                               ('OUT',lambda:app.mark_cursor(False),3),('Criar',app.create_manual_cut,5),('Ondas',app.load_waveform,5)]:
        b=ttk.Button(row,text=text,command=command,width=width,style='Small.TButton');b.pack(side='left',padx=1,pady=2)
        if text in ('Criar','Ondas','IN','OUT'):app._run_buttons.append(b)
    cursor_row=ttk.Frame(timeline_tab,height=52);cursor_row.pack(side='bottom',fill='x');cursor_row.pack_propagate(False)
    ttk.Label(cursor_row,textvariable=app.cursor_time,style='Muted.TLabel').pack(side='left',padx=4)
    mini=ttk.Frame(cursor_row,width=96,height=50);mini.pack(side='right');mini.pack_propagate(False)
    app.timeline_preview=tk.Label(mini,text='Prévia',bg='#081322',fg=MUTED)
    app.timeline_preview.pack(fill='both',expand=True)
    app.timeline.pack(fill='both',expand=True)
    info=ttk.Frame(left,style='Card.TFrame');info.grid(row=1,column=0,sticky='ew',pady=(0,6))
    picker=ttk.Combobox(info,textvariable=app.review_filter,values=['Todos','Favoritos','Aprovados','Pendentes'],state='readonly',width=10)
    picker.pack(side='right');picker.bind('<<ComboboxSelected>>',lambda e:app.refresh())
    ttk.Label(info,textvariable=app.cut_count,style='CardMuted.TLabel').pack(side='left')
    order=ttk.Frame(left,style='Card.TFrame');order.grid(row=2,column=0,sticky='ew',pady=(0,8))
    button(order,'Por tempo',lambda:app.sort('start'))
    button(order,'Por potencial',lambda:app.sort('potential'))
    columns=('id','start','end','duration','score','category','title','ai','favorite','state')
    app.table=ttk.Treeview(left,columns=columns,show='headings',selectmode='extended',height=7,
                           displaycolumns=('favorite','start','score','ai','title'))
    for col,label,width in [('id','#',35),('start','Momento',112),('end','Fim',110),('duration','Duração',75),
                            ('score','Local',50),('category','Potencial',120),('title','Título',190),('ai','Gemini',60),('favorite','★',28),('state','Revisão',100)]:
        app.table.heading(col,text=label,command=lambda key=col:app.sort(key))
        app.table.column(col,width=width,minwidth=45,stretch=col=='title')
    app.table.column('favorite',minwidth=24,width=28);app.table.column('start',width=112)
    app.table.grid(row=3,column=0,sticky='nsew')
    scroll=ttk.Scrollbar(left,orient='vertical',command=app.table.yview)
    scroll.grid(row=3,column=1,sticky='ns')
    app.table.configure(yscrollcommand=scroll.set)
    app.table.bind('<<TreeviewSelect>>',app.show_detail)
    row=ttk.Frame(left,style='Card.TFrame');row.grid(row=4,column=0,sticky='ew',pady=(8,0))
    button(row,'Todos',lambda:app.table.selection_set(app.table.get_children()))
    button(row,'Tempos',app.copy)
    app._run_buttons.append(button(row,'Salvar',app.save_studio_project))
    right=ttk.Frame(parent,style='Card.TFrame',padding=12)
    right.grid(row=0,column=1,sticky='nsew',pady=(0,10))
    right.columnconfigure(0,weight=1);right.rowconfigure(4,weight=1)
    ttk.Label(right,textvariable=app.selected_title,style='Section.TLabel',wraplength=310).grid(row=0,column=0,sticky='ew',pady=(0,7))
    ttk.Label(right,textvariable=app.selected_score,style='CardMuted.TLabel').grid(row=1,column=0,sticky='w',pady=(0,7))
    bounds=ttk.Frame(right,style='Card.TFrame');bounds.grid(row=2,column=0,sticky='ew')
    bounds.columnconfigure(0,weight=1);bounds.columnconfigure(1,weight=1)
    for i,(label,var) in enumerate([('Início no original',app.cut_start),('Fim no original',app.cut_end)]):
        ttk.Label(bounds,text=label,style='CardMuted.TLabel').grid(row=0,column=i,sticky='w')
        ttk.Entry(bounds,textvariable=var,width=14).grid(row=1,column=i,sticky='ew',padx=(0,5),pady=5)
    row=ttk.Frame(right,style='Card.TFrame');row.grid(row=3,column=0,sticky='ew',pady=(2,6))
    app._cut_buttons.append(button(row,'▶ Reproduzir',app.preview))
    app._cut_buttons.append(button(row,'Aplicar limites',app.apply_limits))
    app.review_tabs=ttk.Notebook(right,height=140)
    app.review_tabs.grid(row=4,column=0,sticky='nsew')
    for title,attribute in [('Resumo','detail'),('Falas','transcript_view'),('Gemini','ai_view')]:
        tab=ttk.Frame(app.review_tabs,style='Card.TFrame')
        app.review_tabs.add(tab,text=title)
        setattr(app,attribute,text_panel(app,tab,5))
    organize=ScrollPage(app.review_tabs);app.review_tabs.add(organize,text='Organizar');pane=organize.content
    ttk.Label(pane,text='Título e observação de edição').pack(anchor='w')
    ttk.Entry(pane,textvariable=app.edit_title).pack(fill='x',pady=4)
    ttk.Entry(pane,textvariable=app.edit_notes).pack(fill='x',pady=4)
    ttk.Combobox(pane,textvariable=app.review_label,values=['Pendente','Aprovado','Descartado'],state='readonly').pack(fill='x',pady=4)
    row=ttk.Frame(pane);row.pack(fill='x')
    app._cut_buttons.append(button(row,'★ Favorito',app.toggle_favorite))
    app._cut_buttons.append(button(row,'Aplicar',app.apply_review,True))
    row=ttk.Frame(pane);row.pack(fill='x')
    app._cut_buttons.append(button(row,'Remover corte manual',app.remove_manual_cut))
    legends=ttk.Frame(app.review_tabs,padding=10);app.review_tabs.add(legends,text='Legendas')
    ttk.Label(legends,text='Crie e corrija legendas deste Short com a transcrição local.',wraplength=280).pack(anchor='w')
    app._cut_buttons.append(button(legends,'Abrir Estúdio de Legendas',app.open_captions,True))
    ai=ttk.Frame(right,style='Card.TFrame');ai.grid(row=5,column=0,sticky='ew',pady=(7,0))
    app._cut_buttons.append(button(ai,'Revisar seleção',app.review_gemini,True))
    app.resume_gemini_button=button(ai,'Retomar fluxo',app.retry_gemini)
    export=ttk.Frame(right,style='Card.TFrame');export.grid(row=6,column=0,sticky='ew',pady=(3,0))
    for text,command in [('TXT',app.transcript),('SRT',app.srt),('Exportar MP4',app.export_video)]:
        app._cut_buttons.append(button(export,text,command,primary=text=='Exportar MP4'))


def build_export(app,parent):
    from .render import MODES
    box=card(parent,'Formato, qualidade e legendas')
    description(box,'Formato, qualidade e legendas valem para MP4, fila e reprodução. Para mudar um recorte individual, ajuste as posições, veja o enquadramento e clique Usar posição neste corte. Salvar preset muda o padrão dos cortes sem posição individual. FilmCraft usa o original.')
    for text,var,values in [('Formato',app.render_mode_label,list(MODES.values())),('Resolução do lado menor',app.render_vars['resolution'],['720','1080']),
                            ('Qualidade',app.render_vars['preset'],['leve','equilibrado','qualidade'])]:
        row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x',pady=4)
        ttk.Label(row,text=text,style='Card.TLabel',width=26).pack(side='left')
        ttk.Combobox(row,textvariable=var,values=values,state='readonly',width=36).pack(side='left',fill='x',expand=True)
    for text,key in [('Posição horizontal (0 esquerda / 1 direita)','crop_x'),('Posição vertical (0 topo / 1 base)','crop_y')]:
        row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x',pady=4)
        ttk.Label(row,text=text,style='Card.TLabel',width=42).pack(side='left')
        ttk.Entry(row,textvariable=app.render_vars[key],width=8).pack(side='left')
    ttk.Checkbutton(box,text='Gravar legendas (também altera os cortes selecionados)',variable=app.render_vars['burn_subtitles'],command=app.caption_legacy_toggle).pack(anchor='w')
    description(box,'Legendas usam a transcrição selecionada. Um microfone externo usado na análise precisa ser adicionado no editor se não estiver audível no vídeo original.')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    app._config_buttons.append(button(row,'Salvar preset',app.save_rendering))
    app._cut_buttons.append(button(row,'Usar posição neste corte',app.apply_framing))
    app._run_buttons.append(button(row,'Ver enquadramento',app.load_preview_frame))
    ttk.Label(box,textvariable=app.wave_status,style='CardMuted.TLabel',wraplength=650).pack(anchor='w',pady=(8,0))
    box=card(parent,'Vídeos e relatórios')
    description(box,'MP4 individual usa o primeiro selecionado. A fila exporta a seleção, verifica os clipes prontos e permite retomar na mesma pasta. O relatório reúne todos os resultados.')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    app._cut_buttons.append(button(row,'Exportar corte MP4',app.export_video,True))
    app._cut_buttons.append(button(row,'Selecionados em fila',app.export_batch))
    app._cut_buttons.append(button(row,'Relatório JSON / CSV',app.report))
    box=card(parent,'Falas, legendas e revisão')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    for text,command in [('Transcrição TXT',app.transcript),('Legenda SRT',app.srt),('Copiar para ChatGPT',app.copy_for_chatgpt)]:
        app._cut_buttons.append(button(row,text,command))
    description(box,'TXT usa os horários originais. SRT usa tempos relativos ao corte. Copiar para ChatGPT prepara uma revisão manual.')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    app.ai_export_button=button(row,'Salvar revisão Gemini JSON',app.export_gemini)
    box=card(parent,'Continuar a edição no FilmCraft')
    ttk.Label(box,textvariable=app.filmcraft_status,style='CardMuted.TLabel',wraplength=650).pack(anchor='w',pady=(0,10))
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    button(row,'Conectar ao FilmCraft',app.connect)
    button(row,'Escolher instalação…',lambda:app.connect(True))
    for choices in [[('Selecionados em um projeto',lambda:app.film(False,True)),('Todos em um projeto',lambda:app.film(False,False))],
                    [('Um projeto por Short',lambda:app.film(True,False)),('Abrir projeto para edição',app.open_film)]]:
        row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
        for text,command in choices:
            b=button(row,text,command)
            if text!='Abrir projeto para edição':app._cut_buttons.append(b)
    description(box,'Cada operação cria uma subpasta nova. Seu projeto anterior é preservado. Sem CLI compatível, há exportação OTIO.')


def build_settings(app,parent):
    box=card(parent,'Desempenho em CPU')
    ttk.Label(box,textvariable=app.option_vars['profile'],style='Section.TLabel',wraplength=650).pack(anchor='w',pady=(0,10))
    description(box,'O modo econômico usa etapas sequenciais e lotes limitados. A MX110 não é necessária. O limite de RAM é uma proteção verificada durante o trabalho; não é uma reserva feita no Windows.')
    rows=[('Threads de CPU','threads'),('Máximo de processos da tarefa (1 ou 2)','max_processes'),
          ('Limite de RAM aproximada (MB)','memory_mb'),('Amostras visuais por segundo (0.25 / 0.5 / 1 / 2)','sample_fps'),
          ('Largura da análise visual (64 / 128 / 192)','visual_width'),('Lote em segundos (16–300, múltiplo de 4)','batch_seconds'),
          ('Contexto anterior ao evento (segundos)','before'),('Contexto posterior (segundos)','after')]
    for text,key in rows:
        row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x',pady=3)
        ttk.Label(row,text=text,style='Card.TLabel',width=49).pack(side='left')
        ttk.Entry(row,textvariable=app.option_vars[key],width=10).pack(side='left')
    for key,text in [('audio','Analisar áudio'),('visual','Analisar imagem por amostragem')]:
        ttk.Checkbutton(box,text=text,variable=app.option_vars[key]).pack(anchor='w')
    description(box,'Pesos relativos: sinais ausentes não entram na soma e os demais pesos são normalizados. Áudio alto constante não é tratado automaticamente como destaque ou reação do criador.')
    for key,label in [('gancho_fala','Gancho na fala'),('variação_sonora','Variação sonora'),('atividade_visual','Atividade visual'),('fala_completa','Contexto de fala'),
                      ('reação_vocal','Possível reação vocal'),('ritmo_fala','Mudança de ritmo'),('continuidade','Preparação e desfecho')]:
        row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x',pady=3)
        ttk.Label(row,text=label,style='Card.TLabel',width=32).pack(side='left')
        ttk.Entry(row,textvariable=app.weight_vars[key],width=10).pack(side='left')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x',pady=(8,0))
    app._config_buttons.append(button(row,'Aplicar Modo Econômico — Lenovo MX110',app.economy_profile))
    app._config_buttons.append(button(row,'Salvar desempenho',app.save_analysis_options,True))
    box=card(parent,'Expressões do seu canal')
    description(box,'Uma expressão por linha (ou separada por ponto e vírgula), até 100. A busca ignora maiúsculas e acentos e procura palavras inteiras. Deixe vazio para desligar as expressões; pausas, ritmo e outros sinais continuam disponíveis.')
    app.phrase_editor=tk.Text(box,height=6,width=1,wrap='word',relief='flat',padx=10,pady=8,font=(FONT,10))
    app.phrase_editor.pack(fill='x',pady=(0,8));app._text_widgets.append(app.phrase_editor)
    app.sync_phrase_editor()
    app.phrase_editor.bind('<<Modified>>',app.phrase_edited)
    app.option_vars['phrases'].trace_add('write',app.sync_phrase_editor)
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    app._config_buttons.append(button(row,'Restaurar expressões padrão',app.reset_phrases))
    app._config_buttons.append(button(row,'Salvar expressões e pesos',app.save_analysis_options,True))
    box=card(parent,'Gemini • revisão adicional opcional')
    description(box,'Após cada análise local, o Gemini revisa automaticamente as falas dos candidatos e ordena os melhores cortes. Só texto, horários e critérios dos candidatos são enviados ao Google; o vídeo fica no computador.')
    ttk.Label(box,textvariable=app.workflow_status,style='CardMuted.TLabel',wraplength=650).pack(anchor='w',fill='x',pady=(0,8))
    ttk.Label(box,textvariable=app.gemini_status,style='Card.TLabel',wraplength=650).pack(anchor='w',pady=(0,10))
    ttk.Label(box,text='Chave do Google AI Studio',style='Card.TLabel').pack(anchor='w')
    app.key_entry=ttk.Entry(box,textvariable=app.gemini_key_input,show='•')
    app.key_entry.pack(fill='x',pady=(5,8))
    app.remember_key_button=ttk.Checkbutton(box,text='Salvar protegida para este usuário do Windows',variable=app.remember_key)
    app.remember_key_button.pack(anchor='w')
    if app.non_windows:app.remember_key_button.configure(state='disabled')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    app._config_buttons.append(button(row,'Guardar chave',app.save_gemini_key))
    app._config_buttons.append(button(row,'Remover chave salva',app.forget_gemini_key))
    app._config_buttons.append(button(row,'Validar e listar modelos',app.connect_gemini,True))
    ttk.Label(box,text='Modelo da sua conta',style='Card.TLabel').pack(anchor='w',pady=(12,4))
    app.gemini_model_picker=ttk.Combobox(box,textvariable=app.gemini_model,state='readonly',width=40)
    app.gemini_model_picker.pack(fill='x')
    if app.gemini_model.get():app.gemini_model_picker['values']=[app.gemini_model.get()]
    ttk.Checkbutton(box,text='Pesquisar tendências com Google Search (opcional)',variable=app.gemini_search).pack(anchor='w',pady=5)
    description(box,'Validar a chave não consulta saldo nem garante gratuidade. Confira cota e faturamento no AI Studio. O Radar não impede cobranças de um projeto com faturamento ativo. Pesquisa pode ter limites/custos próprios; não há troca de modelo nem novas tentativas automáticas após erro.')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    app._config_buttons.append(button(row,'Usar Radar + Gemini',app.enable_gemini,True))
    app._config_buttons.append(button(row,'Somente Radar',app.use_radar_only))
    app._config_buttons.append(button(row,'Salvar preferências',app.save_gemini_preferences))
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    button(row,'Criar / gerenciar chave',app.open_ai_studio)
    button(row,'Conferir cota no AI Studio',app.open_gemini_quota)
    box=card(parent,'Identidade do canal')
    ttk.Label(box,text='Nome do canal',style='Card.TLabel').pack(anchor='w')
    ttk.Entry(box,textvariable=app.channel,width=40).pack(fill='x',pady=(5,10))
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    button(row,'Escolher azul / cor principal',app.choose_accent)
    button(row,'Escolher logotipo PNG',app.choose_logo)
    button(row,'Salvar identidade',app.save_brand,True)
    box=card(parent,'Sobre o potencial dos cortes')
    description(box,'A pontuação local é uma heurística. O Gemini acrescenta uma opinião editorial separada. Tendências pesquisadas ajudam na revisão; não garantem viralização.')


def gemini_failure(app,title,text):
    dialog=tk.Toplevel(app)
    dialog.title(title)
    dialog.geometry(f'680x{min(540,app.winfo_screenheight()-100)}')
    dialog.transient(app)
    frame=ttk.Frame(dialog,padding=20);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text=title,style='Title.TLabel',wraplength=630).pack(anchor='w',pady=(0,12))
    ttk.Label(frame,text=text,wraplength=630,justify='left').pack(anchor='w',fill='x',pady=(0,16))
    for label,command in [('Continuar só com o Radar',app.use_radar_only),
                          ('Aguardar e tentar depois',app.wait_for_gemini),
                          ('Configurar Gemini',lambda:(app.wait_for_gemini(),app.show_page('settings'))),
                          ('Conferir cota no AI Studio',app.open_gemini_quota)]:
        ttk.Button(frame,text=label,command=command).pack(fill='x',pady=3)
    dialog.protocol('WM_DELETE_WINDOW',app.wait_for_gemini)
    dialog.grab_set()
    return dialog


def analysis_failure(app,error):
    from .checkpoints import STAGES
    dialog=tk.Toplevel(app)
    dialog.title('Análise interrompida • checkpoints preservados')
    dialog.geometry(f'760x{min(500,app.winfo_screenheight()-100)}')
    dialog.transient(app)
    frame=ttk.Frame(dialog,padding=18);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text=STAGES.get(error.stage,error.stage),style='Title.TLabel',wraplength=700).pack(anchor='w',pady=(0,10))
    box=text_panel(app,frame,7)
    app._set_text(box,str(error))
    row=ttk.Frame(frame);row.pack(fill='x',pady=(12,0))
    button(row,'Retomar análise',app.resume_analysis,True)
    if error.stage in ('extract','audio','visual'):
        button(row,'Continuar sem este módulo',lambda:app.skip_failed_module(error.stage))
    button(row,'Fechar',app._dismiss_analysis_error)
    dialog.protocol('WM_DELETE_WINDOW',app._dismiss_analysis_error)
    return dialog
