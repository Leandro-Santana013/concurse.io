# Migração dos fluxos Android

## Arquitetura

O hard switch segue a decisão final do chat
`01a0c825-942f-7270-a0c4-3fbd1f266319`: processamento e OCR no aplicativo,
Supabase como fonte de identidade, biblioteca, provas, questões e tentativas,
e arquivos de prova, gabarito e imagens no Oracle. O SQLite do Android guarda
somente a fila e os dados de trabalho da extração.

A revisão Android atual é `0.1.7/code8`, preparada no worktree `p2p-desktop`,
branch `codex/concurse-app`. Ela corrige a inicialização do motor, a busca,
a extração de gabarito e a navegação. O usuário informou ter substituído a
função `app-gateway` no painel Supabase; isso ainda não foi confirmado por
uma verificação remota autenticada. O Redmi 14C está conectado por ADB para
validar esta revisão. A 0.1.6/code7 ainda não iniciava o motor por causa da
localização de `libmupdfcpp.so`, conforme o
[diagnóstico da busca](mobile-search-0.1.7-validation.md). O Android permanece beta e a
migração não deve ser considerada operacionalmente concluída.

## Implementação e evidências

| Fluxo | Alteração | Verificação atual |
| --- | --- | --- |
| Inicialização | Mantém a remoção de `plugins.opener.open` e a configuração do OpenSSL. Em 0.1.7, preserva a pasta original das bibliotecas sem SONAME e a localização das extensões Python para que PyMuPDF e Shapely carreguem no Android. | A falha de `libmupdfcpp.so` foi capturada por USB na 0.1.6. Auditoria e bootstrap passaram; o teste release no Redmi confirmou `/health` 200, PDF nativo e OCR real. |
| Login | Preserva o carrossel inicial, a verificação do serviço Auth e o retorno Google por `concurse://oauth/callback`. A identidade usada pela biblioteca vem do serviço central. Falhas de rede/serviço retornam 503, sem indicar sessão expirada. | Testes distinguem token inválido de indisponibilidade, permitem nova tentativa e verificam que o diagnóstico não registra credenciais. HTTPS do serviço Auth respondeu no Redmi; ainda falta concluir a busca com a sessão do usuário. |
| Busca e pesquisa | Usa o motor embarcado, registra resultados públicos no catálogo central e reutiliza provas extraídas. Reconhece `Fiscal de Postura IDCAP`, normaliza `idecap` para IDCAP e compara cargo, cidade, ano e banca. O fallback pode localizar a cópia pública oficial correspondente, sem contornar CAPTCHA. | O teste release no Redmi executou o crawler real: `Fiscal de Postura idecap` encontrou o caderno de Ibirataia em 4,85 s. O download e a extração passaram. A busca pela interface e a reutilização remota autenticada permanecem pendentes. |
| PDF, link e OCR | Empacota Python, FastAPI, PyMuPDF, NumPy, OpenCV, ONNX Runtime e RapidOCR. Executa o mesmo worker de provas do desktop, em uma fila de processamento por vez. | No Redmi, o teste release leu um PDF, executou RapidOCR sobre sua imagem e baixou/extraiu o caderno real IDCAP: 50 questões com quatro alternativas e 50 gabaritos, incluindo Q1 D e Q49 B. A ingestão na biblioteca central pelo aparelho permanece pendente. |
| Gabarito e alternativas | Prioriza as respostas explícitas da prova matriz antes das listas genéricas de letras. Preserva alternativas de associação e o gabarito entre páginas. O cache foi atualizado para `legacy-parse-cache-v12-idcap-embedded-answers`. | Nos dois caminhos, as 50 respostas coincidiram com a prova matriz oficial. Q1 é D; Q49 é B e mantém as quatro permutações completas. As regressões cobrem os erros identificados. |
| Progresso e recuperação | Consulta autenticada substitui SSE sem Bearer. A fila retoma trabalhos interrompidos; a confirmação de publicação remove o trabalho concluído da lista ativa. | Testes do acompanhamento e da passagem do ID de trabalho para o ID central passaram. |
| Publicação da prova | Envia PDF, gabarito e imagens ao Oracle, publica as questões no Supabase e aprova somente após persistência. Repetições e envio concorrente de prova pública reutilizam o mesmo registro. | Testes cobrem persistência, repetição, isolamento de uploads privados, reutilização entre contas, falha parcial e concorrência. O usuário informou ter substituído a função; a confirmação autenticada da publicação e leitura remota permanece pendente. |
| Biblioteca | Sempre lê os vínculos e os dados centrais; atualiza a lista quando uma extração é publicada. | Testes da biblioteca passaram. Validação autenticada da nova função e do APK permanece pendente. |
| Respostas, erros, simulados e progresso de estudo | Corrige por ID de questão, preserva questões anuladas, calcula matérias e estatísticas de tentativas reais e usa as questões da biblioteca nos simulados. | Testes de correção, simulados, navegação e estatísticas passaram. Verificação remota pendente. |
| Perfil e ranking | Usa metadados do Supabase Auth quando os campos legados estão vazios ou criptografados. Exibe participantes com tentativas reais. | Testes de apresentação de identidade passaram; o resultado da função substituída pelo usuário ainda precisa de confirmação autenticada. |
| Navegação e aparência | O topo compacto A, aprovado pelo usuário, respeita as áreas do sistema por insets nativos do Android. Cinco destinos permanecem em uma linha: Início, Biblioteca, Buscar, Progresso e Perfil. O menu complementar contém Caderno de erros, Ranking e Importar prova. O ícone C com check tem duas variantes para os 12 temas. | Os testes de navegador verificam layout responsivo, menu complementar, foco, Escape e navegação. O teste no Redmi confirmou padding nas quatro bordas igual aos insets do sistema. A inspeção visual aguarda o desbloqueio do aparelho. |

