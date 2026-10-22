"""
Popula um Postgres vazio com dados FICTÍCIOS para o painel do 11º GB abrir.

Nada aqui veio do banco real: nomes, REs, telefones, afastamentos, viaturas,
ocorrências e processos são sorteados com semente fixa, em proporções
parecidas com as de um grupamento de ~500 militares, para que cada aba mostre
números plausíveis. Os REs ficam na faixa 900001-900520, que é a mesma usada
nos exemplos do código e nos testes da B.I.A. (avaliacao_llm/).

Uso (dentro do compose):
    docker compose exec webapp python seed/gerar_dados_ficticios.py --recriar

--recriar  apaga os schemas do painel e reaplica db/demo/schema.sql antes da carga.
           Sem ele, o script espera o schema já criado e vazio.

As datas são relativas a HOJE: as views "_hoje" do mapa de força e o nível
operacional só mostram o que foi capturado no dia, então rodar o seed de novo
amanhã "atualiza" o painel.
"""

import argparse
import hashlib
import json
import os
import random
import sys
import unicodedata
from datetime import date, datetime, time, timedelta

import psycopg2
from psycopg2.extras import Json, execute_values

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from _env import exigir, opcional  # noqa: E402

SEMENTE = 11
rnd = random.Random(SEMENTE)
HOJE = date.today()
AGORA = datetime.now().replace(microsecond=0)

SCHEMAS = ("app", "b1", "b3", "b4", "b5", "bia", "sjd", "uge")

# ==========================================
# ESTRUTURA FICTÍCIA DO GRUPAMENTO
# ==========================================
# Códigos de OPM com o prefixo fictício 99011 (o real foi trocado no código
# inteiro). Regra que as views e o efetivo_regras.py seguem: 9 dígitos,
# o 6º diz o SGB (1-4) ou o EM (0/9); código terminado em zero é sede/adm,
# os demais são estações (atividade-fim).

# (opm_cod, sgb, pelotão, nome da estação, município, cod IBGE, lat, lon)
ESTACOES = [
    ("990111101", "1ºSGB", "1ºPB", "PB VILA BETANIA",          "SÃO JOSÉ DOS CAMPOS",    3549904, -23.200, -45.890),
    ("990111102", "1ºSGB", "1ºPB", "BCom PARAIBUNA",           "PARAIBUNA",              3535705, -23.387, -45.662),
    ("990111201", "1ºSGB", "2ºPB", "PB VILA INDUSTRIAL",       "SÃO JOSÉ DOS CAMPOS",    3549904, -23.185, -45.870),
    ("990111202", "1ºSGB", "2ºPB", "BB LESTE",                 "SÃO JOSÉ DOS CAMPOS",    3549904, -23.170, -45.830),
    ("990111301", "1ºSGB", "3ºPB", "PB SUL",                   "SÃO JOSÉ DOS CAMPOS",    3549904, -23.250, -45.900),
    ("990111401", "1ºSGB", "4ºPB", "PB JACAREI",               "JACAREÍ",                3524402, -23.305, -45.966),
    ("990112101", "2ºSGB", "1ºPB", "PB BOM CONSELHO",          "TAUBATÉ",                3554102, -23.026, -45.555),
    ("990112102", "2ºSGB", "1ºPB", "BB QUIRIRIM",              "TAUBATÉ",                3554102, -22.990, -45.480),
    ("990112103", "2ºSGB", "1ºPB", "BCom SÃO LUÍS PARAITINGA", "SÃO LUIZ DO PARAITINGA", 3550001, -23.222, -45.310),
    ("990112201", "2ºSGB", "2ºPB", "PB ANA EMILIA",            "TAUBATÉ",                3554102, -23.040, -45.580),
    ("990112202", "2ºSGB", "2ºPB", "BB CACAPAVA",              "CAÇAPAVA",               3508504, -23.100, -45.707),
    ("990112301", "2ºSGB", "3ºPB", "PB CAMPOS DO JORDAO",      "CAMPOS DO JORDÃO",       3509700, -22.739, -45.591),
    ("990113101", "3ºSGB", "1ºPB", "PB GUARATINGUETA",         "GUARATINGUETÁ",          3518404, -22.816, -45.192),
    ("990113102", "3ºSGB", "1ºPB", "BB LORENA",                "LORENA",                 3527207, -22.731, -45.124),
    ("990113104", "3ºSGB", "1ºPB", "BCom CUNHA",               "CUNHA",                  3513603, -23.074, -44.959),
    ("990113201", "3ºSGB", "2ºPB", "PB CRUZEIRO",              "CRUZEIRO",               3513405, -22.576, -44.963),
    ("990113202", "3ºSGB", "2ºPB", "BB CACHOEIRA PAULISTA",    "CACHOEIRA PAULISTA",     3508603, -22.665, -45.009),
    ("990113203", "3ºSGB", "2ºPB", "BCom BANANAL",             "BANANAL",                3504909, -22.683, -44.322),
    ("990113301", "3ºSGB", "3ºPB", "PB PINDAMONHANGABA",       "PINDAMONHANGABA",        3538006, -22.924, -45.462),
    ("990113302", "3ºSGB", "3ºPB", "BB APARECIDA",             "APARECIDA",              3502507, -22.846, -45.230),
    ("990113303", "3ºSGB", "3ºPB", "BCom POTIM",               "POTIM",                  3540259, -22.842, -45.251),
    ("990114101", "4ºSGB", "1ºPB", "PB CARAGUATATUBA",         "CARAGUATATUBA",          3510500, -23.620, -45.412),
    ("990114102", "4ºSGB", "1ºPB", "BB UBATUBA",               "UBATUBA",                3555406, -23.434, -45.071),
    ("990114201", "4ºSGB", "2ºPB", "PB SAO SEBASTIAO",         "SÃO SEBASTIÃO",          3550704, -23.760, -45.409),
    ("990114202", "4ºSGB", "2ºPB", "BB ILHABELA",              "ILHABELA",               3520400, -23.778, -45.358),
]
EST_POR_COD = {e[0]: e for e in ESTACOES}

# Sedes e setores administrativos (código terminado em zero).
SETORES_EM = {
    "990110000": "11.GB",
    "990119100": "SEC SDM ATIV TEC",
    "990119110": "B/1 E B/5",
    "990119120": "AG AREA",
    "990119130": "B/3 PJMD E MOTOMEC",
    "990119131": "COBOM",
    "990119140": "B/4",
    "990119160": "ST UGE",
    "990119200": "SEC ATIV TEC",
}

LOTACAO_SGB = {"1": "1°Sgb", "2": "2°Sgb", "3": "3°Sgb", "4": "4°Sgb"}
SGB_ROTULO = {"1": "1º SGB", "2": "2º SGB", "3": "3º SGB", "4": "4º SGB"}


def lotacao_de(cod):
    d = cod[5]
    return LOTACAO_SGB.get(d, "EM")


def opm_texto(cod):
    if cod in SETORES_EM:
        return SETORES_EM[cod]
    if cod in EST_POR_COD:
        n = EST_POR_COD[cod][3]
        return f"{cod[-1]}. EB - {n.split(' ', 1)[1]}"
    if cod.endswith("0000"):
        return f"{cod[5]}. SGB"
    if cod.endswith("800"):
        return "ADM"
    if cod.endswith("900"):
        return "NUCL ATIV TEC"
    return f"{cod[6]}. PB"


# ==========================================
# NOMES FICTÍCIOS
# ==========================================
PRENOMES_M = ["ANDRE", "BRUNO", "CAIO", "DANIEL", "DIEGO", "EDUARDO", "FABIO", "FELIPE", "GABRIEL",
              "GUSTAVO", "HENRIQUE", "IGOR", "JULIO", "LEANDRO", "LUCAS", "MARCELO", "MATEUS",
              "MURILO", "NATAN", "OTAVIO", "PAULO", "RAFAEL", "RENATO", "RODRIGO", "SAMUEL",
              "THIAGO", "VAGNER", "VITOR", "WELLINGTON", "ALEX", "CRISTIANO", "EDSON", "FERNANDO",
              "GILBERTO", "HUGO", "JEFERSON", "LEONARDO", "MAURICIO", "RICARDO", "SERGIO"]
