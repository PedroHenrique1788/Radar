# Radar de Cortes 0.8.0 — Painel e Biblioteca / Windows x64

Baixe **RadarCortes-Setup-0.8.0-Windows-x64.exe**, execute o assistente e abra **Radar de Cortes** pelo Menu Iniciar. O pacote inclui Python, FFmpeg/FFprobe/FFplay e Whisper tiny CPU/int8. A atualização usa a mesma instalação por usuário e preserva seus dados separados do aplicativo.

O Radar ganha uma organização inspirada no Clips Studio / Clips Kitty, com implementação própria e a identidade azul CefasGamer:

- **Painel** inicial com importação, projetos recentes, contadores reais e acesso ao estúdio.
- **Biblioteca de clipes** com cartões e miniaturas reais, busca por título/fala/categoria sem exigir acentos, favoritos, revisão e indicação de legendas.
- Filtros Todos/Favoritos/Aprovados/Pendentes/Descartados/Com legendas e ordenação por tempo, potencial ou duração.
- Atalhos **Editar**, **Legendas** e **MP4** em cada cartão. A seleção é preservada entre páginas e filtros, e **Exportar seleção** usa a fila MP4 recuperável já existente.
- **Fila e atividade** com tarefa em execução, pausa/cancelamento, checkpoints e CPU/RAM do Radar, além do disco livre.
- Atalhos de teclado para importar, abrir/salvar projeto, buscar e navegar no estúdio.

As miniaturas usam um quadro por clipe e cache da sessão; não executam Whisper ou uma API. O funcionamento continua local em CPU, sem GPU dedicada ou novas dependências. Gemini mantém sua ativação opcional. O Estúdio de Legendas da versão 0.7.0, projetos anteriores, editor, timeline, formatos e FilmCraft continuam disponíveis.

Esta adaptação cobre a organização e o fluxo visual. Download por URL, rastreamento automático e publicação em redes sociais continuam fora desta versão.

Os testes verificam busca/filtros, pontuação editorial válida, miniaturas por pixels e cache, paginação/seleção, navegação para os editores, exportação real dos clipes marcados e reabertura de projetos pelo painel. O instalador só é publicado após os testes nativos Windows, o EXE offline, a instalação, o app instalado e a desinstalação serem aprovados. Os testes Gemini usam respostas controladas e nenhuma chave real.

[Guia da nova interface](https://github.com/PedroHenrique1788/Radar/blob/main/docs/REFERENCIA_CLIPS_STUDIO.md) · [Referência solicitada](https://github.com/ColinGPT9/clips-studio)
