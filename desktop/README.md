# Aplicativo desktop concurse.io

Este diretório empacota uma aplicação Tauri 2 **local-first híbrida**. A versão
de produção leva a interface, o cache local e o motor de rede no instalador.
O catálogo e as tentativas continuam rápidos no computador, enquanto o login
Google, os vínculos da biblioteca e a sinalização da malha usam o origin
configurado em `frontend/.env.desktop`.

Na rede local, os nós anunciam seus hashes por broadcast UDP e trocam blocos
de até 1 MiB por TCP. Fora da LAN, o origin autentica a conta, mantém leases
curtos dos dispositivos e o endpoint `/mesh/fetch` baixa blocos em paralelo
com fallback íntegro. Um peer desktop só entra na descoberta externa quando seu
endpoint público é configurado e alcançável pelo origin; sem essa configuração,
o aplicativo usa a biblioteca sincronizada pelo origin. O caminho direto entre peers usa um endpoint alcançável;
quando dois clientes estão atrás de NAT sem rota, o origin faz a reconstrução
dos blocos se conseguir alcançar algum provider. Para ligação direta entre NATs
restritivos, configure STUN/TURN ou um relay dedicado no plano de controle.
Cada arquivo é content-addressed por `sha256:<hash>` e só entra no cache depois
da verificação do hash final.

O importador offline continua aceitando PDF para armazenar/redistribuir e JSON
de prova extraída para abrir as questões. O fluxo híbrido usa os dados
atribuídos à conta Google e mantém o cache local para reabrir provas sem
repetir o download. O login desktop abre o navegador padrão, recebe um código
loopback de uso único e nunca transforma a tela principal em um site.

## Desenvolvimento

Pré-requisitos no Windows: Rust com o alvo MSVC, Node.js e WebView2. Na pasta
`desktop`, instale a CLI uma vez e inicie:

```powershell
npm install
npm run dev
```

O modo de desenvolvimento carrega o Vite em `http://localhost:5173`. Para o
perfil híbrido, preencha `VITE_API_ORIGIN` em `.env.desktop`; para testar sem
origin use `npm run build:desktop:offline`. O backend precisa estar publicado
com Google OAuth configurado para o login e com o plano de controle mesh ativo.

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
