-- ==========================================================================
-- Schema do painel (app, b1, b3, b4, b5, bia, sjd, uge) - SO ESTRUTURA.
-- Gerado com pg_dump --schema-only a partir do banco real, sem nenhuma linha
-- de dado e com os codigos de OPM trocados por ficticios (prefixo 99011).
-- Aplicado pelo seed/gerar_dados_ficticios.py; as migracoes migra_*.sql de cada
-- pasta continuam no repositorio como historico de como se chegou aqui.
-- ==========================================================================
--
-- PostgreSQL database dump
--


-- Dumped from database version 16.11 (Debian 16.11-1.pgdg13+1)
-- Dumped by pg_dump version 16.11 (Debian 16.11-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: app; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA app;


--
-- Name: b1; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA b1;


--
-- Name: b3; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA b3;


--
-- Name: b4; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA b4;


--
-- Name: b5; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA b5;


--
-- Name: bia; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA bia;


--
-- Name: sjd; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA sjd;


--
-- Name: uge; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA uge;


--
-- Name: perfil_enum; Type: TYPE; Schema: app; Owner: -
--

CREATE TYPE app.perfil_enum AS ENUM (
    'comando',
    'administrativo',
    'operacional',
    'admin',
    'oficial',
    'praca'
);


--
-- Name: fn_viaturas_trava_siopm(); Type: FUNCTION; Schema: b4; Owner: -
--

CREATE FUNCTION b4.fn_viaturas_trava_siopm() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: usuarios; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.usuarios (
    id integer NOT NULL,
    nome character varying(120) NOT NULL,
    matricula character varying(20) NOT NULL,
    senha_hash character varying(255) NOT NULL,
    perfil app.perfil_enum NOT NULL,
    ativo boolean DEFAULT true NOT NULL,
    apelido_assinatura text,
    deve_trocar_senha boolean DEFAULT false NOT NULL,
    secao text
);


--
-- Name: COLUMN usuarios.deve_trocar_senha; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON COLUMN app.usuarios.deve_trocar_senha IS 'Força a troca de senha antes de liberar o painel. Marcado no cadastro e no reset; limpo quando o próprio usuário troca em /auth/trocar-senha.';


--
-- Name: COLUMN usuarios.secao; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON COLUMN app.usuarios.secao IS 'Seção do EM que o praça enxerga (B/1 e B/5, B/3, B/4, St UGE, COBOM, SJD). NULL para admin e oficial. Escolhida no cadastro, não derivada do RE.';


--
-- Name: usuarios_id_seq; Type: SEQUENCE; Schema: app; Owner: -
--

CREATE SEQUENCE app.usuarios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: usuarios_id_seq; Type: SEQUENCE OWNED BY; Schema: app; Owner: -
--

ALTER SEQUENCE app.usuarios_id_seq OWNED BY app.usuarios.id;


--
-- Name: afastamentos; Type: TABLE; Schema: b1; Owner: -
--

CREATE TABLE b1.afastamentos (
    id bigint NOT NULL,
    re bigint NOT NULL,
    opm text,
    motivo text,
    origem_informacao text,
    data_inicio date,
    data_fim date,
    quantidade_dias integer,
    dt_cadastro date,
    observacao text,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    posto_grad text,
    nome text,
    quadro text,
    condicao text,
    atualizado_em timestamp with time zone,
    ausente_no_sgp_desde date
);


--
-- Name: COLUMN afastamentos.ausente_no_sgp_desde; Type: COMMENT; Schema: b1; Owner: -
--

COMMENT ON COLUMN b1.afastamentos.ausente_no_sgp_desde IS 'Data do primeiro relatório do SGP que deixou de trazer este afastamento. NULL = confirmado pelo SGP (ou fora do alcance do relatório). As views ignoram as marcadas.';


--
-- Name: afastamentos_id_seq; Type: SEQUENCE; Schema: b1; Owner: -
--

CREATE SEQUENCE b1.afastamentos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: afastamentos_id_seq; Type: SEQUENCE OWNED BY; Schema: b1; Owner: -
--

ALTER SEQUENCE b1.afastamentos_id_seq OWNED BY b1.afastamentos.id;


--
-- Name: controle_coleta; Type: TABLE; Schema: b1; Owner: -
--

CREATE TABLE b1.controle_coleta (
    processo text NOT NULL,
    ultimo_re bigint,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: efetivo; Type: TABLE; Schema: b1; Owner: -
--

CREATE TABLE b1.efetivo (
    id bigint NOT NULL,
    re integer NOT NULL,
    nome text NOT NULL,
    posto_grad text NOT NULL,
    cod_opm_atual integer NOT NULL,
    ativo boolean DEFAULT true NOT NULL,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    quadro character varying,
    sexo character varying(1),
    data_admissao date,
    opm_atual character varying,
    opm_efetiva character varying,
    cod_opm_efetiva integer,
    situacao character varying,
    re_dv character varying(1)
);


--
-- Name: efetivo_id_seq; Type: SEQUENCE; Schema: b1; Owner: -
--

CREATE SEQUENCE b1.efetivo_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: efetivo_id_seq; Type: SEQUENCE OWNED BY; Schema: b1; Owner: -
--

ALTER SEQUENCE b1.efetivo_id_seq OWNED BY b1.efetivo.id;


--
-- Name: efetivo_quantitativo_diario; Type: TABLE; Schema: b1; Owner: -
--

CREATE TABLE b1.efetivo_quantitativo_diario (
    data_referencia date NOT NULL,
    lotacao text NOT NULL,
    posto_grad text NOT NULL,
    quantidade integer NOT NULL,
    gravado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: efetivo_snapshot_mensal; Type: TABLE; Schema: b1; Owner: -
--

CREATE TABLE b1.efetivo_snapshot_mensal (
    id bigint NOT NULL,
    data_referencia date NOT NULL,
    re integer NOT NULL,
    nome character varying,
    posto_grad character varying,
    quadro character varying,
    lotacao character varying,
    cod_opm_atual integer,
    opm_efetiva character varying,
    situacao character varying,
    criado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: efetivo_snapshot_mensal_id_seq; Type: SEQUENCE; Schema: b1; Owner: -
--

CREATE SEQUENCE b1.efetivo_snapshot_mensal_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: efetivo_snapshot_mensal_id_seq; Type: SEQUENCE OWNED BY; Schema: b1; Owner: -
--

ALTER SEQUENCE b1.efetivo_snapshot_mensal_id_seq OWNED BY b1.efetivo_snapshot_mensal.id;


--
-- Name: etl_status; Type: TABLE; Schema: b1; Owner: -
--

CREATE TABLE b1.etl_status (
    id bigint NOT NULL,
    dominio text NOT NULL,
    iniciado_em timestamp with time zone DEFAULT now() NOT NULL,
    finalizado_em timestamp with time zone,
    status text DEFAULT 'running'::text NOT NULL,
    linhas_lidas integer,
    linhas_inseridas integer,
    linhas_atualizadas integer,
    erro text,
    re bigint,
    tentativas integer DEFAULT 0 NOT NULL,
    ultima_mensagem text,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    tentativa integer,
    mensagem text
);


--
-- Name: etl_status_id_seq; Type: SEQUENCE; Schema: b1; Owner: -
--

CREATE SEQUENCE b1.etl_status_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: etl_status_id_seq; Type: SEQUENCE OWNED BY; Schema: b1; Owner: -
--

ALTER SEQUENCE b1.etl_status_id_seq OWNED BY b1.etl_status.id;


--
-- Name: ias_inspecao; Type: TABLE; Schema: b1; Owner: -
--

CREATE TABLE b1.ias_inspecao (
    id bigint NOT NULL,
    re bigint NOT NULL,
    ano integer,
    numero_processo text,
    data_inspecao_medica date,
    data_inspecao_odontologica date,
    data_validade date,
    inspecao_medica text,
    inspecao_odontologica text,
    parecer_medico_taf text,
    parecer_medico_tat text,
    carregado_em timestamp with time zone DEFAULT now() NOT NULL,
    situacao_inspecao character varying,
    atualizado_em timestamp with time zone
);


--
-- Name: ias_inspecao_id_seq; Type: SEQUENCE; Schema: b1; Owner: -
--

CREATE SEQUENCE b1.ias_inspecao_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ias_inspecao_id_seq; Type: SEQUENCE OWNED BY; Schema: b1; Owner: -
--

ALTER SEQUENCE b1.ias_inspecao_id_seq OWNED BY b1.ias_inspecao.id;


--
-- Name: promocoes; Type: TABLE; Schema: b1; Owner: -
--

CREATE TABLE b1.promocoes (
    re integer NOT NULL,
    nivel integer,
    codigo_posto integer NOT NULL,
    posto text,
    sigla_anterior text,
    codigo_quadro integer,
    quadro text,
    tipo_promocao text,
    data_promocao date NOT NULL,
    data_quadro date,
    boletim text,
    doe text,
    capturado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: qpo_funcoes; Type: TABLE; Schema: b1; Owner: -
--

CREATE TABLE b1.qpo_funcoes (
    id integer NOT NULL,
    lotacao text NOT NULL,
    secao text,
    subsecao text,
    funcao text,
    quadro text NOT NULL,
    posto_grad text NOT NULL,
    categoria text NOT NULL,
    vagas integer NOT NULL,
    a_designar boolean DEFAULT false NOT NULL,
    municipio text,
    obs text,
    aba_origem text NOT NULL,
    linha_origem integer NOT NULL,
    fonte text NOT NULL,
    criado_em timestamp with time zone DEFAULT now()
);


--
-- Name: qpo_funcoes_id_seq; Type: SEQUENCE; Schema: b1; Owner: -
--

CREATE SEQUENCE b1.qpo_funcoes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: qpo_funcoes_id_seq; Type: SEQUENCE OWNED BY; Schema: b1; Owner: -
--

ALTER SEQUENCE b1.qpo_funcoes_id_seq OWNED BY b1.qpo_funcoes.id;


--
-- Name: qpo_vagas; Type: TABLE; Schema: b1; Owner: -
--

CREATE TABLE b1.qpo_vagas (
    id integer NOT NULL,
    lotacao text NOT NULL,
    quadro text NOT NULL,
    posto_grad text NOT NULL,
    categoria text NOT NULL,
    vagas integer NOT NULL,
    criado_em timestamp with time zone DEFAULT now()
);


--
-- Name: qpo_vagas_fixos_id_seq; Type: SEQUENCE; Schema: b1; Owner: -
--

CREATE SEQUENCE b1.qpo_vagas_fixos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: qpo_vagas_id_seq; Type: SEQUENCE; Schema: b1; Owner: -
--

CREATE SEQUENCE b1.qpo_vagas_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: qpo_vagas_id_seq; Type: SEQUENCE OWNED BY; Schema: b1; Owner: -
--

ALTER SEQUENCE b1.qpo_vagas_id_seq OWNED BY b1.qpo_vagas.id;


--
-- Name: restricoes; Type: TABLE; Schema: b1; Owner: -
--

CREATE TABLE b1.restricoes (
    id bigint NOT NULL,
    re integer NOT NULL,
    condicao character varying,
    restricao_medica text,
    origem character varying,
    data_inicial date NOT NULL,
    data_final date,
    total_dias integer,
    observacao character varying,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: restricoes_id_seq; Type: SEQUENCE; Schema: b1; Owner: -
--

CREATE SEQUENCE b1.restricoes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: restricoes_id_seq; Type: SEQUENCE OWNED BY; Schema: b1; Owner: -
--

ALTER SEQUENCE b1.restricoes_id_seq OWNED BY b1.restricoes.id;


--
-- Name: taf_resultados_raw; Type: TABLE; Schema: b1; Owner: -
--

CREATE TABLE b1.taf_resultados_raw (
    id bigint NOT NULL,
    re integer NOT NULL,
    status text,
    resultado text,
    tipo_taf text,
    data_realizado date,
    lote_importacao text NOT NULL,
    linha_origem integer NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: taf_resultados_raw_id_seq; Type: SEQUENCE; Schema: b1; Owner: -
--

CREATE SEQUENCE b1.taf_resultados_raw_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: taf_resultados_raw_id_seq; Type: SEQUENCE OWNED BY; Schema: b1; Owner: -
--

ALTER SEQUENCE b1.taf_resultados_raw_id_seq OWNED BY b1.taf_resultados_raw.id;


--
-- Name: v_afastamentos_dedup; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.v_afastamentos_dedup AS
 SELECT DISTINCT ON (re,
        CASE
            WHEN ((motivo ~~* '%LIC%TRAT%SAUDE%'::text) OR (motivo ~~* '%LIC%TRAT%SAÚDE%'::text)) THEN 'LICENÇA TRAT. SAÚDE'::text
            ELSE motivo
        END, data_inicio, data_fim) re,
    opm,
        CASE
            WHEN ((motivo ~~* '%LIC%TRAT%SAUDE%'::text) OR (motivo ~~* '%LIC%TRAT%SAÚDE%'::text)) THEN 'LICENÇA TRAT. SAÚDE'::text
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
  WHERE (ausente_no_sgp_desde IS NULL)
  ORDER BY re,
        CASE
            WHEN ((motivo ~~* '%LIC%TRAT%SAUDE%'::text) OR (motivo ~~* '%LIC%TRAT%SAÚDE%'::text)) THEN 'LICENÇA TRAT. SAÚDE'::text
            ELSE motivo
        END, data_inicio, data_fim,
        CASE
            WHEN (motivo ~~* '%INCAP%'::text) THEN 0
            ELSE 1
        END;


--
-- Name: vw_efetivo_classificado; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_efetivo_classificado AS
 SELECT re,
    nome,
    posto_grad,
    cod_opm_atual,
    ativo,
        CASE
            WHEN ("left"((cod_opm_atual)::text, 6) = ANY (ARRAY['990110'::text, '990119'::text])) THEN 'EM'::text
            WHEN ("left"((cod_opm_atual)::text, 6) = '990111'::text) THEN '1°Sgb'::text
            WHEN ("left"((cod_opm_atual)::text, 6) = '990112'::text) THEN '2°Sgb'::text
            WHEN ("left"((cod_opm_atual)::text, 6) = '990113'::text) THEN '3°Sgb'::text
            WHEN ("left"((cod_opm_atual)::text, 6) = '990114'::text) THEN '4°Sgb'::text
            ELSE 'Outros'::text
        END AS lotacao,
        CASE
            WHEN ("left"((cod_opm_atual)::text, 6) = ANY (ARRAY['990110'::text, '990119'::text])) THEN 1
            WHEN ("left"((cod_opm_atual)::text, 6) = '990111'::text) THEN 2
            WHEN ("left"((cod_opm_atual)::text, 6) = '990112'::text) THEN 3
            WHEN ("left"((cod_opm_atual)::text, 6) = '990113'::text) THEN 4
            WHEN ("left"((cod_opm_atual)::text, 6) = '990114'::text) THEN 5
            ELSE 99
        END AS ord_lotacao,
        CASE
            WHEN (posto_grad ~* '(\mTEN\s*CEL\m|TENCEL|\mTC\M|\mCEL\M|CORONEL)'::text) THEN 'Ten Cel PM'::text
            WHEN (posto_grad ~* '(\mMAJ\M|MAJOR)'::text) THEN 'Maj PM'::text
            WHEN (posto_grad ~* '(\mCAP\M|CAPITAO|CAPITÃO)'::text) THEN 'Cap PM'::text
            WHEN ((posto_grad !~* '(SUB\s*TEN|SUBTEN)'::text) AND (posto_grad ~* '(\m[12]\s*\.?\s*TEN\M|\mTEN\M|TENENTE)'::text)) THEN 'Ten PM'::text
            WHEN (posto_grad ~* '(SUB\s*TEN|SUBTEN|SGT)'::text) THEN 'Subten/Sgt'::text
            WHEN (posto_grad ~* '(\mCB\M|\mSD\M)'::text) THEN 'Cb/Sd'::text
            ELSE NULL::text
        END AS posto_qpo
   FROM b1.efetivo e
  WHERE (ativo = true);


--
-- Name: vw_afastamentos_out25_abr26; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_afastamentos_out25_abr26 AS
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
   FROM (b1.afastamentos a
     LEFT JOIN b1.vw_efetivo_classificado e ON ((e.re = a.re)))
  WHERE ((a.data_inicio >= '2025-10-01'::date) AND ((a.data_fim IS NULL) OR (a.data_fim <= '2026-04-30'::date)) AND (a.ausente_no_sgp_desde IS NULL))
  ORDER BY e.lotacao, a.motivo, e.nome;


--
-- Name: vw_antiguidade; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_antiguidade AS
 WITH hist AS (
         SELECT p.re,
            p.nivel,
            p.codigo_posto,
            p.posto,
            p.sigla_anterior,
            p.codigo_quadro,
            p.quadro,
            p.tipo_promocao,
            p.data_promocao,
            p.data_quadro,
            p.boletim,
            p.doe,
            p.capturado_em,
            row_number() OVER (PARTITION BY p.re ORDER BY p.data_promocao DESC, p.nivel) AS n
           FROM b1.promocoes p
        )
 SELECT e.re,
    e.nome,
    e.posto_grad,
    atual.posto AS posto_sgp,
    atual.nivel,
    atual.data_promocao AS data_promocao_atual,
    anterior.data_promocao AS data_promocao_anterior,
    e.data_admissao,
    row_number() OVER (ORDER BY atual.nivel, atual.data_promocao, anterior.data_promocao, e.data_admissao, e.re) AS ordem_geral
   FROM ((b1.efetivo e
     LEFT JOIN hist atual ON (((atual.re = e.re) AND (atual.n = 1))))
     LEFT JOIN hist anterior ON (((anterior.re = e.re) AND (anterior.n = 2))))
  WHERE e.ativo;


--
-- Name: vw_efetivo_disponivel; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_efetivo_disponivel AS
 WITH base AS (
         SELECT
                CASE
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = ANY (ARRAY['990110'::text, '990119'::text])) THEN 'EM + COBOM'::text
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990111'::text) THEN '1°Sgb'::text
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990112'::text) THEN '2°Sgb'::text
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990113'::text) THEN '3°Sgb'::text
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990114'::text) THEN '4°Sgb'::text
                    ELSE 'Outros'::text
                END AS lotacao,
                CASE
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = ANY (ARRAY['990110'::text, '990119'::text])) THEN 1
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990111'::text) THEN 2
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990112'::text) THEN 3
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990113'::text) THEN 4
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990114'::text) THEN 5
                    ELSE 99
                END AS ord_lotacao,
            ((e.cod_opm_atual)::text !~~ '%0'::text) AS operacional,
            ((COALESCE(e.situacao, ''::character varying))::text <> 'EFETIVO'::text) AS fora_do_servico
           FROM b1.efetivo e
          WHERE (e.ativo = true)
        )
 SELECT COALESCE(lotacao, 'TOTAL GERAL'::text) AS lotacao,
    count(*) FILTER (WHERE operacional) AS operacional,
    count(*) FILTER (WHERE (operacional AND fora_do_servico)) AS fora_do_servico,
    count(*) FILTER (WHERE (operacional AND (NOT fora_do_servico))) AS disponivel,
    round(((100.0 * (count(*) FILTER (WHERE (operacional AND (NOT fora_do_servico))))::numeric) / (NULLIF(count(*) FILTER (WHERE operacional), 0))::numeric), 1) AS perc_disponivel
   FROM base
  GROUP BY GROUPING SETS ((lotacao, ord_lotacao), ())
  ORDER BY GROUPING(lotacao), ord_lotacao;


--
-- Name: VIEW vw_efetivo_disponivel; Type: COMMENT; Schema: b1; Owner: -
--

COMMENT ON VIEW b1.vw_efetivo_disponivel IS 'Quantitativo de efetivo operacional disponível: desconta quem está fora do serviço por situação (LSV, candidato, licença em org. civil). Férias e licença-prêmio NÃO descontam. Complementa vw_efetivo_operacional, que responde lotação. Não aplica o override da SAT.';


--
-- Name: vw_efetivo_operacional; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_efetivo_operacional AS
 SELECT COALESCE(lotacao, 'TOTAL GERAL'::text) AS lotacao,
    total_ativos,
    total_operacional,
    perc_operacional
   FROM ( SELECT
                CASE
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = ANY (ARRAY['990110'::text, '990119'::text])) THEN 'EM + COBOM'::text
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990111'::text) THEN '1°Sgb'::text
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990112'::text) THEN '2°Sgb'::text
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990113'::text) THEN '3°Sgb'::text
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990114'::text) THEN '4°Sgb'::text
                    ELSE 'Outros'::text
                END AS lotacao,
                CASE
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = ANY (ARRAY['990110'::text, '990119'::text])) THEN 1
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990111'::text) THEN 2
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990112'::text) THEN 3
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990113'::text) THEN 4
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990114'::text) THEN 5
                    ELSE 99
                END AS ord_lotacao,
            count(*) AS total_ativos,
            sum(
                CASE
                    WHEN ((e.cod_opm_atual)::text !~~ '%0'::text) THEN 1
                    ELSE 0
                END) AS total_operacional,
            round(((100.0 * (sum(
                CASE
                    WHEN ((e.cod_opm_atual)::text !~~ '%0'::text) THEN 1
                    ELSE 0
                END))::numeric) / (NULLIF(count(*), 0))::numeric), 1) AS perc_operacional
           FROM b1.efetivo e
          WHERE (e.ativo = true)
          GROUP BY GROUPING SETS ((
                CASE
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = ANY (ARRAY['990110'::text, '990119'::text])) THEN 'EM + COBOM'::text
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990111'::text) THEN '1°Sgb'::text
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990112'::text) THEN '2°Sgb'::text
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990113'::text) THEN '3°Sgb'::text
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990114'::text) THEN '4°Sgb'::text
                    ELSE 'Outros'::text
                END,
                CASE
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = ANY (ARRAY['990110'::text, '990119'::text])) THEN 1
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990111'::text) THEN 2
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990112'::text) THEN 3
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990113'::text) THEN 4
                    WHEN ("left"((e.cod_opm_atual)::text, 6) = '990114'::text) THEN 5
                    ELSE 99
                END), ())) dados
  ORDER BY
        CASE
            WHEN (lotacao IS NULL) THEN 999
            ELSE ord_lotacao
        END;


--
-- Name: vw_efetivo_quantitativo_lotacao; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_efetivo_quantitativo_lotacao AS
 SELECT data_referencia,
    lotacao,
    (sum(quantidade))::integer AS quantidade
   FROM b1.efetivo_quantitativo_diario
  GROUP BY data_referencia, lotacao;


--
-- Name: vw_ias_quantitativo; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_ias_quantitativo AS
 WITH ultima_ias AS (
         SELECT i.re,
            max(i.data_validade) AS data_validade
           FROM b1.ias_inspecao i
          GROUP BY i.re
        ), situacao AS (
         SELECT e.re,
                CASE
                    WHEN (u.data_validade IS NULL) THEN 'SEM IAS'::text
                    WHEN (u.data_validade < CURRENT_DATE) THEN 'ATRASADA'::text
                    ELSE 'EM DIA'::text
                END AS situacao_ias
           FROM (b1.efetivo e
             LEFT JOIN ultima_ias u ON ((u.re = e.re)))
          WHERE (e.ativo = true)
        )
 SELECT situacao_ias,
    count(*) AS quantidade
   FROM situacao s
  GROUP BY situacao_ias
  ORDER BY
        CASE situacao_ias
            WHEN 'EM DIA'::text THEN 1
            WHEN 'ATRASADA'::text THEN 2
            WHEN 'SEM IAS'::text THEN 3
            ELSE 99
        END;


--
-- Name: vw_ias_percentual; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_ias_percentual AS
 WITH base AS (
         SELECT (count(*))::numeric AS total_ativos
           FROM b1.efetivo e
          WHERE (e.ativo = true)
        ), quantitativo AS (
         SELECT q_1.situacao_ias,
            (q_1.quantidade)::numeric AS quantidade
           FROM b1.vw_ias_quantitativo q_1
        )
 SELECT q.situacao_ias,
    (q.quantidade)::bigint AS quantidade,
    (b.total_ativos)::bigint AS total_ativos,
    round(((q.quantidade / NULLIF(b.total_ativos, (0)::numeric)) * (100)::numeric), 2) AS percentual
   FROM (quantitativo q
     CROSS JOIN base b)
  ORDER BY
        CASE q.situacao_ias
            WHEN 'EM DIA'::text THEN 1
            WHEN 'ATRASADA'::text THEN 2
            WHEN 'SEM IAS'::text THEN 3
            ELSE 99
        END;


--
-- Name: vw_qpo_agregado; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_qpo_agregado AS
 SELECT lotacao,
    posto_grad,
    (sum(vagas))::integer AS vagas
   FROM b1.qpo_vagas
  GROUP BY lotacao, posto_grad;


--
-- Name: vw_qpo_painel; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_qpo_painel AS
 SELECT q.lotacao,
    q.posto_grad,
    q.vagas,
    COALESCE(count(e.re), (0)::bigint) AS existente,
    (q.vagas - COALESCE(count(e.re), (0)::bigint)) AS claro,
        CASE
            WHEN (q.vagas > 0) THEN round((((COALESCE(count(e.re), (0)::bigint))::numeric / (q.vagas)::numeric) * (100)::numeric), 1)
            ELSE (0)::numeric
        END AS percentual_ocupacao
   FROM (b1.vw_qpo_agregado q
     LEFT JOIN b1.vw_efetivo_classificado e ON (((e.lotacao = q.lotacao) AND (e.posto_qpo = q.posto_grad))))
  GROUP BY q.lotacao, q.posto_grad, q.vagas
  ORDER BY
        CASE q.lotacao
            WHEN 'EM'::text THEN 1
            WHEN '1°Sgb'::text THEN 2
            WHEN '2°Sgb'::text THEN 3
            WHEN '3°Sgb'::text THEN 4
            WHEN '4°Sgb'::text THEN 5
            ELSE 99
        END,
        CASE q.posto_grad
            WHEN 'Ten Cel PM'::text THEN 1
            WHEN 'Maj PM'::text THEN 2
            WHEN 'Cap PM'::text THEN 3
            WHEN 'Ten PM'::text THEN 4
            WHEN 'Subten/Sgt'::text THEN 5
            WHEN 'Cb/Sd'::text THEN 6
            ELSE 99
        END;


--
-- Name: vw_qpo_resumo_geral; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_qpo_resumo_geral AS
 SELECT sum(vagas) AS vagas_totais,
    sum(existente) AS existente_total,
    sum(claro) AS claro_total,
    round(((sum(existente) / (NULLIF(sum(vagas), 0))::numeric) * (100)::numeric), 1) AS percentual_ocupacao_geral
   FROM b1.vw_qpo_painel;


--
-- Name: vw_qpo_resumo_lotacao; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_qpo_resumo_lotacao AS
 SELECT lotacao,
    sum(vagas) AS vagas,
    sum(existente) AS existente,
    sum(claro) AS claro,
    round(((sum(existente) / (NULLIF(sum(vagas), 0))::numeric) * (100)::numeric), 1) AS percentual_ocupacao
   FROM b1.vw_qpo_painel
  GROUP BY lotacao
  ORDER BY
        CASE lotacao
            WHEN 'EM'::text THEN 1
            WHEN '1°Sgb'::text THEN 2
            WHEN '2°Sgb'::text THEN 3
            WHEN '3°Sgb'::text THEN 4
            WHEN '4°Sgb'::text THEN 5
            ELSE NULL::integer
        END;


--
-- Name: vw_qpo_resumo_lotacao_cb_sd; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_qpo_resumo_lotacao_cb_sd AS
 WITH fixo AS (
         SELECT qpo_vagas.lotacao AS unidade,
            sum(qpo_vagas.vagas) AS fixo
           FROM b1.qpo_vagas
          WHERE (qpo_vagas.posto_grad = 'Cb/Sd'::text)
          GROUP BY qpo_vagas.lotacao
        ), ocupado AS (
         SELECT
                CASE
                    WHEN ((efetivo.cod_opm_atual)::text ~~ '990119%'::text) THEN 'EM'::text
                    WHEN ((efetivo.cod_opm_atual)::text ~~ '990111%'::text) THEN '1°Sgb'::text
                    WHEN ((efetivo.cod_opm_atual)::text ~~ '990112%'::text) THEN '2°Sgb'::text
                    WHEN ((efetivo.cod_opm_atual)::text ~~ '990113%'::text) THEN '3°Sgb'::text
                    WHEN ((efetivo.cod_opm_atual)::text ~~ '990114%'::text) THEN '4°Sgb'::text
                    ELSE NULL::text
                END AS unidade,
            count(*) AS ocupado
           FROM b1.efetivo
          WHERE ((efetivo.ativo = true) AND (efetivo.posto_grad = ANY (ARRAY['CB PM'::text, 'SD PM'::text])) AND (((efetivo.cod_opm_atual)::text ~~ '990119%'::text) OR ((efetivo.cod_opm_atual)::text ~~ '990111%'::text) OR ((efetivo.cod_opm_atual)::text ~~ '990112%'::text) OR ((efetivo.cod_opm_atual)::text ~~ '990113%'::text) OR ((efetivo.cod_opm_atual)::text ~~ '990114%'::text)))
          GROUP BY
                CASE
                    WHEN ((efetivo.cod_opm_atual)::text ~~ '990119%'::text) THEN 'EM'::text
                    WHEN ((efetivo.cod_opm_atual)::text ~~ '990111%'::text) THEN '1°Sgb'::text
                    WHEN ((efetivo.cod_opm_atual)::text ~~ '990112%'::text) THEN '2°Sgb'::text
                    WHEN ((efetivo.cod_opm_atual)::text ~~ '990113%'::text) THEN '3°Sgb'::text
                    WHEN ((efetivo.cod_opm_atual)::text ~~ '990114%'::text) THEN '4°Sgb'::text
                    ELSE NULL::text
                END
        )
 SELECT f.unidade,
    f.fixo,
    COALESCE(o.ocupado, (0)::bigint) AS ocupado,
    (f.fixo - COALESCE(o.ocupado, (0)::bigint)) AS vago,
    round(((((f.fixo - COALESCE(o.ocupado, (0)::bigint)))::numeric / (NULLIF(f.fixo, 0))::numeric) * (100)::numeric), 2) AS "% - Claro"
   FROM (fixo f
     LEFT JOIN ocupado o ON ((o.unidade = f.unidade)));


--
-- Name: vw_taf_ultimo_apto_por_re; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_taf_ultimo_apto_por_re AS
 WITH ultimo AS (
         SELECT DISTINCT ON (taf_resultados_raw.re) taf_resultados_raw.re,
            taf_resultados_raw.tipo_taf,
            taf_resultados_raw.resultado,
            taf_resultados_raw.status,
            taf_resultados_raw.data_realizado
           FROM b1.taf_resultados_raw
          WHERE (taf_resultados_raw.resultado = 'Apto'::text)
          ORDER BY taf_resultados_raw.re, taf_resultados_raw.data_realizado DESC NULLS LAST, taf_resultados_raw.criado_em DESC, taf_resultados_raw.id DESC
        )
 SELECT re,
    tipo_taf,
    resultado,
    status,
    data_realizado,
    ((data_realizado + '1 year'::interval))::date AS valido_ate,
        CASE
            WHEN ((data_realizado + '1 year'::interval) >= CURRENT_DATE) THEN 'VÁLIDO'::text
            ELSE 'VENCIDO'::text
        END AS situacao_taf
   FROM ultimo u;


--
-- Name: vw_taf_situacao_atual; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_taf_situacao_atual AS
 SELECT e.re,
    e.nome,
    a.data_realizado,
    COALESCE(a.situacao_taf, 'SEM TAF'::text) AS situacao_taf
   FROM (b1.efetivo e
     LEFT JOIN b1.vw_taf_ultimo_apto_por_re a ON ((a.re = e.re)))
  WHERE (e.ativo = true);


--
-- Name: vw_taf_dashboard; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_taf_dashboard AS
 WITH base AS (
         SELECT vw_taf_situacao_atual.re,
            vw_taf_situacao_atual.nome,
            vw_taf_situacao_atual.data_realizado,
            vw_taf_situacao_atual.situacao_taf
           FROM b1.vw_taf_situacao_atual
        ), totais AS (
         SELECT count(*) AS total_efetivo
           FROM base
        )
 SELECT b.situacao_taf,
    count(*) AS quantidade,
    round((((count(*))::numeric * 100.0) / (t.total_efetivo)::numeric), 2) AS percentual
   FROM (base b
     CROSS JOIN totais t)
  GROUP BY b.situacao_taf, t.total_efetivo
  ORDER BY b.situacao_taf;


--
-- Name: vw_taf_ultimo_finalizado_por_re; Type: VIEW; Schema: b1; Owner: -
--

CREATE VIEW b1.vw_taf_ultimo_finalizado_por_re AS
 SELECT DISTINCT ON (re) id,
    re,
    status,
    resultado,
    tipo_taf,
    data_realizado,
    lote_importacao,
    linha_origem,
    criado_em
   FROM b1.taf_resultados_raw
  WHERE (status = 'Finalizado'::text)
  ORDER BY re, data_realizado DESC, criado_em DESC, id DESC;


--
-- Name: auditoria_cobom; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.auditoria_cobom (
    id bigint NOT NULL,
    re integer NOT NULL,
    posto_grad text NOT NULL,
    nome text NOT NULL,
    informacao_num text,
    data_servico date NOT NULL,
    turno text,
    equipe text,
    posto_atendimento text,
    avaliador_1 text,
    avaliador_2 text,
    audios jsonb DEFAULT '[]'::jsonb NOT NULL,
    respostas jsonb NOT NULL,
    nota integer NOT NULL,
    parecer text NOT NULL,
    observacoes text,
    prov_encarregado text,
    prov_chefe text,
    prov_supervisao text,
    criado_por integer,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    atualizado_por integer,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT auditoria_cobom_parecer_check CHECK ((parecer = ANY (ARRAY['APROVADO'::text, 'APROVADO COM ORIENTAÇÕES'::text, 'REPROVADO'::text])))
);


--
-- Name: TABLE auditoria_cobom; Type: COMMENT; Schema: b3; Owner: -
--

COMMENT ON TABLE b3.auditoria_cobom IS 'Fichas de avaliação de desempenho do atendente 193 (monitoria de qualidade do COBOM). Questionário definido em webapp/routers/auditoria_cobom.py.';


--
-- Name: auditoria_cobom_id_seq; Type: SEQUENCE; Schema: b3; Owner: -
--

CREATE SEQUENCE b3.auditoria_cobom_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: auditoria_cobom_id_seq; Type: SEQUENCE OWNED BY; Schema: b3; Owner: -
--

ALTER SEQUENCE b3.auditoria_cobom_id_seq OWNED BY b3.auditoria_cobom.id;


--
-- Name: eap_dispensa; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.eap_dispensa (
    re integer NOT NULL,
    motivo text DEFAULT 'CAO'::text NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    criado_por text
);


--
-- Name: eap_inscricao; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.eap_inscricao (
    turma_id integer NOT NULL,
    re integer NOT NULL,
    escalado boolean DEFAULT false NOT NULL,
    observacao text,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    criado_por text,
    atualizado_em timestamp with time zone
);


--
-- Name: eap_modelo; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.eap_modelo (
    ano integer NOT NULL,
    arquivo bytea NOT NULL,
    nome_arquivo text,
    enviado_em timestamp with time zone DEFAULT now() NOT NULL,
    enviado_por text
);


--
-- Name: eap_os; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.eap_os (
    id integer NOT NULL,
    ano integer NOT NULL,
    numero integer NOT NULL,
    turma_ids integer[] NOT NULL,
    campos jsonb NOT NULL,
    gerado_em timestamp with time zone DEFAULT now() NOT NULL,
    gerado_por text
);


--
-- Name: eap_os_id_seq; Type: SEQUENCE; Schema: b3; Owner: -
--

CREATE SEQUENCE b3.eap_os_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: eap_os_id_seq; Type: SEQUENCE OWNED BY; Schema: b3; Owner: -
--

ALTER SEQUENCE b3.eap_os_id_seq OWNED BY b3.eap_os.id;


--
-- Name: eap_turma; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.eap_turma (
    id integer NOT NULL,
    ano integer NOT NULL,
    ead_inicio date NOT NULL,
    ead_fim date NOT NULL,
    presencial_em timestamp without time zone,
    presencial_local text,
    vagas integer,
    observacao text,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    criado_por text,
    atualizado_em timestamp with time zone,
    publicos jsonb NOT NULL,
    CONSTRAINT eap_turma_check CHECK ((ead_fim >= ead_inicio))
);


--
-- Name: eap_turma_id_seq; Type: SEQUENCE; Schema: b3; Owner: -
--

CREATE SEQUENCE b3.eap_turma_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: eap_turma_id_seq; Type: SEQUENCE OWNED BY; Schema: b3; Owner: -
--

ALTER SEQUENCE b3.eap_turma_id_seq OWNED BY b3.eap_turma.id;


--
-- Name: mapa_forca_estacao; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.mapa_forca_estacao (
    id bigint NOT NULL,
    snapshot_id bigint NOT NULL,
    bloco_nome text NOT NULL,
    estacao_nome text,
    estacao_codigo text,
    estacao_telefone text,
    capacidade_agua_l integer,
    mergulhadores integer,
    ordem integer NOT NULL
);


--
-- Name: mapa_forca_estacao_id_seq; Type: SEQUENCE; Schema: b3; Owner: -
--

CREATE SEQUENCE b3.mapa_forca_estacao_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mapa_forca_estacao_id_seq; Type: SEQUENCE OWNED BY; Schema: b3; Owner: -
--

ALTER SEQUENCE b3.mapa_forca_estacao_id_seq OWNED BY b3.mapa_forca_estacao.id;


--
-- Name: mapa_forca_linha; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.mapa_forca_linha (
    id bigint NOT NULL,
    snapshot_id bigint NOT NULL,
    bloco_nome text NOT NULL,
    estacao_bombeiros text,
    viatura text,
    situacao text,
    efetivo_qtd integer,
    posto_graduacao text,
    militar_e_telefone text,
    capacidade_agua_l integer,
    mergulhadores integer,
    ordem integer NOT NULL,
    estacao_id bigint
);


--
-- Name: mapa_forca_linha_id_seq; Type: SEQUENCE; Schema: b3; Owner: -
--

CREATE SEQUENCE b3.mapa_forca_linha_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mapa_forca_linha_id_seq; Type: SEQUENCE OWNED BY; Schema: b3; Owner: -
--

ALTER SEQUENCE b3.mapa_forca_linha_id_seq OWNED BY b3.mapa_forca_linha.id;


--
-- Name: mapa_forca_snapshot_raw; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.mapa_forca_snapshot_raw (
    id bigint NOT NULL,
    fonte_planilha_id text NOT NULL,
    fonte_aba text NOT NULL,
    capturado_em timestamp with time zone DEFAULT now() NOT NULL,
    data_servico date,
    cabecalho_texto text,
    conteudo_sha256 text NOT NULL,
    payload_raw jsonb NOT NULL
);


--
-- Name: mapa_forca_snapshot_raw_id_seq; Type: SEQUENCE; Schema: b3; Owner: -
--

CREATE SEQUENCE b3.mapa_forca_snapshot_raw_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mapa_forca_snapshot_raw_id_seq; Type: SEQUENCE OWNED BY; Schema: b3; Owner: -
--

ALTER SEQUENCE b3.mapa_forca_snapshot_raw_id_seq OWNED BY b3.mapa_forca_snapshot_raw.id;


--
-- Name: nivel_op_captura; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.nivel_op_captura (
    id bigint NOT NULL,
    capturado_em timestamp with time zone DEFAULT now() NOT NULL,
    estacoes_lidas integer DEFAULT 0 NOT NULL,
    viaturas_lidas integer DEFAULT 0 NOT NULL,
    viaturas_numreg integer DEFAULT 0 NOT NULL,
    estacoes_erro text[] DEFAULT '{}'::text[] NOT NULL
);


--
-- Name: nivel_op_captura_id_seq; Type: SEQUENCE; Schema: b3; Owner: -
--

CREATE SEQUENCE b3.nivel_op_captura_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nivel_op_captura_id_seq; Type: SEQUENCE OWNED BY; Schema: b3; Owner: -
--

ALTER SEQUENCE b3.nivel_op_captura_id_seq OWNED BY b3.nivel_op_captura.id;


--
-- Name: nivel_op_integrante; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.nivel_op_integrante (
    id bigint NOT NULL,
    viatura_id bigint NOT NULL,
    ordem integer NOT NULL,
    posto text,
    re integer,
    nome_guerra text,
    bruto text NOT NULL
);


--
-- Name: nivel_op_integrante_id_seq; Type: SEQUENCE; Schema: b3; Owner: -
--

CREATE SEQUENCE b3.nivel_op_integrante_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nivel_op_integrante_id_seq; Type: SEQUENCE OWNED BY; Schema: b3; Owner: -
--

ALTER SEQUENCE b3.nivel_op_integrante_id_seq OWNED BY b3.nivel_op_integrante.id;


--
-- Name: nivel_op_viatura; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.nivel_op_viatura (
    id bigint NOT NULL,
    captura_id bigint NOT NULL,
    opm_cod text NOT NULL,
    estacao_nome text NOT NULL,
    ordem integer NOT NULL,
    us text NOT NULL,
    status text,
    status_grp text,
    componente text,
    territorio text,
    programa text,
    programa_cod text,
    modalidade text,
    operacao text,
    inicio timestamp without time zone,
    termino timestamp without time zone,
    exige_vtr text,
    existe_vtr text,
    cad_cod text,
    ptrcpn_cod text,
    viatura_prefixo text,
    tpd text,
    efetivo_qtd integer DEFAULT 0 NOT NULL
);


--
-- Name: nivel_op_viatura_id_seq; Type: SEQUENCE; Schema: b3; Owner: -
--

CREATE SEQUENCE b3.nivel_op_viatura_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nivel_op_viatura_id_seq; Type: SEQUENCE OWNED BY; Schema: b3; Owner: -
--

ALTER SEQUENCE b3.nivel_op_viatura_id_seq OWNED BY b3.nivel_op_viatura.id;


--
-- Name: ocorrencias; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.ocorrencias (
    id bigint NOT NULL,
    ocrnum integer,
    ocrdat date NOT NULL,
    statusid smallint,
    cadcod smallint,
    situacaoid smallint,
    atendimentotipoid smallint,
    natcod text,
    dt_chamada timestamp without time zone,
    dt_geracao timestamp without time zone,
    dt_finalizacao timestamp without time zone,
    dt_homologacao timestamp without time zone,
    despacho_min numeric(12,2),
    sgb text,
    gb text,
    comando text,
    pb text,
    opm_fato bigint,
    opm_atendimento bigint,
    logradouro_inicial text,
    numero_inicial text,
    complemento_inicial text,
    bairro_inicial text,
    referencia_inicial text,
    municipio_inicial integer,
    endereco_inicial text,
    logradouro_final text,
    numero_final text,
    complemento_final text,
    bairro_final text,
    municipio_final integer,
    cep_final text,
    endereco text,
    localizacao_inicial text,
    localizacao_final text,
    lon_inicial numeric(11,7),
    lat_inicial numeric(11,7),
    lon_final numeric(11,7),
    lat_final numeric(11,7),
    dados_complementares text,
    historico text,
    motivo_devolucao text,
    comandante_cpf text,
    homologador_cpf text,
    possui_guia smallint,
    ocr_rst_cod smallint,
    lote_importacao text,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    atualizado_em timestamp with time zone
);


--
-- Name: tempo_resposta; Type: TABLE; Schema: b3; Owner: -
--

CREATE TABLE b3.tempo_resposta (
    id_sdov bigint NOT NULL,
    viatura text NOT NULL,
    dt_ocorrencia timestamp without time zone,
    num_ocorrencia integer,
    municipio text,
    bairro text,
    natureza text,
    sgb text,
    t_atendimento_min numeric(10,4),
    t_despacho_min numeric(10,4),
    t_deslocamento_min numeric(10,4),
    lote_importacao text,
    criado_em timestamp with time zone DEFAULT now(),
    atualizado_em timestamp with time zone DEFAULT now()
);


--
-- Name: vw_mapa_ultimo_snapshot_dia; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_mapa_ultimo_snapshot_dia AS
 SELECT DISTINCT ON ((((capturado_em AT TIME ZONE 'America/Sao_Paulo'::text))::date)) id AS snapshot_id,
    ((capturado_em AT TIME ZONE 'America/Sao_Paulo'::text))::date AS data_ref,
    capturado_em,
    fonte_planilha_id,
    fonte_aba
   FROM b3.mapa_forca_snapshot_raw
  ORDER BY (((capturado_em AT TIME ZONE 'America/Sao_Paulo'::text))::date), capturado_em DESC;


--
-- Name: vw_mapa_estacoes_hoje; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_mapa_estacoes_hoje AS
 SELECT u.data_ref,
    u.snapshot_id,
    e.bloco_nome,
    e.estacao_nome,
    e.estacao_codigo,
    e.estacao_telefone,
    e.capacidade_agua_l,
    e.mergulhadores,
    e.ordem
   FROM (b3.vw_mapa_ultimo_snapshot_dia u
     JOIN b3.mapa_forca_estacao e ON ((e.snapshot_id = u.snapshot_id)))
  WHERE (u.data_ref = ((now() AT TIME ZONE 'America/Sao_Paulo'::text))::date);


--
-- Name: vw_agua_disponivel_hoje; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_agua_disponivel_hoje AS
 SELECT data_ref,
    bloco_nome,
    sum(COALESCE(capacidade_agua_l, 0)) AS agua_total_litros
   FROM b3.vw_mapa_estacoes_hoje
  GROUP BY data_ref, bloco_nome
  ORDER BY bloco_nome;


--
-- Name: vw_mapa_linhas_hoje; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_mapa_linhas_hoje AS
 SELECT u.data_ref,
    u.snapshot_id,
    l.bloco_nome,
    l.estacao_bombeiros,
    l.viatura,
    l.situacao,
    l.efetivo_qtd,
    l.posto_graduacao,
    l.militar_e_telefone,
    l.capacidade_agua_l,
    l.mergulhadores,
    l.ordem
   FROM (b3.vw_mapa_ultimo_snapshot_dia u
     JOIN b3.mapa_forca_linha l ON ((l.snapshot_id = u.snapshot_id)))
  WHERE (u.data_ref = ((now() AT TIME ZONE 'America/Sao_Paulo'::text))::date);


--
-- Name: vw_efetivo_operacional_hoje; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_efetivo_operacional_hoje AS
 SELECT data_ref,
    bloco_nome,
    sum(COALESCE(efetivo_qtd, 0)) AS efetivo_operacional
   FROM b3.vw_mapa_linhas_hoje
  WHERE (situacao = 'OPERANDO'::text)
  GROUP BY data_ref, bloco_nome
  ORDER BY bloco_nome;


--
-- Name: vw_mergulhadores_hoje; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_mergulhadores_hoje AS
 SELECT data_ref,
    bloco_nome,
    sum(COALESCE(mergulhadores, 0)) AS total_mergulhadores
   FROM b3.vw_mapa_estacoes_hoje
  GROUP BY data_ref, bloco_nome
  ORDER BY bloco_nome;


--
-- Name: vw_nivel_op_atual; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_nivel_op_atual AS
 SELECT c.capturado_em,
    v.id,
    v.captura_id,
    v.opm_cod,
    v.estacao_nome,
    v.ordem,
    v.us,
    v.status,
    v.status_grp,
    v.componente,
    v.territorio,
    v.programa,
    v.programa_cod,
    v.modalidade,
    v.operacao,
    v.inicio,
    v.termino,
    v.exige_vtr,
    v.existe_vtr,
    v.cad_cod,
    v.ptrcpn_cod,
    v.viatura_prefixo,
    v.tpd,
    v.efetivo_qtd
   FROM (b3.nivel_op_viatura v
     JOIN b3.nivel_op_captura c ON ((c.id = v.captura_id)))
  WHERE (v.captura_id = ( SELECT max(nivel_op_captura.id) AS max
           FROM b3.nivel_op_captura));


--
-- Name: vw_nivel_op_integrantes_atual; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_nivel_op_integrantes_atual AS
 SELECT a.capturado_em,
    a.opm_cod,
    a.estacao_nome,
    a.us,
    a.status,
    a.modalidade,
    a.inicio,
    a.termino,
    i.ordem,
    i.posto,
    i.re,
    i.nome_guerra
   FROM (b3.vw_nivel_op_atual a
     JOIN b3.nivel_op_integrante i ON ((i.viatura_id = a.id)));


--
-- Name: vw_ocorrencias_mensal; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_ocorrencias_mensal AS
 SELECT (date_trunc('month'::text, (ocrdat)::timestamp with time zone))::date AS mes,
    (EXTRACT(year FROM ocrdat))::integer AS ano,
    (EXTRACT(month FROM ocrdat))::integer AS mes_num,
    sgb,
    count(*) AS ocorrencias,
    count(*) FILTER (WHERE ((despacho_min >= (0)::numeric) AND (despacho_min <= (120)::numeric))) AS com_tempo_valido,
    round((percentile_cont((0.5)::double precision) WITHIN GROUP (ORDER BY ((despacho_min)::double precision)) FILTER (WHERE ((despacho_min >= (0)::numeric) AND (despacho_min <= (120)::numeric))))::numeric, 1) AS despacho_mediana_min,
    round((percentile_cont((0.9)::double precision) WITHIN GROUP (ORDER BY ((despacho_min)::double precision)) FILTER (WHERE ((despacho_min >= (0)::numeric) AND (despacho_min <= (120)::numeric))))::numeric, 1) AS despacho_p90_min
   FROM b3.ocorrencias
  GROUP BY ((date_trunc('month'::text, (ocrdat)::timestamp with time zone))::date), ((EXTRACT(year FROM ocrdat))::integer), ((EXTRACT(month FROM ocrdat))::integer), sgb;


--
-- Name: VIEW vw_ocorrencias_mensal; Type: COMMENT; Schema: b3; Owner: -
--

COMMENT ON VIEW b3.vw_ocorrencias_mensal IS 'Ocorrências por mês e SGB, com tempo de despacho (chamada -> geração) em mediana e p90. Não existe carimbo de chegada no local na fonte, então tempo até a chegada não é calculável.';


--
-- Name: vw_viaturas_situacao_hoje; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_viaturas_situacao_hoje AS
 SELECT data_ref,
    bloco_nome,
    COALESCE(situacao, 'SEM INFORMACAO'::text) AS situacao,
    count(*) AS qtd_viaturas
   FROM b3.vw_mapa_linhas_hoje
  GROUP BY data_ref, bloco_nome, COALESCE(situacao, 'SEM INFORMACAO'::text)
  ORDER BY bloco_nome, COALESCE(situacao, 'SEM INFORMACAO'::text);


--
-- Name: vw_pizza_sgb_situacao_hoje; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_pizza_sgb_situacao_hoje AS
 SELECT ((bloco_nome || ' - '::text) || situacao) AS categoria,
    sum(qtd_viaturas) AS total
   FROM b3.vw_viaturas_situacao_hoje
  GROUP BY bloco_nome, situacao
  ORDER BY bloco_nome, situacao;


--
-- Name: vw_resumo_operacional_hoje; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_resumo_operacional_hoje AS
 SELECT data_ref,
    count(*) FILTER (WHERE (situacao = 'OPERANDO'::text)) AS viaturas_operando,
    count(*) FILTER (WHERE (situacao = 'RESERVA'::text)) AS viaturas_reserva,
    count(*) FILTER (WHERE (situacao = ANY (ARRAY['BAIXADA'::text, 'BAIXADO'::text]))) AS viaturas_baixadas,
    sum(COALESCE(efetivo_qtd, 0)) FILTER (WHERE (situacao = 'OPERANDO'::text)) AS efetivo_operacional,
    ( SELECT COALESCE(sum(COALESCE(e.capacidade_agua_l, 0)), (0)::bigint) AS "coalesce"
           FROM b3.vw_mapa_estacoes_hoje e
          WHERE (e.data_ref = l.data_ref)) AS agua_total_litros,
    ( SELECT COALESCE(sum(COALESCE(e.mergulhadores, 0)), (0)::bigint) AS "coalesce"
           FROM b3.vw_mapa_estacoes_hoje e
          WHERE (e.data_ref = l.data_ref)) AS mergulhadores_total
   FROM b3.vw_mapa_linhas_hoje l
  GROUP BY data_ref;


--
-- Name: vw_tempo_resposta_valido; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_tempo_resposta_valido AS
 SELECT id_sdov,
    viatura,
    dt_ocorrencia,
    num_ocorrencia,
    municipio,
    bairro,
    natureza,
    sgb,
    t_atendimento_min,
    t_despacho_min,
    t_deslocamento_min,
    lote_importacao,
    criado_em,
    atualizado_em,
    ((t_atendimento_min + t_despacho_min) + t_deslocamento_min) AS t_total_min
   FROM b3.tempo_resposta
  WHERE (((t_atendimento_min >= (0)::numeric) AND (t_atendimento_min <= (600)::numeric)) AND ((t_despacho_min >= (0)::numeric) AND (t_despacho_min <= (600)::numeric)) AND ((t_deslocamento_min >= (0)::numeric) AND (t_deslocamento_min <= (600)::numeric)));


--
-- Name: vw_tempo_resposta_ocorrencia; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_tempo_resposta_ocorrencia AS
 SELECT id_sdov,
    min(dt_ocorrencia) AS dt_ocorrencia,
    min(num_ocorrencia) AS num_ocorrencia,
    min(municipio) AS municipio,
    min(bairro) AS bairro,
    min(natureza) AS natureza,
    min(sgb) AS sgb,
    count(*) AS viaturas_empenhadas,
    max(t_atendimento_min) AS t_atendimento_min,
    max(t_despacho_min) AS t_despacho_min,
    min(t_deslocamento_min) AS t_deslocamento_min,
    ((max(t_atendimento_min) + max(t_despacho_min)) + min(t_deslocamento_min)) AS t_total_min
   FROM b3.vw_tempo_resposta_valido
  GROUP BY id_sdov;


--
-- Name: vw_tempo_resposta_anual; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_tempo_resposta_anual AS
 SELECT (EXTRACT(year FROM dt_ocorrencia))::integer AS ano,
    count(*) AS ocorrencias,
    round(avg(t_atendimento_min), 2) AS atendimento_medio,
    round(avg(t_despacho_min), 2) AS despacho_medio,
    round(avg(t_deslocamento_min), 2) AS deslocamento_medio,
    round(avg(t_total_min), 2) AS total_medio,
    round((percentile_cont((0.5)::double precision) WITHIN GROUP (ORDER BY ((t_total_min)::double precision)))::numeric, 2) AS total_mediana,
    round((percentile_cont((0.9)::double precision) WITHIN GROUP (ORDER BY ((t_total_min)::double precision)))::numeric, 2) AS total_p90
   FROM b3.vw_tempo_resposta_ocorrencia
  GROUP BY ((EXTRACT(year FROM dt_ocorrencia))::integer)
  ORDER BY ((EXTRACT(year FROM dt_ocorrencia))::integer);


--
-- Name: vw_tempo_resposta_composicao; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_tempo_resposta_composicao AS
 SELECT (EXTRACT(year FROM dt_ocorrencia))::integer AS ano,
    round(((100.0 * sum(t_atendimento_min)) / NULLIF(sum(t_total_min), (0)::numeric)), 1) AS pct_atendimento,
    round(((100.0 * sum(t_despacho_min)) / NULLIF(sum(t_total_min), (0)::numeric)), 1) AS pct_despacho,
    round(((100.0 * sum(t_deslocamento_min)) / NULLIF(sum(t_total_min), (0)::numeric)), 1) AS pct_deslocamento
   FROM b3.vw_tempo_resposta_ocorrencia
  GROUP BY ((EXTRACT(year FROM dt_ocorrencia))::integer)
  ORDER BY ((EXTRACT(year FROM dt_ocorrencia))::integer);


--
-- Name: vw_tempo_resposta_faixas; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_tempo_resposta_faixas AS
 SELECT (EXTRACT(year FROM dt_ocorrencia))::integer AS ano,
        CASE
            WHEN (natureza ~~* '%incêndio%'::text) THEN 'Incêndio'::text
            WHEN (natureza ~~* '%acidente de trânsito%'::text) THEN 'Acidente de trânsito'::text
            WHEN (natureza ~~* '%sem intervenção%'::text) THEN 'Sem intervenção'::text
            ELSE 'Demais'::text
        END AS grupo,
    count(*) AS ocorrencias,
    round(((100.0 * (count(*) FILTER (WHERE (t_total_min <= (10)::numeric)))::numeric) / (count(*))::numeric), 1) AS pct_ate_10min,
    round(((100.0 * (count(*) FILTER (WHERE (t_total_min <= (20)::numeric)))::numeric) / (count(*))::numeric), 1) AS pct_ate_20min,
    round(((100.0 * (count(*) FILTER (WHERE (t_total_min <= (30)::numeric)))::numeric) / (count(*))::numeric), 1) AS pct_ate_30min,
    round((percentile_cont((0.5)::double precision) WITHIN GROUP (ORDER BY ((t_total_min)::double precision)))::numeric, 1) AS mediana
   FROM b3.vw_tempo_resposta_ocorrencia
  GROUP BY ((EXTRACT(year FROM dt_ocorrencia))::integer),
        CASE
            WHEN (natureza ~~* '%incêndio%'::text) THEN 'Incêndio'::text
            WHEN (natureza ~~* '%acidente de trânsito%'::text) THEN 'Acidente de trânsito'::text
            WHEN (natureza ~~* '%sem intervenção%'::text) THEN 'Sem intervenção'::text
            ELSE 'Demais'::text
        END
  ORDER BY ((EXTRACT(year FROM dt_ocorrencia))::integer),
        CASE
            WHEN (natureza ~~* '%incêndio%'::text) THEN 'Incêndio'::text
            WHEN (natureza ~~* '%acidente de trânsito%'::text) THEN 'Acidente de trânsito'::text
            WHEN (natureza ~~* '%sem intervenção%'::text) THEN 'Sem intervenção'::text
            ELSE 'Demais'::text
        END;


--
-- Name: vw_tempo_resposta_municipio; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_tempo_resposta_municipio AS
 SELECT municipio,
    count(*) AS ocorrencias,
    round(avg(t_deslocamento_min), 2) AS deslocamento_medio,
    round((percentile_cont((0.5)::double precision) WITHIN GROUP (ORDER BY ((t_deslocamento_min)::double precision)))::numeric, 2) AS deslocamento_mediana,
    round(avg(t_total_min), 2) AS total_medio
   FROM b3.vw_tempo_resposta_ocorrencia
  WHERE (municipio IS NOT NULL)
  GROUP BY municipio
 HAVING (count(*) >= 100)
  ORDER BY (round((percentile_cont((0.5)::double precision) WITHIN GROUP (ORDER BY ((t_deslocamento_min)::double precision)))::numeric, 2)) DESC;


--
-- Name: vw_tempo_resposta_sgb; Type: VIEW; Schema: b3; Owner: -
--

CREATE VIEW b3.vw_tempo_resposta_sgb AS
 SELECT (EXTRACT(year FROM dt_ocorrencia))::integer AS ano,
    sgb,
    count(*) AS ocorrencias,
    round(avg(t_atendimento_min), 2) AS atendimento_medio,
    round(avg(t_despacho_min), 2) AS despacho_medio,
    round(avg(t_deslocamento_min), 2) AS deslocamento_medio,
    round(avg(t_total_min), 2) AS total_medio,
    round((percentile_cont((0.5)::double precision) WITHIN GROUP (ORDER BY ((t_total_min)::double precision)))::numeric, 2) AS total_mediana
   FROM b3.vw_tempo_resposta_ocorrencia
  WHERE (sgb IS NOT NULL)
  GROUP BY ((EXTRACT(year FROM dt_ocorrencia))::integer), sgb
  ORDER BY ((EXTRACT(year FROM dt_ocorrencia))::integer), sgb;


--
-- Name: siopm_estacao; Type: TABLE; Schema: b4; Owner: -
--

CREATE TABLE b4.siopm_estacao (
    opm_cod text NOT NULL,
    sgb text NOT NULL,
    pb_bb text NOT NULL,
    nome_estacao text NOT NULL,
    municipio text NOT NULL
);


--
-- Name: viaturas; Type: TABLE; Schema: b4; Owner: -
--

CREATE TABLE b4.viaturas (
    id bigint NOT NULL,
    prefixo text NOT NULL,
    opmcb text,
    sgb text,
    pb_bb text,
    nome_estacao text,
    municipio text,
    status text,
    status_raw text,
    proprietario text,
    placa text,
    fabricante text,
    modelo text,
    tipo text,
    ano_fabricacao integer,
    ano_modelo integer,
    combustivel text,
    patrimonio text,
    patrimonio_estado text,
    chassi text,
    renavam text,
    riv text,
    obs text,
    lote_importacao text NOT NULL,
    linha_origem integer,
    carregado_em timestamp with time zone DEFAULT now() NOT NULL,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    status_origem text DEFAULT 'PLANILHA'::text NOT NULL,
    origem_cadastro text DEFAULT 'PLANILHA'::text NOT NULL,
    siopm_us text,
    siopm_status text,
    siopm_opm_cod text,
    siopm_captura_id bigint,
    siopm_visto_em timestamp with time zone
);


--
-- Name: viaturas_id_seq; Type: SEQUENCE; Schema: b4; Owner: -
--

CREATE SEQUENCE b4.viaturas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: viaturas_id_seq; Type: SEQUENCE OWNED BY; Schema: b4; Owner: -
--

ALTER SEQUENCE b4.viaturas_id_seq OWNED BY b4.viaturas.id;


--
-- Name: viaturas_sync_siopm; Type: TABLE; Schema: b4; Owner: -
--

CREATE TABLE b4.viaturas_sync_siopm (
    id bigint NOT NULL,
    executado_em timestamp with time zone DEFAULT now() NOT NULL,
    captura_id bigint NOT NULL,
    prefixo text NOT NULL,
    campo text NOT NULL,
    antes text,
    depois text
);


--
-- Name: viaturas_sync_siopm_id_seq; Type: SEQUENCE; Schema: b4; Owner: -
--

CREATE SEQUENCE b4.viaturas_sync_siopm_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: viaturas_sync_siopm_id_seq; Type: SEQUENCE OWNED BY; Schema: b4; Owner: -
--

ALTER SEQUENCE b4.viaturas_sync_siopm_id_seq OWNED BY b4.viaturas_sync_siopm.id;


--
-- Name: vw_painel_viaturas; Type: VIEW; Schema: b4; Owner: -
--

CREATE VIEW b4.vw_painel_viaturas AS
 SELECT sgb,
    tipo,
    count(*) AS total,
    count(*) FILTER (WHERE (status = 'OPERANDO'::text)) AS operando,
    count(*) FILTER (WHERE (status = ANY (ARRAY['BAIXADA'::text, 'BAIXADA_DESCARGA'::text]))) AS baixadas,
    count(*) FILTER (WHERE (status = 'PROC_DESCARGA'::text)) AS em_descarga,
    round((((count(*) FILTER (WHERE (status = ANY (ARRAY['BAIXADA'::text, 'BAIXADA_DESCARGA'::text]))))::numeric / (NULLIF(count(*), 0))::numeric) * (100)::numeric), 1) AS pct_baixadas,
    round(avg(((EXTRACT(year FROM CURRENT_DATE))::integer - ano_fabricacao)), 1) AS idade_media
   FROM b4.viaturas
  WHERE (ano_fabricacao IS NOT NULL)
  GROUP BY sgb, tipo
  ORDER BY sgb, tipo;


--
-- Name: vw_ppmq_idade_media; Type: VIEW; Schema: b4; Owner: -
--

CREATE VIEW b4.vw_ppmq_idade_media AS
 SELECT count(*) AS total_viaturas,
    round(avg(((EXTRACT(year FROM CURRENT_DATE))::integer - ano_fabricacao)), 2) AS idade_media_anos,
    min(((EXTRACT(year FROM CURRENT_DATE))::integer - ano_fabricacao)) AS idade_minima,
    max(((EXTRACT(year FROM CURRENT_DATE))::integer - ano_fabricacao)) AS idade_maxima,
    count(*) FILTER (WHERE (((EXTRACT(year FROM CURRENT_DATE))::integer - ano_fabricacao) > 15)) AS viaturas_acima_15anos
   FROM b4.viaturas
  WHERE (ano_fabricacao IS NOT NULL);


--
-- Name: vw_ppmq_taxa_baixadas; Type: VIEW; Schema: b4; Owner: -
--

CREATE VIEW b4.vw_ppmq_taxa_baixadas AS
 SELECT count(*) AS total_viaturas,
    count(*) FILTER (WHERE (proprietario <> ALL (ARRAY['LOCADA'::text, 'N/P'::text]))) AS titulares_nop,
    count(*) FILTER (WHERE (status = ANY (ARRAY['BAIXADA'::text, 'BAIXADA_DESCARGA'::text]))) AS baixadas,
    round((((count(*) FILTER (WHERE (status = ANY (ARRAY['BAIXADA'::text, 'BAIXADA_DESCARGA'::text]))))::numeric / (NULLIF(count(*) FILTER (WHERE (proprietario <> ALL (ARRAY['LOCADA'::text, 'N/P'::text]))), 0))::numeric) * (100)::numeric), 2) AS taxa_baixadas_pct,
        CASE
            WHEN (round((((count(*) FILTER (WHERE (status = ANY (ARRAY['BAIXADA'::text, 'BAIXADA_DESCARGA'::text]))))::numeric / (NULLIF(count(*) FILTER (WHERE (proprietario <> ALL (ARRAY['LOCADA'::text, 'N/P'::text]))), 0))::numeric) * (100)::numeric), 2) <= (20)::numeric) THEN '✅ Dentro da meta'::text
            ELSE '❌ Acima da meta'::text
        END AS situacao_meta
   FROM b4.viaturas;


--
-- Name: vw_viaturas_fora_siopm; Type: VIEW; Schema: b4; Owner: -
--

CREATE VIEW b4.vw_viaturas_fora_siopm AS
 SELECT prefixo,
    tipo,
    sgb,
    nome_estacao,
    status,
    proprietario,
    placa,
    siopm_visto_em,
    atualizado_em
   FROM b4.viaturas
  WHERE ((siopm_visto_em IS NULL) OR (siopm_visto_em < ( SELECT (max(viaturas_1.siopm_visto_em) - '01:00:00'::interval)
           FROM b4.viaturas viaturas_1)))
  ORDER BY tipo, prefixo;


--
-- Name: vw_viaturas_situacao; Type: VIEW; Schema: b4; Owner: -
--

CREATE VIEW b4.vw_viaturas_situacao AS
 SELECT prefixo,
    sgb,
    pb_bb,
    nome_estacao,
    municipio,
    tipo,
    fabricante,
    modelo,
    ano_fabricacao,
    ((EXTRACT(year FROM CURRENT_DATE))::integer - ano_fabricacao) AS idade_anos,
    status,
    proprietario,
    placa,
    patrimonio_estado,
    obs,
    atualizado_em
   FROM b4.viaturas
  WHERE (siopm_visto_em >= ( SELECT (max(viaturas_1.siopm_visto_em) - '01:00:00'::interval)
           FROM b4.viaturas viaturas_1))
  ORDER BY sgb, tipo, prefixo;


--
-- Name: elogios; Type: TABLE; Schema: b5; Owner: -
--

CREATE TABLE b5.elogios (
    id integer NOT NULL,
    nbi integer,
    num_bi_11gb integer,
    posto_grad text,
    re text,
    nome text,
    assunto text,
    tipo text,
    data_elogio date,
    sgb text,
    data_lancamento date,
    lancador text,
    solenidade text,
    observacoes text,
    data_base date,
    boletim text,
    mes_ano text,
    ano integer,
    carregado_em timestamp with time zone DEFAULT now()
);


--
-- Name: elogios_id_seq; Type: SEQUENCE; Schema: b5; Owner: -
--

CREATE SEQUENCE b5.elogios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: elogios_id_seq; Type: SEQUENCE OWNED BY; Schema: b5; Owner: -
--

ALTER SEQUENCE b5.elogios_id_seq OWNED BY b5.elogios.id;


--
-- Name: contatos_autorizados; Type: TABLE; Schema: bia; Owner: -
--

CREATE TABLE bia.contatos_autorizados (
    id integer NOT NULL,
    telefone character varying(20) NOT NULL,
    re integer,
    posto_abrev character varying(20),
    nome_curto character varying(60),
    apelido character varying(60),
    papel character varying(30),
    observacao text,
    criado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: contatos_autorizados_id_seq; Type: SEQUENCE; Schema: bia; Owner: -
--

CREATE SEQUENCE bia.contatos_autorizados_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: contatos_autorizados_id_seq; Type: SEQUENCE OWNED BY; Schema: bia; Owner: -
--

ALTER SEQUENCE bia.contatos_autorizados_id_seq OWNED BY bia.contatos_autorizados.id;


--
-- Name: indicadores_mensais; Type: TABLE; Schema: sjd; Owner: -
--

CREATE TABLE sjd.indicadores_mensais (
    indicador text NOT NULL,
    ano integer NOT NULL,
    mes integer NOT NULL,
    valor integer NOT NULL,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT indicadores_mensais_mes_check CHECK (((mes >= 1) AND (mes <= 12)))
);


--
-- Name: processos; Type: TABLE; Schema: sjd; Owner: -
--

CREATE TABLE sjd.processos (
    id bigint NOT NULL,
    data_abertura date NOT NULL,
    titulo text,
    tipo text,
    interessado text,
    unidade text,
    punicao text,
    finalizado text,
    conteudo_sha256 text NOT NULL,
    origem_arquivo text,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: processos_id_seq; Type: SEQUENCE; Schema: sjd; Owner: -
--

CREATE SEQUENCE sjd.processos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: processos_id_seq; Type: SEQUENCE OWNED BY; Schema: sjd; Owner: -
--

ALTER SEQUENCE sjd.processos_id_seq OWNED BY sjd.processos.id;


--
-- Name: vw_kpis_ano; Type: VIEW; Schema: sjd; Owner: -
--

CREATE VIEW sjd.vw_kpis_ano AS
 SELECT ano,
    sum(
        CASE
            WHEN (indicador = 'acidentes_folga_bombeiro'::text) THEN valor
            ELSE NULL::integer
        END) AS acidentes_folga_bombeiro,
    sum(
        CASE
            WHEN (indicador = 'acidentes_viatura_vitima'::text) THEN valor
            ELSE NULL::integer
        END) AS acidentes_viatura_vitima,
    sum(
        CASE
            WHEN (indicador = 'reclamacoes_denuncias'::text) THEN valor
            ELSE NULL::integer
        END) AS reclamacoes_denuncias
   FROM sjd.indicadores_mensais
  GROUP BY ano
  ORDER BY ano;


--
-- Name: pendencia_baixas; Type: TABLE; Schema: uge; Owner: -
--

CREATE TABLE uge.pendencia_baixas (
    id integer NOT NULL,
    processo_id integer NOT NULL,
    usuario_id integer NOT NULL,
    pendencia_texto text,
    assinado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pendencia_baixas_id_seq; Type: SEQUENCE; Schema: uge; Owner: -
--

CREATE SEQUENCE uge.pendencia_baixas_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pendencia_baixas_id_seq; Type: SEQUENCE OWNED BY; Schema: uge; Owner: -
--

ALTER SEQUENCE uge.pendencia_baixas_id_seq OWNED BY uge.pendencia_baixas.id;


--
-- Name: processos; Type: TABLE; Schema: uge; Owner: -
--

CREATE TABLE uge.processos (
    id integer NOT NULL,
    numero integer,
    processo_sei text,
    processo_siafem text,
    licitacao text,
    solicitante text,
    objeto text,
    classe text,
    ptres text,
    nd text,
    fonte text,
    ne text,
    valor_empenhado numeric(14,2),
    entrega_empenhada date,
    ok_empenho text,
    entrega_prorrogada date,
    ok_prorrog text,
    valor_liquidado numeric(14,2),
    observacoes text,
    responsavel text,
    status text,
    ano integer,
    carregado_em timestamp with time zone DEFAULT now(),
    pendencia text
);


--
-- Name: processos_id_seq; Type: SEQUENCE; Schema: uge; Owner: -
--

CREATE SEQUENCE uge.processos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: processos_id_seq; Type: SEQUENCE OWNED BY; Schema: uge; Owner: -
--

ALTER SEQUENCE uge.processos_id_seq OWNED BY uge.processos.id;


--
-- Name: usuarios id; Type: DEFAULT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.usuarios ALTER COLUMN id SET DEFAULT nextval('app.usuarios_id_seq'::regclass);


--
-- Name: afastamentos id; Type: DEFAULT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.afastamentos ALTER COLUMN id SET DEFAULT nextval('b1.afastamentos_id_seq'::regclass);


--
-- Name: efetivo id; Type: DEFAULT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.efetivo ALTER COLUMN id SET DEFAULT nextval('b1.efetivo_id_seq'::regclass);


--
-- Name: efetivo_snapshot_mensal id; Type: DEFAULT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.efetivo_snapshot_mensal ALTER COLUMN id SET DEFAULT nextval('b1.efetivo_snapshot_mensal_id_seq'::regclass);


--
-- Name: etl_status id; Type: DEFAULT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.etl_status ALTER COLUMN id SET DEFAULT nextval('b1.etl_status_id_seq'::regclass);


--
-- Name: ias_inspecao id; Type: DEFAULT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.ias_inspecao ALTER COLUMN id SET DEFAULT nextval('b1.ias_inspecao_id_seq'::regclass);


--
-- Name: qpo_funcoes id; Type: DEFAULT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.qpo_funcoes ALTER COLUMN id SET DEFAULT nextval('b1.qpo_funcoes_id_seq'::regclass);


--
-- Name: qpo_vagas id; Type: DEFAULT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.qpo_vagas ALTER COLUMN id SET DEFAULT nextval('b1.qpo_vagas_id_seq'::regclass);


--
-- Name: restricoes id; Type: DEFAULT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.restricoes ALTER COLUMN id SET DEFAULT nextval('b1.restricoes_id_seq'::regclass);


--
-- Name: taf_resultados_raw id; Type: DEFAULT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.taf_resultados_raw ALTER COLUMN id SET DEFAULT nextval('b1.taf_resultados_raw_id_seq'::regclass);


--
-- Name: auditoria_cobom id; Type: DEFAULT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.auditoria_cobom ALTER COLUMN id SET DEFAULT nextval('b3.auditoria_cobom_id_seq'::regclass);


--
-- Name: eap_os id; Type: DEFAULT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.eap_os ALTER COLUMN id SET DEFAULT nextval('b3.eap_os_id_seq'::regclass);


--
-- Name: eap_turma id; Type: DEFAULT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.eap_turma ALTER COLUMN id SET DEFAULT nextval('b3.eap_turma_id_seq'::regclass);


--
-- Name: mapa_forca_estacao id; Type: DEFAULT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.mapa_forca_estacao ALTER COLUMN id SET DEFAULT nextval('b3.mapa_forca_estacao_id_seq'::regclass);


--
-- Name: mapa_forca_linha id; Type: DEFAULT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.mapa_forca_linha ALTER COLUMN id SET DEFAULT nextval('b3.mapa_forca_linha_id_seq'::regclass);


--
-- Name: mapa_forca_snapshot_raw id; Type: DEFAULT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.mapa_forca_snapshot_raw ALTER COLUMN id SET DEFAULT nextval('b3.mapa_forca_snapshot_raw_id_seq'::regclass);


--
-- Name: nivel_op_captura id; Type: DEFAULT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.nivel_op_captura ALTER COLUMN id SET DEFAULT nextval('b3.nivel_op_captura_id_seq'::regclass);


--
-- Name: nivel_op_integrante id; Type: DEFAULT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.nivel_op_integrante ALTER COLUMN id SET DEFAULT nextval('b3.nivel_op_integrante_id_seq'::regclass);


--
-- Name: nivel_op_viatura id; Type: DEFAULT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.nivel_op_viatura ALTER COLUMN id SET DEFAULT nextval('b3.nivel_op_viatura_id_seq'::regclass);


--
-- Name: viaturas id; Type: DEFAULT; Schema: b4; Owner: -
--

ALTER TABLE ONLY b4.viaturas ALTER COLUMN id SET DEFAULT nextval('b4.viaturas_id_seq'::regclass);


--
-- Name: viaturas_sync_siopm id; Type: DEFAULT; Schema: b4; Owner: -
--

ALTER TABLE ONLY b4.viaturas_sync_siopm ALTER COLUMN id SET DEFAULT nextval('b4.viaturas_sync_siopm_id_seq'::regclass);


--
-- Name: elogios id; Type: DEFAULT; Schema: b5; Owner: -
--

ALTER TABLE ONLY b5.elogios ALTER COLUMN id SET DEFAULT nextval('b5.elogios_id_seq'::regclass);


--
-- Name: contatos_autorizados id; Type: DEFAULT; Schema: bia; Owner: -
--

ALTER TABLE ONLY bia.contatos_autorizados ALTER COLUMN id SET DEFAULT nextval('bia.contatos_autorizados_id_seq'::regclass);


--
-- Name: processos id; Type: DEFAULT; Schema: sjd; Owner: -
--

ALTER TABLE ONLY sjd.processos ALTER COLUMN id SET DEFAULT nextval('sjd.processos_id_seq'::regclass);


--
-- Name: pendencia_baixas id; Type: DEFAULT; Schema: uge; Owner: -
--

ALTER TABLE ONLY uge.pendencia_baixas ALTER COLUMN id SET DEFAULT nextval('uge.pendencia_baixas_id_seq'::regclass);


--
-- Name: processos id; Type: DEFAULT; Schema: uge; Owner: -
--

ALTER TABLE ONLY uge.processos ALTER COLUMN id SET DEFAULT nextval('uge.processos_id_seq'::regclass);


--
-- Name: usuarios usuarios_matricula_key; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.usuarios
    ADD CONSTRAINT usuarios_matricula_key UNIQUE (matricula);


--
-- Name: usuarios usuarios_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.usuarios
    ADD CONSTRAINT usuarios_pkey PRIMARY KEY (id);


--
-- Name: afastamentos afastamentos_pkey; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.afastamentos
    ADD CONSTRAINT afastamentos_pkey PRIMARY KEY (id);


--
-- Name: controle_coleta controle_coleta_pkey; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.controle_coleta
    ADD CONSTRAINT controle_coleta_pkey PRIMARY KEY (processo);


--
-- Name: efetivo efetivo_pkey; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.efetivo
    ADD CONSTRAINT efetivo_pkey PRIMARY KEY (id);


--
-- Name: efetivo_quantitativo_diario efetivo_quantitativo_diario_pkey; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.efetivo_quantitativo_diario
    ADD CONSTRAINT efetivo_quantitativo_diario_pkey PRIMARY KEY (data_referencia, lotacao, posto_grad);


--
-- Name: efetivo_snapshot_mensal efetivo_snapshot_mensal_data_referencia_re_key; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.efetivo_snapshot_mensal
    ADD CONSTRAINT efetivo_snapshot_mensal_data_referencia_re_key UNIQUE (data_referencia, re);


--
-- Name: efetivo_snapshot_mensal efetivo_snapshot_mensal_pkey; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.efetivo_snapshot_mensal
    ADD CONSTRAINT efetivo_snapshot_mensal_pkey PRIMARY KEY (id);


--
-- Name: etl_status etl_status_pkey; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.etl_status
    ADD CONSTRAINT etl_status_pkey PRIMARY KEY (id);


--
-- Name: ias_inspecao ias_inspecao_pkey; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.ias_inspecao
    ADD CONSTRAINT ias_inspecao_pkey PRIMARY KEY (id);


--
-- Name: promocoes promocoes_pkey; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.promocoes
    ADD CONSTRAINT promocoes_pkey PRIMARY KEY (re, codigo_posto, data_promocao);


--
-- Name: qpo_funcoes qpo_funcoes_pkey; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.qpo_funcoes
    ADD CONSTRAINT qpo_funcoes_pkey PRIMARY KEY (id);


--
-- Name: qpo_vagas qpo_vagas_lotacao_quadro_posto_grad_key; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.qpo_vagas
    ADD CONSTRAINT qpo_vagas_lotacao_quadro_posto_grad_key UNIQUE (lotacao, quadro, posto_grad);


--
-- Name: qpo_vagas qpo_vagas_pkey; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.qpo_vagas
    ADD CONSTRAINT qpo_vagas_pkey PRIMARY KEY (id);


--
-- Name: restricoes restricoes_pkey; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.restricoes
    ADD CONSTRAINT restricoes_pkey PRIMARY KEY (id);


--
-- Name: taf_resultados_raw taf_resultados_raw_pkey; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.taf_resultados_raw
    ADD CONSTRAINT taf_resultados_raw_pkey PRIMARY KEY (id);


--
-- Name: afastamentos uq_afastamento; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.afastamentos
    ADD CONSTRAINT uq_afastamento UNIQUE (re, motivo, data_inicio);


--
-- Name: efetivo uq_efetivo_re; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.efetivo
    ADD CONSTRAINT uq_efetivo_re UNIQUE (re);


--
-- Name: etl_status uq_etl_status_dominio; Type: CONSTRAINT; Schema: b1; Owner: -
--

ALTER TABLE ONLY b1.etl_status
    ADD CONSTRAINT uq_etl_status_dominio UNIQUE (dominio);


--
-- Name: auditoria_cobom auditoria_cobom_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.auditoria_cobom
    ADD CONSTRAINT auditoria_cobom_pkey PRIMARY KEY (id);


--
-- Name: eap_dispensa eap_dispensa_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.eap_dispensa
    ADD CONSTRAINT eap_dispensa_pkey PRIMARY KEY (re);


--
-- Name: eap_inscricao eap_inscricao_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.eap_inscricao
    ADD CONSTRAINT eap_inscricao_pkey PRIMARY KEY (turma_id, re);


--
-- Name: eap_modelo eap_modelo_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.eap_modelo
    ADD CONSTRAINT eap_modelo_pkey PRIMARY KEY (ano);


--
-- Name: eap_os eap_os_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.eap_os
    ADD CONSTRAINT eap_os_pkey PRIMARY KEY (id);


--
-- Name: eap_turma eap_turma_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.eap_turma
    ADD CONSTRAINT eap_turma_pkey PRIMARY KEY (id);


--
-- Name: mapa_forca_estacao mapa_forca_estacao_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.mapa_forca_estacao
    ADD CONSTRAINT mapa_forca_estacao_pkey PRIMARY KEY (id);


--
-- Name: mapa_forca_linha mapa_forca_linha_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.mapa_forca_linha
    ADD CONSTRAINT mapa_forca_linha_pkey PRIMARY KEY (id);


--
-- Name: mapa_forca_snapshot_raw mapa_forca_snapshot_raw_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.mapa_forca_snapshot_raw
    ADD CONSTRAINT mapa_forca_snapshot_raw_pkey PRIMARY KEY (id);


--
-- Name: nivel_op_captura nivel_op_captura_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.nivel_op_captura
    ADD CONSTRAINT nivel_op_captura_pkey PRIMARY KEY (id);


--
-- Name: nivel_op_integrante nivel_op_integrante_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.nivel_op_integrante
    ADD CONSTRAINT nivel_op_integrante_pkey PRIMARY KEY (id);


--
-- Name: nivel_op_viatura nivel_op_viatura_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.nivel_op_viatura
    ADD CONSTRAINT nivel_op_viatura_pkey PRIMARY KEY (id);


--
-- Name: ocorrencias ocorrencias_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.ocorrencias
    ADD CONSTRAINT ocorrencias_pkey PRIMARY KEY (id);


--
-- Name: tempo_resposta tempo_resposta_pkey; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.tempo_resposta
    ADD CONSTRAINT tempo_resposta_pkey PRIMARY KEY (id_sdov, viatura);


--
-- Name: mapa_forca_snapshot_raw uq_mapa_forca_snapshot_raw; Type: CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.mapa_forca_snapshot_raw
    ADD CONSTRAINT uq_mapa_forca_snapshot_raw UNIQUE (fonte_planilha_id, fonte_aba, conteudo_sha256);


--
-- Name: siopm_estacao siopm_estacao_pkey; Type: CONSTRAINT; Schema: b4; Owner: -
--

ALTER TABLE ONLY b4.siopm_estacao
    ADD CONSTRAINT siopm_estacao_pkey PRIMARY KEY (opm_cod);


--
-- Name: viaturas viaturas_pkey; Type: CONSTRAINT; Schema: b4; Owner: -
--

ALTER TABLE ONLY b4.viaturas
    ADD CONSTRAINT viaturas_pkey PRIMARY KEY (id);


--
-- Name: viaturas_sync_siopm viaturas_sync_siopm_pkey; Type: CONSTRAINT; Schema: b4; Owner: -
--

ALTER TABLE ONLY b4.viaturas_sync_siopm
    ADD CONSTRAINT viaturas_sync_siopm_pkey PRIMARY KEY (id);


--
-- Name: elogios elogios_pkey; Type: CONSTRAINT; Schema: b5; Owner: -
--

ALTER TABLE ONLY b5.elogios
    ADD CONSTRAINT elogios_pkey PRIMARY KEY (id);


--
-- Name: contatos_autorizados contatos_autorizados_pkey; Type: CONSTRAINT; Schema: bia; Owner: -
--

ALTER TABLE ONLY bia.contatos_autorizados
    ADD CONSTRAINT contatos_autorizados_pkey PRIMARY KEY (id);


--
-- Name: contatos_autorizados contatos_autorizados_telefone_key; Type: CONSTRAINT; Schema: bia; Owner: -
--

ALTER TABLE ONLY bia.contatos_autorizados
    ADD CONSTRAINT contatos_autorizados_telefone_key UNIQUE (telefone);


--
-- Name: indicadores_mensais indicadores_mensais_pkey; Type: CONSTRAINT; Schema: sjd; Owner: -
--

ALTER TABLE ONLY sjd.indicadores_mensais
    ADD CONSTRAINT indicadores_mensais_pkey PRIMARY KEY (indicador, ano, mes);


--
-- Name: processos processos_conteudo_sha256_key; Type: CONSTRAINT; Schema: sjd; Owner: -
--

ALTER TABLE ONLY sjd.processos
    ADD CONSTRAINT processos_conteudo_sha256_key UNIQUE (conteudo_sha256);


--
-- Name: processos processos_pkey; Type: CONSTRAINT; Schema: sjd; Owner: -
--

ALTER TABLE ONLY sjd.processos
    ADD CONSTRAINT processos_pkey PRIMARY KEY (id);


--
-- Name: pendencia_baixas pendencia_baixas_pkey; Type: CONSTRAINT; Schema: uge; Owner: -
--

ALTER TABLE ONLY uge.pendencia_baixas
    ADD CONSTRAINT pendencia_baixas_pkey PRIMARY KEY (id);


--
-- Name: pendencia_baixas pendencia_baixas_processo_id_usuario_id_pendencia_texto_key; Type: CONSTRAINT; Schema: uge; Owner: -
--

ALTER TABLE ONLY uge.pendencia_baixas
    ADD CONSTRAINT pendencia_baixas_processo_id_usuario_id_pendencia_texto_key UNIQUE (processo_id, usuario_id, pendencia_texto);


--
-- Name: processos processos_pkey; Type: CONSTRAINT; Schema: uge; Owner: -
--

ALTER TABLE ONLY uge.processos
    ADD CONSTRAINT processos_pkey PRIMARY KEY (id);


--
-- Name: ix_usuarios_apelido; Type: INDEX; Schema: app; Owner: -
--

CREATE INDEX ix_usuarios_apelido ON app.usuarios USING btree (apelido_assinatura);


--
-- Name: ix_afastamentos_dt_cadastro; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_afastamentos_dt_cadastro ON b1.afastamentos USING btree (dt_cadastro);


--
-- Name: ix_afastamentos_periodo; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_afastamentos_periodo ON b1.afastamentos USING btree (data_inicio, data_fim);


--
-- Name: ix_afastamentos_re; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_afastamentos_re ON b1.afastamentos USING btree (re);


--
-- Name: ix_efetivo_ativo; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_efetivo_ativo ON b1.efetivo USING btree (ativo);


--
-- Name: ix_efetivo_cod_opm_atual; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_efetivo_cod_opm_atual ON b1.efetivo USING btree (cod_opm_atual);


--
-- Name: ix_efetivo_snap_data; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_efetivo_snap_data ON b1.efetivo_snapshot_mensal USING btree (data_referencia);


--
-- Name: ix_efetivo_snap_lot; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_efetivo_snap_lot ON b1.efetivo_snapshot_mensal USING btree (data_referencia, lotacao);


--
-- Name: ix_etl_status_dominio_tempo; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_etl_status_dominio_tempo ON b1.etl_status USING btree (dominio, iniciado_em DESC);


--
-- Name: ix_ias_re; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_ias_re ON b1.ias_inspecao USING btree (re);


--
-- Name: ix_qpo_categoria; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_qpo_categoria ON b1.qpo_vagas USING btree (categoria);


--
-- Name: ix_qpo_func_categoria; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_qpo_func_categoria ON b1.qpo_funcoes USING btree (categoria);


--
-- Name: ix_qpo_func_lotacao; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_qpo_func_lotacao ON b1.qpo_funcoes USING btree (lotacao);


--
-- Name: ix_qpo_func_secao; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_qpo_func_secao ON b1.qpo_funcoes USING btree (secao);


--
-- Name: ix_qpo_lotacao; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_qpo_lotacao ON b1.qpo_vagas USING btree (lotacao);


--
-- Name: ix_qpo_posto; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_qpo_posto ON b1.qpo_vagas USING btree (posto_grad);


--
-- Name: ix_qpo_quadro; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_qpo_quadro ON b1.qpo_vagas USING btree (quadro);


--
-- Name: ix_restricoes_data_final; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_restricoes_data_final ON b1.restricoes USING btree (data_final);


--
-- Name: ix_restricoes_natural; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_restricoes_natural ON b1.restricoes USING btree (re, origem, data_inicial);


--
-- Name: ix_restricoes_observacao; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_restricoes_observacao ON b1.restricoes USING btree (observacao);


--
-- Name: ix_restricoes_re; Type: INDEX; Schema: b1; Owner: -
--

CREATE INDEX ix_restricoes_re ON b1.restricoes USING btree (re);


--
-- Name: uq_etl_status_dominio_re; Type: INDEX; Schema: b1; Owner: -
--

CREATE UNIQUE INDEX uq_etl_status_dominio_re ON b1.etl_status USING btree (dominio, re);


--
-- Name: uq_ias_re_ano_processo; Type: INDEX; Schema: b1; Owner: -
--

CREATE UNIQUE INDEX uq_ias_re_ano_processo ON b1.ias_inspecao USING btree (re, ano, numero_processo);


--
-- Name: ux_efetivo_re; Type: INDEX; Schema: b1; Owner: -
--

CREATE UNIQUE INDEX ux_efetivo_re ON b1.efetivo USING btree (re);


--
-- Name: auditoria_cobom_data_idx; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX auditoria_cobom_data_idx ON b3.auditoria_cobom USING btree (data_servico DESC);


--
-- Name: auditoria_cobom_re_idx; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX auditoria_cobom_re_idx ON b3.auditoria_cobom USING btree (re);


--
-- Name: ix_eap_inscricao_re; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_eap_inscricao_re ON b3.eap_inscricao USING btree (re);


--
-- Name: ix_mapa_forca_estacao_snapshot; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_mapa_forca_estacao_snapshot ON b3.mapa_forca_estacao USING btree (snapshot_id);


--
-- Name: ix_mapa_forca_linha_estacao; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_mapa_forca_linha_estacao ON b3.mapa_forca_linha USING btree (estacao_id);


--
-- Name: ix_mapa_forca_raw_capturado_em; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_mapa_forca_raw_capturado_em ON b3.mapa_forca_snapshot_raw USING btree (capturado_em DESC);


--
-- Name: ix_mapa_forca_raw_data_servico; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_mapa_forca_raw_data_servico ON b3.mapa_forca_snapshot_raw USING btree (data_servico);


--
-- Name: ix_mfl_bloco; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_mfl_bloco ON b3.mapa_forca_linha USING btree (bloco_nome);


--
-- Name: ix_mfl_snapshot; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_mfl_snapshot ON b3.mapa_forca_linha USING btree (snapshot_id);


--
-- Name: ix_mfl_viatura; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_mfl_viatura ON b3.mapa_forca_linha USING btree (viatura);


--
-- Name: ix_nivel_op_captura_em; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_nivel_op_captura_em ON b3.nivel_op_captura USING btree (capturado_em DESC);


--
-- Name: ix_nivel_op_integrante_re; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_nivel_op_integrante_re ON b3.nivel_op_integrante USING btree (re);


--
-- Name: ix_nivel_op_integrante_viatura; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_nivel_op_integrante_viatura ON b3.nivel_op_integrante USING btree (viatura_id);


--
-- Name: ix_nivel_op_viatura_captura; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_nivel_op_viatura_captura ON b3.nivel_op_viatura USING btree (captura_id, opm_cod);


--
-- Name: ix_ocorrencias_natcod; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_ocorrencias_natcod ON b3.ocorrencias USING btree (natcod);


--
-- Name: ix_ocorrencias_ocrdat; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_ocorrencias_ocrdat ON b3.ocorrencias USING btree (ocrdat);


--
-- Name: ix_ocorrencias_sgb; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_ocorrencias_sgb ON b3.ocorrencias USING btree (sgb);


--
-- Name: ix_ocorrencias_sgb_dat; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_ocorrencias_sgb_dat ON b3.ocorrencias USING btree (sgb, ocrdat);


--
-- Name: ix_tr_dt; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_tr_dt ON b3.tempo_resposta USING btree (dt_ocorrencia);


--
-- Name: ix_tr_municipio; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_tr_municipio ON b3.tempo_resposta USING btree (municipio);


--
-- Name: ix_tr_natureza; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_tr_natureza ON b3.tempo_resposta USING btree (natureza);


--
-- Name: ix_tr_sgb; Type: INDEX; Schema: b3; Owner: -
--

CREATE INDEX ix_tr_sgb ON b3.tempo_resposta USING btree (sgb);


--
-- Name: ix_b4_viaturas_sgb; Type: INDEX; Schema: b4; Owner: -
--

CREATE INDEX ix_b4_viaturas_sgb ON b4.viaturas USING btree (sgb);


--
-- Name: ix_b4_viaturas_status; Type: INDEX; Schema: b4; Owner: -
--

CREATE INDEX ix_b4_viaturas_status ON b4.viaturas USING btree (status);


--
-- Name: ix_b4_viaturas_tipo; Type: INDEX; Schema: b4; Owner: -
--

CREATE INDEX ix_b4_viaturas_tipo ON b4.viaturas USING btree (tipo);


--
-- Name: ix_viaturas_sync_siopm_captura; Type: INDEX; Schema: b4; Owner: -
--

CREATE INDEX ix_viaturas_sync_siopm_captura ON b4.viaturas_sync_siopm USING btree (captura_id);


--
-- Name: uq_b4_viaturas_prefixo; Type: INDEX; Schema: b4; Owner: -
--

CREATE UNIQUE INDEX uq_b4_viaturas_prefixo ON b4.viaturas USING btree (prefixo);


--
-- Name: ix_elogios_ano; Type: INDEX; Schema: b5; Owner: -
--

CREATE INDEX ix_elogios_ano ON b5.elogios USING btree (ano);


--
-- Name: ix_elogios_re; Type: INDEX; Schema: b5; Owner: -
--

CREATE INDEX ix_elogios_re ON b5.elogios USING btree (re);


--
-- Name: ix_elogios_sgb; Type: INDEX; Schema: b5; Owner: -
--

CREATE INDEX ix_elogios_sgb ON b5.elogios USING btree (sgb);


--
-- Name: ix_elogios_tipo; Type: INDEX; Schema: b5; Owner: -
--

CREATE INDEX ix_elogios_tipo ON b5.elogios USING btree (tipo);


--
-- Name: ix_sjd_processos_data; Type: INDEX; Schema: sjd; Owner: -
--

CREATE INDEX ix_sjd_processos_data ON sjd.processos USING btree (data_abertura);


--
-- Name: ix_sjd_processos_tipo; Type: INDEX; Schema: sjd; Owner: -
--

CREATE INDEX ix_sjd_processos_tipo ON sjd.processos USING btree (tipo);


--
-- Name: ix_sjd_processos_unidade; Type: INDEX; Schema: sjd; Owner: -
--

CREATE INDEX ix_sjd_processos_unidade ON sjd.processos USING btree (unidade);


--
-- Name: ix_baixas_processo; Type: INDEX; Schema: uge; Owner: -
--

CREATE INDEX ix_baixas_processo ON uge.pendencia_baixas USING btree (processo_id);


--
-- Name: ix_baixas_usuario; Type: INDEX; Schema: uge; Owner: -
--

CREATE INDEX ix_baixas_usuario ON uge.pendencia_baixas USING btree (usuario_id);


--
-- Name: ix_uge_ano; Type: INDEX; Schema: uge; Owner: -
--

CREATE INDEX ix_uge_ano ON uge.processos USING btree (ano);


--
-- Name: ix_uge_entrega; Type: INDEX; Schema: uge; Owner: -
--

CREATE INDEX ix_uge_entrega ON uge.processos USING btree (entrega_empenhada);


--
-- Name: ix_uge_licitacao; Type: INDEX; Schema: uge; Owner: -
--

CREATE INDEX ix_uge_licitacao ON uge.processos USING btree (licitacao);


--
-- Name: ix_uge_responsavel; Type: INDEX; Schema: uge; Owner: -
--

CREATE INDEX ix_uge_responsavel ON uge.processos USING btree (responsavel);


--
-- Name: ix_uge_solicitante; Type: INDEX; Schema: uge; Owner: -
--

CREATE INDEX ix_uge_solicitante ON uge.processos USING btree (solicitante);


--
-- Name: ix_uge_status; Type: INDEX; Schema: uge; Owner: -
--

CREATE INDEX ix_uge_status ON uge.processos USING btree (status);


--
-- Name: viaturas tg_viaturas_trava_siopm; Type: TRIGGER; Schema: b4; Owner: -
--

CREATE TRIGGER tg_viaturas_trava_siopm BEFORE UPDATE ON b4.viaturas FOR EACH ROW EXECUTE FUNCTION b4.fn_viaturas_trava_siopm();


--
-- Name: auditoria_cobom auditoria_cobom_atualizado_por_fkey; Type: FK CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.auditoria_cobom
    ADD CONSTRAINT auditoria_cobom_atualizado_por_fkey FOREIGN KEY (atualizado_por) REFERENCES app.usuarios(id);


--
-- Name: auditoria_cobom auditoria_cobom_criado_por_fkey; Type: FK CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.auditoria_cobom
    ADD CONSTRAINT auditoria_cobom_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES app.usuarios(id);


--
-- Name: eap_inscricao eap_inscricao_turma_id_fkey; Type: FK CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.eap_inscricao
    ADD CONSTRAINT eap_inscricao_turma_id_fkey FOREIGN KEY (turma_id) REFERENCES b3.eap_turma(id) ON DELETE CASCADE;


--
-- Name: mapa_forca_estacao mapa_forca_estacao_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.mapa_forca_estacao
    ADD CONSTRAINT mapa_forca_estacao_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES b3.mapa_forca_snapshot_raw(id) ON DELETE CASCADE;


--
-- Name: mapa_forca_linha mapa_forca_linha_estacao_id_fkey; Type: FK CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.mapa_forca_linha
    ADD CONSTRAINT mapa_forca_linha_estacao_id_fkey FOREIGN KEY (estacao_id) REFERENCES b3.mapa_forca_estacao(id) ON DELETE SET NULL;


--
-- Name: mapa_forca_linha mapa_forca_linha_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.mapa_forca_linha
    ADD CONSTRAINT mapa_forca_linha_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES b3.mapa_forca_snapshot_raw(id) ON DELETE CASCADE;


--
-- Name: nivel_op_integrante nivel_op_integrante_viatura_id_fkey; Type: FK CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.nivel_op_integrante
    ADD CONSTRAINT nivel_op_integrante_viatura_id_fkey FOREIGN KEY (viatura_id) REFERENCES b3.nivel_op_viatura(id) ON DELETE CASCADE;


--
-- Name: nivel_op_viatura nivel_op_viatura_captura_id_fkey; Type: FK CONSTRAINT; Schema: b3; Owner: -
--

ALTER TABLE ONLY b3.nivel_op_viatura
    ADD CONSTRAINT nivel_op_viatura_captura_id_fkey FOREIGN KEY (captura_id) REFERENCES b3.nivel_op_captura(id) ON DELETE CASCADE;


--
-- Name: pendencia_baixas pendencia_baixas_processo_id_fkey; Type: FK CONSTRAINT; Schema: uge; Owner: -
--

ALTER TABLE ONLY uge.pendencia_baixas
    ADD CONSTRAINT pendencia_baixas_processo_id_fkey FOREIGN KEY (processo_id) REFERENCES uge.processos(id) ON DELETE CASCADE;


--
-- Name: pendencia_baixas pendencia_baixas_usuario_id_fkey; Type: FK CONSTRAINT; Schema: uge; Owner: -
--

ALTER TABLE ONLY uge.pendencia_baixas
    ADD CONSTRAINT pendencia_baixas_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES app.usuarios(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


