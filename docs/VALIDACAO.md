# Validação

## Evolução 2.0, Fase 3 — preparação 0.6.0 (13 de novembro de 2026)

Base: commit `e2a0ec6`, sem alterações pendentes antes do trabalho. A suíte anterior passou com **131 testes em 96,81 s**. Também foi confirmado o resultado da execução Windows da Fase 2: [43489998486](https://github.com/PedroHenrique1788/Radar/actions/runs/43489998486), incluindo código, PyInstaller, EXE offline, instalação, teste instalado e desinstalação. Esse workflow produziu um artefato 0.5.0-dev; não publicou uma release.

A Fase 3 passou na suíte completa com **150 testes em 124,07 s**, Python 3.12, FFmpeg real, FilmCraft oficial e Tk/Xvfb. Os 19 casos novos incluem dimensões dos quatro formatos, duração/áudio preservados, recortes esquerdo/direito conferidos por pixels, legenda visível somente durante as palavras do corte, texto literal sem alteração de posicionamento ASS, áudio atrasado com PTS inicial não zero no MP4 vertical, fila com reutilização e separação por preset, picos PCM e zoom com cache independente, silêncio/cancelamento, projetos com favoritos/revisão/falas/presets, reconexão de original movido, integridade e intervalos inválidos, falha de gravação mantendo o projeto anterior, exportação pela CLI sem análise e interação real da timeline.

Após incluir a prévia pequena no painel Timeline e o indicador de alterações não salvas no cabeçalho, os **18 testes de interface passaram em 20,80 s**. O ensaio percorre Shift+arrastar, criação/alinhamento de um corte, favorito, aprovação, posição de enquadramento, leitura das ondas, prévia extraída por FFmpeg, salvamento/reabertura e preservação de cortes manuais e títulos/observações editados após nova análise. Também confere os botões nos painéis Timeline/Organizar em uma janela de 1000×620.

Uma primeira rodada da suíte completa encontrou o Xvfb anterior encerrado: cinco testes GUI falharam e quatorze erros eram de conexão ao display. A rodada de 150 testes acima iniciou o display no mesmo processo de execução da suíte, com limpeza ao final, e passou. Nenhum erro de código foi mascarado ou teste GUI desativado.

### Executável Linux para verificação local

Foi gerado um executável real com PyInstaller 6.16.0, usando a receita existente, FFmpeg nativo e o modelo tiny incluído fisicamente. A receita passou a incluir explicitamente as bibliotecas Tcl/Tk encontradas no prefixo de um Python Linux standalone, pois elas não estavam nos caminhos usados pelo coletor automático. O preparo temporário também foi corrigido para copiar o modelo em vez de usar um link de diretório ignorado pelo coletor. A configuração e os hooks Windows continuam separados dessa condição Linux.

No executável congelado, o smoke passou pela interface, mídia/exportação, retomada, Whisper real CPU/int8, amostra portuguesa, VAD, áudio externo a +2,5 s, TXT/OTIO e FilmCraft oficial. O bloco novo `studio_roundtrip` concluiu MP4 720×1280 com legenda, áudio original, salvamento/reabertura, picos PCM, criação manual/favorito pela GUI e zoom da timeline.

**O smoke global Linux não ficou verde:** depois do bloco do estúdio, o cliente Gemini sem rede falhou ao construir o contexto TLS no Python específico deste executor (`ssl.SSLContext`, `FileNotFoundError`). A construção do mesmo contexto no Python fonte funciona. Não foi usada uma chave real, a verificação TLS não foi desativada e o gate Windows completo foi mantido. Este ensaio não comprova o instalador Windows 0.6.0. O binário Linux é uma verificação local, não um pacote distribuível.

### Entrega e limites

As alterações permanecem no rascunho local, respeitando a orientação de não publicar. Os arquivos de build foram preparados para 0.6.0-dev, e o smoke do pacote inclui as novas funções. Antes de disponibilizar um instalador Windows, é necessário autorizar o envio desta versão ao GitHub e passar novamente nos gates nativos do código, EXE, instalação, aplicativo instalado e desinstalação.

As capturas do [guia da Fase 3](FASE3.md) mostram a aplicação real em Tk 8.6, mídia sintética, cortes criados manualmente, ondas lidas do arquivo e prévia vertical efetivamente renderizada. Não houve medição no Lenovo i7-8565U/MX110, avaliação editorial com gameplay real ou chamada Gemini autenticada. SRT/ASS dependem dos tempos da transcrição; fonte externa continua não sendo incorporada automaticamente ao áudio do MP4. Projetos não incluem cópias dos vídeos nem credenciais.

## Evolução 2.0, Fase 2 — 0.5.0 (13 de novembro de 2026)

O trabalho partiu do commit `0157197`, sem alterações pendentes. Após reativar o Xvfb local e localizar o FilmCraft oficial, a base passou com **107 testes em 38,44 s**. Nenhuma dependência nova foi adicionada. O [guia da Fase 2](FASE2.md) descreve parâmetros, origem do áudio, retomada e limites.

A suíte local final passou com **131 testes em 66,01 s**, Python 3.12, Xvfb `:115`, FFmpeg e FilmCraft real. Os 24 casos novos cobrem áudio externo com +2,5/-2,5 s medidos nas amostras PCM, lotes posteriores, silêncio fora da cobertura, PTS inicial não zero, vídeo sem áudio, invalidação de áudio sem repetir imagem, fonte externa alterada durante o trabalho, arquivos/ajustes inválidos, relatórios JSON/CSV, expressões com acentos e palavras inteiras, reclassificação sem retranscrever, confiança menor no mix, ritmo com palavras cronometradas, pausas, preparação/desfecho, proteção de palavras/segmentos e restauração pelo desktop.

O teste funcional do pacote também foi executado localmente com modelo tiny real CPU/int8, VAD, amostra sintética em português, MP4/TXT, retomada e FilmCraft oficial. A amostra foi usada como áudio externo de um vídeo sem áudio a +2,5 s: houve transcrição e geração de sugestões, com palavras limitadas à cobertura real do microfone. Esse ensaio revelou que o Whisper estimava a primeira palavra em 2,1 s, antes do áudio existir; foi acrescentada uma limitação à cobertura, seguida de nova verificação funcional aprovada e teste de regressão. Isso corrige a extrapolação, não torna os horários internos do modelo exatos.

A CLI analisou e exportou um MP4 usando esse microfone, com JSON final; a segunda execução reutilizou as etapas e a fila íntegra, preservou o primeiro relatório e criou outro numerado. O MP4 conserva somente o áudio do vídeo original, como explicitado na interface. Capturas da configuração usam a aplicação real em Linux/Tk 8.6 com uma amostra local, sem chave ou chamada Gemini.

Esta suíte não mede qualidade editorial em gameplays reais nem desempenho no Lenovo i7-8565U/MX110. A fala é sintética e tiny apresenta erros de reconhecimento. Gemini usa respostas controladas, sem validar chave/cota real. A liberação do instalador 0.5.0 depende dos testes nativos Windows, do EXE offline, da instalação, do aplicativo instalado e da desinstalação. O smoke Windows inclui a nova análise/transcrição com áudio externo real a +2,5 s. Na primeira execução nativa, a suíte de 129 testes passou e o EXE foi gerado, mas o novo smoke não reconheceu a palavra esperada na amostra com silêncio acrescentado. Antes de liberar o instalador, a entrada do ASR foi refinada para decodificar apenas a cobertura real do microfone e reaplicar seu deslocamento nos horários. Dois testes adicionais verificam a retirada do silêncio artificial e a omissão de lotes totalmente fora da cobertura. A suíte local de 131 testes e o teste funcional com tiny real passaram após essa alteração.

## Evolução 2.0, Fase 1 — 0.4.1

A auditoria partiu do commit `7764a97`, sem alterações pendentes. A suíte prévia passou com **84 testes em 23,81 s**. O novo motor preserva a API principal e usa checkpoints JSON por etapa/lote, perfil CPU, controle por `psutil` e a navegação Tkinter existente. O guia atual está em [FASE1.md](FASE1.md); as seções posteriores deste documento são registros históricos das entregas anteriores.

Na validação local final da Fase 1, **107 testes passaram em 41,72 s** com Python 3.12, Xvfb `:114`, FFmpeg e FilmCraft oficial real. Essa execução inclui regressões, pausa de subprocesso sem bloquear a UI, cancelamento/retomada em nova tarefa, falha por lote e continuação sem módulo, reabertura de análise no desktop, integridade do cache, invalidação do original, cache independente da transcrição e pesos, limites de memória/processos, fila MP4 com retomada e preservação de arquivo editado, pesos normalizados, rejeição de atividade constante como destaque e fala atualizada no relatório após ajuste manual dos limites.

A CLI foi executada de ponta a ponta duas vezes sobre mídia sintética: a primeira analisou/exportou; a segunda reutilizou checkpoints e verificou o clipe sem recodificá-lo, preservando o relatório anterior e criando `report_2.json`. O teste auxiliar do pacote para Gemini também passou localmente com transporte controlado, confirmando início local sem API e manutenção da revisão opcional.

Um vídeo sintético de **30 minutos**, 32×18 a 0,25 fps, valida lotes e timestamps de uma transição conhecida aos 15 minutos. Ele não representa custo de decodificação de uma gameplay 1080p/4K nem prova desempenho no i7-8565U/MX110. A amostra Windows de português e as integrações nativas continuam no workflow, que deve passar antes de liberar o instalador. Gemini é testado com respostas controladas; não há chave pessoal ou validação da cota real.

Capturas da Fase 1 usam a aplicação real em Linux/Tk 8.6, vídeo sintético e análise local sem API, com métricas do ambiente de teste. Essas capturas não são medições do computador do usuário.

### Validação Windows e entrega

A release [0.4.1](https://github.com/PedroHenrique1788/Radar/releases/tag/v0.4.1), código `123ded3`, passou no workflow nativo [43476796828](https://github.com/PedroHenrique1788/Radar/actions/runs/43476796828): suíte de código, geração PyInstaller, teste do EXE offline, Inno Setup, instalação silenciosa por usuário, teste funcional do aplicativo instalado e desinstalação. O pacote verificou retomada dos checkpoints sem repetir extração/áudio/imagem, funcionamento local sem API, modelo tiny real CPU/int8 e amostra de português, MP4/TXT, FilmCraft oficial real e DPAPI. O fluxo Gemini usa transporte simulado.

A primeira rodada Windows encontrou duas leituras sem `encoding='utf-8'` nos testes de JSON; foram corrigidas sem alterar a gravação UTF-8 do aplicativo. A versão 0.4.1 também estabiliza a fila cronologicamente para reutilizar clipes concluídos mesmo após reordenar a tabela. O teste da fila foi repetido com a seleção invertida e passou localmente; a suíte Windows completa validou essa alteração antes da publicação.

## Registro inicial, antes do instalador Windows

Ambiente atual: Linux x86_64, Python 3.12.14, FFmpeg/FFprobe 7.1.5, Tk 9.0, NumPy 2.2.6, faster-whisper 1.2.1, OpenTimelineIO 0.18.1, FilmCraft CLI oficial 0.18.0. Testes GUI em Xvfb 1280×900; sem GPU necessária para análise e exportação.

Comando final executado:

```bash
DISPLAY=:99 FILMCRAFT_CLI=/workspace/tools/filmcraft/bin/filmcraft-cli \
  .venv/bin/python -m pytest -q --basetemp=/tmp/radar-tests-final
```

**23 passaram; nenhum falhou ou foi ignorado; 17,25 s.**

- Conversão de timestamps, arredondamento e vídeos com mais de 99 horas na representação temporal; rejeição de valores inválidos.
- Leitura de mídia sintética com duas faixas distintas e seleção de cada faixa/mix.
- Exportação FFmpeg: limites originais, duração, resolução, duas faixas e alinhamento entre mudança visual e pico sonoro.
- Relatórios CSV/JSON e legendas SRT relativas ao corte.
- Análise de todo o vídeo sintético, silêncio, vídeo sem áudio, arquivos inválidos, cancelamento e falha de transcrição.
- Deslocamento entre blocos de 300 s com transcritor simulado; cache de análise sem transcrição.
- PTS inicial não zero em MKV e atraso de áudio; alinhamento a quadros e vídeo VFR.
- Deduplicação e fronteiras de palavras nos candidatos.
- Interface: metadados, faixas, seleção, detalhe, copiar tempos e ajuste assíncrono.
- FilmCraft real: três intervalos (1,12–4,28 s; 17,12–20,68 s; 25,2–33,6 s), criação e reabertura de projeto, títulos, resolução, sequências, duas faixas, source-in e duração. Exportação de cada sequência pela CLI com CPU. No segundo intervalo, verificadas mudança de imagem e reação de 440 Hz na posição correta, mantendo o áudio independente de 880 Hz.

Também executados: instalação repetida por `scripts/setup_cloud.sh`, importações reais das bibliotecas e CLI headless do Radar sobre vídeo sintético, que gerou uma sugestão e `resultados/smoke.json`. O arquivo de mídia e os projetos de teste ficam em `/tmp/radar-tests-final`, temporários desta instância. Não são exemplos permanentes distribuídos.

O arquivo oficial FilmCraft foi validado com SHA256SUMS da release via HTTPS. Xvfb foi extraído sem root de pacote Debian, com índice InRelease assinado verificado pelas chaves do sistema e SHA-256 do pacote conferido.

## Pendente ou não validado

- **Reconhecimento real de português:** o acesso HTTPS ao Hugging Face retornou bloqueio de proxy (403). Importar faster-whisper passou, mas isso não comprova transcrição. Domínios foram propostos no rascunho do ambiente; aplicar a rede, baixar um modelo e testar uma amostra conhecida ainda é necessário.
- Windows 10/11, instaladores BAT, desktop FilmCraft no Windows, microfone/gravações reais do OBS e desempenho em vídeos de muitas horas não foram testados nesta máquina Linux.
- MCP/canal JSON ao vivo não foram exercitados; a integração validada usa a CLI headless oficial.
- Publicação e restauração em nova tarefa pertencem à interface de ambientes e não foram executadas por este trabalho.

Configuração reutilizável salva: `install_script`, `start_skill`, associação do checkout `Radar` e domínios de download de modelos. Salvar o rascunho não aplica a rede nem publica o snapshot. O repositório remoto estava vazio e o checkout em branch local ainda sem commits; os arquivos implementados permanecem locais, sem push.


## Validação adicional do pacote Windows

A automação nativa [Instalador Windows](https://github.com/PedroHenrique1788/Radar/actions/workflows/windows-installer.yml) verifica os executáveis no runner Windows Server 2022 x64 com Python 3.12. Isso não equivale a um teste manual no computador do usuário com Windows 10/11.

- A suíte atual passou em Linux: **27 testes**, com GUI Xvfb e integração real FilmCraft. No Windows, a suíte passou com o teste opcional da CLI FilmCraft ignorado, pois o editor não foi instalado nesse runner.
- O executável PyInstaller passou no teste com `HF_HUB_OFFLINE=1`: GUI, FFmpeg/FFprobe/FFplay incluídos, leitura e exportação MP4, JSON, OpenTimelineIO, carregamento de modelo tiny CPU int8, VAD sobre silêncio e reconhecimento real de uma amostra sintética de português. A amostra é gerada com eSpeak, não com gravação pessoal. Não mede precisão em gameplay.
- A validação real detectou incompatibilidade entre faster-whisper 1.2.1 e PyAV 19. O projeto agora fixa **PyAV 16.0.1**, com um teste adicional do decodificador.
- O modelo tiny é incluído na revisão `d90ca5fe260221311c53c58e660288d3deb8d356`; não depende do primeiro download no computador do usuário. Os resultados desta automação substituem a pendência inicial de reconhecimento básico no pacote Windows; o download direto de pesos nesta máquina cloud continuou bloqueado no CDN.
- O pacote inclui os runtimes Python/Visual C++, FFmpeg com verificação SHA-256 e licenças dos componentes. Não há assinatura digital de editor nesta versão.
- A execução [42419007223](https://github.com/PedroHenrique1788/Radar/actions/runs/42419007223) também passou na geração Inno Setup, instalação silenciosa por usuário, repetição do teste funcional no aplicativo instalado e desinstalação. O artefato gerado tem aproximadamente 279 MB. A publicação de uma versão usa novamente esses mesmos gates antes de liberar o download.


## Correções e usabilidade — 0.1.2

Os relatos do usuário esclareceram que os projetos eram criados, mas o fluxo e os retornos da interface não eram claros. A atualização acrescenta confirmação de conexão, progresso de operações, mensagem com o caminho salvo, erro copiável, seleção inicial e controles adaptáveis à tela.

A revisão também corrigiu pontos frágeis: finalização de MP4 em sistemas de arquivos sem hard links, substituição de MP4 apenas após confirmação, repetição de projetos sem colisões, busca da instalação pelo registro/seleção do executável desktop, preferência persistente e restauração da busca normal de DLLs para processos externos do executável PyInstaller. Busca antecipada de vídeo com origem zero foi verificada sem perder os limites; origens não zero usam o caminho conservador.

**35 testes passaram em Linux**, incluindo ações reais dos botões de MP4/conexão/projetos, pastas com caracteres não ASCII, simulação de ausência de hard links, preservação do original e projetos conjuntos/individuais/repetidos.

O workflow Windows passou nos testes de código e no teste do executável empacotado, usando **FilmCraft 0.18.0 Windows x64 oficial**, com SHA-256 verificado. Os testes criam projetos agrupados e individuais na mesma pasta, reabrem os nativos, renderizam um MP4 e iniciam o desktop numa sessão isolada; o canal oficial confirma que o projeto correto e suas três sequências foram abertos. Nenhum projeto existente do usuário é alterado. A publicação da release continua condicionada também à instalação e ao teste funcional do aplicativo instalado.

O botão “Copiar para ChatGPT” foi testado preservando tempos e omitindo o caminho privado do vídeo. Ele prepara uma revisão manual; nenhuma API paga foi integrada e nenhuma pesquisa de tendências é executada automaticamente pelo aplicativo. A classificação local continua heurística.

O helper que baixa o editor para os testes foi protegido por `main()` para não executar downloads nem escrever arquivos durante a coleta do pytest. A importação sem efeitos colaterais foi verificada separadamente. A versão de entrega com essa correção de build é 0.1.3.


## Transcrição TXT — 0.1.4

39 testes passaram em Linux. Os novos testes verificam o botão da interface e o conteúdo do TXT: horários originais, limites ajustados manualmente, exclusão de palavras externas, ausência de arquivo vazio quando não há fala e aviso para palavras/segmentos nas bordas. O teste do pacote Windows foi ampliado para usar transcrição real com timestamps por palavra e exportar o TXT dessa amostra; a release 0.1.4 só é publicada se esse teste e os demais gates passarem.

## Interface azul e Gemini opcional — 0.2.0

O azul foi fornecido pelo usuário. O YouTube não pôde ser inspecionado pela política de rede desta máquina; não foi copiado nem inventado um logotipo oficial. Nome, cor e PNG local podem ser configurados. A captura `interface-azul.png` mostra a aplicação real em desenvolvimento (Tk 8.6/Linux), usando vídeo e dados sintéticos, não uma imagem gerada nem uma captura do computador do usuário.

O cliente opcional Gemini usa REST `v1beta/models` e `generateContent`, conforme os conversores/documentação oficiais do repositório `googleapis/python-genai`. A chave vai em `x-goog-api-key`, não na URL; redirecionamentos HTTP são recusados para não encaminhá-la a outro destino. O JSON contém só dados dos cortes escolhidos. Erros do provedor são convertidos em mensagens sem corpo bruto de autenticação. A resposta é validada por ID, nota finita e tamanho; nenhuma resposta muda os tempos ou scores locais. Pesquisa confirmada depende de referências retornadas em `groundingMetadata`.

Nenhuma chave fornecida na conversa foi inserida em arquivos, comandos, logs, GitHub ou testes. As provas de API usam credenciais fictícias e transporte controlado. Não houve validação online com uma credencial real. A política de rede corrente bloqueou YouTube e `generativelanguage.googleapis.com`; domínios adicionais foram propostos no rascunho de configuração, sem publicação automática do ambiente.

O armazenamento persistente é opcional e usa DPAPI do usuário no Windows. Os testes Windows verificam cifrar, ler e remover uma credencial fictícia, inclusive no executável empacotado. O aplicativo também permite uso só em memória; no Linux a persistência é recusada explicitamente.

**63 testes passaram em Linux** (23,72 s), com FilmCraft real e interface em Xvfb. Os 26 testes finais direcionados a GUI/Gemini também passaram após os últimos ajustes. A execução Windows [43131357231](https://github.com/PedroHenrique1788/Radar/actions/runs/43131357231), no commit `c698f74`, passou na suíte de código, no executável empacotado offline e na geração/instalação/teste/desinstalação do instalador. Isso inclui a prova nativa DPAPI com credencial fictícia, sem validar uma conta Google real.

## Radar + Gemini automático — 0.3.0

A interface agora inicia pela configuração da chave/modelo, exige validação nesta sessão e pede autorização antes de ativar a revisão automática. Depois da análise local, envia até o dobro da quantidade desejada (máximo 20 candidatos) para comparação das falas. A seleção final segue a nota editorial Gemini, preservando IDs, horários, títulos e notas dos objetos locais. A tabela pode mostrar o título sugerido pela IA; os dados originais continuam disponíveis no resumo/relatório local.

**84 testes passaram em Linux, em 27,29 s**, com Python 3.12/Tk 9, Xvfb `:112`, FFmpeg e FilmCraft CLI oficial real. Foram verificados: bloqueio inicial até configuração; consentimento antes da automação; mudança efetiva da seleção pela avaliação das falas; envio de candidatos adicionais; preservação dos tempos; erro 429 e `Retry-After` numérico/data; limites do prazo; ausência de tentativas/trocas de modelo automáticas; espera e retomada sem repetir a análise local; modo somente Radar para esta sessão; erros de autorização e indisponibilidade; ausência de transcrição/candidatos sem chamada à API; cancelamento e fechamento antes do envio; troca de chave/modelo/pesquisa exigindo nova configuração. Os 46 testes direcionados a GUI/Gemini também passaram antes da inclusão do teste adicional de fechamento.

Comando da suíte completa:

```bash
DISPLAY=:112 FILMCRAFT_CLI=/workspace/tools/filmcraft/bin/filmcraft-cli \
  .venv/bin/python -m pytest -q --basetemp=/tmp/radar-hybrid-full-verified
```

As capturas atuais `interface-azul.png`, `gemini-configuracao.png` e `gemini-limite-simulado.png` foram feitas na aplicação real com Python do sistema/Tk 8.6 Linux. A revisão e o erro de cota nas capturas são explicitamente simulados. A prévia usa um vídeo sintético; a interface foi exercitada com o cliente REST real e transporte controlado, sem rede nem credencial válida.

Essa suíte local não comprova execução no Windows, qualidade editorial em gameplay real ou acesso autenticado ao Google. A validação Windows 0.2.0 acima é histórica; a entrega 0.3.0 depende novamente dos testes nativos e do instalador no workflow. O teste do pacote agora também verifica configuração obrigatória e seleção automática via Gemini simulado, em um perfil temporário isolado que preserva as preferências reais. Listar modelos não consulta saldo/cota restante nem assegura uma chamada gratuita; essa limitação aparece antes da ativação. Nenhuma chave pessoal foi adicionada ao código, às capturas ou aos testes.

### Validação nativa para a entrega 0.3.0

A execução Windows [43439195977](https://github.com/PedroHenrique1788/Radar/actions/runs/43439195977), no commit `15fc917`, passou na suíte de código, na geração do executável e no teste funcional do pacote offline. Além de mídia, transcrição e FilmCraft real, o executável verificou configuração inicial obrigatória, seleção automática de um candidato preferido pelo Gemini simulado, preservação de horários/scores locais e armazenamento DPAPI nativo com credencial fictícia. A automação também gerou o instalador, instalou silenciosamente por usuário, repetiu o teste no aplicativo instalado e confirmou a desinstalação. A release `v0.3.0` executa esses mesmos gates antes de publicar o arquivo final. Estes testes continuam sem validar uma chave/conta Google real ou a cota gratuita disponível para ela.
