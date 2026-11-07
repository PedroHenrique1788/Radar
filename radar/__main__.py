import argparse
from pathlib import Path
from .pipeline import analyze
from .export import export_report


def main():
    parser = argparse.ArgumentParser(description='Radar de Cortes — CefasGamer')
    parser.add_argument('video', nargs='?')
    parser.add_argument('--model', default='tiny', help='tiny/base/small, pasta local ou off')
    parser.add_argument('--track', default='mix', help='mix ou índice global da faixa')
    parser.add_argument('--count', type=int, default=10)
    parser.add_argument('--min', type=float, default=15)
    parser.add_argument('--max', type=float, default=60)
    parser.add_argument('--output', default='resultados/relatorio.json')
    args = parser.parse_args()
    if not args.video:
        from .gui import App
        App().mainloop()
        return
    media, cuts, speech, warnings = analyze(args.video, args.track, args.count, args.min, args.max, args.model,
        progress=lambda n, msg: print(f'{n:.0f}% {msg}', flush=True))
    export_report(media, cuts, args.output)
    for warning in warnings:
        print('Aviso:', warning)
    print(f'Relatório: {Path(args.output).resolve()}')


if __name__ == '__main__':
    main()
