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
    style.configure('TButton',background='#1d3049',foreground=TEXT,borderwidth=0,padding=(12,8),relief='flat')
    style.map('TButton',background=[('active','#2b4463'),('disabled','#142033')],foreground=[('disabled','#71829a')])
    style.configure('Primary.TButton',background=accent,foreground=foreground,font=(FONT,10,'bold'))
    style.map('Primary.TButton',background=[('active',accent),('disabled','#233852')],foreground=[('disabled','#71829a')])
    style.configure('Nav.TButton',background=SIDE,anchor='w',padding=(10,12))
    style.configure('NavActive.TButton',background='#163a60',foreground='#ffffff',anchor='w',padding=(10,12),font=(FONT,10,'bold'))
    style.map('NavActive.TButton',background=[('active','#204d78')])
    style.configure('TEntry',fieldbackground='#0a1525',foreground=TEXT,insertcolor=TEXT,bordercolor=BORDER,padding=6)
    style.configure('TCombobox',fieldbackground='#0a1525',background='#1d3049',foreground=TEXT,padding=5,arrowsize=14)
    style.map('TCombobox',fieldbackground=[('readonly','#0a1525')],foreground=[('readonly',TEXT)],selectbackground=[('readonly','#0a1525')])
    style.configure('TCheckbutton',background=PANEL,foreground=TEXT,padding=(0,5))
    style.map('TCheckbutton',background=[('active',PANEL)])
    style.configure('TNotebook',background=PANEL,borderwidth=0)
    style.configure('TNotebook.Tab',background='#192d46',padding=(10,7))
    style.map('TNotebook.Tab',background=[('selected','#244c78')])
    style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=40,borderwidth=0,font=(FONT,10))
    style.layout('Treeview',[('Treeview.treearea',{'sticky':'nswe'})])
    style.configure('Vertical.TScrollbar',background='#24364d',troughcolor='#0b1525',bordercolor=PANEL,arrowcolor=MUTED,lightcolor=PANEL,darkcolor=PANEL)
    style.map('Treeview',background=[('selected','#194c80')],foreground=[('selected','#ffffff')])
    style.configure('Treeview.Heading',background='#1a2e47',foreground=MUTED,font=(FONT,9,'bold'),padding=(5,10))
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
    footer=ttk.Frame(app,padding=(18,10))
    footer.pack(side='bottom',fill='x')
    app.progress=ttk.Progressbar(footer,maximum=100,length=130)
    app.progress.pack(side='left',padx=(0,12))
    ttk.Label(footer,textvariable=app.status,style='Muted.TLabel',wraplength=720).pack(side='left',fill='x',expand=True)
    ttk.Button(footer,text='Cancelar',command=app.cancel.set).pack(side='right',padx=(10,0))
    shell=ttk.Frame(app)
    shell.pack(fill='both',expand=True)
    sidebar=ttk.Frame(shell,style='Side.TFrame',width=204,padding=(12,22))
    sidebar.pack(side='left',fill='y')
    sidebar.pack_propagate(False)
    app.logo_label=tk.Label(sidebar,text='CG',font=(FONT,24,'bold'),bg=app.accent,fg='white',width=4,height=1)
    app.logo_label.pack(anchor='w',pady=(0,12))
    app.brand_label=ttk.Label(sidebar,textvariable=app.channel,style='Brand.TLabel',wraplength=156)
    app.brand_label.pack(anchor='w')
    ttk.Label(sidebar,text='RADAR DE CORTES',style='BrandSmall.TLabel').pack(anchor='w',pady=(3,26))
    for key,label in [('video','1  Selecionar vídeo'),('analysis','2  Analisar'),('review','3  Revisar cortes'),('export','4  Exportar')]:
        b=ttk.Button(sidebar,text=label,style='Nav.TButton',command=lambda k=key:app.show_page(k))
        b.pack(fill='x',pady=3)
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
    for name in ('video','analysis','review','export','settings'):
        page=ttk.Frame(app.page_host) if name=='review' else ScrollPage(app.page_host)
        page.grid(row=0,column=0,sticky='nsew')
        app.pages[name]=page
    build_video(app,app.pages['video'].content)
    build_analysis(app,app.pages['analysis'].content)
    build_review(app,app.pages['review'])
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
    box=card(parent,'Um fluxo simples')
    description(box,'1. Selecione o vídeo   →   2. Analise   →   3. Revise os cortes   →   4. Exporte\n\nOs horários sempre se referem ao vídeo original. Você decide os limites e o que vai publicar.')


