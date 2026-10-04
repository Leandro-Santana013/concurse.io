# concurse.io

Aplicativo para estudar com provas de concursos, simulados e revisão de erros.
O mesmo projeto entrega a interface web e os aplicativos Tauri para Windows e
Android.

## Recursos

- login Google pelo Supabase Auth;
- biblioteca de provas associada à conta, disponível em mais de um dispositivo;
- cache local para reabrir provas já sincronizadas;
- extração/OCR de PDF no desktop e motor embarcado no APK Android beta, além de
  importação de JSON estruturado, com envio dos arquivos para o Oracle Object
  Storage;
- imagens e PDFs entregues por Edge Functions do Supabase, com autorização por
  PAR somente para os prefixos necessários;
- renderização de fórmulas, simulados, progresso e caderno de erros;
- ícone e manifesto instaláveis para Windows e Android.

O projeto usa o Supabase como camada de autenticação e distribuição. Não é
necessário manter uma VM, uma API própria, um domínio DNS ou uma rede P2P para
usar os aplicativos. O Oracle fica como armazenamento de mídia; as credenciais
privadas do bucket permanecem nos secrets das Edge Functions e nunca são
embutidas nos instaladores.

No desktop Windows, o perfil `desktop-local` inclui um sidecar FastAPI com o
pipeline de extração/OCR, SQLite e mídia de trabalho do motor. A prova final é
enviada ao Supabase e os arquivos ao Oracle. Biblioteca, tentativas,
estatísticas, caderno de erros e ranking usam os dados centrais pelo gateway;
o SQLite do motor não é a biblioteca principal.

O APK Android `0.1.6/code7` usa o mesmo gateway e inclui um motor de
extração/OCR embarcado, com a mesma lógica de processamento de provas do
desktop. O SQLite do Android guarda a fila e os dados de trabalho; a biblioteca
e as tentativas usam os serviços centrais. A revisão corrige uma falha do
OpenSSL capturada no Redmi 14C que impedia o motor de iniciar e tornava a busca
indisponível. O usuário informou ter substituído a função `app-gateway` no
painel Supabase; a validação remota autenticada e o teste desta revisão no
aparelho continuam pendentes. Consulte a
[auditoria mobile](docs/mobile-migration-audit.md) antes de considerar a migração
operacionalmente concluída.

## Downloads

Os binários versionados ficam em [`downloads/`](downloads/). Cada arquivo é
acompanhado pelo SHA-256 em [`downloads/SHA256SUMS.txt`](downloads/SHA256SUMS.txt).

| Plataforma | Arquivo | Observação |
| --- | --- | --- |
| Windows x64 | [`concurse.io_0.1.2_x64-setup.exe`](downloads/concurse.io_0.1.2_x64-setup.exe) | Instalador interativo atual; exige WebView2 |
| Windows x64 | [`concurse.io_0.1.2_x64_en-US.msi`](downloads/concurse.io_0.1.2_x64_en-US.msi) | Instalador MSI atual; exige WebView2 |
| Android ARM64 | [`concurse-mobile-aarch64-release-v0.1.6-code7-16k.apk`](downloads/concurse-mobile-aarch64-release-v0.1.6-code7-16k.apk) | Revisão beta, Android 7.0 ou superior; motor OCR embarcado; teste no aparelho pendente |

O APK Android apresenta três páginas sobre biblioteca, prática e
revisão, seguidas do login. O carrossel permite deslizar, usar a paginação e
ir diretamente ao acesso. Antes de abrir o Google, o aplicativo verifica o
serviço e apresenta erros na própria tela, permitindo uma nova tentativa.
O topo compacto aprovado respeita as áreas do sistema Android por insets
nativos. A barra inferior mantém Início, Biblioteca, Buscar, Progresso e Perfil
em uma única linha. O menu hambúrguer reúne Caderno de erros, Ranking e
Importar prova, sem repetir os cinco destinos principais. O ícone C com check
tem duas variantes para manter a legibilidade nos 12 temas da interface.

