# Radar de Cortes 0.7.0 — Estúdio de Legendas / Windows x64

Baixe **RadarCortes-Setup-0.7.0-Windows-x64.exe**, execute o assistente e abra **Radar de Cortes** pelo Menu Iniciar. Inclui Python, FFmpeg/FFprobe/FFplay com libass e o Whisper tiny CPU/int8. Instala sobre a versão anterior, mantendo os dados do usuário separados do aplicativo.

Selecione um Short e abra **Estúdio de Legendas**, também disponível na aba Legendas do editor:

- Geração automática reutilizando a transcrição Whisper existente e o cache. Quando necessário, transcreve somente o áudio ainda não processado do Short em CPU, sem API paga.
- Correção de texto e tempos do bloco, sincronização manual por palavra, inclusão/remoção de blocos e ajuste automático dos horários relativos ao Short.
- Clássico, Palavra Destacada, Pop/Zoom e Karaokê; fontes, cores, tamanho, contorno, sombra, posição e negrito configuráveis.
- Estilo global ou individual por bloco, ativação/desativação e presets personalizados salvos neste computador.
- Prévia de um quadro sincronizado com o cursor e reprodução de até seis segundos com animação e áudio no FFplay, sem renderizar o vídeo inteiro a cada edição.
- Exportação SRT, ASS com estilos/animações e MP4 final com legendas. Áudio compatível copiado; outros codecs usam ALAC/PCM preservando a precisão, inclusive PCM de 32 bits e ponto flutuante. Essa opção pode aumentar os arquivos; desativá-la usa AAC.
- Projetos `.radar.json` versão 2 preservam todos os textos, tempos e estilos para novas edições. O leitor continua aceitando projetos da versão 0.6.0.

Sem tempos por palavra utilizáveis, Destaque/Karaokê exibem a aparência clássica até a sincronização manual. Alterar a quantidade de palavras remove a associação antiga; o editor não inventa novos tempos. SRT guarda texto/tempos; ASS guarda também os estilos. Fontes ausentes podem ser substituídas pelo sistema.

O Radar e o editor da Fase 3 continuam disponíveis, incluindo timeline, ondas, cortes manuais, favoritos, fila recuperável, formatos de vídeo e FilmCraft. Whisper e Gemini permanecem opcionais no fluxo de análise. Legendas não dependem de Gemini, chave ou serviço pago. Microfone externo usado na análise não é adicionado ao MP4; a exportação preserva as faixas do vídeo original.

Os testes verificam timestamps, cache, arquivos e pixels reais dos quatro efeitos, prévia sincronizada, pacotes AAC, áudio atrasado e precisão PCM, projetos e o fluxo da interface. Também foi exercitado o Whisper tiny real offline com a amostra de português do projeto. A release é criada somente após a suíte nativa Windows, o EXE offline, a instalação, os testes do aplicativo instalado e a desinstalação passarem. As validações Gemini usam dados controlados, sem consumir uma chave real.

Guia: [Estúdio de Legendas](https://github.com/PedroHenrique1788/Radar/blob/main/docs/ESTUDIO_LEGENDAS.md). O manifesto e o SHA-256 acompanham o instalador.
