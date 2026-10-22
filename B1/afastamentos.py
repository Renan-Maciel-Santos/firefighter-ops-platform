# ==========================================
# ETL DE AFASTAMENTOS — a partir do RELATÓRIO do SGP
# ==========================================
# Substitui a versão em Selenium que raspava a tela de gestão RE a RE, exigia
# login manual ("pressione ENTER...") e por isso nunca pôde ser agendada. Ficou
# parada de 04/03/2026 a 17/08/2026 — 166 dias.
#
# O SGP passou a oferecer /Relatorios/Afastamentos com export Excel da unidade
# inteira, então aqui só se lê a planilha. 500+ navegações viraram um arquivo.
#
# Semântica de carga (merge):
#   - chave que não existe no banco  -> INSERT
#   - chave que existe e mudou       -> UPDATE
#   - chave que existe e está igual  -> não toca (contabilizado como "sem mudança")
#   - chave que SUMIU do relatório    -> marca ausente_no_sgp_desde (não apaga);
#                                        volta a NULL se o lançamento reaparecer
#
# Uso:
#     python afastamentos.py                      # pega o mais recente em Downloads
#     python afastamentos.py caminho/arquivo.xlsx
# ==========================================

# Acima: Leitura da planilha
import pandas as pd

# Acima: Paths e argumentos
import os, sys
from datetime import date

# Acima: Carga em lote na tabela temporária
from psycopg2.extras import execute_values

# Acima: Conexão, auditoria em b1.etl_status e parsers compartilhados com os outros ETLs.
# Acima: Traz também as credenciais via .env — esta versão não tem mais senha no fonte.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _comum import (
    conectar_postgres,
    iniciar_etl,
    finalizar_etl_sucesso,
    finalizar_etl_erro,
    localizar_arquivo_relatorio,
    confirmar_com_usuario,
    re_para_int,
    data_ptbr_para_date,
    to_int,
    texto_ou_none,
)

DOMINIO = "afastamentos"

# Acima: Início do período pedido ao SGP na exportação do relatório. A marcação de
# ausentes só vale dentro dele — o que terminou antes nunca viria no relatório.
INICIO_PERIODO_RELATORIO = date(2000, 1, 1)

# Acima: Relatório com menos de 95% das linhas da última carga não marca
# ninguém como ausente. Um export cortado no meio faria milhares de
# afastamentos verdadeiros sumirem do painel de uma vez.
FRACAO_MINIMA_PARA_MARCAR = 0.95

# Acima: Nome com que o SGP exporta o relatório
PADRAO_ARQUIVO = "Relatório Afastamentos*.xlsx"

# Acima: Colunas esperadas — se o SGP mudar o layout, falha aqui com mensagem clara
# em vez de gravar lixo silenciosamente.
COLUNAS = ["Posto/ Grad", "RE", "Nome", "Quadro", "OPM Cadastro", "Condição",
           "Tipo de Afastamento", "Data Inicial", "Data Final", "Total Dias", "Observações"]


def ler_planilha(caminho):
    # Acima: engine="calamine" NÃO é preferência de estilo: o openpyxl quebra com
    # TypeError('expected Fill') no stylesheet que o SGP gera neste relatório.
    # Trocar de engine é o que torna o arquivo legível.
    df = pd.read_excel(caminho, sheet_name=0, engine="calamine", dtype=str)

    faltando = [c for c in COLUNAS if c not in df.columns]
    if faltando:
        raise ValueError(
            f"Layout do relatório mudou — colunas ausentes: {faltando}\n"
            f"Colunas encontradas: {list(df.columns)}"
        )
    return df


def montar_linhas(df):
    """Normaliza a planilha e resolve chaves repetidas. Devolve (linhas, descartadas)."""
    por_chave = {}
    descartadas = 0

    for _, r in df.iterrows():
        re_int = re_para_int(r["RE"])
        motivo = texto_ou_none(r["Tipo de Afastamento"])
        inicio = data_ptbr_para_date(r["Data Inicial"])

        # Acima: Sem chave completa a linha é inútil — não dá pra casar nem atualizar
        if re_int is None or motivo is None or inicio is None:
            descartadas += 1
            continue

        obs = texto_ou_none(r["Observações"])
        chave = (re_int, motivo, inicio)

        if chave in por_chave:
            # Acima: O próprio relatório traz ~24 chaves repetidas que diferem só na
            # observação (o mesmo afastamento citado em dois documentos, ex.
            # "OF 11GB-258/130/12" e "BI 01/13"). Juntar preserva os dois documentos
            # em vez de deixar a última linha lida ganhar por acaso.
            anterior = por_chave[chave]
            if obs and obs not in (anterior["observacao"] or ""):
                anterior["observacao"] = " | ".join(filter(None, [anterior["observacao"], obs]))
            continue

        por_chave[chave] = {
            "re": re_int,
            "motivo": motivo,
            "data_inicio": inicio,
            "data_fim": data_ptbr_para_date(r["Data Final"]),
            "quantidade_dias": to_int(r["Total Dias"]),
            "observacao": obs,
            "opm": texto_ou_none(r["OPM Cadastro"]),
            "posto_grad": texto_ou_none(r["Posto/ Grad"]),
            "nome": texto_ou_none(r["Nome"]),
            "quadro": texto_ou_none(r["Quadro"]),
            "condicao": texto_ou_none(r["Condição"]),
        }

    return list(por_chave.values()), descartadas


