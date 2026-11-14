"""Caption editor actions on the existing desktop worker and project model."""
from copy import deepcopy
from dataclasses import asdict,replace
from pathlib import Path
import re
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog,colorchooser

from .captions import CaptionStyle,EFFECTS,generate_track,entries_for_cut,update_cue,set_style,set_words,style_for,validate_track
from .caption_transcription import transcribe_cut
from .caption_preview import frame,preview_key
from .export import export_ass,export_srt,export_clip,transcript_entries
from .media import executable
from .model import Cut,parse_time,timestamp
from .render import for_cut
from .runtime import start_process
from .settings import save_settings
from .checkpoints import signature


def seconds(value):
    value=str(value).strip()
    return parse_time(value) if ':' in value else float(value.replace(',','.'))


class CaptionDesktop:
    def init_captions(self,prefs):
        self.caption_clip=tk.StringVar();self.caption_effect=tk.StringVar(value=EFFECTS['classic'])
        self.caption_enabled=tk.BooleanVar(value=True);self.caption_audio=tk.BooleanVar(value=True)
        self.caption_start=tk.StringVar();self.caption_end=tk.StringVar()
        self.caption_time=tk.StringVar(value='00:00:00.000');self.caption_cursor=tk.DoubleVar(value=0.)
        self.caption_status=tk.StringVar(value='Selecione um corte e gere as legendas. A transcrição existente será reutilizada.')
        self.caption_word_status=tk.StringVar();self.caption_preset=tk.StringVar()
        self.caption_style_vars={k:(tk.BooleanVar(value=v) if isinstance(v,bool) else tk.StringVar(value=str(v))) for k,v in CaptionStyle().record().items() if k!='effect'}
        self.caption_presets={}
        raw=prefs.get('caption_presets',{})
        for name,value in list(raw.items())[:50] if isinstance(raw,dict) else []:
            if isinstance(name,str) and 1<=len(name)<=60:
                try:self.caption_presets[name]=CaptionStyle.from_record(value).record()
                except ValueError:pass
        self._caption_cut_id=None;self._caption_cue_id=None
        self._caption_buffer=None;self._caption_style_buffer=None;self._caption_after=None
        self._caption_refreshing=False;self._caption_image=None;self._caption_preview_key=None
        self._caption_players=[]

    def caption_cut(self):
        cut=next((c for c in self.cuts if c.id==self._caption_cut_id),None)
        if cut is None:raise ValueError('Selecione um corte no Estúdio de Legendas.')
        return cut

    def reset_captions(self):
        if self._caption_after is not None:self.after_cancel(self._caption_after);self._caption_after=None
        self._caption_cut_id=None;self._caption_cue_id=None;self._caption_buffer=None;self._caption_style_buffer=None
        self._caption_image=None;self._caption_preview_key=None
        self.caption_clip.set('');self.caption_cursor.set(0.)
        self.caption_preview_canvas.delete('all')
        self.caption_table.delete(*self.caption_table.get_children())
        self.caption_text.delete('1.0','end');self.caption_start.set('');self.caption_end.set('')
        self.caption_status.set('Selecione um corte e gere as legendas. A transcrição existente será reutilizada.')

    def refresh_caption_clips(self):
        self.caption_picker['values']=[f'{c.id:03} • {c.title[:60]}' for c in self.cuts]
        if self._caption_cut_id is not None and not any(c.id==self._caption_cut_id for c in self.cuts):self.reset_captions()

    def open_captions(self):self.show_page('captions')

    def enter_captions(self):
        self.refresh_caption_clips()
        selected=self.table.selection()
        ident=int(selected[0]) if selected else self._caption_cut_id
        if ident is None and self.cuts:ident=self.cuts[0].id
        if ident is not None:self.caption_select_cut(ident)

    def caption_choose_clip(self,event=None):
        if self.busy:return
        try:
            self.caption_select_cut(int(self.caption_clip.get().split(' • ',1)[0]))
        except (ValueError,TypeError) as exc:self.error(exc)

    def caption_select_cut(self,ident):
        self.flush_captions()
        if ident==self._caption_cut_id:
            self.caption_refresh();return
        cut=next((c for c in self.cuts if c.id==ident),None)
        if cut is None:return
        self._caption_cut_id=ident;self._caption_cue_id=None;self._caption_buffer=None;self._caption_style_buffer=None
        self.caption_cursor.set(0.);self.caption_time.set(timestamp(0))
        self._caption_preview_key=None;self._caption_image=None;self.caption_preview_canvas.delete('all')
        if not self.table.exists(str(ident)):self.review_filter.set('Todos');self.refresh()
        self.table.selection_set(str(ident));self.show_detail()
        self.caption_refresh()
        self.caption_status.set('Legendas editáveis carregadas.' if cut.captions else 'Clique em Gerar legendas para reutilizar a transcrição ou transcrever somente este Short.')
        self.caption_preview_canvas.create_text(12,12,anchor='nw',text='Mova o cursor ou clique em Atualizar prévia.',fill='#93a8c4',width=280)

    def _caption_load_style(self,style):
        style=CaptionStyle.from_record(style).record()
        self.caption_effect.set(EFFECTS[style.pop('effect')])
        for key,value in style.items():self.caption_style_vars[key].set(value)
        self._caption_style_buffer=self.caption_style_snapshot()

    def caption_style_snapshot(self):
        return (self.caption_effect.get(),tuple((k,v.get()) for k,v in self.caption_style_vars.items()))

    def caption_style_from_ui(self):
        style={k:v.get() for k,v in self.caption_style_vars.items()}
        style['effect']=next((key for key,label in EFFECTS.items() if label==self.caption_effect.get()),'')
        for key in ('size','outline','shadow','x','y'):style[key]=float(str(style[key]).replace(',','.'))
        return CaptionStyle.from_record(style)

    def caption_refresh(self,selected=None):
        if self._caption_cut_id is None:return
        cut=self.caption_cut();self._caption_refreshing=True
        try:
            self.caption_clip.set(f'{cut.id:03} • {cut.title[:60]}')
            self.caption_scale.configure(to=cut.duration)
            self.caption_cursor.set(min(self.caption_cursor.get(),max(0,cut.duration-1/self.media.fps)))
            self.caption_enabled.set(cut.captions.get('enabled',True));self.caption_audio.set(cut.captions.get('preserve_audio',True))
            self.caption_table.delete(*self.caption_table.get_children())
            entries=entries_for_cut(cut,include_disabled=True) if cut.captions else []
            for entry in entries:
                self.caption_table.insert('','end',iid=str(entry['id']),values=(timestamp(entry['start']-cut.start),timestamp(entry['end']-cut.start),entry['text']))
            ident=selected if selected is not None else self._caption_cue_id
            if ident is None or not self.caption_table.exists(str(ident)):
                ident=entries[0]['id'] if entries else None
            self._caption_cue_id=ident
            if ident is not None:self.caption_table.selection_set(str(ident));self.caption_table.see(str(ident))
            self._caption_load_cue()
            original='\n'.join(e['text'] for e in transcript_entries(cut,self.speech)[0])
            self._set_text(self.caption_original,original or 'Sem transcrição em memória. Gerar legendas procura o cache e transcreve somente o Short se necessário.')
            self.caption_update_active()
        finally:self._caption_refreshing=False

    def _caption_load_cue(self):
        cut=self.caption_cut();cue=next((c for c in cut.captions.get('cues',[]) if c['id']==self._caption_cue_id),None)
        self.caption_text.delete('1.0','end')
        if cue:
            self.caption_text.insert('1.0',cue['text']);self.caption_start.set(timestamp(max(0,cue['start']-cut.start)));self.caption_end.set(timestamp(min(cut.duration,cue['end']-cut.start)))
            self.caption_word_status.set(f'{len(cue.get("words",[]))} palavras sincronizadas.' if cue.get('words') else 'Sem tempos por palavra. Destaque/Karaokê usam o estilo Clássico até sincronizar.')
            self._caption_load_style(style_for(cut.captions,cue))
        else:
            self.caption_start.set('');self.caption_end.set('');self.caption_word_status.set('Gere legendas ou adicione um bloco manualmente.')
            self._caption_load_style(cut.captions.get('style') or CaptionStyle())
        self._caption_buffer=(self.caption_start.get(),self.caption_end.get(),self.caption_text.get('1.0','end-1c'))

    def flush_captions(self,*,style_scope='cue'):
        """Commit visible edits before selection, save, preview and export."""
        if self._caption_cut_id is None or not hasattr(self,'caption_text'):return
        cut=self.caption_cut()
        if not cut.captions:return
        changed=False;track=cut.captions
        buffer=(self.caption_start.get(),self.caption_end.get(),self.caption_text.get('1.0','end-1c'))
        if self._caption_cue_id is not None and self._caption_buffer is not None and buffer!=self._caption_buffer:
            start,end=seconds(buffer[0])+cut.start,seconds(buffer[1])+cut.start
            if start<cut.start-1e-6 or end>cut.end+1e-6:raise ValueError('A legenda deve ficar dentro da duração deste Short.')
            track=update_cue(track,self._caption_cue_id,text=buffer[2],start=start,end=end);changed=True
        style_snapshot=self.caption_style_snapshot()
        if self._caption_style_buffer is not None and style_snapshot!=self._caption_style_buffer:
            track=set_style(track,self.caption_style_from_ui(),self._caption_cue_id if style_scope=='cue' else None);changed=True
        if changed:
            cut.captions=track
            self._caption_buffer=buffer;self._caption_style_buffer=style_snapshot
            self.studio_changed();self._caption_preview_key=None

    def caption_select_cue(self,event=None):
        if self._caption_refreshing or self.busy:return
        selection=self.caption_table.selection()
        if not selection or int(selection[0])==self._caption_cue_id:return
        old=self._caption_cue_id
        try:
            self.flush_captions();self._caption_cue_id=int(selection[0]);self._caption_load_cue()
            cue=next(c for c in self.caption_cut().captions['cues'] if c['id']==self._caption_cue_id)
            self.caption_seek(max(0,cue['start']-self.caption_cut().start))
        except (ValueError,TypeError) as exc:
            if old is not None:self.caption_table.selection_set(str(old))
            self.error(exc)

    def caption_generate(self):
        if self.busy:return
        try:
            self.flush_captions();cut=self.caption_cut()
            if cut.captions and cut.captions.get('cues') and not messagebox.askyesno('Regerar legendas?', 'Substituir os textos e tempos editados deste corte pela transcrição? O estilo global será mantido.'):
                return
            style=cut.captions.get('style') or self.caption_style_from_ui().record()
            media=self.media;options=self.options_from_ui();model=self.model.get()
            track='mix' if self.track.current()==0 else str(media.audio[self.track.current()-1]['index'])
            # In-memory analysis is authoritative, including silence when a
            # completed analysis used Whisper. Otherwise consult its cache.
            speech=deepcopy(self.speech)
            def done(result):
                data,used=result;cut.captions=generate_track(cut,data,style)
                self._caption_buffer=None;self._caption_style_buffer=None;self._caption_cue_id=None
                self.studio_changed();self.caption_refresh()
                self.render_vars['burn_subtitles'].set(True)
                self.caption_status.set(f'{len(cut.captions["cues"])} blocos • {used}. Textos e estilos ficam editáveis no projeto.' if cut.captions['cues'] else 'Nenhuma fala reconhecida neste Short. Adicione um bloco manual ou escolha outra faixa de áudio na análise.')
                self.caption_request_preview()
            if transcript_entries(cut,speech)[0]:
                done((speech,'transcrição existente reutilizada'))
            else:
                self.work(lambda:(transcribe_cut(media,cut,track,model,options=options,cancel=self.cancel,
                    progress=lambda n,msg:self.events.put(('progress',(n,msg)))),'cache local / Whisper CPU'),done,message='Buscando transcrição em cache para este Short…')
        except (ValueError,TypeError,OSError) as exc:self.error(exc)

    def caption_apply_text(self):
        if self.busy:return
        try:
            self.flush_captions();self.caption_refresh();self.caption_request_preview()
            self.caption_status.set('Texto e tempos salvos na faixa editável. A transcrição original foi preservada.')
        except (ValueError,TypeError) as exc:self.error(exc)

    def caption_apply_style(self,global_style=False):
        if self.busy:return
        try:
            style=self.caption_style_from_ui();self.flush_captions(style_scope='global' if global_style else 'cue')
            cut=self.caption_cut()
            if not cut.captions:raise ValueError('Gere legendas antes de aplicar um estilo.')
            cut.captions=set_style(cut.captions,style,None if global_style else self._caption_cue_id)
            self.studio_changed();self.caption_refresh();self.caption_request_preview()
            self.caption_status.set('Estilo global aplicado. Blocos com estilo individual mantêm sua personalização.' if global_style else 'Estilo individual aplicado ao bloco selecionado.')
        except (ValueError,TypeError) as exc:self.error(exc)

    def caption_reset_style(self):
        if self.busy:return
        try:
            self.flush_captions();cut=self.caption_cut()
            cue=next(c for c in cut.captions.get('cues',[]) if c['id']==self._caption_cue_id)
            cue['style']={};self.studio_changed();self.caption_refresh();self.caption_request_preview()
        except (ValueError,StopIteration) as exc:self.error(str(exc) or 'Selecione um bloco.')

    def caption_toggle(self):
        if self.busy:return
        try:
            self.flush_captions();cut=self.caption_cut()
            if not cut.captions:return
            cut.captions['enabled']=self.caption_enabled.get();cut.captions['preserve_audio']=self.caption_audio.get()
            self.render_vars['burn_subtitles'].set(cut.captions['enabled'])
            self.studio_changed();self.caption_request_preview()
        except ValueError as exc:self.error(exc)

    def caption_legacy_toggle(self):
        if self.busy:return
        try:
            self.flush_captions()
            for cut in self.selected():
                if cut.captions:cut.captions['enabled']=bool(self.render_vars['burn_subtitles'].get())
            self.studio_changed()
            if self._caption_cut_id is not None:self.caption_enabled.set(self.caption_cut().captions.get('enabled',True))
        except ValueError:pass

    def caption_add(self):
        if self.busy:return
        try:
            self.flush_captions();cut=self.caption_cut()
            track=deepcopy(cut.captions) if cut.captions else generate_track(cut,[],self.caption_style_from_ui())
            left=cut.start+self.caption_cursor.get();right=min(cut.end,left+2.)
            if right-left<.05:raise ValueError('Mova o cursor para antes do fim do Short.')
            ident=max((c['id'] for c in track['cues']),default=0)+1
            track['cues'].append({'id':ident,'start':left,'end':right,'text':'Nova legenda','words':[],'style':{}})
            track['cues'].sort(key=lambda c:c['start']);validate_track(track,self.media.duration)
            cut.captions=track;self.studio_changed();self._caption_buffer=None;self._caption_style_buffer=None
            self.caption_refresh(ident);self.caption_status.set('Bloco adicionado. Corrija o texto e os tempos no painel ao lado.')
        except (ValueError,TypeError) as exc:self.error(exc)

    def caption_delete(self):
        if self.busy:return
        try:
            self.flush_captions();cut=self.caption_cut()
            if self._caption_cue_id is None:raise ValueError('Selecione um bloco para remover.')
            cut.captions['cues']=[c for c in cut.captions['cues'] if c['id']!=self._caption_cue_id]
            self._caption_cue_id=None;self._caption_buffer=None;self._caption_style_buffer=None
            self.studio_changed();self.caption_refresh();self.caption_request_preview()
        except ValueError as exc:self.error(exc)

    def caption_mark(self,start):
        (self.caption_start if start else self.caption_end).set(timestamp(self.caption_cursor.get()))

    def caption_seek(self,value):
        if self._caption_refreshing:return
        self.caption_cursor.set(float(value));self.caption_update_active()
        if self._caption_after is not None:self.after_cancel(self._caption_after)
        self._caption_after=self.after(350,self._caption_seek_preview)

    def caption_update_active(self):
        if self._caption_cut_id is None:return
        cut=self.caption_cut();t=cut.start+self.caption_cursor.get();self.caption_time.set(timestamp(t-cut.start))
        cues={str(c['id']):c for c in cut.captions.get('cues',[])}
        for item in self.caption_table.get_children():
            cue=cues.get(item)
            self.caption_table.item(item,tags=('active',) if cue and cue['start']<=t<cue['end'] else ())
        cue=next((c for c in cut.captions.get('cues',[]) if c['start']<=t<c['end']),None)
        word=next((w['word'] for w in cue.get('words',[]) if w['start']<=t<w['end']),None) if cue else None
        self.caption_active.set('Palavra: '+word.strip() if word else 'Bloco: '+cue['text'] if cue else 'Sem legenda neste instante')

    def _caption_seek_preview(self):
        self._caption_after=None
        if self._closing or self.current_page!='captions':return
        if self.busy:self._caption_after=self.after(400,self._caption_seek_preview);return
        self.caption_request_preview()

    def caption_request_preview(self):
        if self.busy or not self.media or self._caption_cut_id is None:return
        try:
            self.flush_captions();cut=Cut(**asdict(self.caption_cut()));media=self.media
            options=self.rendering_for_export();relative=self.caption_cursor.get()
            w,h=for_cut(options,cut).dimensions(media)
            scale=min(1,640/max(w,h),max(80,self.caption_preview_canvas.winfo_width()-4)/w,max(80,self.caption_preview_canvas.winfo_height()-4)/h)
            preview_size=max(32,int(max(w,h)*scale))
            key=signature([preview_key(media,cut,options,relative),preview_size])
            folder=Path(self.preview_dir.name);output=folder/f'caption-{key}.png'
            def done(path):
                if self._caption_cut_id!=cut.id or abs(self.caption_cursor.get()-relative)>.001:return
                self._caption_preview_key=key;self._caption_image=tk.PhotoImage(master=self,file=str(path));self.caption_draw_preview()
                self.caption_update_active()
                self.caption_status.set('Quadro sincronizado em '+timestamp(relative)+'. Reproduzir 6 s abre a animação com áudio no player.')
                self.notify('Prévia de legenda pronta. Edite o bloco ou exporte o resultado.')
                stale=sorted(folder.glob('caption-*.png'),key=lambda p:p.stat().st_mtime,reverse=True)[32:]
                for path in stale:path.unlink(missing_ok=True)
            if output.is_file():done(output);return
            def failed(exc):
                self.caption_status.set('Não foi possível renderizar a prévia. Verifique FFmpeg/libass; SRT e ASS continuam disponíveis.')
                self.error(exc)
            self.work(lambda:frame(media,cut,options,self.speech,relative,output,self.cancel,max_size=preview_size),done,
                      message='Renderizando somente um quadro da legenda em CPU…',failed=failed)
        except (ValueError,TypeError,OSError) as exc:self.error(exc)

    def caption_draw_preview(self,event=None):
        canvas=self.caption_preview_canvas;canvas.delete('all')
        if self._caption_image is None:return
        image=self._caption_image;w,h=max(1,canvas.winfo_width()),max(1,canvas.winfo_height())
        factor=max(1,(image.width()+w-1)//w,(image.height()+h-1)//h)
        self._caption_display_image=image.subsample(factor,factor)
        canvas.create_image(w/2,h/2,image=self._caption_display_image,anchor='center')

    def caption_position(self,event):
        if self._caption_image is None or self.busy:return
        image=self._caption_display_image;canvas=self.caption_preview_canvas
        x=(event.x-(canvas.winfo_width()-image.width())/2)/image.width()
        y=(event.y-(canvas.winfo_height()-image.height())/2)/image.height()
        if 0<=x<=1 and 0<=y<=1:
            self.caption_style_vars['x'].set(f'{x:.3f}');self.caption_style_vars['y'].set(f'{y:.3f}')
            self.caption_apply_style(False)

    def caption_play(self):
        if self.busy:return
        try:
            self.flush_captions();cut=Cut(**asdict(self.caption_cut()));media=self.media
            start=min(cut.start+self.caption_cursor.get(),cut.end-1/self.media.fps)
            fragment=replace(cut,start=start,end=min(cut.end,start+6.))
            options=self.rendering_for_export();options.preset='leve'
            # Preview encodes a maximum of six seconds, never the full Short.
            options.resolution=720
            key=preview_key(media,fragment,options,0.);output=Path(self.preview_dir.name)/f'caption-play-{key}.mp4'
            player=executable('ffplay')
            def done(path):
                self.preview_processes=[p for p in self.preview_processes if p.poll() is None]
                for process,_ in self._caption_players:
                    if process.poll() is None:process.terminate()
                process=start_process([player,'-autoexit','-loglevel','error',str(path)])
                self.preview_processes.append(process)
                self._caption_players=[(p,f) for p,f in self._caption_players if p.poll() is None]+[(process,path)]
                active={str(f) for p,f in self._caption_players if p.poll() is None}
                files=sorted(Path(self.preview_dir.name).glob('caption-play-*.mp4'),key=lambda p:p.stat().st_mtime,reverse=True)
                for old in files[4:]:
                    if str(old) not in active:
                        try:old.unlink(missing_ok=True)
                        except OSError:pass
                self.caption_status.set('Prévia de até 6 s aberta com áudio. A exportação final usa a qualidade selecionada.')
            if output.is_file():done(output);return
            self.work(lambda:export_clip(media,fragment,output,self.cancel,render_options=options,speech=self.speech,preview_size=640),done,message='Preparando até 6 s com animação e áudio…')
        except (ValueError,TypeError,RuntimeError) as exc:self.error(exc)

    def caption_color(self,key):
        value=colorchooser.askcolor(color=self.caption_style_vars[key].get(),title='Cor da legenda')[1]
        if value:self.caption_style_vars[key].set(value)

    def caption_save_preset(self):
        try:
            style=self.caption_style_from_ui().record()
            name=simpledialog.askstring('Salvar preset de legenda','Nome do preset (até 60 caracteres):',parent=self)
            if name is None:return
            name=name.strip()
            if not 1<=len(name)<=60:raise ValueError('Use um nome com 1 a 60 caracteres.')
            if name not in self.caption_presets and len(self.caption_presets)>=50:raise ValueError('Limite de 50 presets personalizados.')
            self.caption_presets[name]=style;save_settings({'caption_presets':self.caption_presets})
            self.caption_preset_picker['values']=list(self.caption_presets);self.caption_preset.set(name)
            self.caption_status.set('Preset salvo neste computador. Aplique no clipe ou no bloco para utilizá-lo.')
        except (ValueError,OSError) as exc:self.error(exc)

    def caption_load_preset(self,event=None):
        style=self.caption_presets.get(self.caption_preset.get())
        if style:
            before=self._caption_style_buffer
            self._caption_load_style(style);self._caption_style_buffer=before

    def caption_export(self,kind):
        if self.busy:return
        try:
            self.flush_captions();cut=self.caption_cut()
            if kind=='mp4':
                self.table.selection_set(str(cut.id));self.export_video();return
            path=filedialog.asksaveasfilename(title='Exportar legenda '+kind.upper(),defaultextension='.'+kind,
                initialfile=f'corte_{cut.id:02}.{kind}',filetypes=[('Legenda '+kind.upper(),'*.'+kind)],initialdir=str(self.last_output))
            if path:
                if kind=='srt':output=export_srt(cut,self.speech,path)
                else:
                    w,h=for_cut(self.rendering_for_export(),cut).dimensions(self.media)
                    output=export_ass(cut,self.speech,path,width=w,height=h)
                self.last_output=Path(path).parent;self.caption_status.set(f'Legenda {kind.upper()} salva: {output}')
                self.notify(f'Legenda {kind.upper()} exportada.')
        except (ValueError,OSError) as exc:self.error(exc)

    def caption_words(self):
        if self.busy:return
        try:
            self.flush_captions();cut=self.caption_cut()
            cue=next(c for c in cut.captions.get('cues',[]) if c['id']==self._caption_cue_id)
        except (ValueError,StopIteration) as exc:return self.error(str(exc) or 'Selecione um bloco.')
        dialog=tk.Toplevel(self);dialog.title('Sincronização por palavra');dialog.geometry('660x470');dialog.transient(self)
        dialog.grab_set()
        pane=ttk.Frame(dialog,padding=12);pane.pack(fill='both',expand=True)
        ttk.Label(pane,text='Tempos em segundos do Short. Use o cursor da prévia como referência.\nApós mudar a quantidade de palavras, preencha os novos tempos; não são estimados.',wraplength=620).pack(anchor='w')
        tree=ttk.Treeview(pane,columns=('word','start','end'),show='headings',height=7,selectmode='browse')
        for key,label,width in [('word','Palavra',230),('start','Início (s)',120),('end','Fim (s)',120)]:tree.heading(key,text=label);tree.column(key,width=width)
        tree.pack(fill='both',expand=True,pady=8)
        rows=deepcopy(cue.get('words',[])) or [{'word':word,'start':None,'end':None} for word in cue['text'].split()]
        for i,row in enumerate(rows):tree.insert('','end',iid=str(i),values=(row['word'],'' if row['start'] is None else f'{row["start"]-cut.start:.3f}','' if row['end'] is None else f'{row["end"]-cut.start:.3f}'))
        a=tk.StringVar();b=tk.StringVar();status=tk.StringVar()
        entry=ttk.Frame(pane);entry.pack(fill='x')
        ttk.Label(entry,text='Início').pack(side='left');ttk.Entry(entry,textvariable=a,width=12).pack(side='left',padx=6)
        ttk.Label(entry,text='Fim').pack(side='left');ttk.Entry(entry,textvariable=b,width=12).pack(side='left',padx=6)
        def choose(event=None):
            if tree.selection():
                values=tree.item(tree.selection()[0],'values');a.set(values[1]);b.set(values[2])
        tree.bind('<<TreeviewSelect>>',choose)
        def apply():
            try:
                if not tree.selection():raise ValueError('Selecione uma palavra.')
                i=int(tree.selection()[0]);left,right=seconds(a.get())+cut.start,seconds(b.get())+cut.start
                if not cue['start']<=left<=right<=cue['end']:raise ValueError('Use tempos dentro do bloco.')
                rows[i].update(start=left,end=right);tree.item(str(i),values=(rows[i]['word'],f'{left-cut.start:.3f}',f'{right-cut.start:.3f}'));status.set('Palavra ajustada. Salve após revisar a lista.')
                return True
            except ValueError as exc:status.set(str(exc));return False
        ttk.Button(entry,text='Ajustar palavra',command=apply).pack(side='left')
        ttk.Label(pane,textvariable=status,wraplength=610).pack(anchor='w',pady=8)
        def save():
            try:
                if tree.selection() and not apply():return
                if any(r['start'] is None or r['end'] is None for r in rows):raise ValueError('Preencha os tempos de todas as palavras antes de salvar.')
                cut.captions=set_words(cut.captions,cue['id'],rows);self.studio_changed();dialog.destroy();self.caption_refresh();self.caption_request_preview()
            except ValueError as exc:status.set(str(exc))
        buttons=ttk.Frame(pane);buttons.pack(fill='x')
        ttk.Button(buttons,text='Salvar sincronização',command=save).pack(side='left')
        ttk.Button(buttons,text='Fechar',command=dialog.destroy).pack(side='right')
        if rows:tree.selection_set('0');choose()
