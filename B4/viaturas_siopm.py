# ==========================================
# SINCRONIZAÇÃO SIOPM → BASE DA MOTOMEC (b4.viaturas)
# ==========================================
# Desde 22/10/2026 o SIOPM (COMP MAPA FORÇA) é a fonte oficial de STATUS e
# ESTAÇÃO das viaturas. Este módulo pega uma captura de b3.nivel_op_* e aplica
# em b4.viaturas:
#   - prefixo que o SIOPM mostra e a base tem → status e estação do SIOPM
#   - prefixo que o SIOPM mostra e a base não tem → cadastro mínimo, origem SIOPM
#   - prefixo da base que o SIOPM não mostra → não mexe (frota administrativa)
#   - US sem viatura (TLGR, EFT-E, existe_vtr = N) → ignorada
# Placa, chassi, patrimônio, ano, modelo etc. continuam sendo da planilha.
# Cada campo alterado vai para b4.viaturas_sync_siopm (o "antes e depois").
#
# Uso:
#     python B4/viaturas_siopm.py              # sincroniza com a última captura
#     python B4/viaturas_siopm.py --simular    # mostra o que mudaria e desfaz
#     python B4/viaturas_siopm.py --captura=7  # usa uma captura específica
# Normalmente roda logo depois de cada captura do nível operacional.
# ==========================================

# Acima: Utilitários
import os, re, sys
from collections import Counter

# Acima: Permite importar _comum da raiz do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _comum import conectar_postgres, iniciar_etl, finalizar_etl_sucesso, finalizar_etl_erro


# ==========================================
# CONFIGURAÇÕES
# ==========================================

DOMINIO_ETL = "b4_viaturas_siopm"

# Acima: Prefixo de viatura de verdade (UR11324, ABS11119). Deixa de fora as US
# sem viatura própria: CAR-TLGR, SSL-EFT-E...
RX_PREFIXO = re.compile(r"^([A-Z]{1,4})(\d{5})$")

# Acima: Status do SIOPM em que a viatura está em condição de uso. RESERVA é
# viatura sem guarnição, não viatura quebrada.
STATUS_OPERANDO = {"DISPONÍVEL", "EM ATENDIMENTO", "RESERVA", "OP ESPECIAL", "SUPERVISÃO"}

# Acima: Variantes da base que já dizem a mesma coisa; se a base estiver numa
# delas, fica a variante da base (é mais detalhada que o SIOPM)
EQUIVALENTES = {
    "BAIXA(DEFEITO)": ("BAIXADA", {"BAIXADA", "BAIXADA_DESCARGA"}),
    "PROC DESCARGA":  ("BAIXADA_DESCARGA", {"BAIXADA_DESCARGA", "PROC_DESCARGA"}),
}

CAMPOS_ESTACAO = ["sgb", "pb_bb", "nome_estacao", "municipio"]


def normalizar(prefixo):
    """'UR-11324' e 'UR11324' viram a mesma chave."""
    return re.sub(r"[^A-Z0-9]", "", (prefixo or "").upper())


def status_base(status_siopm, atual):
    """Traduz o status do SIOPM para o vocabulário da base. None = não mexer."""
    if status_siopm in STATUS_OPERANDO:
        return "OPERANDO"
    if status_siopm in EQUIVALENTES:
        padrao, aceitos = EQUIVALENTES[status_siopm]
        return atual if atual in aceitos else padrao
    # Acima: SUBST PREFIXO e status novos que o SIOPM venha a ter: sem regra, sem mudança
    return None


# ==========================================
# SINCRONIZAÇÃO
# ==========================================

