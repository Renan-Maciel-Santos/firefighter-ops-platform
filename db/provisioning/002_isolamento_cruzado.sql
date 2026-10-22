-- ============================================================
-- 002_isolamento_cruzado.sql
-- Impede que a role do n8n alcance os demais databases do cluster.
--
-- O 001 fecha o database do n8n para quem vem de fora. Falta a direcao
-- contraria: por padrao PUBLIC tem CONNECT em todo database, entao a
-- role n8n conectaria em `11gb` e `evolution_api` mesmo sem ser dona
-- deles. A correcao e revogar CONNECT de PUBLIC nesses dois.
--
-- RISCO NESTE CLUSTER: BAIXO. Levantado em 2026-08-31, o cluster tem uma
-- unica role com LOGIN -- `admin`, SUPERUSER -- e e ela que o webapp
-- (:8000) e a evolution_11gb usam. Superuser ignora a checagem de
-- CONNECT, entao o REVOKE abaixo nao afeta nada que roda hoje.
--
-- Rode a checagem do passo 1 assim mesmo antes de aplicar: se alguma
-- role NAO-superuser tiver aparecido no cluster desde entao, ela perde
-- o acesso na hora.
--
-- Variaveis esperadas:
--   :outro_db   database a fechar (rodar uma vez por database)
-- ============================================================

\set ON_ERROR_STOP on

-- ------------------------------------------------------------
-- PASSO 1 -- CHECAGEM (nao altera nada; rode e leia a saida)
-- ------------------------------------------------------------
-- datacl vazio/NULL = database no padrao permissivo, PUBLIC conecta.
SELECT datname,
       pg_catalog.pg_get_userbyid(datdba) AS owner,
       datacl
FROM pg_database
WHERE datistemplate = false
ORDER BY datname;

-- Roles com LOGIN. Se aparecer alguma sem `rolsuper`, descubra o que ela
-- usa antes de revogar.
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole
FROM pg_roles
WHERE rolcanlogin
ORDER BY rolname;

-- Esperado em 2026-08-31: apenas `admin` (superuser) e a role nova do
-- n8n criada pelo 001.

-- ------------------------------------------------------------
-- PASSO 2 -- REVOGACAO
-- ------------------------------------------------------------
-- Rodar uma vez com :outro_db=11gb e outra com :outro_db=evolution_api.
--
-- APLICADO em 2026-08-31 nos dois databases, depois da checagem acima
-- confirmar que so `admin` (superuser) e `n8n_bia_user` tem LOGIN, e que
-- as conexoes abertas do evolution_api eram todas de `admin`.
--
-- Idempotente: revogar de novo o que ja foi revogado nao da erro.
REVOKE CONNECT ON DATABASE :"outro_db" FROM PUBLIC;

-- ------------------------------------------------------------
-- VERIFICACAO
-- ------------------------------------------------------------
-- Deve FALHAR com: FATAL: permission denied for database
--   psql "postgresql://<n8n_user>:<senha>@localhost:5432/11gb" -c "SELECT 1"
--
-- Deve PASSAR (admin e superuser):
--   psql -U admin -d 11gb -c "SELECT 1"

-- ------------------------------------------------------------
-- ROLLBACK
-- ------------------------------------------------------------
-- Devolve o padrao permissivo do Postgres para esse database:
--
-- GRANT CONNECT ON DATABASE :"outro_db" TO PUBLIC;
