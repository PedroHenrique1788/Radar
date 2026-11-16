# Entrega incremental da pré-edição 0.9

Estado: **funcionalidade implementada com validações pendentes; não declarar 0.9 completamente concluída**. Base 0.8.0 (`e82664b`), branch `feature/radar-0.9-preeditor`. Não foi criada release nem alterada a principal.

## 1. Desenvolvimento efetivo

Pré-editor local CPU integrado ao aplicativo existente: detector conservador por faixas originais, revisão não destrutiva, histórico reversível, projeto v3, uma sequência editável OTIO/FilmCraft e preparação opcional de áudio em cópia separada. Reutilizados FFmpeg/FFprobe, sinais, cache/checkpoints, worker, timeline, salvamento atômico, CLI FilmCraft e navegação Tk azul. Sem nova dependência básica ou chamada externa de análise.

## 2. Arquivos

Criados: `radar/preedit.py`, `preedit_pipeline.py`, `preedit_ui.py`, `audio_prepare.py`, `preedit_benchmark.py`, `tests/test_preedit.py`; documentos `AUDITORIA_0_9.md`, `PREEDICAO_0_9.md`, `VALIDACAO_EDITORIAL_0_9.md`, `PLANEJAMENTO_1_0_1_1.md` e este relatório.

Modificados: `radar/projects.py`, `desktop_studio.py`, `__main__.py`, `timeline.py`, `ui.py`, `filmcraft.py`, README, teste do pacote, receita Inno Setup, notas de versão e workflow Windows. O registro `docs/benchmark-sintetico-0.9.json` conserva as medições brutas. O núcleo de highlights, transcrição, biblioteca, legendas e MP4 permaneceu disponível.

## 3. Concluído no código e verificado em Linux

- Importação MKV multifaixa e análise por faixa em lotes limitados; proteção de jogo audível durante silêncio do microfone.
- Modos Conservador/Equilibrado/Dinâmico/Somente marcar configuráveis; nenhuma remoção automática.
- Aceitar/rejeitar/restaurar, IN/OUT com quadros reais, undo/redo, duração original/proposta, timeline original/compactada e marcadores de clipes existentes.
- Persistência v3 com histórico; leitura v1/v2; gravação atômica com preservação do último projeto válido após falha simulada.
- Exportação de sequência única com cortes modificáveis, vídeo original e WAVs separados/sincronizados; CLI oficial real salva/reabre e inspeciona, OTIO como fallback.
- Análise RMS/picos e sugestão de ganho; cópia opcional com compressor/gate/loudnorm configuráveis, sem alterar original ou áudio padrão do editor.
- Benchmark frio/quente reproduzível; protocolo para três gameplays e planejamento 1.0/1.1.

## 4. Parcial ou pendente

- **Windows x64, EXE, instalador e aplicativo instalado desta mudança:** não executados localmente em Linux. Workflow ampliado para PR e smoke de pré-edição; resultado depende do runner Windows.
- **Três gameplays reais e hardware do usuário:** não fornecidos; precisão editorial, cortes úteis perdidos, dano de contexto e tempo de revisão ainda não medidos.
- **Preservação exata de todo formato de áudio:** o integrador existente usa PCM48 estéreo; surround é reduzido e formatos de maior precisão não preservam seus bits exatos. Separação/sincronismo testados em mídia sintética.
- **VFR/formatos avançados:** análise em PTS; editor nominal, sujeito a arredondamentos. HDR/rotação/PAR/surround sem validação editorial específica.
- **Tratamento de áudio:** RMS/peak mono de análise, não medição final de LUFS/true peak; loudnorm de uma passagem. Aplicação produz sidecar, não efeitos nativos reversíveis no FilmCraft. Compare ouvindo e importe manualmente se aprovado.
- **Recuperação:** lotes confirmados e última versão salva sobrevivem a interrupção; não há autosave das decisões ainda não salvas nem retomada parcial de WAV FilmCraft interrompido. Refazer exportação cria pasta nova.
- **Player integrado, proxies, aprendizado local e multimodal:** planejados, não implementados antecipadamente.

## 5. Testes reais

Antes da implementação: **185 passaram, 151,27 s**, Python 3.12/Linux, Tk com Xvfb, FFmpeg 7.1.5 e CLI FilmCraft oficial 0.18.0 com SHA-256 verificado.

Primeira regressão direcionada: **49 passaram, 56,26 s** (estúdio/legendas). Primeiros novos testes: **16 passaram, 13,20 s** após corrigir agrupamento excessivo de pausas. Suíte ampliada intermediária: **201 passaram, 168,19 s**.

