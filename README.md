# Clips Lives Analyzer

Aplicativo local para analisar VODs brutos de League of Legends e devolver timestamps de
possíveis conteúdos bons, sem enviar vídeo, áudio ou transcrição para a internet.

A meta do sistema é alta cobertura editorial: encontrar tudo que vale revisão, aceitar alguns
candidatos duvidosos e descartar rotina vazia. O resultado principal de cada VOD é simples:

    nome-do-vod.mp4

    00:12:31 - 00:13:18
    00:47:02 - 00:47:49
    01:21:11 - 01:22:06

## Como usar no Windows

1. Baixe ou clone este repositório.
2. Dê dois cliques em INSTALAR.bat.
3. Aguarde o download dos componentes e modelos locais.
4. Abra o atalho Clips Lives Analyzer criado na área de trabalho.
5. Adicione vários VODs ou uma pasta e clique em Iniciar fila.

Você não precisa abrir editor, terminal ou escrever código. O primeiro setup baixa cerca de
8-12 GB entre dependências e modelos. Recomenda-se ao menos 20 GB livres durante a análise.

## O que ele realmente analisa

O programa não usa um frame aleatório e finge que assistiu à live. O pipeline:

1. transcreve todo o áudio com timestamps por palavra;
2. percorre o vídeo continuamente a 2 amostras por segundo;
3. mede combate, mudanças de cena, HUD, região do kill feed e energia/reação do áudio;
4. usa a fala inteira para encontrar explicações, Ciências, humor, opiniões e sistemas da live;
5. abre janelas com preparação e reação ao redor de sinais suspeitos;
6. mostra storyboards temporais ao modelo visual local;
7. obriga o modelo a explicar o que ocorreu antes de manter um candidato;
8. procura histórias distantes como explicação -> teste -> payoff;
9. devolve somente os intervalos sustentados por evidência.

Kills bonitas são válidas sozinhas. Explicações de item, build ou pick estranho também são
válidas durante gameplay calmo. Farming, caminhada, recall e luta genérica não entram sem um
motivo editorial concreto.

## Fila e retomada

- Aceita vários arquivos e pastas inteiras.
- Processa um VOD por vez para não disputar VRAM.
- Salva checkpoints depois de cada etapa.
- Se o programa ou o computador for fechado, o item atual volta para a fila.
- Ao tentar novamente depois de uma falha, reaproveita tudo que já foi concluído.
- Nunca altera o VOD original.
- Temporários são apagados ao concluir por padrão.

Os dados operacionais ficam em AppData/Local/InsanoToni/ClipsLivesAnalyzer.

## Hardware e desempenho

Configuração-alvo inicial:

- Windows 10 22H2 ou Windows 11;
- RTX 5060 Ti 16 GB;
- 16 GB de RAM;
- CPU Ryzen 5 9600X;
- driver NVIDIA atualizado.

O modelo visual padrão é qwen3-vl:8b, executado pelo Ollama local. O Whisper tenta usar CUDA e
cai automaticamente para CPU se as bibliotecas CUDA de transcrição não estiverem disponíveis.
Isso deixa o processamento mais lento, mas não perde a análise nem quebra a fila.

O modo padrão coverage pode inspecionar até 45 janelas por hora de VOD. Esse limite existe para
impedir que ruído gere centenas de análises, mas candidatos vindos de fala relevante têm
prioridade e não são descartados só para caber no limite.

## Resultado e privacidade

O arquivo principal é timestamps.txt. Com a opção de análise interna ativa, o aplicativo também
guarda details.md e analysis.json para depuração e calibração. Esses arquivos não são uploads e
permanecem no computador.

O cliente recusa URLs do Ollama que não apontem para localhost ou 127.0.0.1. Não há API paga,
Google Drive, telemetria ou provedor externo no pipeline.

## Limite honesto da primeira versão

O sistema está implementado e testável, mas sua precisão editorial real só pode ser medida na
RTX e nos VODs de referência. O primeiro critério de aceitação é recuperar pelo menos 6 dos 7
momentos do VOD-gabarito de 23 minutos, idealmente 7/7, aceitando até 10-15 candidatos no total.
Ajustes de limiar e prompt devem ser feitos a partir desse resultado, não de chute.

Consulte docs/ARCHITECTURE.md e docs/CALIBRATION.md para os detalhes técnicos.
