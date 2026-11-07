# Radar de Cortes — CefasGamer

Aplicativo desktop em português para revisar gravações longas de gameplay e localizar intervalos aproveitáveis. Processa localmente em CPU, oferece faixas OBS, análise sonora/visual, transcrição opcional, pontuação explicável, revisão manual e exportação. Não prevê viralização nem reconhece semanticamente acontecimentos de jogos.

## Instalação com assistente (recomendada)

Baixe o arquivo **RadarCortes-Setup-…-Windows-x64.exe** na [página de versões](https://github.com/PedroHenrique1788/Radar/releases). Execute-o, conclua o assistente e abra **Radar de Cortes** no Menu Iniciar. A Área de Trabalho pode receber um atalho opcional. Não baixe “Source code” para esse modo de instalação.

O pacote inclui Python, FFmpeg/FFprobe/FFplay e o modelo `tiny` de transcrição em CPU. O uso básico funciona sem instalar dependências nem baixar modelos na primeira abertura. `base` e `small` continuam opcionais e precisam de download. FilmCraft é um aplicativo separado, opcional.

Instala por usuário, sem exigir administrador. Caches, logs e resultados ficam em `%LOCALAPPDATA%\RadarCortes`, separados dos arquivos instalados. O desinstalador aparece nas configurações de aplicativos do Windows e preserva vídeos e dados do usuário. O instalador ainda não é assinado com certificado comercial; o Windows pode identificar o editor como desconhecido. Confira a origem e o SHA-256 publicado.

### Gerar o instalador

A automação [Instalador Windows](https://github.com/PedroHenrique1788/Radar/actions/workflows/windows-installer.yml) executa em Windows x64 quando uma tag `v*` é enviada ou quando iniciada manualmente. Instala dependências, verifica SHA-256 do FFmpeg, inclui o modelo `tiny` em revisão fixa, roda os testes, empacota com PyInstaller e gera o assistente Inno Setup. Executa testes reais no EXE e no aplicativo instalado, incluindo GUI, mídia sintética, transcrição de uma amostra de português, VAD e exportação. Só publica uma release após esses testes passarem. Instalação silenciosa e desinstalação também são verificadas. Artefatos incluem manifesto de componentes e SHA-256.

As dependências de build estão em `packaging/requirements-build.txt`, entradas/receita em `packaging/` e a automação em `.github/workflows/windows-installer.yml`. Para testar o pacote manualmente: `RadarCortes.exe --self-test C:\caminho\relatorio.json`. O relatório informa falhas sem depender de uma janela de console.

## Instalar pelo código-fonte no Windows 10/11

1. Instale **Python 3.12 de 64 bits** (3.11 também aceito) pelo [python.org](https://www.python.org/downloads/windows/). Inclua **Tcl/Tk**, pip e Python Launcher. Não use o Python embutido de outro aplicativo.
2. Instale FFmpeg a partir dos links de builds Windows da [página oficial](https://ffmpeg.org/download.html). Extraia e adicione a pasta `bin` ao `PATH`; abra um novo terminal e confirme `ffmpeg -version`, `ffprobe -version` e `ffplay -version`. Se preferir, configure `FFMPEG_PATH`, `FFPROBE_PATH` e `FFPLAY_PATH` com os caminhos completos dos executáveis.
3. Extraia/clone este projeto e dê duplo clique em **instalar.bat**. O instalador cria `.venv` e instala dependências gratuitas. Não exige CUDA ou uma chave de API.
4. Abra **iniciar.bat**. O primeiro uso de um modelo de fala baixa seus pesos do Hugging Face; depois os arquivos ficam em cache. Esse download precisa de Internet. Escolha **off** para usar apenas áudio/imagem sem baixar modelos.

Use `tiny` no i7-8565U com MX110; `base` ou `small` consomem mais tempo e memória. A MX110 não é exigida. O FFmpeg precisa de libx264 e codificador AAC, presentes nos builds usuais.

## Usar

1. **Selecionar vídeo** (MP4, MKV, MOV ou AVI). Veja duração, resolução, FPS, codec e faixas disponíveis.
2. Escolha o microfone OBS para transcrição/análise sonora ou **Áudio completo (mix)**. A escolha afeta a análise; os MP4 exportados preservam todas as faixas de áudio.
3. Configure quantidade (1–20, padrão 10) e duração (padrão 15–60 s). Clique em **Analisar vídeo**. A interface continua responsiva; **Cancelar** interrompe operações e remove temporários de processamento.
4. Clique em um resultado para ler a justificativa, os componentes da pontuação e a transcrição. Clique no cabeçalho **Pontos** ou **Início** para ordenar. Ctrl permite selecionar vários cortes.
5. **Reproduzir trecho** cria uma prévia temporária recodificada e abre FFplay. **Ajustar início e fim** aceita `HH:MM:SS.mmm` e alinha aos quadros originais. O score permanece o da análise anterior após ajustes manuais.
6. **Copiar tempos**, exportar **JSON/CSV**, **SRT** ou **MP4**. O vídeo original é sempre protegido. Um MP4 existente só é substituído após confirmação e após concluir a nova exportação; relatórios e legendas usam destinos novos. Os MP4 mantêm resolução, proporção e faixas de áudio; não há conversão automática para 9:16.

A pontuação soma gancho lexical (até 30), variação sonora (25), atividade visual (20) e quantidade de fala completa disponível (25). Alto ≥70, médio ≥45, baixo <45. “Fala completa” é uma aproximação lexical, não uma avaliação semântica de começo/meio/fim. Sons constantes ou silêncio não geram sugestões por si só; volume sem fala/atividade visual não basta. O sistema pode retornar menos de 5 sugestões ou nenhuma. Revise ganchos, contexto, emoção e desfecho; os títulos são trechos literais da fala ou descrições neutras de atividade.

## Tempos, memória e precisão

Todos os tempos usam o **primeiro quadro do vídeo original como zero**, sem perder posição após blocos de transcrição. HH:MM:SS.mmm é uma representação de segundos, não timecode SMPTE. O leitor considera PTS inicial e atraso das faixas. A transcrição usa WAV mono 16 kHz em disco e blocos de cinco minutos (os limites desses blocos ainda podem prejudicar frases). Cada bloco recebe novamente seu deslocamento original. Amostragem visual: 1 quadro/s em 64×36; mede diferenças entre imagens, sem fingir reconhecer ações. Essa alternativa ao PySceneDetect reduz dependências e não produz uma lista exaustiva de cenas.

A análise percorre o arquivo inteiro. Mantém features por segundo e transcrição em memória, não todos os quadros nem o áudio completo. O uso cresce com a duração; não existe garantia de duração ilimitada. WAV temporário mono usa aproximadamente 115 MB/h; a integração com editor gera aproximadamente **691 MB/h por faixa** estéreo PCM 48 kHz. Garanta espaço em disco. Não há benchmark em gravações reais de muitas horas neste ambiente.

Os limites sugeridos são alinhados aos PTS de quadros próximos usando FFprobe. Em VFR, índices de quadro no JSON são **nominais**, não índices reais; utilize os tempos. A detecção de VFR por taxas médias é apenas indicativa. Transcrição e amostragem visual não garantem a fronteira perfeita de uma frase: revise cada corte. A exportação FFmpeg recodifica por timestamps em vez de copiar por keyframes; a precisão final é limitada pelos quadros/amostras existentes. Em arquivos com origem temporal zero, a exportação busca perto do intervalo para evitar decodificar horas anteriores. Arquivos com offsets usam o caminho conservador para preservar sincronismo. A publicação do MP4 funciona também sem hard links (exFAT/FAT32/compartilhamentos); FAT32 continua limitado a arquivos de 4 GB. Imagens com dimensões ímpares recebem até 1 pixel de borda para compatibilidade H.264.

Features e transcrições bem-sucedidas são reutilizadas em `temporarios/`, identificadas por caminho, tamanho, data do vídeo e parâmetros. A análise sem transcrição também fica em cache. Falhas de fala não são armazenadas como sucesso. Alterar o arquivo sem mudar tamanho/data não invalida o cache: apague o cache manualmente nesse caso. Logs em `temporarios/radar.log`. Não execute duas instâncias simultaneamente usando a mesma pasta de cache.

## FilmCraft

Baseado na [documentação oficial de agentes](https://github.com/storytold/filmcraft/blob/main/docs/agents.md), [protocolo de controle](https://github.com/storytold/filmcraft/blob/main/docs/control-protocol.md) e importador OTIO. Validado com **CLI 0.18.0 para Linux e Windows x64**, incluindo abertura de projeto no FilmCraft desktop Windows pelo teste do executável empacotado. Nenhuma API de IA paga é usada.

1. Instale o FilmCraft desktop oficial no Windows. A CLI acompanha o MSI, normalmente em `%LOCALAPPDATA%\Programs\ArtCraft\FilmCraft\filmcraft-cli.exe` ou `C:\Program Files\ArtCraft\FilmCraft\filmcraft-cli.exe`.
2. Clique em **Conectar ao FilmCraft**. O Radar procura esses locais e o PATH, ou permite selecionar o executável do editor, a CLI ou usar a opção “Escolher instalação FilmCraft…”. Consulta o registro do instalador e lembra a instalação selecionada. Também aceita `FILMCRAFT_CLI`. Confere `--help` e os esquemas reais de `file.import` e `sequence.settings` antes de editar.
3. Selecione os cortes e use **Enviar cortes selecionados** para criar um projeto novo com uma sequência por Short. **Criar projeto com todos os cortes** usa todos os resultados; **Criar projeto individual por Short** gera um `.fcproj` por corte encontrado. Escolha uma pasta de saída. Cada operação cria uma subpasta própria, permitindo repetir exportações sem colidir nem alterar projetos anteriores.
4. O Radar gera timelines OTIO, WAVs auxiliares e um roteiro JSONL. A CLI importa o vídeo original, os áudios sincronizados, define títulos/resolução/FPS e salva `.fcproj` com `--save-as`. Em seguida reabre o projeto para conferir sua leitura. Preserve os WAVs, timelines e vídeo original nos mesmos locais. O projeto referencia mídia, não a incorpora.
5. **Abrir projeto para edição** inicia o FilmCraft localizado junto à CLI (ou a associação de arquivos do Windows). Revise e exporte no editor.

Cada faixa de áudio OBS é convertida em um WAV estéreo separado, com atraso original preservado. Isso evita depender do mapeamento implícito de faixas do importador e permite ajuste de volume no editor. Faixas com mais de dois canais são reduzidas a estéreo. A timeline pode somar microfone+mix e duplicar sons se a gravação já contiver ambas as versões; revise mute/ganho.

**Sem CLI:** os mesmos botões criam `.otio` com vídeo, faixas e intervalos; importe pelo menu de importação do FilmCraft. Não se fabrica um `.fcproj` nem se declara projeto nativo salvo nesse modo. Versões antigas podem não aceitar extensões de metadados OTIO de resolução: confira as configurações da sequência.

O MCP oficial (`filmcraft-cli mcp`) e o canal JSON (`filmcraft --control 9876`) foram investigados. A criação usa a CLI headless para manter a sessão atual do usuário intacta. Nenhum projeto existente é alterado; os comandos sempre partem de uma sessão nova. O módulo possui uma função de inspeção local, limitada a leitura, para o canal JSON: aceita apenas `127.0.0.1` e lê `FILMCRAFT_CONTROL_TOKEN` do ambiente, sem gravá-lo em logs ou argumentos. Caso use esse canal manualmente, gere 64 caracteres hexadecimais aleatórios para cada sessão e herde a mesma variável nos processos. O Radar não precisa desse token para o fluxo normal via CLI.

Limites: VFR é representado pela taxa nominal do editor, portanto revise arredondamentos no FilmCraft. Preservação de HDR, colorimetria avançada, rotação de metadados, pixel aspect ratio não quadrado e áudio multicanal não foram validados; a versão inicial se destina a gameplay SDR com pixels quadrados. O teste Windows abre um projeto num processo isolado do FilmCraft desktop e confirma a leitura pelo canal oficial de controle. Isso verifica a abertura, não todas as funções de edição manual. O servidor MCP não foi exercitado. A abertura nativa e exportação pela CLI Linux foram testadas.

## Desenvolvimento e testes

Python 3.12 + FFmpeg/FFprobe, Tkinter, NumPy, faster-whisper (CTranslate2 CPU int8) e OpenTimelineIO. Dependências diretas fixadas em `requirements.txt`; as transitivas são resolvidas pelo pip. Tkinter vem com Python no Windows; no Linux é um componente do sistema. As dependências e a GUI são verificadas em Python 3.12 Linux e Windows x64. PyAV é fixado em 16.0.1 porque a versão 19 removeu um argumento usado pelo faster-whisper 1.2.1; há um teste de decodificação real para detectar essa incompatibilidade. Os BAT de instalação pelo código-fonte não são executados na automação; o instalador pronto usa PyInstaller e Inno Setup.

```bash
python -m venv .venv
# Linux:
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m radar
# Modo sem interface:
.venv/bin/python -m radar video.mp4 --model off --track mix --min 15 --max 60 --output resultados/relatorio.json
# Para testar FilmCraft de verdade (caso contrário só esse teste é marcado skip):
FILMCRAFT_CLI=/caminho/filmcraft-cli .venv/bin/python -m pytest -q
# Interface com display real ou Xvfb:
DISPLAY=:99 FILMCRAFT_CLI=/caminho/filmcraft-cli .venv/bin/python -m pytest -q
```

No Windows, substitua `.venv/bin/python` por `.venv\Scripts\python.exe`. Para um modelo já baixado, a CLI aceita `--model C:\modelos\faster-whisper-tiny`. No ambiente cloud, o primeiro download está sujeito à allowlist do Hugging Face. Nenhuma chave é necessária para modelos públicos. Falha de transcrição gera aviso e continua com áudio/imagem; não equivale a transcrição validada.

Testes geram mídia sintética com FFmpeg e verificam leitura, duas faixas OBS, duração, HH:MM:SS.mmm, offsets, VFR, ausência de áudio/fala, falha de transcrição, offsets entre blocos de 300 s, cancelamento, seleção/deduplicação, relatórios, SRT, limites dos quadros e sincronismo após recodificação. A integração real usa três intervalos conhecidos, salva/reabre `.fcproj` e verifica sequências, faixas e tempos; exporta cada sequência pela CLI e confere duração, imagem e sincronismo dos tons. O teste de GUI verifica metadados, seleção, detalhes, cópia e ajuste assíncrono.

O teste de deslocamento entre blocos usa um transcritor simulado; ele não mede reconhecimento de fala. Separadamente, o teste do executável Windows carrega os pesos incluídos e transcreve uma amostra sintética conhecida de português com o modelo real, em modo offline. Esse teste confirma funcionamento básico, sem medir a qualidade em gravações reais de gameplay.

## Organização e próximos passos

`radar/model.py`: tempos/dados; `media.py`: FFprobe/extração; `signals.py`: features; `transcription.py`: fala em blocos; `candidates.py`: candidatos/pontuação; `pipeline.py`: fluxo/cache; `export.py`: MP4/CSV/JSON/SRT; `filmcraft.py`: integração; `gui.py`: interface; `__main__.py`: GUI/CLI.

Segunda etapa: análise semântica multimodal local e mensurada, avaliação em gameplay real, sobreposição entre blocos para frases nas fronteiras, ajuste de pontuação com avaliação humana, cache por etapas e retomada fina, player integrado com waveform, edição vertical opcional, detecção precisa de VFR e preservação completa de HDR/multicanal. Antes de distribuir, testar em Windows 10/11 com vídeos reais do OBS e modelos de fala.


## Revisão pelo ChatGPT e API

O botão **Copiar para ChatGPT** copia uma solicitação com os cortes selecionados, horários, transcrição e critérios locais. Cole o conteúdo numa conversa no ChatGPT e peça revisão de contexto e pesquisa de tendências, com fontes e datas. O arquivo de vídeo e seu caminho privado não são incluídos nesse texto. A revisão é manual e ocorre naquela conversa; o aplicativo não envia dados automaticamente.

**[ChatGPT Plus](https://help.openai.com/en/articles/6950777-what-is-chatgpt-plus) e API têm cobranças separadas.** O Plus não fornece créditos para chamadas de API de um aplicativo externo. Uma integração automática poderia usar uma chave própria, com orçamento e cobrança separados, e envio explícito dos trechos escolhidos. A versão atual oferece o fluxo manual sem chave. Pesquisa de tendências ajuda a embasar uma avaliação editorial, sem garantir viralização nem produzir probabilidades de engajamento não medidas.

### Atualização 0.1.2

Correções de exportação em sistemas de arquivos sem hard links, repetição de projetos na mesma pasta, detecção/persistência da instalação FilmCraft, ambiente de DLLs para processos externos no executável empacotado, mensagens copiáveis e confirmação do destino dos arquivos. A interface seleciona o primeiro resultado automaticamente, preserva seleção ao ordenar e adapta os controles a telas menores. Projetos individuais usam todos os cortes; “Enviar cortes selecionados” respeita a seleção. A automação Windows agora usa a CLI oficial real e testa também projetos conjuntos, individuais e abertura no editor a partir do aplicativo empacotado.
