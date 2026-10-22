-- ============================================================
-- b1.vw_efetivo_disponivel — quantitativo de efetivo operacional
-- DISPONÍVEL, descontando apenas quem está fora do serviço.
--
-- POR QUE
-- b1.vw_efetivo_operacional responde "onde a pessoa está lotada":
-- classifica por cod_opm_atual (código que não termina em zero é
-- operacional) e filtra só por `ativo = true`. Mas `ativo` não quer
-- dizer disponível: ele é derivado em B1/efetivo.py e significa apenas
-- "apareceu na última captura do SGP". Quem está em LSV, em licença
-- junto a organização civil ou candidato a cargo eletivo continua
-- aparecendo na relação e entra na conta como se estivesse servindo.
--
-- Esta view NÃO substitui aquela. A antiga responde quadro e lotação e
-- é o que cruza com o QPO; esta responde quantos efetivamente contam
-- como disponíveis.
--
-- REGRAS DE NEGÓCIO (definidas com o Cmt em 09/09/2026)
-- - Férias e licença-prêmio NÃO reduzem o disponível. São ausências
--   rotativas e previstas: o militar segue pertencendo ao efetivo, e o
--   quantitativo que interessa ao Comando é o da tropa, não o do dia.
--   Por isso esta view não olha b1.v_afastamentos_dedup e não depende
--   de CURRENT_DATE — o número não muda porque alguém saiu de férias.
-- - Sai da conta apenas quem está fora do serviço por situação:
--   qualquer `situacao` diferente de 'EFETIVO' (LSV, candidato a cargo
--   eletivo, licença para atividade em organização civil). São
--   afastamentos longos, sem data de volta previsível, e não passam
--   pela tabela de afastamentos. Ficam em coluna própria, para o
--   Comando ver quantos são e não só o líquido.
--
-- RESSALVA: o override da SAT (Sub/Sgt em cod_opm 990119200 contam como
-- operacionais, decisão do comando) vive no endpoint
-- /pessoal/operacional, em Python, não na view. Esta view segue a mesma
-- regra da vw_efetivo_operacional e portanto TAMBÉM não o aplica — as
-- duas continuam comparáveis entre si.
-- ============================================================

-- DROP antes de criar: CREATE OR REPLACE nao consegue remover coluna, e
-- assim a migracao pode ser reexecutada depois de mudar o formato.
DROP VIEW IF EXISTS b1.vw_efetivo_disponivel;

CREATE VIEW b1.vw_efetivo_disponivel AS
WITH base AS (
    SELECT
        CASE
            WHEN left(e.cod_opm_atual::text, 6) IN ('990110','990119') THEN 'EM + COBOM'
            WHEN left(e.cod_opm_atual::text, 6) = '990111' THEN '1°Sgb'
            WHEN left(e.cod_opm_atual::text, 6) = '990112' THEN '2°Sgb'
            WHEN left(e.cod_opm_atual::text, 6) = '990113' THEN '3°Sgb'
            WHEN left(e.cod_opm_atual::text, 6) = '990114' THEN '4°Sgb'
            ELSE 'Outros'
        END AS lotacao,
        CASE
            WHEN left(e.cod_opm_atual::text, 6) IN ('990110','990119') THEN 1
            WHEN left(e.cod_opm_atual::text, 6) = '990111' THEN 2
            WHEN left(e.cod_opm_atual::text, 6) = '990112' THEN 3
            WHEN left(e.cod_opm_atual::text, 6) = '990113' THEN 4
            WHEN left(e.cod_opm_atual::text, 6) = '990114' THEN 5
            ELSE 99
        END AS ord_lotacao,
        -- Mesma regra da vw_efetivo_operacional: cod que não termina em 0.
        (e.cod_opm_atual::text NOT LIKE '%0') AS operacional,
        COALESCE(e.situacao, '') <> 'EFETIVO' AS fora_do_servico
      FROM b1.efetivo e
     WHERE e.ativo = true
)
SELECT
    COALESCE(lotacao, 'TOTAL GERAL') AS lotacao,
    count(*) FILTER (WHERE operacional)                            AS operacional,
    count(*) FILTER (WHERE operacional AND fora_do_servico)        AS fora_do_servico,
    count(*) FILTER (WHERE operacional AND NOT fora_do_servico)    AS disponivel,
    round(100.0 * count(*) FILTER (WHERE operacional AND NOT fora_do_servico)
          / NULLIF(count(*) FILTER (WHERE operacional), 0), 1)     AS perc_disponivel
  FROM base
 GROUP BY GROUPING SETS ((lotacao, ord_lotacao), ())
 -- GROUPING() distingue a linha do total das de detalhe. Sem isso
 -- min(ord_lotacao) devolve 1 no agregado e o TOTAL GERAL sobe para o meio.
 ORDER BY GROUPING(lotacao), ord_lotacao;

COMMENT ON VIEW b1.vw_efetivo_disponivel IS
    'Quantitativo de efetivo operacional disponível: desconta quem está fora '
    'do serviço por situação (LSV, candidato, licença em org. civil). Férias e '
    'licença-prêmio NÃO descontam. Complementa vw_efetivo_operacional, que '
    'responde lotação. Não aplica o override da SAT.';
