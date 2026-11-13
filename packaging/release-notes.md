# Radar de Cortes 0.6.0 — Fase 3 / Windows x64

Baixe **RadarCortes-Setup-0.6.0-Windows-x64.exe**, execute o assistente e abra **Radar de Cortes** pelo Menu Iniciar. Inclui Python, FFmpeg/FFprobe/FFplay e tiny CPU/int8; não exige instalar Python ou baixar tiny na primeira abertura.

O Cefas Radar de Cortes ganha um estúdio de revisão no mesmo aplicativo azul:

- Timeline com cursor, zoom, deslocamento, IN/OUT e marcação por Shift + arrastar.
- Ondas reais do áudio original, lidas em lotes e armazenadas por janela; prévia pequena na timeline e quadro maior em aba própria.
- Cortes manuais antes ou depois da análise, favoritos, títulos/observações e estados Pendente/Aprovado/Descartado.
- Projetos .radar.json com gravação atômica, reabertura sem nova análise e localização de um original movido. Projetos referenciam os arquivos; não incluem cópias dos vídeos ou credenciais.
- MP4 original, horizontal 16:9 ou vertical 9:16, com recorte fixo por corte ou fundo desfocado. Resoluções 720/1080 e presets leve/equilibrado/qualidade.
- Legendas gravadas no vídeo e SRT com os horários das palavras efetivamente contidas no corte.
- Fila com integridade SHA-256 e configurações separadas por formato/qualidade/legenda, preservando saídas anteriores.

Whisper e Gemini continuam opcionais. O motor local usa CPU, sem API obrigatória, GPU ou Ollama. Os recursos de checkpoint, pausa/cancelamento/retomada, transcrição, MP4/TXT/SRT/JSON/CSV e FilmCraft permanecem disponíveis.

O MP4 preserva todas as faixas originais. O microfone externo continua sendo apenas uma fonte de análise/transcrição: adicione-o no editor se ele não estiver audível no vídeo. FilmCraft/OTIO continuam usando o original, sem aplicar automaticamente o novo formato ou legendas gravadas. Reproduzir renderiza uma prévia temporária no FFplay, em janela própria.

Cortes manuais não recebem nota automática. As notas locais e opiniões Gemini exigem revisão humana e não indicam probabilidade de viralização. Não há rastreamento automático de rosto ou ação. O desempenho não foi medido no Lenovo do usuário.

A suíte local completa passou em 150 testes e os 18 testes de interface passaram após os ajustes visuais. Esta release só é criada após a suíte nativa Windows, o teste offline do EXE, a instalação, o teste do aplicativo instalado e a desinstalação. A verificação inclui renderização vertical, legendas, projetos e fala real em português. Os testes Gemini usam respostas controladas; não há chave pessoal ou consulta de cota real.

A distribuição Windows usa o mesmo AppId e pasta por usuário, mantendo caches/resultados/projetos separados do aplicativo instalado. Inclui Python, FFmpeg e tiny. O instalador ainda não possui certificado comercial de assinatura de código; confira a origem e o SHA-256 publicado.

Guia: [Fase 3](https://github.com/PedroHenrique1788/Radar/blob/main/docs/FASE3.md).
