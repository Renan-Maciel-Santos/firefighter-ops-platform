-- ============================================================
-- Migração: b1.qpo_vagas_fixos → b1.qpo_vagas (granular)
-- Base: QPO Vol. XIX (arquivo oficial PMESP)
-- ============================================================

BEGIN;

-- 1. Backup da tabela antiga
ALTER TABLE IF EXISTS b1.qpo_vagas_fixos
    RENAME TO qpo_vagas_fixos_bkp_20260622;

-- 2. Nova tabela granular
CREATE TABLE b1.qpo_vagas (
    id          SERIAL PRIMARY KEY,
    lotacao     TEXT NOT NULL,
    quadro      TEXT NOT NULL,             -- QOPM | QAOPM | QOS | QPPM
    posto_grad  TEXT NOT NULL,             -- Cel PM, Ten Cel PM, Maj PM, Cap PM, Ten PM, Subten/Sgt, Cb/Sd
    categoria   TEXT NOT NULL,             -- Oficial | Praça
    vagas       INTEGER NOT NULL,
    criado_em   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (lotacao, quadro, posto_grad)
);

CREATE INDEX ix_qpo_lotacao    ON b1.qpo_vagas (lotacao);
CREATE INDEX ix_qpo_quadro     ON b1.qpo_vagas (quadro);
CREATE INDEX ix_qpo_posto      ON b1.qpo_vagas (posto_grad);
CREATE INDEX ix_qpo_categoria  ON b1.qpo_vagas (categoria);

-- 3. Carga dos dados do QPO Vol. XIX
INSERT INTO b1.qpo_vagas (lotacao, quadro, posto_grad, categoria, vagas) VALUES
    -- EM (Sede) — total 81
    ('EM',     'QOPM',  'Ten Cel PM',  'Oficial', 1),    -- Comandante
    ('EM',     'QOPM',  'Maj PM',      'Oficial', 1),    -- Subcomandante
    ('EM',     'QOPM',  'Cap PM',      'Oficial', 2),    -- Chefes de Seção
    ('EM',     'QOPM',  'Ten PM',      'Oficial', 2),
    ('EM',     'QAOPM', 'Ten PM',      'Oficial', 3),    -- B/1, B/4, UGE
    ('EM',     'QPPM',  'Subten/Sgt',  'Praça',  27),
    ('EM',     'QPPM',  'Cb/Sd',       'Praça',  45),

    -- 1°SGB — total 142
    ('1°Sgb',  'QOPM',  'Cap PM',      'Oficial',  1),
    ('1°Sgb',  'QOPM',  'Ten PM',      'Oficial',  4),
    ('1°Sgb',  'QPPM',  'Subten/Sgt',  'Praça',   25),
    ('1°Sgb',  'QPPM',  'Cb/Sd',       'Praça',  112),

    -- 2°SGB — total 123
    ('2°Sgb',  'QOPM',  'Cap PM',      'Oficial',  1),
    ('2°Sgb',  'QOPM',  'Ten PM',      'Oficial',  3),
    ('2°Sgb',  'QPPM',  'Subten/Sgt',  'Praça',   25),
    ('2°Sgb',  'QPPM',  'Cb/Sd',       'Praça',   94),

    -- 3°SGB — total 145
    ('3°Sgb',  'QOPM',  'Cap PM',      'Oficial',  1),
    ('3°Sgb',  'QOPM',  'Ten PM',      'Oficial',  3),
    ('3°Sgb',  'QPPM',  'Subten/Sgt',  'Praça',   34),
    ('3°Sgb',  'QPPM',  'Cb/Sd',       'Praça',  107),

    -- 4°SGB — total 97
    ('4°Sgb',  'QOPM',  'Cap PM',      'Oficial',  1),
    ('4°Sgb',  'QOPM',  'Ten PM',      'Oficial',  2),
    ('4°Sgb',  'QPPM',  'Subten/Sgt',  'Praça',   23),
    ('4°Sgb',  'QPPM',  'Cb/Sd',       'Praça',   71);

-- 4. View auxiliar agregada (por lotacao + posto_grad, ignorando o quadro)
-- Substitui o uso direto da tabela antiga nas demais views
CREATE OR REPLACE VIEW b1.vw_qpo_agregado AS
SELECT lotacao, posto_grad, SUM(vagas)::INTEGER AS vagas
FROM b1.qpo_vagas
GROUP BY lotacao, posto_grad;

-- 5. Recria vw_qpo_painel apontando para a nova estrutura
CREATE OR REPLACE VIEW b1.vw_qpo_painel AS
SELECT
    q.lotacao,
    q.posto_grad,
    q.vagas,
    COALESCE(COUNT(e.re), 0)::BIGINT AS existente,
    (q.vagas - COALESCE(COUNT(e.re), 0))::BIGINT AS claro,
    CASE WHEN q.vagas > 0
         THEN ROUND((COALESCE(COUNT(e.re), 0)::NUMERIC / q.vagas::NUMERIC) * 100, 1)
         ELSE 0
    END AS percentual_ocupacao
