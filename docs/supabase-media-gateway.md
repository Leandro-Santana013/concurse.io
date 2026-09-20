# Supabase media gateway

The `media-gateway` Edge Function authenticates the Supabase session and then
reads or writes objects in the private OCI bucket through scoped OCI
pre-authenticated request (PAR) URLs. The desktop and mobile builds never
receive OCI API keys.

Configure these Edge Function secrets:

- `OCI_MEDIA_READ_PAR_URL`: a read PAR scoped to the `questions/` and `exams/`
  prefixes (or to the bucket if the application enforces the prefixes).
- `OCI_MEDIA_WRITE_PAR_URL`: optional write PAR for uploads. Do not configure
  this in a public build unless uploads are needed.
- `OCI_MEDIA_ALLOWED_PREFIXES`: optional comma-separated prefixes; it defaults
  to `questions/,exams/`.
- `MEDIA_CORS_ORIGIN`: optional allowed application origin; it defaults to `*`.

The client sends `Authorization: Bearer <Supabase access token>` and requests
`/functions/v1/media-gateway?path=questions/<object>`. The function validates
the user with Supabase Auth, then streams the object from OCI. A device with no
network continues using its local cache and synchronizes when connectivity is
restored.
