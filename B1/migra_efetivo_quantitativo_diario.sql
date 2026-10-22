-- ==========================================
-- MIGRAÇÃO: QUANTITATIVO DIÁRIO DO EFETIVO EXISTENTE
-- ==========================================
-- b1.efetivo_snapshot_mensal guarda o efetivo militar por militar, um dia por
-- linha; a contagem nunca ficava gravada em lugar nenhum. Esta tabela guarda
-- o número: quantos militares ativos havia em cada lotação (SGB/EM) e posto,
-- em cada dia. B1/efetivo.py grava o dia corrente a cada carga do SGP.
--
-- Só o EXISTENTE (cadastro do SGP). Disponível e escalado ficam de fora por
-- decisão do usuário (22/10/2026).
--
-- O preenchimento inicial sai do snapshot: 37 dias entre 14/07 e 22/10/2026.
-- Os dias em que a captura não rodou não têm fotografia e não há como
-- reconstruí-los.
--
-- Idempotente: pode rodar de novo sem efeito colateral.
-- ==========================================

BEGIN;

CREATE TABLE IF NOT EXISTS b1.efetivo_quantitativo_diario (
    data_referencia date    NOT NULL,
    -- Acima: Lotação como em vw_efetivo_classificado: EM, 1°Sgb, 2°Sgb, 3°Sgb, 4°Sgb
    lotacao         text    NOT NULL,
    posto_grad      text    NOT NULL,
    quantidade      integer NOT NULL,
    gravado_em      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (data_referencia, lotacao, posto_grad)
);

INSERT INTO b1.efetivo_quantitativo_diario (data_referencia, lotacao, posto_grad, quantidade)
SELECT data_referencia,
       COALESCE(lotacao, 'SEM LOTAÇÃO'),
       COALESCE(posto_grad, 'SEM POSTO'),
       count(*)
  FROM b1.efetivo_snapshot_mensal
 GROUP BY 1, 2, 3
ON CONFLICT (data_referencia, lotacao, posto_grad) DO UPDATE SET
    quantidade = EXCLUDED.quantidade,
    gravado_em = now();

-- Acima: Total por lotação e dia, que é o que o painel costuma querer
CREATE OR REPLACE VIEW b1.vw_efetivo_quantitativo_lotacao AS
SELECT data_referencia, lotacao, sum(quantidade)::integer AS quantidade
  FROM b1.efetivo_quantitativo_diario
 GROUP BY data_referencia, lotacao;

COMMIT;
