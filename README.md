# concurse.io

Aplicativo para estudar com provas de concursos, simulados e revisão de erros.
O mesmo projeto entrega a interface web e os aplicativos Tauri para Windows e
Android.

## O que está pronto

- login Google pelo Supabase Auth;
- biblioteca de provas associada à conta, disponível em mais de um dispositivo;
- cache local para reabrir provas já sincronizadas;
- ingestão local de PDF/JSON e envio dos arquivos para o Oracle Object Storage;
- imagens e PDFs entregues por Edge Functions do Supabase, com autorização por
  PAR somente para os prefixos necessários;
- renderização de fórmulas, simulados, progresso e caderno de erros;
- ícone e manifesto instaláveis para Windows e Android.

O projeto usa o Supabase como camada de autenticação e distribuição. Não é
necessário manter uma VM, uma API própria, um domínio DNS ou uma rede P2P para
usar os aplicativos. O Oracle fica como armazenamento de mídia; as credenciais
privadas do bucket permanecem nos secrets das Edge Functions e nunca são
embutidas nos instaladores.

## Downloads

Os binários versionados ficam em [`downloads/`](downloads/). Cada arquivo é
acompanhado pelo SHA-256 em [`downloads/SHA256SUMS.txt`](downloads/SHA256SUMS.txt).

| Plataforma | Arquivo | Observação |
| --- | --- | --- |
| Windows x64 | [`concurse.io_0.1.0_x64_en-US.msi`](downloads/concurse.io_0.1.0_x64_en-US.msi) | Instalador MSI |
| Windows x64 | [`concurse.io_0.1.0_x64-setup.exe`](downloads/concurse.io_0.1.0_x64-setup.exe) | Instalador NSIS |
| Android arm64 | [`concurse-mobile-aarch64-release-v0.1.2-code3-16k.apk`](downloads/concurse-mobile-aarch64-release-v0.1.2-code3-16k.apk) | APK para Redmi/Android arm64 |

O APK Android está publicado para teste mesmo com a falha nativa conhecida no
Android 16/HyperOS: em alguns aparelhos o processo aborta durante a criação do
WebView, antes de a tela aparecer. O arquivo é assinado com a chave de
desenvolvimento usada nesta build e serve para diagnóstico; uma versão de
produção só deve ser publicada depois da correção desse abort e da assinatura
com uma chave de release própria.

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

O instalador Windows sai em `desktop/src-tauri/target/release/bundle/`. O APK
Android sai em `desktop/src-tauri/gen/android/app/build/outputs/apk/`. Os
comandos de build não executam OCR; a extração de provas é uma etapa separada.

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

O fluxo Windows/web está preparado para uso com Supabase. O APK Android está
disponível para reproduzir o problema de inicialização e validar a correção em
aparelhos afetados. A falha não impede o uso do código-fonte, do instalador
Windows ou da biblioteca web.
