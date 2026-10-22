-- ==========================================================================
-- b3.ocorrencias — todas as ocorrências do 11º GB (COBOM), 2021 em diante
-- ==========================================================================
-- Fonte: export do COBOM em .xls (6 abas paginadas pelo limite de 65.536
-- linhas do formato legado). 382.977 linhas no arquivo, das quais carregamos
-- as 131.232 com STATUSID = 5.
--
-- Por que só STATUSID = 5: as linhas com STATUSID = 0 (251.696) são registros
-- sem preenchimento — sem natureza, sem endereço, sem comandante, sem
-- finalização. São casca, não ocorrência. Existem ainda 40 linhas em estados
-- 1, 2 e 3 (provavelmente em andamento) e 9 sem status.
--
-- Os nomes originais das colunas do export vêm anotados em cada campo, porque
-- eles não são autoexplicativos e é por eles que se confere contra a planilha.
-- ==========================================================================

CREATE SCHEMA IF NOT EXISTS b3;

CREATE TABLE IF NOT EXISTS b3.ocorrencias (
    -- Acima: ID do export é único (verificado: 131.232 ids, zero duplicados)
    id                  bigint      PRIMARY KEY,                  -- ID
    ocrnum              integer,                                  -- OCRNUM
    ocrdat              date        NOT NULL,                     -- OCRDAT
    statusid            smallint,                                 -- STATUSID (5 = finalizada)
    cadcod              smallint,                                 -- CADCOD
    situacaoid          smallint,                                 -- SITUACAOID
    atendimentotipoid   smallint,                                 -- ATENDIMENTOTIPOID
    natcod              text,                                     -- NATCOD (natureza, ex: J09)

    -- ---------------------------------------------------------------- tempos
    -- Acima: dt_chamada -> dt_geracao é o intervalo de despacho. Mediana medida
    -- de 3,0 min e p90 de 5,5 min. NÃO existe carimbo de chegada no local no
    -- export, então tempo até a chegada não é calculável a partir desta fonte.
    dt_chamada          timestamp,                                -- OcrChmDat
    dt_geracao          timestamp,                                -- OCRGREDAT
    dt_finalizacao      timestamp,                                -- DATAFINALIZACAO
    dt_homologacao      timestamp,                                -- DATAHOMOLOGACAO

    -- Acima: gravado na carga porque a conta é sempre a mesma e indexá-la
    -- barateia qualquer agregação por tempo. Pode ser negativo ou absurdo:
    -- a fonte tem lixo (mínimo negativo, máximo de 143 milhões de minutos).
    -- Filtrar é responsabilidade de quem consulta — ver vw_ocorrencias_mensal.
    despacho_min        numeric(12,2),

    -- ------------------------------------------------------------- estrutura
    sgb                 text,                                     -- SGB (1.SGB … 4.SGB)
    gb                  text,                                     -- GB
    comando             text,                                     -- COMANDO
    pb                  text,                                     -- PB
    opm_fato            bigint,                                   -- OPMFATO
    opm_atendimento     bigint,                                   -- OPMATENDIMENTO

    -- ------------------------------------------------- endereço do acionamento
    logradouro_inicial  text,                                     -- LOGRADOUROINICIAL
    numero_inicial      text,                                     -- NUMEROINICIAL
    complemento_inicial text,                                     -- COMPLEMENTOINICIAL
    bairro_inicial      text,                                     -- BAIRROINICIAL
    referencia_inicial  text,                                     -- REFERENCIAINICIAL
    municipio_inicial   integer,                                  -- MUNICIPIOIDINICIAL (código IBGE)
    endereco_inicial    text,                                     -- ENDERECOINICIAL

    -- ------------------------------------------------------ endereço apurado
    logradouro_final    text,                                     -- LOGRADOUROFINAL
    numero_final        text,                                     -- NUMEROFINAL
    complemento_final   text,                                     -- COMPLEMENTOFINAL
    bairro_final        text,                                     -- BAIRROFINAL
    municipio_final     integer,                                  -- MUNICIPIOIDFINAL
    cep_final           text,                                     -- CEPFINAL
    endereco            text,                                     -- ENDERECO

    -- ------------------------------------------------------------ geolocalização
    -- Acima: o export traz "POINT (lon lat) | id". Guardamos o texto original e
    -- também lon/lat extraídos, que é o que serve para mapa e cálculo de distância.
    localizacao_inicial text,                                     -- LOCALIZACAOINICIAL
    localizacao_final   text,                                     -- LOCALIZACAOFINAL
    lon_inicial         numeric(11,7),
    lat_inicial         numeric(11,7),
    lon_final           numeric(11,7),
    lat_final           numeric(11,7),

    -- ------------------------------------------------------------------ texto
    dados_complementares text,                                    -- DADOSCOMPLEMENTARES
    historico            text,                                    -- HISTORICO
    motivo_devolucao     text,                                    -- MOTIVODEVOLUCAO

    -- ------------------------------------------------------------------ pessoas
    -- Acima: CPF de quem comandou e de quem homologou. Dado pessoal — mesmo
    -- cuidado do resto da plataforma (que já guarda RE e restrição médica).
    comandante_cpf       text,                                    -- COMANDANTECPF
    homologador_cpf      text,                                    -- HOMOLOGADORCPF

    possui_guia          smallint,                                -- POSSUIAGUIA
    ocr_rst_cod          smallint,                                -- OcrRstCod

    lote_importacao      text,
    criado_em            timestamptz NOT NULL DEFAULT now(),
    atualizado_em        timestamptz
);

