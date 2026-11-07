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
from .export import export_report, export_clip, export_srt
from .filmcraft import locate_cli, capabilities, create_projects, open_project


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Radar de Cortes — CefasGamer')
        self.geometry('1180x800')
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
        self.track = ttk.Combobox(opts, state='readonly', width=40)
        self.track.pack(side='left', padx=4)
        self.count, self.minimum, self.maximum = tk.StringVar(value='10'), tk.StringVar(value='15'), tk.StringVar(value='60')
        for name, var in [('Sugestões', self.count), ('Mín. s', self.minimum), ('Máx. s', self.maximum)]:
            ttk.Label(opts, text=name).pack(side='left', padx=4)
            ttk.Entry(opts, textvariable=var, width=5).pack(side='left')
        ttk.Label(opts, text='Modelo CPU').pack(side='left', padx=4)
        self.model = ttk.Combobox(opts, values=['tiny', 'base', 'small', 'off'], state='readonly', width=8)
        self.model.set('tiny')
        self.model.pack(side='left')
        ttk.Button(opts, text='Analisar vídeo', command=self.analyze).pack(side='left', padx=8)
        ttk.Button(opts, text='Cancelar', command=self.cancel.set).pack(side='left')
        self.progress = ttk.Progressbar(self, maximum=100)
        self.progress.pack(fill='x', padx=12)
        ttk.Label(self, textvariable=self.status, wraplength=1100, padding=10).pack(fill='x')
        columns = ('id', 'start', 'end', 'duration', 'score', 'category', 'title')
        self.table = ttk.Treeview(self, columns=columns, show='headings', selectmode='extended')
        for col, name, width in zip(columns, ['Corte', 'Início', 'Fim', 'Duração s', 'Pontos', 'Potencial', 'Título'], [45, 115, 115, 80, 65, 120, 360]):
            self.table.heading(col, text=name, command=lambda key=col: self.sort(key))
            self.table.column(col, width=width)
        self.table.pack(fill='both', expand=True, padx=12)
        self.table.bind('<<TreeviewSelect>>', self.show_detail)
        self.detail = tk.Text(self, height=7, wrap='word', bg='#161a20', fg='white')
        self.detail.pack(fill='x', padx=12, pady=8)
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill='x')
        for text, callback in [('Copiar tempos', self.copy), ('Reproduzir trecho', self.preview), ('Ajustar início e fim', self.adjust),
                               ('Exportar corte MP4', self.export_video), ('Exportar relatório', self.report), ('Exportar SRT', self.srt)]:
            ttk.Button(bar, text=text, command=callback).pack(side='left', padx=3)
        film = ttk.Frame(self, padding=8)
        film.pack(fill='x')
        for text, callback in [('Conectar ao FilmCraft', self.connect), ('Enviar cortes selecionados', lambda: self.film(False, True)),
                               ('Criar projeto com todos os cortes', lambda: self.film(False, False)),
                               ('Criar projeto individual por Short', lambda: self.film(True, True)), ('Abrir projeto para edição', self.open_film)]:
            ttk.Button(film, text=text, command=callback).pack(side='left', padx=3)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)

    def error(self, exc):
        messagebox.showerror('Radar de Cortes', str(exc))

    def selected(self, one=False):
        ids = self.table.selection()
        if not ids:
            raise ValueError('Selecione um ou mais cortes na tabela (Ctrl para vários).')
        return [c for c in self.cuts if str(c.id) in ids][:1 if one else len(self.cuts)]

    def work(self, function, done):
        if self.busy:
            self.error('Aguarde a operação atual ou clique em Cancelar.')
            return
        self.busy = True
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
                    self.progress['value'], msg = value
                    self.status.set(msg)
                else:
                    self.busy = False
                    if kind == 'done':
                        callback, result = value
                        callback(result)
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
        if warnings:
            messagebox.showwarning('Limitações da análise', '\n'.join(warnings))

    def refresh(self):
        self.table.delete(*self.table.get_children())
        for c in self.cuts:
            self.table.insert('', 'end', iid=str(c.id), values=(c.id, timestamp(c.start), timestamp(c.end), f'{c.duration:.3f}', c.score, c.category, c.title))

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
        try:
            c = self.selected(True)[0]
            path = filedialog.asksaveasfilename(defaultextension='.mp4', initialfile=f'corte_{c.id:02}.mp4')
            if path:
                self.work(lambda: export_clip(self.media, c, path, self.cancel), self.notify)
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
                self.preview_processes.append(subprocess.Popen([player, '-autoexit', '-loglevel', 'error', str(output)]))
                self.notify('Prévia temporária aberta no FFplay.')
            self.work(lambda: export_clip(self.media, c, path, self.cancel), done)
        except Exception as exc:
            self.error(exc)

    def connect(self):
        cli = locate_cli()
        if not cli:
            cli = filedialog.askopenfilename(title='Localizar filmcraft-cli (Cancelar para usar OTIO)')
        if cli:
            self.work(lambda: capabilities(cli), lambda result: (setattr(self, 'cli', cli), self.notify(f'CLI verificada: {cli}')))
        else:
            self.notify('CLI não localizada: disponível exportação OTIO para importar no FilmCraft.')

    def film(self, individual, selected):
        try:
            cuts = self.selected() if selected else list(self.cuts)
            if not cuts:
                raise ValueError('Não há cortes para enviar.')
            folder = filedialog.askdirectory(title='Pasta nova/vazia para projetos e timelines')
            if folder:
                self.work(lambda: create_projects(self.media, cuts, folder, individual, self.cli, self.cancel),
                          lambda files: self.notify('Criados: ' + ', '.join(str(p) for p in files) + '. Revise áudio OBS, resolução e proporção no editor.'))
        except Exception as exc:
            self.error(exc)

    def open_film(self):
        path = filedialog.askopenfilename(filetypes=[('Projeto FilmCraft', '*.fcproj'), ('Timeline OTIO', '*.otio')])
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
