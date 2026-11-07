from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile
from .media import probe, extract_audio, align_bounds, check_cancel, Cancelled
from .signals import sound_features, visual_features
from .transcription import transcribe
from .candidates import generate
from .model import Cut


def analyze(path, track='mix', count=10, minimum=15., maximum=60., model='tiny',
            cache_dir='temporarios', cancel=None, progress=lambda *a: None):
    media = probe(path)
    if not 1 <= count <= 20 or not 1 <= minimum <= maximum <= 600:
        raise ValueError('Configuração de duração ou quantidade inválida.')
    if track != 'mix' and int(track) not in [a['index'] for a in media.audio]:
        raise ValueError('Faixa de áudio inexistente.')
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    stat = Path(media.path).stat()
    key = hashlib.sha256(json.dumps([2, media.path, stat.st_size, stat.st_mtime_ns, track, model]).encode()).hexdigest()
    cache = cache_dir / (key + '.json')
    warnings = []
    if cache.exists():
        data = json.loads(cache.read_text(encoding='utf-8'))
        sound, visual, speech = data['sound'], data['visual'], data['speech']
        warnings = data.get('warnings', [])
        progress(85, 'Reutilizando análise em cache…')
    else:
        with tempfile.TemporaryDirectory(prefix='radar-', dir=cache_dir) as tmp:
            audio = Path(tmp) / 'audio.wav'
            sound, speech = [], []
            if media.audio:
                progress(5, 'Extraindo áudio para disco…')
                extract_audio(media, audio, track, cancel)
                progress(30, 'Medindo variações sonoras…')
                sound = sound_features(audio, cancel)
            visual = visual_features(media, cancel, progress)
            if model != 'off' and media.audio and any(s['db'] > -50 for s in sound):
                try:
                    speech = transcribe(audio, model, cancel, progress)
                except Cancelled:
                    raise
                except Exception as e:
                    warnings.append(f'Transcrição indisponível ({type(e).__name__}). Verifique o modelo local ou conexão para o primeiro download. Análise sem fala; pontuação limitada.')
            elif model == 'off':
                warnings.append('Transcrição desativada. Limites e contexto requerem revisão humana.')
            if not warnings or model == 'off':
                temp = cache.with_suffix('.tmp')
                temp.write_text(json.dumps({'sound': sound, 'visual': visual, 'speech': speech, 'warnings': warnings}), encoding='utf-8')
                temp.replace(cache)
    check_cancel(cancel)
    progress(88, 'Classificando e alinhando aos quadros originais…')
    cuts = generate(media, sound, visual, speech, count, minimum, maximum)
    aligned = []
    for cut in cuts:
        cut.start, cut.end = align_bounds(media, cut.start, cut.end, cancel)
        if minimum - 1e-6 <= cut.duration <= maximum + 1e-6:
            cut.id = len(aligned) + 1
            aligned.append(cut)
    if media.variable_fps:
        warnings.append('Possível taxa de quadros variável: use timestamps; números de quadro são nominais.')
    progress(100, f'Concluído: {len(aligned)} sugestões. A pontuação é heurística, não previsão de viralização.')
    return media, aligned, speech, warnings
