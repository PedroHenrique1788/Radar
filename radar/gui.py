import logging
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from .media import probe, align_bounds, executable, Cancelled
from .model import timestamp, parse_time
from .pipeline import analyze
from .export import export_report, export_clip, export_srt, export_transcript
from .filmcraft import locate_cli, capabilities, create_projects, open_project, cli_from_selection
from .settings import save_filmcraft
from .runtime import start_process
from .review import review_prompt


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Radar de Cortes — CefasGamer')
        self.geometry(f'{min(1180, self.winfo_screenwidth()-60)}x{min(800, self.winfo_screenheight()-100)}')
        self.configure(bg='#20242b')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background='#20242b', foreground='#eeeeee', fieldbackground='#303640')
        style.map('Treeview', background=[('selected', '#305980')], foreground=[('selected', 'white')])
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.media, self.cuts, self.speech, self.cli = None, [], [], None
        self.preview_processes = []
        self.last_output = Path('resultados').resolve()
        self.last_output.mkdir(exist_ok=True)
        self.preview_dir = tempfile.TemporaryDirectory(prefix='radar-preview-')
        Path('temporarios').mkdir(exist_ok=True)
        logging.basicConfig(filename='temporarios/radar.log', level=logging.INFO)
        self.path = tk.StringVar()
        self.info = tk.StringVar(value='Selecione um vídeo. Análise local; GPU e APIs pagas não são necessárias.')
        self.status = tk.StringVar(value='Pontuação heurística de potencial; não prevê viralização. Revise os cortes.')
        top = ttk.Frame(self, padding=12)
        top.pack(fill='x')
        ttk.Button(top, text='Selecionar vídeo', command=self.choose).pack(side='left')
        ttk.Entry(top, textvariable=self.path, state='readonly').pack(side='left', fill='x', expand=True, padx=8)
        ttk.Label(self, textvariable=self.info, wraplength=1100, padding=10).pack(fill='x')
        opts = ttk.Frame(self, padding=10)
        opts.pack(fill='x')
        choices = ttk.Frame(opts)
        choices.pack(fill='x')
        limits = ttk.Frame(opts)
        limits.pack(fill='x', pady=4)
        self.track = ttk.Combobox(choices, state='readonly', width=40)
        self.track.pack(side='left', padx=4)
        self.count, self.minimum, self.maximum = tk.StringVar(value='10'), tk.StringVar(value='15'), tk.StringVar(value='60')
        for name, var in [('Sugestões', self.count), ('Mín. s', self.minimum), ('Máx. s', self.maximum)]:
            ttk.Label(limits, text=name).pack(side='left', padx=4)
            ttk.Entry(limits, textvariable=var, width=5).pack(side='left')
        ttk.Label(choices, text='Modelo CPU').pack(side='left', padx=4)
        self.model = ttk.Combobox(choices, values=['tiny', 'base', 'small', 'off'], state='readonly', width=8)
        self.model.set('tiny')
        self.model.pack(side='left')
        ttk.Button(limits, text='Analisar vídeo', command=self.analyze).pack(side='left', padx=8)
        ttk.Button(limits, text='Cancelar', command=self.cancel.set).pack(side='left')
        self.progress = ttk.Progressbar(self, maximum=100)
        self.progress.pack(fill='x', padx=12)
        ttk.Label(self, textvariable=self.status, wraplength=1100, padding=10).pack(fill='x')
        columns = ('id', 'start', 'end', 'duration', 'score', 'category', 'title')
        self.table = ttk.Treeview(self, columns=columns, show='headings', selectmode='extended')
        for col, name, width in zip(columns, ['Corte', 'Início', 'Fim', 'Duração s', 'Pontos', 'Potencial', 'Título'], [45, 115, 115, 80, 65, 120, 360]):
            self.table.heading(col, text=name, command=lambda key=col: self.sort(key))
            self.table.column(col, width=width)
        self.table.bind('<<TreeviewSelect>>', self.show_detail)
        footer = ttk.Frame(self)
        footer.pack(side='bottom', fill='x')
        self.detail = tk.Text(footer, height=4, wrap='word', bg='#161a20', fg='white')
        self.detail.pack(fill='x', padx=12, pady=8)
        bar = ttk.Frame(footer, padding=4)
        bar.pack(fill='x')
        for i, (text, callback) in enumerate([('Copiar tempos', self.copy), ('Reproduzir trecho', self.preview), ('Ajustar início e fim', self.adjust),
                               ('Exportar corte MP4', self.export_video), ('Exportar relatório', self.report), ('Exportar SRT', self.srt), ('Exportar transcrição TXT', self.transcript), ('Copiar para ChatGPT', self.copy_for_chatgpt)]):
            ttk.Button(bar, text=text, command=callback).grid(row=i//3, column=i%3, sticky='ew', padx=3, pady=2)
        for i in range(3):
            bar.columnconfigure(i, weight=1)
        film = ttk.Frame(footer, padding=4)
        film.pack(fill='x')
        for i, (text, callback) in enumerate([('Conectar ao FilmCraft', self.connect), ('Escolher instalação FilmCraft…', lambda: self.connect(True)), ('Enviar cortes selecionados', lambda: self.film(False, True)),
                               ('Criar projeto com todos os cortes', lambda: self.film(False, False)),
                               ('Criar projeto individual por Short', lambda: self.film(True, False)), ('Abrir projeto para edição', self.open_film)]):
            ttk.Button(film, text=text, command=callback).grid(row=i//3, column=i%3, sticky='ew', padx=3, pady=2)
        for i in range(3):
            film.columnconfigure(i, weight=1)
        self.table.pack(fill='both', expand=True, padx=12)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)

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
        self.refresh()
        self.info.set(f'{timestamp(media.duration)} | {media.width}×{media.height} | FPS médio {media.fps:.3f} | {media.codec} | {len(media.audio)} faixas de áudio')
        self.track['values'] = ['Áudio completo (mix)'] + [f"Faixa {a['index']} — {a['codec']} {a['channels']} canais {a['language']} {a['title']}" for a in media.audio]
        self.track.current(0)

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
        self.refresh()
        if self.cuts:
            self.table.selection_set(str(self.cuts[0].id))
            self.table.focus(str(self.cuts[0].id))
        if warnings:
            messagebox.showwarning('Limitações da análise', '\n'.join(warnings))

    def refresh(self):
        selection = self.table.selection()
        self.table.delete(*self.table.get_children())
        for c in self.cuts:
            self.table.insert('', 'end', iid=str(c.id), values=(c.id, timestamp(c.start), timestamp(c.end), f'{c.duration:.3f}', c.score, c.category, c.title))
        self.table.selection_set([i for i in selection if self.table.exists(i)])

    def sort(self, key):
        attrs = {'id':'id', 'start':'start', 'end':'end', 'duration':'duration', 'score':'score', 'category':'category', 'title':'title'}
        self.cuts.sort(key=lambda c: getattr(c, attrs[key]), reverse=key == 'score')
        self.refresh()

    def show_detail(self, event=None):
        try:
            c = self.selected(True)[0]
            self.detail.delete('1.0', 'end')
            self.detail.insert('end', f'{c.title}\n{c.reason}\nTranscrição: {c.transcript or "indisponível"}\nEdição: {c.editing}\nTempos relativos ao primeiro quadro do original. Revisão humana necessária.')
        except ValueError:
            pass

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