def build_analysis(app,parent):
    box=card(parent,'Áudio e transcrição')
    description(box,'Em gravações do OBS, escolha o microfone para analisar as falas ou use o mix completo.')
    ttk.Label(box,text='Faixa de áudio',style='Card.TLabel').pack(anchor='w')
    app.track=ttk.Combobox(box,state='readonly',width=40)
    app.track.pack(fill='x',pady=(5,12))
    ttk.Label(box,text='Modelo de fala',style='Card.TLabel').pack(anchor='w')
    app.model=ttk.Combobox(box,values=['tiny','base','small','off'],state='readonly',width=18)
    app.model.set('tiny');app.model.pack(anchor='w',pady=(5,10))
    description(box,'tiny: leve e incluído no instalador. base/small: mais lentos e podem exigir download. off: somente sinais de áudio e imagem.')
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
    preview=ttk.Frame(left,style='Card.TFrame',height=150)
    preview.grid(row=0,column=0,columnspan=2,sticky='ew',pady=(0,10))
    preview.pack_propagate(False)
    parent.bind('<Configure>',lambda e:preview.configure(height=max(110,min(260,int(e.height*.37)))))
    app.preview_label=tk.Label(preview,text='Prévia do vídeo\nSelecione um corte e clique aqui para ver um quadro.',bg='#08111f',fg=MUTED,font=(FONT,11),wraplength=300)
    app.preview_label.pack(fill='both',expand=True)
    app.preview_label.configure(cursor='hand2')
    app.preview_label.bind('<Button-1>',lambda e:app.load_preview_frame())
    ttk.Label(left,textvariable=app.cut_count,style='Section.TLabel').grid(row=1,column=0,sticky='w',pady=(0,8))
    order=ttk.Frame(left,style='Card.TFrame');order.grid(row=2,column=0,sticky='ew',pady=(0,8))
    button(order,'Por tempo',lambda:app.sort('start'))
    button(order,'Por potencial',lambda:app.sort('score'))
    columns=('id','start','end','duration','score','category','title','ai')
    app.table=ttk.Treeview(left,columns=columns,show='headings',selectmode='extended',height=7,
                           displaycolumns=('start','score','ai','title'))
    for col,label,width in [('id','#',35),('start','Momento',112),('end','Fim',110),('duration','Duração',75),
                            ('score','Local',55),('category','Potencial',120),('title','Título',190),('ai','Gemini',70)]:
        app.table.heading(col,text=label,command=lambda key=col:app.sort(key))
        app.table.column(col,width=width,minwidth=45,stretch=col=='title')
    app.table.grid(row=3,column=0,sticky='nsew')
    scroll=ttk.Scrollbar(left,orient='vertical',command=app.table.yview)
    scroll.grid(row=3,column=1,sticky='ns')
    app.table.configure(yscrollcommand=scroll.set)
    app.table.bind('<<TreeviewSelect>>',app.show_detail)
    row=ttk.Frame(left,style='Card.TFrame');row.grid(row=4,column=0,sticky='ew',pady=(8,0))
    button(row,'Selecionar todos',lambda:app.table.selection_set(app.table.get_children()))
    button(row,'Copiar tempos',app.copy)
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
    ai=ttk.Frame(right,style='Card.TFrame');ai.grid(row=5,column=0,sticky='ew',pady=(7,0))
    app._cut_buttons.append(button(ai,'Revisar com Gemini',app.review_gemini,True))
    button(ai,'Configurar',lambda:app.show_page('settings'))
    export=ttk.Frame(right,style='Card.TFrame');export.grid(row=6,column=0,sticky='ew',pady=(3,0))
    for text,command in [('TXT',app.transcript),('SRT',app.srt),('Exportar MP4',app.export_video)]:
        app._cut_buttons.append(button(export,text,command,primary=text=='Exportar MP4'))


def build_export(app,parent):
    box=card(parent,'Vídeos e relatórios')
    description(box,'Use a seleção da tela de revisão. MP4 exporta o primeiro corte selecionado; o relatório reúne todos os resultados.')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    app._cut_buttons.append(button(row,'Exportar corte MP4',app.export_video,True))
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
    box=card(parent,'Identidade do canal')
    ttk.Label(box,text='Nome do canal',style='Card.TLabel').pack(anchor='w')
    ttk.Entry(box,textvariable=app.channel,width=40).pack(fill='x',pady=(5,10))
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    button(row,'Escolher azul / cor principal',app.choose_accent)
    button(row,'Escolher logotipo PNG',app.choose_logo)
    button(row,'Salvar identidade',app.save_brand,True)
    description(box,'A cor azul é a referência informada por você. O logotipo pode ser escolhido do computador; a imagem original permanece intacta.')
    box=card(parent,'Gemini • revisão opcional')
    description(box,'Envia somente as transcrições e os horários dos cortes escolhidos ao Google. Nenhum vídeo é enviado. A análise local funciona sem chave.')
    ttk.Label(box,textvariable=app.gemini_status,style='Card.TLabel',wraplength=650).pack(anchor='w',pady=(0,10))
    ttk.Label(box,text='Chave do Google AI Studio',style='Card.TLabel').pack(anchor='w')
    app.key_entry=ttk.Entry(box,textvariable=app.gemini_key_input,show='•')
    app.key_entry.pack(fill='x',pady=(5,8))
    app.remember_key_button=ttk.Checkbutton(box,text='Salvar protegida para este usuário do Windows',variable=app.remember_key)
    app.remember_key_button.pack(anchor='w')
    if app.non_windows:app.remember_key_button.configure(state='disabled')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    button(row,'Guardar chave',app.save_gemini_key)
    button(row,'Remover chave salva',app.forget_gemini_key)
    button(row,'Validar e listar modelos',app.connect_gemini,True)
    ttk.Label(box,text='Modelo da sua conta',style='Card.TLabel').pack(anchor='w',pady=(12,4))
    app.gemini_model_picker=ttk.Combobox(box,textvariable=app.gemini_model,state='readonly',width=40)
    app.gemini_model_picker.pack(fill='x')
    if app.gemini_model.get():app.gemini_model_picker['values']=[app.gemini_model.get()]
    ttk.Checkbutton(box,text='Pesquisar tendências com Google Search (opcional)',variable=app.gemini_search).pack(anchor='w',pady=5)
    description(box,'A cota gratuita e eventual cobrança dependem do projeto/modelo no Google. Pesquisa pode ter limites ou custos próprios. Confira no AI Studio. O Radar não ativa faturamento nem troca de modelo por conta própria.')
    row=ttk.Frame(box,style='Card.TFrame');row.pack(fill='x')
    button(row,'Salvar preferências Gemini',app.save_gemini_preferences,True)
    button(row,'Abrir Google AI Studio',app.open_ai_studio)
    box=card(parent,'Sobre o potencial dos cortes')
    description(box,'A pontuação local é uma heurística. O Gemini acrescenta uma opinião editorial separada. Tendências pesquisadas ajudam na revisão; não garantem viralização.')
