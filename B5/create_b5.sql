-- ============================================================
-- Schema B/5 — Elogios e Láureas
-- Executar conectado ao banco 11gb como admin
-- ============================================================

CREATE SCHEMA IF NOT EXISTS b5;

CREATE TABLE IF NOT EXISTS b5.elogios (
    id              SERIAL PRIMARY KEY,
    nbi             INTEGER,
    num_bi_11gb     INTEGER,
    posto_grad      TEXT,
    re              TEXT,
    nome            TEXT,
    assunto         TEXT,
    tipo            TEXT,           -- ELO | LMP | LOU
    data_elogio     DATE,
    sgb             TEXT,           -- SEDE | 1° SGB | 2° SGB | 3° SGB | 4° SGB | COBOM | SAT
    data_lancamento DATE,
    lancador        TEXT,
    solenidade      TEXT,
    observacoes     TEXT,
    data_base       DATE,
    boletim         TEXT,
    mes_ano         TEXT,
    ano             INTEGER,
    carregado_em    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_elogios_re   ON b5.elogios (re);
CREATE INDEX IF NOT EXISTS ix_elogios_sgb  ON b5.elogios (sgb);
CREATE INDEX IF NOT EXISTS ix_elogios_tipo ON b5.elogios (tipo);
CREATE INDEX IF NOT EXISTS ix_elogios_ano  ON b5.elogios (ano);
