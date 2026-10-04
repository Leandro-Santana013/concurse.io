# concurse.io

Aplicativo para estudar com provas de concursos, simulados e revisão de erros.
O mesmo projeto entrega a interface web e os aplicativos Tauri para Windows e
Android.

## O que está pronto

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

O APK Android `0.1.5/code6` usa o mesmo gateway e inclui um motor de
extração/OCR embarcado, com a mesma lógica de processamento de provas do
desktop. O SQLite do Android guarda a fila e os dados de trabalho; a biblioteca
e as tentativas usam os serviços centrais. A compilação, os testes e a auditoria
do pacote passaram, mas o teste desse APK no aparelho e a confirmação do deploy
das novas rotas do Supabase continuam pendentes. Consulte a
[auditoria mobile](docs/mobile-migration-audit.md) antes de considerar a migração
operacionalmente concluída.

## Downloads

Os binários versionados ficam em [`downloads/`](downloads/). Cada arquivo é
acompanhado pelo SHA-256 em [`downloads/SHA256SUMS.txt`](downloads/SHA256SUMS.txt).

| Plataforma | Arquivo | Observação |
| --- | --- | --- |
| Windows x64 | [`concurse.io_0.1.2_x64-setup.exe`](downloads/concurse.io_0.1.2_x64-setup.exe) | Instalador interativo atual; exige WebView2 |
| Windows x64 | [`concurse.io_0.1.2_x64_en-US.msi`](downloads/concurse.io_0.1.2_x64_en-US.msi) | Instalador MSI atual; exige WebView2 |
| Android ARM64 | [`concurse-mobile-aarch64-release-v0.1.5-code6-16k.apk`](downloads/concurse-mobile-aarch64-release-v0.1.5-code6-16k.apk) | Beta, Android 7.0 ou superior; motor OCR embarcado e alinhamento de 16 KB; teste no aparelho pendente |

O APK Android 0.1.5/code6 apresenta três páginas sobre biblioteca, prática e
revisão, seguidas do login. O carrossel permite deslizar, usar a paginação e
ir diretamente ao acesso. Antes de abrir o Google, o aplicativo verifica o
serviço e apresenta erros na própria tela, permitindo uma nova tentativa.
O APK também inclui cinco ícones na barra inferior e um menu hambúrguer com
os demais acessos.

A versão 0.1.3/code4 corrigiu a configuração inválida `plugins.opener.open`;
o usuário confirmou que chegou à tela de login no Redmi 14C. A captura USB em
03/10/2026 havia confirmado que esse campo fazia a versão 0.1.2/code3 abortar
antes da interface. A versão nova preserva essa correção e o alinhamento de 16 KB.

A falha de DNS no login foi resolvida após o usuário retomar o projeto Supabase
em 03/10/2026. A verificação remota confirmou o serviço Auth respondendo com
Google habilitado e a autorização redirecionando para `accounts.google.com`.
O usuário confirmou o retorno do Google ao aplicativo na versão instalada
0.1.3. A interface, o login e o processamento da versão 0.1.5 ainda precisam de
teste no aparelho. O novo arquivo usa a mesma chave de desenvolvimento do
anterior, permitindo instalá-lo como atualização. Uma distribuição de produção
exige uma chave de release própria.

Os artefatos atuais estão publicados na branch `codex/concurse-app`. O
[inventário de downloads](downloads/README.md) registra as versões anteriores,
os hashes e a diferença entre código publicado e validação operacional.

## Página de apresentação e instalação

A landing page reúne os downloads e explica o fluxo de estudo. Veja os arquivos
e as instruções em [`landing/README.md`](landing/README.md).
A página está publicada no GitHub Pages em
[`https://leandro-santana013.github.io/concurse.io/`](https://leandro-santana013.github.io/concurse.io/).
O endereço público e os três downloads foram verificados em 04/10/2026.

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
instaladores Windows `0.1.2` e o APK Android `0.1.5/code6` estão publicados no
GitHub. O Android permanece beta: o pacote foi compilado, assinado e auditado,
mas os novos fluxos ainda precisam de teste no aparelho e de confirmação do
deploy da função Supabase. Login e sincronização exigem conexão com a internet.
