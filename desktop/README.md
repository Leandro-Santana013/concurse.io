# Aplicativo desktop concurse.io

Este diretório empacota a aplicação React em uma janela Tauri 2. A versão de
produção leva o frontend compilado dentro do instalador e abre esses arquivos
locais; ela não navega para o site DuckDNS como página de fundo. O endereço de
`frontend/.env.desktop` é usado somente para API, autenticação e mídia protegida.
O cliente usa as rotas de ticket/mesh do backend quando houver peers alcançáveis
e mantém o fallback central.

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
`desktop/src-tauri/target/release/bundle/`. Se o backend mudar, altere apenas
`VITE_API_ORIGIN` em `frontend/.env.desktop` e gere o instalador novamente.

O aplicativo não recebe `SESSION_SECRET`, `MESH_SHARED_SECRET` ou credenciais
Google. O backend continua sendo a autoridade para identidade, biblioteca e
permissões; esta etapa remove a dependência de carregar o HTML do site dentro
do aplicativo.

No Windows, o Tauri ainda usa o WebView2 como motor de renderização da
interface React, mas o conteúdo carregado é o `frontend/dist` local. Remover
também o WebView2 exigiria reescrever a interface em Win32/WinUI.
