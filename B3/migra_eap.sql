-- ============================================================
-- EAP (B/3) — turmas, escala do efetivo e Ordem de Serviço
--
-- Todo militar do GB faz o EAP uma vez por ano, menos Ten Cel, Maj e Cap
-- com CAO. O calendário de turmas vem da DEC em janeiro; o B/3 escala o
-- efetivo nas turmas ao longo do ano e emite a Ordem de Serviço de cada uma.
--
-- Idempotente: pode rodar de novo sem perder nada.
--   psql -U admin -d 11gb -f B3/migra_eap.sql
-- ============================================================

-- Dígito verificador do RE. A OS cita o RE completo ("900209-7") e o dígito
-- não sai de conta nenhuma — vem do relatório de efetivo do SGP, que até
-- aqui o descartava (B1/efetivo.py passou a gravar).
ALTER TABLE b1.efetivo ADD COLUMN IF NOT EXISTS re_dv varchar(1);

-- Turmas do calendário da DEC. Uma linha por fase virtual (EaD): públicos
-- diferentes fazem o EaD juntos, mas a DEC numera cada público na sua
-- sequência — na OS 073/26, "Turma V para Oficiais e Turma XIV para Cb/Sd"
-- são o mesmo EaD. Daí `publicos`: [{"publico": "Oficiais", "turma": "V"},
-- {"publico": "Cb/Sd", "turma": "XIV"}]. O presencial (data e local) é o
-- dos praças; o dos oficiais é na ESB, por convocação.
CREATE TABLE IF NOT EXISTS b3.eap_turma (
    id                serial PRIMARY KEY,
    ano               integer     NOT NULL,
    publicos          jsonb       NOT NULL,
    ead_inicio        date        NOT NULL,
    ead_fim           date        NOT NULL,
    presencial_em     timestamp,                         -- data e hora da fase presencial
    presencial_local  text,
    vagas             integer,
    observacao        text,
    criado_em         timestamptz NOT NULL DEFAULT now(),
    criado_por        text,
    atualizado_em     timestamptz,
    CHECK (ead_fim >= ead_inicio)
);

-- Upgrade da primeira versão (um público e um número por linha).
ALTER TABLE b3.eap_turma ADD COLUMN IF NOT EXISTS publicos jsonb;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'b3' AND table_name = 'eap_turma' AND column_name = 'publico') THEN
        UPDATE b3.eap_turma
           SET publicos = jsonb_build_array(jsonb_build_object('publico', publico, 'turma', turma))
         WHERE publicos IS NULL;
        ALTER TABLE b3.eap_turma DROP COLUMN publico, DROP COLUMN turma;
    END IF;
END $$;
ALTER TABLE b3.eap_turma ALTER COLUMN publicos SET NOT NULL;

-- Militares inscritos em cada turma. "escalado" é a confirmação: só quem
-- está escalado entra na Ordem de Serviço.
CREATE TABLE IF NOT EXISTS b3.eap_inscricao (
    turma_id      integer     NOT NULL REFERENCES b3.eap_turma(id) ON DELETE CASCADE,
    re            integer     NOT NULL,
    escalado      boolean     NOT NULL DEFAULT false,
    observacao    text,
    criado_em     timestamptz NOT NULL DEFAULT now(),
    criado_por    text,
    atualizado_em timestamptz,
    PRIMARY KEY (turma_id, re)
);
CREATE INDEX IF NOT EXISTS ix_eap_inscricao_re ON b3.eap_inscricao (re);

-- Dispensa permanente do EAP que não sai do posto: Capitão com CAO. Ten Cel
-- e Maj são dispensados pelo posto e não precisam de linha aqui.
CREATE TABLE IF NOT EXISTS b3.eap_dispensa (
    re          integer     PRIMARY KEY,
    motivo      text        NOT NULL DEFAULT 'CAO',
    criado_em   timestamptz NOT NULL DEFAULT now(),
    criado_por  text
);

-- Modelo da Ordem de Serviço, um por ano. A OS de janeiro vira o modelo e
-- é replicada no resto do ano; o que muda a cada turma são os campos
-- {{...}} (os trechos em amarelo do documento original). Sem linha para o
-- ano, vale o modelo padrão do repositório (webapp/modelos/eap_os_modelo.docx).
CREATE TABLE IF NOT EXISTS b3.eap_modelo (
    ano          integer     PRIMARY KEY,
    arquivo      bytea       NOT NULL,
    nome_arquivo text,
    enviado_em   timestamptz NOT NULL DEFAULT now(),
    enviado_por  text
);

-- Ordens de Serviço emitidas — guarda os campos usados, para a próxima
-- sugerir o número seguinte e o mesmo assinante.
CREATE TABLE IF NOT EXISTS b3.eap_os (
    id          serial      PRIMARY KEY,
    ano         integer     NOT NULL,
    numero      integer     NOT NULL,
    turma_ids   integer[]   NOT NULL,
    campos      jsonb       NOT NULL,
    gerado_em   timestamptz NOT NULL DEFAULT now(),
    gerado_por  text
);