def merge(cur, linhas):
    """Carrega numa temporária e faz o merge. Devolve (inseridas, atualizadas, sem_mudanca)."""
    cur.execute("""
        CREATE TEMP TABLE tmp_afast (
            re bigint, motivo text, data_inicio date, data_fim date,
            quantidade_dias int, observacao text, opm text,
            posto_grad text, nome text, quadro text, condicao text
        ) ON COMMIT DROP;
    """)

    execute_values(cur, """
        INSERT INTO tmp_afast (re, motivo, data_inicio, data_fim, quantidade_dias,
                               observacao, opm, posto_grad, nome, quadro, condicao)
        VALUES %s
    """, [(d["re"], d["motivo"], d["data_inicio"], d["data_fim"], d["quantidade_dias"],
           d["observacao"], d["opm"], d["posto_grad"], d["nome"], d["quadro"], d["condicao"])
          for d in linhas], page_size=1000)

    # Acima: O WHERE do DO UPDATE é o coração da semântica pedida: quando nada mudou,
    # a linha não é tocada e nem aparece no RETURNING — é o "passa batido", e sem ele
    # o atualizado_em seria reescrito em 29 mil linhas toda madrugada.
    # Acima: origem_informacao e dt_cadastro NÃO entram no UPDATE porque o relatório não
    # os fornece — sobrescrevê-los apagaria o histórico vindo do P1 e das PERÍCIAS.
    # Acima: xmax = 0 distingue linha inserida de linha atualizada no mesmo RETURNING.
    cur.execute("""
        INSERT INTO b1.afastamentos AS a
            (re, motivo, data_inicio, data_fim, quantidade_dias, observacao, opm,
             posto_grad, nome, quadro, condicao, origem_informacao, atualizado_em)
        SELECT re, motivo, data_inicio, data_fim, quantidade_dias, observacao, opm,
               posto_grad, nome, quadro, condicao, 'RELATORIO_SGP', now()
          FROM tmp_afast
        ON CONFLICT (re, motivo, data_inicio) DO UPDATE SET
            data_fim        = EXCLUDED.data_fim,
            quantidade_dias = EXCLUDED.quantidade_dias,
            observacao      = EXCLUDED.observacao,
            opm             = EXCLUDED.opm,
            posto_grad      = EXCLUDED.posto_grad,
            nome            = EXCLUDED.nome,
            quadro          = EXCLUDED.quadro,
            condicao        = EXCLUDED.condicao,
            atualizado_em   = now()
        WHERE (a.data_fim, a.quantidade_dias, a.observacao, a.opm,
               a.posto_grad, a.nome, a.quadro, a.condicao)
              IS DISTINCT FROM
              (EXCLUDED.data_fim, EXCLUDED.quantidade_dias, EXCLUDED.observacao, EXCLUDED.opm,
               EXCLUDED.posto_grad, EXCLUDED.nome, EXCLUDED.quadro, EXCLUDED.condicao)
        RETURNING (xmax = 0) AS inserida;
    """)

    resultados = cur.fetchall()
    inseridas = sum(1 for (ins,) in resultados if ins)
    atualizadas = len(resultados) - inseridas
    return inseridas, atualizadas, len(linhas) - len(resultados)


