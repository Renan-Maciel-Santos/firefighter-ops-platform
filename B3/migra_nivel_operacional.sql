-- ==========================================
-- MIGRAÇÃO: NÍVEL OPERACIONAL (SIOPM → COMP MAPA FORÇA)
-- ==========================================
-- Fonte: tela de composição do SIOPM Web, lida estação por estação
-- (código OPM); coletor não incluído nesta cópia.
--
-- Três níveis:
--   nivel_op_captura    1 linha por execução (quando, quantas estações/viaturas)
--   nivel_op_viatura    1 linha por viatura (US) por captura
--   nivel_op_integrante 1 linha por militar dentro da viatura, com RE
--
-- Idempotente: pode rodar de novo sem efeito colateral.
-- ==========================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS b3;

-- Acima: Uma linha por execução da captura
CREATE TABLE IF NOT EXISTS b3.nivel_op_captura (
    id               bigserial PRIMARY KEY,
    capturado_em     timestamptz NOT NULL DEFAULT now(),
    estacoes_lidas   integer     NOT NULL DEFAULT 0,
    viaturas_lidas   integer     NOT NULL DEFAULT 0,
    -- Acima: Soma dos span__NUMREG; difere de viaturas_lidas se a paginação falhar
    viaturas_numreg  integer     NOT NULL DEFAULT 0,
    -- Acima: Estações que deram erro na leitura (o resto da captura segue valendo)
    estacoes_erro    text[]      NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_nivel_op_captura_em
    ON b3.nivel_op_captura (capturado_em DESC);

-- Acima: Uma linha por viatura (US) por captura, campos como vêm do grid
CREATE TABLE IF NOT EXISTS b3.nivel_op_viatura (
    id              bigserial PRIMARY KEY,
    captura_id      bigint  NOT NULL REFERENCES b3.nivel_op_captura(id) ON DELETE CASCADE,
    opm_cod         text    NOT NULL,
    estacao_nome    text    NOT NULL,
    ordem           integer NOT NULL,
    us              text    NOT NULL,
    status          text,
    -- Acima: O = operando, R = reserva (_PTRSTTGRP)
    status_grp      text,
    componente      text,
    territorio      text,
    programa        text,
    programa_cod    text,
    modalidade      text,
    operacao        text,
    inicio          timestamp,
    termino         timestamp,
    exige_vtr       text,
    existe_vtr      text,
    cad_cod         text,
    -- Acima: Código do componente/turno no SIOPM (_PTRCPNCOD)
    ptrcpn_cod      text,
    -- Acima: 1º colchete do _COMPONENTE: viatura física (pode diferir da US)
    viatura_prefixo text,
    -- Acima: Colchete "TPD:..." do _COMPONENTE (terminal embarcado)
    tpd             text,
    efetivo_qtd     integer NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_nivel_op_viatura_captura
    ON b3.nivel_op_viatura (captura_id, opm_cod);

-- Acima: Integrantes extraídos de _COMPONENTE ("[1.SGT_PM_900104_FULANO]")
CREATE TABLE IF NOT EXISTS b3.nivel_op_integrante (
    id           bigserial PRIMARY KEY,
    viatura_id   bigint  NOT NULL REFERENCES b3.nivel_op_viatura(id) ON DELETE CASCADE,
    ordem        integer NOT NULL,
    posto        text,
    re           integer,
    nome_guerra  text,
    bruto        text    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_nivel_op_integrante_viatura
    ON b3.nivel_op_integrante (viatura_id);

CREATE INDEX IF NOT EXISTS ix_nivel_op_integrante_re
    ON b3.nivel_op_integrante (re);


-- ==========================================
-- VIEWS
-- ==========================================

-- Acima: Viaturas da captura mais recente
CREATE OR REPLACE VIEW b3.vw_nivel_op_atual AS
SELECT c.capturado_em, v.*
  FROM b3.nivel_op_viatura v
  JOIN b3.nivel_op_captura c ON c.id = v.captura_id
 WHERE v.captura_id = (SELECT max(id) FROM b3.nivel_op_captura);

-- Acima: Integrantes da captura mais recente, com a viatura e a estação
CREATE OR REPLACE VIEW b3.vw_nivel_op_integrantes_atual AS
SELECT a.capturado_em, a.opm_cod, a.estacao_nome, a.us, a.status,
       a.modalidade, a.inicio, a.termino,
       i.ordem, i.posto, i.re, i.nome_guerra
  FROM b3.vw_nivel_op_atual a
  JOIN b3.nivel_op_integrante i ON i.viatura_id = a.id;

COMMIT;