-- Acima: ocrdat sustenta toda agregação por mês/ano, que é o uso principal
CREATE INDEX IF NOT EXISTS ix_ocorrencias_ocrdat  ON b3.ocorrencias (ocrdat);
CREATE INDEX IF NOT EXISTS ix_ocorrencias_natcod  ON b3.ocorrencias (natcod);
CREATE INDEX IF NOT EXISTS ix_ocorrencias_sgb     ON b3.ocorrencias (sgb);
CREATE INDEX IF NOT EXISTS ix_ocorrencias_sgb_dat ON b3.ocorrencias (sgb, ocrdat);

-- ==========================================================================
-- VIEW: quantitativo por mês/ano e tempo de despacho
-- ==========================================================================
-- Duas decisões que mudam o resultado, e por isso ficam escritas:
--
-- 1. A estatística de tempo usa MEDIANA e p90, não média. A fonte tem valores
--    impossíveis (negativos e até 143 milhões de minutos); a média fica em
--    16.364 min contra mediana de 3,0 min. Média aqui é número inventado.
--
-- 2. Só entram no cálculo de tempo os despachos entre 0 e 120 minutos. Fora
--    dessa janela é erro de registro, não desempenho. A contagem de ocorrências
--    NÃO é filtrada — toda ocorrência conta, mesmo sem tempo aproveitável.
-- ==========================================================================

CREATE OR REPLACE VIEW b3.vw_ocorrencias_mensal AS
SELECT
    date_trunc('month', ocrdat)::date            AS mes,
    extract(year  FROM ocrdat)::int              AS ano,
    extract(month FROM ocrdat)::int              AS mes_num,
    sgb,
    count(*)                                     AS ocorrencias,

    count(*) FILTER (WHERE despacho_min BETWEEN 0 AND 120)  AS com_tempo_valido,

    round(percentile_cont(0.5) WITHIN GROUP (
        ORDER BY despacho_min) FILTER (WHERE despacho_min BETWEEN 0 AND 120)::numeric, 1)
                                                 AS despacho_mediana_min,
    round(percentile_cont(0.9) WITHIN GROUP (
        ORDER BY despacho_min) FILTER (WHERE despacho_min BETWEEN 0 AND 120)::numeric, 1)
                                                 AS despacho_p90_min
FROM b3.ocorrencias
GROUP BY 1, 2, 3, 4;

COMMENT ON VIEW b3.vw_ocorrencias_mensal IS
'Ocorrências por mês e SGB, com tempo de despacho (chamada -> geração) em mediana e p90. Não existe carimbo de chegada no local na fonte, então tempo até a chegada não é calculável.';
