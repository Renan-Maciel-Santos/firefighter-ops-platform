-- ==========================================
-- MIGRAÇÃO: água e mergulhadores viram atributo da ESTAÇÃO
-- ==========================================
-- Motivo: na planilha do mapa de força as colunas "Capacidade de Água em
-- Litros" e "Mergulhadores" são células MESCLADAS verticalmente sobre todo
-- o grupo de linhas de uma estação. O get_all_values() devolve o valor só
-- na primeira linha do range, então o ETL antigo atribuía o total da
-- estação à primeira viatura do grupo (ex.: AC-11104 aparecia com 4000 L
-- que são da estação inteira, e USA-11104 idem).
--
-- Os totais agregados sempre estiveram certos; o que estava errado era a
-- atribuição por viatura. Esta migração cria o nível "estação" para que o
-- dado fique onde ele realmente existe.
-- ==========================================

BEGIN;

-- Acima: Uma linha por estação por snapshot. Água e mergulhadores moram aqui.
CREATE TABLE IF NOT EXISTS b3.mapa_forca_estacao (
    id                 bigserial PRIMARY KEY,
    snapshot_id        bigint  NOT NULL REFERENCES b3.mapa_forca_snapshot_raw(id) ON DELETE CASCADE,
    bloco_nome         text    NOT NULL,
    estacao_nome       text,
    estacao_codigo     text,
    estacao_telefone   text,
    capacidade_agua_l  integer,
    mergulhadores      integer,
    ordem              integer NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_mapa_forca_estacao_snapshot
    ON b3.mapa_forca_estacao (snapshot_id);

-- Acima: Liga cada viatura à sua estação (nulo nos snapshots antigos)
ALTER TABLE b3.mapa_forca_linha
    ADD COLUMN IF NOT EXISTS estacao_id bigint
    REFERENCES b3.mapa_forca_estacao(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_mapa_forca_linha_estacao
    ON b3.mapa_forca_linha (estacao_id);

-- Acima: capacidade_agua_l e mergulhadores continuam em mapa_forca_linha só
-- para preservar o histórico já capturado. A partir desta migração o ETL
-- grava NULL nelas e a verdade passa a ser mapa_forca_estacao.


-- ==========================================
-- VIEWS
-- ==========================================

-- Acima: Estações do último snapshot do dia (espelha vw_mapa_linhas_hoje)
CREATE OR REPLACE VIEW b3.vw_mapa_estacoes_hoje AS
SELECT u.data_ref,
       u.snapshot_id,
       e.bloco_nome,
       e.estacao_nome,
       e.estacao_codigo,
       e.estacao_telefone,
       e.capacidade_agua_l,
       e.mergulhadores,
       e.ordem
  FROM b3.vw_mapa_ultimo_snapshot_dia u
  JOIN b3.mapa_forca_estacao e ON e.snapshot_id = u.snapshot_id
 WHERE u.data_ref = ((now() AT TIME ZONE 'America/Sao_Paulo'))::date;

-- Acima: Água agora soma por estação. Sem filtro de situação: o reservatório
-- é do quartel e não deixa de existir porque a viatura está em reserva.
CREATE OR REPLACE VIEW b3.vw_agua_disponivel_hoje AS
SELECT data_ref,
       bloco_nome,
       sum(COALESCE(capacidade_agua_l, 0)) AS agua_total_litros
  FROM b3.vw_mapa_estacoes_hoje
 GROUP BY data_ref, bloco_nome
 ORDER BY bloco_nome;

CREATE OR REPLACE VIEW b3.vw_mergulhadores_hoje AS
SELECT data_ref,
       bloco_nome,
       sum(COALESCE(mergulhadores, 0)) AS total_mergulhadores
  FROM b3.vw_mapa_estacoes_hoje
 GROUP BY data_ref, bloco_nome
 ORDER BY bloco_nome;

-- Acima: Viaturas continuam vindo de mapa_forca_linha; água/mergulhadores
-- passam a vir do nível estação.
CREATE OR REPLACE VIEW b3.vw_resumo_operacional_hoje AS
SELECT l.data_ref,
       count(*) FILTER (WHERE l.situacao = 'OPERANDO')                    AS viaturas_operando,
       count(*) FILTER (WHERE l.situacao = 'RESERVA')                     AS viaturas_reserva,
       count(*) FILTER (WHERE l.situacao IN ('BAIXADA', 'BAIXADO'))       AS viaturas_baixadas,
       sum(COALESCE(l.efetivo_qtd, 0)) FILTER (WHERE l.situacao = 'OPERANDO') AS efetivo_operacional,
       (SELECT COALESCE(sum(COALESCE(e.capacidade_agua_l, 0)), 0)
          FROM b3.vw_mapa_estacoes_hoje e
         WHERE e.data_ref = l.data_ref)                                   AS agua_total_litros,
       (SELECT COALESCE(sum(COALESCE(e.mergulhadores, 0)), 0)
          FROM b3.vw_mapa_estacoes_hoje e
         WHERE e.data_ref = l.data_ref)                                   AS mergulhadores_total
  FROM b3.vw_mapa_linhas_hoje l
 GROUP BY l.data_ref;

COMMIT;
