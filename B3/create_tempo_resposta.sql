-- ============================================================
-- B/3 — Tempo-resposta por ocorrência e viatura empenhada
-- Executar conectado ao banco 11gb como admin
-- ============================================================
-- A fonte é o export do SDOV2 ("tempo resposta completo.xlsx"), que quebra o
-- tempo-resposta em três fases encadeadas:
--
--   01  entrada da ligação  ->  geração da ocorrência   (atendimento no COBOM)
--   02  geração             ->  despacho do recurso     (decisão/empenho)
--   03  despacho            ->  chegada no local        (deslocamento)
--
-- A soma das três é o tempo-resposta que o cidadão sente: do telefone tocando
-- até o bombeiro na porta. Guardar as fases separadas, e não só o total, é o que
-- permite dizer ONDE o tempo foi perdido — sem isso um total ruim não distingue
-- COBOM lento de trânsito ruim.
--
-- GRÃO: uma linha por (ocorrência, viatura empenhada) — NÃO por ocorrência.
-- Uma ocorrência com 4 viaturas gera 4 linhas, cada uma com o próprio tempo de
-- deslocamento. Média sobre a tabela crua pondera ocorrência grande em dobro;
-- para indicador por ocorrência use vw_tempo_resposta_ocorrencia.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS b3;

CREATE TABLE IF NOT EXISTS b3.tempo_resposta (
    id_sdov              BIGINT      NOT NULL,   -- ID (CBPMESP SDOV2 stage)
    viatura              TEXT        NOT NULL,   -- prefixo empenhado (AB11103, UR11424...)
    dt_ocorrencia        TIMESTAMP,
    num_ocorrencia       INTEGER,                -- sequencial do dia, NÃO é único no ano
    municipio            TEXT,
    bairro               TEXT,
    natureza             TEXT,                   -- NIVEL01 do SDOV2, ex "12-Acidente de trânsito"
    sgb                  TEXT,                   -- derivado do prefixo da viatura
    t_atendimento_min    NUMERIC(10,4),          -- fase 01
    t_despacho_min       NUMERIC(10,4),          -- fase 02
    t_deslocamento_min   NUMERIC(10,4),          -- fase 03
    lote_importacao      TEXT,
    criado_em            TIMESTAMPTZ DEFAULT now(),
    atualizado_em        TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (id_sdov, viatura)
);

-- Acima: Os valores entram como vêm da fonte, inclusive negativos e absurdos.
-- Mesma decisão do ocorrencias_etl: sanear na carga esconderia da vista de quem
-- consulta um problema de qualidade que é da origem, não nosso.

CREATE INDEX IF NOT EXISTS ix_tr_dt        ON b3.tempo_resposta (dt_ocorrencia);
CREATE INDEX IF NOT EXISTS ix_tr_sgb       ON b3.tempo_resposta (sgb);
CREATE INDEX IF NOT EXISTS ix_tr_natureza  ON b3.tempo_resposta (natureza);
CREATE INDEX IF NOT EXISTS ix_tr_municipio ON b3.tempo_resposta (municipio);


-- ============================================================
-- FAIXA VÁLIDA
-- ============================================================
-- Toda view abaixo descarta fase fora de [0, 600] minutos. O limite superior de
-- 10 h é o mesmo já usado nas consultas de b3.ocorrencias.despacho_min, para que
-- os dois indicadores de despacho continuem comparáveis. O corte inferior existe
-- porque a fonte tem 7 registros com fase negativa — relógio do SDOV2 andando
-- para trás, não ocorrência atendida antes de existir.

CREATE OR REPLACE VIEW b3.vw_tempo_resposta_valido AS
SELECT *,
       t_atendimento_min + t_despacho_min + t_deslocamento_min AS t_total_min
FROM   b3.tempo_resposta
WHERE  t_atendimento_min  BETWEEN 0 AND 600
  AND  t_despacho_min     BETWEEN 0 AND 600
  AND  t_deslocamento_min BETWEEN 0 AND 600;


-- ============================================================
-- GRÃO DE OCORRÊNCIA
-- ============================================================
-- Colapsa as N viaturas de uma ocorrência em uma linha. O deslocamento adotado é
-- o da PRIMEIRA viatura a chegar, que é o instante em que a população passa a ser
-- socorrida — a segunda e a terceira viatura chegando depois não pioram o
-- atendimento, então a média delas descreveria outra coisa.

CREATE OR REPLACE VIEW b3.vw_tempo_resposta_ocorrencia AS
SELECT
    id_sdov,
    min(dt_ocorrencia)                                       AS dt_ocorrencia,
    min(num_ocorrencia)                                      AS num_ocorrencia,
    min(municipio)                                           AS municipio,
    min(bairro)                                              AS bairro,
    min(natureza)                                            AS natureza,
    min(sgb)                                                 AS sgb,
    count(*)                                                 AS viaturas_empenhadas,
    max(t_atendimento_min)                                   AS t_atendimento_min,
    max(t_despacho_min)                                      AS t_despacho_min,
    min(t_deslocamento_min)                                  AS t_deslocamento_min,
    max(t_atendimento_min) + max(t_despacho_min)
        + min(t_deslocamento_min)                            AS t_total_min