def marcar_ausentes(cur, data_relatorio, fim_janela):
    """Marca o que sumiu do relatório e desmarca o que voltou. Devolve (marcadas, desmarcadas).

    Antes disto o merge só inseria e atualizava: férias reprogramadas no SGP
    deixavam a linha antiga no banco, e o militar seguia "afastado" no painel.

    Só é marcada a linha que o relatório DEVERIA trazer — senão a ausência dela
    não prova nada:
      - o RE aparece no relatório (quem saiu da unidade não vem mais nele);
      - o motivo existe no relatório (LICENCA COMPULSORIA e LICENÇA PARA
        TRATAMENTO DE SAÚDE vêm das Perícias e o relatório não as traz);
      - o afastamento começou dentro do período pedido: entre 01/01/2000 e
        fim_janela (31/12 do ano, desde 22/10/2026; antes era o dia do
        relatório, e afastamento futuro cancelado nunca saía do banco). Contar só o
        início, e não a sobreposição, deixa de fora as ~200 linhas da raspagem
        antiga com início 1900 ou 1969 — data de preenchimento, não real, que
        nunca casaria com o relatório e seria dada como sumida.
    """
    cur.execute("""
        UPDATE b1.afastamentos a
           SET ausente_no_sgp_desde = NULL
          FROM tmp_afast t
         WHERE a.ausente_no_sgp_desde IS NOT NULL
           AND (a.re, a.motivo, a.data_inicio) = (t.re, t.motivo, t.data_inicio)
    """)
    desmarcadas = cur.rowcount

    cur.execute("""
        UPDATE b1.afastamentos a
           SET ausente_no_sgp_desde = %(dia)s
         WHERE a.ausente_no_sgp_desde IS NULL
           AND a.data_inicio BETWEEN %(ini)s AND %(fim)s
           AND a.re     IN (SELECT re     FROM tmp_afast)
           AND a.motivo IN (SELECT motivo FROM tmp_afast)
           AND NOT EXISTS (SELECT 1 FROM tmp_afast t
                            WHERE (t.re, t.motivo, t.data_inicio) = (a.re, a.motivo, a.data_inicio))
    """, {"dia": data_relatorio, "ini": INICIO_PERIODO_RELATORIO, "fim": fim_janela})
    return cur.rowcount, desmarcadas


def linhas_da_ultima_carga(cur):
    cur.execute("SELECT linhas_lidas FROM b1.etl_status WHERE dominio = %s AND status = 'success'",
                (DOMINIO,))
    r = cur.fetchone()
    return r[0] if r else None


def main():
    caminho = localizar_arquivo_relatorio(
        PADRAO_ARQUIVO,
        sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else None,
    )
    confirmar_com_usuario(caminho)

    print(f"📂 Lendo {caminho}")
    df = ler_planilha(caminho)
    print(f"🔎 Linhas na planilha: {len(df)}")

    linhas, descartadas = montar_linhas(df)
    print(f"✅ Chaves únicas montadas: {len(linhas)}")
    if descartadas:
        print(f"⚠️  Descartadas por chave incompleta (RE/motivo/data inicial): {descartadas}")

    # Acima: O relatório vai até o dia em que foi exportado. A data do arquivo,
    # e não a de hoje, é o que vale: rodar à mão com um arquivo de dias atrás não
    # pode dar por sumido o que começou depois dele.
    data_relatorio = date.fromtimestamp(os.path.getmtime(caminho))

    # Acima: A captura pede até 31/12. Mas só dá para dar por sumido o afastamento
    # futuro se o relatório de fato trouxe afastamentos futuros: um arquivo baixado
    # à mão com data fim = hoje faria toda a programação do P1 "sumir" de uma vez.
    tem_futuro = any(l["data_inicio"] > data_relatorio for l in linhas)
    fim_janela = date(data_relatorio.year, 12, 31) if tem_futuro else data_relatorio
    if not tem_futuro:
        print("ℹ️  Relatório sem afastamento futuro: ausências conferidas só até "
              f"{data_relatorio:%d/%m/%Y}.")

    conn = conectar_postgres()
    cur = conn.cursor()
    anterior = linhas_da_ultima_carga(cur)
    etl_id = iniciar_etl(cur, DOMINIO)
    conn.commit()

    try:
        inseridas, atualizadas, sem_mudanca = merge(cur, linhas)

        if anterior and len(df) < FRACAO_MINIMA_PARA_MARCAR * anterior:
            marcadas = desmarcadas = None
            print(f"⚠️  Relatório com {len(df)} linhas contra {anterior} da última carga — "
                  f"ausências NÃO marcadas nesta execução (export pode ter vindo cortado).")
        else:
            marcadas, desmarcadas = marcar_ausentes(cur, data_relatorio, fim_janela)
        finalizar_etl_sucesso(cur, etl_id, len(df), inseridas, atualizadas)
        conn.commit()

        print("\n✅ Merge concluído.")
        print(f"📥 Linhas lidas:      {len(df)}")
        print(f"➕ Inseridas (novas): {inseridas}")
        print(f"🔁 Atualizadas:       {atualizadas}")
        print(f"⏭️  Sem mudança:       {sem_mudanca}")
        if marcadas is not None:
            print(f"🚫 Sumiram do SGP:    {marcadas}")
            print(f"↩️  Voltaram ao SGP:   {desmarcadas}")

    except Exception as e:
        conn.rollback()
        try:
            finalizar_etl_erro(cur, etl_id, str(e))
            conn.commit()
        except Exception:
            conn.rollback()
        print(f"❌ Falhou: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
