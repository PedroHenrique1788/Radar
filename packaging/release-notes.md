**Radar de Cortes 0.2.0** — instalador para **Windows 10/11 de 64 bits**.

Baixe o arquivo **RadarCortes-Setup-…-Windows-x64.exe**, abra-o e siga o assistente. Depois abra **Radar de Cortes** pelo Menu Iniciar. O atalho na Área de Trabalho é opcional.

Inclui Python, FFmpeg/FFprobe/FFplay e o modelo de fala tiny em CPU. As funções básicas não exigem instalação de Python, assinatura, chave de API ou download de modelo na primeira abertura. Modelos maiores e FilmCraft são opcionais e separados.

Os seus vídeos não são enviados a serviços de IA. Caches, logs e resultados ficam em `%LOCALAPPDATA%\RadarCortes`; desinstalar preserva esses dados. Projetos FilmCraft referenciam os vídeos e WAVs auxiliares: mantenha-os disponíveis.

O instalador ainda não tem certificado de assinatura de código; o Windows pode mostrar “editor desconhecido”. Confira a origem deste repositório e o SHA-256 publicado. Não desative o antivírus.

A pontuação é heurística, não uma previsão de viralização. Revise cortes e legendas antes de publicar.


**Interface azul CefasGamer.** Navegação por etapas: selecionar vídeo, analisar, revisar cortes e exportar. Quadro de prévia, horários editáveis, falas e exportações organizadas. Nome, cor e logotipo PNG podem ser personalizados.

**Exportações preservadas:** MP4, transcrição TXT com horários originais, legendas SRT e projetos FilmCraft conjuntos ou individuais. A análise precisa ter transcrição de fala (tiny/base/small) para exportar TXT/SRT. O aplicativo confirma o destino dos arquivos e permite repetir projetos sem colidir com os anteriores.

**Revisão opcional com Gemini.**

Configure sua própria chave em **Preferências → Gemini**, valide os modelos e solicite a revisão dos cortes escolhidos. A chave pode ficar somente na sessão ou ser salva com Windows DPAPI. O vídeo não é enviado; a solicitação usa texto e horários selecionados. Nota editorial e fontes ficam separadas dos scores locais. Pesquisa Google é opcional, desligada por padrão, e pode ter cota/custo próprio. O aplicativo não habilita faturamento ou faz trocas automáticas de modelo.

Os testes de integração de API usam respostas controladas e não validam sua chave real. Use **Validar e listar modelos** após configurar uma chave nova. A gratuidade depende do seu projeto Google.

**Copiar para ChatGPT** continua disponível para revisão manual. ChatGPT Plus não inclui créditos de API.
