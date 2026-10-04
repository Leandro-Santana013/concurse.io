# Aplicativo concurse.io para Windows e Android

O diretório `desktop` empacota a interface React em Tauri 2. O login é feito
com Google pelo Supabase Auth; a biblioteca e as provas atribuídas à conta são
sincronizadas pelas Edge Functions do próprio projeto. O Oracle Object Storage
guarda PDFs e imagens, mas suas credenciais ficam apenas nos secrets do
Supabase.

No Windows, o build `desktop-local` inicia um sidecar FastAPI com o worker de
extração/OCR do projeto. O SQLite e a mídia local são usados pelo motor durante
a extração; a prova final vai para o Supabase e seus arquivos para o Oracle.
Biblioteca, estatísticas, tentativas, caderno de erros e ranking continuam
consultando os dados centrais. A extração não exige uma FastAPI externa.

O perfil offline legado é separado e não é ativado pelos builds atuais de
Windows ou Android. O Android não inclui o motor OCR do Windows; sua migração
completa ainda está pendente. Consulte a
[auditoria dos fluxos mobile](../docs/mobile-migration-audit.md).

## Desenvolvimento

No Windows, instale Node.js, Rust/MSVC e WebView2. Depois:

```powershell
npm install
npm run dev
```

O modo padrão do desktop usa `frontend/.env.desktop-local` e o sidecar FastAPI
local. Para o perfil online legado, use `frontend/.env.desktop`; para testar
apenas o catálogo Tauri antigo, use `npm run build:desktop:offline`.

## Builds

```powershell
npm run build                 # gera o sidecar OCR e MSI/NSIS Windows x64
npm run engine:build          # apenas recria o sidecar FastAPI/OCR
npm run android:init          # uma vez por checkout
npm run android:build         # APK arm64
```

Os instaladores Windows aparecem em
`src-tauri/target/release/bundle/`. O APK aparece em
`src-tauri/gen/android/app/build/outputs/apk/`. Os arquivos que podem ser
baixados diretamente estão em [`../downloads/`](../downloads/).

O Android usa o esquema `concurse://oauth/callback` para retornar do navegador
do sistema após o login Google. O novo APK
[`0.1.4/code5`](../downloads/concurse-mobile-aarch64-release-v0.1.4-code5-16k.apk)
inclui um carrossel inicial de quatro páginas, com apresentação antes do login,
deslize, paginação, navegação por teclado e acesso direto ao Google. O login
verifica a disponibilidade do serviço e do provedor antes de abrir o navegador;
o botão permite outra tentativa após o usuário voltar sem concluir o acesso.

A versão 0.1.3 removeu o campo inválido `plugins.opener.open` dos perfis Android
e iOS. O usuário confirmou que essa versão chegou à tela de login no Redmi 14C;
o defeito de inicialização da 0.1.2/code3 foi identificado pela captura USB.
A versão 0.1.4 preserva a correção e o alinhamento de 16 KB. Ela ainda não foi
publicada no GitHub e precisa de teste da nova interface e do login completo no
aparelho. A mesma chave de desenvolvimento permite instalá-la como atualização.

Em 03/10/2026, o domínio do Supabase retornou NXDOMAIN. Após o usuário retomar
o projeto, o DNS voltou a resolver, `/auth/v1/settings` respondeu HTTP 200 com
Google habilitado e `/auth/v1/authorize` redirecionou para `accounts.google.com`.
O usuário confirmou que o Google abriu e retornou ao aplicativo no Redmi 14C
com a versão instalada 0.1.3.
Os testes visuais no navegador não foram realizados porque a permissão de
acesso foi negada.

O build Android usa `frontend/.env.mobile` e não embute o sidecar OCR do Windows.
Os flags de alinhamento de 16 KB estão em
[`desktop/.cargo/config.toml`](.cargo/config.toml), na raiz do pacote npm, para
que tanto o primeiro build em `src-tauri` quanto o callback do Gradle em
`desktop` encontrem a mesma configuração.

Para registrar uma abertura do aplicativo instalado, use
`scripts/collect-android-startup.ps1` com o celular conectado e autorizado por
Depuração USB. A coleta salva versão do sistema, ABI, tamanho de página,
provider WebView, SHA-256 do APK instalado, logcat e histórico de encerramento
em `src-tauri/gen/android/app/build/outputs/diagnostics/`. O script reinicia
somente o concurse.io e não apaga os dados do aplicativo.

## Integração de mídia

O frontend chama `app-gateway` para a biblioteca e `media-gateway` para ler ou
enviar objetos. O app nunca recebe a service role key, a chave privada OCI ou a
URL completa de um PAR de escrita. Configure os PARs nos secrets do Supabase e
gere novos PARs quando a validade terminar.
