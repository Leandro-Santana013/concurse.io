# ADR 0002: Herança Topológica Global, Paridade Rust/Python e Leitura Polimórfica de Tentativas

## Contexto
Após a definição do ADR 0001 (Two-Pass Header Topology e desacoplamento por `question.id`), restavam decisões de fronteira quanto à inferência de páginas com poucas questões, integridade do histórico legado de tentativas no banco de dados e sincronia entre a engine nativa em Rust e o fallback em Python.

## Decisão
1. **Herança Topológica de Caderno**: Páginas com apenas uma questão ou com layout ambíguo herdam a topologia predominante (Z-order vs N-order) calculada a partir das demais páginas do caderno que possuem duas ou mais questões identificadas.
2. **Leitura Polimórfica de Tentativas com Fallback**: O cálculo de estatísticas e auditoria de tentativas busca primeiro a chave correspondente a `question_id` (novo formato primário imutável). Caso ausente, utiliza `numero_questao` ou o índice ordinal `idx` como fallback para preservar 100% de compatibilidade com tentativas legadas gravadas anteriormente.
3. **Paridade Estrita Rust Engine e Python Bridge**: O particionamento de monotonicidade do DP Chain com suporte a reinício de contagem em 1 após banners de matérias é implementado em paridade idêntica tanto no motor compilado (`rust_engine/src/dp_chain.rs`) quanto no pipeline de fallback (`services/pdf_pipeline/hybrid_extractor.py`).

## Consequências
- Zero páginas orfãs ou com leitura truncada por falta de amostragem local de cabeçalhos.
- Transição segura sem necessidade de migrações destrutivas no banco de dados.
- Alta performance em produção nativa combinada com resiliência completa do ambiente de desenvolvimento.
