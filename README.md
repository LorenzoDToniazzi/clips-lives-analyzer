# Picotador de Lives

Aplicativo local para dividir VODs grandes em partes que o ChatGPT consegue acessar pelo
Google Drive. Ele não analisa, não comprime e não altera a qualidade: vídeo, áudio e demais
faixas são apenas copiados para novos arquivos com FFmpeg.

## Regras fixas

- cada parte fica abaixo de 256 MB; o alvo seguro é 250 MB;
- nenhuma parte ultrapassa 20 minutos;
- cada parte, exceto a primeira, repete aproximadamente 30 segundos da anterior;
- nomes são ordenáveis: `live 1 - arquivo 001.mp4`, `002`, `003`...;
- cada live recebe um manifesto com o início global real de cada arquivo;
- o VOD original nunca é modificado ou removido;
- o processamento acontece 100% no computador.

Como não existe recodificação, os cortes respeitam os keyframes do vídeo. Isso pode aumentar a
sobreposição em alguns segundos, mas não reduz a qualidade. O manifesto registra os tempos usados
para que o GPT converta a minutagem local para a minutagem da live.

## Instalação no Windows

1. No GitHub, selecione a branch `feat/vod-splitter`, use **Code > Download ZIP** e
   extraia a pasta.
2. Dê dois cliques em `INSTALAR.bat`.
3. Use o atalho **Picotador de Lives** criado na área de trabalho.

O instalador prepara Python e FFmpeg automaticamente usando o `winget` quando necessário.
Você não precisa instalar Git, abrir terminal nem escrever código para usar o programa.

## Uso

1. Clique em **Adicionar lives** e selecione um ou mais VODs.
2. Escolha a pasta de saída.
3. Clique em **Iniciar fila**.
4. Para cada VOD será criada uma pasta com as partes e os manifestos `.txt` e `.json`.
5. Envie a pasta da live ao Google Drive mantendo os nomes.

Se uma live variável ultrapassaria o limite de tamanho, o programa refaz apenas aquela parte com
menos duração. Se nem um trecho curto puder ficar abaixo de 256 MB sem recodificação, ele interrompe
com uma mensagem em vez de reduzir a qualidade silenciosamente.

Exemplo de saída:

```text
live 1/
  live 1 - arquivo 001.mp4
  live 1 - arquivo 002.mp4
  live 1 - arquivo 003.mp4
  MANIFESTO - live 1.txt
  MANIFESTO - live 1.json
```

## Desenvolvimento

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m live_splitter
```
