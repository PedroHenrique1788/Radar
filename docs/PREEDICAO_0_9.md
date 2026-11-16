# Pré-edição 0.9 — manual, arquitetura e limitações

Entrega incremental sobre 0.8.0. Não é release estável validada; não há migração de interface ou implementação antecipada da 1.0.

## Começar

1. Abra pelo código-fonte com `iniciar.bat` ou `python -m radar`, importe MKV/MP4 e clique **Pré-edição** no menu. Não precisa analisar Shorts antes. Para usar fala Whisper, execute primeiro a análise existente com tiny e a faixa correta; o pré-editor reutiliza a transcrição em memória/reaberta e nunca liga uma API.
2. Na aba **Detector e faixas OBS**, confira os papéis Microfone/Jogo/Mix/Não identificado. Etiquetas são sugestões de identificação, não reconhecimento do conteúdo. Cada faixa original é analisada separadamente, mesmo se não selecionada para exportação. Se alterar papéis, execute a análise novamente para atualizar as justificativas.
3. Escolha modo, pausa mínima, sensibilidade, margens, proteção narrativa e intensidade. Clique **Analisar pré-edição**. A tarefa usa o worker existente, progresso real por segundos/faixa, perfil econômico, pausa, cancelamento e checkpoints. Repetir a análise retoma lotes compatíveis.
4. Na aba **Revisar sequência**, selecione um intervalo e leia o motivo. **Aceitar remoção** reduz a proposta; **Rejeitar / manter** preserva o intervalo; **Restaurar intervalo** volta a pendente, também preservado. Enter aceita e Delete rejeita a sugestão selecionada. Trechos classificados Manter não podem ser aceitos para remoção. Somente marcar nunca permite remoção.
5. Ajuste IN/OUT em horários do original, ou arraste os marcadores na visão original e clique **Aplicar IN/OUT**. O FFprobe alinha aos quadros reais, inclusive VFR. Sobreposição com outra sugestão é recusada sem alterar a edição anterior. **Desfazer/Refazer** ou Ctrl+Z/Ctrl+Y revertem decisões e limites; nova edição após desfazer descarta o ramo de refazer.
6. Alterne **Visão original** para inspecionar a timeline compactada. A tabela e IN/OUT continuam sempre em tempos do original. Azul = mantido; âmbar = oportunidade de remoção; roxo = revisar; vermelho = remoção aprovada; verde = sugestão rejeitada/preservada. Linhas ★/S são marcadores importantes/Shorts dos clipes existentes. O resumo mostra original/proposta, intervalos, aprovações, economia e conteúdo preservado.
7. **Ouvir/ver original** abre diretamente o arquivo original no FFplay no intervalo selecionado, sem MP4 temporário. Esta versão não reproduz continuamente a proposta com cursor sincronizado: o player integrado pertence ao planejamento 1.0.
8. **Salvar projeto** usa o salvamento do estúdio e inclui pré-edição, faixas, medições, marcadores e histórico no `.radar.json`. Abrir projeto restaura tudo sem nova análise. Salvar como uma nova versão preserva a edição anterior. A reanálise avisa antes de substituir decisões. Salve antes de trocar de vídeo ou fechar: não há autosave de decisões ainda não salvas.

## Presets e detector

| Modo | Pausa mínima padrão | Margem anterior/posterior | Limiar de imagem estática |
| --- | --- | --- | --- |
| Conservador | 12 s | 3/3 s | diferença < 0,003 |
| Equilibrado | 8 s | 2/2 s | diferença < 0,005 |
| Dinâmico | 5 s | 1/1 s | diferença < 0,008 |
| Somente marcar | 12 s | 3/3 s | diferença < 0,005; não aceita remoções |

A duração mínima é piso rígido; intensidade 0–1 aplica fator 1,5–1 ao piso (padrão 1,25). Sensibilidade 0–1 ajusta limiar RMS relativo por faixa: percentil 90 menos 30 dB mais 12×sensibilidade, limitado entre −72 e −45 dBFS. Não é um volume absoluto único e áudio audível constante não é normalizado artificialmente para silêncio. Margem “antes do contexto seguinte” diminui o OUT, e “após contexto anterior” aumenta o IN da possível remoção.

Oportunidades vêm de pausas do microfone declarado ou, sem microfone, das faixas disponíveis. O estado muda conforme o áudio/imagem dentro da pausa, sem agrupar indiscriminadamente uma cutscene e uma tela silenciosa. Fala transcrita, seu contexto e marcadores importantes protegem regiões. Jogo/mix audível classifica Manter mesmo com microfone silencioso. Somente pausa longa em **todas** as faixas e imagem amostrada estática, com jogo identificado, sugere remoção. Evidência ausente, vídeo sem áudio, papel desconhecido ou imagem ativa exige revisão. Desativar proteção narrativa permite oportunidades sem jogo identificado quando todos os outros sinais estão quietos/estáticos; continua exigindo decisão humana.

RMS e envelopes não são um VAD semântico. VAD já faz parte da transcrição Whisper opcional; não há novo modelo obrigatório. Ausência de transcrição não prova ausência de fala. Cutscenes silenciosas com quadro estático, menus e exploração ainda podem exigir julgamento editorial. A força heurística não é probabilidade calibrada nem detecção validada de acontecimentos do jogo.

## FilmCraft e faixas OBS

