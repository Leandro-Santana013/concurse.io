# Aplicativo desktop concurse.io

Este diretório empacota uma aplicação Tauri 2 **local-first**. A versão de
produção leva a interface, o catálogo, os arquivos das provas e o motor de
rede no instalador. Ela não abre o site, não usa DuckDNS, Supabase, Google ou
um backend remoto. Cada computador tem um perfil local e guarda sua biblioteca
no diretório de dados privado da aplicação (`io.concurse.desktop` no Windows).

Quando habilitada, a única comunicação é a malha entre instâncias do próprio
aplicativo: os nós anunciam seus hashes por broadcast UDP na rede local e
trocam blocos de até 1 MiB por TCP. Cada arquivo é content-addressed por
`sha256:<hash>` e o download só é aceito depois da verificação do hash final.
O catálogo/manifests acompanham o arquivo para que um par possa reconstruir a
prova. Não existe servidor de descoberta global neste modo; para atravessar
NATs diferentes seria necessário um pareamento manual ou um relay, o que seria
um serviço externo e contrariaria o modo totalmente autônomo.

O importador desktop aceita um PDF para armazenar e redistribuir localmente e
um JSON de prova extraída para abrir as questões sem servidor. Para manter
figuras sem um servidor, o JSON deve trazer as imagens como `data:`; referências
HTTP externas são descartadas no modo offline. A extração de PDF/OCR continua
sendo uma etapa local separada; nenhum link remoto é chamado.

## Desenvolvimento

Pré-requisitos no Windows: Rust com o alvo MSVC, Node.js e WebView2. Na pasta
`desktop`, instale a CLI uma vez e inicie:

```powershell
npm install
npm run dev
```

O modo de desenvolvimento carrega o Vite em `http://localhost:5173` com o
mesmo armazenamento offline e o mesmo núcleo de descoberta mesh do instalador.
Não é necessário iniciar FastAPI, Docker ou qualquer serviço web.

## Instalador

```powershell
npm run build
```

O Tauri gera o executável e o instalador para o sistema operacional atual em
`desktop/src-tauri/target/release/bundle/`. O instalador não recebe credenciais
de serviço e não depende de variáveis de ambiente de produção.

No Windows, o Tauri ainda usa o WebView2 como motor de renderização da
interface React, mas o conteúdo carregado é o `frontend/dist` local. Remover
também o WebView2 exigiria reescrever a interface em Win32/WinUI; isso não
cria uma conexão com a internet.
