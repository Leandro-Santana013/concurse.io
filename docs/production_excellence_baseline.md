# Baseline de excelência para Production

Data do baseline: 2026-09-09

## Checkout de referência

- Branch: `codex-production-excellence`
- Base: `origin/Production`
- Commit: `ddcb64ee2b478a05ba26405d8ee279ff5ad904e6`
- Worktree original preservado em `C:\Users\Santana\Documents\GitHub\concurse.io`

## Testes executados

Comando:

```powershell
C:\Users\Santana\Documents\GitHub\concurse.io\venv\Scripts\python.exe -m pytest `
  tests/test_gabarito_code_matching.py `
  tests/test_gabarito_multifactor_matching.py `
  tests/test_gabarito_aggregate_blocks.py `
  tests/test_reprocess_pdf_artifacts.py -q
```

Resultado: `21 passed in 3.20s`.

Esse conjunto cobre matching por código, fatores de identidade, blocos
agregados e reprocessamento/artefatos. Ele é o gate mínimo antes de qualquer
porte do pipeline estrutural.

## Ambiente observado

- Python `3.10.6`
- FastAPI `0.141.1`
- Uvicorn `0.52.4`
- SQLAlchemy `2.0.51`
- PyMuPDF `1.28.0`
- RapidOCR `1.4.4`
- NumPy `2.2.6`
- OpenCV `5.0.0.93`
- Pytest `9.1.1`
- `scikit-learn` e `joblib`: ausentes no ambiente baseline

As dependências do pipeline estrutural não serão ativadas globalmente sem
pinagem, teste de instalação limpa e validação de compatibilidade com Python
3.10.

## Delta da Nick-Production

`origin/Nick-Production` aponta para `0f5e752721f7516fe7f42e82449a4d18184b617c`
e está um commit à frente da Production. O delta contém 105 arquivos,
98.360 adições e 14 remoções.

O conteúdo mistura código estrutural, artefatos de treinamento, modelos
binários, snapshots, corpus e testes. O benchmark versionado reporta:

- detecção de questões: `1.0` precision e recall;
- ordenação: `0.84756`;
- extração de alternativas: `0.52857`;
- ownership de imagens: `0.0`;
- sucesso completo: `0.375`;
- generalização holdout: `0.5`.

Conclusão: a branch é fonte de componentes experimentais, não um merge pronto
para Production.

## Inventário do worktree original

O checkout original tinha alterações locais em ingestão assíncrona, UI,
rotas, schemas, parser de gabarito, extração PDF, mídia, busca e testes, além
dos arquivos não rastreados abaixo:

- `frontend/src/test/direct-ingest-modal.test.tsx`
- `scripts/recreate_database.sql`
- `services/pdf_pipeline/media/scan_pipeline.py`
- `tmp/`

Essas alterações não foram copiadas nem sobrescritas nesta branch.

## Gate atual

O primeiro gate de implementação é o caso IBAM/Uberaba 2016: somente o bloco
`Códigos: 133 a 139` pode ser aceito quando a prova traz essa faixa. O PDF
persistido ainda não está disponível no checkout; a URL retornou uma página
HTML protegida por Turnstile. A regressão sintética de posição de páginas será
mantida até que o artefato real seja fornecido/exportado de forma autorizada.
