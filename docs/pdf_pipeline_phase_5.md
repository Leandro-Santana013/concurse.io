# PDF pipeline - Fase 5

## Arquitetura final

```text
PhysicalExtractor -> LayoutAnalyzer/DocumentProfile -> Candidates/Graph/Regions
    -> ConstraintSolver -> Question AST -> Compatibility Renderer
    -> Shadow + Layout Families + optional ML -> ResultArbiter
    -> legacy result / structural result / quarantine
```

`LEGACY_ONLY` continua sendo o default. `STRUCTURAL_SHADOW` executa o caminho
estrutural para diagnóstico e mantém o resultado legado. `STRUCTURAL_PREFERRED`
é opt-in: promove apenas uma saída estrutural que passe pela política do
`ResultArbiter`; em baixa confiança mantém o fallback legado ou marca
quarentena. O schema de perguntas, a API, o banco e o parser híbrido não foram
alterados.

## Dataset confiável e splits

`ReliableDatasetBuilder` só aceita weak labels quando:

- o resultado legado não está vazio nem possui números duplicados;
- o gabarito está disponível e completo;
- os números do gabarito e do resultado legado coincidem;
- respostas já presentes no resultado legado não contradizem o gabarito.

Exames rejeitados ficam em `rejected_exams` com motivos auditáveis. Cada
registro mantém `exam_id`; `GroupKFoldSplitter` usa esse campo como grupo e
`DatasetSplits` verifica que TRAIN, VALIDATION e HOLDOUT não compartilham
exames. Nunca se divide uma página isolada entre splits.

O manifest reproduzível usado pelos comandos está em
`golden/phase5_corpus.json`. A separação por `split` é por prova completa.

## ML supervisionado leve

O primeiro alvo é binário: `QUESTION_HEADER` versus
`NOT_QUESTION_HEADER`. O estimador padrão é `LogisticRegression` com
normalização; `HistGradientBoostingClassifier` pode ser comparado, mas não é
dependência nem requisito do pipeline.

Todo artefato registra:

```text
model_version
feature_schema_version
training_dataset_version
metrics
created_at
```

`ModelRegistry` valida `feature_schema` antes de carregar um modelo. Um
modelo incompatível falha fechado. A ausência do modelo não impede geometria,
clustering, evidências ou constraints: `STRUCTURAL_ML_ENABLED=false` é o
default e a feature flag é lida no rollout estrutural.

## Layout Families

As famílias usam somente o fingerprint do `DocumentProfile`. O nome da banca
não é feature nem label. O clusterizador tenta HDBSCAN quando disponível
(inclusive `sklearn.cluster.HDBSCAN`) e usa DBSCAN quando ele não está
disponível.

Uma família fornece apenas priors: quantidade esperada de colunas, estilo de
cabeçalho/opções, reading order provável e padrões de ruído. A evidência do
PDF atual continua vencendo um prior conflitante. Um perfil distante pode ser
atribuído a `noise`.

## Adapters legados e arbitragem

`build_legacy_adapter_roles` expõe cada adapter preservado em três papéis:

1. evidence provider (`legacy_bank_header_match`, `legacy_option_pattern`,
   `legacy_subject_pattern`);
2. recovery provider (`recover_question(region, expected_number)`);
3. full fallback (`parse` delegando ao parser existente).

`ResultArbiter` aplica os gates HIGH/MEDIUM/LOW. Divergência estrutural/legada
em nível MEDIUM vai para revisão/quarentena; nenhum caminho cria questões para
fazer uma prova passar.

## Benchmark e observabilidade

`BenchmarkReport` mede:

- precision/recall de detecção;
- option extraction accuracy;
- image ownership accuracy;
- ordering accuracy;
- Full Exam Success Rate;
- Zero-Modification Success Rate, também exposta como `generalization_rate`
  para HOLDOUT;
- comparação legacy versus structural;
- cortes por banca, layout family e HOLDOUT.

Cada resultado estrutural pode produzir trace com `document_profile`,
`layout_family`, candidates, sequence, regions, recoveries, adapter, modelos,
confidence e warnings.

## Comandos

Treinar o classificador e gerar registry/modelos:

```bash
python scripts/train_pdf_pipeline_phase5.py \
  --manifest golden/phase5_corpus.json \
  --output-dir artifacts/phase5
```

Executar o benchmark completo ou uma amostra:

```bash
python scripts/benchmark_pdf_pipeline_phase5.py --manifest golden/phase5_corpus.json
python scripts/benchmark_pdf_pipeline_phase5.py --manifest golden/corpus.json --limit 1
```

Ativar apenas em um processo controlado:

```powershell
$env:PDF_PIPELINE_MODE = "STRUCTURAL_SHADOW"
$env:STRUCTURAL_ML_ENABLED = "false"
```

Com o modelo gerado, o shadow completo pode ser ligado no processo da API ou
do worker sem alterar a persistência legada:

```powershell
$null = New-Item -ItemType Directory -Force ".scratch/structural_shadow"
$env:PDF_PIPELINE_MODE = "STRUCTURAL_SHADOW"
$env:STRUCTURAL_ML_ENABLED = "true"
$env:STRUCTURAL_ML_MODEL_REGISTRY = (Resolve-Path "artifacts/phase5/model_registry.json").Path
$env:STRUCTURAL_TRACE_DIR = (Resolve-Path ".scratch/structural_shadow").Path
```

O worker chama esse seam depois do gate de gabarito oficial. Em
`STRUCTURAL_SHADOW`, perguntas persistidas continuam sendo as legadas e cada
execução pode deixar um trace JSON. `STRUCTURAL_PREFERRED` só deve ser
habilitado depois de revisar os KPIs e os traces; divergências são mantidas em
fallback ou quarentena pelo `ResultArbiter`.

Depois de comparar shadow e aprovar os KPIs, o modo preferido pode ser
ativado explicitamente:

```powershell
$env:PDF_PIPELINE_MODE = "STRUCTURAL_PREFERRED"
$env:STRUCTURAL_ML_ENABLED = "false"
```

Para rollback, remova a flag/mode ou defina `PDF_PIPELINE_MODE=LEGACY_ONLY`.
O fallback legado permanece disponível e não há migração de dados necessária.

## Limitações conhecidas

- O corpus local ainda é pequeno para declarar uma melhoria estatisticamente
  confiável em layouts não vistos; os comandos medem e reportam isso.
- Os PDFs locais de gabarito sem bloco completo são rejeitados como labels,
  em vez de virarem truth automática.
- No corpus local executado, as duas variantes da prova 55 foram rejeitadas
  porque o parser legado produz numeração duplicada e o gabarito pareado não
  cobre o mesmo conjunto. A prova 56 passou depois que o script deixou de usar
  o ID técnico do manifest como identidade de cargo. O treino gerou modelo
  diagnóstico com 447 registros provenientes de seis provas aceitas; os
  rejeitos continuam auditáveis em `training_report.json`.
- No benchmark local com o registry, a detecção estrutural foi 1,0, mas a
  extração de opções foi 0,5286, a ordenação 0,8476, o Full Exam Success Rate
  0,375 e a generalização HOLDOUT 0,5. Portanto o rollout permanece em
  `STRUCTURAL_SHADOW`; o modelo não está aprovado para promoção global.
- O caminho estrutural continua opt-in; nenhuma alteração global de ingestão,
  API ou banco foi feita.
- Imagens e opções continuam sendo comparadas como métricas de benchmark;
  diferenças observadas no shadow são diagnósticos, não são escondidas pelo
  arbiter.

## Status

```text
FASE 5 CONCLUÍDA.
Migração estrutural implementada conforme o escopo.
```