PRENOMES_F = ["ALINE", "BEATRIZ", "CAMILA", "DANIELA", "FERNANDA", "GABRIELA", "JULIANA", "LARISSA",
              "MARIANA", "NATALIA", "PATRICIA", "RENATA", "TATIANE", "VANESSA"]
SOBRENOMES = ["ALVES", "AMARAL", "ANDRADE", "ARANTES", "BARROS", "BRAGA", "CAMARGO", "CAMPOS",
              "CARDOSO", "CASTRO", "CORREA", "COUTO", "DUARTE", "ESTEVES", "FARIAS", "FIGUEIRA",
              "FONTES", "FRANCO", "GALVAO", "GODOY", "LACERDA", "LEMOS", "MACHADO", "MAGALHAES",
              "MEDEIROS", "MIRANDA", "MOTA", "NOVAES", "PACHECO", "PEIXOTO", "PIRES", "QUEIROZ",
              "RAMOS", "RESENDE", "SAMPAIO", "SIQUEIRA", "TAVARES", "TOLEDO", "VASCONCELOS",
              "VENTURA", "VIANA", "XAVIER", "AGUIAR", "BORGES", "CUNHA NETO", "DANTAS", "FREIRE",
              "LOBO", "MONTEIRO", "PRATES", "SALGADO", "VALENTE"]


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


# ==========================================
# POSTOS E GRADUAÇÕES
# ==========================================
# posto_grad (SGP) -> (quadro, nivel, codigo_posto, sigla, rótulo do mapa de força, posto SIOPM)
POSTOS = {
    "TEN CEL PM": ("QOPM", 2, 20, "TC", "TENENTE CORONEL PM", "TEN CEL"),
    "MAJ PM":     ("QOPM", 3, 21, "MJ", "MAJOR PM", "MAJ"),
    "CAP PM":     ("QOPM", 4, 27, "CP", "CAPITÃO PM", "CAP"),
    "1. TEN PM":  ("QOPM", 5, 23, "1T", "1° TENENTE PM", "1.TEN"),
    "2. TEN PM":  ("QAOPM", 6, 25, "2T", "2° TENENTE PM", "2.TEN"),
    "SUBTEN PM":  ("QPPM", 12, 18, "ST", "SUB TENENTE PM", "SUBTEN"),
    "1. SGT PM":  ("QPPM", 13, 22, "1S", "1° SARGENTO PM", "1.SGT"),
    "2. SGT PM":  ("QPPM", 14, 24, "2S", "2° SARGENTO PM", "2.SGT"),
    "3. SGT PM":  ("QPPM", 15, 26, "3S", "3° SARGENTO PM", "3.SGT"),
    "CB PM":      ("QPPM", 16, 5, "CB", "CABO PM", "CB"),
    "SD PM":      ("QPPM", 17, 16, "SD", "SOLDADO PM", "SD"),
}
ABREV = {"TEN CEL PM": "Ten Cel", "MAJ PM": "Maj", "CAP PM": "Cap", "1. TEN PM": "1º Ten",
         "2. TEN PM": "2º Ten", "SUBTEN PM": "Subten", "1. SGT PM": "1º Sgt", "2. SGT PM": "2º Sgt",
         "3. SGT PM": "3º Sgt", "CB PM": "Cb", "SD PM": "Sd"}
PRACA_OP = ("SUBTEN PM", "1. SGT PM", "2. SGT PM", "3. SGT PM", "CB PM", "SD PM")


def dv_re(re):
    soma = sum(int(d) * p for d, p in zip(str(re), range(7, 1, -1)))
    r = 11 - soma % 11
    return "0" if r >= 10 else str(r)


def fone_ficticio(i):
    """Celular fictício na faixa 11 90000-NNNN (não sorteia números reais)."""
    return f"1190000{i % 10000:04d}"


# ==========================================
# GERAÇÃO DO EFETIVO
# ==========================================
def gerar_efetivo():
    """~500 militares: oficiais nas sedes, praças distribuídos pelas estações."""
    vagas = []  # (posto, cod_opm)
    vagas += [("TEN CEL PM", "990110000"), ("MAJ PM", "990110000"), ("CAP PM", "990119100")]
    for s in "1234":
        vagas.append(("CAP PM", f"99011{s}000"))
        vagas += [("1. TEN PM", f"99011{s}{p}00") for p in "12"]
        vagas += [("1. SGT PM", f"99011{s}800"), ("CB PM", f"99011{s}800"), ("CB PM", f"99011{s}800")]
        vagas += [("1. SGT PM", f"99011{s}900"), ("CB PM", f"99011{s}900")]
    vagas += [("1. TEN PM", "990119110"), ("2. TEN PM", "990119130"), ("2. TEN PM", "990119140"),
              ("1. TEN PM", "990119131")]
    em_pracas = {"990119110": 12, "990119120": 2, "990119130": 10, "990119131": 29,
                 "990119140": 3, "990119160": 4, "990119200": 11}
    for cod, n in em_pracas.items():
        for i in range(n):
            vagas.append((rnd.choices(PRACA_OP, weights=[3, 10, 4, 1, 25, 6])[0], cod))
    # Estações: PB maior que BB, BCom pequeno.
    for cod, _sgb, _pb, nome, *_ in ESTACOES:
        n = 23 if nome.startswith("PB") else (12 if nome.startswith("BB") else 2)
        n += rnd.randint(-2, 3) if n > 2 else 0
        for i in range(n):
            vagas.append((rnd.choices(PRACA_OP, weights=[3, 11, 3, 1, 58, 18])[0], cod))
    rnd.shuffle(vagas)

    res = list(range(900001, 900001 + len(vagas) + 12))
    efetivo, usados = [], set()
    # Os primeiros REs são personagens fixos citados nos testes e no README.
    fixos = {
        900001: ("TEN CEL PM", "990110000", "MARCELO BRAGANCA SAMPAIO", "M"),
        900002: ("MAJ PM", "990110000", "RICARDO MOURA LACERDA", "M"),
        900003: ("CB PM", "990119130", "RAFAEL DUARTE LIMA", "M"),
        900004: ("CAP PM", "990119100", "HENRIQUE PRATES GODOY", "M"),
    }
    for re, (pg, cod, nome, sexo) in fixos.items():
        efetivo.append(dict(re=re, posto_grad=pg, cod=cod, nome=nome, sexo=sexo))
        usados.add(re)
    removidos = {("TEN CEL PM", "990110000"), ("MAJ PM", "990110000"), ("CAP PM", "990119100")}
    livres = [r for r in res if r not in usados]
    for (pg, cod) in vagas:
        if (pg, cod) in removidos:
            removidos.discard((pg, cod))
            continue
        re = livres.pop(0)
        sexo = "F" if rnd.random() < 0.08 else "M"
        pren = rnd.choice(PRENOMES_F if sexo == "F" else PRENOMES_M)
        nome = f"{pren} {rnd.choice(SOBRENOMES)} {rnd.choice(SOBRENOMES)}"
        efetivo.append(dict(re=re, posto_grad=pg, cod=cod, nome=nome, sexo=sexo))

    for m in efetivo:
        nivel = POSTOS[m["posto_grad"]][1]
        anos = {2: 26, 3: 23, 4: 18, 5: 12, 6: 25, 12: 26, 13: 21, 14: 17, 15: 14, 16: 9, 17: 3}[nivel]
        m["data_admissao"] = HOJE - timedelta(days=int(365 * max(1, anos + rnd.uniform(-4, 4))))
        m["quadro"] = POSTOS[m["posto_grad"]][0]
        m["re_dv"] = dv_re(m["re"])
        m["guerra"] = m["nome"].split()[-1] if rnd.random() < 0.7 else m["nome"].split()[0]
        m["situacao"] = "EFETIVO"
    for m in rnd.sample(efetivo, 4):
        m["situacao"] = "LSV - (LICENCA CARATER PARTICULAR)"
    return efetivo


# ==========================================
# CARGA
# ==========================================
def conectar():
    return psycopg2.connect(
        host=opcional("PG_HOST", "localhost"), port=opcional("PG_PORT", "5432"),
        dbname=opcional("PG_DB", "11gb"), user=opcional("PG_USER", "admin"),
        password=exigir("PG_PASS"),
    )


