# Clips Lives Analyzer

Aplicativo local para analisar VODs brutos de League of Legends e devolver timestamps de
possíveis conteúdos bons, sem enviar vídeo, áudio ou transcrição para a internet.

A meta do sistema é alta cobertura editorial: encontrar praticamente tudo que vale revisão,
aceitar alguns candidatos duvidosos e descartar rotina vazia. O resultado principal de cada VOD
é simples:

    nome-do-vod.mp4

    00:12:31 - 00:13:18
    00:47:02 - 00:47:49
    01:21:11 - 01:22:06

O programa caça material. Ele não tenta decidir sozinho o que será publicado.

## Como usar no Windows

1. Baixe ou clone este repositório.
2. Dê dois cliques em INSTALAR.bat.
3. Aguarde o download dos componentes e modelos locais.
4. Abra o atalho Clips Lives Analyzer criado na área de trabalho.
5. Adicione vários VODs ou uma pasta e clique em Iniciar fila.

Você não precisa abrir editor, terminal ou escrever código. O primeiro setup baixa cerca de
8-12 GB entre dependências e modelos. Recomenda-se ao menos 20 GB livres durante a análise.

## O que ele realmente analisa

1. transcreve todo o áudio com timestamps por palavra;
2. percorre o vídeo continuamente a 2 amostras por segundo em 320x180 e escala de cinza;
3. mede combate, mudanças de cena, HUD, região superior direita e energia/reação do áudio;
4. usa a fala inteira para encontrar explicações, Ciências, humor, opiniões e sistemas da live;
5. abre janelas com preparação e reação ao redor de sinais suspeitos;
6. faz uma primeira inspeção multimodal com 9 frames distribuídos na janela;
7. aprofunda para 27 frames somente quando a decisão é ambígua ou conflita com evidências fortes;
8. exige descrição objetiva, razão editorial, diferença para rotina e evidências timestampadas;
9. relaciona candidatos distantes quando ambos já foram encontrados;
10. devolve somente os intervalos sustentados por evidência.

Sinais técnicos nunca aprovam clips sozinhos. Eles apenas pedem inspeção.

Kills bonitas são válidas sozinhas. Explicações de item, build ou pick estranho também são
válidas durante gameplay calmo. Mortes e erros podem ser conteúdo quando contexto, humor,
Ciência, tentativa ou consequência dão valor ao trecho.

Não existe quota de clips por hora. Três highlights diferentes de Gragas continuam sendo três
candidatos se os três tiverem valor. Só o mesmo acontecimento detectado por janelas fortemente
sobrepostas é deduplicado.

## Critério editorial

A pergunta central é:

> Existe alguma razão concreta para alguém querer assistir a este trecho além do simples fato de
> algo ter acontecido?

As portas principais são independentes: gameplay/highlight; Ciência/build; explicação/educativo;
humor/reação; erro/morte com contexto; sistemas/comunidade; história/callback/payoff.

A prioridade é recall. Na dúvida fundamentada, o momento pode permanecer como C para revisão. Na
dúvida sem evidência concreta, é descartado.

## Fila e retomada

- Aceita vários arquivos e pastas inteiras.
- Processa um VOD por vez para não disputar VRAM.
- Salva checkpoints depois de cada etapa.
- Se o programa ou o computador for fechado, o item atual volta para a fila.
- Ao tentar novamente depois de uma falha, reaproveita tudo que já foi concluído.
- Nunca altera o VOD original.
- Temporários são apagados ao concluir por padrão.

## Hardware e desempenho

A RTX 5060 Ti 16 GB, 16 GB de RAM e Ryzen 5 9600X são a máquina de calibração inicial, não
requisitos mínimos comprovados.

O modelo visual padrão continua sendo qwen3-vl:8b. O contexto comum foi reduzido de 32K para 8K;
a etapa textual que relaciona muitos candidatos pode usar 16K.

O Whisper tenta usar CUDA. Por padrão, se a GPU/CUDA falhar, a análise para com erro claro em vez
de cair silenciosamente para CPU. O fallback lento pode ser habilitado explicitamente no config.

O scanner permanece em 2 FPS no primeiro benchmark. Reduzi-lo para 1 FPS e testar Qwen 4B são
experimentos posteriores que só serão aceitos se mantiverem recall.

## Resultado e privacidade

O arquivo principal é timestamps.txt. Com a análise interna ativa, details.md e analysis.json são
guardados localmente para depuração e calibração.

## Limite honesto da primeira versão

A precisão editorial real só pode ser medida na GPU e nos VODs de referência. O primeiro gabarito
deve cobrir pelo menos oito casos positivos, incluindo highlights, sistemas da live e a explicação
da build estranha de Gragas durante a partida. O mínimo funcional inicial é 7/8; a meta é 8/8.

O componente de histórias atual apenas relaciona candidatos que já sobreviveram à detecção. Uma
busca ativa por payoff que nunca virou candidato é uma evolução pós-benchmark.

Consulte docs/ARCHITECTURE.md e docs/CALIBRATION.md.
