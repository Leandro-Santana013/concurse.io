# 🏛️ Arquitetura Completa do concurse.io: Do Treinamento ao Frontend

Este documento explica, **arquivo por arquivo**, todas as etapas do sistema: desde o treinamento offline de padrões e compilação do motor em **Rust**, passando pelo download, extração geométrica de PDFs, inserção no banco de dados, até a disponibilização na API **FastAPI** e renderização interativa no frontend **React**.

---

## 🗺️ Mapa Visual do Fluxo Ponta a Ponta

```mermaid
flowchart TD
    subgraph ETAPA 1 [1. Treinamento & Compilação Rust]
        Corpus[training_corpus/] --> Opt[scripts/optimize_regex.py]
        Opt --> Inject[scripts/inject_trained_pipeline.py]
        Inject --> RustPatterns[rust_engine/src/patterns.rs]
        Inject --> RustDP[rust_engine/src/dp_chain.rs]
        Inject --> RustLib[rust_engine/src/lib.rs]
        RustLib --> RustWheel[concurse_core (.pyd/.so)]
    end

    subgraph ETAPA 2 [2. Download & Extração Híbrida]
        URL[URL da Prova / Upload] --> Download[scripts/extract_external_pdf_to_md.py]
        Download --> Hybrid[services/pdf_pipeline/hybrid_extractor.py]
        Hybrid --> Layout[services/pdf_pipeline/layout_detector.py]
        Hybrid --> RustBridge[services/pdf_pipeline/rust_bridge.py]
        RustBridge --> RustWheel
        Hybrid --> Crop[services/pdf_pipeline/diagram_cropper.py]
        Hybrid --> Formula[services/pdf_pipeline/formula_formatter.py]
        Hybrid --> Subject[services/pdf_pipeline/subject_classifier.py]
        Hybrid --> Gabarito[services/gabarito_service.py]
        Hybrid --> Cleaner[services/html_exam_parser.py]
    end

    subgraph ETAPA 3 [3. Banco de Dados & Backend]
        Hybrid --> InsertDB[scripts/insert_exam_to_db.py]
        InsertDB --> Models[models/database.py]
        Models --> SQLite[(concurse.db / PostgreSQL)]
        SQLite --> Backend[fastapi_app.py]
    end

    subgraph ETAPA 4 [4. Interface do Usuário]
        Backend --> APIService[frontend/src/services/api.js]
        APIService --> AppReact[frontend/src/App.jsx]
        AppReact --> Simulator[frontend/src/components/ExamSimulator.jsx]
    end
```

---

## 📂 ETAPA 1: Treinamento Offline e Motor Nativo em Rust

### 1. [`training_corpus/`](file:///c:/Users/Santana/Documents/GitHub/concurse/training_corpus/)
- **O que é:** Diretório contendo PDFs de provas reais de diversas bancas (IDCAP, CEBRASPE, VUNESP, FGV, IBAM) e anotações *ground truth* (gabaritos oficiais, quantidade exata de questões e enunciados).
- **Papel no fluxo:** Serve como base de teste e validação estatística para os algoritmos de otimização.

### 2. [`scripts/optimize_regex.py`](file:///c:/Users/Santana/Documents/GitHub/concurse/scripts/optimize_regex.py)
- **O que é:** Otimizador genético e sintetizador de expressões regulares.
- **Papel no fluxo:** Executa mutações em padrões de Regex, testando-os contra o `training_corpus/` para encontrar a combinação de expressões com **maior F1-Score (100%)**, eliminando falsos positivos e falsos negativos.

### 3. [`scripts/inject_trained_pipeline.py`](file:///c:/Users/Santana/Documents/GitHub/concurse/scripts/inject_trained_pipeline.py)
- **O que é:** O orquestrador de build e injeção de padrões.
- **Papel no fluxo:** Pega as expressões regulares vencedoras, atualiza o código-fonte em Python e em Rust (`rust_engine/src/patterns.rs`), e dispara a compilação da extensão nativa via `maturin build --release`.

### 4. [`rust_engine/Cargo.toml`](file:///c:/Users/Santana/Documents/GitHub/concurse/rust_engine/Cargo.toml)
- **O que é:** Manifesto do pacote Rust (`concurse_core`).
- **Papel no fluxo:** Configura a crate com tipo `cdylib` e declara as dependências nativas: `pyo3` (para interoperabilidade com Python), `regex` (motor de busca em tempo linear) e `once_cell` (compilação *lazy* de padrões).

### 5. [`rust_engine/src/patterns.rs`](file:///c:/Users/Santana/Documents/GitHub/concurse/rust_engine/src/patterns.rs)
- **O que é:** Repositório de expressões regulares pré-compiladas em Rust.
- **Papel no fluxo:** Contém o `HEADER_REGEX` (detecção de início de questão), `OPTION_PRIMARY_REGEX` (detecção de alternativas `A..E`), `OPTION_NEWLINE_REGEX` e `CONTEXT_TEXT_BANNER_REGEX` (textos de apoio). Executa em autômato finito determinístico (DFA), garantindo imunidade a travamentos (*Catastrophic Backtracking*).