FROM   b3.vw_tempo_resposta_valido
GROUP  BY id_sdov;


-- ============================================================
-- INDICADORES
-- ============================================================

-- Série anual das três fases + total, no grão de ocorrência.
CREATE OR REPLACE VIEW b3.vw_tempo_resposta_anual AS
SELECT
    extract(year FROM dt_ocorrencia)::int                                        AS ano,
    count(*)                                                                     AS ocorrencias,
    round(avg(t_atendimento_min), 2)                                             AS atendimento_medio,
    round(avg(t_despacho_min), 2)                                                AS despacho_medio,
    round(avg(t_deslocamento_min), 2)                                            AS deslocamento_medio,
    round(avg(t_total_min), 2)                                                   AS total_medio,
    round((percentile_cont(0.5) WITHIN GROUP (ORDER BY t_total_min))::numeric, 2) AS total_mediana,
    round((percentile_cont(0.9) WITHIN GROUP (ORDER BY t_total_min))::numeric, 2) AS total_p90
FROM   b3.vw_tempo_resposta_ocorrencia
GROUP  BY 1
ORDER  BY 1;

-- Mesma leitura estratificada por SGB — responde "onde o tempo é pior".
CREATE OR REPLACE VIEW b3.vw_tempo_resposta_sgb AS
SELECT
    extract(year FROM dt_ocorrencia)::int                                        AS ano,
    sgb,
    count(*)                                                                     AS ocorrencias,
    round(avg(t_atendimento_min), 2)                                             AS atendimento_medio,
    round(avg(t_despacho_min), 2)                                                AS despacho_medio,
    round(avg(t_deslocamento_min), 2)                                            AS deslocamento_medio,
    round(avg(t_total_min), 2)                                                   AS total_medio,
    round((percentile_cont(0.5) WITHIN GROUP (ORDER BY t_total_min))::numeric, 2) AS total_mediana
FROM   b3.vw_tempo_resposta_ocorrencia
WHERE  sgb IS NOT NULL
GROUP  BY 1, 2
ORDER  BY 1, 2;

-- Onde o tempo se perde: participação de cada fase no total.
-- É o indicador acionável — mostra se atacar o COBOM, o empenho ou a frota.
CREATE OR REPLACE VIEW b3.vw_tempo_resposta_composicao AS
SELECT
    extract(year FROM dt_ocorrencia)::int                                AS ano,
    round(100.0 * sum(t_atendimento_min)  / nullif(sum(t_total_min),0), 1) AS pct_atendimento,
    round(100.0 * sum(t_despacho_min)     / nullif(sum(t_total_min),0), 1) AS pct_despacho,
    round(100.0 * sum(t_deslocamento_min) / nullif(sum(t_total_min),0), 1) AS pct_deslocamento
FROM   b3.vw_tempo_resposta_ocorrencia
GROUP  BY 1
ORDER  BY 1;

-- Percentual atendido dentro de faixas de tempo, por natureza agregada.
-- 'faixa' é o corte de serviço; 20 min é o usado no relatório do Cap.
CREATE OR REPLACE VIEW b3.vw_tempo_resposta_faixas AS
SELECT
    extract(year FROM dt_ocorrencia)::int  AS ano,
    CASE
        WHEN natureza ILIKE '%incêndio%'            THEN 'Incêndio'
        WHEN natureza ILIKE '%acidente de trânsito%' THEN 'Acidente de trânsito'
        WHEN natureza ILIKE '%sem intervenção%'      THEN 'Sem intervenção'
        ELSE 'Demais'
    END                                                                   AS grupo,
    count(*)                                                              AS ocorrencias,
    round(100.0 * count(*) FILTER (WHERE t_total_min <= 10) / count(*), 1) AS pct_ate_10min,
    round(100.0 * count(*) FILTER (WHERE t_total_min <= 20) / count(*), 1) AS pct_ate_20min,
    round(100.0 * count(*) FILTER (WHERE t_total_min <= 30) / count(*), 1) AS pct_ate_30min,
    round((percentile_cont(0.5) WITHIN GROUP (ORDER BY t_total_min))::numeric, 1) AS mediana
FROM   b3.vw_tempo_resposta_ocorrencia
GROUP  BY 1, 2
ORDER  BY 1, 2;

-- Ranking de municípios pelo deslocamento — o indicador que aponta vazio de
-- cobertura, porque deslocamento alto e persistente é distância de quartel.
CREATE OR REPLACE VIEW b3.vw_tempo_resposta_municipio AS
SELECT
    municipio,
    count(*)                                                                       AS ocorrencias,
    round(avg(t_deslocamento_min), 2)                                              AS deslocamento_medio,
    round((percentile_cont(0.5) WITHIN GROUP (ORDER BY t_deslocamento_min))::numeric, 2) AS deslocamento_mediana,
    round(avg(t_total_min), 2)                                                     AS total_medio
FROM   b3.vw_tempo_resposta_ocorrencia
WHERE  municipio IS NOT NULL
GROUP  BY municipio
HAVING count(*) >= 100
ORDER  BY deslocamento_mediana DESC;
