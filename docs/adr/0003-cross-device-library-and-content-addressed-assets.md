# ADR 0003: Biblioteca centralizada entre dispositivos

## Status

Accepted

## Decision

Os dispositivos compartilham provas pela biblioteca central da aplicação. O
login Google identifica a conta, `user_exams` define as provas atribuídas e o
Supabase mantém os registros e os arquivos. O desktop pode guardar uma cópia
local para leitura offline, mas não anuncia peers nem transfere blocos entre
computadores.

## Consequences

- Não há descoberta UDP, servidor TCP local, leases de dispositivos ou
  endpoints `/mesh/*`.
- A autorização continua centralizada nas políticas da aplicação e nas rotas
  protegidas de prova e mídia.
- Uma atribuição feita em outro dispositivo fica disponível após a próxima
  sincronização com a biblioteca central.
