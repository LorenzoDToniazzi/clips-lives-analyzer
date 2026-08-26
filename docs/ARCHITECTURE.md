# Arquitetura

## Fluxo

VOD bruto -> FFmpeg e ffprobe -> transcrição e scanner contínuo -> candidatos semânticos e
visuais -> storyboards com Qwen3-VL -> Story Builder -> timestamps.txt.

## Decisões

- Python 3.11: ecossistema estável para faster-whisper e Windows.
- SQLite/WAL: fila persistente, atômica e sem servidor.
- FFmpeg: leitura previsível de MP4, MKV e codecs comuns.
- faster-whisper turbo: transcrição rápida para indexação semântica em português.
- Ollama + qwen3-vl:8b: inferência visual e textual 100% local em GPU de 16 GB.
- Tkinter: interface nativa, sem navegador, Node ou serviço web.
- JSON Schema: decisões do modelo estruturadas antes de chegar ao relatório.

## Detecção barata antes da IA pesada

O scanner decodifica frames em escala de cinza a 320x180 e 2 FPS. Para cada amostra mede:

- diferença global;
- proporção de mudança brusca;
- atividade no centro da tela;
- atividade no terço inferior do HUD;
- atividade na área superior direita, usada como indício de kill feed;
- energia e pico relativos do áudio.

Os valores são normalizados por percentis dentro do próprio VOD. Isso evita limiares absolutos
frágeis entre OBS, volume e resoluções diferentes.

Esses sinais não aprovam clips. Eles só criam janelas. Uma porta independente baseada na
transcrição impede que uma explicação relevante durante farming seja perdida.

## Julgamento editorial

Cada janela recebe dezoito frames distribuídos temporalmente em dois storyboards, transcrição,
sinais e hipótese do primeiro passe. A saída exige decisão A/B/C/descarte, início e fim globais,
descrição concreta, motivo editorial, evidências e confiança.

No modo cobertura, um descarte pouco confiante pode ser preservado como C apenas quando há fala
semântica concreta ou sinais excepcionais combinados. Movimento isolado nunca recebe proteção.

## Checkpoints

Cada job possui artefatos atômicos por etapa. Arquivos JSON são escritos em temporário e
substituídos com os.replace, evitando checkpoint corrompido em queda de energia. A análise
profunda salva cada candidato terminado. Ao concluir, temporários são removidos por padrão.

## Pontos de extensão

- perfis de HUD por resolução;
- OCR especializado no kill feed e inventário;
- feedback Bom/Talvez/Ruim para recalibrar pesos;
- provedor visual alternativo local;
- exportação opcional de cortes, sem alterar o motor de seleção.