FROM b1.vw_qpo_agregado q
LEFT JOIN b1.vw_efetivo_classificado e
       ON e.lotacao   = q.lotacao
      AND e.posto_qpo = q.posto_grad
GROUP BY q.lotacao, q.posto_grad, q.vagas
ORDER BY
    CASE q.lotacao
        WHEN 'EM'    THEN 1
        WHEN '1°Sgb' THEN 2
        WHEN '2°Sgb' THEN 3
        WHEN '3°Sgb' THEN 4
        WHEN '4°Sgb' THEN 5
        ELSE 99
    END,
    CASE q.posto_grad
        WHEN 'Ten Cel PM' THEN 1
        WHEN 'Maj PM'     THEN 2
        WHEN 'Cap PM'     THEN 3
        WHEN 'Ten PM'     THEN 4
        WHEN 'Subten/Sgt' THEN 5
        WHEN 'Cb/Sd'      THEN 6
        ELSE 99
    END;

-- 6. Drop e recria views que dependem do tipo (evita conflito de tipos)
DROP VIEW IF EXISTS b1.vw_qpo_resumo_geral;
DROP VIEW IF EXISTS b1.vw_qpo_resumo_lotacao;
DROP VIEW IF EXISTS b1.vw_qpo_resumo_lotacao_cb_sd;

CREATE VIEW b1.vw_qpo_resumo_lotacao_cb_sd AS
WITH fixo AS (
    SELECT lotacao AS unidade,
           SUM(vagas) AS fixo
    FROM b1.qpo_vagas
    WHERE posto_grad = 'Cb/Sd'
    GROUP BY lotacao
),
ocupado AS (
    SELECT
        CASE
            WHEN cod_opm_atual::TEXT LIKE '990119%' THEN 'EM'
            WHEN cod_opm_atual::TEXT LIKE '990111%' THEN '1°Sgb'
            WHEN cod_opm_atual::TEXT LIKE '990112%' THEN '2°Sgb'
            WHEN cod_opm_atual::TEXT LIKE '990113%' THEN '3°Sgb'
            WHEN cod_opm_atual::TEXT LIKE '990114%' THEN '4°Sgb'
        END AS unidade,
        COUNT(*) AS ocupado
    FROM b1.efetivo
    WHERE ativo = true
      AND posto_grad IN ('CB PM', 'SD PM')
      AND (cod_opm_atual::TEXT LIKE '990119%' OR cod_opm_atual::TEXT LIKE '990111%'
        OR cod_opm_atual::TEXT LIKE '990112%' OR cod_opm_atual::TEXT LIKE '990113%'
        OR cod_opm_atual::TEXT LIKE '990114%')
    GROUP BY 1
)
SELECT
    f.unidade,
    f.fixo,
    COALESCE(o.ocupado, 0) AS ocupado,
    f.fixo - COALESCE(o.ocupado, 0) AS vago,
    ROUND(((f.fixo - COALESCE(o.ocupado, 0))::NUMERIC / NULLIF(f.fixo, 0)::NUMERIC) * 100, 2) AS "% - Claro"
FROM fixo f
LEFT JOIN ocupado o ON o.unidade = f.unidade;

-- Recria vw_qpo_resumo_lotacao e vw_qpo_resumo_geral (consomem vw_qpo_painel)
CREATE VIEW b1.vw_qpo_resumo_lotacao AS
SELECT
    lotacao,
    SUM(vagas)     AS vagas,
    SUM(existente) AS existente,
    SUM(claro)     AS claro,
    ROUND((SUM(existente)::NUMERIC / NULLIF(SUM(vagas), 0)::NUMERIC) * 100, 1) AS percentual_ocupacao
FROM b1.vw_qpo_painel
GROUP BY lotacao
ORDER BY
    CASE lotacao
        WHEN 'EM'    THEN 1
        WHEN '1°Sgb' THEN 2
        WHEN '2°Sgb' THEN 3
        WHEN '3°Sgb' THEN 4
        WHEN '4°Sgb' THEN 5
    END;

CREATE VIEW b1.vw_qpo_resumo_geral AS
SELECT
    SUM(vagas)     AS vagas_totais,
    SUM(existente) AS existente_total,
    SUM(claro)     AS claro_total,
    ROUND((SUM(existente)::NUMERIC / NULLIF(SUM(vagas), 0)::NUMERIC) * 100, 1) AS percentual_ocupacao_geral
FROM b1.vw_qpo_painel;

COMMIT;

-- Validação
SELECT lotacao, SUM(vagas) AS total
FROM b1.qpo_vagas
GROUP BY lotacao
ORDER BY lotacao;
