-- ============================================================
-- app.usuarios: troca de senha obrigatória no primeiro acesso
--
-- POR QUE
-- Até 09/09/2026 o sistema tinha UM usuário ("Administrador") e nenhuma
-- forma de criar outro nem de trocar senha. Compartilhar o painel nesse
-- estado significaria todo mundo entrando na mesma conta, sem rastro de
-- quem viu o quê — num sistema com dados de pessoal, saúde e disciplina.
--
-- O cadastro de um usuário gera senha provisória, exibida uma única vez no
-- terminal de quem cadastrou. Sem esta coluna, essa senha provisória vira
-- definitiva e circula por WhatsApp até alguém perceber.
--
-- Usuários que já existem entram com `false`: ninguém é obrigado a trocar
-- retroativamente. Quem for criado pelo script nasce com `true`.
-- ============================================================

ALTER TABLE app.usuarios
    ADD COLUMN IF NOT EXISTS deve_trocar_senha BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN app.usuarios.deve_trocar_senha IS
    'Força a troca de senha antes de liberar o painel. Marcado no cadastro e '
    'no reset; limpo quando o próprio usuário troca em /auth/trocar-senha.';
