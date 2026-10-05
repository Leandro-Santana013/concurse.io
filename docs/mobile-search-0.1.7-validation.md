# Diagnóstico da busca Android — 04/10/2026

## Falha reproduzida no Redmi 14C

O aparelho estava com `0.1.6/code7`. A tela de busca mostrava:
“O processamento no dispositivo ainda não iniciou. Feche e abra o aplicativo
para tentar novamente.” O endpoint local `/health` não respondia.

Uma inicialização nova capturada por USB identificou o erro:

```text
ConcurseEngine: Processing engine failed to start
ImportError: dlopen failed: library "libmupdfcpp.so" not found
needed by .../requirements/pymupdf/_extra.so
```

O erro ocorre durante `fitz` → `services.gabarito` → `fastapi_app`, antes de
o servidor de processamento abrir sua porta. A biblioteca existe no APK,
mas foi movida para `chaquopy/lib`. Ela não possui `DT_SONAME`, enquanto as
extensões do PyMuPDF usam `DT_RUNPATH=$ORIGIN`. O alinhamento de 16 KB estava
correto; a auditoria anterior não verificava essa relação entre dependências.

## Correção instalada em 0.1.7/code8

- Preserva a localização original das bibliotecas sem SONAME, permitindo
  que o carregador do Android encontre as dependências pelo `$ORIGIN`.
- Distingue extensões Python chamadas `lib` das bibliotecas compartilhadas,
  preservando a extensão `shapely.lib` na pasta do pacote.
- A auditoria do APK rejeita dependências sem SONAME que foram movidas
  para fora da pasta necessária. O APK 0.1.6 reproduz essa reprovação.
- Conserva `androidx.tracing` no build release para executar o teste
  instrumental. A primeira execução desse teste falhou na infraestrutura,
  antes de testar o motor, porque R8 havia removido `Trace`.
- Falhas de rede, limite de chamadas e indisponibilidade do Auth retornam
  503, enquanto tokens rejeitados retornam 401. A interface permite repetir
  a busca sem apresentar a conta como expirada por falha de conexão. O log
  inclui somente tipos de exceção e números de erro, sem URLs ou tokens.

As mudanças incluem empacotamento Android e tratamento da indisponibilidade
da validação local de identidade. Os instaladores Windows não foram
recompilados; autenticação e biblioteca continuam usando os serviços centrais.

## Validação

O APK foi assinado, auditado e instalado por atualização no Redmi, sem
desinstalação ou limpeza dos dados. Metadados conferidos: versão 0.1.7,
versionCode 8, 158.589.296 bytes, 124 ELFs ARM64 alinhados a 16 KB e SHA-256
`3add80ff7fc57e5e82c6487191cf74a368ff8e02427ab570435b2c503549c859`.

Passaram os três testes de organização/auditoria das bibliotecas e o teste de
bootstrap (quatro testes). A primeira tentativa do bootstrap excedeu 60 s
durante a compilação concorrente; a repetição terminou com sucesso em 37 s.

O teste instrumental release passou no Redmi conectado: `OK (1 test)`.
Conferiu `/health` HTTP 200, as quatro margens nativas das barras do Android,
AES-GCM, sessão assinada, inicialização do backend de busca, texto de PDF
nativo e inferência real do RapidOCR sobre uma imagem. Também conferiu DNS
do Supabase e HTTPS do endpoint público `/auth/v1/health` com HTTP 200.

```text
CONCURSE_NETWORK_HTTP_STATUS: 200
CONCURSE_ANDROID_ENGINE_OK: API, AES-GCM, session, search backend, PDF text and OCR passed
```

A repetição do teste também executou o validador de identidade em uma thread
de trabalho, usando um token propositalmente inválido e sem consultar a sessão
do usuário. O Supabase respondeu com a rejeição esperada, confirmando que esse
caminho consegue fazer HTTPS. Marcador: `CONCURSE_NETWORK_WORKER_OK`.

Com `liveSearch=true`, o teste release executou o crawler público no Redmi.
A consulta `Fiscal de Postura idecap` encontrou a prova de Ibirataia em 5,82 s
e, na repetição, em 4,85 s. Baixou o PDF oficial, conferiu seu SHA-256 e
verificou 50 questões, quatro alternativas por questão e 50 respostas,
incluindo Q1 D e Q49 B. Resultado final: `OK (1 test)` em 23,369 s.

```text
CONCURSE_LIVE_SEARCH_RESULTS: 1, 4.85s
CONCURSE_LIVE_IDCAP_OK: public search, PDF download, 50 questions, 50 answers, Q1 D and Q49 B passed
```

A primeira execução já havia extraído 50 questões, mas a conferência usava
os campos da API (`options`/`correct_answer`) em vez dos campos do extrator
(`opcoes`/`resposta`). Somente o teste foi corrigido antes da repetição.

Esses testes não comprovam a sessão autenticada: na execução normal, com a
tela bloqueada, `/auth/supabase/exchange` registrou `ConnectionError` →
`NameResolutionError` → `gaierror[errno=7]`. O teste pela rota local, com um
token inválido, alcançou Auth e retornou a rejeição 401 esperada. Ainda não
foi determinada a causa da diferença de DNS entre essas execuções.
A inspeção da tela aguarda o desbloqueio pelo usuário.

A busca pela interface com a sessão do usuário, o salvamento na biblioteca
e a publicação central da extração ainda precisam ser verificados. O teste
público do motor não autenticou uma conta nem publicou um registro remoto.