### 6. [`rust_engine/src/dp_chain.rs`](file:///c:/Users/Santana/Documents/GitHub/concurse/rust_engine/src/dp_chain.rs)
- **O que é:** Algoritmo de Programação Dinâmica de Encadeamento Ótimo.
- **Papel no fluxo:** Recebe todos os números de questão encontrados no texto e descobre a sequência contínua verdadeira ($1 \to 2 \to 3 \to \dots \to N$) usando pontuação com janela deslizante, ignorando números espúrios soltos no meio de enunciados ou leis.

### 7. [`rust_engine/src/lib.rs`](file:///c:/Users/Santana/Documents/GitHub/concurse/rust_engine/src/lib.rs)
- **O que é:** Módulo PyO3 principal da extensão nativa.
- **Papel no fluxo:** Expõe as funções `scan_question_headers`, `scan_context_banners` e `parse_options_fast` diretamente para o interpretador Python como a biblioteca nativa `concurse_core`.

---

## 📂 ETAPA 2: Extração Híbrida e Normalização de PDFs

### 8. [`services/pdf_pipeline/rust_bridge.py`](file:///c:/Users/Santana/Documents/GitHub/concurse/services/pdf_pipeline/rust_bridge.py)
- **O que é:** Camada de adaptação e segurança Python $\leftrightarrow$ Rust.
- **Papel no fluxo:** Tenta carregar o módulo nativo `concurse_core`. Se compilado, delega a varredura ultra-rápida (executada em ~3ms) ao Rust. Caso o ambiente não possua o binário compilado, ativa transparentemente o fallback em Python puro sem quebrar a execução.

### 9. [`services/pdf_pipeline/layout_detector.py`](file:///c:/Users/Santana/Documents/GitHub/concurse/services/pdf_pipeline/layout_detector.py)
- **O que é:** Analisador geométrico de páginas e detector de layouts.
- **Papel no fluxo:**
  - Extrai blocos de texto mantendo a ordem correta de leitura (em colunas duplas ou triplas).
  - Remove marcas d'água, rodapés globais e cabeçalhos repetitivos de páginas.
  - Detecta "deadzones" de layout e extrai blocos de textos de apoio compartilhados (`extract_context_blocks`), vinculando quais questões pertencem àquele texto.

### 10. [`services/pdf_pipeline/diagram_cropper.py`](file:///c:/Users/Santana/Documents/GitHub/concurse/services/pdf_pipeline/diagram_cropper.py)
- **O que é:** Extrator e recortador automático de imagens.
- **Papel no fluxo:** Localiza coordenadas vetoriais e bitmaps de tirinhas, diagramas, figuras, gráficos e tabelas dentro das páginas do PDF. Recorta essas regiões em alta definição e salva os arquivos em `static/images/questions/`.

### 11. [`services/pdf_pipeline/formula_formatter.py`](file:///c:/Users/Santana/Documents/GitHub/concurse/services/pdf_pipeline/formula_formatter.py)
- **O que é:** Parser de fórmulas e notações científicas.
- **Papel no fluxo:** Identifica expoentes, frações, matrizes e equações em texto plano/Unicode e converte para sintaxe padrão **LaTeX** (`$x^2 + \frac{a}{b}$`), permitindo renderização perfeita no frontend.

### 12. [`services/pdf_pipeline/subject_classifier.py`](file:///c:/Users/Santana/Documents/GitHub/concurse/services/pdf_pipeline/subject_classifier.py)
- **O que é:** Classificador determinístico de matérias e disciplinas.
- **Papel no fluxo:** Mapeia mais de 50 disciplinas de concursos públicos (ex: *Língua Portuguesa*, *Direito Administrativo*, *Raciocínio Lógico-Matemático*), identificando a mudança de matéria ao longo do caderno de prova.

### 13. [`services/gabarito_service.py`](file:///c:/Users/Santana/Documents/GitHub/concurse/services/gabarito_service.py)
- **O que é:** Extrator e casador de gabaritos oficiais.
- **Papel no fluxo:** Localiza tabelas de gabarito embutidas no final da prova ou em documentos anexos, extraindo as respostas corretas (`A`, `B`, `C`, `D`, `E`, `Certo`, `Errado`, `Anulada`) e associando-as a cada questão.

### 14. [`services/html_exam_parser.py`](file:///c:/Users/Santana/Documents/GitHub/concurse/services/html_exam_parser.py)
- **O que é:** Higienizador de texto e resolvedor de ruídos.
- **Papel no fluxo:** Remove quebras de linha indevidas no meio de frases, corrige hifenização partida entre linhas e limpa artefatos de OCR.

### 15. [`services/pdf_pipeline/hybrid_extractor.py`](file:///c:/Users/Santana/Documents/GitHub/concurse/services/pdf_pipeline/hybrid_extractor.py)
- **O que é:** O cérebro maestro do pipeline.
- **Papel no fluxo:**
  1. Recebe o PDF e executa a análise de layout.
  2. Aciona o `rust_bridge` para varrer e encadear as questões.
  3. Trunca questões anteriores antes de banners de textos de apoio para evitar vazamentos.
  4. Injeta textos de apoio e propaga imagens para as questões compartilhadas.
  5. Desmembra enunciados, tabelas de associação (Coluna I e II) e alternativas `(A)..(E)`.
  6. Retorna a lista de dicionários estruturados de cada questão.

