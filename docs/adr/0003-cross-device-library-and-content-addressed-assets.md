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
pode usar os endpoints autenticados `/mesh/announce`, `/mesh/providers` e
`/mesh/fetch`: o desktop anuncia um lease curto e o servidor procura peers da
mesma conta antes de buscar a mídia central. O peer só serve blobs por
`sha256:<digest>` e o proxy descarta qualquer resposta cujo hash não confira.

O snapshot hidrata o cache `MESH_CONTENT_DIR` do nó local. Portanto, a primeira
abertura de uma prova torna as imagens referenciadas disponíveis para anúncio;
o nome original do PNG não entra na chave de armazenamento. O lease expira
sozinho e pode ser renovado pelo desktop, sem deixar endpoints antigos ativos.

O transporte exige que o endpoint anunciado seja alcançável pelo servidor
(rede local, VPN ou encaminhamento HTTPS). NAT sem rota direta continua sendo
um caso para um relay/WebRTC posterior; a verificação de conteúdo e a
autorização da conta já ficam prontas para essa troca.

Para reduzir latência e dependência do origin, o transporte agora possui um
manifesto de blocos. O manifesto usa blocos de 1 MiB por padrão, com hash
SHA-256 individual e hash completo do asset. O `fetch` consulta todos os peers
disponíveis, baixa índices em paralelo com um limite de conexões, valida cada
bloco e grava o resultado em uma troca atômica. Falhas são tentadas em outro
peer e, por compatibilidade, o download inteiro antigo continua disponível.

O cache local é consultado antes da descoberta e um arquivo montado com sucesso
entra no conjunto de providers do nó. A política de cache é privada porque o
isolamento por `user_id` continua sendo obrigatório; a mesma prova pode ser
deduplicada por hash dentro da conta sem virar um objeto público. O tamanho do
bloco, concorrência, pool HTTP e timeouts são ajustáveis por variáveis `MESH_*`
para respeitar os limites de CPU, memória e banda da VM.

Clientes desktop podem obter um ticket curto em `/mesh/ticket/{asset_id}`. O
ticket entrega apenas URLs e tokens limitados ao asset e ao node; o segredo
compartilhado nunca deixa o origin. Assim, o cliente busca diretamente os
blocos dos peers quando a topologia permite e usa `/mesh/fetch` como fallback.
