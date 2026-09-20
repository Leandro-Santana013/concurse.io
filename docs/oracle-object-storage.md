# Oracle Object Storage para mídia de provas

O bucket `concurseio-media` é mantido privado. O desktop e o mobile chamam a
API autenticada do concurse.io; nenhum aplicativo recebe OCID, fingerprint ou
chave privada da OCI.

## Fluxo

1. O usuário entra com Google e a API resolve a sessão.
2. `UserExam` decide quais provas aparecem na biblioteca.
3. A API consulta `questions` e valida a referência da imagem antes de servir
   `GET /api/v1/exams/{exam_id}/media/{filename}`.
4. Se o objeto existir em OCI, a API o lê do bucket. Enquanto a migração não
   terminar, o arquivo local em `static/images/questions/` continua como
   fallback.
5. O worker de ingestão sincroniza PDFs canônicos em
   `exams/{exam_id}/prova.pdf` e `exams/{exam_id}/gabarito.pdf`, e imagens em
   `questions/{filename}`.

O endpoint de PDF segue o mesmo controle de acesso em
`/api/v1/exams/{exam_id}/pdf/prova` e
`/api/v1/exams/{exam_id}/pdf/gabarito`.

## Configuração do servidor

Preencha os valores em `deploy/oracle/.env` ou no secret manager do host da
API. O namespace aparece nos detalhes do bucket. A PEM deve ficar somente no
servidor; é possível informar `OCI_OBJECT_STORAGE_PRIVATE_KEY_FILE` em vez de
colocar o conteúdo em uma variável.

```dotenv
OCI_OBJECT_STORAGE_NAMESPACE=<namespace-da-tenancy>
OCI_OBJECT_STORAGE_BUCKET=concurseio-media
OCI_OBJECT_STORAGE_REGION=sa-saopaulo-1
OCI_OBJECT_STORAGE_TENANCY=<ocid-da-tenancy>
OCI_OBJECT_STORAGE_USER=<ocid-do-usuario-de-api>
OCI_OBJECT_STORAGE_FINGERPRINT=<fingerprint-da-chave>
OCI_OBJECT_STORAGE_PRIVATE_KEY_FILE=/run/secrets/oci_api_key.pem
OCI_OBJECT_STORAGE_QUESTION_PREFIX=questions
```

Crie um usuário técnico com uma chave de API e coloque-o em um grupo que tenha
acesso somente a esse bucket. Na política do compartimento, use o nome real do
compartimento e do grupo:

```text
Allow group concurseio-storage to read buckets in compartment <compartimento>
Allow group concurseio-storage to manage objects in compartment <compartimento> where target.bucket.name='concurseio-media'
```

O OCID do usuário, o fingerprint e a PEM ficam apenas no host da API. O
desktop e o mobile recebem somente `VITE_API_ORIGIN` e nunca acessam o bucket
com uma chave de serviço.

O pacote `oci` é instalado junto com a API. Sem essas variáveis, o projeto
continua funcionando com os arquivos locais, o que permite migrar os artefatos
sem interromper as provas existentes.

Para migrar os arquivos já extraídos, execute primeiro o plano:

```powershell
python scripts/sync_oracle_storage.py
```

Depois de revisar os caminhos, execute com `--apply`. O script é separado da
API e não abre uma porta de upload pública.

## Aplicativos

Os builds Tauri usam somente `VITE_API_ORIGIN`, por exemplo:

```dotenv
VITE_API_ORIGIN=https://api.exemplo.com
```

O desktop mantém o cache local para leitura offline; o mobile usa o diretório
privado do aplicativo. O login Google e a atribuição de provas continuam no
servidor, portanto uma prova atribuída em outro dispositivo aparece após a
sincronização da biblioteca.
