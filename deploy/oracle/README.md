# Hospedagem no Oracle Cloud Always Free

Esta implantação usa uma VM OCI Ampere A1 Flex com Docker Compose. O FastAPI serve o frontend React já compilado e o Caddy termina HTTPS e renova o certificado automaticamente. O app usa o banco Supabase já configurado no projeto; não cria um PostgreSQL vazio na VM nem copia dados. PDFs, imagens extraídas e cache usam volumes persistentes.

## Limites e escolha da VM

Na oferta Always Free atual, a cota Ampere A1 equivale a **2 OCPUs e 12 GB de RAM** por mês; o armazenamento Block Volume é **200 GB no total**, contando discos de boot e volumes de dados. A VM precisa ser criada na região inicial (home region) da tenancy. Escolha essa região com cuidado antes de criar a conta. A Oracle pode não ter capacidade A1 disponível no momento; nesse caso, tente outro domínio de disponibilidade ou aguarde. Consulte os limites atuais no [guia oficial Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

Crie uma VM `VM.Standard.A1.Flex` com **2 OCPUs e 12 GB**, imagem Ubuntu ARM64 elegível para Always Free e disco de boot de **50 GB**. Isso deixa espaço dentro da cota total de 200 GB para o boot volume e um Block Volume de dados de **100 GB**, mantendo 50 GB de margem para crescimento. Não crie recursos que não estejam identificados como Always Free na Console.

Crie o Block Volume na mesma região, compartimento e domínio de disponibilidade da VM. Use a opção de anexação paravirtualizada, anexe-o à instância e aguarde o dispositivo aparecer no Ubuntu. A OCI normalmente expõe o primeiro volume como `/dev/oracleoci/oraclevdb`, mas confirme o caminho na página de anexos da instância antes de formatar.

Na criação da VM, associe uma chave pública SSH e guarde a chave privada correspondente em local seguro; ela não deve entrar no repositório nem no `.env`.

Considere que a Oracle pode recuperar VMs Always Free classificadas como ociosas: para A1, a documentação define isso como CPU p95, rede e memória abaixo de 20% durante sete dias. Um site com pouco tráfego pode atingir esse critério; monitore a instância e mantenha backups fora dela.

## Rede e domínio

Na VCN, use uma subnet pública com Internet Gateway e IP público na VM. Libere TCP 80 e 443 para a internet. Restrinja SSH (TCP 22) ao seu IP. Mantenha as portas 5432 e 8000 fechadas: o Compose não as publica no host.

O hostname escolhido é `concurse.duckdns.org`; não é necessário contratar DNS. Depois que a VM receber o IPv4 público, configure no DuckDNS o subdomínio `concurse` para apontar para esse IP. Confirme que o nome resolve para o IP da VM e que as portas 80/443 estão acessíveis antes de iniciar o Caddy. Não compartilhe nem grave o token DuckDNS no repositório.

## Deploy

Instale Docker Engine e o plugin Docker Compose no Ubuntu usando a [documentação oficial do Docker](https://docs.docker.com/engine/install/ubuntu/). Transfira para a VM o worktree atual, incluindo as alterações locais que ainda não estão no Git. Inclua também `pdfs/` e `static/images/questions/`: essas pastas são ignoradas pelo Git, mas contêm arquivos usados pela ingestão e pela exibição das questões. Não transfira o `.env` raiz; configure apenas os valores necessários em `deploy/oracle/.env`.

Prepare o Block Volume antes de iniciar o Compose:

```sh
cd /caminho/do/concurse.io
sudo bash deploy/oracle/prepare-persistent-storage.sh /dev/oracleoci/oraclevdb /srv/concurse-data
```

O script só cria `ext4` quando o dispositivo está sem filesystem. Se o volume já tiver um filesystem, ele não o formata; monta-o usando UUID no `/etc/fstab` com `nofail` e prepara `pdfs`, `question-images`, `parse-cache`, `caddy-data` e `caddy-config`.

```sh
cd /caminho/do/concurse.io/deploy/oracle
cp .env.example .env
chmod 600 .env
```

Edite `.env` somente para preencher as credenciais e chaves necessárias. Preserve `CONCURSE_DATA_ROOT=/srv/concurse-data`. Copie somente `DATABASE_URL` do `.env` existente para manter o Supabase atual. Preserve o valor existente de `FLASK_SECRET_KEY` em `SESSION_SECRET` e `USER_DATA_ENCRYPTION_KEY`; não gere chaves novas para uma instalação com dados existentes. Informe também as credenciais OAuth atuais do Google, se o login for usado. No Google Cloud Console, cadastre `https://concurse.duckdns.org` como origem JavaScript autorizada e exatamente `https://concurse.duckdns.org/api/v1/auth/google/callback` como URI de redirecionamento. Para uso de produção, verifique `concurse.duckdns.org` no Google Search Console e cadastre-o entre os domínios autorizados do consentimento; se o Google solicitar um TXT, o DuckDNS permite configurá-lo. Mantenha o token DuckDNS na sua conta e não o envie neste repositório.

Guarde `deploy/oracle/.env` e suas cópias de segurança fora do Git. Não copie o `.env` raiz inteiro para a VM: ele pode conter credenciais que o container não usa.

Valide e inicie os serviços:

```sh
docker compose --env-file .env -f compose.yml config --quiet
docker compose --env-file .env -f compose.yml up -d --build
docker compose --env-file .env -f compose.yml ps
curl -fsS "https://${DOMAIN}/health"
```

Para acompanhar a inicialização:

```sh
docker compose --env-file .env -f compose.yml logs -f app caddy
```

## Dados e atualização

Este Compose conecta ao Supabase indicado por `DATABASE_URL`; não copia o `concurse.db` local nem cria um banco novo. No primeiro início, `init_db()` pode criar tabelas, adicionar colunas ausentes e atualizar registros legados da tabela `users` para proteger dados pessoais. A atualização de dados atinge `users`; ela não reescreve o texto nem o gabarito de provas e questões. Faça backup do Supabase e confirme a chave de criptografia antes de iniciar o app; a VM também precisa de acesso de saída ao endpoint do banco.

Os volumes `exam_pdfs`, `question_images` e `parser_cache` agora são volumes Docker com `bind` para o Block Volume (`/srv/concurse-data`). PDFs e imagens extraídos continuam sendo gravados nas mesmas pastas que o pipeline já usa, mas deixam de depender do disco de boot e sobrevivem a recriações do container e atualizações da imagem. `caddy-data` e `caddy-config` também ficam no mesmo volume para preservar os certificados HTTPS.

Se a VM já tinha os volumes Docker nomeados, faça uma cópia única para o Block Volume antes de subir o Compose com a configuração nova. Pare apenas o serviço da aplicação, preserve os volumes e copie o conteúdo:

```sh
docker compose --env-file .env -f compose.yml stop app
docker run --rm -v exam_pdfs:/from -v /srv/concurse-data/pdfs:/to alpine sh -c 'cp -a /from/. /to/'
docker run --rm -v question_images:/from -v /srv/concurse-data/question-images:/to alpine sh -c 'cp -a /from/. /to/'
docker run --rm -v parser_cache:/from -v /srv/concurse-data/parse-cache:/to alpine sh -c 'cp -a /from/. /to/'
```

Em uma VM nova, copie `pdfs/` e `static/images/questions/` para os diretórios correspondentes antes do primeiro `up`. Não use `docker compose down -v`: os nomes antigos continuam existindo como cópia de segurança até a migração ser conferida.

O Block Volume é o armazenamento de origem do backend. Mobile e desktop não montam esse disco nem recebem credenciais OCI: eles acessam PDFs e imagens pela API autenticada (`/api/v1/exams/{id}/media/{filename}`), e cada cliente pode manter seu próprio cache local para uso offline.

Para atualizar o código depois de copiá-lo para a VM, atualize o repositório e execute novamente:

```sh
docker compose --env-file .env -f compose.yml up -d --build
```

Faça backup periódico do Supabase e dos volumes `exam_pdfs` e `question_images`. Não use `docker compose down -v` em uma instalação com dados: a opção `-v` remove os volumes persistentes.
