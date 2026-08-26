# Protocolo de calibração

A qualidade deve ser medida por cobertura de conteúdo bom, não por quantidade bruta de acertos.

## Gabarito inicial

O VOD de referência de 23 minutos possui sete categorias positivas conhecidas:

1. triple kill + tentativa de quadra;
2. double kill;
3. dive ruim na Lux;
4. kill depois da morte;
5. apresentação do X1;
6. demonstração da Arena;
7. descoberta de mapa repetido.

Os timestamps humanos exatos devem ser cadastrados localmente no manifesto de avaliação; VODs
e transcrições nunca entram no Git.

## Métricas

- Recall de bons: quantos momentos do gabarito possuem sobreposição com algum candidato.
- Cobertura temporal: interseção sobre o intervalo humano, tolerando margem editorial.
- Extras: candidatos sem correspondência; 30-70% extras são aceitáveis na fase de triagem.
- Rotina morta: extras formados só por farm, caminhada, loading ou ruído.
- Precisão do intervalo: presença de preparação, evento e reação.

## Aceitação

- mínimo funcional: 6/7 momentos;
- meta: 7/7;
- saída saudável: 10-15 candidatos totais;
- nenhum bloco genérico de vários minutos;
- nenhum candidato sem descrição e evidência internas;
- farming com explicação entra; farming vazio não entra.

## Ajuste

1. Rode o VOD no perfil coverage.
2. Compare analysis.json com o gabarito.
3. Classifique os erros em geração, análise visual, timestamp ou Story Builder.
4. Ajuste somente a camada responsável.
5. Rode novamente o mesmo VOD e um segundo VOD de validação.
6. Não reduza falsos positivos se isso derrubar o recall de bons.

Fine-tuning só deve ser considerado depois de dezenas de lives rotuladas. Antes disso, pesos,
prompts e exemplos negativos difíceis oferecem mais retorno e são reversíveis.
