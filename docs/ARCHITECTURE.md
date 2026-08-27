# Arquitetura

## Fluxo

VOD bruto -> FFmpeg e ffprobe -> transcrição e scanner contínuo -> candidatos semânticos e
visuais -> inspeção visual adaptativa com Qwen3-VL -> relação entre candidatos -> timestamps.txt.

## Decisões

- Python 3.11: ecossistema estável para faster-whisper e Windows.
- SQLite/WAL: fila persistente, atômica e sem servidor.
- FFmpeg: leitura previsível de MP4, MKV e codecs comuns.
- faster-whisper turbo: transcrição rápida para indexação semântica em português.
- Ollama + qwen3-vl:8b: inferência visual e textual 100% local em GPU de 16 GB.
- Tkinter: interface nativa, sem navegador, Node ou serviço web.
- JSON Schema: decisões do modelo estruturadas antes de chegar ao relatório.

A RTX 5060 Ti 16 GB, Ryzen 5 9600X e 16 GB de RAM são a máquina de calibração inicial, não
requisitos mínimos comprovados. Requisitos reais só devem ser definidos depois do benchmark.

## Detecção barata antes da IA pesada

O scanner decodifica frames em escala de cinza a 320x180 e 2 FPS. Para cada amostra mede:

- diferença global;
- proporção de mudança brusca;
- atividade no centro da tela;
- atividade no terço inferior do HUD;
- atividade na área superior direita, usada apenas como indício de mudança na região do kill feed;
- energia e pico relativos do áudio.

Os valores são normalizados por percentis dentro do próprio VOD. Esses sinais NUNCA aprovam
clips. Eles só abrem janelas para inspeção. Uma porta independente baseada na transcrição impede
que uma explicação relevante durante farming seja perdida.

O scanner permanece em 2 FPS no primeiro benchmark. Reduzir para 1 FPS só deve ocorrer depois de
comparar recall.

## Geração e deduplicação de candidatos

Não existe quota editorial por hora. Se uma live tiver muitos momentos realmente bons, todos
devem poder chegar ao julgamento profundo.

A deduplicação existe apenas para detecções fortemente sobrepostas do MESMO acontecimento. Duas
plays distintas não são fundidas só porque aconteceram próximas ou pertencem à mesma categoria.

## Julgamento editorial

Cada janela começa com 9 frames distribuídos temporalmente, transcrição, sinais e hipótese do
primeiro passe. A IA precisa responder de forma concreta:

1. o que aconteceu;
2. se existe potencial de conteúdo;
3. qual é a razão editorial principal;
4. evidências com timestamps;
5. o que diferencia o momento de rotina;
6. contexto anterior/posterior relevante;
7. A/B/C/descarte.

Gameplay, Ciência/build, explicação, humor/reação, erro/situação negativa, sistemas/comunidade e
história são portas independentes.

### Inspeção visual adaptativa

- primeira leitura: 9 frames;
- A/B com confiança alta: encerra;
- C, baixa confiança ou descarte conflitante com sinais fortes: nova leitura com 27 frames;
- descarte muito confiante e sem evidência prévia forte pode encerrar na leitura curta.

No modo coverage, uma contradição entre uma primeira leitura positiva e uma segunda negativa não
apaga silenciosamente o candidato: ele pode ser preservado como C quando houver evidência.

## Contexto do Ollama

O contexto comum foi reduzido de 32K para 8K. A etapa textual de relação entre candidatos pode
usar 16K porque recebe uma lista maior e não carrega storyboards.

Durante calibração, `ollama ps` deve ser usado para confirmar que o modelo permanece 100% na GPU.

## Whisper e CPU

O modo padrão não aceita fallback silencioso do Whisper para CPU. Se CUDA falhar, a análise para
com mensagem clara. O usuário pode habilitar `whisper_allow_cpu_fallback` explicitamente.

## Relações e histórias

O componente atual relaciona candidatos que já foram encontrados. Ele NÃO procura ativamente no
VOD um payoff que nunca virou candidato. Nesta versão ele deve ser entendido como Story Linker.

Uma futura busca ativa por payoff deve começar pela transcrição e `related_search_terms`, abrindo
nova inspeção visual somente quando texto/contexto sugerirem uma relação. Isso é pós-benchmark.

Momentos relacionados nunca são fundidos ou removidos por causa da relação.

## Checkpoints

Cada job possui artefatos atômicos por etapa. A análise profunda salva cada candidato terminado.
Ao concluir, temporários são removidos por padrão.

## Pontos de extensão pós-benchmark

- Story Finder ativo baseado primeiro em transcrição;
- perfis de HUD por resolução;
- OCR especializado no kill feed e inventário, somente se o scanner perder eventos reais;
- feedback Bom/Talvez/Ruim;
- teste Qwen3-VL 4B versus 8B;
- comparação scanner 1 FPS versus 2 FPS;
- exportação opcional de cortes.
