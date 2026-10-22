-- ============================================================
-- Novo modelo de acesso: admin, oficial, praça (com seção)
--
-- O modelo anterior — comando / administrativo / operacional — misturava
-- posto e função numa coisa só, e não tinha como dizer "este praça vê a
-- seção dele". Decidido em 09/09/2026:
--
--   admin    apenas o RE 900003. Tudo, mais a gestão de usuários.
--   oficial  todas as abas, menos a gestão de usuários.
--   praca    apenas as abas da seção escolhida no cadastro.
--
-- Praça de SGB não recebe login: são 421 dos 501, atendidos pela B.I.A. no
-- WhatsApp, que já é o canal deles. Menos conta para gerenciar e menos
-- superfície exposta.
--
-- A seção é escolhida no cadastro, não derivada do RE. Derivar seria
-- automático e se atualizaria sozinho na captura do SGP, mas quem estivesse
-- com o código errado no SGP — como o 1º Sgt Fulano em 09/09 — ficaria sem
-- aba nenhuma sem ninguém entender por quê.
--
-- Os valores antigos do enum ficam: o Postgres não remove valor de enum sem
-- recriar o tipo, e recriar exigiria derrubar a coluna. Eles deixam de ser
-- usados; o app.py não os aceita mais no cadastro.
-- ============================================================

ALTER TYPE app.perfil_enum ADD VALUE IF NOT EXISTS 'admin';
ALTER TYPE app.perfil_enum ADD VALUE IF NOT EXISTS 'oficial';
ALTER TYPE app.perfil_enum ADD VALUE IF NOT EXISTS 'praca';

-- Seção do praça. NULL para admin e oficial, que veem tudo de qualquer jeito.
ALTER TABLE app.usuarios
    ADD COLUMN IF NOT EXISTS secao TEXT;

COMMENT ON COLUMN app.usuarios.secao IS
    'Seção do EM que o praça enxerga (B/1 e B/5, B/3, B/4, St UGE, COBOM, SJD). '
    'NULL para admin e oficial. Escolhida no cadastro, não derivada do RE.';
