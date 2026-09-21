-- O app-gateway usa o papel service_role para ler e gravar a biblioteca
-- depois de validar o JWT do usuário. Alguns projetos existentes perderam
-- os grants padrão do schema public, causando "permission denied for schema
-- public" mesmo com o bypass de RLS ativo.
grant usage on schema public to service_role;
grant all privileges on all tables in schema public to service_role;
grant all privileges on all sequences in schema public to service_role;
grant all privileges on all functions in schema public to service_role;

alter default privileges for role postgres in schema public
  grant all privileges on tables to service_role;
alter default privileges for role postgres in schema public
  grant all privileges on sequences to service_role;
alter default privileges for role postgres in schema public
  grant all privileges on functions to service_role;
