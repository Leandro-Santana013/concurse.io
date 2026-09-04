# concurse.io Domain Context

Domínio de ingestão, estruturação, simulação e avaliação de provas de concursos públicos e vestibulares a partir de documentos PDF e gabaritos oficiais.

## Termos Canônicos

**Caderno de Questões**:
O documento oficial de prova contendo enunciados, alternativas, textos de apoio e imagens associadas.
_Evitar_: Apostila, simulado bruto, folha de perguntas

**Questão**:
A unidade atômica de avaliação, composta por enunciado, alternativas estruturadas (A..E ou Certo/Errado), resposta correta e metadados como disciplina.
_Evitar_: Item de prova, pergunta, teste

**Número Canônico**:
O identificador numérico oficial atribuído pela banca examinadora impresso no cabeçalho da questão (ex: 1 a N).
_Evitar_: Posição física, índice relativo, linha

**Topologia de Layout (N-Order vs Z-Order)**:
O padrão geométrico de leitura da diagramação da prova: N-Order indica leitura vertical estrita por colunas (coluna esquerda completa, depois coluna direita); Z-Order indica leitura horizontal alternada (linha a linha cruzando as colunas).
_Evitar_: Ordem arbitrária, leitura cega

**Herança Topológica de Caderno**:
A propagação da topologia de leitura predominante (Z-order ou N-order) inferida a nível de documento para páginas ambíguas ou com questão única.
_Evitar_: Heurística pontual por página isolada

**Identificação Imutável de Questão**:
O uso do ID numérico de banco de dados (`question.id`) como chave de integridade para submissões, estados e tentativas no simulador, desacoplado do rótulo textual `numero_questao`.
_Evitar_: Indexação volátil por posição no array, dependência estrita de string de número

**Cadeia de Encadeamento (Question Chain)**:
A sequência ordenada de questões reconstruída pelo algoritmo de programação dinâmica que preserva a integridade lógica da prova contra falsos positivos numéricos e suporta transições por matéria. Sua posição (0-based) é materializada em `question_index` na extração; o async worker a usa como âncora de ordenação e reatribui o Número Canônico a partir dela quando os rótulos apresentam duplicatas ou não numéricos (lacunas isoladas não disparam renumeração).
_Evitar_: Lista desordenada, conjunto avulso

**Texto de Apoio Compartilhado**:
Trecho textual ou motivador (ex: textos literários, leis, tabelas) que serve de base para a resolução de um intervalo explícito de questões contíguas.
_Evitar_: Enunciado global, introdução
