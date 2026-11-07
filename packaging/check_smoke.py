"""Publish a structured package-test failure as a GitHub check annotation."""
import json
import os
from pathlib import Path
import sys


def annotate(message):
    text=message.replace('%','%25').replace('\r','%0D').replace('\n','%0A')
    print('::error title=Teste do aplicativo instalado::'+text)


if __name__ == '__main__':
    report=Path(sys.argv[1])
    if not report.exists():
        startup=Path(os.environ['LOCALAPPDATA'])/'RadarCortes'/'temporarios'/'startup.log'
        annotate('O executável não gerou o relatório. '+ (startup.read_text(encoding='utf-8',errors='replace')[-12000:] if startup.exists() else 'Sem log de inicialização.'))
        raise SystemExit(1)
    result=json.loads(report.read_text(encoding='utf-8'))
    if not result.get('ok'):
        annotate(result.get('error','Smoke test falhou.'))
        raise SystemExit(1)
    print(json.dumps(result,ensure_ascii=True))
