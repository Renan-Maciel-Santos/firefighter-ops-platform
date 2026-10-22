-- ==========================================
-- MIGRAÇÃO: SIOPM COMO FONTE OFICIAL DE STATUS E ESTAÇÃO DAS VIATURAS
-- ==========================================
-- Decisão do usuário em 22/10/2026: a relação de viaturas do SIOPM (tela COMP
-- MAPA FORÇA, capturada em b3.nivel_op_*) é a oficial. A base da Motomec
-- (b4.viaturas) passa a ter status e estação vindos dela, todo dia
-- (B4/viaturas_siopm.py).
--
-- Divisão de responsabilidade:
--   SIOPM    → status, sgb, pb_bb, nome_estacao, municipio (dos prefixos que ele mostra)
--   planilha → placa, chassi, patrimônio, ano, modelo, proprietário... (tudo o mais)
--   Prefixo da base que não aparece no SIOPM (frota administrativa: CT/TP/VT da
--   SAT, MO, UT) continua como a planilha deixou.
--
-- A carga automática da planilha foi desligada no mesmo dia, mas B4/viaturas.py
-- segue chamável à mão. A trava abaixo é um TRIGGER para que essa carga manual
-- também não desfaça o SIOPM.
--
-- Idempotente: pode rodar de novo sem efeito colateral.
-- ==========================================

BEGIN;

-- Acima: Rastro do SIOPM em cada viatura
ALTER TABLE b4.viaturas ADD COLUMN IF NOT EXISTS status_origem    text NOT NULL DEFAULT 'PLANILHA';
ALTER TABLE b4.viaturas ADD COLUMN IF NOT EXISTS origem_cadastro  text NOT NULL DEFAULT 'PLANILHA';
ALTER TABLE b4.viaturas ADD COLUMN IF NOT EXISTS siopm_us         text;
ALTER TABLE b4.viaturas ADD COLUMN IF NOT EXISTS siopm_status     text;
ALTER TABLE b4.viaturas ADD COLUMN IF NOT EXISTS siopm_opm_cod    text;
ALTER TABLE b4.viaturas ADD COLUMN IF NOT EXISTS siopm_captura_id bigint;
-- Acima: Última vez que o SIOPM mostrou a viatura. NULL = nunca visto (frota
-- administrativa); data velha = sumiu do mapa de força.
ALTER TABLE b4.viaturas ADD COLUMN IF NOT EXISTS siopm_visto_em   timestamptz;


-- ==========================================
-- ESTAÇÕES DO SIOPM (código OPM → como gravar na base)
-- ==========================================
-- pb_bb é o PB ao qual o código subordina a estação (7º dígito: 99011 S P EE),
-- e não a numeração de BB da planilha (1ªBB, 2ªBB), que não batia com a
-- hierarquia do SIOPM (ex.: Caçapava 4ºPB na planilha, sob a Ana Emília no
-- SIOPM). nome_estacao é o nome do SIOPM, que já diz se é PB, BB ou BCom.
CREATE TABLE IF NOT EXISTS b4.siopm_estacao (
    opm_cod       text PRIMARY KEY,
    sgb           text NOT NULL,
    pb_bb         text NOT NULL,
    nome_estacao  text NOT NULL,
    municipio     text NOT NULL
);

