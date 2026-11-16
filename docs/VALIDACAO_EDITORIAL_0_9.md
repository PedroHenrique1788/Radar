# Protocolo editorial — três gameplays reais

Estado: **pendente de mídia real**, sem resultados inventados. Testes sintéticos não medem preservação narrativa.

Escolher, com autorização local do dono: (A) gameplay narrativa com cutscene longa sem narrador, (B) ação/Soulslike com preparação, tentativa, pausa e reação, (C) roguelike/gameplay completa com menus, exploração e variação sonora. Conservar MKV multifaixa, metadados OBS e SHA-256 integral antes/depois. Não enviar mídia ou transcrição a serviços.

Um revisor marca manualmente intervalos removíveis e protegidos antes de ver as sugestões. Registrar perfil, origem, FPS/VFR, offsets, papéis das faixas, versão/hash do Radar, FFmpeg, CPU, RAM, disco, configuração e duração. Usar a mesma amostra/configuração em comparações; separar cache frio e quente.

Para cada sugestão registrar início/fim, decisão, limites corrigidos, motivo e se prejudicaria diálogo, preparação, desfecho ou continuidade. Considerar correspondência com intervalo manual quando IoU temporal ≥ 0,5; não contar múltiplas sugestões para o mesmo trecho como múltiplos acertos. Relatar também interseção em segundos para evitar viés de fragmentação.

| Métrica | Cálculo / coleta |
| --- | --- |
| Precisão | sugestões úteis / total de sugestões de remoção |
| Cortes úteis perdidos | intervalos manuais sem correspondência / total manual |
| Sugestões incorretas | quantidade e duração não removíveis |
| Contexto prejudicado | quantidade e duração, com motivo editorial |
| Tempo de revisão | cronômetro, incluindo correções IN/OUT |
| Processamento | tempo de parede; cache frio e quente separados |
| RAM máxima | Radar + subprocessos amostrados; informar frequência |
| CPU e disco | segundos de CPU, bytes lidos/escritos, crescimento do cache |
| Sincronismo | conferir fala, tons/efeitos e PTS em início, cortes e fim no FilmCraft |

Não aceitar versão estável sem revisar todos os cortes dessas três amostras e investigar qualquer corte que prejudique contexto. Conservar projeto .radar.json, OTIO, WAVs e relatório do editor. Reabrir projeto Radar/FilmCraft, ajustar um corte e um ganho independentemente e exportar pelo editor. Repetir no Windows x64 com instalador, inclusive cancelamento/retomada e original intacto.
