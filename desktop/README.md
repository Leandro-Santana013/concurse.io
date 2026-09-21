# Aplicativo concurse.io para Windows e Android

O diretório `desktop` empacota a interface React em Tauri 2. O login é feito
com Google pelo Supabase Auth; a biblioteca e as provas atribuídas à conta são
sincronizadas pelas Edge Functions do próprio projeto. O Oracle Object Storage
guarda PDFs e imagens, mas suas credenciais ficam apenas nos secrets do
Supabase.

O aplicativo mantém cache local para leitura rápida e reabertura offline das
provas que já foram sincronizadas. Não há descoberta de pares, broadcast,
servidor local, VM ou domínio externo. A ingestão de PDF/OCR continua sendo
executada fora do aplicativo, e o importador aceita um PDF ou um JSON já
extraído.

## Desenvolvimento

No Windows, instale Node.js, Rust/MSVC e WebView2. Depois:

```powershell
npm install
npm run dev
```

O modo normal usa `frontend/.env.desktop` e as Edge Functions do Supabase. Para
testar apenas a biblioteca local, use `npm run build:desktop:offline`; esse
perfil não faz login nem sincroniza a conta.

## Builds

```powershell
npm run build                 # MSI e NSIS para Windows x64
npm run android:init          # uma vez por checkout
npm run android:build         # APK arm64
```

Os instaladores Windows aparecem em
`src-tauri/target/release/bundle/`. O APK aparece em
`src-tauri/gen/android/app/build/outputs/apk/`. Os arquivos que podem ser
baixados diretamente estão em [`../downloads/`](../downloads/).

O Android usa o esquema `concurse://oauth/callback` para retornar do navegador
do sistema após o login Google. O APK atualmente publicado é experimental: em
alguns Redmi com Android 16/HyperOS o runtime nativo aborta durante a criação do
WebView. Essa limitação está registrada no README raiz e não é escondida do
usuário.

## Integração de mídia

O frontend chama `app-gateway` para a biblioteca e `media-gateway` para ler ou
enviar objetos. O app nunca recebe a service role key, a chave privada OCI ou a
URL completa de um PAR de escrita. Configure os PARs nos secrets do Supabase e
gere novos PARs quando a validade terminar.
