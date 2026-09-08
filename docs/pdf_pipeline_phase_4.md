# PDF pipeline — Fase 4

## Escopo

A Fase 4 é opt-in e recebe a saída da Fase 3 (`Question Candidates`,
`DocumentGraph` e `DocumentProfile`). Ela acrescenta solver global, recovery
localizado, Question AST, renderer compatível e execução shadow. O parser
legado, os adapters de Dataprev/IBAM/IDCAP, a API e o schema do banco não foram
substituídos.

Fluxo implementado:

```text
Question Candidates + Document Graph + Document Profile + evidências
    -> ConstraintSolver
    -> ExamDocumentNode / QuestionNode AST
    -> render_legacy_question_dict
```

## Constraint Solver

O seam público é `ConstraintSolver.solve(analysis, ...)`. O resultado é um
`SequenceSolution` serializável com sequência escolhida, candidatos
descartados, candidatos recuperados, score, violações, warnings, recovery e
`DocumentParseConfidence`.

As regras auditáveis são:

- sequência `n -> n + 1` recebe recompensa; saltos, inversões e duplicidades
  recebem penalidade;
- a ordem física é usada como restrição de leitura e pode ser superada apenas
  quando a evidência global do gabarito dá suporte à sequência numérica;
- candidatos com o mesmo número são deduplicados e a escolha fica registrada
  como `unique_printed_number`;
- regiões que compartilham elementos ou têm overlap geométrico impossível não
  podem coexistir;
- `option_support` prefere quatro/cinco opções ou as contagens inferidas do
  `DocumentProfile`;
- assinaturas/estilos e a evidência legada entram como suporte, nunca como
  parser final;
- o gabarito oficial apoia números presentes, mas não cria uma questão sem
  candidato físico ou recuperação localizada.

O score usado pelo solver é:

```text
candidate_score
+ sequence_score
+ layout_consistency_weight * layout_consistency
+ option_support_weight * option_support
+ answer_key_support_weight * answer_key_support
+ legacy_support_weight * legacy_support
- overlap/impossible-jump/backward penalties
```

Os pesos e limites estão centralizados em `SolverConfig`; não há thresholds
espalhados na implementação.

Quando há um gabarito global suficientemente informativo, o solver escolhe o
melhor candidato disponível por número e ordena a sequência numericamente,
registrando a justificativa de inversões físicas. Isso resolve, por exemplo,
uma leitura intercalada de duas colunas sem deixar o gabarito inventar
questões.

## Recovery localizado

Para lacunas como `11, 13`, o `RecoveryPass` procura somente entre os limites
físicos dos candidatos vizinhos. As fontes avaliadas são:

- candidato já detectado para o número, mas não escolhido;
- elemento físico com número isolado ou cabeçalho OCR;
- estilo dominante e proximidade local;
- evidência das regras legadas;
- questão legada, apenas como último suporte e sem inventar `source_element_ids`.

O threshold de recovery é local e configurável. O parser global não fica mais
permissivo.

## Question AST

`ExamDocumentNode` contém `ContextNode` compartilhados e `QuestionNode`s.
Cada questão mantém `QuestionHeaderNode`, `StatementNode`, `FigureNode`,
`TableNode`, `OptionGroupNode`/`OptionNode`, referências de contexto, matéria,
confiança e evidências. Todos os nós possuem `source_element_ids` e o AST tem
`to_dict`/`to_json`/`from_dict`/`from_json`.

Contextos físicos sobrepostos são coalescidos em um único `ContextNode`.
`context_refs` mantém o vínculo sem duplicar a semântica; a repetição exigida
pelo payload antigo acontece somente no renderer.

## Compatibility Renderer

`render_legacy_question_dict(ast_question)` produz o schema atual:

```text
numero_questao, enunciado, opcoes, resposta, disciplina,
images, latex_support, question_index
```

`render_legacy_document` pode materializar contextos compartilhados para
preservar o comportamento de consumidores atuais. Typography restoration,
fórmulas e tabelas são hooks tardios opcionais (`late_formatting=True`); a
implementação legada continua intacta.

## STRUCTURAL_SHADOW e diff

`StructuralShadowRunner` e `run_structural_shadow` executam:

```text
legacy_result
structural_result
```

O campo `user_result` sempre aponta para `legacy_result`. Falha estrutural é
capturada em `errors`/`metrics` e não altera o resultado entregue. O modo
padrão continua `LEGACY_ONLY`; `STRUCTURAL_PREFERRED` e `STRUCTURAL_ONLY` não
foram ativados nesta fase.

`StructuralDiff` compara semanticamente `question_count`, `question_order`,
`printed_numbers`, `option_count`, `option_keys`, `image_count`,
`image_ownership`, `subject` e `answer_key_coverage`. Textos literais de
enunciado não entram no diff.

## Validação

Testes da Fase 4 cobrem sequência ambígua, lacuna Q12, duplicidade, mismatch
de gabarito, overlap impossível, AST cross-page, source trace, renderer,
contexto compartilhado, `LEGACY_ONLY`, `STRUCTURAL_SHADOW`, falha estrutural
isolada e diff semântico.

Também foi executada a prova real `pdfs/56_1788095849.pdf` com o gabarito
`pdfs/56_gab_1788095849.pdf`: 30 entradas de gabarito, 30 questões resolvidas,
30 nós AST e cobertura de gabarito de 100% no resultado estrutural shadow.

## Ponto de parada

Não foram implementados classificador ML supervisionado, Layout Families
históricas finais ou rollout global `STRUCTURAL_PREFERRED`.
