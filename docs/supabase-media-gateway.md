# Supabase gateways

O aplicativo desktop e o mobile não dependem de uma API FastAPI, VM ou DNS
externo. A Edge Function `app-gateway` mantém os contratos de biblioteca,
provas, tentativas e estatísticas usados pela interface, consultando o banco
Supabase com o token da sessão. A `media-gateway` lê os artefatos do Oracle.

As duas funções são hospedadas no próprio projeto Supabase.

## Media gateway

The `media-gateway` Edge Function authenticates the Supabase session and then
reads or writes objects in the private OCI bucket through scoped OCI
pre-authenticated request (PAR) URLs. The desktop and mobile builds never
receive OCI API keys.

Configure these Edge Function secrets:

- `OCI_MEDIA_READ_QUESTIONS_PAR_URL`: read PAR scoped to `questions/`.
- `OCI_MEDIA_READ_EXAMS_PAR_URL`: read PAR scoped to `exams/`.
- `OCI_MEDIA_WRITE_QUESTIONS_PAR_URL`: write PAR scoped to `questions/`.
- `OCI_MEDIA_WRITE_EXAMS_PAR_URL`: write PAR scoped to `exams/`.
- `OCI_MEDIA_READ_PAR_URL` and `OCI_MEDIA_WRITE_PAR_URL` remain accepted as
  compatibility fallbacks, but the prefix-specific secrets are preferred.
- `OCI_MEDIA_ALLOWED_PREFIXES`: optional comma-separated prefixes; it defaults
  to `questions/,exams/`.
- `MEDIA_CORS_ORIGIN`: optional allowed application origin; it defaults to `*`.

The client sends `Authorization: Bearer <Supabase access token>` and requests
`/functions/v1/media-gateway?path=questions/<object>`. The function validates
the user with Supabase Auth, then streams or uploads the object to OCI. The
online import dialog accepts a PDF/JSON plus optional extracted image files;
path references in the JSON are rewritten to their uploaded `questions/`
objects. Data URLs embedded in the JSON are uploaded by `app-gateway` itself.
A device with no network continues using its local cache and synchronizes when
connectivity is restored.
