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
Windows ou Android. O APK Android `0.1.5/code6` inclui um motor próprio,
embarcado com Python, FastAPI e OCR, que executa a mesma lógica de processamento
de provas do desktop. O SQLite no Android guarda a fila e os dados de trabalho;
a biblioteca e as tentativas usam os serviços centrais. O teste desse APK no
aparelho e a confirmação do deploy das novas rotas do Supabase continuam
pendentes. Consulte a [auditoria dos fluxos mobile](../docs/mobile-migration-audit.md).

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

Os artefatos atuais publicados na branch `codex/concurse-app` são:

| Plataforma | Arquivo | Requisito e estado |
| --- | --- | --- |
| Windows x64 | [`concurse.io_0.1.2_x64-setup.exe`](../downloads/concurse.io_0.1.2_x64-setup.exe) | Instalador interativo; exige WebView2 |
| Windows x64 | [`concurse.io_0.1.2_x64_en-US.msi`](../downloads/concurse.io_0.1.2_x64_en-US.msi) | MSI; exige WebView2 |
| Android ARM64 | [`concurse-mobile-aarch64-release-v0.1.5-code6-16k.apk`](../downloads/concurse-mobile-aarch64-release-v0.1.5-code6-16k.apk) | Beta, Android 7.0 ou superior; teste no aparelho pendente |

Confira os hashes em [`../downloads/SHA256SUMS.txt`](../downloads/SHA256SUMS.txt).
A landing page e suas instruções estão em
[`../landing/README.md`](../landing/README.md). A página está publicada em
[`https://leandro-santana013.github.io/concurse.io/`](https://leandro-santana013.github.io/concurse.io/),
com endereço público e downloads verificados em 04/10/2026.

O Android usa o esquema `concurse://oauth/callback` para retornar do navegador
do sistema após o login Google. O novo APK
[`0.1.5/code6`](../downloads/concurse-mobile-aarch64-release-v0.1.5-code6-16k.apk)
inclui um carrossel inicial de quatro páginas, com apresentação antes do login,
deslize, paginação, navegação por teclado e acesso direto ao Google. O login
verifica a disponibilidade do serviço e do provedor antes de abrir o navegador;
o botão permite outra tentativa após o usuário voltar sem concluir o acesso.

A versão 0.1.3 removeu o campo inválido `plugins.opener.open` dos perfis Android
e iOS. O usuário confirmou que essa versão chegou à tela de login no Redmi 14C;
o defeito de inicialização da 0.1.2/code3 foi identificado pela captura USB.
A versão 0.1.5 preserva a correção e o alinhamento de 16 KB, inclui o motor de
extração/OCR, cinco ícones na barra inferior e menu hambúrguer. O APK está
publicado no GitHub; a interface, o login e o processamento ainda precisam de
teste no aparelho. A mesma chave de desenvolvimento permite instalá-lo como
atualização. A distribuição de produção exige validação no aparelho e uma chave
de release própria.

Em 03/10/2026, o domínio do Supabase retornou NXDOMAIN. Após o usuário retomar
o projeto, o DNS voltou a resolver, `/auth/v1/settings` respondeu HTTP 200 com
Google habilitado e `/auth/v1/authorize` redirecionou para `accounts.google.com`.
O usuário confirmou que o Google abriu e retornou ao aplicativo no Redmi 14C
com a versão instalada 0.1.3.
Os testes visuais no navegador não foram realizados porque a permissão de
acesso foi negada.

O build Android usa `frontend/.env.mobile` e seu próprio motor embarcado em
`desktop/engine/android/`. A preparação do motor é executada automaticamente
antes da compilação da interface. Login e sincronização exigem conexão com a
internet; o processamento local não torna todos os fluxos disponíveis offline.
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
