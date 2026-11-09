-- ============================================================
-- Schema FINANCAS — quanto cada SGB custa por mês e por ano
-- 11° GB PMESP
--
-- Substitui a planilha "Gastos das prefeituras por SGB" (Google Sheets):
-- cada SGB lançava, por posto/município, o que a prefeitura gastou com
-- telefone, água, energia, combustível, manutenção de frota, alimentação e
-- outros. A aba TOTAL somava tudo e juntava os recursos da UGE.
--
-- Idempotente: pode rodar de novo sem perder dado.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS financas;

-- Postos/municípios de cada SGB (os blocos de cada aba da planilha).
CREATE TABLE IF NOT EXISTS financas.locais (
    id          SERIAL PRIMARY KEY,
    sgb         TEXT NOT NULL CHECK (sgb IN ('1°SGB','2°SGB','3°SGB','4°SGB')),
    nome        TEXT NOT NULL,
    ordem       INTEGER NOT NULL DEFAULT 0,
    observacao  TEXT,              -- ex.: "Prefeitura não fornece telefone"
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (sgb, nome)
);

-- Um valor por local × categoria × mês. Sem linha = em branco (não há valor).
CREATE TABLE IF NOT EXISTS financas.gastos (
    ano            INTEGER NOT NULL CHECK (ano BETWEEN 2020 AND 2100),
    mes            INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    local_id       INTEGER NOT NULL REFERENCES financas.locais(id),
    categoria      TEXT NOT NULL CHECK (categoria IN
                     ('tel','agua','energia','combustivel','manutencao_frota','alimentacao','outros')),
    valor          NUMERIC(14,2) NOT NULL,
    atualizado_por TEXT,
    atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ano, mes, local_id, categoria)
);

CREATE INDEX IF NOT EXISTS ix_fin_gastos_ano ON financas.gastos (ano);

-- 09/11/2026: a 1ª versão guardava "PBVI" como situação. O Cmt preferiu célula
-- em branco quando não há valor — as linhas PBVI somem e a coluna sai.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'financas' AND table_name = 'gastos' AND column_name = 'situacao') THEN
        DELETE FROM financas.gastos WHERE situacao = 'pbvi' OR valor IS NULL;
        ALTER TABLE financas.gastos DROP COLUMN situacao;
        ALTER TABLE financas.gastos ALTER COLUMN valor SET NOT NULL;
    END IF;
END $$;

-- Recursos geridos pela UGE (bloco "TOTAL DE GASTOS UGE" da planilha):
-- item comprado/pago, valor e a fonte que pagou.
CREATE TABLE IF NOT EXISTS financas.recursos_uge (
    id             SERIAL PRIMARY KEY,
    ano            INTEGER NOT NULL,
    descricao      TEXT NOT NULL,          -- o "Item" na tela
    valor          NUMERIC(14,2) NOT NULL,
    fonte          TEXT,
    ordem          INTEGER NOT NULL DEFAULT 0,
    atualizado_por TEXT,
    atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 09/11/2026: "detalhe" (texto livre) virou "fonte" (lista fechada).
ALTER TABLE financas.recursos_uge ADD COLUMN IF NOT EXISTS fonte TEXT;
ALTER TABLE financas.recursos_uge DROP COLUMN IF EXISTS detalhe;
ALTER TABLE financas.recursos_uge DROP CONSTRAINT IF EXISTS recursos_uge_fonte_check;
ALTER TABLE financas.recursos_uge ADD CONSTRAINT recursos_uge_fonte_check CHECK (fonte IN
    ('RINEM','Tesouro','Emenda Parlamentar','TAC','Prestação Pecuniária','FEPOM','Doação'));

CREATE INDEX IF NOT EXISTS ix_fin_uge_ano ON financas.recursos_uge (ano);