def checar_banco_demo(cur):
    """Recusa carregar num banco que não seja de demonstração.

    O --recriar começa com DROP SCHEMA ... CASCADE. Se este script for rodado
    fora do container com um .env apontando para um Postgres de produção (que
    aceite a conexão sem senha, como um pg_hba com trust), ele apagaria tudo.
    Por isso só segue em banco vazio ou em banco já marcado como demo por uma
    carga anterior (demo.instancia).
    """
    cur.execute("SELECT to_regclass('demo.instancia') IS NOT NULL, to_regclass('b1.efetivo') IS NOT NULL")
    marcado, tem_schema = cur.fetchone()
    if marcado or not tem_schema:
        return
    cur.execute("SELECT current_database(), inet_server_addr(), inet_server_port()")
    banco, host, porta = cur.fetchone()
    sys.exit(
        f"\nRECUSADO: o banco '{banco}' ({host or 'socket'}:{porta}) já tem o schema do painel e NÃO está\n"
        "marcado como demonstração (falta demo.instancia). Isto parece um banco de produção.\n"
        "Confira PG_HOST/PG_PORT/PG_DB no .env. O seed só roda em banco vazio ou criado por ele.\n"
    )


def marcar_banco_demo(cur):
    cur.execute("""CREATE SCHEMA IF NOT EXISTS demo;
                   CREATE TABLE IF NOT EXISTS demo.instancia (
                       criado_em timestamptz NOT NULL DEFAULT now(),
                       observacao text NOT NULL DEFAULT 'banco de demonstração com dados fictícios')""")
    cur.execute("INSERT INTO demo.instancia DEFAULT VALUES")


def recriar(cur):
    cur.execute("DROP SCHEMA IF EXISTS " + ", ".join(SCHEMAS) + " CASCADE")
    with open(os.path.join(RAIZ, "db", "demo", "schema.sql"), encoding="utf-8") as f:
        cur.execute(f.read())
    cur.execute("SET search_path TO public")


def ins(cur, tabela, colunas, linhas, page_size=1000):
    if not linhas:
        return
    execute_values(cur, f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES %s", linhas,
                   page_size=page_size)
    print(f"  {tabela:<34} {len(linhas):>6}")


