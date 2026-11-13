"""Analysis controls added to the existing Tk desktop, independent of Gemini."""
from pathlib import Path
import tkinter as tk

from .checkpoints import StageError,STAGES,latest_request,recent_jobs
from .control import ExecutionControl
from .profiles import AnalysisOptions,ECONOMY
from .settings import save_settings
from .model import timestamp


class AnalysisDesktop:
    def init_analysis(self,prefs):
        try:self.analysis_options=AnalysisOptions.from_record(prefs.get('analysis_options'))
        except ValueError:self.analysis_options=AnalysisOptions()
        self.cancel=ExecutionControl(self.analysis_options)
        self.option_vars={}
        for name,value in self.analysis_options.record().items():
            if name=='weights':continue
            self.option_vars[name]=(tk.BooleanVar(value=value) if isinstance(value,bool) else tk.StringVar(value=str(value)))
        self.weight_vars={k:tk.StringVar(value=str(v)) for k,v in self.analysis_options.weights.items()}
        self.whisper_default=str(prefs.get('whisper_model','off'))
        if self.whisper_default not in ('off','tiny','base','small'):self.whisper_default='off'
        self.pause_text=tk.StringVar(value='Pausar')
        self.execution_info=tk.StringVar(value='Etapa: aguardando análise • CPU e RAM serão medidos durante o processamento.')
        self.resume_info=tk.StringVar(value='Selecione uma gameplay para consultar os checkpoints locais.')
        self._has_resume=False
        self._analysis_error_dialog=None
        self._recent_records=[]

    def options_from_ui(self):
        raw={name:var.get() for name,var in self.option_vars.items()}
        for name in ('threads','max_processes','memory_mb','visual_width','batch_seconds'):raw[name]=int(raw[name])
        for name in ('sample_fps','before','after'):raw[name]=float(str(raw[name]).replace(',','.'))
        raw['weights']={k:float(v.get().replace(',','.')) for k,v in self.weight_vars.items()}
        result=AnalysisOptions.from_record(raw)
        baseline=AnalysisOptions().record();actual=result.record()
        baseline.pop('profile');actual.pop('profile')
        result.profile=ECONOMY if baseline==actual else 'Personalizado (CPU)'
        self.option_vars['profile'].set(result.profile)
        return result

    def apply_options(self,options):
        self.analysis_options=AnalysisOptions.from_record(options)
        for name,value in self.analysis_options.record().items():
            if name!='weights':self.option_vars[name].set(value)
        for name,value in self.analysis_options.weights.items():self.weight_vars[name].set(str(value))

    def save_analysis_options(self):
        if self.busy:return
        try:
            self.analysis_options=self.options_from_ui()
            save_settings({'analysis_options':self.analysis_options.record(),'whisper_model':self.model.get()})
            self.notify('Perfil CPU salvo. Alterações invalidam somente os checkpoints relevantes.')
        except (ValueError,TypeError) as exc:self.error(exc)

    def economy_profile(self):
        if self.busy:return
        self.apply_options(AnalysisOptions())
        self.model.set('off')
        self.save_analysis_options()

    def update_runtime(self):
        if self._closing:return
        snapshot=self.cancel.snapshot()
        def clock(value):return timestamp(max(0,value)).split('.')[0] if value is not None else '—'
        cpu=f'{snapshot["cpu_percent"]:.0f}%' if snapshot['cpu_percent'] is not None else 'n/d'
        ram=f'{snapshot["ram_bytes"]/1024**2:.0f} MB' if snapshot['ram_bytes'] is not None else 'n/d'
        paused=' • PAUSADO' if snapshot['paused'] else ' • pausa solicitada' if snapshot['pause_requested'] else ''
        units=f'{snapshot["done"]:g}/{snapshot["total"]:g} {snapshot["unit"]}' if snapshot['total'] is not None else 'atividade indeterminada'
        self.execution_info.set(f'Etapa: {snapshot["stage"]}{paused}\n{units} • Decorrido: {clock(snapshot["elapsed"])} • Restante nesta etapa: {clock(snapshot["eta"])}\n'
            f'CPU Radar (estimativa da máquina): {cpu} • RAM Radar + processos: {ram}\n'
            f'Pontos de sinal: {snapshot.get("moments","—")} • Candidatos avaliados: {snapshot.get("evaluated","—")} • Cortes: {snapshot.get("candidates","—")}')
        self.pause_text.set('Retomar' if snapshot['pause_requested'] else 'Pausar')
        if snapshot['paused']:self.progress.stop()
        self._monitor_after=self.after(500,self.update_runtime)

    def toggle_pause(self):
        if not self.busy:return
        if self.cancel.pause_event.is_set():
            self.cancel.resume()
            if str(self.progress['mode'])=='indeterminate':self.progress.start(20)
            self.notify('Retomando a unidade atual, mantendo os checkpoints.')
        else:
            self.cancel.pause()
            self.notify('Pausa solicitada. Aguardando o limite da unidade atual; a interface continua disponível.')

    def load_analysis_state(self,media):
        record=latest_request(media.path)
        self._has_resume=bool(record)
        if record and isinstance(record.get('request'),dict):
            request=record['request']
            try:
                self.apply_options(request.get('options'))
                self.count.set(str(request.get('requested_count',request.get('count',10))));self.minimum.set(str(request.get('minimum',15)))
                self.maximum.set(str(request.get('maximum',60)));self.model.set(request.get('model','off'))
                track=request.get('track','mix')
                self.track.current(0 if track=='mix' else next((i+1 for i,a in enumerate(media.audio) if str(a['index'])==str(track)),0))
                pending=next((name for name,row in record.get('stages',{}).items() if row.get('status') in ('failed','cancelled','running')),record.get('current_stage','identify'))
                self.resume_info.set(f'Checkpoint disponível • {STAGES.get(pending,pending)}. Retomar reaproveita etapas/lotes válidos; configurações alteradas serão verificadas.')
            except (ValueError,TypeError):self.resume_info.set('Configuração antiga incompatível. Use o perfil econômico; os checkpoints anteriores serão preservados.')
        else:self.resume_info.set('Nova análise: ainda não há checkpoints válidos para esta identidade do arquivo.')
        self.refresh_jobs()

    def refresh_jobs(self):
        self._recent_records=recent_jobs()
        self.jobs_table.delete(*self.jobs_table.get_children())
        statuses={'complete':'Concluída','complete_with_warnings':'Com módulos pendentes','running':'Interrompida/em uso','cancelled':'Cancelada','failed':'Falhou'}
        for index,record in enumerate(self._recent_records):
            source=record.get('source',{})
            stage=record.get('current_stage','identify')
            self.jobs_table.insert('','end',iid=str(index),values=(Path(source.get('path','')).name,statuses.get(record.get('status'),'Pendente'),STAGES.get(stage,stage)))

    def open_recent_analysis(self):
        if self.busy:return
        selected=self.jobs_table.selection()
        if not selected:return self.error('Selecione uma análise recente na lista.')
        record=self._recent_records[int(selected[0])]
        from .media import probe
        self.work(lambda:probe(record['source']['path'],self.cancel),self.loaded,message='Verificando original e checkpoints…')

    def resume_analysis(self):
        if self.busy:return
        self._dismiss_analysis_error()
        self.analyze()

    def analysis_cancelled(self):
        if self.media:self._has_resume=latest_request(self.media.path) is not None
        self.resume_info.set('Análise cancelada. Os lotes concluídos foram preservados. Clique em Retomar análise para continuar.')
        self.notify(self.resume_info.get());self.refresh_jobs();self._sync_controls()

    def analysis_failed(self,exc):
        if not isinstance(exc,StageError):return self.error(exc)
        self._has_resume=True
        self.resume_info.set(f'Falhou em {STAGES.get(exc.stage,exc.stage)}. Checkpoints preservados; a retomada revalida original e configurações.')
        self.notify(self.resume_info.get())
        self._dismiss_analysis_error()
        from . import ui
        self._analysis_error_dialog=ui.analysis_failure(self,exc)
        self.refresh_jobs();self._sync_controls()

    def skip_failed_module(self,stage):
        if self.busy:return
        if stage in ('audio','extract'):
            self.option_vars['audio'].set(False);self.model.set('off')
        elif stage=='visual':self.option_vars['visual'].set(False)
        self._dismiss_analysis_error()
        self.analyze()

    def _dismiss_analysis_error(self):
        if self._analysis_error_dialog is not None:
            self._analysis_error_dialog.destroy();self._analysis_error_dialog=None
            self._text_widgets[:]=[widget for widget in self._text_widgets if widget.winfo_exists()]
