# Migração dos fluxos Android

## Arquitetura

O hard switch segue a decisão final do chat
`01a0c825-942f-7270-a0c4-3fbd1f266319`: processamento e OCR no aplicativo,
Supabase como fonte de identidade, biblioteca, provas, questões e tentativas,
e arquivos de prova, gabarito e imagens no Oracle. O SQLite do Android guarda
somente a fila e os dados de trabalho da extração.

O APK `0.1.5/code6` foi gerado e assinado no worktree `p2p-desktop`, branch
`codex/concurse-app`, em 04/10/2026, e publicado no GitHub no commit `73f8cee`.
A publicação operacional da função no Supabase e o teste no aparelho continuam
pendentes de verificação; não considerar a migração operacionalmente concluída.

## Implementação e evidências

| Fluxo | Alteração | Verificação atual |
| --- | --- | --- |
| Inicialização | Mantém a remoção da configuração inválida `plugins.opener.open` que abortava a versão `0.1.2/code3`. Falhas do motor são registradas sem encerrar a interface. | APK assinado, ARM64, Android mínimo 24 e alvo 36. A versão instalada no Redmi antes desta atualização era `0.1.3/code4`. |
| Login | Preserva o carrossel inicial, a verificação do serviço Auth e o retorno Google por `concurse://oauth/callback`. A identidade usada pela biblioteca vem do serviço central. | Testes de login passaram. O usuário confirmou Google e retorno na versão anterior; ainda falta verificar o APK novo. |
| Busca e pesquisa | Usa o motor embarcado, registra resultados públicos no catálogo central e consulta provas já extraídas para reutilização. | Testes de busca do backend passaram. O código e o bundle das novas rotas do gateway estão publicados no GitHub; o deploy operacional aguarda confirmação. |
| PDF, link e OCR | Empacota Python, FastAPI, PyMuPDF, NumPy, OpenCV, ONNX Runtime e RapidOCR. Executa o mesmo worker de provas do desktop, em uma fila de processamento por vez. | Compilação completa passou. Auditoria do APK encontrou 123 ELFs ARM64, todos com alinhamento para páginas de 16 KB, incluindo as bibliotecas dentro dos arquivos Python. Teste PDF/OCR para o aparelho foi compilado, mas ainda não executado. |
| Progresso e recuperação | Consulta autenticada substitui SSE sem Bearer. A fila retoma trabalhos interrompidos; a confirmação de publicação remove o trabalho concluído da lista ativa. | Testes do acompanhamento e da passagem do ID de trabalho para o ID central passaram. |
| Publicação da prova | Envia PDF, gabarito e imagens ao Oracle, publica as questões no Supabase e aprova somente após persistência. Repetições e envio concorrente de prova pública reutilizam o mesmo registro. | Testes cobrem persistência, repetição, isolamento de uploads privados, reutilização entre contas, falha parcial e concorrência. O código está publicado; a publicação operacional remota aguarda confirmação. |
| Biblioteca | Sempre lê os vínculos e os dados centrais; atualiza a lista quando uma extração é publicada. | Testes da biblioteca passaram. Validação autenticada da nova função e do APK permanece pendente. |
| Respostas, erros, simulados e progresso de estudo | Corrige por ID de questão, preserva questões anuladas, calcula matérias e estatísticas de tentativas reais e usa as questões da biblioteca nos simulados. | Testes de correção, simulados, navegação e estatísticas passaram. Verificação remota pendente. |
| Perfil e ranking | Usa metadados do Supabase Auth quando os campos legados estão vazios ou criptografados. Exibe participantes com tentativas reais. | Testes de apresentação de identidade passaram. O código está publicado; a publicação operacional remota aguarda confirmação. |
| Navegação | Cinco ícones em uma única linha: Início, Biblioteca, Buscar, Progresso e Perfil. Menu hambúrguer com os demais acessos. | Interface compilada e testes de navegação passaram. Ainda falta inspeção no aparelho. |

