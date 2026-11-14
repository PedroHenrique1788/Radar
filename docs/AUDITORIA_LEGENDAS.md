# Inspeção antes do Estúdio de Legendas

Base inspecionada: `272d363`, versão publicada 0.6.0, árvore limpa. Antes de editar, a suíte existente passou com **150 testes em 79,15 s**.

- `transcription.py` já usa Faster-Whisper local CPU/int8, `word_timestamps=True`, VAD, lotes e deslocamentos relativos ao original. Não será criado outro transcritor.
- `pipeline.py` já separa e verifica caches de áudio/transcrição, incluindo microfone externo. O estúdio reutilizará essas assinaturas; se faltarem dados, transcreverá somente o corte solicitado com os serviços existentes.
- `export.subtitle_entries` já divide blocos por palavras, pausas e comprimento. `transcript_entries` seleciona o intervalo original; SRT subtrai `cut.start`. Essa referência temporal será mantida.
- `render.write_ass` possui apenas um estilo fixo e é usado pelo MP4 com legendas. Não há editor de blocos/palavras, presets de estilo ou exportação ASS na interface. A renderização existente será estendida, mantendo a chamada antiga compatível.
- `projects.py` salva cortes/falas/configurações em JSON atômico. As edições de legendas serão uma faixa separada em cada `Cut`; o cache Whisper continuará intacto. O novo leitor abrirá projetos antigos.
- A interface Tkinter já oferece seleção de cortes, preview, trabalhos em thread, cancelamento e FFplay. A nova página reutilizará esses mecanismos e terá o nome **Estúdio de Legendas**.

Ordem de implementação: faixa editável e exportações sincronizadas; integração com cache e projetos; quatro efeitos ASS com personalização; editor visual e presets; testes reais com FFmpeg/libass e validação do pacote Windows. Alterar texto/estilo/posição renderizará um quadro ou uma prévia curta, sem refazer transcrição ou o vídeo inteiro.
