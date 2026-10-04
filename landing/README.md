# Landing pública concurse.io

Página estática de apresentação e downloads. Preserva a identidade de leitura
do aplicativo, com temas claro e escuro, prévia ilustrativa das funções,
instruções de instalação e FAQ.

O símbolo é o C com check usado nos aplicativos, em preto e branco. Os arquivos
`assets/concurse-icon-light-64.png` e `assets/concurse-icon-dark-64.png` são
cópias das variantes de `frontend/public/`, sem redesenhar o símbolo. Cabeçalho,
prévia, rodapé e favicon acompanham a escolha claro/escuro ou a preferência do
sistema. A imagem de compartilhamento usa a variante clara; ao alterar
`assets/social-card.svg`, renderize novamente `assets/social-card.png` no
navegador, em 1200 × 630 pixels.

As fontes Inter e Source Serif 4 são hospedadas junto da página; suas licenças
Open Font License ficam em `assets/fonts/`. A página não usa analytics, cookies
de rastreamento nem credenciais do Supabase.

A publicação usa GitHub Pages. A URL de destino é
https://leandro-santana013.github.io/concurse.io/.

## Desenvolvimento

Não há dependências para instalar. Use Node.js 20 ou mais recente:

```powershell
npm --prefix landing run build
npm --prefix landing run check -- --local-artifacts --remote
npm --prefix landing run dev
```

O servidor local abre em http://127.0.0.1:4175/concurse.io/.
O diretório `landing/dist` é gerado e não deve ser versionado.

## Atualizar instaladores

1. Publique o novo binário em `downloads/` pelo Git LFS e atualize
   `downloads/SHA256SUMS.txt`.
2. Em `landing/releases.json`, atualize o nome, versão, tamanho em bytes,
   SHA-256 e o commit completo que contém o binário publicado.
3. Atualize as versões/requisitos descritos em `landing/index.html`.
4. Gere a página e execute a conferência local e remota antes de publicar.

O build interrompe a publicação quando o manifesto não corresponde aos hashes
de `SHA256SUMS.txt`. Os downloads apontam para `media.githubusercontent.com`
com um commit fixo, para entregar o instalador completo do Git LFS sem login.
Os binários não são copiados para o site.

## Publicação

O workflow `.github/workflows/landing-pages.yml` publica mudanças da landing e
do manifesto na branch `codex/concurse-app`. O repositório deve estar configurado
para GitHub Pages com fonte GitHub Actions, e o ambiente `github-pages` deve
permitir essa branch. A página gerada inclui os três instaladores atuais, seus
hashes, metadados de compartilhamento, robots e sitemap.

O Android é apresentado como beta: APK 0.1.5/code6 ARM64, Android 7.0 ou mais
recente, com validação no aparelho e confirmação dos fluxos remotos pendentes.
Isso não significa compatibilidade universal nem funcionamento totalmente
offline.