## Prova real de referência

O caderno [IDCAP 2024 — Fiscal de Obras, Posturas e Meio Ambiente de
Ibirataia/BA](https://arquivos.qconcursos.com/prova/arquivo_prova/131135/idcap-2024-prefeitura-de-ibirataia-ba-fiscal-de-obras-posturas-e-meio-ambiente-prova.pdf)
foi comparado com a [prova matriz publicada pelo
IDCAP](https://anexos.cdn.selecao.net.br/uploads/227/concursos/155/anexos/tRaWy5eLSx1XAx1SsL7AT1n7QmZ6lDeYUhh3Qfe4.pdf),
listada no [concurso 001/2024](https://idcap.selecao.net.br/informacoes/155/).
As duas URLs públicas responderam com o mesmo PDF: 12 páginas, 341.766 bytes,
50 questões e SHA-256
`34891104503e03d489554f35a3e36acf9405e4f8744b7952ddccea438e30b7e0`.
A prova matriz contém as 50 marcações explícitas de resposta correta.

Não foi usado um arquivo de gabarito separado sem confirmar seu conteúdo.
O endereço de gabarito derivado do Qconcursos devolveu o mesmo caderno; o
gabarito individual no portal da banca exigia login. A conferência utilizou
as respostas da prova matriz pública, incluindo Q1 D, Q48 C, Q49 B e Q50 A.
O parser completo preservou as alternativas de Q49: A `C, B, A.`, B `A, B, C.`,
C `B, A, C.` e D `A, C, B.`.

## Ranking

A consulta somente de leitura à base confirmou que a entrada genérica
`Concurseiro`, com 62,5%, corresponde à conta real do usuário: uma tentativa
com 25 acertos em 40 questões. Não foi encontrada uma conta de demonstração
`Concurseiro App` ou `Dev` para excluir. Nenhuma conta real foi removida.

## Artefatos desta revisão

- `downloads/concurse-mobile-aarch64-release-v0.1.7-code8-16k.apk`:
  revisão beta ARM64, Android mínimo 24, alvo 36, versionCode 8;
  158.589.296 bytes, SHA-256
  `3add80ff7fc57e5e82c6487191cf74a368ff8e02427ab570435b2c503549c859`.
- O [inventário de downloads](../downloads/README.md) e
  [`SHA256SUMS.txt`](../downloads/SHA256SUMS.txt) registram os arquivos de
  distribuição e seus hashes. Assinaturas v2/v3 e certificado de atualização
  foram verificados. O APK passou em `zipalign -c -P 16 4`; a auditoria
  confirmou 124 ELFs ARM64 alinhados a 16 KB e 102 arquivos permitidos do
  motor, sem banco de dados ou chave privada no pacote. A nova auditoria
  também verifica a localização das dependências nativas sem SONAME.
- `downloads/app-gateway-mobile-hard-switch.ts`: pacote único, gerado dos
  cinco arquivos de `supabase/functions/app-gateway`, para publicação pelo
  editor do painel. Os arquivos originais continuam disponíveis para manutenção.
- `desktop/engine/android/EngineSmokeTest.java`: teste Android que inicia a
  aplicação, verifica a API do motor, AES-GCM, sessão assinada, backend de busca,
  margens das barras do sistema, texto de PDF e OCR. Foi compilado contra a
  variante release code8 e assinado com o mesmo certificado do APK principal.
  A execução no Redmi passou: `OK (1 test)`. O registro do diagnóstico
  separa esses testes da busca autenticada e publicação central pendentes.
- `desktop/engine/android/audit_apk.py`: verifica também os ELFs dentro dos
  arquivos Python e restringe os arquivos do motor à lista de fontes permitida.

Os instaladores Windows `0.1.2` não foram recompilados nesta revisão. As
alterações nos componentes e ícones compartilhados estão nas fontes e só
alteram esses binários após um novo build.

## Histórico do APK 0.1.5/code6

O APK `0.1.5/code6` foi gerado e assinado em 04/10/2026 no mesmo worktree e
publicado no GitHub no commit `73f8cee`.

- `downloads/concurse-mobile-aarch64-release-v0.1.5-code6-16k.apk`:
  158.568.816 bytes; SHA-256
  `96ef599748e93528ffe0974ec0d379dbf940def77eb45c750d43fef6646cb663`.
- A assinatura coincide com a chave das versões anteriores, permitindo
  atualização com preservação dos dados. O alinhamento do APK assinado
  também passou na verificação do Android SDK para páginas de 16 KB.
- A auditoria de code6 encontrou 123 ELFs ARM64 com alinhamento para páginas
  de 16 KB, incluindo as bibliotecas dentro dos arquivos Python, e não
  encontrou banco de dados ou chave privada no pacote.

Essa auditoria de empacotamento não provava que o motor iniciava no Redmi.
A falha do OpenSSL foi identificada depois na captura do aparelho e motivou
a correção incluída na revisão code7.

## Verificações e pendências

Na revisão code8 passaram 23 testes de autenticação, bootstrap e organização
das dependências nativas, cinco da integração mobile e o teste instrumental
release no Redmi. O motor local iniciou, o PDF nativo e o OCR real passaram,
as margens do sistema foram conferidas e o serviço Auth respondeu via HTTPS.
O crawler público encontrou a prova real de Ibirataia, baixou seu PDF e
conferiu 50 questões e 50 respostas no próprio Redmi.
O diagnóstico registra a captura e as pendências da sessão autenticada.

Na revisão code7, o backend passou em 29 testes, com um ignorado. As
verificações do pipeline e das regressões passaram em 52 testes. Passaram
também 20 testes frontend e seis testes de navegador. A prova real foi
conferida nos caminhos Rust e Python, além das regressões com os casos de
gabarito e alternativas. Os testes de navegador incluem inspeção visual do
layout responsivo; não substituem a execução do APK no Android.

No histórico de code6, 53 testes frontend passaram em dois grupos: 48 no
pool `threads` e cinco de busca no pool `vmThreads`. Não foi uma execução
integral bem-sucedida em um único pool. O teste Android foi compilado e
assinado naquela revisão, mas não executado no aparelho.

Na tentativa anterior à reconexão, a instalação de code7 retornou
`device not found`. Depois, a captura USB confirmou code7 instalado no Redmi,
com falha de `libmupdfcpp.so`. Code8 foi instalado por atualização e iniciou
o motor. Não houve desinstalação ou limpeza de dados.

A consulta somente de leitura ao PostgreSQL central não conseguiu concluir
uma conexão com a configuração existente. Nenhuma escrita foi executada.
Não foi possível conferir se já existe um registro de Ibirataia e se suas
respostas e alternativas correspondem à matriz corrigida; a reutilização
desse registro remoto deve ser verificada com a sessão do aparelho.

A automação do painel foi bloqueada anteriormente por uma regra de acesso.
Depois disso, o usuário informou ter substituído a função manualmente no
Supabase. O estado atual da pendência é a validação remota autenticada das
novas rotas, não uma nova solicitação de autorização para publicar.

Com o motor e PDF/OCR verificados no Redmi, concluir login, busca,
ingestão por link e arquivo, gabarito, publicação no Oracle e
Supabase, biblioteca, resolução, erros, simulados, estatísticas, ranking e
navegação, incluindo as áreas do sistema e o menu complementar. Confirmar
também os fluxos remotos com uma sessão autenticada. Não usar apenas
compilação, testes de navegador ou contagem de questões como prova de que
todos os fluxos foram concluídos.