Conecte o FilmCraft pela tela **Exportar**, ou configure `FILMCRAFT_CLI`. **Enviar pré-edição para FilmCraft** cria pasta exclusiva por operação e uma única timeline com todos os intervalos mantidos, na ordem original, como cortes modificáveis. A mídia de vídeo referencia o original; cada faixa selecionada usa WAV PCM48 estéreo alinhado ao zero do vídeo, com seus offsets originais. Não há MP4 intermediário.

O mix nomeado é inicialmente desmarcado quando há microfone e jogo nomeados. Confira manualmente: etiquetas desconhecidas podem ocultar um mix. Selecionar mix e individuais solicita escolha explícita por risco concreto de duplicação. Nenhuma faixa é apagada da gravação ou do projeto Radar; seleção só controla a entrega ao editor. O ganho original é mantido, sem filtros automáticos. Faixas com mais de dois canais são reduzidas a estéreo, como no integrador existente: não é preservação exata de surround/32-bit float.

A CLI oficial é consultada com `--help` e `describe file.import/sequence.settings`. Importa o OTIO, salva projeto novo, reabre e verifica mídia online, duração, quantidade de cortes, faixas e IN/duração/posição de cada item via inspeção oficial. O formato nativo não é fabricado. Sem CLI, esquema incompatível ou falha de criação nativa, a entrega é OTIO e `Verificacao.json` registra o motivo. **Abrir resultado** inicia o editor quando disponível; no fallback importe `Preedicao.otio` pelo menu do FilmCraft.

Conserve `Preedicao.otio`, WAVs, original e `.fcproj` juntos em caminhos acessíveis. Os WAVs consomem aproximadamente 691 MB/h/faixa; há verificação de espaço antes de gerar. Nenhuma limpeza automática apaga sidecars. Origem temporal não nula e atraso de áudio são testados com tons; VFR continua representado pela taxa nominal do editor. Revise as bordas no FilmCraft; HDR, rotação, pixel aspect não quadrado e surround não estão validados. `Inspecao_cli.json` e `Verificacao.json` permitem conferir a estrutura efetivamente criada. Uma falha deixa `Estado.json` incompleto sem apagar entregas anteriores.

## Áudio opcional

A aba **Preparar áudio** mostra RMS e picos da análise mono 16 kHz, segundos com pico perto de 0 dBFS e sugestão de ganho para pico de −6 dBFS (limitada a −24/+12 dB). Não mede clipping de todos os canais, não prova distorção, não é LUFS e não substitui audição.

Ganho, compressor (limiar/razão), gate leve (limiar) e normalização loudnorm (alvo LUFS) são configuráveis. Todos os filtros adicionais começam desligados. **Criar cópia tratada para comparar** aplica somente os filtros escolhidos numa nova cópia WAV PCM48 estéreo e grava `.treatment.json`. Não substitui o original nem os WAVs padrão do FilmCraft. Loudnorm usa uma passagem dinâmica; a interface não declara loudness final medido/garantido. Compare pelo FFplay e importe manualmente a cópia no editor somente se aprovada, silenciando a faixa equivalente para não duplicá-la. Gate pode ocultar sons baixos; não há redução de ruído neural automática.

## Persistência, cancelamento e migração

Projeto v3 tem campo opcional `preedit`: fonte, duração, metadados/papéis das faixas, seleção, parâmetros, sugestões, razões, confiança heurística, decisão, marcadores, medições e histórico limitado às últimas 500 operações. A sequência mantida é calculada como complemento das remoções aceitas; não há alteração de bytes da mídia. Teto: 10000 sugestões, 4000 marcadores, limite de projeto existente 32 MB. Falha de salvamento atômico mantém a última versão válida. Decisões não salvas não são recuperadas automaticamente.

Leitura de v1/v2 continua funcionando, sem inventar uma pré-edição para clipes antigos. O aplicativo antigo 0.8 não lê v3; preserve uma cópia do projeto antigo ao atualizar. Relocalização verifica tamanho/hash amostrado e reconecta a identidade da pré-edição. A identificação do original segue o mecanismo existente (não hash integral para arquivos gigantes).

Extração usa WAVs mono por lote de até 300 s e as mesmas assinaturas de cache do pipeline existente. Imagem e áudio independentes são reutilizados; alterar decisões/modo não exige nova decodificação de lotes válidos. Cancelar deixa somente lotes confirmados e permite repetir; o lote em execução pode ser refeito. Não há limpeza automática de dados referenciados. Sinais em memória crescem com a duração; não se promete duração ilimitada. A pré-edição não transcreve nem importa automaticamente microfone externo; o fluxo antigo continua disponível e suas falas podem proteger a proposta se já carregadas.

## Benchmark e validação

Execute, pelo venv (Windows: `.venv\Scripts\python.exe`):

```bash
python -m radar.preedit_benchmark gameplay.mkv --cache temporarios/benchmark-novo --output resultados/benchmark.json --threads 2 --batch-seconds 300
```

Exige cache inicialmente vazio e destino novo, não apaga dados. Faz duas execuções com mesma configuração/fonte: fria e quente. Registra tempo, RSS máximo amostrado de processo/subprocessos, CPU e bytes de I/O aproximados, crescimento do cache, máquina e FFmpeg. A amostragem de 50 ms pode perder processos curtos; não é benchmark de qualidade editorial nem comparação com versões antigas. Use sem outras tarefas concorrentes e compare amostras idênticas.

Veja [relatório](ENTREGA_0_9.md) e [protocolo de três gameplays](VALIDACAO_EDITORIAL_0_9.md). Windows x64, empacotamento e validação editorial continuam gates separados; não publicar release apenas porque testes Linux passaram.
