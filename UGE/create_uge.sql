-- ============================================================
-- Schema UGE — Controle de Processos da UGE 990210
-- 11° GB PMESP
-- ============================================================

CREATE SCHEMA IF NOT EXISTS uge;

CREATE TABLE IF NOT EXISTS uge.processos (
    id                  SERIAL PRIMARY KEY,
    numero              INTEGER,
    processo_sei        TEXT,
    processo_siafem     TEXT,
    licitacao           TEXT,          -- ARP, PREGÃO, INEX, DL-DISP, DL-DIRETA, ADTO, DIÁRIAS
    solicitante         TEXT,          -- 11°GB, 1°SGB, 2°SGB, 3°SGB, 4°SGB, SEDE, SAT
    objeto              TEXT,
    classe              TEXT,          -- natureza de despesa (33903918, 449052, etc.)
    ptres               TEXT,
    nd                  TEXT,
    fonte               TEXT,
    ne                  TEXT,          -- nota de empenho
    valor_empenhado     NUMERIC(14,2),
    entrega_empenhada   DATE,
    ok_empenho          TEXT,
    entrega_prorrogada  DATE,
    ok_prorrog          TEXT,
    valor_liquidado     NUMERIC(14,2),
    observacoes         TEXT,
    responsavel         TEXT,          -- Cb Fulano, Cb Beltrano, Ten Sicrano
    status              TEXT,          -- ANDAMENTO, ENCERRADO, CANCELADO
    ano                 INTEGER,
    carregado_em        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_uge_status      ON uge.processos (status);
CREATE INDEX IF NOT EXISTS ix_uge_licitacao   ON uge.processos (licitacao);
CREATE INDEX IF NOT EXISTS ix_uge_solicitante ON uge.processos (solicitante);
CREATE INDEX IF NOT EXISTS ix_uge_responsavel ON uge.processos (responsavel);
CREATE INDEX IF NOT EXISTS ix_uge_ano         ON uge.processos (ano);
CREATE INDEX IF NOT EXISTS ix_uge_entrega     ON uge.processos (entrega_empenhada);
