# Referência para player e formato no Estúdio de Legendas

Pedido atual: levar os controles de formato/enquadramento para a etapa de legendas e reproduzir o clipe continuamente, com play/pause dentro do Radar, superando a prévia externa de seis segundos. Esse pedido autoriza antecipar esta parte do planejamento de player numa **branch separada de evolução do estúdio**. Não representa validação da versão estável 1.0 nem dispensa os gates editoriais pendentes da pré-edição 0.9.

## Referência consultada

Repositório [ColinGPT9/clips-studio](https://github.com/ColinGPT9/clips-studio), também apresentado como Clips Kitty, revisão **56a571faadd244926d1abdae5843d413af8665f9**. Auditoria somente leitura do README, licença/NOTICE, editor e rotas de mídia; não foi instalado nem executado o aplicativo de referência.

| Componente real da referência | Comportamento observado |
| --- | --- |
| `ui/src/renderer/src/components/EditorModal.tsx` | Player HTML `<video controls autoPlay>`, imagem/áudio no editor e sobreposições de texto. |
| `TimelineEditor.tsx` | Cursor acompanha o relógio do vídeo; play/pause, seek, volume/velocidade e simulação de cortes. Os cortes são pulados somente enquanto reproduz, para não disputar o cursor durante arraste. |
| `GamingLayoutEditor.tsx` | Prévia e seleção manual das regiões de câmera/jogo, proporções, divisão e posicionamento. |
| `gaming/layouts.json` | Presets de quadro completo, fundo desfocado, câmera/jogo empilhados e picture-in-picture. |
| `server/api.py`, rota `/clips/{clip_id}/preview` | Renderiza a prévia exata com alterações pendentes pelo caminho do exportador. O player costuma reproduzir um clipe MP4 já preparado. Não é um renderizador universal instantâneo. |

## Adaptação ao Radar

Preservar Python/Tkinter, visual azul, mídia original, projetos e serviços de exportação existentes. A referência orienta a organização do produto; seus componentes React/Electron não funcionam diretamente dentro do Canvas Tk.

A aba **Formato e enquadramento** reúne os quatro formatos que o Radar já renderiza de verdade: original, horizontal 16:9, vertical com recorte e vertical com fundo desfocado. Resolução/qualidade continuam compartilhadas com Exportar e são opções do projeto. X/Y ficam explícitos como enquadramento por clipe; os controles permitem aplicar, centralizar e conferir prévia. Não são expostos câmera separada, tracking, picture-in-picture ou tela dividida enquanto não houver renderização e persistência próprias para esses recursos.

O player precisa usar relógio de reprodução, manter áudio/imagem sincronizados, limitar buffers/CPU e liberar processos e arquivos ao trocar de clipe ou fechar. A prévia deve refletir o mesmo enquadramento e as mesmas legendas do exportador. Uma preparação de mídia deve mostrar seu estado real, permitir cancelamento e reutilizar resultados compatíveis. Não chamar uma animação de relógio sem vídeo/áudio de player funcional.

Uma eventual comparação de Tk com Qt/Electron requer medições no hardware alvo. A referência recomenda 16 GB de RAM e inclui uma pilha de dependências maior; ela não fornece evidência para migrar toda a interface do Radar.

## Licença e autoria

`LICENSE`, `NOTICE` e `ui/package.json` da revisão inspecionada indicam **AGPL-3.0-or-later**. Nesta adaptação, os controles são implementados com código próprio e reutilizam os módulos do Radar. Nenhum componente React, pipeline de renderização, conteúdo de preset ou ativo visual da referência foi transplantado. Incorporar código AGPL diretamente exigiria avaliar e cumprir as obrigações de distribuição e disponibilização de código correspondentes.

As ideias de interface descritas não estabelecem reconhecimento de câmera, semântica de jogos ou qualidade editorial. O resultado continua sujeito à validação funcional, de sincronização, Windows/empacotamento e uso em vídeos reais.