def sincronizar(conn, captura_id=None):
    """Aplica a captura em b4.viaturas. Não faz commit: quem chama decide."""
    cur = conn.cursor()

    if captura_id is None:
        cur.execute("SELECT max(id) FROM b3.nivel_op_captura")
        captura_id = cur.fetchone()[0]
    if captura_id is None:
        raise RuntimeError("Nenhuma captura em b3.nivel_op_captura.")

    cur.execute("""
        SELECT v.us, v.status, v.existe_vtr, v.opm_cod,
               e.sgb, e.pb_bb, e.nome_estacao, e.municipio
          FROM b3.nivel_op_viatura v
          LEFT JOIN b4.siopm_estacao e ON e.opm_cod = v.opm_cod
         WHERE v.captura_id = %s
         ORDER BY v.opm_cod, v.ordem""", (captura_id,))
    siopm = cur.fetchall()

    cur.execute("SELECT id, prefixo, status, sgb, pb_bb, nome_estacao, municipio FROM b4.viaturas")
    base = {normalizar(r[1]): r for r in cur.fetchall()}

    resumo = Counter()
    mudancas_status = Counter()

    def logar(prefixo, campo, antes, depois):
        cur.execute("""INSERT INTO b4.viaturas_sync_siopm (captura_id, prefixo, campo, antes, depois)
                       VALUES (%s, %s, %s, %s, %s)""", (captura_id, prefixo, campo, antes, depois))

    for us, st_siopm, existe_vtr, opm_cod, sgb, pb_bb, nome_estacao, municipio in siopm:
        m = RX_PREFIXO.match(normalizar(us))
        if existe_vtr == "N" or not m:
            resumo["ignorada_sem_viatura"] += 1
            continue
        if sgb is None:
            raise RuntimeError(f"OPM {opm_cod} sem linha em b4.siopm_estacao.")

        estacao = {"sgb": sgb, "pb_bb": pb_bb, "nome_estacao": nome_estacao, "municipio": municipio}
        linha = base.get(normalizar(us))

        if linha is None:
            novo_status = status_base(st_siopm, None)
            if novo_status is None:
                resumo["ignorada_sem_regra"] += 1
                continue
            prefixo = f"{m.group(1)}-{m.group(2)}"
            cur.execute("""
                INSERT INTO b4.viaturas
                    (prefixo, opmcb, sgb, pb_bb, nome_estacao, municipio, status, tipo,
                     status_origem, origem_cadastro, siopm_us, siopm_status, siopm_opm_cod,
                     siopm_captura_id, siopm_visto_em, lote_importacao, carregado_em, atualizado_em)
                VALUES (%s, '11.GB', %s, %s, %s, %s, %s, %s,
                        'SIOPM', 'SIOPM', %s, %s, %s, %s, now(), %s, now(), now())""",
                (prefixo, sgb, pb_bb, nome_estacao, municipio, novo_status, m.group(1),
                 us, st_siopm, opm_cod, captura_id, f"SIOPM__captura_{captura_id}"))
            logar(prefixo, "CRIADA", None, f"{novo_status} | {nome_estacao}")
            resumo["criada"] += 1
            continue

        vid, prefixo, st_atual = linha[0], linha[1], linha[2]
        atuais = dict(zip(CAMPOS_ESTACAO, linha[3:7]))
        novo_status = status_base(st_siopm, st_atual)
        if novo_status is None:
            # Acima: Sem regra para o status: não muda nada, nem marca como visto
            resumo["ignorada_sem_regra"] += 1
            continue

        if novo_status != st_atual:
            logar(prefixo, "status", st_atual, novo_status)
            mudancas_status[(st_atual, novo_status)] += 1
            resumo["status_alterado"] += 1
        estacao_mudou = False
        for campo in CAMPOS_ESTACAO:
            if atuais[campo] != estacao[campo]:
                logar(prefixo, campo, atuais[campo], estacao[campo])
                estacao_mudou = True
        resumo["estacao_alterada"] += estacao_mudou

        # Acima: siopm_visto_em = now() é o que deixa este UPDATE passar pela trava
        # (tg_viaturas_trava_siopm), que segura qualquer outro escritor
        cur.execute("""
            UPDATE b4.viaturas
               SET status = %s, sgb = %s, pb_bb = %s, nome_estacao = %s, municipio = %s,
                   status_origem = 'SIOPM', siopm_us = %s, siopm_status = %s,
                   siopm_opm_cod = %s, siopm_captura_id = %s, siopm_visto_em = now(),
                   atualizado_em = now()
             WHERE id = %s""",
            (novo_status, sgb, pb_bb, nome_estacao, municipio,
             us, st_siopm, opm_cod, captura_id, vid))
        resumo["casada"] += 1

    return captura_id, resumo, mudancas_status


def imprimir(captura_id, resumo, mudancas_status):
    print(f"🔄 Sincronização SIOPM → b4.viaturas (captura {captura_id}):")
    print(f"   casadas com a base: {resumo['casada']}")
    print(f"   status alterado:    {resumo['status_alterado']}")
    for (antes, depois), n in sorted(mudancas_status.items(), key=str):
        print(f"      {antes or '(vazio)'} → {depois}: {n}")
    print(f"   estação alterada:   {resumo['estacao_alterada']}")
    print(f"   criadas (origem SIOPM): {resumo['criada']}")
    print(f"   ignoradas (US sem viatura): {resumo['ignorada_sem_viatura']}, "
          f"(status sem regra): {resumo['ignorada_sem_regra']}")


def executar(captura_id=None, simular=False):
    """Sincroniza com auditoria em b1.etl_status. Em --simular, desfaz no fim."""
    conn = conectar_postgres()
    cur = conn.cursor()
    etl_id = None
    try:
        if not simular:
            etl_id = iniciar_etl(cur, DOMINIO_ETL)
            conn.commit()
        captura_id, resumo, mudancas = sincronizar(conn, captura_id)
        imprimir(captura_id, resumo, mudancas)
        if simular:
            conn.rollback()
            print("🧪 Simulação: nada foi gravado.")
            return resumo
        finalizar_etl_sucesso(cur, etl_id, resumo["casada"] + resumo["criada"],
                              resumo["criada"], resumo["status_alterado"])
        conn.commit()
        return resumo
    except Exception as ex:
        conn.rollback()
        if etl_id:
            finalizar_etl_erro(cur, etl_id, str(ex)[:1000])
            conn.commit()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    except AttributeError:
        pass
    args = sys.argv[1:]
    cap = next((int(a.split("=", 1)[1]) for a in args if a.startswith("--captura=")), None)
    executar(cap, simular="--simular" in args)