---

## 📂 ETAPA 3: Persistência no Banco e Servidor Backend

### 16. [`models/database.py`](file:///c:/Users/Santana/Documents/GitHub/concurse/models/database.py)
- **O que é:** Definição do esquema do banco de dados relacional via SQLAlchemy.
- **Tabelas principais:**
  - `User`: Dados de autenticação e perfil do usuário.
  - `Folder`: Pastas de organização (ex: *IDCAP*, *CEBRASPE*, *Simulados 2026*).
  - `Exam`: Metadados da prova (título, URL de origem, status, cobertura de gabarito).
  - `Question`: Conteúdo da questão (enunciado, opções em JSON, resposta correta, disciplina, imagens vinculadas em JSON, flag de LaTeX).
  - `ExamAttempt`: Histórico de execuções do simulado pelo aluno, tempo gasto, pontuação e respostas submetidas.

### 17. [`scripts/insert_exam_to_db.py`](file:///c:/Users/Santana/Documents/GitHub/concurse/scripts/insert_exam_to_db.py)
- **O que é:** Script de ingestão no banco de dados.
- **Papel no fluxo:** Chama o extrator híbrido no PDF, cria/atualiza o registro na tabela `exams` e persiste todas as questões na tabela `questions`, associando caminhos de imagens e gabaritos.

### 18. [`fastapi_app.py`](file:///c:/Users/Santana/Documents/GitHub/concurse/fastapi_app.py)
- **O que é:** Servidor Web RESTful em FastAPI com suporte a async e streaming.
- **Endpoints principais:**
  - `GET /api/folders`: Lista pastas e categorias de provas.
  - `GET /api/exams`: Lista todas as provas aprovadas e cadastradas.
  - `GET /api/exams/{id}`: Retorna a prova completa com todas as suas questões, imagens, textos de apoio e gabaritos para o simulador.
  - `POST /api/exams/upload`: Endpoint para upload de PDF e processamento instantâneo via pipeline híbrido.
  - `POST /api/attempts`: Salva a tentativa de simulado do usuário e computa o relatório estatístico de acertos por matéria.
  - `GET /static/images/questions/{filename}`: Serve as imagens e diagramas recortados.

---

## 📂 ETAPA 4: Apresentação no Frontend (SPA React + Vite)

### 19. [`frontend/src/services/api.js`](file:///c:/Users/Santana/Documents/GitHub/concurse/frontend/src/services/api.js)
- **O que é:** Cliente de comunicação HTTP.
- **Papel no fluxo:** Encapsula requisições para a API FastAPI com tratamento de erros, cache de requisições e headers de autenticação.

### 20. [`frontend/src/App.jsx`](file:///c:/Users/Santana/Documents/GitHub/concurse/frontend/src/App.jsx)
- **O que é:** Componente raiz e orquestrador de telas do frontend.
- **Papel no fluxo:** Gerencia navegação entre abas (*Biblioteca de Provas*, *Gerenciador de Pastas*, *Simulador de Questões*, *Dashboard de Desempenho*).

### 21. [`frontend/src/components/ExamView.jsx`](file:///c:/Users/Santana/Documents/GitHub/concurse/frontend/src/components/ExamView.jsx) (ou componentes de simulado)
- **O que é:** A interface interativa de resolução da prova.
- **Papel no fluxo:**
  - Renderiza o enunciado com formatação rica e equações matemáticas formatadas via KaTeX.
  - Apresenta as imagens recortadas em tamanho adaptável com zoom ao clicar.
  - Renderiza as alternativas `(A)`, `(B)`, `(C)`, `(D)`, `(E)` como botões de seleção únicos.
  - Exibe timer de prova, controle de questões marcadas para revisão e cálculo instantâneo de desempenho ao finalizar o teste.

---

## 🔄 Resumo do Ciclo de Vida de uma Prova

| Fase | Ação Principal | Tecnologias Envolvidas |
| :--- | :--- | :--- |
| **1. Treino** | Otimização genética de expressões regulares contra corpus | Python (`scripts/optimize_regex.py`) |
| **2. Compilação** | Compilação dos padrões e DP Chain em código nativo | Rust + PyO3 (`rust_engine/`) |
| **3. Leitura** | Download do PDF, fatiamento geométrico e recorte de figuras | PyMuPDF + Rust DFA (`services/pdf_pipeline/`) |
| **4. Normalização** | Formatação de fórmulas LaTeX, textos de apoio e gabarito | Python (`formula_formatter.py`, `layout_detector.py`) |
| **5. Persistência** | Gravação transacional da prova e questões estruturadas | SQLAlchemy + SQLite / Postgres (`models/database.py`) |
| **6. API** | Disponibilização dos endpoints JSON de alta performance | FastAPI (`fastapi_app.py`) |
| **7. Exibição** | Resolução interativa no navegador com timer e estatísticas | React + Vite + TailwindCSS (`frontend/`) |
