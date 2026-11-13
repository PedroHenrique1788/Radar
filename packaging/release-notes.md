**Cefas Radar de Cortes 2.0 — Fase 1 / versão 0.4.1**, para **Windows 10/11 de 64 bits**.

Baixe o arquivo **RadarCortes-Setup-…-Windows-x64.exe**, abra-o e siga o assistente. Depois abra **Radar de Cortes** pelo Menu Iniciar. O atalho na Área de Trabalho é opcional.

Inclui Python, FFmpeg/FFprobe/FFplay e o modelo de fala tiny em CPU. Não é preciso instalar Python nem baixar esse modelo na primeira abertura. Modelos maiores e FilmCraft são opcionais e separados.

Os seus vídeos não são enviados a serviços de IA. Caches, logs e resultados ficam em `%LOCALAPPDATA%\RadarCortes`; desinstalar preserva esses dados. Projetos FilmCraft referenciam os vídeos e WAVs auxiliares: mantenha-os disponíveis.

O instalador ainda não tem certificado de assinatura de código; o Windows pode mostrar “editor desconhecido”. Confira a origem deste repositório e o SHA-256 publicado. Não desative o antivírus.

A pontuação é heurística, não uma previsão de viralização. Revise cortes e legendas antes de publicar.


**Interface azul CefasGamer.** Navegação por etapas: selecionar vídeo, analisar, revisar cortes e exportar. Quadro de prévia, horários editáveis, falas e exportações organizadas. Nome, cor e logotipo PNG podem ser personalizados.

**Motor local confiável, sem API obrigatória.** O aplicativo abre diretamente para selecionar a gameplay. O perfil **Modo Econômico — Lenovo MX110** usa CPU, etapas sequenciais, limites de threads/memória e imagem em baixa resolução. Whisper começa desligado; tiny/base são opcionais e locais.

**Checkpoints por etapa e lote.** Pausar/retomar, cancelar e reabrir análises recentes preservam os lotes concluídos. Arquivo e configurações são revalidados antes de reutilizar o cache. Erros identificam a etapa; é possível continuar sem áudio/imagem ou sem transcrição opcional. O progresso é da etapa atual, com unidades, tempo, ETA quando houver dados e métricas aproximadas de CPU/RAM.

**Pesos configuráveis e fila MP4 recuperável.** Sinais ausentes têm os pesos redistribuídos; os motivos mostram a composição da nota. A fila é sequencial, verifica SHA-256 de clipes prontos, retoma pendentes e preserva arquivos alterados pelo usuário. Relatórios incluem o identificador do original. Vertical 9:16, timeline/waveform e novos indicadores vocais ficam nas próximas fases.

A versão 0.4.1 estabiliza a ordem cronológica da fila: reordenar os mesmos cortes na tabela antes de retomar não repete os clipes íntegros já concluídos.

**Exportações preservadas:** MP4, transcrição TXT com horários originais, legendas SRT e projetos FilmCraft conjuntos ou individuais. A análise precisa ter transcrição de fala (tiny/base/small) para exportar TXT/SRT. O aplicativo confirma o destino dos arquivos e permite repetir projetos sem colidir com os anteriores.

**Radar + Gemini no mesmo fluxo.**

Gemini é opcional em **Preferências**: informe sua chave, valide os modelos e ative **Usar Radar + Gemini** se quiser a comparação automática das falas dos candidatos. Tiny é selecionado se a transcrição estiver desligada. Horários e scores locais são preservados; a avaliação editorial aparece separadamente. A chave pode ficar só na sessão ou ser salva com Windows DPAPI. O vídeo não é enviado.

Se houver limite de uso ou falha, escolha **Continuar só com o Radar** ou **Aguardar e tentar depois**. Os candidatos locais são preservados. **Retomar fluxo** repete apenas a etapa Gemini, sem analisar o vídeo novamente. O app respeita a espera informada pelo Google e não troca de modelo nem repete chamadas automaticamente após erro.

**Validar a chave não informa saldo nem garante gratuidade.** Confira cota e faturamento no AI Studio. Um projeto com faturamento ativo pode gerar cobranças; o aplicativo não consegue impedi-las. Pesquisa Google é opcional, desligada por padrão, e pode ter cota/custo próprio.

Os testes de integração de API usam respostas controladas e não validam sua chave real. Use **Validar e listar modelos** após configurar uma chave nova. A gratuidade depende do seu projeto Google.

**Copiar para ChatGPT** continua disponível para revisão manual. ChatGPT Plus não inclui créditos de API.