## Ranking

A consulta somente de leitura à base confirmou que a entrada genérica
`Concurseiro`, com 62,5%, corresponde à conta real do usuário: uma tentativa
com 25 acertos em 40 questões. Não foi encontrada uma conta de demonstração
`Concurseiro App` ou `Dev` para excluir. Nenhuma conta real foi removida.

## Artefatos

- `downloads/concurse-mobile-aarch64-release-v0.1.5-code6-16k.apk`:
  158.568.816 bytes; SHA-256
  `96ef599748e93528ffe0974ec0d379dbf940def77eb45c750d43fef6646cb663`.
- A assinatura coincide com a chave das versões anteriores, permitindo
  atualização com preservação dos dados. O alinhamento do APK assinado
  também passou na verificação do Android SDK para páginas de 16 KB.
- `downloads/app-gateway-mobile-hard-switch.ts`: pacote único, gerado dos
  cinco arquivos de `supabase/functions/app-gateway`, para publicação pelo
  editor do painel. Os arquivos originais continuam disponíveis para manutenção.
- `desktop/engine/android/EngineSmokeTest.kt`: teste Android que inicia a
  aplicação, verifica a API do motor, lê texto de PDF e executa OCR de imagem.
- `desktop/engine/android/audit_apk.py`: verifica também os ELFs dentro dos
  arquivos Python e restringe os arquivos do motor à lista de fontes permitida.

A auditoria não encontrou banco de dados ou chave privada no APK.

## Verificações e pendências

O backend passou em 29 testes de biblioteca, busca e gabarito, com um teste
ignorado. Os 53 testes frontend passaram em dois grupos: 48 testes de
14 arquivos no pool `threads` e os cinco testes de busca no pool `vmThreads`.
Os relatórios estão em `build/outputs/diagnostics/frontend-unit-threads.json`
e `frontend-search-vm-threads.json`, dentro do aplicativo Android gerado.
A busca não iniciava seu worker no primeiro pool. O segundo pool, aplicado
à suíte inteira, falhou em testes de mocks e Web Crypto que passam no pool
normal; por isso foi usado somente para a busca. Não considerar essa
verificação como uma execução integral bem-sucedida em um único pool.

O teste Android foi compilado contra a variante release do aplicativo e
assinado com a mesma chave do APK principal; sua assinatura foi verificada.
A tentativa de atualizar o Redmi não instalou o APK: o aparelho deixou de
aparecer na conexão USB. Não houve desinstalação nem limpeza de dados.

O usuário autorizou acessar o painel Supabase e publicar a função. O navegador
continua rejeitando o acesso por uma preferência salva que bloqueia
`supabase.com`. Em 04/10, uma regra específica para `https://supabase.com`
foi salva pela interface do Codex como "Requer aprovação". A consulta somente
de leitura à configuração confirmou `access = "allow"`; mesmo assim, a
ferramenta do navegador manteve a recusa pelo bloqueio anterior. Após o usuário
liberar a janela, a conexão do navegador foi desativada e reativada pela
interface; o estado ativado foi confirmado. O usuário informou que a regra já
está em "Sempre permitir". Depois de reabrir a sessão, o painel ficou visível e
listou `app-gateway`, mas uma nova tentativa pelo controle normal continuou
recusada antes de expor a página à automação, mesmo após o usuário informar que
liberou todas as permissões e reiniciou completamente o aplicativo. Não houve
acesso por outra superfície nem publicação. Antes de publicar, conferir o
código remoto para preservar eventuais alterações mais recentes.

Após liberar o painel e reconectar o Redmi, verificar inicialização, PDF/OCR,
login, busca, ingestão por link e arquivo, gabarito, publicação no Oracle e
Supabase, biblioteca, resolução, erros, simulados, estatísticas, ranking e
navegação. Não usar apenas compilação ou contagem de questões como prova de
que todos os fluxos foram concluídos.
