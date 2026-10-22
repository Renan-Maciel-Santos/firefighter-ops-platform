-- ============================================================
-- B/3 — Auditoria de qualidade do atendimento 193 (COBOM)
-- Executar conectado ao banco 11gb como admin
-- ============================================================
-- Substitui o par que a B/3 mantinha à mão no share:
--   * "Controle_de_Monitorias_QUALIDADE" (xlsx, aba TURNO 193): uma linha por
--     áudio, S/N em 14 colunas e a nota por fórmula;
--   * "FICHA DE AVALIAÇÃO - <militar>" (docx): o mesmo questionário, um por
--     militar, com os áudios, o parecer e os campos de providências.
--
-- GRÃO: uma linha por ficha, como no Word. Os áudios monitorados vão em
-- `audios` (lista), e o questionário é respondido uma vez para o conjunto.
--
-- O questionário em si (texto, peso, se é grave) NÃO mora aqui: está em
-- webapp/routers/auditoria_cobom.py. `respostas` guarda só a chave do item,
-- se ficou conforme e a observação da inconformidade. Mudar o texto de uma
-- pergunta não exige migração; tirar um item não apaga o que já foi respondido.
--
-- `nota` é gravada já calculada (pela regra da planilha) para que a lista e os
-- totais do mês não dependam de recalcular o JSON — e para que uma mudança de
-- peso no futuro não reescreva a nota de fichas antigas.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS b3;

CREATE TABLE IF NOT EXISTS b3.auditoria_cobom (
    id                  BIGSERIAL   PRIMARY KEY,

    -- Avaliado. Posto e nome são cópia do b1.efetivo no momento da ficha:
    -- promoção ou transferência depois não muda o que foi assinado.
    re                  INTEGER     NOT NULL,
    posto_grad          TEXT        NOT NULL,
    nome                TEXT        NOT NULL,

    informacao_num      TEXT,                   -- "INFORMAÇÃO Nº ..." do cabeçalho
    data_servico        DATE        NOT NULL,   -- dia do turno avaliado
    turno               TEXT,                   -- ex.: "07h30 às 19h30"
    equipe              TEXT,
    posto_atendimento   TEXT,                   -- P.A.
    avaliador_1         TEXT,
    avaliador_2         TEXT,

    -- [{"ocorrencia": "...", "audio": "...", "data": "AAAA-MM-DD", "tma": "mm:ss"}]
    audios              JSONB       NOT NULL DEFAULT '[]'::jsonb,
    -- {"<chave do item>": {"conforme": true|false, "obs": "..."}}
    respostas           JSONB       NOT NULL,

    nota                INTEGER     NOT NULL,
    parecer             TEXT        NOT NULL
                        CHECK (parecer IN ('APROVADO', 'APROVADO COM ORIENTAÇÕES', 'REPROVADO')),
    observacoes         TEXT,
    prov_encarregado    TEXT,                   -- providências do encarregado do STTQ
    prov_chefe          TEXT,                   -- providências do chefe do COBOM
    prov_supervisao     TEXT,                   -- providências da supervisão do COBOM

    criado_por          INTEGER     REFERENCES app.usuarios(id),
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_por      INTEGER     REFERENCES app.usuarios(id),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS auditoria_cobom_data_idx ON b3.auditoria_cobom (data_servico DESC);
CREATE INDEX IF NOT EXISTS auditoria_cobom_re_idx   ON b3.auditoria_cobom (re);

COMMENT ON TABLE b3.auditoria_cobom IS
    'Fichas de avaliação de desempenho do atendente 193 (monitoria de qualidade do COBOM). '
    'Questionário definido em webapp/routers/auditoria_cobom.py.';
