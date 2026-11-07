import math
import re
import numpy as np
from .model import Cut

HOOKS = re.compile(r'\b(olha|como|por que|porque|quê|não acredito|consegui|conseguimos|cuidado|espera|agora|nossa|caramba|mano|quase|finalmente)\b', re.I)


def generate(media, sound, visual, speech, count=10, minimum=15., maximum=60.):
    if not 1 <= count <= 20 or not 1 <= minimum <= maximum <= 600:
        raise ValueError('Use 1–20 sugestões e durações entre 1 e 600 s, mínima ≤ máxima.')
    if media.duration < minimum:
        return []
    db = np.array([s['db'] for s in sound], dtype=float)
    baseline = float(np.median(db)) if len(db) else -60
    spread = max(6., float(np.std(db))) if len(db) else 6
    events = {}
    for s in sound:
        t = s['t']
        # Relative transients plus audible floor; silence and constant loudness are not candidates.
        prev = sound[max(0, t - 3):t]
        local = float(np.mean([x['db'] for x in prev])) if prev else baseline
        strength = min(1, max(0, (s['db'] - max(baseline, local)) / (2 * spread))) if s['db'] > -45 else 0
        if strength > .15:
            events.setdefault(t, {})['audio'] = strength
    for v in visual:
        if v['change'] > .07:
            events.setdefault(v['t'], {})['visual'] = min(1, v['change'] / .4)
    for seg in speech:
        hook = len(HOOKS.findall(seg['text']))
        if hook or '?' in seg['text'] or '!' in seg['text']:
            events.setdefault(int(seg['start']), {})['speech'] = min(1, .4 + hook * .2)
    candidates = []
    for t, signals in events.items():
        start = max(0., t - 5)
        end = min(media.duration, start + min(maximum, max(minimum, 30.)))
        nearby = [s for s in speech if s['end'] > start and s['start'] < end]
        if nearby:
            # Include complete segments where duration permits, then snap away from words.
            start = max(0, min(start, nearby[0]['start'] - .15))
            end = min(media.duration, max(end, nearby[-1]['end'] + .15))
            if end - start > maximum:
                end = start + maximum
            for seg in speech:
                for word in seg.get('words', []):
                    if word['start'] < start < word['end']:
                        start = max(0, word['start'] - .05)
                    if word['start'] < end < word['end']:
                        end = min(media.duration, word['end'] + .05)
        if end - start < minimum:
            start = max(0, end - minimum)
        if not minimum - 1e-6 <= end - start <= maximum + 1e-6:
            continue
        text = ' '.join(s['text'] for s in speech if s['start'] >= start and s['end'] <= end)
        context = min(1, len(text.split()) / 35)
        components = {'gancho_fala': round(30 * signals.get('speech', 0), 1),
                      'variação_sonora': round(25 * signals.get('audio', 0), 1),
                      'atividade_visual': round(20 * max([v['change'] / .4 for v in visual if start <= v['t'] <= end] or [0]), 1),
                      'fala_completa': round(25 * context, 1)}
        components['atividade_visual'] = min(20, components['atividade_visual'])
        # A single loud event cannot qualify without speech or visual corroboration.
        if signals.get('audio') and not text and components['atividade_visual'] < 3:
            continue
        score = round(min(100, sum(components.values())), 1)
        if score < 18:
            continue
        reason = '; '.join(f'{k.replace("_", " ")}: {v:g} pontos' for k, v in components.items() if v)
        reason += '. Contexto narrativo e emoção não confirmados; revisar manualmente.'
        title = (text[:80] if text else f'Atividade audiovisual em {t // 60:02}:{t % 60:02}')
        candidates.append(Cut(0, start, end, score, title, reason, text, components=components))
    chosen = []
    for cut in sorted(candidates, key=lambda c: c.score, reverse=True):
        if all(max(0, min(cut.end, c.end) - max(cut.start, c.start)) / min(c.duration, cut.duration) < .35 for c in chosen):
            cut.id = len(chosen) + 1
            chosen.append(cut)
            if len(chosen) == count:
                break
    return chosen
