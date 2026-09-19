# Hospedagem no Oracle Cloud Always Free

Esta implantação usa uma VM OCI Ampere A1 Flex com Docker Compose. O FastAPI serve o frontend React já compilado e o Caddy termina HTTPS e renova o certificado automaticamente. O app usa o banco Supabase já configurado no projeto; não cria um PostgreSQL vazio na VM nem copia dados. PDFs, imagens extraídas e cache usam volumes persistentes.

## Limites e escolha da VM

Na oferta Always Free atual, a cota Ampere A1 equivale a **2 OCPUs e 12 GB de RAM** por mês; o armazenamento Block Volume é **200 GB no total**, contando discos de boot e volumes de dados. A VM precisa ser criada na região inicial (home region) da tenancy. Escolha essa região com cuidado antes de criar a conta. A Oracle pode não ter capacidade A1 disponível no momento; nesse caso, tente outro domínio de disponibilidade ou aguarde. Consulte os limites atuais no [guia oficial Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

Crie uma VM `VM.Standard.A1.Flex` com **2 OCPUs e 12 GB**, imagem Ubuntu ARM64 elegível para Always Free e disco de boot de **50 GB**. Isso deixa espaço dentro da cota total de 200 GB para o boot volume e eventuais dados adicionais. Não crie recursos que não estejam identificados como Always Free na Console.

Na criação da VM, associe uma chave pública SSH e guarde a chave privada correspondente em local seguro; ela não deve entrar no repositório nem no `.env`.

Considere que a Oracle pode recuperar VMs Always Free classificadas como ociosas: para A1, a documentação define isso como CPU p95, rede e memória abaixo de 20% durante sete dias. Um site com pouco tráfego pode atingir esse critério; monitore a instância e mantenha backups fora dela.

## Rede e domínio

Na VCN, use uma subnet pública com Internet Gateway e IP público na VM. Libere TCP 80 e 443 para a internet. Restrinja SSH (TCP 22) ao seu IP. Mantenha as portas 5432 e 8000 fechadas: o Compose não as publica no host.

O hostname escolhido é `concurse.duckdns.org`; não é necessário contratar DNS. Depois que a VM receber o IPv4 público, configure no DuckDNS o subdomínio `concurse` para apontar para esse IP. Confirme que o nome resolve para o IP da VM e que as portas 80/443 estão acessíveis antes de iniciar o Caddy. Não compartilhe nem grave o token DuckDNS no repositório.

## Deploy

Instale Docker Engine e o plugin Docker Compose no Ubuntu usando a [documentação oficial do Docker](https://docs.docker.com/engine/install/ubuntu/). Transfira para a VM o worktree atual, incluindo as alterações locais que ainda não estão no Git. Inclua também `pdfs/` e `static/images/questions/`: essas pastas são ignoradas pelo Git, mas contêm arquivos usados pela ingestão e pela exibição das questões. Não transfira o `.env` raiz; configure apenas os valores necessários em `deploy/oracle/.env`.

```sh
cd /caminho/do/concurse.io/deploy/oracle
cp .env.example .env
chmod 600 .env
```

Edite `.env` somente para preencher as credenciais e chaves necessárias. Copie somente `DATABASE_URL` do `.env` existente para manter o Supabase atual. Preserve o valor existente de `FLASK_SECRET_KEY` em `SESSION_SECRET` e `USER_DATA_ENCRYPTION_KEY`; não gere chaves novas para uma instalação com dados existentes. Informe também as credenciais OAuth atuais do Google, se o login for usado. No Google Cloud Console, cadastre `https://concurse.duckdns.org` como origem JavaScript autorizada e exatamente `https://concurse.duckdns.org/api/v1/auth/google/callback` como URI de redirecionamento. Para uso de produção, verifique `concurse.duckdns.org` no Google Search Console e cadastre-o entre os domínios autorizados do consentimento; se o Google solicitar um TXT, o DuckDNS permite configurá-lo. Mantenha o token DuckDNS na sua conta e não o envie neste repositório.

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

## Compartilhamento centralizado

O compartilhamento entre dispositivos usa a biblioteca central do projeto. A
conta Google identifica o usuário, `user_exams` vincula cada prova à biblioteca
correta e o snapshot da biblioteca entrega os metadados e as imagens protegidas
pela API. O Supabase continua sendo o banco de dados e o armazenamento da
aplicação; não há leases de dispositivos, descoberta de pares ou volume de
blocos de distribuição na VM.

O aplicativo desktop mantém uma cópia local somente para acelerar a leitura e
permitir reabrir provas sincronizadas quando a conexão cair. Uma prova nova ou
uma atribuição feita em outro dispositivo aparece depois da próxima
sincronização central.

O Docker inicializa um volume nomeado vazio com os arquivos que já existem naquele caminho na imagem. Assim, no primeiro deploy, os volumes `exam_pdfs` e `question_images` recebem o conteúdo local incluído no build; depois disso, eles persistem e não são sobrescritos nas atualizações. Consulte a [documentação oficial de volumes Docker](https://docs.docker.com/engine/storage/volumes/).

Para atualizar o código depois de copiá-lo para a VM, atualize o repositório e execute novamente:

```sh
docker compose --env-file .env -f compose.yml up -d --build
```

Faça backup periódico do Supabase e dos volumes `exam_pdfs` e `question_images`. Não use `docker compose down -v` em uma instalação com dados: a opção `-v` remove os volumes persistentes.
