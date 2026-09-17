# ADR 0003: biblioteca entre dispositivos e imagens endereçadas por conteúdo

## Contexto

Uma prova canônica pode ser vinculada a vários usuários por `user_exams`, e a
mesma pessoa pode abrir a conta em um computador ou celular. O nome dos PNGs
gerados pelo OCR (`qimg_exam...`) é local e muda quando a prova é reprocessada;
ele não é uma identidade adequada para uma futura rede mesh.

## Decisão

O banco compartilhado continua sendo a autoridade da identidade e dos
vínculos. O login Google valida o `sub`, guarda somente o identificador
pseudonimizado e resolve a mesma linha `users` em qualquer dispositivo.

Após a sessão ser estabelecida, o cliente usa `GET /api/v1/library/snapshot`.
O snapshot contém:

- todas as provas aprovadas que pertencem ao usuário ou estão em `user_exams`;
- a lista plana e a organização por pastas;
- uma `library_version` determinística para detectar mudanças;
- um manifesto de mídia por prova.

Cada mídia disponível no volume recebe `sha256:<digest>` calculado sobre os
bytes do arquivo. A questão continua aceitando as referências antigas, mas o
manifesto também informa a questão, o corpo ou alternativa e o índice da
imagem. Assim, um peer pode buscar o blob pelo digest e reconstruir a URL
autorizada localmente. Referências ausentes são preservadas como `ref:<digest>`
com `available=false` para que uma futura ingestão possa corrigi-las.

O servidor não persiste URLs assinadas nem o `sub` bruto do Google. A rota de
mídia segue protegida por autorização da prova, e o manifesto é somente um
índice; o acesso aos bytes ainda passa pela API autenticada.

## Consequências

O caminho central funciona imediatamente em web/PWA e desktop: o celular faz
login com a mesma conta e recebe os mesmos vínculos do Supabase. A camada P2P
pode ser adicionada depois atrás do `asset_id`, sem alterar a estrutura das
questões. O snapshot calcula hashes dos arquivos referenciados, portanto uma
biblioteca muito grande pode exigir cache de hash quando a rede mesh entrar em
produção.
