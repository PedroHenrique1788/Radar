# Planejamento técnico 1.0 / 1.1

**Bloqueio de escopo:** não iniciar implementação dessas versões antes de validar os gates da 0.9, incluindo Windows empacotado, reabertura FilmCraft e avaliação de três gameplays reais. Não há player novo, proxy, aprendizado ou classificador semântico entregue nesta branch.

## 1.0 — fluidez e preferências

1. **Player: protótipo isolado.** Medir no i7-8565U/20 GB/MX110: abrir/reproduzir/seek em original OBS e VFR, play/pause, velocidade, loop, monitoramento de faixas, cursor e troca original/proposta. Comparar Tk + decodificação PyAV existente (fila limitada e relógio de áudio) com um protótipo Qt/PySide6 (motor multimídia e seus limites MKV/multifaixa). Registrar RSS ocioso e durante reprodução, frames perdidos, latência de seek, CPU e tamanho empacotado, nas mesmas amostras. Não existem números medidos para justificar migração. Escolher Tk se atender; migração completa só com benefício demonstrado e manutenção/instalador avaliados.
2. **Proxy opcional.** Cache versionado por identidade/configuração/FPS/origem, arquivo de baixa resolução, mapa temporal e sidecar. Preservar origem como referência editorial e usar original na exportação. Testar VFR, timestamps não nulos, faixas OBS e alternância sem acumular deriva. Registrar arquivos referenciados antes de permitir limpeza; não usar glob destrutivo em diretórios de mídia do usuário. Limite de espaço, recriação explícita e cancelamento por lote.
3. **Preferências locais explicáveis.** Agregar histórico de aceitação/rejeição e ajustes IN/OUT por perfil. Relatar contagem e frequência, sem inferir estatística robusta com poucos exemplos. Só sugerir pesos; aplicar exige escolha explícita. Não mudar decisões antigas ao recalibrar. Testar consistência ao desfazer/refazer para não contar o mesmo exemplo duas vezes.
4. **Perfis de gameplay.** Narrativo, Ação/Soulslike, Roguelike, Completa e Highlights/Shorts ajustam pesos/margens existentes. Não afirmar reconhecimento de vitória, combate ou reação. Expor valores e permitir restaurar padrão. Validar em amostras reais por perfil.

## 1.1 — audiovisual opcional

- Primeiro baseline com sinais locais e quadros selecionados/cache; depois comparar modelos leves opcionais em CPU. Avaliar vitória/derrota, menus/loading, ambientes/transições, combate e fala/reação em conjunto anotado de jogos diferentes. Relatar erros por classe e jogo. Nenhum classificador influencia remoções antes de validação editorial.
- Evoluir `RenderOptions`/enquadramento atual para keyframes por trecho, presets e ajustes manuais. Suavizar movimentos e preservar HUD/regiões importantes. Testar exportações horizontal/vertical, prévia, proxies e integração com legendas sem alterar tempos de origem.
- Estender o estúdio de legendas com dicionário local de jogos/personagens, busca/substituição com prévia, presets CefasGamer e revisão de sincronização. Texto corrigido continua separado do cache ASR e só é substituído por escolha explícita. Mostrar incerteza por palavra apenas quando houver dado válido do modelo.
- Assistente de publicação baseado somente em transcrição/eventos observados e marcações humanas: títulos, descrição, capítulos e ideias de Shorts. Versão manual/local permanece disponível. Qualquer serviço externo/API deve explicar dados enviados/custo e obter consentimento. Não inventar tendências ou probabilidades de viralização.

## Gates comuns

Projetos v1/v2/v3 legíveis, mídia original idêntica, recursos anteriores preservados, testes de cancelamento/cache e falha de disco, orçamento CPU/RAM e instalador Windows. Separar métricas sintéticas, testes de integração e validação editorial; cada release precisa de evidências próprias.
