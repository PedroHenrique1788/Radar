# Validação — 7 de novembro de 2026

## Registro inicial, antes do instalador Windows

Ambiente atual: Linux x86_64, Python 3.12.14, FFmpeg/FFprobe 7.1.5, Tk 9.0, NumPy 2.2.6, faster-whisper 1.2.1, OpenTimelineIO 0.18.1, FilmCraft CLI oficial 0.18.0. Testes GUI em Xvfb 1280×900; sem GPU necessária para análise e exportação.

Comando final executado:

```bash
DISPLAY=:99 FILMCRAFT_CLI=/workspace/tools/filmcraft/bin/filmcraft-cli \
  .venv/bin/python -m pytest -q --basetemp=/tmp/radar-tests-final
```

**23 passaram; nenhum falhou ou foi ignorado; 17,25 s.**

- Conversão de timestamps, arredondamento e vídeos com mais de 99 horas na representação temporal; rejeição de valores inválidos.
- Leitura de mídia sintética com duas faixas distintas e seleção de cada faixa/mix.
- Exportação FFmpeg: limites originais, duração, resolução, duas faixas e alinhamento entre mudança visual e pico sonoro.
- Relatórios CSV/JSON e legendas SRT relativas ao corte.
- Análise de todo o vídeo sintético, silêncio, vídeo sem áudio, arquivos inválidos, cancelamento e falha de transcrição.
- Deslocamento entre blocos de 300 s com transcritor simulado; cache de análise sem transcrição.
- PTS inicial não zero em MKV e atraso de áudio; alinhamento a quadros e vídeo VFR.
- Deduplicação e fronteiras de palavras nos candidatos.
- Interface: metadados, faixas, seleção, detalhe, copiar tempos e ajuste assíncrono.
- FilmCraft real: três intervalos (1,12–4,28 s; 17,12–20,68 s; 25,2–33,6 s), criação e reabertura de projeto, títulos, resolução, sequências, duas faixas, source-in e duração. Exportação de cada sequência pela CLI com CPU. No segundo intervalo, verificadas mudança de imagem e reação de 440 Hz na posição correta, mantendo o áudio independente de 880 Hz.

Também executados: instalação repetida por `scripts/setup_cloud.sh`, importações reais das bibliotecas e CLI headless do Radar sobre vídeo sintético, que gerou uma sugestão e `resultados/smoke.json`. O arquivo de mídia e os projetos de teste ficam em `/tmp/radar-tests-final`, temporários desta instância. Não são exemplos permanentes distribuídos.

O arquivo oficial FilmCraft foi validado com SHA256SUMS da release via HTTPS. Xvfb foi extraído sem root de pacote Debian, com índice InRelease assinado verificado pelas chaves do sistema e SHA-256 do pacote conferido.

## Pendente ou não validado

- **Reconhecimento real de português:** o acesso HTTPS ao Hugging Face retornou bloqueio de proxy (403). Importar faster-whisper passou, mas isso não comprova transcrição. Domínios foram propostos no rascunho do ambiente; aplicar a rede, baixar um modelo e testar uma amostra conhecida ainda é necessário.
- Windows 10/11, instaladores BAT, desktop FilmCraft no Windows, microfone/gravações reais do OBS e desempenho em vídeos de muitas horas não foram testados nesta máquina Linux.
- MCP/canal JSON ao vivo não foram exercitados; a integração validada usa a CLI headless oficial.
- Publicação e restauração em nova tarefa pertencem à interface de ambientes e não foram executadas por este trabalho.

Configuração reutilizável salva: `install_script`, `start_skill`, associação do checkout `Radar` e domínios de download de modelos. Salvar o rascunho não aplica a rede nem publica o snapshot. O repositório remoto estava vazio e o checkout em branch local ainda sem commits; os arquivos implementados permanecem locais, sem push.


## Validação adicional do pacote Windows

A automação nativa [Instalador Windows](https://github.com/PedroHenrique1788/Radar/actions/workflows/windows-installer.yml) verifica os executáveis no runner Windows Server 2022 x64 com Python 3.12. Isso não equivale a um teste manual no computador do usuário com Windows 10/11.

- A suíte atual passou em Linux: **27 testes**, com GUI Xvfb e integração real FilmCraft. No Windows, a suíte passou com o teste opcional da CLI FilmCraft ignorado, pois o editor não foi instalado nesse runner.
- O executável PyInstaller passou no teste com `HF_HUB_OFFLINE=1`: GUI, FFmpeg/FFprobe/FFplay incluídos, leitura e exportação MP4, JSON, OpenTimelineIO, carregamento de modelo tiny CPU int8, VAD sobre silêncio e reconhecimento real de uma amostra sintética de português. A amostra é gerada com eSpeak, não com gravação pessoal. Não mede precisão em gameplay.
- A validação real detectou incompatibilidade entre faster-whisper 1.2.1 e PyAV 19. O projeto agora fixa **PyAV 16.0.1**, com um teste adicional do decodificador.
- O modelo tiny é incluído na revisão `d90ca5fe260221311c53c58e660288d3deb8d356`; não depende do primeiro download no computador do usuário. Os resultados desta automação substituem a pendência inicial de reconhecimento básico no pacote Windows; o download direto de pesos nesta máquina cloud continuou bloqueado no CDN.
- O pacote inclui os runtimes Python/Visual C++, FFmpeg com verificação SHA-256 e licenças dos componentes. Não há assinatura digital de editor nesta versão.
- A execução [42419007223](https://github.com/PedroHenrique1788/Radar/actions/runs/42419007223) também passou na geração Inno Setup, instalação silenciosa por usuário, repetição do teste funcional no aplicativo instalado e desinstalação. O artefato gerado tem aproximadamente 279 MB. A publicação de uma versão usa novamente esses mesmos gates antes de liberar o download.