A busca reconhece termos unidos, como `FiscalPosturaIDCAP`, e a grafia
`idecap`, normalizada para IDCAP. O resultado é associado ao cargo, à cidade,
ao ano e à banca; quando necessário, usa a cópia pública oficial correspondente.
O caderno de Fiscal de Obras, Posturas e Meio Ambiente de Ibirataia/BA, IDCAP
2024, foi conferido com a mesma cópia oficial: 50 questões com quatro
alternativas e 50 gabaritos coincidentes com a matriz, incluindo Q1 D e Q49 B.
A revisão preserva os gabaritos explícitos da prova matriz e as alternativas de associação;
a versão 12 do cache descarta extrações antigas afetadas por esses erros.

A versão 0.1.3/code4 corrigiu a configuração inválida `plugins.opener.open`;
o usuário confirmou que chegou à tela de login no Redmi 14C. A captura USB em
03/10/2026 havia confirmado que esse campo fazia a versão 0.1.2/code3 abortar
antes da interface. A versão nova preserva essa correção e o alinhamento de 16 KB.

A falha de DNS no login foi resolvida após o usuário retomar o projeto Supabase
em 03/10/2026. A verificação remota confirmou o serviço Auth respondendo com
Google habilitado e a autorização redirecionando para `accounts.google.com`.
O usuário confirmou o retorno do Google ao aplicativo na versão instalada
0.1.3. A interface, o login, a busca e o processamento da revisão 0.1.6 ainda
precisam de teste no aparelho: o Redmi não está disponível na conexão ADB.
As versões anteriores usam uma chave de desenvolvimento; uma distribuição
de produção exige uma chave de release própria.

O APK `0.1.5/code6` permanece no histórico. Os instaladores Windows `0.1.2`
não foram recompilados nesta revisão; as mudanças nos componentes e ícones
compartilhados estão nas fontes e só chegam ao instalador após um novo build.
A branch de distribuição é `codex/concurse-app`. O
[inventário de downloads](downloads/README.md) registra as versões anteriores,
os hashes e a diferença entre código publicado e validação operacional.

## Página de apresentação e instalação

A landing page reúne os downloads e explica o fluxo de estudo. Veja os arquivos
e as instruções em [`landing/README.md`](landing/README.md).
A página está publicada no GitHub Pages em
[`https://leandro-santana013.github.io/concurse.io/`](https://leandro-santana013.github.io/concurse.io/).
O endereço público e os downloads da publicação anterior foram verificados
em 04/10/2026; isso não valida o novo APK no aparelho.

## Desenvolvimento

Pré-requisitos:

- Node.js 20 ou mais recente;
- Rust com o alvo `stable-x86_64-pc-windows-msvc` no Windows;
- WebView2 no Windows;
- JDK, Android SDK/NDK e Gradle para Android.

Instalação e execução do frontend:

```powershell
npm --prefix frontend install
npm --prefix frontend run dev
```

Execução do aplicativo desktop:

```powershell
npm --prefix desktop install
npm --prefix desktop run dev
```

Builds:

```powershell
npm --prefix frontend run build:desktop
npm --prefix desktop run build
npm --prefix frontend run build:mobile
npm --prefix desktop run android:build
```

O instalador Windows sai em `desktop/src-tauri/target/release/bundle/`. O build
desktop gera e embute o sidecar OCR antes de criar o instalador; a extração
acontece localmente durante o uso. O APK Android sai em
`desktop/src-tauri/gen/android/app/build/outputs/apk/`.

## Configuração

Os perfis públicos de build ficam em `frontend/.env.desktop` e
`frontend/.env.mobile`. Eles contêm apenas a URL do projeto Supabase e a chave
publishable. Chaves de service role, PARs e credenciais OCI devem ser definidas
como secrets nas Edge Functions `app-gateway` e `media-gateway`.

Consulte [`desktop/README.md`](desktop/README.md),
[`docs/supabase-media-gateway.md`](docs/supabase-media-gateway.md) e
[`docs/oracle-object-storage.md`](docs/oracle-object-storage.md) para o fluxo
completo de desenvolvimento e armazenamento.

## Estado do projeto

O fluxo Windows/web usa Supabase para autenticação e dados centrais. Os
instaladores Windows continuam na versão `0.1.2`; a revisão Android é
`0.1.6/code7` e permanece beta. A verificação desta revisão passou em 29 testes
de backend, com um ignorado, 52 testes do pipeline e de regressão, 20 testes
frontend e seis testes de navegador. Esses resultados não substituem o teste
do APK no Redmi nem a validação autenticada da função remota que o usuário
informou ter atualizado. Login e sincronização exigem conexão com a internet.
