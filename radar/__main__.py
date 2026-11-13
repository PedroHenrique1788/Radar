import argparse
import sys
from pathlib import Path
from .pipeline import analyze
from .export import export_report,export_clips
from .profiles import AnalysisOptions
from .control import ExecutionControl,ResourceLimitError
from .checkpoints import StageError


def main():
    parser = argparse.ArgumentParser(description='Radar de Cortes — CefasGamer')
    parser.add_argument('video', nargs='?')
    parser.add_argument('--model', default='off', help='off (local sem fala), tiny/base/small ou pasta local')
    parser.add_argument('--track', default='mix', help='mix ou índice global da faixa')
    parser.add_argument('--external-audio',default='',help='Áudio separado usado somente na análise/transcrição')
    parser.add_argument('--audio-offset',type=float,default=0.,help='t_vídeo = t_áudio + ajuste; positivo se o microfone começou depois')
    parser.add_argument('--audio-role',choices=['auto','microphone','mixed'],default='auto')
    parser.add_argument('--phrases',help='Expressões personalizadas separadas por ponto e vírgula; vazio desliga a busca lexical')
    parser.add_argument('--count', type=int, default=10)
    parser.add_argument('--min', type=float, default=15)
    parser.add_argument('--max', type=float, default=60)
    parser.add_argument('--output', default='resultados/relatorio.json')
    parser.add_argument('--threads',type=int,default=2)
    parser.add_argument('--max-processes',type=int,default=1)
    parser.add_argument('--memory-mb',type=int,default=1024)
    parser.add_argument('--sample-fps',type=float,default=.5)
    parser.add_argument('--visual-width',type=int,default=64)
    parser.add_argument('--batch-seconds',type=int,default=300)
    parser.add_argument('--no-audio',action='store_true')
    parser.add_argument('--no-visual',action='store_true')
    parser.add_argument('--before',type=float,default=5)
    parser.add_argument('--after',type=float,default=10)
    parser.add_argument('--export-dir',help='Exportar sugestões em fila; repetir pasta/parâmetros retoma clipes íntegros')
    args = parser.parse_args()
    if not args.video:
        from .gui import App
        App().mainloop()
        return
    try:
        options=AnalysisOptions(threads=args.threads,max_processes=args.max_processes,memory_mb=args.memory_mb,
            sample_fps=args.sample_fps,visual_width=args.visual_width,batch_seconds=args.batch_seconds,
            audio=not args.no_audio,visual=not args.no_visual,before=args.before,after=args.after,
            external_audio=args.external_audio,external_offset=args.audio_offset,audio_role=args.audio_role)
        if args.phrases is not None:options.phrases=args.phrases
        options.validate()
    except ValueError as exc:parser.error(str(exc))
    control=ExecutionControl(options)
    progress=lambda n,msg:print((f'{n:.1f}% da etapa ' if n is not None else '[atividade] ')+msg,flush=True)
    try:
        media,cuts,speech,warnings=analyze(args.video,args.track,args.count,args.min,args.max,args.model,
            cancel=control,options=options,progress=progress)
        if args.export_dir:export_clips(media,cuts,args.export_dir,control,progress=progress)
        target=Path(args.output)
        if target.suffix.lower() in ('.json','.csv') and target.resolve()!=Path(media.path).resolve():
            base=target;version=1
            while target.exists():
                version+=1;target=base.with_name(f'{base.stem}_{version}{base.suffix}')
        export_report(media,cuts,target,speech=speech)
    except KeyboardInterrupt:
        control.set()
        print('Cancelado. Reexecute o mesmo comando para retomar os lotes concluídos.',file=sys.stderr)
        raise SystemExit(130)
    except (RuntimeError,ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr);raise SystemExit(1)
    for warning in warnings:
        print('Aviso:', warning)
    print(f'Relatório: {target.resolve()}')


if __name__ == '__main__':
    main()