INSERT INTO b4.siopm_estacao (opm_cod, sgb, pb_bb, nome_estacao, municipio) VALUES
    ('990111101', '1ºSGB', '1ºPB', 'PB VILA BETANIA',          'SÃO JOSÉ DOS CAMPOS'),
    ('990111102', '1ºSGB', '1ºPB', 'BCom PARAIBUNA',           'PARAIBUNA'),
    ('990111201', '1ºSGB', '2ºPB', 'PB VILA INDUSTRIAL',       'SÃO JOSÉ DOS CAMPOS'),
    ('990111202', '1ºSGB', '2ºPB', 'BB LESTE',                 'SÃO JOSÉ DOS CAMPOS'),
    ('990111301', '1ºSGB', '3ºPB', 'PB SUL',                   'SÃO JOSÉ DOS CAMPOS'),
    ('990111401', '1ºSGB', '4ºPB', 'PB JACAREI',               'JACAREÍ'),
    ('990112101', '2ºSGB', '1ºPB', 'PB BOM CONSELHO',          'TAUBATÉ'),
    ('990112102', '2ºSGB', '1ºPB', 'BB QUIRIRIM',              'TAUBATÉ'),
    ('990112103', '2ºSGB', '1ºPB', 'BCom SÃO LUÍS PARAITINGA', 'SÃO LUIZ DO PARAITINGA'),
    ('990112201', '2ºSGB', '2ºPB', 'PB ANA EMILIA',            'TAUBATÉ'),
    ('990112202', '2ºSGB', '2ºPB', 'BB CACAPAVA',              'CAÇAPAVA'),
    ('990112301', '2ºSGB', '3ºPB', 'PB CAMPOS DO JORDAO',      'CAMPOS DO JORDÃO'),
    ('990113101', '3ºSGB', '1ºPB', 'PB GUARATINGUETA',         'GUARATINGUETÁ'),
    ('990113102', '3ºSGB', '1ºPB', 'BB LORENA',                'LORENA'),
    ('990113104', '3ºSGB', '1ºPB', 'BCom CUNHA',               'CUNHA'),
    ('990113201', '3ºSGB', '2ºPB', 'PB CRUZEIRO',              'CRUZEIRO'),
    ('990113202', '3ºSGB', '2ºPB', 'BB CACHOEIRA PAULISTA',    'CACHOEIRA PAULISTA'),
    ('990113203', '3ºSGB', '2ºPB', 'BCom BANANAL',             'BANANAL'),
    ('990113301', '3ºSGB', '3ºPB', 'PB PINDAMONHANGABA',       'PINDAMONHANGABA'),
    ('990113302', '3ºSGB', '3ºPB', 'BB APARECIDA',             'APARECIDA'),
    ('990113303', '3ºSGB', '3ºPB', 'BCom POTIM',               'POTIM'),
    ('990114101', '4ºSGB', '1ºPB', 'PB CARAGUATATUBA',         'CARAGUATATUBA'),
    ('990114102', '4ºSGB', '1ºPB', 'BB UBATUBA',               'UBATUBA'),
    ('990114201', '4ºSGB', '2ºPB', 'PB SAO SEBASTIAO',         'SÃO SEBASTIÃO'),
    ('990114202', '4ºSGB', '2ºPB', 'BB ILHABELA',              'ILHABELA')
ON CONFLICT (opm_cod) DO UPDATE SET
    sgb          = EXCLUDED.sgb,
    pb_bb        = EXCLUDED.pb_bb,
    nome_estacao = EXCLUDED.nome_estacao,
    municipio    = EXCLUDED.municipio;


-- ==========================================
-- LOG DA SINCRONIZAÇÃO
-- ==========================================
-- Acima: Uma linha por campo alterado (ou viatura criada). É daqui que sai o
-- "antes e depois" de cada execução, e é por aqui que se desfaz um erro.
CREATE TABLE IF NOT EXISTS b4.viaturas_sync_siopm (
    id           bigserial PRIMARY KEY,
    executado_em timestamptz NOT NULL DEFAULT now(),
    captura_id   bigint      NOT NULL,
    prefixo      text        NOT NULL,
    -- Acima: 'status', 'sgb', 'pb_bb', 'nome_estacao', 'municipio' ou 'CRIADA'
    campo        text        NOT NULL,
    antes        text,
    depois       text
);

CREATE INDEX IF NOT EXISTS ix_viaturas_sync_siopm_captura
    ON b4.viaturas_sync_siopm (captura_id);


-- ==========================================
-- TRAVA: A PLANILHA NÃO DESFAZ O SIOPM
-- ==========================================
-- Uma viatura vista no SIOPM nos últimos 3 dias tem status e estação travados.
-- Só passa quem também mexe em siopm_visto_em, ou seja, a própria
-- sincronização. Três dias e não "para sempre": viatura que saiu do mapa de
-- força (transferida, descarregada) volta sozinha a obedecer a planilha.
CREATE OR REPLACE FUNCTION b4.fn_viaturas_trava_siopm() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status_origem = 'SIOPM'
       AND OLD.siopm_visto_em > now() - interval '3 days'
       AND NEW.siopm_visto_em IS NOT DISTINCT FROM OLD.siopm_visto_em THEN
        NEW.status        := OLD.status;
        NEW.sgb           := OLD.sgb;
        NEW.pb_bb         := OLD.pb_bb;
        NEW.nome_estacao  := OLD.nome_estacao;
        NEW.municipio     := OLD.municipio;
        NEW.status_origem := OLD.status_origem;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS tg_viaturas_trava_siopm ON b4.viaturas;
CREATE TRIGGER tg_viaturas_trava_siopm
    BEFORE UPDATE ON b4.viaturas
    FOR EACH ROW EXECUTE FUNCTION b4.fn_viaturas_trava_siopm();

COMMIT;
