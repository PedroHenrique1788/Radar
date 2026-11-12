import logging
import hashlib
import json
import os
import re
import shutil
import webbrowser
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser
from .media import probe, align_bounds, executable, Cancelled
from .model import timestamp, parse_time
from .pipeline import analyze
from .export import export_report, export_clip, export_srt, export_transcript
from .filmcraft import locate_cli, capabilities, create_projects, open_project, cli_from_selection
from .settings import save_filmcraft, read_settings, save_settings
from .runtime import start_process
from .review import review_prompt
from .credentials import KeyStore, validate_key
from .gemini import GeminiClient, cut_record, record_signature
from . import ui
from .export import transcript_entries


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        prefs=read_settings()
        self.title('Radar de Cortes — CefasGamer')
        self.geometry(f'{min(1320, self.winfo_screenwidth()-50)}x{min(850, self.winfo_screenheight()-90)}')
        self.events=queue.Queue()
        self.cancel=threading.Event()
        self.busy=False
        self.media,self.cuts,self.speech,self.cli=None,[],[],None
        self.preview_processes=[]
        self.preview_dir=tempfile.TemporaryDirectory(prefix='radar-preview-')
        self.last_output=Path('resultados').resolve();self.last_output.mkdir(exist_ok=True)
        Path('temporarios').mkdir(exist_ok=True)
        logging.basicConfig(filename='temporarios/radar.log',level=logging.INFO)
        self.path=tk.StringVar()
        self.info=tk.StringVar(value='Nenhum vídeo selecionado.')
        self.status=tk.StringVar(value='Tudo começa com um vídeo. Selecione sua gravação para continuar.')
        self.count,self.minimum,self.maximum=tk.StringVar(value='10'),tk.StringVar(value='15'),tk.StringVar(value='60')
        self.channel=tk.StringVar(value=str(prefs.get('channel_name','CEFASGAMER'))[:40])
        accent=prefs.get('accent',ui.BLUE)
        self.accent=accent if isinstance(accent,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',accent) else ui.BLUE
        self.logo_path=str(prefs.get('channel_logo',''))
        self.page_title=tk.StringVar();self.page_subtitle=tk.StringVar()
        self.cut_count=tk.StringVar(value='Nenhum corte ainda')
        self.selected_title=tk.StringVar(value='Selecione um corte')
        self.selected_score=tk.StringVar(value='Avaliação local • revisão humana recomendada')
        self.cut_start,self.cut_end=tk.StringVar(),tk.StringVar()
        self.filmcraft_status=tk.StringVar(value='FilmCraft opcional: conecte sua instalação para criar projetos nativos.')
        self.gemini_key_input=tk.StringVar()
        self.gemini_model=tk.StringVar(value=str(prefs.get('gemini_model','')))
        self.gemini_search=tk.BooleanVar(value=bool(prefs.get('gemini_search',False)))
        self.gemini_status=tk.StringVar(value='Gemini não configurado. A análise local está disponível.')
        self.remember_key=tk.BooleanVar(value=False)
        self.non_windows=os.name!='nt'
        self.key_store=KeyStore()
        self._session_key=''
        self._gemini_consent=None
        self.ai_reviews={};self.ai_signatures={};self.ai_context={};self.ai_response=None
        ui.build(self)
        self.bind('<MouseWheel>',self._scroll_page,add='+')
        self.bind('<Button-4>',self._scroll_page,add='+')
        self.bind('<Button-5>',self._scroll_page,add='+')
        self._load_logo()
        self._update_key_status()
        self.show_page('video')
        self._sync_controls()
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.after(100,self.poll)

    def show_page(self,name):
        pages={'video':('Selecione sua gravação','Traga o vídeo. O Radar ajuda a encontrar momentos que merecem revisão.'),
               'analysis':('Prepare a análise','Escolha o áudio, a transcrição e a duração dos seus cortes.'),
               'review':('Revise os cortes','Veja os horários originais, ajuste os limites e decida o que exportar.'),
               'export':('Pronto para editar e publicar','Vídeos, transcrições, legendas e projetos de edição em um só lugar.'),
               'settings':('Sua identidade. Suas opções.','Azul CefasGamer, integrações opcionais e configurações locais.')}
        if name not in pages:return
        self.current_page=name
        self.page_title.set(pages[name][0]);self.page_subtitle.set(pages[name][1])
        for key,page in self.pages.items():
            if key==name:page.grid()
            else:page.grid_remove()
        self.pages[name].tkraise()
        for key,b in self._nav_buttons.items():
            b.configure(style='NavActive.TButton' if key==name else 'Nav.TButton')

    def _scroll_page(self,event):
        page=self.pages.get(self.current_page)
        if not isinstance(page,ui.ScrollPage) or event.widget==page.canvas:return
        if isinstance(event.widget,(tk.Text,ttk.Treeview,ttk.Combobox)):return
        num=getattr(event,'num',None)
        amount=-3 if num==4 else 3 if num==5 else -int(getattr(event,'delta',0)/120)
        if amount:
            page.canvas.yview_scroll(amount,'units')
            return 'break'

    def _sync_controls(self):
        for b in self._run_buttons:b.configure(state='disabled' if self.busy else 'normal')
        for b in self._cut_buttons:b.configure(state='normal' if self.cuts and not self.busy else 'disabled')
        self.next_analysis.configure(state='normal' if self.media else 'disabled')
        self.ai_export_button.configure(state='normal' if self.ai_response and not self.busy else 'disabled')
        self.configure(cursor='watch' if self.busy else '')

    def _set_text(self,widget,text):
        widget.configure(state='normal');widget.delete('1.0','end');widget.insert('end',text);widget.configure(state='disabled')

    def _load_logo(self):
        self.logo_label.configure(bg=self.accent)
        if not self.logo_path or not Path(self.logo_path).is_file():return
        try:
            image=tk.PhotoImage(file=self.logo_path)
            scale=max(1,(max(image.width(),image.height())+63)//64)
            self._logo_image=image.subsample(scale,scale)
            self.logo_label.configure(image=self._logo_image,text='',width=68,height=68)
        except tk.TclError:
            self.logo_path=''

    def choose_accent(self):
        chosen=colorchooser.askcolor(color=self.accent,title='Cor principal do canal')[1]
        if chosen:
            self.accent=chosen
            ui.theme(self);self._load_logo()

    def choose_logo(self):
        path=filedialog.askopenfilename(title='Logotipo do canal em PNG',filetypes=[('Imagem PNG','*.png')])
        if not path:return
        try:
            tk.PhotoImage(file=path)
            destination=Path('config/channel_logo.png')
            destination.parent.mkdir(parents=True,exist_ok=True)
            if Path(path).resolve()!=destination.resolve():shutil.copyfile(path,destination)
            self.logo_path=str(destination.resolve())
            self._load_logo()
        except (OSError,tk.TclError) as exc:self.error(exc)

    def save_brand(self):
        name=self.channel.get().strip()[:40] or 'CEFASGAMER'
        self.channel.set(name)
        save_settings({'channel_name':name,'accent':self.accent,'channel_logo':self.logo_path})
        self.notify('Identidade visual salva neste computador.')

    def apply_limits(self):
        if self.busy:return
        try:
            cut=self.selected(True)[0]
            start,end=parse_time(self.cut_start.get()),parse_time(self.cut_end.get())
            if not 0<=start<end<=self.media.duration:raise ValueError('Intervalo inválido no vídeo original.')
            def done(bounds):
                cut.start,cut.end=bounds
                cut.reason+=' Limites ajustados manualmente; pontuação local da análise original.'
                self.ai_reviews.pop(cut.id,None);self.ai_signatures.pop(cut.id,None);self.ai_response=None
                self.refresh();self.table.selection_set(str(cut.id));self.show_detail()
            self.work(lambda:align_bounds(self.media,start,end,self.cancel),done,message='Alinhando aos quadros do vídeo original…')
        except Exception as exc:self.error(exc)

    def _valid_ai(self,cut):
        signature=record_signature(cut_record(cut,self.speech))
        return self.ai_reviews.get(cut.id) if self.ai_signatures.get(cut.id)==signature else None

    def report_callback_exception(self,exception,value,tb):
        location=''
        while tb is not None:
            location=f'{Path(tb.tb_frame.f_code.co_filename).name}:{tb.tb_lineno}'
            tb=tb.tb_next
        detail=f'Falha na interface ({exception.__name__}) em {location}. Reinicie o aplicativo e, se persistir, copie este erro.'
        logging.error('%s',detail)
        self.error(detail)

    def error(self, exc):
        detail = str(exc) or 'O programa não forneceu detalhes do erro.'
        log = Path('temporarios/radar.log').resolve()
        dialog = tk.Toplevel(self)
        dialog.title('Não foi possível concluir')
        dialog.geometry('760x360')
        ttk.Label(dialog, text='Detalhes do erro (podem ser copiados):', padding=8).pack(anchor='w')
        box = tk.Text(dialog, wrap='word', height=12)
        box.pack(fill='both', expand=True, padx=8)
        box.insert('1.0', detail + f'\n\nLog: {log}')
        box.configure(state='disabled')
        def copy_error():
            self.clipboard_clear()
            self.clipboard_append(detail)
        buttons = ttk.Frame(dialog, padding=8)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Copiar erro', command=copy_error).pack(side='left')
        ttk.Button(buttons, text='Fechar', command=dialog.destroy).pack(side='right')
        dialog.transient(self)

    def selected(self, one=False):
        ids = self.table.selection()
        if not ids:
            raise ValueError('Selecione um ou mais cortes na tabela (Ctrl para vários).')
        return [c for c in self.cuts if str(c.id) in ids][:1 if one else len(self.cuts)]

    def work(self, function, done, message='Processando… Aguarde ou clique em Cancelar.'):
        if self.busy:
            self.error('Aguarde a operação atual ou clique em Cancelar.')
            return
        self.busy = True
        self.status.set(message)
        self.progress.configure(mode='indeterminate')
        self.progress.start(20)
        self.cancel.clear()
        self._sync_controls()
        def worker():
            try:
                result = function()
                self.events.put(('done', (done, result)))
            except Cancelled:
                self.events.put(('cancel', None))
            except Exception as exc:
                logging.exception('Falha na operação')
                self.events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'progress':
                    self.progress.stop()
                    self.progress.configure(mode='determinate')
                    self.progress['value'], msg = value
                    self.status.set(msg)
                else:
                    self.progress.stop()
                    self.progress.configure(mode='determinate')
                    self.busy = False
                    self._sync_controls()
                    if kind == 'done':
                        callback, result = value
                        try:
                            callback(result)
                        except Exception as exc:
                            logging.exception('Falha ao exibir resultado')
                            self.error(exc)
                    elif kind == 'error':
                        self.status.set('Falha. Consulte temporarios/radar.log.')
                        self.error(value)
                    else:
                        self.status.set('Operação cancelada. Arquivos temporários removidos.')
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def notify(self, value):
        self.status.set(str(value))

    def choose(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(filetypes=[('Vídeo', '*.mp4 *.mkv *.mov *.avi'), ('Todos', '*.*')])
        if path:
            self.work(lambda: probe(path), self.loaded)

    def loaded(self, media):
        self.media = media
        self.path.set(media.path)
        self.cuts, self.speech = [], []
        self.ai_reviews.clear();self.ai_signatures.clear();self.ai_context.clear();self.ai_response=None
        self.refresh()
        self.info.set(f'{timestamp(media.duration)} | {media.width}×{media.height} | FPS médio {media.fps:.3f} | {media.codec} | {len(media.audio)} faixas de áudio')
        self.track['values'] = ['Áudio completo (mix)'] + [f"Faixa {a['index']} — {a['codec']} {a['channels']} canais {a['language']} {a['title']}" for a in media.audio]
        self.track.current(0)
        self.show_page('analysis')
        self._sync_controls()

    def analyze(self):
        if not self.media:
            return self.error('Selecione um vídeo primeiro.')
        try:
            args = (self.media.path, 'mix' if self.track.current() == 0 else str(self.media.audio[self.track.current()-1]['index']),
                    int(self.count.get()), float(self.minimum.get()), float(self.maximum.get()), self.model.get())
            self.work(lambda: analyze(*args, cancel=self.cancel, progress=lambda n, msg: self.events.put(('progress', (n, msg)))), self.results)
        except Exception as exc:
            self.error(exc)

    def results(self, result):
        self.media, self.cuts, self.speech, warnings = result
        self.ai_reviews.clear();self.ai_signatures.clear();self.ai_context.clear();self.ai_response=None
        self.refresh()
        if self.cuts:
            self.table.selection_set(str(self.cuts[0].id))
            self.table.focus(str(self.cuts[0].id))
        self.show_page('review')
        self.show_detail()
        if warnings:
            messagebox.showwarning('Limitações da análise', '\n'.join(warnings))

    def refresh(self):
        selection = self.table.selection()
        self.table.delete(*self.table.get_children())
        for c in self.cuts:
            self.table.insert('', 'end', iid=str(c.id), values=(c.id, timestamp(c.start), timestamp(c.end), f'{c.duration:.3f}', c.score, c.category, c.title, self._valid_ai(c)['nota_editorial'] if self._valid_ai(c) else '—'))
        self.table.selection_set([i for i in selection if self.table.exists(i)])
        self.cut_count.set(f'{len(self.cuts)} sugestões' if self.cuts else 'Nenhum corte ainda')
        self._sync_controls()

    def sort(self, key):
        attrs = {'id':'id', 'start':'start', 'end':'end', 'duration':'duration', 'score':'score', 'category':'category', 'title':'title'}
        if key=='ai':
            self.cuts.sort(key=lambda c:self._valid_ai(c)['nota_editorial'] if self._valid_ai(c) else -1,reverse=True)
        else:
            self.cuts.sort(key=lambda c: getattr(c, attrs[key]), reverse=key == 'score')
        self.refresh()

    def show_detail(self,event=None):
        try:
            cut=self.selected(True)[0]
            self.selected_title.set(f'Corte {cut.id:02} • {cut.duration:.2f} s')
            preview_key=(cut.id,cut.start,cut.end)
            if getattr(self,'_shown_preview_key',None)!=preview_key:
                self.preview_label.configure(image='',text=f'Prévia do corte {cut.id:02}\nClique aqui para ver um quadro ou use Reproduzir.')
                self._preview_image=None
                self._shown_preview_key=preview_key
            self.selected_score.set(f'Local: {cut.score:g}/100 • {cut.category}')
            self.cut_start.set(timestamp(cut.start));self.cut_end.set(timestamp(cut.end))
            self._set_text(self.detail,f'{cut.title}\n\n{cut.reason}\n\nEdição: {cut.editing}\n\nTranscrição: {cut.transcript or "indisponível"}')
            entries,omitted,partial=transcript_entries(cut,self.speech)
            lines=[f"[{timestamp(e['start'])}] {e['text']}" for e in entries]
            self._set_text(self.transcript_view,'\n\n'.join(lines) or 'Sem fala transcrita neste intervalo. Analise com tiny, base ou small.')
            review=self._valid_ai(cut)
            if review:
                text=(f"Avaliação editorial Gemini: {review['nota_editorial']:g}/100\n\n{review['titulo']}\n\n"
                      f"{review['justificativa']}\n\nEdição: {review['sugestao_edicao']}\n\nLimitações: {review['limitacoes']}")
                context=self.ai_context.get(cut.id,{})
                if context:
                    text+='\n\nModelo: '+context['model']
                    text+='\nPesquisa: '+('fontes retornadas pelo Google' if context['search_confirmed'] else 'sem fontes de pesquisa confirmadas')
                    for source in context['sources']:text+=f"\n{source['titulo']}\n{source['url']}"
                self._set_text(self.ai_view,text)
            else:
                self._set_text(self.ai_view,'Revisão opcional com Gemini. Configure sua chave e selecione “Revisar com Gemini”. As falas escolhidas serão enviadas ao Google somente quando você solicitar.')
        except ValueError:
            self.selected_title.set('Selecione um corte')
            for widget in (self.detail,self.transcript_view,self.ai_view):self._set_text(widget,'')

    def copy(self):
        try:
            text = '\n'.join(f'Corte {c.id:02}: {timestamp(c.start)} — {timestamp(c.end)} ({c.duration:.3f} s)' for c in self.selected())
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception as exc:
            self.error(exc)

    def copy_for_chatgpt(self):
        try:
            cuts = self.selected() if self.table.selection() else self.cuts
            text = review_prompt(self.media, cuts, self.speech)
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo('Análise copiada', 'Cole o conteúdo em uma conversa no ChatGPT para revisar os cortes e pedir pesquisa de tendências. A revisão acontece naquela conversa.')
        except Exception as exc:
            self.error(exc)

    def adjust(self):
        if self.busy:
            return
        try:
            c = self.selected(True)[0]
            start = simpledialog.askstring('Início', 'HH:MM:SS.mmm', initialvalue=timestamp(c.start))
            if start is None:
                return
            end = simpledialog.askstring('Fim', 'HH:MM:SS.mmm', initialvalue=timestamp(c.end))
            if end is None:
                return
            start, end = parse_time(start), parse_time(end)
            if not 0 <= start < end <= self.media.duration:
                raise ValueError('Intervalo inválido.')
            def done(bounds):
                c.start, c.end = bounds
                self.ai_reviews.pop(c.id,None);self.ai_signatures.pop(c.id,None);self.ai_response=None
                c.reason += ' Limites ajustados manualmente; pontuação da análise original.'
                self.refresh()
                self.table.selection_set(str(c.id))
            self.work(lambda: align_bounds(self.media, start, end, self.cancel), done)
        except Exception as exc:
            self.error(exc)

    def report(self):
        try:
            if not self.media:
                raise ValueError('Selecione e analise um vídeo.')
            path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json'), ('CSV', '*.csv')])
            if path:
                self.notify(export_report(self.media, self.cuts, path))
        except Exception as exc:
            self.error(exc)

    def export_video(self):
        if self.busy:
            return self.error('Aguarde a operação atual antes de exportar.')
        try:
            c = self.selected(True)[0]
            path = filedialog.asksaveasfilename(defaultextension='.mp4', initialfile=f'corte_{c.id:02}.mp4',
                filetypes=[('Vídeo MP4', '*.mp4')], initialdir=str(self.last_output), confirmoverwrite=False)
            if path:
                overwrite = Path(path).exists()
                if overwrite and not messagebox.askyesno('Substituir MP4?', 'O arquivo já existe. Deseja substituí-lo após a exportação concluir?'):
                    return
                def done(output):
                    self.last_output = Path(output).parent
                    self.notify(f'MP4 salvo: {output}')
                    messagebox.showinfo('MP4 exportado', f'Arquivo salvo em:\n{output}')
                self.work(lambda: export_clip(self.media, c, path, self.cancel, overwrite), done,
                          message=f'Exportando MP4: {timestamp(c.start)} até {timestamp(c.end)}…')
        except Exception as exc:
            self.error(exc)

    def transcript(self):
        if self.busy:
            return self.error('Aguarde a análise ou exportação atual antes de salvar a transcrição.')
        try:
            cut = self.selected(True)[0]
            path = filedialog.asksaveasfilename(defaultextension='.txt', initialfile=f'transcricao_corte_{cut.id:02}.txt',
                filetypes=[('Transcrição de texto', '*.txt')], initialdir=str(self.last_output))
            if path:
                output = export_transcript(cut, self.speech, path)
                self.last_output = Path(output).parent
                self.notify(f'Transcrição salva: {output}')
                messagebox.showinfo('Transcrição exportada', f'Transcrição do corte {cut.id:02} salva em:\n{output}')
        except Exception as exc:
            self.error(exc)

    def srt(self):
        try:
            c = self.selected(True)[0]
            path = filedialog.asksaveasfilename(defaultextension='.srt', initialfile=f'corte_{c.id:02}.srt')
            if path:
                self.notify(export_srt(c, self.speech, path))
        except Exception as exc:
            self.error(exc)

    def preview(self):
        try:
            c = self.selected(True)[0]
            player = executable('ffplay')
            path = Path(self.preview_dir.name) / f'preview_{len(list(Path(self.preview_dir.name).iterdir()))}.mp4'
            def done(output):
                self.preview_processes.append(start_process([player, '-autoexit', '-loglevel', 'error', str(output)]))
                self.notify('Prévia temporária aberta no FFplay.')
            self.work(lambda: export_clip(self.media, c, path, self.cancel), done)
        except Exception as exc:
            self.error(exc)

    def connect(self, choose=False):
        if self.busy:
            return self.error('Aguarde a operação atual antes de conectar ao FilmCraft.')
        cli = None if choose else (self.cli or locate_cli())
        if not cli:
            selected = filedialog.askopenfilename(title='Selecionar FilmCraft ou filmcraft-cli da instalação',
                filetypes=[('FilmCraft', 'filmcraft.exe filmcraft-cli.exe filmcraft filmcraft-cli'), ('Executável', '*.exe'), ('Todos', '*.*')])
            if selected:
                cli = cli_from_selection(selected)
                if not cli:
                    return self.error('Não foi encontrado filmcraft-cli ao lado do arquivo escolhido. Selecione a pasta da versão oficial que inclui a CLI.')
            else:
                self.notify('FilmCraft não selecionado. Os projetos podem ser exportados como OTIO para importar no editor.')
                return
        def done(result):
            self.cli = result['cli']
            self.filmcraft_status.set('FilmCraft conectado. Novos projetos podem ser criados e abertos para edição.')
            save_filmcraft(self.cli)
            self.notify('FilmCraft localizado e verificado. A instalação será lembrada nas próximas aberturas.')
            messagebox.showinfo('FilmCraft disponível', 'Integração verificada. Você já pode criar projetos novos e abri-los para editar.')
        self.work(lambda: capabilities(cli), done, message='Verificando a instalação do FilmCraft…')

    def film(self, individual, selected):
        if self.busy:
            return self.error('Aguarde a operação atual antes de criar projetos.')
        try:
            cuts = self.selected() if selected else list(self.cuts)
            if not cuts:
                raise ValueError('Não há cortes para enviar. Analise um vídeo primeiro.')
            folder = filedialog.askdirectory(title='Pasta para os projetos (será criada uma subpasta por operação)', initialdir=str(self.last_output))
            if folder:
                cli = self.cli or locate_cli() or False
                def done(files):
                    if not files:
                        return self.error('Nenhum projeto foi criado.')
                    self.last_output = Path(files[0]).parent
                    native = all(Path(f).suffix == '.fcproj' for f in files)
                    label = 'projetos FilmCraft (.fcproj)' if native else 'timelines de intercâmbio (.otio)'
                    self.notify(f'{len(files)} {label} criados em {self.last_output}')
                    text = f'{len(files)} {label} criados.\nPasta:\n{self.last_output}'
                    if native:
                        messagebox.showinfo('Projetos criados', text + '\nUse “Abrir projeto para edição” para revisar.')
                    else:
                        messagebox.showwarning('Exportação OTIO', text + '\nA CLI não está conectada; não foi gerado .fcproj. Importe os OTIO pelo FilmCraft ou conecte uma instalação oficial para gerar projetos nativos.')
                self.work(lambda: create_projects(self.media, cuts, folder, individual, cli, self.cancel,
                    progress=lambda n, msg: self.events.put(('progress', (n, msg)))), done,
                    message='Criando projetos para o FilmCraft…')
        except Exception as exc:
            self.error(exc)

    def open_film(self):
        path = filedialog.askopenfilename(filetypes=[('Projeto FilmCraft', '*.fcproj'), ('Timeline OTIO', '*.otio')], initialdir=str(self.last_output))
        if path:
            try:
                open_project(path, self.cli)
            except Exception as exc:
                self.error(exc)

    def load_preview_frame(self):
        if self.busy:return
        try:
            cut=self.selected(True)[0]
            key=(cut.id,cut.start,cut.end)
            media=self.media
            output=Path(self.preview_dir.name)/f'frame-{len(list(Path(self.preview_dir.name).iterdir()))}.png'
            width=max(160,self.preview_label.winfo_width()-16)
            height=max(90,self.preview_label.winfo_height()-10)
            def extract():
                from .media import run
                run([executable('ffmpeg'),'-v','error','-nostdin','-y','-ss',cut.start,'-i',media.path,
                     '-map',f'0:{media.video_index}','-frames:v','1','-vf',f'scale={width}:{height}:force_original_aspect_ratio=decrease',output],self.cancel,timeout=25)
                return output
            def done(path):
                selected=self.selected(True)[0]
                if (selected.id,selected.start,selected.end)!=key:return
                self._preview_image=tk.PhotoImage(master=self,file=str(path))
                self.preview_label.configure(image=self._preview_image,text='')
                self.notify('Quadro de referência carregado. Reproduza o trecho para conferir áudio e contexto.')
            self.work(extract,done,message='Carregando imagem do início do corte…')
        except Exception as exc:self.error(exc)

    def _get_gemini_key(self):
        value=self.gemini_key_input.get().strip() or self._session_key
        if not value:value=self.key_store.load()
        if not value:value=os.environ.get('GEMINI_API_KEY','')
        return validate_key(value)

    def _update_key_status(self):
        if self.key_store.exists():
            self.gemini_status.set('Há uma chave protegida salva para este usuário do Windows.')
        elif self._session_key or self.gemini_key_input.get().strip():
            self.gemini_status.set('Chave disponível somente nesta sessão.')
        elif os.environ.get('GEMINI_API_KEY'):
            self.gemini_status.set('Chave disponível pela variável GEMINI_API_KEY do sistema.')
        else:self.gemini_status.set('Gemini não configurado. A análise local está disponível.')

    def save_gemini_key(self):
        if self.busy:return self.error('Aguarde a operação atual antes de alterar a chave.')
        try:
            key=self._get_gemini_key()
            if self.remember_key.get():
                self.key_store.save(key)
                self._session_key='';self.gemini_key_input.set('')
            else:
                self._session_key=key
                self.gemini_key_input.set('')
            self._gemini_consent=None
            self._update_key_status()
            self.notify('Chave configurada. Use “Validar e listar modelos” para verificar o acesso.')
        except Exception as exc:self.error(exc)

    def forget_gemini_key(self):
        if self.busy:return self.error('Aguarde a solicitação atual antes de remover a chave salva.')
        try:
            self.key_store.delete()
            self._session_key='';self.gemini_key_input.set('');self._gemini_consent=None
            self._update_key_status()
            self.notify('Chave salva e chave desta sessão removidas.')
        except Exception as exc:self.error(exc)

    def connect_gemini(self):
        if self.busy:return self.error('Aguarde a operação atual antes de validar a chave.')
        try:
            key=self._get_gemini_key()
            def done(models):
                self._session_key=key
                self.gemini_model_picker['values']=models
                if self.gemini_model.get() not in models:self.gemini_model.set(models[0])
                self.gemini_status.set(f'Conexão verificada • {len(models)} modelos de texto disponíveis na sua conta.')
                self.notify('Escolha o modelo e salve as preferências. Confira a cota no AI Studio.')
            self.work(lambda:GeminiClient(key).list_models(self.cancel),done,message='Validando acesso ao Gemini e carregando modelos…')
        except Exception as exc:self.error(exc)

    def save_gemini_preferences(self):
        try:
            model=self.gemini_model.get().strip()
            if model and not re.fullmatch(r'gemini-[A-Za-z0-9._-]{1,120}',model):raise ValueError('Selecione um modelo da lista da sua conta.')
            save_settings({'gemini_model':model,'gemini_search':bool(self.gemini_search.get())})
            self.notify('Preferências Gemini salvas. Os limites e a cobrança são controlados pelo projeto Google.')
        except Exception as exc:self.error(exc)

    def open_ai_studio(self):
        webbrowser.open('https://aistudio.google.com/apikey')

    def review_gemini(self):
        if self.busy:return self.error('Aguarde ou cancele a operação atual antes de solicitar outra revisão.')
        try:
            cuts=self.selected()
            key=self._get_gemini_key()
            model=self.gemini_model.get().strip()
            if not model:
                self.show_page('settings')
                raise ValueError('Configure a chave e use “Validar e listar modelos” antes de revisar com Gemini.')
            search=bool(self.gemini_search.get())
            consent=(model,search,hashlib.sha256(key.encode()).digest())
            if self._gemini_consent!=consent:
                text=(f'Serão enviados ao Google os horários e as transcrições de {len(cuts)} corte(s). O vídeo não será enviado.\n\n'
                      f'Modelo: {model}\nPesquisa Google: {"ativada" if search else "desativada"}\n\n'
                      'A cota gratuita e eventual cobrança dependem do seu projeto no Google. Deseja solicitar a revisão?')
                if not messagebox.askyesno('Revisão opcional com Gemini',text):return
                self._gemini_consent=consent
            media,speech=self.media,list(self.speech)
            def done(result):
                self.ai_response=result
                for review in result['reviews']:
                    ident=review['id']
                    self.ai_reviews[ident]=review
                    self.ai_signatures[ident]=result['input_signatures'][str(ident)]
                    self.ai_context[ident]={k:result[k] for k in ('model','created_at','sources','search_confirmed')}
                self.refresh();self.show_detail();self.review_tabs.select(2)
                self.show_page('review')
                if result['search_requested'] and not result['search_confirmed']:
                    self.notify('Revisão concluída; o Google não retornou fontes de pesquisa confirmadas.')
                else:self.notify('Revisão Gemini concluída. Leia as justificativas e as limitações na aba Gemini.')
            self.work(lambda:GeminiClient(key).review(media,cuts,speech,model,search,self.cancel),done,message='Gemini está revisando os cortes selecionados…')
        except Exception as exc:
            if not self.gemini_model.get():self.show_page('settings')
            self.error(exc)

    def export_gemini(self):
        try:
            if not self.ai_response:raise ValueError('Faça uma revisão Gemini antes de exportar.')
            for cut in self.cuts:
                signature=self.ai_response['input_signatures'].get(str(cut.id))
                if signature and signature!=record_signature(cut_record(cut,self.speech)):
                    raise ValueError('Os limites ou a transcrição mudaram após esta revisão. Solicite uma revisão atualizada.')
            path=filedialog.asksaveasfilename(defaultextension='.json',initialfile='revisao_gemini.json',
                filetypes=[('Revisão Gemini JSON','*.json')],initialdir=str(self.last_output))
            if path:
                with Path(path).open('x',encoding='utf-8') as out:json.dump(self.ai_response,out,ensure_ascii=False,indent=2)
                self.notify(f'Revisão Gemini salva: {path}')
        except Exception as exc:self.error(exc)

    def close(self):
        self.cancel.set()
        if self.busy:
            self.status.set('Cancelando antes de fechar…')
            self.after(200, self.close)
            return
        for p in self.preview_processes:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=5)
        self.preview_dir.cleanup()
        self.destroy()
