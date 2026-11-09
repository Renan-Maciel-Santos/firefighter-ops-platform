-- ============================================================
-- Abas por usuário (09/11/2026)
--
-- Até aqui o praça via exatamente as abas da seção dele (acesso.py,
-- SECAO_ABAS). O Cmt quer ajustar pessoa a pessoa pelo painel, na aba
-- "Permissões". Oficiais e o admin continuam vendo tudo — a coluna não vale
-- para eles.
--
--   NULL          segue o padrão da seção (comportamento de antes)
--   '{a,b,...}'   exatamente estas abas
--
-- A aba SJD só pode ser dada a praça da seção SJD — o acesso.py filtra
-- mesmo que alguém grave à mão aqui.
-- ============================================================

ALTER TABLE app.usuarios
    ADD COLUMN IF NOT EXISTS abas_personalizadas TEXT[];

COMMENT ON COLUMN app.usuarios.abas_personalizadas IS
    'Abas do praça escolhidas pelo admin na aba Permissões. NULL = padrão da seção. '
    'Ignorado para admin e oficial. SJD só vale para praça da seção SJD.';