**Suíte final: 207 passaram, 143,64 s**, incluindo mais casos reais de VFR/sem áudio, áudio desativado, proteção por marcador, relocalização e cancelamento de tratamento. Após os ajustes finais de interface e validação RF64, **24 testes direcionados passaram em 19,24 s** (23 de pré-edição e um fluxo completo do estúdio). Um arquivo RF64 real foi conferido por FFprobe, sem carregá-lo inteiro em RAM. O smoke novo do pacote também foi executado como função Python em Linux, com fonte multifaixa e criação/reabertura FilmCraft; isso não equivale a executá-lo dentro de EXE Windows. Não houve acesso a conta Gemini nem envio de mídia/transcrição. Testes de cliente externo existentes usam dados controlados.

## 6. Problemas e soluções

- Primeiro CI Windows: 207 testes passaram e um teste novo falhou ao ler JSON UTF-8 com encoding padrão cp1252. Corrigida a leitura explícita UTF-8 no teste, mantendo a validação nativa obrigatória. EXE/instalador foram corretamente bloqueados nessa execução (`43959690755`).
- Dependências/pytest não estavam instalados: criado venv com requirements-dev existente; Xvfb extraído localmente, sem instalar pacote no sistema.
- Código antigo representava Shorts, não uma sequência completa: mantido Cut para highlights e criado modelo separado de decisões, evitando mudança do retorno público do pipeline.
- Mix OBS somado a individuais: seleção explícita; mix nomeado inicialmente excluído quando há voz/jogo nomeados e aviso ao escolher combinação duplicável.
- Pausa longa no microfone escondia mudanças internas no jogo: classificação por bins audiovisuais antes do agrupamento, com teste de regressão em MKV real sintético.
- Validação de áudio pelo leitor WAV do Python não aceita RF64 de arquivos longos: substituída por FFprobe e testada com RF64 real.
- Layout inicial poderia ocultar botões na janela mínima: reservado espaço de ações e tabela elástica, conferido em Tk real.
- CLI indisponível/incompatível: OTIO verificável, sem inventar comandos ou arquivo nativo. Falha mantém saídas anteriores e diagnóstico.

## 7. Desempenho

Não há comparação de velocidade com 0.8 ou medição no i7-8565U/MX110. Cache frio/quente da mesma implementação: amostra sintética de **180 s, 320×180/25 fps, duas faixas PCM16 (microfone intermitente e tom de jogo)**, sem outra tarefa de teste em execução. Frio: **1,893 s**, RSS máximo amostrado **72,41 MiB**, CPU amostrada **2,00 s**, cache +**11.593.873 bytes**. Quente: **0,335 s**, RSS **66,40 MiB**, CPU **0,15 s**, cache +**0 bytes**. I/O amostrado: leitura física 0 em ambos (cache do sistema); escrita 20.594.688 / 12.288 bytes. Hardware do ambiente: 3 CPUs lógicas, aproximadamente 9,73 GiB RAM, Linux/FFmpeg 7.1.5. [Registro bruto](benchmark-sintetico-0.9.json). Isso não demonstra desempenho em gameplays reais longas.

## 8. Usar a pré-edição

Importe vídeo → **Pré-edição** → confira faixas/preset → **Analisar pré-edição** → selecione e revise motivos → aceite/rejeite/restaure, ajuste IN/OUT e use undo/redo → compare original/proposta → **Salvar projeto**. A proposta preserva tudo até aprovação explícita. Reabra pelo fluxo de projetos existente. Detalhes: [manual](PREEDICAO_0_9.md).

## 9. Abrir no FilmCraft

Conecte CLI oficial pela tela Exportar, confira faixas selecionadas e use **Enviar pré-edição para FilmCraft**. A operação cria pasta exclusiva, OTIO/WAVs e, com CLI compatível, `.fcproj` reaberto/conferido. Clique **Abrir resultado**. Sem CLI, importe OTIO no editor e leia `Verificacao.json`. Preserve todos os sidecars e o original; não há MP4 intermediário.

## 10. Próximas ações

Concluir os gates Windows/instalador e validar três gameplays reais antes de promover 0.9. Depois, medir protótipo de player Tk versus Qt no hardware alvo, implementar proxies com mapa temporal seguro, estatísticas de decisões e perfis explicáveis. Plano: [1.0/1.1](PLANEJAMENTO_1_0_1_1.md).
