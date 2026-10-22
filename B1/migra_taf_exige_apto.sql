-- ============================================================
-- b1.vw_taf_situacao_atual — TAF só conta como VÁLIDO se o
-- resultado for Apto.
--
-- POR QUE
-- A versão anterior partia de b1.vw_taf_ultimo_finalizado_por_re,
-- que filtra só por status = 'Finalizado'. Um TAF finalizado com
-- resultado Inapto ou Ausente contava como VÁLIDO por um ano, igual
-- a um Apto.
--
-- REGRA
-- - VÁLIDO:  último TAF com resultado Apto há menos de 1 ano.
-- - VENCIDO: tem TAF Apto, mas o último já passou de 1 ano.
-- - SEM TAF: nunca teve TAF com resultado Apto.
-- O status não importa (decisão do Cmt em 14/10/2026): Apto em
-- "Pronto para Avaliação" conta igual a Apto "Finalizado". A
-- homologação no sistema do TAF atrasa meses, e o militar que já foi
-- aprovado no teste aparecia VENCIDO enquanto isso.
-- Inapto e Ausente não renovam a validade: quem tem um Apto anterior
-- ainda no prazo segue VÁLIDO até ele vencer; quem não tem fica
-- VENCIDO ou SEM TAF. data_realizado passa a ser a do último Apto.
--
-- A regra mora em b1.vw_taf_ultimo_apto_por_re, que o painel (via
-- vw_taf_situacao_atual) e a B.I.A. (/consulta/taf e dossiê) leem.
-- Ela não filtra efetivo ativo: o dossiê também responde por militar
-- transferido.
--
-- vw_taf_situacao_atual mantém as mesmas colunas e tipos, então
-- CREATE OR REPLACE mantém b1.vw_taf_dashboard funcionando sem recriar.
-- ============================================================

CREATE OR REPLACE VIEW b1.vw_taf_ultimo_apto_por_re AS
WITH ultimo AS (
    SELECT DISTINCT ON (re)
           re, tipo_taf, resultado, status, data_realizado
    FROM b1.taf_resultados_raw
    WHERE resultado = 'Apto'
    -- NULLS LAST: no DESC o Postgres põe nulo primeiro, e uma linha
    -- Apto sem data esconderia o Apto datado do mesmo militar.
    ORDER BY re, data_realizado DESC NULLS LAST, criado_em DESC, id DESC
)
SELECT u.*,
       (u.data_realizado + '1 year'::interval)::date AS valido_ate,
       CASE
           WHEN (u.data_realizado + '1 year'::interval) >= CURRENT_DATE THEN 'VÁLIDO'::text
           ELSE 'VENCIDO'::text
       END AS situacao_taf
FROM ultimo u;

CREATE OR REPLACE VIEW b1.vw_taf_situacao_atual AS
SELECT e.re,
       e.nome,
       a.data_realizado,
       COALESCE(a.situacao_taf, 'SEM TAF'::text) AS situacao_taf
FROM b1.efetivo e
LEFT JOIN b1.vw_taf_ultimo_apto_por_re a ON a.re = e.re
WHERE e.ativo = true;
