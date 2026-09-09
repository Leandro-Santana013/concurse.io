# Rollout estrutural seguro

## Invariante de produção

O worker continua usando o parser legado como resultado canônico. O pipeline
estrutural só é executado depois que o gabarito oficial passa pelo gate de
completude e nunca transforma uma falha estrutural em erro da ingestão.

## Configuração

```text
PDF_PIPELINE_MODE=LEGACY_ONLY
STRUCTURAL_ROLLOUT_PERCENT=0
STRUCTURAL_TRACE_DIR=artifacts/structural-traces
```

Modos suportados:

- `LEGACY_ONLY`: somente o parser legado; rollback imediato.
- `STRUCTURAL_SHADOW`: execução estrutural amostrada, resultado legado para o usuário.
- `STRUCTURAL_PREFERRED`: estrutural só é promovido por arbitragem; divergências ficam em quarentena.
- `STRUCTURAL_ONLY`: reservado para testes/gates; ainda preserva o legado em falha.

`STRUCTURAL_ROLLOUT_PERCENT` usa bucket determinístico SHA-256 por `exam_id`.
Assim, o mesmo exame permanece no mesmo grupo entre processos e reinícios.
Definir `0` desliga a amostragem; definir `100` executa todos os exames do modo
selecionado. `PDF_PIPELINE_MODE=LEGACY_ONLY` sempre vence qualquer percentual.

## Trace e privacidade

Quando `STRUCTURAL_TRACE_DIR` está definido, cada trace é gravado com arquivo
temporário e `os.replace`. O payload contém contagens, ids físicos, scores,
diferenças e motivo da arbitragem, mas não persiste enunciados, alternativas,
respostas ou texto de linha. Falha de escrita do trace não interrompe a
ingestão.

## Promoção

No estado atual, a promoção estrutural exige arbitragem `STRUCTURAL`. Se o
resultado divergir do legado em qualquer métrica estrutural observada, ele vai
para `QUARANTINE` e o legado continua sendo persistido. O helper de adoção
também não permite que valor estrutural vazio apague um valor legado nem cria
resposta padrão.

Antes de `STRUCTURAL_PREFERRED` em produção, executar os gates quantitativos
publicados no plano de excelência, incluindo o corpus holdout do IBAM 2016,
zero regressão do parser legado e ausência de P0/P1.
