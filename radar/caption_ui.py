"""Visual caption workspace, embedded in the existing Radar desktop."""
import tkinter as tk
from tkinter import ttk,font
from . import ui
from .captions import EFFECTS
from .render import MODES


def build(app,parent):
    parent.rowconfigure(1,weight=1);parent.columnconfigure(0,weight=1)
    top=ttk.Frame(parent);top.grid(row=0,column=0,sticky='ew',pady=(0,8));top.columnconfigure(1,weight=1)
    ttk.Label(top,text='Clipe').grid(row=0,column=0,padx=(0,8))
    app.caption_picker=ttk.Combobox(top,textvariable=app.caption_clip,state='readonly',width=24)
    app.caption_picker.grid(row=0,column=1,sticky='ew');app.caption_picker.bind('<<ComboboxSelected>>',app.caption_choose_clip)
    generate=ttk.Button(top,text='Gerar legendas',command=app.caption_generate,style='Primary.TButton')
    generate.grid(row=0,column=2,padx=(8,0));app._cut_buttons.append(generate)
    body=ttk.Frame(parent);body.grid(row=1,column=0,sticky='nsew')
    body.columnconfigure(0,weight=5,minsize=290);body.columnconfigure(1,weight=4,minsize=300);body.rowconfigure(0,weight=1)
    left=ttk.Frame(body);left.grid(row=0,column=0,sticky='nsew',padx=(0,10));left.columnconfigure(0,weight=1);left.rowconfigure(0,weight=3);left.rowconfigure(4,weight=2)
    app.caption_preview_canvas=tk.Canvas(left,bg='#060c16',highlightthickness=1,highlightbackground=ui.BORDER,width=300,height=220,cursor='crosshair')
    app.caption_preview_canvas.grid(row=0,column=0,sticky='nsew')
    app.caption_preview_canvas.bind('<Configure>',app.caption_draw_preview)
    app.caption_preview_canvas.bind('<Button-1>',app.caption_position)
    seek=ttk.Frame(left);seek.grid(row=1,column=0,sticky='ew',pady=4);seek.columnconfigure(0,weight=1)
    app.caption_scale=ttk.Scale(seek,variable=app.caption_cursor,from_=0,to=1,command=app.caption_seek)
    app.caption_scale.grid(row=0,column=0,sticky='ew');ttk.Label(seek,textvariable=app.caption_time).grid(row=0,column=1,padx=(8,0))
    buttons=ttk.Frame(left);buttons.grid(row=2,column=0,sticky='ew')
    for label,action in [('Atualizar prévia',app.caption_request_preview),('▶ Reproduzir 6 s',app.caption_play)]:
        b=ttk.Button(buttons,text=label,command=action,style='Small.TButton');b.pack(side='left',padx=(0,6),pady=3);app._cut_buttons.append(b)
    app.caption_active=tk.StringVar(value='Sem legenda neste instante')
    active=ttk.Label(left,textvariable=app.caption_active,style='Muted.TLabel',wraplength=350)
    active.grid(row=3,column=0,sticky='ew',pady=4);active.bind('<Configure>',lambda e:active.configure(wraplength=max(200,e.width)))
    table=ttk.Frame(left);table.grid(row=4,column=0,sticky='nsew');table.columnconfigure(0,weight=1);table.rowconfigure(0,weight=1)
    app.caption_table=ttk.Treeview(table,columns=('start','end','text'),displaycolumns=('start','text'),show='headings',selectmode='browse',height=4,style='Caption.Treeview')
    for key,label,width in [('start','No Short',106),('end','Fim',106),('text','Legenda',210)]:
        app.caption_table.heading(key,text=label);app.caption_table.column(key,width=width,minwidth=80,stretch=key=='text')
    app.caption_table.grid(row=0,column=0,sticky='nsew');scroll=ttk.Scrollbar(table,command=app.caption_table.yview);scroll.grid(row=0,column=1,sticky='ns');app.caption_table.configure(yscrollcommand=scroll.set)
    app.caption_table.tag_configure('active',background='#123d64')
    app.caption_table.bind('<<TreeviewSelect>>',app.caption_select_cue)
    right=ttk.Notebook(body);right.grid(row=0,column=1,sticky='nsew');app.caption_tabs=right
    text=ui.ScrollPage(right);style=ui.ScrollPage(right);exports=ui.ScrollPage(right)
    for page,label in [(text,'Texto e tempos'),(style,'Estilo'),(exports,'Exportar')]:right.add(page,text=label)
    pane=text.content
    ttk.Label(pane,text='Texto do bloco selecionado').pack(anchor='w',pady=6)
    app.caption_text=tk.Text(pane,height=4,width=1,wrap='word',bg='#0b1627',fg=ui.TEXT,insertbackground=ui.TEXT,relief='flat',padx=8,pady=8)
    app.caption_text.pack(fill='x');app._text_widgets.append(app.caption_text)
    for label,var in [('Início no Short',app.caption_start),('Fim no Short',app.caption_end)]:
        row=ttk.Frame(pane);row.pack(fill='x',pady=4);ttk.Label(row,text=label,width=16).pack(side='left');ttk.Entry(row,textvariable=var,width=14).pack(side='left',fill='x',expand=True)
    row=ttk.Frame(pane);row.pack(fill='x')
    for label,action in [('IN no cursor',lambda:app.caption_mark(True)),('OUT no cursor',lambda:app.caption_mark(False))]:
        b=ttk.Button(row,text=label,command=action,style='Small.TButton');b.pack(side='left',padx=(0,5),pady=4);app._cut_buttons.append(b)
    for label,action in [('Aplicar texto e tempos',app.caption_apply_text),('Sincronizar palavras…',app.caption_words)]:
        b=ttk.Button(pane,text=label,command=action);b.pack(fill='x',pady=3);app._cut_buttons.append(b)
    label=ttk.Label(pane,textvariable=app.caption_word_status,style='Muted.TLabel',wraplength=260);label.pack(fill='x',pady=6);label.bind('<Configure>',lambda e,widget=label:widget.configure(wraplength=max(160,e.width)))
    row=ttk.Frame(pane);row.pack(fill='x')
    for label,action in [('Adicionar bloco',app.caption_add),('Remover',app.caption_delete)]:
        b=ttk.Button(row,text=label,command=action,style='Small.TButton');b.pack(side='left',padx=(0,5),pady=4);app._cut_buttons.append(b)
    ttk.Label(pane,text='Transcrição original (somente leitura)',wraplength=260).pack(anchor='w',pady=(12,4))
    app.caption_original=ui.text_panel(app,pane,height=4)
    pane=style.content
    ttk.Label(pane,text='Animação').pack(anchor='w',pady=(8,4))
    ttk.Combobox(pane,textvariable=app.caption_effect,values=list(EFFECTS.values()),state='readonly').pack(fill='x')
    ttk.Label(pane,text='Fonte').pack(anchor='w',pady=(8,4))
    ttk.Combobox(pane,textvariable=app.caption_style_vars['font'],values=sorted(set(font.families(app))),width=20).pack(fill='x')
    for label,key in [('Tamanho (720p)','size'),('Contorno (0–12)','outline'),('Sombra (0–12)','shadow'),('Posição X (0–1)','x'),('Posição Y (0–1)','y')]:
        row=ttk.Frame(pane);row.pack(fill='x',pady=3);ttk.Label(row,text=label,width=21).pack(side='left');ttk.Entry(row,textvariable=app.caption_style_vars[key],width=7).pack(side='left',fill='x',expand=True)
    ttk.Checkbutton(pane,text='Negrito',variable=app.caption_style_vars['bold']).pack(anchor='w')
    for label,key in [('Texto','color'),('Destaque','highlight'),('Contorno','outline_color'),('Sombra','shadow_color')]:
        row=ttk.Frame(pane);row.pack(fill='x',pady=3);ttk.Label(row,text=label,width=11).pack(side='left');ttk.Entry(row,textvariable=app.caption_style_vars[key],width=9).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='Cor…',command=lambda k=key:app.caption_color(k),style='Small.TButton').pack(side='left',padx=(5,0))
    for label,action in [('Aplicar no clipe (global)',lambda:app.caption_apply_style(True)),('Aplicar neste bloco',app.caption_apply_style),('Usar global neste bloco',app.caption_reset_style),('Salvar como preset…',app.caption_save_preset)]:
        b=ttk.Button(pane,text=label,command=action);b.pack(fill='x',pady=3);app._cut_buttons.append(b)
    ttk.Label(pane,text='Presets personalizados').pack(anchor='w',pady=(10,4))
    app.caption_preset_picker=ttk.Combobox(pane,textvariable=app.caption_preset,values=list(app.caption_presets),state='readonly');app.caption_preset_picker.pack(fill='x');app.caption_preset_picker.bind('<<ComboboxSelected>>',app.caption_load_preset)
    ttk.Label(pane,text='Clique na prévia para posicionar a legenda do bloco. Aplique no clipe para mudar o padrão.',wraplength=260,style='Muted.TLabel').pack(fill='x',pady=8)
    pane=exports.content
    for label,var in [('Legendas ativadas neste clipe',app.caption_enabled),('Preservar qualidade do áudio',app.caption_audio)]:
        ttk.Checkbutton(pane,text=label,variable=var,command=app.caption_toggle).pack(anchor='w',pady=4)
    ttk.Label(pane,text='O texto e os estilos continuam editáveis no projeto, mesmo com as legendas desativadas.',wraplength=260,style='Muted.TLabel').pack(fill='x',pady=8)
    for label,var,values in [('Formato do MP4',app.render_mode_label,list(MODES.values())),('Resolução',app.render_vars['resolution'],['720','1080']),('Qualidade',app.render_vars['preset'],['leve','equilibrado','qualidade'])]:
        ttk.Label(pane,text=label).pack(anchor='w',pady=(6,3));ttk.Combobox(pane,textvariable=var,values=values,state='readonly',width=20).pack(fill='x')
    for label,action in [('Exportar MP4 final',lambda:app.caption_export('mp4')),('Exportar SRT (texto e tempos)',lambda:app.caption_export('srt')),('Exportar ASS (estilos e animações)',lambda:app.caption_export('ass')),('Salvar projeto editável',app.save_studio_project)]:
        b=ttk.Button(pane,text=label,command=action,style='Primary.TButton' if 'MP4' in label else 'TButton');b.pack(fill='x',pady=5);app._cut_buttons.append(b)
    ttk.Label(pane,text='Áudio compatível é copiado; demais codecs usam ALAC ou PCM, preservando a precisão. FFmpeg/libass renderiza em CPU; nenhuma API paga é usada.',wraplength=260,style='Muted.TLabel').pack(fill='x',pady=8)
    status=ttk.Label(parent,textvariable=app.caption_status,style='Muted.TLabel',wraplength=680)
    status.grid(row=2,column=0,sticky='ew',pady=6);status.bind('<Configure>',lambda e:status.configure(wraplength=max(200,e.width)))
