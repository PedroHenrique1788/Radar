**Cefas Radar de Cortes 2.0 — Fase 2 / versão 0.5.0**, para **Windows 10/11 de 64 bits**.

Baixe **RadarCortes-Setup-0.5.0-Windows-x64.exe**, execute o assistente e abra **Radar de Cortes** pelo Menu Iniciar. Inclui Python, FFmpeg/FFprobe/FFplay e o modelo tiny CPU/int8; não exige chave, Ollama ou GPU. Base/small e FilmCraft são opcionais e separados.

**Novidades da Fase 2**

- Microfone externo para análise/transcrição, com ajuste manual positivo ou negativo em segundos e silêncio fora da cobertura. Faixas do OBS continuam disponíveis; uma única faixa nomeada como microfone é preferida.
- Expressões personalizadas do canal, busca sem distinção de acentos/maiúsculas e sete pesos editáveis. Os sinais disponíveis têm os pesos normalizados.
- Indicadores de variação de intensidade, pausas antes de expressões e mudança de palavras por segundo. O mix recebe confiança menor; sons do jogo não são atribuídos automaticamente ao criador.
- Preparação/desfecho lexicais, limites próximos a pausas/frases/amostras de cena, proteção de palavras e verificação após alinhamento aos quadros reais.
- Transcrições limitadas à cobertura física do microfone e recalculadas no intervalo final. Relatórios registram a fonte do áudio e seu ajuste.
- Checkpoints independentes: trocar áudio/ajuste preserva imagem compatível; mudar expressões/pesos só reclassifica. Alteração do arquivo externo durante o trabalho interrompe com diagnóstico.

Whisper começa em **off**. Escolha **tiny** ou **base** para ativar palavras, ritmo e contexto lexical. O áudio externo é usado somente na análise: MP4, prévia e projetos preservam as faixas originais do vídeo. Adicione o microfone no editor se ele não estiver no original. Sincronização é manual e não corrige deriva entre relógios.

**Base preservada:** interface azul CefasGamer, perfil econômico CPU, limites configuráveis, métricas por etapa, pausa/cancelamento/retomada após reabrir, MP4 individual ou fila recuperável, JSON/CSV, transcrição TXT, SRT e projetos FilmCraft conjuntos/individuais. Vídeos originais e arquivos já existentes são preservados. Caches, logs e resultados ficam em `%LOCALAPPDATA%/RadarCortes`; desinstalar conserva esses dados.

**Gemini continua opcional.** Após validar sua chave/modelo e ativar o modo, revisa automaticamente os textos candidatos. O vídeo não é enviado. Sua nota editorial fica separada do score local. Em erro/cota, escolha Radar local ou aguarde e tente depois; não há troca de modelo nem repetição automática. Validar a chave não consulta saldo nem garante gratuidade. Projetos Google com faturamento podem gerar cobrança; pesquisa opcional pode ter limites/custos próprios. Nenhuma chave pessoal é incluída; testes usam transporte controlado. ChatGPT Plus não inclui créditos de API.

A nota local é heurística. Não há reconhecimento confirmado de emoções, identidade vocal, acontecimentos do jogo ou chance de viralização. A precisão depende da transcrição; revise os trechos e legendas. Não houve benchmark no Lenovo i7-8565U/MX110. Timeline interativa, exportação vertical, presets e demais itens do estúdio permanecem na Fase 3.

O instalador ainda não possui certificado comercial de assinatura de código; o Windows pode mostrar editor desconhecido. Confira a origem e o SHA-256 publicado. A release só é criada após testes nativos do código, EXE, instalação, aplicativo instalado e desinstalação, incluindo fala real em português e áudio externo sincronizado.

Guia e comandos: [Fase 2](https://github.com/PedroHenrique1788/Radar/blob/main/docs/FASE2.md).
