-- ==========================================================================
-- MIGRAÇÃO: marca afastamentos que sumiram do relatório do SGP
-- ==========================================================================
-- Contexto (13/10/2026): o merge de B1/afastamentos.py só insere e atualiza.
-- Quando um afastamento sai do SGP — férias reprogramadas, lançamento
-- cancelado ou corrigido —, a linha antiga ficava no banco para sempre. No
-- dia da migração, 6 dos 69 militares que o painel dava como afastados só
-- apareciam por uma linha que o SGP não tinha mais (quase todas férias de
-- outubro, de origem P1, remarcadas depois da raspagem antiga).
--
-- A linha NÃO é apagada: recebe a data em que deixou de vir no relatório. As
-- views passam a ignorá-la, e o ETL limpa a marca se o lançamento voltar.
-- Apagar perderia o histórico — e o relatório não cobre tudo o que está aqui
-- (ver as regras de escopo em B1/afastamentos.py, função marcar_ausentes).
-- ==========================================================================

\set ON_ERROR_STOP on

BEGIN;

ALTER TABLE b1.afastamentos ADD COLUMN IF NOT EXISTS ausente_no_sgp_desde date;

COMMENT ON COLUMN b1.afastamentos.ausente_no_sgp_desde IS
    'Data do primeiro relatório do SGP que deixou de trazer este afastamento. '
    'NULL = confirmado pelo SGP (ou fora do alcance do relatório). As views ignoram as marcadas.';

-- Mesma definição de antes, mais o filtro da marca.
CREATE OR REPLACE VIEW b1.v_afastamentos_dedup AS
 SELECT DISTINCT ON (re, (
        CASE
            WHEN motivo ~~* '%LIC%TRAT%SAUDE%'::text OR motivo ~~* '%LIC%TRAT%SAÚDE%'::text THEN 'LICENÇA TRAT. SAÚDE'::text
            ELSE motivo
        END), data_inicio, data_fim) re,
    opm,
        CASE
            WHEN motivo ~~* '%LIC%TRAT%SAUDE%'::text OR motivo ~~* '%LIC%TRAT%SAÚDE%'::text THEN 'LICENÇA TRAT. SAÚDE'::text
            ELSE motivo
        END AS motivo_grupo,
    motivo AS motivo_original,
    origem_informacao,
    data_inicio,
    data_fim,
    quantidade_dias,
    dt_cadastro,
    observacao
   FROM b1.afastamentos
  WHERE ausente_no_sgp_desde IS NULL
  ORDER BY re, (
        CASE
            WHEN motivo ~~* '%LIC%TRAT%SAUDE%'::text OR motivo ~~* '%LIC%TRAT%SAÚDE%'::text THEN 'LICENÇA TRAT. SAÚDE'::text
            ELSE motivo
        END), data_inicio, data_fim, (
        CASE
            WHEN motivo ~~* '%INCAP%'::text THEN 0
            ELSE 1
        END);

CREATE OR REPLACE VIEW b1.vw_afastamentos_out25_abr26 AS
 SELECT a.re,
    e.nome,
    e.posto_grad,
    e.lotacao,
    a.motivo,
    a.data_inicio,
    a.data_fim,
    a.quantidade_dias,
    a.opm,
    a.origem_informacao,
    a.observacao,
    a.dt_cadastro
   FROM b1.afastamentos a
     LEFT JOIN b1.vw_efetivo_classificado e ON e.re = a.re
  WHERE a.data_inicio >= '2025-10-01'::date AND (a.data_fim IS NULL OR a.data_fim <= '2026-04-30'::date)
    AND a.ausente_no_sgp_desde IS NULL
  ORDER BY e.lotacao, a.motivo, e.nome;

COMMIT;
