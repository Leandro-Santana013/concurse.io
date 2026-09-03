# ADR 0001: Ordenação Canônica de Questões por Topologia Espacial e Identificação Imutável

## Contexto
O concurse.io processa cadernos de provas em PDF diagramados em formatos heterogêneos por dezenas de bancas examinadoras. Questões frequentemente vinham com ordem invertida ou com itens descartados quando diagramadas em duas colunas de leitura horizontal (Z-order) ou quando a numeração reiniciava por disciplina. Além disso, o frontend e backend dessincronizavam na submissão de respostas quando `numero_questao` vinha ausente ou não puramente numérico.

## Decisão
1. **Topologia Espacial Two-Pass**: Antes de concatenar blocos de texto de uma página de 2 colunas, o pipeline mapeia as posições espaciais dos cabeçalhos $(x, y)$. Se os números de questões progredirem horizontalmente ($Q_1$ à esquerda, $Q_2$ à direita na mesma altura), a página é lida em Z-order (linha a linha); se progredirem verticalmente ($Q_1$ e $Q_2$ à esquerda), é lida em N-order (coluna por coluna).
2. **Autoridade do Número Canônico**: A numeração explícita da banca ($1 \dots N$) prevalece sobre a ordem física cega de blocos brutos do PDF.
3. **DP Chain com Particionamento por Disciplina**: O algoritmo nativo em Rust (`dp_chain.rs`) e seu fallback em Python passam a aceitar reinício de cadeia monotônica a partir do número 1 caso haja um banner de disciplina intermediário.
4. **Desacoplamento de Estado por `question_id`**: A persistência de tentativas e respostas selecionadas no simulador passa a usar o ID primário imutável da questão (`question.id`), mantendo `numero_questao` estritamente como rótulo de exibição visual.

## Consequências
- Fim de saltos espúrios e textos de enunciados comilões no fatiamento da questão subsequente.
- Preservação de 100% de coerência no cruzamento entre o gabarito oficial da banca e as questões da prova.
- Retrocompatibilidade no cálculo de tentativas anteriores mantida via conversão defensiva no backend.
