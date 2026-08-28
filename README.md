# Picotador de Lives

Aplicativo local para dividir VODs grandes em partes que o ChatGPT consegue acessar pelo
Google Drive e transcrever automaticamente toda a fala em português. O vídeo não é
comprimido nem recodificado: vídeo, áudio e demais faixas são apenas copiados para novos
arquivos com FFmpeg. A transcrição roda localmente com faster-whisper.

## Regras fixas

- cada parte fica abaixo de 256 MB; o alvo seguro é 250 MB;
- nenhuma parte ultrapassa 20 minutos;
- cada parte, exceto a primeira, repete aproximadamente 30 segundos da anterior;
- nomes são ordenáveis: `live 1 - arquivo 001.mp4`, `002`, `003`...;
- cada live recebe um manifesto com o início global real de cada arquivo;
- a transcrição usa por padrão português e o modelo `large-v3`;
- o VOD original é transcrito uma vez na timeline completa;
- cada MP4 recebe um TXT e JSON com timestamps locais e globais;
- o VOD original nunca é modificado ou removido;
- o processamento acontece 100% no computador.

Como não existe recodificação, os cortes respeitam os keyframes do vídeo. Isso pode aumentar a
sobreposição em alguns segundos, mas não reduz a qualidade. O manifesto registra os tempos usados
para que o GPT converta a minutagem local para a minutagem da live.

## Versão portátil para Windows - recomendada

1. Baixe [`Picotador-de-Lives-portatil.zip`](https://github.com/LorenzoDToniazzi/clips-lives-analyzer/releases/download/vod-splitter-portable-latest/Picotador-de-Lives-portatil.zip).
2. Extraia todo o ZIP para uma pasta normal.
3. Abra `Picotador de Lives.exe`.

O pacote já contém Python, FFmpeg e ffprobe. Não exige instalação, `winget`, Git, terminal ou
configuração manual. Também contém o faster-whisper; o modelo `large-v3` é baixado
automaticamente no primeiro uso e mantido em
`%LOCALAPPDATA%\Picotador de Lives\modelos-whisper`. Mantenha todos os arquivos extraídos
juntos.

O programa tenta primeiro NVIDIA/CUDA em `float16`. Se as bibliotecas de GPU não estiverem
disponíveis, repete automaticamente pela CPU em `int8`. O pacote portátil inclui as DLLs
necessárias de CUDA 12 e cuDNN 9; ainda é necessário ter um driver NVIDIA compatível. Uma
falha de transcrição não apaga nem invalida as partes de vídeo já criadas.

Se o Windows exibir o SmartScreen, use **Mais informações > Executar assim mesmo**. O executável é
gerado automaticamente pelo GitHub Actions a partir deste código, mas ainda não possui assinatura
digital comercial.

## Instalação pelo código-fonte - alternativa

1. Baixe a branch `feat/vod-splitter` usando **Code > Download ZIP** e extraia a pasta.
2. Execute `INSTALAR.bat`.
3. Use o atalho **Picotador de Lives** criado na área de trabalho.

Esta opção instala Python e FFmpeg automaticamente e permanece disponível principalmente para
diagnóstico e desenvolvimento.

## Uso

1. Clique em **Adicionar lives** e selecione um ou mais VODs.
2. Escolha a pasta de saída.
3. Deixe **Transcrever em português (large-v3)** marcado. Desmarque apenas quando quiser
   gerar somente os vídeos e o manifesto.
4. Clique em **Iniciar fila**.
5. Aguarde as etapas **Picotando** e **Transcrevendo**. No primeiro uso, o download do modelo
   pode demorar e a porcentagem pode ficar parada enquanto ele é carregado.
6. Para cada VOD será criada uma pasta com as partes, manifestos e transcrições.
7. Envie a pasta inteira ao Google Drive mantendo todos os nomes.

O manifesto JSON é a fonte de verdade. O faster-whisper fornece os tempos na timeline do VOD
original, e o programa calcula para cada parte:

```text
tempo local = tempo global da fala - início global real do arquivo
```

Trechos dentro da sobreposição aparecem nos dois arquivos com o mesmo `segment_id`, permitindo
deduplicação sem perder contexto.

Em caso de falha, selecione **Abrir log**. O arquivo fica em
`%LOCALAPPDATA%\Picotador de Lives\picotador.log`.

Se uma live variável ultrapassaria o limite de tamanho, o programa refaz apenas aquela parte com
menos duração. Se nem um trecho curto puder ficar abaixo de 256 MB sem recodificação, ele interrompe
com uma mensagem em vez de reduzir a qualidade silenciosamente.

Exemplo de saída:

```text
live 1/
  live 1 - arquivo 001.mp4
  live 1 - arquivo 001 - transcricao.txt
  live 1 - arquivo 001 - transcricao.json
  live 1 - arquivo 002.mp4
  live 1 - arquivo 002 - transcricao.txt
  live 1 - arquivo 002 - transcricao.json
  live 1 - arquivo 003.mp4
  live 1 - arquivo 003 - transcricao.txt
  live 1 - arquivo 003 - transcricao.json
  TRANSCRICAO - live 1.txt
  TRANSCRICAO - live 1.json
  TRANSCRICAO - live 1.srt
  MANIFESTO - live 1.txt
  MANIFESTO - live 1.json
```

O TXT de cada arquivo traz as duas referências na mesma linha:

```text
[ARQUIVO 00:07:42.120-00:07:48.900 | LIVE 01:17:42.120-01:17:48.900]
Essa interação funciona porque o E aplica...
```

## Desenvolvimento

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m live_splitter
```
