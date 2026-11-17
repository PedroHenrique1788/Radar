"""Format/framing controls for the caption studio; rendering stays in services."""
import math
import tkinter as tk
from tkinter import ttk

from .render import MODES


def _description(parent,text):
    label=ttk.Label(parent,text=text,style='Muted.TLabel',wraplength=255,justify='left')
    label.pack(fill='x',pady=(4,8))
    label.bind('<Configure>',lambda event:label.configure(wraplength=max(120,event.width)))
    return label


def build_layout(app,parent):
    """Build inside a ScrollPage's content, including narrow notebook panels.

    Global output variables are shared with Exportar. Crop coordinates remain
    staged until the explicit per-clip action handled by CaptionDesktop.
    """
    ttk.Label(parent,text='Formato e enquadramento',style='Section.TLabel').pack(anchor='w',pady=(8,4))
    _description(parent,'Escolha como o vídeo aparece junto das legendas. A prévia e o MP4 usam os mesmos formatos existentes do Radar.')
    ttk.Label(parent,text='Modelos rápidos').pack(anchor='w',pady=(4,3))
    app.caption_layout_preset_buttons={}
    for mode,label in [('original','Original'),('landscape','Horizontal 16:9'),
                       ('vertical_crop','Vertical 9:16 — recorte'),
                       ('vertical_blur','Vertical 9:16 — fundo desfocado')]:
        button=ttk.Button(parent,text=label,command=lambda key=mode:app.caption_layout_preset(key),style='Small.TButton')
        button.pack(fill='x',pady=2)
        app._cut_buttons.append(button);app.caption_layout_preset_buttons[mode]=button

    ttk.Separator(parent).pack(fill='x',pady=10)
    _description(parent,'Formato, resolução e qualidade são opções do projeto e também aparecem em Exportar. A posição X/Y abaixo é aplicada somente ao clipe selecionado.')
    app.caption_layout_pickers={}
    for key,label,var,values in [('mode','Formato do projeto',app.render_mode_label,list(MODES.values())),
                                 ('resolution','Resolução de saída',app.render_vars['resolution'],['720','1080']),
                                 ('preset','Qualidade do MP4',app.render_vars['preset'],['leve','equilibrado','qualidade'])]:
        ttk.Label(parent,text=label).pack(anchor='w',pady=(6,3))
        picker=ttk.Combobox(parent,textvariable=var,values=values,state='readonly',width=18)
        picker.pack(fill='x');app.caption_layout_pickers[key]=picker
        picker.bind('<<ComboboxSelected>>',lambda event:app.caption_layout_preview())

    ttk.Separator(parent).pack(fill='x',pady=10)
    ttk.Label(parent,text='Posição do recorte neste clipe').pack(anchor='w',pady=(3,4))
    _description(parent,'No vertical com recorte, mova a área visível para manter a ação no quadro. 0 = esquerda/topo; 1 = direita/base. O fundo desfocado preserva o quadro completo.')
    app.caption_crop_scales={};app.caption_crop_entries={}
    for key,label in [('crop_x','Horizontal (X)'),('crop_y','Vertical (Y)')]:
        ttk.Label(parent,text=label).pack(anchor='w',pady=(5,2))
        row=ttk.Frame(parent);row.pack(fill='x')
        row.columnconfigure(0,weight=1)
        entry=ttk.Entry(row,textvariable=app.render_vars[key],width=7)
        entry.grid(row=0,column=1,sticky='e',padx=(7,0))
        # An independent numeric slider lets an entry temporarily contain an
        # incomplete decimal without a Tcl scale-variable conversion error.
        position=tk.DoubleVar(master=app,value=.5)
        source=app.render_vars[key]
        def sync(*_,field=source,number=position):
            try:value=float(str(field.get()).replace(',','.'))
            except (ValueError,TypeError,tk.TclError):return
            if math.isfinite(value) and 0<=value<=1:number.set(value)
        def slide(value,field=source):field.set(f'{float(value):.3f}')
        scale=ttk.Scale(row,from_=0,to=1,variable=position,command=slide)
        scale.grid(row=0,column=0,sticky='ew')
        trace=source.trace_add('write',sync);sync()
        def cleanup(event,widget=scale,field=source,token=trace):
            if event.widget is widget:
                try:field.trace_remove('write',token)
                except tk.TclError:pass
        scale.bind('<Destroy>',cleanup,add='+')
        app.caption_crop_scales[key]=scale;app.caption_crop_entries[key]=entry

    app.caption_layout_apply_button=ttk.Button(parent,text='Aplicar enquadramento neste clipe',command=app.caption_apply_layout,style='Primary.TButton')
    app.caption_layout_apply_button.pack(fill='x',pady=(12,4));app._cut_buttons.append(app.caption_layout_apply_button)
    for label,command in [('Centralizar neste clipe',app.caption_reset_layout),('Ver prévia com este formato',app.caption_layout_preview)]:
        button=ttk.Button(parent,text=label,command=command)
        button.pack(fill='x',pady=3);app._cut_buttons.append(button)
    _description(parent,'As mudanças não alteram o vídeo original. Salve o projeto para conservar o enquadramento aplicado. Layouts com câmera separada ou tela dividida não estão incluídos aqui.')
