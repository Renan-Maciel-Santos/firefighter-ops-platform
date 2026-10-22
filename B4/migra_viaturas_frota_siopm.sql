-- ==========================================
-- MIGRAÇÃO: A FROTA DA MOTOMEC PASSA A SER A DO SIOPM
-- ==========================================
-- Decisão do usuário em 22/10/2026: o SIOPM fica no lugar da planilha da
-- Motomec. A aba Motomec, os filtros e as tools de frota da B.I.A. leem
-- b4.vw_viaturas_situacao; ela passa a mostrar só as viaturas que o SIOPM
-- mostrou na última sincronização (B4/viaturas_siopm.py).
--
-- As viaturas que o SIOPM não mostra (TP, VT, MO, UT, carretas CT...) NÃO
-- são apagadas: continuam em b4.viaturas e ficam em b4.vw_viaturas_fora_siopm
-- até haver um jeito de relacioná-las.
--
-- "Última sincronização", e não "vistas nos últimos N dias": se a captura
-- parar, a aba fica com a última frota conhecida em vez de esvaziar (o
-- watchdog acusa o atraso por b4_viaturas_siopm).
--
-- Idempotente: pode rodar de novo sem efeito colateral.
-- ==========================================

BEGIN;

-- Acima: Mesmas colunas e ordem de antes (CREATE OR REPLACE exige)
CREATE OR REPLACE VIEW b4.vw_viaturas_situacao AS
SELECT prefixo,
       sgb,
       pb_bb,
       nome_estacao,
       municipio,
       tipo,
       fabricante,
       modelo,
       ano_fabricacao,
       EXTRACT(year FROM CURRENT_DATE)::integer - ano_fabricacao AS idade_anos,
       status,
       proprietario,
       placa,
       patrimonio_estado,
       obs,
       atualizado_em
  FROM b4.viaturas
 WHERE siopm_visto_em >= (SELECT max(siopm_visto_em) - interval '1 hour' FROM b4.viaturas)
 ORDER BY sgb, tipo, prefixo;

-- Acima: As que ficaram de fora, com a última vez que o SIOPM as viu (NULL = nunca)
CREATE OR REPLACE VIEW b4.vw_viaturas_fora_siopm AS
SELECT prefixo, tipo, sgb, nome_estacao, status, proprietario, placa,
       siopm_visto_em, atualizado_em
  FROM b4.viaturas
 WHERE siopm_visto_em IS NULL
    OR siopm_visto_em < (SELECT max(siopm_visto_em) - interval '1 hour' FROM b4.viaturas)
 ORDER BY tipo, prefixo;

COMMIT;
