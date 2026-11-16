# Auditoria para pré-edição 0.9

Base: `e82664b`, branch principal consultada em 16/11/2026. Branch de trabalho: `feature/radar-0.9-preeditor`. Versão distribuída: **0.8.0**, conforme README, Inno Setup e GitHub Actions; o título “2.0” é histórico, não versão instalada neste ambiente. Nenhum aplicativo Windows está instalado aqui.

## Inventário e contratos

Árvore rastreada inspecionada com `rg --files`, incluindo README, todos os documentos Markdown em docs, testes, BAT, scripts, spec PyInstaller, Inno Setup e workflow Windows. Sem AGENTS.md no checkout.

| Componentes | Implementação existente / reutilização |
| --- | --- |
| model, candidates, intelligence | Media/Cut em segundos do primeiro quadro; sugestões de highlights, índices de fala e contexto lexical. Não há modelo de sequência completa nem decisões de remoção. |
| signals, media | RMS/peak/envelopes por segundo, imagem reduzida, FFprobe e alinhamento PTS real. Silêncio acústico não é VAD nem reconhecimento de cutscene. |
| pipeline, transcription | Lotes CPU limitados, Whisper opcional e VAD no Whisper; saída pública `(media,cuts,speech,warnings)`, preservada. |
| checkpoints, control | Identidade amostrada, hashes de configurações, bloqueio por fonte, escrita atômica, cancelamento/pausa e retomada. |
| projects | Projeto v1/v2 com integridade, limites, salvamento atômico e publicação sem sobrescrita. Sem undo/redo ou pré-edição. |
| timeline, desktop_studio | Canvas Tk com zoom/pan, IN/OUT, waveform e cortes manuais. FFplay externo; sem reprodução contínua embutida. |
| gui, ui, desktop_workspace | Worker e fila de eventos; navegação azul, biblioteca e projetos recentes; manter o fluxo e recursos existentes. |
| export, captions | MP4 multifaixa, fila recuperável, legendas manuais, ASS/SRT e enquadramento; não substituir. |
| filmcraft | OTIO e WAVs separados, CLI inspecionada em runtime, projeto novo por operação, reabertura. Hoje cria uma sequência por Short, não uma única pré-edição. |
| Windows | PyInstaller/Inno Setup/Actions com gates reais antes da release; preservar e ampliar smoke, sem publicar tag. |

## Limites e riscos observados

- Exportar mix + voz + jogo simultaneamente pode duplicar áudio. Pré-edição deve oferecer seleção explícita, sem alegar identificar conteúdo pelas etiquetas.
- WAVs estéreo PCM48 usam aproximadamente 691 MB/h/faixa. Não há cache seguro com gestão de referências para apagá-los; nunca removê-los automaticamente.
- Imagem amostrada e ausência de transcrição não provam ausência de narrativa. Proteção exige áudio do jogo e revisão de situações incertas.
- Sinais compactos crescem com a duração. Offsets não nulos podem obrigar decodificação repetida; não afirmar ganhos sem comparação.
- VFR usa timestamps reais na análise, taxa nominal no editor; HDR/multicanal e round-trip Windows requerem validação específica.
- Dependências diretas fixadas; transitivas não fixadas. Nenhuma dependência nova planejada.
- Não há gameplays reais fornecidas para validação editorial, nem hardware Windows/i7-8565U neste ambiente.

## Arquitetura incremental

Manter Cut como highlight. Acrescentar modelo separado de pré-edição: fonte, faixas, sugestões justificadas, decisão humana, histórico reversível e marcadores. A sequência é o complemento das remoções **explicitamente aceitas**, mantendo referências ao tempo original. Modo somente marcar nunca reduz a sequência. Persistir opcionalmente no projeto v3, com leitura de v1/v2.

Detector usa sinais por faixa, limiares relativos limitados conservadoramente, duração, imagem e fala já disponível. Conteúdo de jogo audível é preservado; evidência ausente vira revisão. Não reconhecer eventos sem classificador validado. Reutilizar chaves de extração/sinais e lotes existentes; não executar ranking de Shorts desnecessariamente.

Interface de revisão dedicada dentro da navegação atual, com timeline existente, decisões explícitas, IN/OUT e undo/redo. Áudio: separar medição/sugestão de exportação opcional de uma cópia tratada. FilmCraft: uma timeline de todos os intervalos mantidos, WAV por faixa selecionada; CLI oficial ou OTIO, sem MP4 intermediário.

## Testes iniciais

Primeira tentativa: `pytest` ausente (código 127), antes de instalar dependências. Criado venv com requirements-dev existente. Preparado Xvfb local sem instalação no sistema e CLI oficial Linux 0.18.0, arquivo conferido contra SHA256SUMS oficial. Resultado da suíte inicial será registrado após término, antes de modificar código de produção.

Suíte inicial concluída **antes das alterações de produção**: `DISPLAY=:99 FILMCRAFT_CLI=<CLI oficial 0.18.0> .venv/bin/python -m pytest -q --junitxml=...`: **185 passed, 151,27 s**. Sem skips nesta execução Linux. Isso não constitui teste nativo Windows nem avaliação editorial.
