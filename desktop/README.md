# Aplicativo desktop concurse.io

Este diretório empacota uma aplicação Tauri 2 local-first. A interface e o
cache de provas ficam no computador, enquanto o login Google, a biblioteca de
cada usuário e o compartilhamento de provas usam o fluxo central do projeto,
com dados persistidos no Supabase por meio da API da aplicação.

Quando o origin está disponível, a conta Google determina quais provas estão
atribuídas ao usuário. O aplicativo consulta a biblioteca central e mantém uma
cópia local para reabrir provas sincronizadas sem repetir o download. Não há
descoberta de pares, broadcast UDP, servidor TCP local ou endpoint `/mesh/*`.

O importador desktop continua aceitando PDF para guardar localmente e JSON de
prova extraída para abrir as questões. A extração de PDF/OCR continua sendo
uma etapa separada; o aplicativo não executa OCR em segundo plano.

## Desenvolvimento

Pré-requisitos no Windows: Rust com o alvo MSVC, Node.js e WebView2. Na pasta
`desktop`, instale a CLI uma vez e inicie:

```powershell
npm install
npm run dev
```

O perfil normal usa `frontend/.env.desktop` e o origin configurado em
`VITE_API_ORIGIN`. Para testar sem rede, use o perfil local com
`npm run build:desktop:offline`; nesse modo o login e o compartilhamento entre
usuários ficam indisponíveis, mas o cache e a importação local continuam.

## Instalador

```powershell
npm run build
```

O Tauri gera o executável e os instaladores em
`desktop/src-tauri/target/release/bundle/`. O instalador não contém credenciais
de serviço. No Windows, a interface React é renderizada pelo WebView2 local;
isso não abre o site como tela principal.
