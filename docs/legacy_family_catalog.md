# Cadastro de famílias dos parsers legados

O cadastro inicial está em `data/legacy_family_catalog.json`. Ele contém as
quatro famílias de `BancaFamily`, os aliases de `BANCA_MAPPING`, os padrões
de `PROFILES` e as dez regras de `LEGACY_RULES`, com referências de origem.

| Identificador estável | Família |
| --- | --- |
| `legacy-standard-academic` | Acadêmica padrão |
| `legacy-true-false-item` | Itens de certo ou errado |
| `legacy-municipal-prefixed` | Municipal com prefixos |
| `legacy-universal` | Universal (fallback) |

Aliases são normalizados removendo acentos e pontuação e convertendo para
maiúsculas. A associação entre regras e famílias exige igualdade do alias
normalizado. Por exemplo, a regra Dataprev referencia a família de itens por
seu sinal QUADRIX; isso registra uma associação histórica, sem afirmar que
toda prova Dataprev ou Quadrix seja de certo/errado. Sinais sem correspondência
não recebem família inventada. Os aliases originais também são preservados.

Todos os registros começam como `imported_from_legacy`, com
`pending_pdf_validation` e nenhuma prova marcada como validada. Os limites de
confiança são valores do parser original, não métricas de acurácia medidas.
Quantidade de colunas e ordem de leitura não são inferidas pelo nome da banca.

Este catálogo pode ser consumido em Python por
`services.pdf_pipeline.legacy.family_catalog.build_legacy_family_catalog`.
Para regenerar o JSON de forma determinística:

```powershell
python scripts/register_legacy_families.py
```

`schema_version` identifica o formato; `content_sha256` identifica a revisão do
conteúdo. O JSON é uma exportação gerada: não adicionar validações manualmente
nele, pois a regeneração as sobrescreve. A próxima etapa é registrar evidências
de PDFs em um cadastro separado, vinculado à família e à revisão validada.

O cadastro não altera a seleção dos parsers, não cadastra provas no banco e
não é um modelo `LayoutFamilyModel`. As famílias visuais aprendidas na fase 5
continuam independentes. Não há tela administrativa para este catálogo ainda.
