-- ============================================================
-- b1.vw_antiguidade — ordem de antiguidade do efetivo ativo,
-- para apontar o encarregado (o mais antigo) de cada viatura no
-- relatório do SDO.
--
-- FONTE
-- b1.promocoes, alimentada pelo histórico de promoções do SGP (um RE
-- por vez; coletor não incluído nesta cópia). Aqui só a view.
--
-- REGRA
-- 1. Posto/graduação: menor nível do SGP é mais alto (CB 16,
--    SD 1C 17, SD 2C 18). O nível vem da última promoção.
-- 2. Mesmo posto: mais antigo é quem foi promovido a ele primeiro.
-- 3. Empate na data: vale a promoção ao posto anterior, depois a
--    data de admissão, depois o RE (menor RE entrou antes).
-- Os desempates 3 são uma aproximação: confirmar com o Cmt se a
-- regra da corporação usa a classificação no curso/concurso.
--
-- ordem_geral: 1 = mais antigo do GB. Para a viatura, basta pegar
-- o menor ordem_geral entre os REs da guarnição.
-- ============================================================

CREATE OR REPLACE VIEW b1.vw_antiguidade AS
WITH hist AS (
    SELECT p.*,
           row_number() OVER (PARTITION BY p.re ORDER BY p.data_promocao DESC, p.nivel ASC) AS n
    FROM b1.promocoes p
)
SELECT
    e.re,
    e.nome,
    e.posto_grad,
    atual.posto          AS posto_sgp,
    atual.nivel,
    atual.data_promocao  AS data_promocao_atual,
    anterior.data_promocao AS data_promocao_anterior,
    e.data_admissao,
    row_number() OVER (
        ORDER BY atual.nivel ASC NULLS LAST,
                 atual.data_promocao ASC NULLS LAST,
                 anterior.data_promocao ASC NULLS LAST,
                 e.data_admissao ASC NULLS LAST,
                 e.re ASC
    ) AS ordem_geral
FROM b1.efetivo e
LEFT JOIN hist atual    ON atual.re = e.re    AND atual.n = 1
LEFT JOIN hist anterior ON anterior.re = e.re AND anterior.n = 2
WHERE e.ativo;
