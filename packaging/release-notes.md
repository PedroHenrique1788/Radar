**Radar de Cortes 0.3.0** — instalador para **Windows 10/11 de 64 bits**.

Baixe o arquivo **RadarCortes-Setup-…-Windows-x64.exe**, abra-o e siga o assistente. Depois abra **Radar de Cortes** pelo Menu Iniciar. O atalho na Área de Trabalho é opcional.

Inclui Python, FFmpeg/FFprobe/FFplay e o modelo de fala tiny em CPU. Não é preciso instalar Python nem baixar esse modelo na primeira abertura. Modelos maiores e FilmCraft são opcionais e separados.

Os seus vídeos não são enviados a serviços de IA. Caches, logs e resultados ficam em `%LOCALAPPDATA%\RadarCortes`; desinstalar preserva esses dados. Projetos FilmCraft referenciam os vídeos e WAVs auxiliares: mantenha-os disponíveis.

O instalador ainda não tem certificado de assinatura de código; o Windows pode mostrar “editor desconhecido”. Confira a origem deste repositório e o SHA-256 publicado. Não desative o antivírus.

A pontuação é heurística, não uma previsão de viralização. Revise cortes e legendas antes de publicar.


**Interface azul CefasGamer.** Navegação por etapas: selecionar vídeo, analisar, revisar cortes e exportar. Quadro de prévia, horários editáveis, falas e exportações organizadas. Nome, cor e logotipo PNG podem ser personalizados.

**Exportações preservadas:** MP4, transcrição TXT com horários originais, legendas SRT e projetos FilmCraft conjuntos ou individuais. A análise precisa ter transcrição de fala (tiny/base/small) para exportar TXT/SRT. O aplicativo confirma o destino dos arquivos e permite repetir projetos sem colidir com os anteriores.

**Radar + Gemini no mesmo fluxo.**

Na tela inicial, informe sua chave Gemini, clique em **Validar e listar modelos**, escolha o modelo e clique em **Usar Radar + Gemini**. Depois dessa configuração, a análise prepara até 20 candidatos e o Gemini compara as falas para escolher e ordenar a quantidade solicitada. Os horários e scores locais são preservados; a avaliação editorial aparece separadamente. A chave pode ficar só na sessão ou ser salva com Windows DPAPI. O vídeo não é enviado.

Se houver limite de uso ou falha, escolha **Continuar só com o Radar** ou **Aguardar e tentar depois**. Os candidatos locais são preservados. **Retomar fluxo** repete apenas a etapa Gemini, sem analisar o vídeo novamente. O app respeita a espera informada pelo Google e não troca de modelo nem repete chamadas automaticamente após erro.

**Validar a chave não informa saldo nem garante gratuidade.** Confira cota e faturamento no AI Studio. Um projeto com faturamento ativo pode gerar cobranças; o aplicativo não consegue impedi-las. Pesquisa Google é opcional, desligada por padrão, e pode ter cota/custo próprio.

Os testes de integração de API usam respostas controladas e não validam sua chave real. Use **Validar e listar modelos** após configurar uma chave nova. A gratuidade depende do seu projeto Google.

**Copiar para ChatGPT** continua disponível para revisão manual. ChatGPT Plus não inclui créditos de API.
