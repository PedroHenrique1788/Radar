Instalador para **Windows 10/11 de 64 bits**.

Baixe o arquivo **RadarCortes-Setup-…-Windows-x64.exe**, abra-o e siga o assistente. Depois abra **Radar de Cortes** pelo Menu Iniciar. O atalho na Área de Trabalho é opcional.

Inclui Python, FFmpeg/FFprobe/FFplay e o modelo de fala tiny em CPU. As funções básicas não exigem instalação de Python, assinatura, chave de API ou download de modelo na primeira abertura. Modelos maiores e FilmCraft são opcionais e separados.

Os seus vídeos não são enviados a serviços de IA. Caches, logs e resultados ficam em `%LOCALAPPDATA%\RadarCortes`; desinstalar preserva esses dados. Projetos FilmCraft referenciam os vídeos e WAVs auxiliares: mantenha-os disponíveis.

O instalador ainda não tem certificado de assinatura de código; o Windows pode mostrar “editor desconhecido”. Confira a origem deste repositório e o SHA-256 publicado. Não desative o antivírus.

A pontuação é heurística, não uma previsão de viralização. Revise cortes e legendas antes de publicar.


Correções desta versão: exportação MP4 em discos sem suporte a hard links, projetos repetidos sem colisões, detecção de instalações FilmCraft/portáteis com preferência salva, limpeza do ambiente de DLLs ao abrir ferramentas externas e erros copiáveis. Os botões confirmam onde os arquivos foram salvos. Inclui “Copiar para ChatGPT” para revisão manual com sua conta; Plus não inclui créditos de API e o aplicativo não faz chamadas pagas automaticamente.


**Novo: Exportar transcrição TXT.** Selecione um corte e salve as falas do intervalo com os horários do vídeo original. Os limites ajustados são respeitados. A exportação de legendas SRT permanece disponível. A análise precisa ter transcrição de fala (tiny/base/small).

**0.2.0 — Azul CefasGamer + revisão opcional com Gemini.** Interface por etapas, quadro de prévia, horários editáveis, falas e exportações organizadas. Nome/cor/logotipo PNG podem ser personalizados.

Configure sua própria chave em **Preferências → Gemini**, valide os modelos e solicite a revisão dos cortes escolhidos. A chave pode ficar somente na sessão ou ser salva com Windows DPAPI. O vídeo não é enviado; a solicitação usa texto e horários selecionados. Nota editorial e fontes ficam separadas dos scores locais. Pesquisa Google é opcional, desligada por padrão, e pode ter cota/custo próprio. O aplicativo não habilita faturamento ou faz trocas automáticas de modelo.

Os testes de integração de API usam respostas controladas e não validam sua chave real. Use **Validar e listar modelos** após configurar uma chave nova. A gratuidade depende do seu projeto Google.
