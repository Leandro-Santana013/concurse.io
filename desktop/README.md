# Aplicativo desktop concurse.io

Este diretório empacota a aplicação React em uma janela Tauri 2. A versão de
produção abre o origin HTTPS (`https://concurse.duckdns.org`) dentro do
WebView; assim o login Google, os cookies HTTP-only e a autorização por conta
continuam exatamente no mesmo domínio. O cliente usa as rotas de ticket/mesh
do origin quando houver peers alcançáveis e mantém o fallback central.

## Desenvolvimento

Pré-requisitos no Windows: Rust com o alvo MSVC, Node.js e WebView2. Na pasta
`desktop`, instale a CLI uma vez e inicie:

```powershell
npm install
npm run dev
```

O modo de desenvolvimento carrega o Vite em `http://localhost:5173`, usando o
proxy já configurado para o FastAPI em `127.0.0.1:8000`.

## Instalador

```powershell
npm run build
```

O Tauri gera o executável e o instalador para o sistema operacional atual em
`desktop/src-tauri/target/release/bundle/`. A URL de produção fica em
`desktop/src-tauri/tauri.conf.json`; altere-a se o domínio do origin mudar.

O aplicativo não recebe `SESSION_SECRET`, `MESH_SHARED_SECRET` ou credenciais
Google. A sessão permanece no WebView do origin e o servidor continua sendo a
autoridade para identidade, biblioteca e permissões.
