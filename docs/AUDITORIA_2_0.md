# Cefas Radar de Cortes 2.0 — auditoria e evolução incremental

## Base inspecionada

Commit inicial: `7764a97`, aplicativo 0.3.0. Suíte anterior à edição: **84 testes passaram em Linux em 23,81 s**, com Xvfb, FFmpeg e FilmCraft CLI oficial real. Não é um benchmark de gameplay longo nem uma medição no Lenovo de referência.

O projeto é Python/Tkinter, com operações em thread e fila de eventos para a interface. `__main__.py` oferece GUI/CLI; `pipeline.py` encadeia FFprobe, áudio, imagem, Faster-Whisper opcional, candidatos e alinhamento. `export.py` recodifica MP4 por PTS e gera CSV/JSON/SRT/TXT; `filmcraft.py` usa CLI oficial/OTIO, sem automação de mouse. `runtime.py` separa dados do instalador e restaura o ambiente de ferramentas externas. PyInstaller, Inno Setup e GitHub Actions verificam o executável e a instalação nativa Windows.

Operacionais: leitura de mídia/faixas OBS, transcrição local CPU int8 em blocos de cinco minutos, análise RMS e diferenças visuais em baixa resolução, notas explicáveis, ajustes de limites, prévia/FFplay, MP4 e relatórios, projetos FilmCraft conjuntos/individuais e revisão Gemini. A chave é opcional do ponto de vista do motor, mas a GUI 0.3.0 bloqueia o início até configurá-la; isso precisa mudar para cumprir a nova Fase 1.

Parciais: o cache JSON é gravado ao final de áudio/imagem/fala; uma falha anterior repete essas etapas. O cancelamento encerra subprocessos e limpa temporários, mas não há pausa nem retomada persistente por lote. O progresso mistura percentuais fixos e medições. Os pesos são fixos e não são normalizados quando faltam sinais.

Planejados para fases posteriores: áudio externo sincronizado e novos indicadores vocais, timeline com waveform/marcadores, favoritos/classificação manual, formatos verticais/presets, rastreamento e organização completa do estúdio. As funções existentes de fala, edição e exportação permanecem disponíveis.

## Gargalos e decisões da Fase 1

- CPU: decodificação de vídeo, FFmpeg/x264 e Whisper. O gerador também percorre todos os sinais novamente para cada candidato; será indexado por tempo e limitado a uma lista de candidatos preliminares. A amostragem reduz a análise e a RAM, mas o decoder ainda pode precisar decodificar quadros entre keyframes.
- RAM: já se lê áudio/quadros em streaming, mas listas de sinais crescem com a duração e o Whisper mantém modelo e buffers. Lotes limitados, um modelo por vez, medição e limite de memória evitam tratar 20 GB como recursos ilimitados.
- Disco: WAV mono 16 kHz/16 bits ocupa aproximadamente 115 MB/h. Lotes de até 300 s evitam WAVs individuais gigantes; checkpoints persistem em `temporarios/`, separados dos originais. Espaço livre é conferido antes de extrair cada lote. WAVs estéreo usados pelo FilmCraft continuam separados e maiores.
- Confiabilidade: manter JSON e estender o cache existente com manifestos e resultados atômicos por etapa/lote, sem criar uma segunda base SQLite redundante. Identidade do original e assinaturas das configurações impedem reutilização indevida. Arquivos antigos não serão apagados automaticamente.
- Controle: adicionar `psutil` como dependência pequena e multiplataforma para medir CPU/RAM e suspender apenas os subprocessos pertencentes à tarefa. A interface permanece ativa. Trabalho interno de bibliotecas coopera nos limites das unidades; a UI diferencia pedido de pausa de pausa confirmada.

## Sequência de entrega

1. Motor local e perfil **Modo Econômico — Lenovo MX110**, limites de recursos e checkpoints por lote para identificação, extração, áudio, imagem, fala opcional, fusão/classificação e exportação.
2. Retomada após cancelamento/falha/reabertura, progresso real por etapa, diagnóstico do módulo que falhou e continuação sem módulos opcionais.
3. Notas com pesos configuráveis/normalizados, busca eficiente por tempo, preservação dos limites originais e fila sequencial de MP4 recuperável.
4. Integração na navegação Tkinter atual, regressões automatizadas e documentação de uso/limites. O pipeline Windows será preservado e só poderá liberar um instalador após seus testes nativos passarem.

As Fases 2 e 3 não serão declaradas prontas por existirem botões ou telas. Sem um detector validado, não se atribuem eventos específicos do jogo, emoções certas ou probabilidade de viralização.