def carregar_b1(cur, efetivo):
    agora = AGORA
    ins(cur, "b1.efetivo",
        ["re", "nome", "posto_grad", "cod_opm_atual", "ativo", "quadro", "sexo", "data_admissao",
         "opm_atual", "opm_efetiva", "cod_opm_efetiva", "situacao", "re_dv"],
        [(m["re"], m["nome"], m["posto_grad"], int(m["cod"]), True, m["quadro"], m["sexo"],
          m["data_admissao"], opm_texto(m["cod"]), "11.GB", 990110000, m["situacao"], m["re_dv"])
         for m in efetivo])

    # Afastamentos: histórico de férias + eventos, e ~18% do efetivo afastado hoje.
    MOTIVOS = [("FERIAS", 30, "P1", 40), ("DISPENSA DO SERVICO", 2, "P1", 14),
               ("CONVALESCENCA", 10, "PERÍCIAS", 8), ("LICENCA-PREMIO", 30, "P1", 7),
               ("LICENÇA PARA TRATAMENTO DE SAÚDE", 15, "PERÍCIAS", 5), ("LUTO", 8, "P1", 2),
               ("LICENÇA-PATERNIDADE", 20, "P1", 2), ("LOUVOR - DOACAO DE SANGUE", 1, "P1", 2),
               ("NUPCIAS", 8, "P1", 1), ("DISPENSA RECOMPENSA", 3, "P1", 1)]
    pesos = [m[3] for m in MOTIVOS]
    afast, chaves = [], set()

    def add(m, motivo, ini, dias, origem):
        k = (m["re"], motivo, ini)
        if k in chaves:
            return
        chaves.add(k)
        afast.append((m["re"], opm_texto(m["cod"]), motivo, origem, ini, ini + timedelta(days=dias - 1),
                      dias, ini - timedelta(days=rnd.randint(5, 40)), None, m["posto_grad"],
                      m["nome"], m["quadro"], "ATIVO", agora, None))

    for m in efetivo:
        for ano in (HOJE.year - 2, HOJE.year - 1, HOJE.year):
            ini = date(ano, rnd.randint(1, 12), rnd.randint(1, 28))
            add(m, "FERIAS", ini, 30, "RELATORIO_SGP" if rnd.random() < .3 else "P1")
        for _ in range(rnd.randint(0, 4)):
            motivo, dias, origem, _p = rnd.choices(MOTIVOS, weights=pesos)[0]
            add(m, motivo, HOJE - timedelta(days=rnd.randint(1, 900)), max(1, dias + rnd.randint(-2, 5)), origem)
    for m in rnd.sample(efetivo, int(len(efetivo) * 0.18)):
        motivo, dias, origem, _p = rnd.choices(MOTIVOS, weights=pesos)[0]
        dias = max(dias, 3)
        add(m, motivo, HOJE - timedelta(days=rnd.randint(0, dias - 1)), dias, origem)
    for m in rnd.sample(efetivo, 60):  # futuros (até 31/12)
        add(m, "FERIAS", HOJE + timedelta(days=rnd.randint(3, max(4, (date(HOJE.year, 12, 31) - HOJE).days))), 30, "RELATORIO_SGP")
    ins(cur, "b1.afastamentos",
        ["re", "opm", "motivo", "origem_informacao", "data_inicio", "data_fim", "quantidade_dias",
         "dt_cadastro", "observacao", "posto_grad", "nome", "quadro", "condicao", "atualizado_em",
         "ausente_no_sgp_desde"], afast)

    # Restrições médicas: ~8% com restrição vigente.
    ESPEC = ["Ortopedia"] * 8 + ["Psiquiatria", "Cirurgia Geral", "Cardiologia", "Neurologia", "Oftalmologia"]
    CODS = ["EF", "EF,SP", "EF,SE,SP", "EF,OU,SE,SP", "SE,SP", "SN", "EF,LP,SE,SP", None, None]
    restr = []
    for m in rnd.sample(efetivo, 140):
        for _ in range(rnd.randint(1, 3)):
            ini = HOJE - timedelta(days=rnd.randint(0, 700))
            dias = rnd.choice([15, 30, 30, 60, 90, 180])
            fim = ini + timedelta(days=dias)
            restr.append((m["re"], "ATIVO", rnd.choice(CODS), rnd.choice(ESPEC), ini, fim, dias,
                          "Apto Pleno" if fim < HOJE and rnd.random() < .5 else
                          rnd.choice(["Apto com Restrição"] * 3 + ["Licença para tratamento de saúde"])))
    ins(cur, "b1.restricoes",
        ["re", "condicao", "restricao_medica", "origem", "data_inicial", "data_final", "total_dias", "observacao"],
        restr)

    # IAS: inspeção anual; ~12% atrasada e ~3% sem nenhuma.
    ias = []
    for m in efetivo:
        r = rnd.random()
        if r < 0.03:
            continue
        ultimo = HOJE.year - (1 if r < 0.15 else 0)
        for ano in range(ultimo - 2, ultimo + 1):
            dm = date(ano, rnd.randint(1, 9), rnd.randint(1, 28))
            if ano == HOJE.year and dm > HOJE:
                dm = HOJE - timedelta(days=rnd.randint(1, 60))
            val = date(ano + 1, 7, 31) if r >= 0.15 else dm + timedelta(days=rnd.randint(200, 330))
            if ano < ultimo:
                val = date(ano + 1, 7, 31)
            apto_r = rnd.random() < 0.05
            ias.append((m["re"], ano, f"IAS{ano % 100}{rnd.randint(10000, 99999)}", dm,
                        dm + timedelta(days=rnd.randint(0, 20)), val,
                        "APTO COM RESTRIÇÃO" if apto_r else "APTO", "APTO",
                        "INAPTO" if rnd.random() < .02 else "APTO", "APTO",
                        "IAS válida" if val >= HOJE else "IAS expirada", agora))
    ins(cur, "b1.ias_inspecao",
        ["re", "ano", "numero_processo", "data_inspecao_medica", "data_inspecao_odontologica",
         "data_validade", "inspecao_medica", "inspecao_odontologica", "parecer_medico_taf",
         "parecer_medico_tat", "situacao_inspecao", "atualizado_em"], ias)

    # TAF: aplicações semestrais; a última define a situação.
    taf, linha = [], 0
    lote = f"taf_ficticio.xlsx__{HOJE:%Y-%m-%d}_08-00-00"
    for m in efetivo:
        atraso = 420 if rnd.random() < 0.07 else 0  # ~7% com o último TAF vencido
        for k in range(rnd.randint(2, 4)):
            linha += 1
            d = HOJE - timedelta(days=180 * k + rnd.randint(0, 150) + atraso)
            r = rnd.random()
            if k == 0 and r < 0.10:
                taf.append((m["re"], "Pronto para Avaliação", "Convocado", "TAF 3", None, lote, linha))
            elif r < 0.06:
                taf.append((m["re"], "Finalizado", "Inapto", "TAF 3", d, lote, linha))
            elif r < 0.09:
                taf.append((m["re"], "Finalizado", "Ausente", "TAF 3", d, lote, linha))
            else:
                taf.append((m["re"], "Finalizado", "Apto", rnd.choice(["TAF 3"] * 9 + ["TAF 4 Coluna"]), d, lote, linha))
    ins(cur, "b1.taf_resultados_raw",
        ["re", "status", "resultado", "tipo_taf", "data_realizado", "lote_importacao", "linha_origem"], taf)

    # Promoções (alimentam a antiguidade): posto atual e o anterior.
    ANTERIOR = {"CB PM": "SD PM", "3. SGT PM": "CB PM", "2. SGT PM": "3. SGT PM", "1. SGT PM": "2. SGT PM",
                "SUBTEN PM": "1. SGT PM", "1. TEN PM": "2. TEN PM", "CAP PM": "1. TEN PM",
                "MAJ PM": "CAP PM", "TEN CEL PM": "MAJ PM"}
    promo = []
    for m in efetivo:
        pg = m["posto_grad"]
        d = HOJE - timedelta(days=rnd.randint(60, 2400))
        for p in (pg, ANTERIOR.get(pg)):
            if not p:
                break
            q, nivel, cod, sigla, *_ = POSTOS[p]
            promo.append((m["re"], nivel, cod, p, sigla, None,
                          "QUADRO DE PRACAS POLICIAIS MILITARES" if q == "QPPM" else "QUADRO DE OFICIAIS DA POLICIA MILITAR",
                          rnd.choice(["ANTIGUIDADE", "MERECIMENTO", "CONCURSO"]), max(d, m["data_admissao"]),
                          None, f"BOL G PM {rnd.randint(1, 240)}/{d.year}", None))
            d = d - timedelta(days=rnd.randint(900, 3000))
    ins(cur, "b1.promocoes",
        ["re", "nivel", "codigo_posto", "posto", "sigla_anterior", "codigo_quadro", "quadro", "tipo_promocao",
         "data_promocao", "data_quadro", "boletim", "doe"], promo)

    carregar_qpo(cur)

    # Quantitativo diário e snapshot (série dos últimos 100 dias, com leve oscilação).
    def lot_snap(m):
        return lotacao_de(m["cod"])
    base = {}
    for m in efetivo:
        k = (lot_snap(m), m["posto_grad"])
        base[k] = base.get(k, 0) + 1
    qd = []
    for d in range(100, -1, -1):
        dia = HOJE - timedelta(days=d)
        for (lot, pg), n in base.items():
            ajuste = rnd.choice([0, 0, 0, 0, 1, -1]) if d > 0 else 0
            qd.append((dia, lot, pg, max(0, n + ajuste * (d // 30))))
    ins(cur, "b1.efetivo_quantitativo_diario", ["data_referencia", "lotacao", "posto_grad", "quantidade"], qd)
    snap = []
    for d in [HOJE] + [date(HOJE.year, mes, 1) for mes in range(1, HOJE.month + 1)]:
        for m in efetivo:
            snap.append((d, m["re"], m["nome"], m["posto_grad"], m["quadro"], lot_snap(m), int(m["cod"]),
                         "11.GB", m["situacao"]))
    snap = list({(s[0], s[1]): s for s in snap}.values())
    ins(cur, "b1.efetivo_snapshot_mensal",
        ["data_referencia", "re", "nome", "posto_grad", "quadro", "lotacao", "cod_opm_atual", "opm_efetiva",
         "situacao"], snap)

    etl = []
    for dom, h in [("efetivo", 1), ("afastamentos", 1), ("ias", 1), ("restricoes", 1), ("taf", 30),
                   ("promocoes", 6), ("b4_viaturas", 2), ("b4_viaturas_siopm", 2), ("b3_nivel_operacional", 2),
                   ("mapa_forca", 0), ("ocorrencias", 60), ("tempo_resposta", 60), ("sjd", 3), ("uge", 3),
                   ("elogios", 2), ("backup", 10)]:
        ini = AGORA - timedelta(hours=h, minutes=rnd.randint(5, 50))
        etl.append((dom, ini, ini + timedelta(minutes=rnd.randint(1, 9)), "success",
                    rnd.randint(100, 5000), rnd.randint(0, 300), rnd.randint(0, 900)))
    ins(cur, "b1.etl_status",
        ["dominio", "iniciado_em", "finalizado_em", "status", "linhas_lidas", "linhas_inseridas",
         "linhas_atualizadas"], etl)


def carregar_qpo(cur):
    """QPO fictício no mesmo formato do importado do documento oficial."""
    f = []
    fonte, aba = "QPO fictício (demo)", "11GB"

    def v(lot, secao, sub, funcao, quadro, pg, cat, n, des=False, mun=None):
        f.append((lot, secao, sub, funcao, quadro, pg, cat, n, des, mun, None, aba, len(f) + 1, fonte))

    v("EM", "Comando", None, "Comandante", "QOPM", "Ten Cel PM", "Oficial", 1)
    v("EM", "Comando", None, "Subcomandante", "QOPM", "Maj PM", "Oficial", 1)
    v("EM", "Seção Adm", None, "Chefe", "QOPM", "Cap PM", "Oficial", 1)
    for sub, ten, sgt, cb in [("B/1 e B/5", 1, 3, 9), ("Agência de Área (AA)", 1, 1, 1),
                              ("B/3, PJMD e Motomec", 1, 4, 6), ("B/4", 1, 1, 3), ("St UGE", 0, 2, 2),
                              ("COBOM", 1, 6, 24)]:
        if ten:
            v("EM", "Seção Adm", sub, "Chefe", "QAOPM" if sub == "B/4" else "QOPM", "Ten PM", "Oficial", 1)
        v("EM", "Seção Adm", sub, "Auxiliar", "QPPM", "Subten/Sgt", "Praça", sgt)
        v("EM", "Seção Adm", sub, "Auxiliar", "QPPM", "Cb/Sd", "Praça", cb)
    v("EM", "Seção de Ativ Técnicas", None, "Chefe", "QOPM", "Cap PM", "Oficial", 1)
    v("EM", "Seção de Ativ Técnicas", "Vistorias", "Vistoriador", "QPPM", "Subten/Sgt", "Praça", 13)
    v("EM", "Seção de Ativ Técnicas", "Vistorias", "Auxiliar", "QPPM", "Cb/Sd", "Praça", 6)
    for s in "1234":
        lot = LOTACAO_SGB[s]
        v(lot, "Comando", None, "Comandante", "QOPM", "Cap PM", "Oficial", 1)
        v(lot, "Adm", None, "Auxiliar", "QPPM", "Subten/Sgt", "Praça", 2)
        v(lot, "Adm", None, "Auxiliar", "QPPM", "Cb/Sd", "Praça", 3)
        for e in [e for e in ESTACOES if e[0][5] == s]:
            pel = f"{e[0][6]}º PB"
            if e[0].endswith("01"):
                v(lot, pel, None, "Comandante de Pelotão", "QOPM", "Ten PM", "Oficial", 1)
            grande = e[3].startswith("PB")
            pequeno = e[3].startswith("BCom")
            v(lot, pel, e[3], "Chefe de Guarnição", "QPPM", "Subten/Sgt", "Praça",
              1 if pequeno else (6 if grande else 3), mun=e[4])
            v(lot, pel, e[3], "Guarnição", "QPPM", "Cb/Sd", "Praça",
              2 if pequeno else (22 if grande else 11), mun=e[4])
    ins(cur, "b1.qpo_funcoes",
        ["lotacao", "secao", "subsecao", "funcao", "quadro", "posto_grad", "categoria", "vagas", "a_designar",
         "municipio", "obs", "aba_origem", "linha_origem", "fonte"], f)
    agg = {}
    for lot, _s, _sub, _f, q, pg, cat, n, *_ in f:
        agg[(lot, q, pg, cat)] = agg.get((lot, q, pg, cat), 0) + n
    ins(cur, "b1.qpo_vagas", ["lotacao", "quadro", "posto_grad", "categoria", "vagas"],
        [(*k, n) for k, n in sorted(agg.items())])


# ==========================================
# B4 — FROTA E NÍVEL OPERACIONAL (SIOPM)
# ==========================================
TIPOS_VTR = [  # tipo, peso, (fabricante, modelo), combustível, programa SIOPM
    ("UR", 3, ("MERCEDES BENS", "SPRINTER"), "DIESEL", "RESGATE"),
    ("AB", 2, ("IVECO", "TECTOR ATTACK 170E22"), "DIESEL", "INCÊNDIO"),
    ("ABS", 2, ("FORD", "CARGO 1722-E"), "DIESEL", "INCÊNDIO"),
    ("AT", 1, ("VW", "17280 CRM 4X2"), "DIESEL", "INCÊNDIO"),
    ("VO", 4, ("TOYOTA", "YARIS SA XL15"), "FLEX", "VIATURA ORGÂNICA"),
    ("TP", 2, ("GM", "S-10"), "DIESEL", "TRANSPORTE PESSOAL"),
    ("AS", 1, ("RENAULT", "MASTER ENGE"), "DIESEL", "SALVAMENTO"),
    ("MOB", 1, ("HONDA", "XRE-300"), "GASOLINA", "MOTO OPERACIONAL DE BOMBEIRO"),
    ("UT", 1, ("FIAT", "DUCATO"), "DIESEL", "UTILITÁRIO"),
]


def gerar_frota():
    frota, contador = [], {}
    for cod, sgb, pb, nome, mun, *_ in ESTACOES:
        s = cod[5]
        n = 11 if nome.startswith("PB") else (6 if nome.startswith("BB") else 2)
        tipos = rnd.choices(TIPOS_VTR, weights=[t[1] for t in TIPOS_VTR], k=n)
        if nome.startswith("PB"):
            tipos[:3] = [TIPOS_VTR[0], TIPOS_VTR[1], TIPOS_VTR[4]]
        for t in tipos:
            contador[(t[0], s)] = contador.get((t[0], s), 0) + 1
            prefixo = f"{t[0]}-11{s}{contador[(t[0], s)]:02d}"
            ano = rnd.randint(2008, HOJE.year - 1)
            r = rnd.random()
            status = "OPERANDO" if r < 0.68 else ("BAIXADA" if r < 0.9 else "BAIXADA_DESCARGA")
            frota.append(dict(prefixo=prefixo, tipo=t[0], fab=t[2][0], modelo=t[2][1], comb=t[3], prog=t[4],
                              cod=cod, sgb=sgb, pb=pb, nome=nome, mun=mun, ano=ano, status=status))
    for i in range(1, 4):  # viaturas administrativas da sede, fora do SIOPM
        frota.append(dict(prefixo=f"VA-1100{i}", tipo="VA", fab="RENAULT", modelo="LOGAN EXPRESSION 1.6",
                          comb="FLEX", prog=None, cod=None, sgb="SEDE", pb="SEDE", nome="B4",
                          mun="SÃO JOSÉ DOS CAMPOS", ano=rnd.randint(2010, 2020), status="OPERANDO"))
    return frota


SIOPM_STATUS = {"OPERANDO": [("DISPONÍVEL", "O"), ("RESERVA", "R"), ("DISPONÍVEL", "O"), ("EM ATENDIMENTO", "O")],
                "BAIXADA": [("BAIXA(DEFEITO)", "B")], "BAIXADA_DESCARGA": [("PROC DESCARGA", "B")]}


def carregar_b4_b3(cur, efetivo, frota):
    execute_values(cur, "INSERT INTO b4.siopm_estacao (opm_cod, sgb, pb_bb, nome_estacao, municipio) VALUES %s",
                   [(e[0], e[1], e[2], e[3], e[4]) for e in ESTACOES])
    print(f"  {'b4.siopm_estacao':<34} {len(ESTACOES):>6}")

    # Captura do nível operacional (SIOPM) de hoje cedo e a de ontem.
    capturas = []
    for dt in (AGORA - timedelta(days=1, hours=2), AGORA - timedelta(hours=2)):
        cur.execute("""INSERT INTO b3.nivel_op_captura (capturado_em, estacoes_lidas, viaturas_lidas, viaturas_numreg)
                       VALUES (%s, %s, %s, %s) RETURNING id""", (dt, len(ESTACOES), 0, 0))
        capturas.append(cur.fetchone()[0])
    cap_id = capturas[-1]

    por_estacao = {}
    for m in efetivo:
        if m["cod"] in EST_POR_COD and m["posto_grad"] in PRACA_OP:
            por_estacao.setdefault(m["cod"], []).append(m)

    ordem_est = {}
    for v in frota:
        if not v["cod"]:
            continue
        st, grp = rnd.choice(SIOPM_STATUS[v["status"]])
        v["siopm_status"], v["siopm_grp"] = st, grp
        for cid in capturas:
            ordem_est[(cid, v["cod"])] = ordem_est.get((cid, v["cod"]), 0) + 1
            us = v["prefixo"].replace("-", "")
            integrantes = []
            if grp == "O" and cid == cap_id:
                pool = por_estacao.get(v["cod"], [])
                integrantes = rnd.sample(pool, min(len(pool), {"UR": 3, "AB": 4, "ABS": 3, "AT": 2}.get(v["tipo"], 1)))
            comp = " ".join([f"[{us}]"] + [
                f"[{POSTOS[m['posto_grad']][5]}_PM_{m['re']}_{m['guerra']}]" for m in integrantes])
            inicio = datetime.combine(HOJE if cid == cap_id else HOJE - timedelta(days=1), time(7, 30)) + \
                timedelta(minutes=rnd.randint(0, 40))
            cur.execute("""INSERT INTO b3.nivel_op_viatura (captura_id, opm_cod, estacao_nome, ordem, us, status,
                             status_grp, componente, programa, programa_cod, modalidade, operacao, inicio, termino,
                             exige_vtr, existe_vtr, cad_cod, ptrcpn_cod, viatura_prefixo, efetivo_qtd)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'RADIOPATRULHA','6',%s,'ATIV PREV OP TERRESTRE DIVERSA',
                                   %s,%s,'S','S','1','0',%s,%s) RETURNING id""",
                        (cid, v["cod"], v["nome"], ordem_est[(cid, v["cod"])], us, st, grp, comp, v["prog"],
                         inicio, inicio + timedelta(hours=24), us, len(integrantes)))
            vid = cur.fetchone()[0]
            for i, m in enumerate(integrantes, 1):
                bruto = f"{POSTOS[m['posto_grad']][5]}_PM_{m['re']}_{m['guerra']}"
                cur.execute("""INSERT INTO b3.nivel_op_integrante (viatura_id, ordem, posto, re, nome_guerra, bruto)
                               VALUES (%s,%s,%s,%s,%s,%s)""",
                            (vid, i, POSTOS[m["posto_grad"]][5], m["re"], m["guerra"], bruto))
            v.setdefault("integrantes", integrantes)
    cur.execute("""UPDATE b3.nivel_op_captura c SET viaturas_lidas = (SELECT count(*) FROM b3.nivel_op_viatura v
                   WHERE v.captura_id = c.id), viaturas_numreg = (SELECT count(*) FROM b3.nivel_op_viatura v
                   WHERE v.captura_id = c.id AND v.viatura_prefixo IS NOT NULL)""")
    cur.execute("SELECT count(*) FROM b3.nivel_op_viatura")
    print(f"  {'b3.nivel_op_viatura':<34} {cur.fetchone()[0]:>6}")

    lote = f"Viaturas_ficticias.xlsx__{HOJE:%Y-%m-%d}_06-00-00"
    linhas = []
    for i, v in enumerate(frota, 1):
        no_siopm = v["cod"] is not None
        linhas.append((v["prefixo"], "11.GB", v["sgb"], v["pb"], v["nome"], v["mun"], v["status"],
                       v["status"].replace("_", " ").replace("BAIXADA DESCARGA", "BAIXADA *"),
                       rnd.choices(["ESTADO", "PREFEITURA-INT", "LOCADA"], weights=[8, 2, 1])[0],
                       f"FIC{rnd.randint(1000, 9999)}", v["fab"], v["modelo"], v["tipo"], v["ano"], v["ano"] + 1,
                       v["comb"], None, None, None, None, None, None, lote, i,
                       "SIOPM" if no_siopm else "PLANILHA", "PLANILHA",
                       v["prefixo"].replace("-", "") if no_siopm else None, v.get("siopm_status"),
                       v["cod"], cap_id if no_siopm else None, AGORA - timedelta(hours=2) if no_siopm else None))
    ins(cur, "b4.viaturas",
        ["prefixo", "opmcb", "sgb", "pb_bb", "nome_estacao", "municipio", "status", "status_raw", "proprietario",
         "placa", "fabricante", "modelo", "tipo", "ano_fabricacao", "ano_modelo", "combustivel", "patrimonio",
         "patrimonio_estado", "chassi", "renavam", "riv", "obs", "lote_importacao", "linha_origem",
         "status_origem", "origem_cadastro", "siopm_us", "siopm_status", "siopm_opm_cod", "siopm_captura_id",
         "siopm_visto_em"], linhas)
    ins(cur, "b4.viaturas_sync_siopm", ["captura_id", "prefixo", "campo", "antes", "depois"],
        [(cap_id, v["prefixo"], "status", "OPERANDO", v["status"]) for v in frota
         if v["cod"] and v["status"] != "OPERANDO"][:25])
    carregar_mapa_forca(cur, efetivo, frota)


def carregar_mapa_forca(cur, efetivo, frota):
    """Mapa de força: um snapshot por dia nos últimos 15 dias (o de hoje alimenta a aba)."""
    oficiais = [m for m in efetivo if m["posto_grad"] in ("MAJ PM", "CAP PM")]
    n_est = n_lin = 0
    for d in range(14, -1, -1):
        dia = HOJE - timedelta(days=d)
        cap = datetime.combine(dia, time(7, 45)) if d else AGORA - timedelta(minutes=20)
        of = rnd.choice(oficiais)
        cab = f"OFICIAL SUPERIOR DE SERVIÇO:  {of['posto_grad']} {of['re']} {of['guerra']} {fone_ficticio(of['re'])}"
        payload = [[dia.strftime("%d/%m/%Y"), "M A P A   F O R Ç A   -   1 1 º  G R U P A M E N T O   D E   B O M B E I R O S"],
                   [cab]]
        cur.execute("""INSERT INTO b3.mapa_forca_snapshot_raw (fonte_planilha_id, fonte_aba, capturado_em, data_servico,
                         cabecalho_texto, conteudo_sha256, payload_raw) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    ("PLANILHA_FICTICIA", "Página1", cap, dia, cab,
                     hashlib.sha256(f"{dia}{rnd.random()}".encode()).hexdigest(), Json(payload)))
        sid = cur.fetchone()[0]
        ordem = 5
        for cod, sgb, pb, nome, mun, *_ in ESTACOES:
            bloco = SGB_ROTULO[cod[5]]
            nome_mf = nome
            agua = rnd.choice([0, 1500, 4000, 6000, 8000, 12000, 20000]) if not nome.startswith("BCom") else 0
            merg = rnd.choice([0, 0, 1, 1, 2])
            ordem += 1
            cur.execute("""INSERT INTO b3.mapa_forca_estacao (snapshot_id, bloco_nome, estacao_nome, estacao_codigo,
                             estacao_telefone, capacidade_agua_l, mergulhadores, ordem)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (sid, bloco, nome_mf, cod, f"0000-{int(cod[-4:]):04d}", agua, merg, ordem))
            eid = cur.fetchone()[0]
            n_est += 1
            for v in [v for v in frota if v["cod"] == cod]:
                ordem += 1
                if v["status"] != "OPERANDO":
                    sit, qtd, pg, mil = "BAIXADA", None, None, None
                elif rnd.random() < 0.55:
                    sit = "OPERANDO"
                    qtd = {"UR": 3, "AB": 4, "ABS": 3, "AT": 2}.get(v["tipo"], 2)
                    ch = (v.get("integrantes") or [rnd.choice(efetivo)])[0]
                    pg = POSTOS[ch["posto_grad"]][4]
                    # Acima: Mesmo formato da planilha real: nome de guerra e celular
                    mil = f"{ch['guerra']} {fone_ficticio(ch['re'])}"
                else:
                    sit, qtd, pg, mil = "RESERVA", 0, None, None
                cur.execute("""INSERT INTO b3.mapa_forca_linha (snapshot_id, bloco_nome, estacao_bombeiros, viatura,
                                 situacao, efetivo_qtd, posto_graduacao, militar_e_telefone, capacidade_agua_l,
                                 mergulhadores, ordem, estacao_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (sid, bloco, nome_mf, v["prefixo"], sit, qtd, pg, mil, None, None, ordem, eid))
                n_lin += 1
    print(f"  {'b3.mapa_forca_estacao':<34} {n_est:>6}")
    print(f"  {'b3.mapa_forca_linha':<34} {n_lin:>6}")


# ==========================================
# B3 — OCORRÊNCIAS, TEMPO-RESPOSTA, AUDITORIA COBOM, EAP
# ==========================================
RUAS = ["RUA DAS ACACIAS", "AV. DOS EXEMPLOS", "RUA PROJETADA UM", "RUA SETE", "ESTRADA MUNICIPAL",
        "AV. CENTRAL", "RUA DO COMERCIO", "RUA DAS PALMEIRAS", "RODOVIA ESTADUAL KM 12"]
RESUMOS = {"N": "Vítima com mal súbito em via pública, consciente e orientada.",
           "L": "Colisão entre automóvel e motocicleta, uma vítima com escoriações.",
           "M": "Solicitante relata animal em residência, sem vítimas.",
           "E": "Fogo em vegetação às margens da via, sem risco a edificações.",
           "A": "Princípio de incêndio em residência, extinto pela guarnição.",
           "J": "Ocorrência resolvida antes da chegada da viatura."}

NATUREZAS = [  # natcod, peso, natureza do tempo-resposta
    ("N01", 18, "15-Emergência clínica"), ("L08", 16, "12-Acidente de trânsito"),
    ("M15", 13, "9-Ocorrência envolvendo animal ou inseto"), ("M01", 9, "8-Ocorrência com árvore"),
    ("N26", 6, "14-Acidente pessoal"), ("N12", 6, "14-Acidente pessoal"), ("L12", 5, "12-Acidente de trânsito"),
    ("E07", 4, "2-Incêndio Área de risco"), ("M04", 4, "9-Ocorrência envolvendo animal ou inseto"),
    ("A23", 2, "1-Incêndio Em edificação"), ("A05", 1, "1-Incêndio Em edificação"),
    ("J09", 1, "0-Sem Intervenção-Resolvido por populares"),
]
PESO_SGB = {"1": 31, "2": 23, "3": 29, "4": 17}


def carregar_ocorrencias(cur):
    oc, tr = [], []
    ini = date(HOJE.year - 2, 1, 1)
    fim_tr = date(HOJE.year - 1, 12, 15)
    num = 100000
    est_sgb = {s: [e for e in ESTACOES if e[0][5] == s] for s in "1234"}
    d = ini
    while d < HOJE - timedelta(days=1):
        sazonal = 1.25 if d.month in (8, 9) else (1.1 if d.month in (12, 1) else 1.0)
        for _ in range(int(rnd.gauss(9, 2) * sazonal)):
            num += 1
            s = rnd.choices("1234", weights=[PESO_SGB[k] for k in "1234"])[0]
            e = rnd.choice(est_sgb[s])
            nat = rnd.choices(NATUREZAS, weights=[n[1] for n in NATUREZAS])[0]
            cham = datetime.combine(d, time(rnd.randint(0, 23), rnd.randint(0, 59)))
            atend = max(0.3, rnd.lognormvariate(1.1, 0.45))
            ger = cham + timedelta(minutes=atend)
            fin = ger + timedelta(minutes=rnd.lognormvariate(5.5, 1.0))
            oc.append((num, num, d, 5, 5, 1, rnd.choice([2, 9, 12, 14, 15]), nat[0], cham, ger, fin, fin,
                       round(atend, 2), f"{s}.SGB", "11.GB", int(e[0]), int(e[0]), rnd.choice(RUAS),
                       str(rnd.randint(10, 2000)), e[4].title(), e[5], RESUMOS[nat[0][0]],
                       round(e[7] + rnd.uniform(-.04, .04), 7), round(e[6] + rnd.uniform(-.04, .04), 7),
                       f"ficticio_{d.year}.xlsx"))
            if d <= fim_tr and rnd.random() < 0.9:
                prefixo = rnd.choice(["UR", "AB", "ABS", "VO"]) + f"11{s}{rnd.randint(1, 9):02d}"
                tr.append((num, prefixo, cham, num, e[4].title(), None, nat[2], SGB_ROTULO[s],
                           round(atend, 4), round(max(0.5, rnd.lognormvariate(1.9, 0.6)), 4),
                           round(max(1.0, rnd.lognormvariate(2.3, 0.55)), 4), f"sdov_ficticio_{d.year}.xlsx"))
        d += timedelta(days=1)
    ins(cur, "b3.ocorrencias",
        ["id", "ocrnum", "ocrdat", "statusid", "cadcod", "situacaoid", "atendimentotipoid", "natcod", "dt_chamada",
         "dt_geracao", "dt_finalizacao", "dt_homologacao", "despacho_min", "sgb", "gb", "opm_fato",
         "opm_atendimento", "logradouro_inicial", "numero_inicial", "bairro_inicial", "municipio_inicial",
         "dados_complementares", "lon_inicial", "lat_inicial",
         "lote_importacao"], oc, page_size=2000)
    ins(cur, "b3.tempo_resposta",
        ["id_sdov", "viatura", "dt_ocorrencia", "num_ocorrencia", "municipio", "bairro", "natureza", "sgb",
         "t_atendimento_min", "t_despacho_min", "t_deslocamento_min", "lote_importacao"], tr, page_size=2000)


def carregar_auditoria(cur, efetivo, uid_avaliador):
    sys.path.insert(0, os.path.join(RAIZ, "webapp"))
    itens = [("abertura", 5, False), ("tempo", 5, False), ("abreviaturas", 5, False), ("dados", 10, False),
             ("historico", 20, False), ("encerramento", 5, False), ("orientacao", 20, False),
             ("cordialidade", 10, False), ("objetividade", 10, False), ("imparcialidade", 10, False),
             ("despacho", 50, True), ("normas", 100, True), ("imagem", 100, True), ("auto_impacto", 100, True)]
    cobom = [m for m in efetivo if m["cod"] == "990119131"]
    fichas = []
    for i in range(48):
        m = rnd.choice(cobom)
        resp, nota = {}, 0
        for chave, peso, grave in itens:
            ok = rnd.random() > (0.03 if grave else 0.12)
            resp[chave] = {"conforme": ok, "obs": None if ok else "Orientado na devolutiva."}
            nota += (-peso if not ok else 0) if grave else (peso if ok else 0)
        nota = max(nota, 0)
        parecer = "APROVADO" if nota >= 90 else ("APROVADO COM ORIENTAÇÕES" if nota >= 70 else "REPROVADO")
        dia = HOJE - timedelta(days=rnd.randint(1, 120))
        fichas.append((m["re"], m["posto_grad"], m["nome"], f"INF {rnd.randint(1, 300)}/{dia.year}", dia,
                       rnd.choice(["07h30 às 19h30", "19h30 às 07h30"]), rnd.choice("ABCD"),
                       f"PA {rnd.randint(1, 8)}", "Avaliador Fictício 1", "Avaliador Fictício 2",
                       Json([{"tma": None, "data": str(dia), "audio": str(rnd.randint(10**6, 10**8)),
                              "ocorrencia": None}]), Json(resp), nota, parecer, None, None, None, None,
                       uid_avaliador, uid_avaliador))
    ins(cur, "b3.auditoria_cobom",
        ["re", "posto_grad", "nome", "informacao_num", "data_servico", "turno", "equipe", "posto_atendimento",
         "avaliador_1", "avaliador_2", "audios", "respostas", "nota", "parecer", "observacoes",
         "prov_encarregado", "prov_chefe", "prov_supervisao", "criado_por", "atualizado_por"], fichas)


def carregar_eap(cur, efetivo):
    ano = HOJE.year
    turmas = [
        (ano, HOJE + timedelta(days=4), HOJE + timedelta(days=22), datetime.combine(HOJE + timedelta(days=25), time(8)),
         "EB Fictícia Centro - Rua Exemplo, 100", 30, [{"turma": "XIV", "publico": "Subten/Sgt"},
                                                      {"turma": "XIV", "publico": "Cb/Sd"}]),
        (ano, HOJE + timedelta(days=25), HOJE + timedelta(days=43), datetime.combine(HOJE + timedelta(days=48), time(8)),
         "Ginásio Municipal Fictício - Av. Modelo, 500", 40, [{"turma": "XV", "publico": "Subten/Sgt"},
                                                             {"turma": "XV", "publico": "Cb/Sd"}]),
    ]
    ids = []
    for t in turmas:
        cur.execute("""INSERT INTO b3.eap_turma (ano, ead_inicio, ead_fim, presencial_em, presencial_local, vagas,
                         publicos, criado_por) VALUES (%s,%s,%s,%s,%s,%s,%s,'seed') RETURNING id""",
                    (*t[:6], Json(t[6])))
        ids.append(cur.fetchone()[0])
    pracas = [m for m in efetivo if m["posto_grad"] in PRACA_OP]
    insc = [(ids[0], m["re"], rnd.random() < .7, None, "seed") for m in rnd.sample(pracas, 26)]
    insc += [(ids[1], m["re"], False, None, "seed") for m in rnd.sample(pracas, 18) if (ids[0], m["re"]) not in {(a, b) for a, b, *_ in insc}]
    ins(cur, "b3.eap_inscricao", ["turma_id", "re", "escalado", "observacao", "criado_por"], insc)
    # Acima: Dispensa por CAO só existe para Capitão (regra de eap.py).
    ins(cur, "b3.eap_dispensa", ["re", "motivo", "criado_por"],
        [(m["re"], "CAO", "seed") for m in efetivo if m["posto_grad"] == "CAP PM"][:2])


# ==========================================
# B5, UGE, SJD, B.I.A. E USUÁRIOS
# ==========================================
def carregar_b5(cur, efetivo):
    TIPOS = [("ELO", "ELOGIO SEI", 60), ("ELO", "ELOGIO", 10), ("LOU", "LOUVOR", 9), ("LMP", "LMP 3º GRAU", 5),
             ("LMP", "LMP 2º GRAU", 4), ("LMP", "LMP 1º GRAU", 2), ("ELO", "ELOGIO PM DO MÊS", 1)]
    el = []
    ini = HOJE - timedelta(days=440)
    for i in range(1050):
        m = rnd.choice(efetivo)
        tipo, assunto, _ = rnd.choices(TIPOS, weights=[t[2] for t in TIPOS])[0]
        d = ini + timedelta(days=rnd.randint(0, 438))
        lanc = d + timedelta(days=rnd.randint(3, 40))
        if lanc > HOJE:
            lanc = HOJE
        s = m["cod"][5]
        sgb = f"{s}° SGB" if s in "1234" else "SEDE"
        el.append((rnd.randint(100, 2000), rnd.randint(1, 45), m["posto_grad"], f"{m['re']}-{m['re_dv']}",
                   m["nome"], assunto, tipo, d, sgb, lanc, "Lançador Fictício", None, None, None,
                   f"BI {rnd.randint(1, 45)}/{lanc.year}", f"{lanc.month}/{lanc.year}", lanc.year))
    ins(cur, "b5.elogios",
        ["nbi", "num_bi_11gb", "posto_grad", "re", "nome", "assunto", "tipo", "data_elogio", "sgb",
         "data_lancamento", "lancador", "solenidade", "observacoes", "data_base", "boletim", "mes_ano", "ano"], el)


def carregar_uge(cur):
    OBJ = [("AQUISIÇÃO DE MANGUEIRAS DE INCÊNDIO", "449052"), ("EPI PARA COMBATE A INCÊNDIO", "339030"),
           ("MANUTENÇÃO DE VIATURAS", "339039"), ("BALSAS INFLÁVEIS", "449052"), ("MATERIAL DE EXPEDIENTE", "339030"),
           ("CONJUNTOS AUTÔNOMOS DE AR", "449052"), ("PNEUS PARA VIATURAS", "339030"),
           ("TORRES DE ILUMINAÇÃO", "449052"), ("UNIFORMES OPERACIONAIS", "339030"), ("COMBUSTÍVEL", "339030"),
           ("CORDAS E MATERIAL DE SALVAMENTO", "449052"), ("PUBLICAÇÃO EM JORNAL", "339039")]
    proc = []
    for i in range(1, 25):
        objeto, classe = rnd.choice(OBJ)
        valor = round(rnd.uniform(800, 900000), 2)
        ent = HOJE + timedelta(days=rnd.randint(-60, 120))
        status = rnd.choices(["ANDAMENTO", "ENCERRADO", "CANCELADO"], weights=[14, 8, 1])[0]
        liquid = valor if status == "ENCERRADO" else None
        proc.append((i, f"000.{rnd.randint(10**7, 10**8 - 1):08d}/{HOJE.year}-{rnd.randint(10, 99)}",
                     f"{HOJE.year}{rnd.randint(10**6, 10**7 - 1)}", rnd.choice(["ARP", "PREGÃO", "DISPENSA"]),
                     rnd.choice(["11º GB", "1º SGB", "2º SGB", "3º SGB", "4º SGB", "SAT"]), objeto, classe,
                     "180512", rnd.choice(["S", "P"]), "150010001", str(rnd.randint(1, 30)), valor, ent,
                     liquid, None, rnd.choice(["Cb Fulano", "Cb Beltrano", "Ten Sicrano"]), status, HOJE.year,
                     # Acima: A pendência cita o apelido de quem deve agir; é o que alimenta
                     # "minhas pendências" de cada usuário (ver uge.py).
                     (f"{rnd.choice(['Cb Duarte', 'Maj Moura'])}: cobrar nota fiscal do fornecedor"
                      if status == "ANDAMENTO" and ent < HOJE + timedelta(days=10) else None)))
    ins(cur, "uge.processos",
        ["numero", "processo_sei", "processo_siafem", "licitacao", "solicitante", "objeto", "classe", "ptres",
         "nd", "fonte", "ne", "valor_empenhado", "entrega_empenhada", "valor_liquidado", "observacoes",
         "responsavel", "status", "ano", "pendencia"], proc)


def carregar_sjd(cur):
    TIT = ["Atraso ao serviço", "Trabalhar mal", "Deixar de tomar providências", "Acidente com viatura",
           "Extravio de material", "Faltar ao serviço", "Desrespeito a superior", "Uso indevido de viatura"]
    pr = []
    for i in range(38):
        d = HOJE - timedelta(days=rnd.randint(10, 1500))
        fin = rnd.random() < 0.6
        tipo = rnd.choice(["Sindicância", "PD", "PD", "Inv Preliminar", "IPM"])
        pr.append((d, rnd.choice(TIT), tipo,
                   "Militar fictício", rnd.choice(["1° SGB", "2° SGB", "3° SGB", "4° SGB", "COBOM"]),
                   rnd.choice(["Repreensão", "Repreensão", "Permanência", "Inexistência"]) if fin and tipo == "PD" else None,
                   "Finalizado" if fin else "Andamento", hashlib.sha256(f"sjd{i}".encode()).hexdigest(),
                   "sjd_ficticio.xlsx"))
    ins(cur, "sjd.processos", ["data_abertura", "titulo", "tipo", "interessado", "unidade", "punicao",
                               "finalizado", "conteudo_sha256", "origem_arquivo"], pr)
    ind = []
    for ano in (HOJE.year - 1, HOJE.year):
        for mes in range(1, 13):
            if date(ano, mes, 1) > HOJE:
                break
            ind += [("reclamacoes_denuncias", ano, mes, rnd.randint(0, 4)),
                    ("acidentes_folga_bombeiro", ano, mes, rnd.randint(0, 2)),
                    ("acidentes_viatura_vitima", ano, mes, rnd.choice([0, 0, 0, 1]))]
    ins(cur, "sjd.indicadores_mensais", ["indicador", "ano", "mes", "valor"], ind)


def carregar_app(cur, senha):
    from passlib.context import CryptContext
    h = CryptContext(schemes=["bcrypt"]).hash(senha)
    usuarios = [  # (nome, matrícula, perfil, seção, apelido)
        ("RAFAEL DUARTE LIMA", "900003", "admin", None, "Cb Duarte"),
        ("RICARDO MOURA LACERDA", "900002", "oficial", None, "Maj Moura"),
        ("HENRIQUE PRATES GODOY", "900004", "oficial", None, "Cap Prates"),
        ("Usuário B/1 (demo)", "demo.b1", "praca", "B/1 e B/5", None),
        ("Usuário B/4 (demo)", "demo.b4", "praca", "B/4", None),
    ]
    ids = {}
    for nome, mat, perfil, secao, apelido in usuarios:
        cur.execute("""INSERT INTO app.usuarios (nome, matricula, senha_hash, perfil, ativo, apelido_assinatura,
                         deve_trocar_senha, secao) VALUES (%s,%s,%s,%s,true,%s,false,%s) RETURNING id""",
                    (nome, mat, h, perfil, apelido, secao))
        ids[mat] = cur.fetchone()[0]
    print(f"  {'app.usuarios':<34} {len(usuarios):>6}")
    ins(cur, "bia.contatos_autorizados", ["telefone", "re", "posto_abrev", "nome_curto", "apelido", "papel"], [
        ("5511900000010", 900001, "TEN CEL PM", "Bragança", "Cmt Bragança", "Cmt Geral"),
        ("5511900000011", 900002, "MAJ PM", "Moura", "Maj Moura", "Subcmt"),
        ("5511900000012", 900004, "CAP PM", "Prates", "Cap Prates", "Oficial"),
        ("5511900000001", 900003, "CB PM", "Duarte", "Cb Duarte", "Praca"),
    ])
    return ids


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recriar", action="store_true", help="apaga e recria os schemas antes da carga")
    ap.add_argument("--senha", default=opcional("DEMO_SENHA", "demo1234"),
                    help="senha dos usuários de teste (padrão: demo1234 ou $DEMO_SENHA)")
    a = ap.parse_args()

    con = conectar()
    con.autocommit = False
    cur = con.cursor()
    checar_banco_demo(cur)
    marcar_banco_demo(cur)
    cur.execute("SELECT to_regclass('b1.efetivo') IS NULL")
    if a.recriar or cur.fetchone()[0]:
        print("Recriando schemas a partir de db/demo/schema.sql ...")
        recriar(cur)
    cur.execute("SELECT count(*) FROM b1.efetivo")
    if cur.fetchone()[0]:
        sys.exit("b1.efetivo já tem linhas. Rode com --recriar para zerar e carregar de novo.")

    print(f"Gerando dados fictícios (semente {SEMENTE}, referência {HOJE:%d/%m/%Y}) ...")
    efetivo = gerar_efetivo()
    frota = gerar_frota()
    ids = carregar_app(cur, a.senha)
    carregar_b1(cur, efetivo)
    carregar_b4_b3(cur, efetivo, frota)
    carregar_ocorrencias(cur)
    carregar_auditoria(cur, efetivo, ids["900002"])
    carregar_eap(cur, efetivo)
    carregar_b5(cur, efetivo)
    carregar_uge(cur)
    carregar_sjd(cur)
    con.commit()
    print(f"\nPronto: {len(efetivo)} militares e {len(frota)} viaturas fictícios.")
    print("Login no painel: matrícula 900003 (admin) ou 900002 (oficial), senha", a.senha)


if __name__ == "__main__":
    main()
