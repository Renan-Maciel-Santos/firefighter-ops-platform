-- ============================================================
-- 001_n8n_database.sql
-- Database e role dedicados para o n8n proprio da B.I.A.
--
-- Cria a base propria do n8n no postgres_11gb, com role que so
-- enxerga o proprio database (sem acesso aos dados do painel).
--
-- PRE-CONDICOES
--   * Executar contra -d postgres, NAO contra o database 11gb.
--   * Executar como a role superuser do cluster (admin).
--   * A senha entra por variavel do psql (-v), nunca literal no arquivo.
--
-- IDEMPOTENTE: rodar duas vezes nao da erro. CREATE ROLE e CREATE
-- DATABASE sao guardados por NOT EXISTS via \gexec; REVOKE e GRANT sao
-- idempotentes por natureza.
--
-- NAO USA TRANSACAO: CREATE DATABASE nao roda dentro de BEGIN.
-- Rollback = DROP DATABASE / DROP ROLE (seguro enquanto o database
-- estiver vazio; depois do setup do n8n, ver o runbook).
--
-- Variaveis esperadas:
--   :n8n_user      role do n8n       (.env N8N_PG_USER)
--   :n8n_password  senha da role     (.env N8N_PG_PASS)
--   :n8n_db        database do n8n   (.env N8N_PG_DB)
-- ============================================================

\set ON_ERROR_STOP on

-- --- Role do n8n -------------------------------------------
-- Sem SUPERUSER, sem CREATEDB, sem CREATEROLE: so LOGIN.
-- Hoje o cluster tem uma unica role, `admin`, superuser, usada por
-- todos os sistemas. Esta e a primeira role de privilegio minimo aqui.
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'n8n_user', :'n8n_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'n8n_user')
\gexec

-- --- Database do n8n ---------------------------------------
-- Owner = a propria role: o n8n cria e migra o schema dele sozinho no
-- primeiro start, entao precisa de DDL dentro deste database, e so
-- dentro dele.
SELECT format('CREATE DATABASE %I OWNER %I', :'n8n_db', :'n8n_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'n8n_db')
\gexec

-- --- Fecha o padrao permissivo do Postgres ------------------
-- Por padrao PUBLIC pode conectar em qualquer database do cluster. Sem
-- este REVOKE, qualquer role futura conectaria no database do n8n e
-- leria as credenciais cifradas.
REVOKE CONNECT ON DATABASE :"n8n_db" FROM PUBLIC;
GRANT  CONNECT ON DATABASE :"n8n_db" TO :"n8n_user";

-- --- Schema public dentro do database do n8n ----------------
-- Do PG15 em diante o schema public deixou de ser gravavel por PUBLIC.
-- O owner do database ja herda CREATE via pg_database_owner; o GRANT
-- explicito deixa o script correto em qualquer versao. O cluster hoje
-- e postgres:16.
\connect :"n8n_db"
GRANT ALL ON SCHEMA public TO :"n8n_user";

-- Fim. O isolamento na direcao contraria (impedir que a role do n8n
-- alcance os databases 11gb e evolution_api) esta em
-- 002_isolamento_cruzado.sql.
