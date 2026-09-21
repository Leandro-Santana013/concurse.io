# Oracle Object Storage para mídia de provas

O bucket `concurseio-media` é mantido privado. O desktop e o mobile chamam as
Edge Functions autenticadas do Supabase; nenhum aplicativo recebe OCID,
fingerprint ou chave privada da OCI. Não é necessário criar VM, DNS ou API
FastAPI para este fluxo.

## Fluxo

1. O usuário entra com Google pelo Supabase Auth.
2. `app-gateway` resolve a sessão e decide quais provas aparecem na biblioteca.
3. A `media-gateway` valida o mesmo token antes de ler ou gravar no bucket.
4. Um PDF selecionado no aplicativo é gravado em `exams/uploads/<sha256>.pdf`.
5. O JSON extraído é gravado no banco; imagens incorporadas como Data URL são
   convertidas e gravadas em `questions/` antes de salvar as referências.
6. Artefatos locais que ainda usam `/static/images/questions/<arquivo>` devem
   ser enviados junto com o JSON para o prefixo `questions/` para que a
   referência fique disponível em todos os dispositivos.

Links `oci://exams/...` persistidos pelo importador são convertidos pelo
`app-gateway` para o PAR de leitura do prefixo `exams/`.

## Configuração do servidor

As Edge Functions usam PARs escopadas e guardadas como secrets do projeto
Supabase. Uma PAR de leitura não permite upload; por isso a ingestão requer
PARs de escrita separadas. O namespace aparece nos detalhes do bucket.

```dotenv
OCI_MEDIA_READ_QUESTIONS_PAR_URL=<PAR-somente-leitura-questions>
OCI_MEDIA_READ_EXAMS_PAR_URL=<PAR-somente-leitura-exams>
OCI_MEDIA_WRITE_QUESTIONS_PAR_URL=<PAR-escrita-questions>
OCI_MEDIA_WRITE_EXAMS_PAR_URL=<PAR-escrita-exams>
OCI_MEDIA_ALLOWED_PREFIXES=questions/,exams/
```

Crie quatro PARs no bucket `concurseio-media`, limitando cada uma ao prefixo e
à operação indicada pelo nome. Cole as quatro URLs somente na tela **Edge
Function Secrets** do projeto Supabase. O OCID, fingerprint e qualquer chave
privada da OCI não entram nos aplicativos.

## Login Supabase

O projeto Supabase também está configurado como provedor Google. Nos builds,
preencha a URL do projeto e a chave publicável:

```dotenv
SUPABASE_URL=https://pvojiokewtteroaraykk.supabase.co
SUPABASE_PUBLISHABLE_KEY=<chave-publicável>
```

O frontend inicia o OAuth diretamente pelo Supabase. O access token é enviado
às Edge Functions `app-gateway` e `media-gateway`, que validam a sessão e
consultam a biblioteca ou o bucket. Não há troca por cookie de uma API externa.

Antes de ativar o bridge em um banco existente, aplique
`supabase/migrations/20260920000000_add_supabase_auth_id.sql` no SQL Editor ou
deixe a migração aditiva do `init_db()` executá-la no primeiro start da API.
Os builds desktop e mobile mantêm o callback privado já existente; a conta
Google continua apontando para o mesmo usuário interno.

Sem as PARs de escrita, uma tentativa de upload retorna `503` e não cria um
registro incompleto. Sem as PARs de leitura, as referências permanecem
privadas e os aplicativos não conseguem exibi-las até que os secrets sejam
configurados.

Para migrar os arquivos já extraídos, execute primeiro o plano:

```powershell
python scripts/sync_oracle_storage.py
```

Depois de revisar os caminhos, execute com `--apply`. O script é separado da
API e não abre uma porta de upload pública.

## Aplicativos

Os builds Tauri usam as Edge Functions do projeto:

```dotenv
VITE_SUPABASE_URL=https://pvojiokewtteroaraykk.supabase.co
VITE_SUPABASE_FUNCTIONS_URL=https://pvojiokewtteroaraykk.supabase.co/functions/v1
```

O desktop mantém o cache local para leitura offline; o mobile usa o diretório
privado do aplicativo. O login Google e a atribuição de provas ficam no
Supabase, portanto uma prova atribuída em outro dispositivo aparece após a
sincronização da biblioteca.
