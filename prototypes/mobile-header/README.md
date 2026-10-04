# Protótipos do cabeçalho mobile

Comparação visual separada do aplicativo; os dados são ilustrativos e nenhuma prova é baixada aqui.

- **A — compacto:** `http://127.0.0.1:4190/?opcao=a`
- **B — duas linhas:** `http://127.0.0.1:4190/?opcao=b`

Para servir, execute `node prototypes/mobile-header/serve.mjs` a partir deste worktree.

Os controles permitem trocar o tema, a largura simulada, as cinco abas e abrir o menu lateral. O menu inclui apenas destinos secundários. O relógio, o sinal e a bateria são uma representação da área reservada ao sistema Android, separada dos controles do aplicativo.

O ícone preserva o **C com check do instalador atual**, agora em duas variantes preto e branco copiadas dos arquivos corrigidos do aplicativo. O controle de tema troca automaticamente entre branco sobre preto no tema escuro e preto sobre branco no tema claro, tanto no cabeçalho quanto no menu. As cores escuras correspondem ao tema emerald do aplicativo. Inter e Source Serif 4 são hospedadas localmente com suas licenças OFL.
