# Protocolo de calibração

A qualidade deve ser medida principalmente por cobertura de conteúdo bom. O maior erro do sistema
é um momento realmente útil existir e não aparecer como candidato.

Falsos positivos fundamentados são aceitáveis. Rotina vazia não é.

## Gabarito inicial

O VOD de referência de aproximadamente 23 minutos deve possuir pelo menos oito positivos humanos:

1. triple kill + tentativa de quadra;
2. double kill;
3. dive ruim na Lux;
4. kill depois da morte;
5. apresentação do X1;
6. demonstração da Arena;
7. descoberta de mapa repetido;
8. build estranha de Gragas com razão concreta e explicação durante a partida.

Os timestamps humanos exatos devem ser cadastrados localmente no manifesto de avaliação. VODs e
transcrições nunca entram no Git.

O item 8 é obrigatório porque testa um caso que detector genérico de highlight tende a perder:
valor editorial durante gameplay potencialmente calmo.

## Métricas

- Recall de bons: quantos momentos do gabarito possuem sobreposição com algum candidato.
- Recall por categoria: gameplay, Ciência/build, explicação, humor, erro, sistema e história.
- Cobertura temporal: interseção sobre o intervalo humano, tolerando margem editorial.
- Extras fundamentados: candidatos sem correspondência que ainda possuem motivo concreto.
- Rotina morta: extras formados só por farm, caminhada, loading, kill/morte banal ou ruído.
- Precisão do intervalo: presença de preparação, evento e reação/payoff quando necessários.
- Duplicação real: o MESMO acontecimento aparecendo várias vezes por sobreposição técnica.

Não penalizar dois highlights diferentes por serem do mesmo campeão, mesma partida ou categoria.

## Aceitação inicial

- mínimo funcional: pelo menos 7/8 positivos;
- meta imediata: 8/8;
- nenhum bloco genérico de vários minutos;
- nenhum candidato mantido apenas por movimento, áudio ou HUD;
- farming com explicação entra; farming vazio não entra;
- quantidade alta de candidatos não é falha por si só se houver valor concreto em cada um.

Depois do primeiro VOD, a meta deve migrar para >= 90% de recall em um conjunto maior de VODs.

## Negativos difíceis para ampliar o benchmark

- kill normal sem diferencial;
- morte normal;
- farm e recall;
- grito/pico de áudio sem conteúdo;
- fight genérica;
- uso rotineiro de X1/Arena/Laboratório;
- conversa administrativa ou irrelevante;
- duas detecções sobrepostas do mesmo evento;
- eventos semelhantes mas diferentes, que NÃO devem ser deduplicados.

## Positivos futuros

- highlight mecânico sem fala;
- Ciência funcionando e falhando;
- explicação durante farm;
- humor/reação;
- morte ou erro que vira conteúdo pelo contexto;
- sistema autoral com bug, disputa ou descoberta;
- hipótese -> teste -> payoff distante.

## Comparação com Work

Para VODs analisados pelo GPT Work, guardar localmente o gabarito humano/Work com timestamp,
categoria, motivo de entrada e, quando útil, motivo de descarte de falsos candidatos óbvios.

O Work é referência editorial para calibração, não fonte de dados durante a execução local.

## Ajuste

1. Rode o VOD no perfil coverage.
2. Compare analysis.json com o gabarito.
3. Classifique cada erro em geração, julgamento editorial, visão, timestamp ou relação de história.
4. Ajuste somente a camada responsável.
5. Rode novamente o mesmo VOD e pelo menos um VOD de validação.
6. Não reduza falsos positivos se isso derrubar recall de bons.
7. Não altere scanner, modelo ou thresholds por intuição quando o erro real estiver no prompt.

Fine-tuning só deve ser considerado depois de dezenas de lives rotuladas.
