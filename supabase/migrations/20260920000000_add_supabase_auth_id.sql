-- Liga a identidade do Supabase Auth ao usuário interno do concurse.io.
-- A coluna é nullable para manter compatibilidade com contas que ainda usam
-- o fluxo Google legado da API.
alter table if exists public.users
  add column if not exists supabase_auth_id varchar(200);

create unique index if not exists ix_users_supabase_auth_id
  on public.users (supabase_auth_id)
  where supabase_auth_id is not null;
