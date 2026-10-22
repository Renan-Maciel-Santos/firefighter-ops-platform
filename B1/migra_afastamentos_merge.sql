-- ==========================================================================
-- MIGRAÇÃO: prepara b1.afastamentos para merge a partir do RELATÓRIO do SGP
-- ==========================================================================
-- Contexto: até 17/08/2026 os afastamentos vinham de raspagem da tela de gestão,
-- RE a RE (B1/afastamentos.py em Selenium, com login manual), parada desde 04/03.
-- O SGP passou a ter /Relatorios/Afastamentos com export Excel, o que permite
-- carregar a unidade inteira de uma vez.
--
-- Três problemas do modelo antigo impedem o merge:
--
--   1. A UNIQUE incluía data_fim e origem_informacao. Como 1.297 linhas têm
--      data_fim NULL e o Postgres trata cada NULL como distinto, a constraint
--      não segurava nada: cada reexecução reinseria as mesmas linhas. Resultado
--      medido: 341 grupos duplicados.
--   2. origem_informacao (P1 / PERÍCIAS) NÃO existe no relatório. Mantê-la na
--      chave impediria qualquer casamento com o histórico.
--   3. observacao estava gravada como '' em 20.911 de 25.201 linhas — a raspagem
--      antiga não conseguia ler o campo. Com '' e NULL misturados, a detecção de
--      mudança acusaria diferença eterna.
--
-- A chave natural de um afastamento é (re, motivo, data_inicio): a mesma pessoa
-- não inicia dois afastamentos do mesmo tipo no mesmo dia. data_fim, dias e
-- observação são carga mutável (prorrogação, correção de documento).
-- ==========================================================================

\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------- backup
-- Acima: 25 mil linhas de produção. O backup fica no schema, não em arquivo solto.
DROP TABLE IF EXISTS b1.afastamentos_bkp_20260817;
CREATE TABLE b1.afastamentos_bkp_20260817 AS SELECT * FROM b1.afastamentos;

\echo '--- backup criado ---'
SELECT count(*) AS linhas_no_backup FROM b1.afastamentos_bkp_20260817;

-- ------------------------------------------------- normaliza '' para NULL
-- Acima: Sem isto, '' (banco) vs NULL (relatório sem observação) diferem para
-- sempre e nenhuma linha jamais "passa batido" na comparação.
UPDATE b1.afastamentos SET observacao = NULL WHERE observacao = '';
UPDATE b1.afastamentos SET opm = NULL WHERE opm = '';
UPDATE b1.afastamentos SET motivo = NULL WHERE motivo = '';

-- ------------------------------------------------------------- deduplica
-- Acima: Mantém a linha mais informativa de cada chave: prefere a que tem
-- data_fim, depois a que tem quantidade_dias, depois a de observação mais
-- longa, e por fim o menor id como desempate determinístico.
DELETE FROM b1.afastamentos a
USING (
    SELECT id FROM (
        SELECT id,
               row_number() OVER (
                   PARTITION BY re, motivo, data_inicio
                   ORDER BY (data_fim IS NULL),
                            (quantidade_dias IS NULL),
                            length(coalesce(observacao, '')) DESC,
                            id
               ) AS rn
        FROM b1.afastamentos
    ) x WHERE rn > 1
) d
WHERE a.id = d.id;

\echo '--- deduplicado ---'
SELECT count(*) AS linhas_restantes FROM b1.afastamentos;

-- ------------------------------------------------------- troca a UNIQUE
ALTER TABLE b1.afastamentos DROP CONSTRAINT uq_afastamento;
ALTER TABLE b1.afastamentos
    ADD CONSTRAINT uq_afastamento UNIQUE (re, motivo, data_inicio);

-- --------------------------------------------------- colunas do relatório
-- Acima: O relatório traz Posto/Grad, Nome, Quadro e Condição. Não são redundantes
-- com b1.efetivo: aquela tabela só tem os 502 militares ATUAIS da unidade, e o
-- relatório de afastamentos alcança também INATIVO, AGREGADO, EXCLUIDO e FALECIDO —
-- gente para quem este passa a ser o único registro de nome e posto.
ALTER TABLE b1.afastamentos ADD COLUMN IF NOT EXISTS posto_grad    text;
ALTER TABLE b1.afastamentos ADD COLUMN IF NOT EXISTS nome          text;
ALTER TABLE b1.afastamentos ADD COLUMN IF NOT EXISTS quadro        text;
ALTER TABLE b1.afastamentos ADD COLUMN IF NOT EXISTS condicao      text;

-- Acima: Carimbo de quando a linha mudou pela última vez — permite ao painel de
-- frescor (fase 3) distinguir "carregado hoje" de "sem alteração há meses".
ALTER TABLE b1.afastamentos ADD COLUMN IF NOT EXISTS atualizado_em timestamptz;

-- Acima: Índice para a consulta mais comum da B.I.A. (afastamentos de um militar)
CREATE INDEX IF NOT EXISTS ix_afastamentos_re ON b1.afastamentos (re);

\echo '--- estado final ---'
SELECT conname, pg_get_constraintdef(oid)
  FROM pg_constraint WHERE conrelid = 'b1.afastamentos'::regclass AND contype = 'u';

COMMIT;
