"""
Gerador do Relatório Comparativo entre Unidades — 11º GB (PPTX).

Complementa o `gerar_semestre_comparativo.py`:
    - O outro: unidade fixa, mostra evolução no tempo (Q1 → Q2 → S1)
    - Este:   período fixo, compara as 5 unidades lado a lado

Estrutura (~9 slides):
    Capa
    Sumário Executivo (foto do S1)
    ── 1º Trimestre
        Comparativo geral (5 unidades × 8 KPIs)
    ── 2º Trimestre
        Comparativo geral
    ── Consolidado 1º Semestre
        Comparativo consolidado (com Δ e destaque melhor/pior)
    Fechamento

Uso:
    python gerar_comparativo_unidades.py 2026 1    → S1 (Q1+Q2)
    python gerar_comparativo_unidades.py 2026 2    → S2 (Q3+Q4)
"""

import sys, os, re
from datetime import date
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dados import carregar_tudo

# ==========================================================================
# PALETA / TIPOGRAFIA / LAYOUT
# ==========================================================================

COR_ACENTO       = RGBColor(0xB2, 0x22, 0x22)
COR_ACENTO_CLARO = RGBColor(0xE8, 0xB0, 0xB0)
COR_TEXTO        = RGBColor(0x1F, 0x23, 0x28)
COR_TEXTO_DIM    = RGBColor(0x6E, 0x77, 0x81)
COR_TEXTO_MUTED  = RGBColor(0x8B, 0x94, 0x9E)
COR_BG           = RGBColor(0xFF, 0xFF, 0xFF)
COR_BG_SUAVE     = RGBColor(0xF6, 0xF8, 0xFA)
COR_LINHA        = RGBColor(0xD0, 0xD7, 0xDE)
COR_BOM          = RGBColor(0x1F, 0x88, 0x3D)
COR_ATENCAO      = RGBColor(0xBF, 0x83, 0x00)
COR_CRITICO      = RGBColor(0xCF, 0x22, 0x2E)
COR_INDISP       = RGBColor(0xB0, 0xB0, 0xB0)
COR_MELHOR_BG    = RGBColor(0xE8, 0xF5, 0xEC)   # verde bem suave — destaque melhor
COR_PIOR_BG      = RGBColor(0xFB, 0xEA, 0xEA)   # vermelho bem suave — destaque pior

FONT_TITULO = "Cambria"
FONT_CORPO  = "Calibri"
FONT_DADOS  = "Consolas"

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN  = Inches(0.5)


# ==========================================================================
# HELPERS: normalização, shapes, tabelas
# ==========================================================================

def norm_sgb(s):
    if not s:
        return None
    s = str(s).upper().replace("°", "º").strip()
    if "SEDE" in s or s == "EM":
        return "EM"
    m = re.match(r"(\d)\s*º?\s*S?GB", s)
    return f"{m.group(1)}_SGB" if m else s


def buscar_por_sgb(lista, chave, campo="lotacao"):
    for it in lista or []:
        if norm_sgb(it.get(campo)) == chave:
            return it
    return None


def _blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def add_text(slide, x, y, w, h, texto, *, font=FONT_CORPO, size=14,
             bold=False, color=COR_TEXTO, align=PP_ALIGN.LEFT,
             anchor=MSO_ANCHOR.TOP, italic=False):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.margin_left = tf.margin_right = Emu(0)
    tf.margin_top = tf.margin_bottom = Emu(0)
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, line in enumerate(str(texto).split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = 1.15
        r = p.add_run()
        r.text = line
        r.font.name = font
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.italic = italic
        r.font.color.rgb = color
    return box


def add_rect(slide, x, y, w, h, *, fill=COR_BG_SUAVE, line=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shp.fill.solid(); shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(0.5)
    shp.shadow.inherit = False
    return shp


def add_eyebrow(slide, x, y, numero, texto):
    add_text(slide, x, y, Inches(11), Inches(0.28),
             f"{numero}   {texto}",
             font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y + Inches(0.30),
                                    Inches(0.8), Emu(15000))
    line.fill.solid(); line.fill.fore_color.rgb = COR_ACENTO
    line.line.fill.background()


def add_titulo_slide(slide, texto, size=28):
    add_text(slide, MARGIN, Inches(0.9), SLIDE_W - 2 * MARGIN, Inches(0.85),
             texto, font=FONT_TITULO, size=size, color=COR_TEXTO)


def add_footer(slide, texto):
    add_text(slide, MARGIN, SLIDE_H - Inches(0.35),
             SLIDE_W - 2 * MARGIN, Inches(0.25),
             texto, font=FONT_CORPO, size=9, color=COR_TEXTO_MUTED)


def add_bignum(slide, x, y, w, h, valor, unidade, label, cor=None):
    add_rect(slide, x, y, w, h, fill=COR_BG_SUAVE)
    cor_valor = cor or COR_ACENTO
    pad_x = Inches(0.25); pad_top = Inches(0.15); pad_bot = Inches(0.12)
    label_h = Inches(0.28); unidade_h = Inches(0.24) if unidade else Inches(0)
    gap = Inches(0.05)
    valor_h = h - label_h - unidade_h - pad_top - pad_bot - gap * (2 if unidade else 1)
    emu_per_inch = 914400
    h_emu = int(valor_h) if not hasattr(valor_h, 'emu') else valor_h.emu
    h_in = h_emu / emu_per_inch
    fs = 22 if h_in < 0.55 else 28 if h_in < 0.75 else 34 if h_in < 0.95 else 40 if h_in < 1.15 else 46
    y_cursor = y + pad_top
    add_text(slide, x + pad_x, y_cursor, w - 2 * pad_x, valor_h,
             str(valor), font=FONT_TITULO, size=fs, color=cor_valor,
             anchor=MSO_ANCHOR.MIDDLE)
    y_cursor += valor_h + gap
    if unidade:
        add_text(slide, x + pad_x, y_cursor, w - 2 * pad_x, unidade_h,
                 unidade, font=FONT_CORPO, size=11, color=COR_TEXTO_DIM)
    add_text(slide, x + pad_x, y + h - pad_bot - label_h,
             w - 2 * pad_x, label_h,
             label.upper(), font=FONT_CORPO, size=9, bold=True,
             color=COR_TEXTO_MUTED)


def add_tabela_destacada(slide, x, y, w, cabecalhos, linhas,
                          largura_col=None, melhores=None, piores=None):
    """Tabela com destaque opcional em células (índice em melhores/piores)."""
    n_col = len(cabecalhos); n_row = len(linhas) + 1
    altura = Inches(0.35 * n_row)
    table = slide.shapes.add_table(n_row, n_col, x, y, w, altura).table
    if largura_col:
        for i, lc in enumerate(largura_col):
            table.columns[i].width = lc

    # Cabeçalho
    for j, hh in enumerate(cabecalhos):
        cell = table.cell(0, j)
        cell.fill.solid(); cell.fill.fore_color.rgb = COR_BG_SUAVE
        cell.text_frame.text = str(hh)
        for p in cell.text_frame.paragraphs:
            for r in p.runs:
                r.font.name = FONT_CORPO; r.font.size = Pt(10)
                r.font.bold = True; r.font.color.rgb = COR_TEXTO_MUTED

    # Linhas
    for i, linha in enumerate(linhas, start=1):
        for j, valor in enumerate(linha):
            cell = table.cell(i, j)

            # Determina cor de fundo (destaque melhor/pior)
            fill = COR_BG
            if melhores and (i - 1, j) in melhores:
                fill = COR_MELHOR_BG
            elif piores and (i - 1, j) in piores:
                fill = COR_PIOR_BG
            cell.fill.solid(); cell.fill.fore_color.rgb = fill

            cell.text_frame.text = str(valor)
            for p in cell.text_frame.paragraphs:
                for r in p.runs:
                    r.font.name = FONT_DADOS if j > 0 else FONT_CORPO
                    r.font.size = Pt(11); r.font.color.rgb = COR_TEXTO


# ==========================================================================
# CLASSIFICAÇÃO (identifica melhor/pior por KPI entre unidades)
# ==========================================================================

def classificar(valores, sentido):
    """Retorna (idx_melhor, idx_pior) dentre valores numéricos, ignorando None.
       sentido: 'maior_melhor' ou 'menor_melhor'
       Retorna (None, None) se não houver valores."""
    validos = [(i, float(v)) for i, v in enumerate(valores)
               if v is not None and v != "—"]
    if not validos:
        return None, None
    if sentido == "maior_melhor":
        melhor = max(validos, key=lambda t: t[1])[0]
        pior   = min(validos, key=lambda t: t[1])[0]
    else:  # menor_melhor
        melhor = min(validos, key=lambda t: t[1])[0]
        pior   = max(validos, key=lambda t: t[1])[0]
    return melhor, pior


# ==========================================================================
# EXTRAÇÃO DE KPIs POR UNIDADE
# ==========================================================================

def kpis_unidade(dados, chave):
    ef_op = buscar_por_sgb(dados["efetivo"]["operacional_por_sgb"], chave, "lotacao")
    ab    = buscar_por_sgb(dados["absenteismo"]["por_sgb"], chave, "lotacao")
    el    = buscar_por_sgb(dados["elogios"]["por_sgb"], chave, "sgb")
    mm    = buscar_por_sgb(dados["motomec"]["por_sgb"], chave, "sgb")

    return {
        "total":           ef_op["total"] if ef_op else None,
        "op_pct":          ef_op["pct"] if ef_op else None,
        "lts_pct":         ab["pct"] if ab else 0,
        "em_lts":          ab["em_lts"] if ab else 0,
        "elogios":         el["elogios"] if el else 0,
        "lmp":             el["lmp"] if el else 0,
        "vtr_total":       mm["total"] if mm else None,
        "vtr_operando":    mm["operando"] if mm else None,
        "vtr_baixadas":    mm["baixada"] if mm else None,
        "pct_baixadas":    mm["pct_baixadas"] if mm else None,
        "idade":           mm["idade_media"] if mm else None,
    }


UNIDADES = [
    ("EM",    "Sede"),
    ("1_SGB", "1º SGB"),
    ("2_SGB", "2º SGB"),
    ("3_SGB", "3º SGB"),
    ("4_SGB", "4º SGB"),
]


# ==========================================================================
# SLIDES
# ==========================================================================

def slide_capa(prs, ano, num_sem):
    slide = _blank(prs)
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.5), SLIDE_H)
    bar.fill.solid(); bar.fill.fore_color.rgb = COR_ACENTO
    bar.line.fill.background()

    add_text(slide, Inches(1.2), Inches(2.0), Inches(11), Inches(0.4),
             "11º GRUPAMENTO DE BOMBEIROS  ·  PMESP",
             font=FONT_CORPO, size=13, bold=True, color=COR_TEXTO_MUTED)
    add_text(slide, Inches(1.2), Inches(2.5), Inches(11), Inches(1.4),
             "Relatório Comparativo",
             font=FONT_TITULO, size=58, color=COR_TEXTO)
    add_text(slide, Inches(1.2), Inches(4.0), Inches(11), Inches(0.7),
             f"Unidades — {num_sem}º Semestre de {ano}",
             font=FONT_TITULO, size=38, italic=True, color=COR_ACENTO)
    add_text(slide, Inches(1.2), Inches(4.9), Inches(11), Inches(0.4),
             "Sede e 4 SGBs lado a lado — Q1, Q2 e consolidado do semestre",
             font=FONT_CORPO, size=15, color=COR_TEXTO_DIM)
    add_text(slide, Inches(1.2), Inches(6.5), Inches(11), Inches(0.4),
             f"Vale do Paraíba  ·  Litoral Norte  ·  emitido em {date.today().strftime('%d/%m/%Y')}",
             font=FONT_CORPO, size=11, color=COR_TEXTO_MUTED)


def slide_sumario(prs, dados_s, n, num_sem):
    slide = _blank(prs)
    p = dados_s["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}",
                f"SUMÁRIO EXECUTIVO  ·  {p['label_curto']}")
    add_titulo_slide(slide, f"Foto consolidada do {num_sem}º semestre de {p['ano']}.")

    ef = dados_s["efetivo"]; ab = dados_s["absenteismo"]
    te = dados_s["territorio"]; el = dados_s["elogios"]; mm = dados_s["motomec"]

    card_w = Inches(4.0); card_h = Inches(1.7); gap = Inches(0.15)
    x0, x1, x2 = MARGIN, MARGIN + card_w + gap, MARGIN + 2 * (card_w + gap)

    add_bignum(slide, x0, Inches(1.9), card_w, card_h,
               ef["total_ativos"], "militares ativos", "Efetivo total")
    add_bignum(slide, x1, Inches(1.9), card_w, card_h,
               f"{ef['operacional_geral']['pct']}%", "operacional",
               "Efetivo empregado")
    add_bignum(slide, x2, Inches(1.9), card_w, card_h,
               f"{ab['geral']['pct']}%", "em LTS no semestre", "Absenteísmo")
    add_bignum(slide, x0, Inches(3.85), card_w, card_h,
               f"{te['atendidos']}/{te['total_municipios']}", f"{te['pct']}%",
               "Cobertura territorial")
    add_bignum(slide, x1, Inches(3.85), card_w, card_h,
               el["geral"]["total"], "reconhecimentos", "Elogios + LMP + LOU")
    add_bignum(slide, x2, Inches(3.85), card_w, card_h,
               f"{mm['geral']['pct_baixadas']}%", f"{mm['geral']['baixada']} viaturas",
               "Taxa de baixadas")

    add_text(slide, MARGIN, Inches(6.0), SLIDE_W - 2 * MARGIN, Inches(0.9),
             "Nas próximas páginas: mesmos KPIs, mas comparando Sede e 4 SGBs entre si — para cada trimestre e o consolidado.",
             font=FONT_CORPO, size=11, italic=True, color=COR_TEXTO_MUTED)
    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_divisor(prs, titulo, subtitulo):
    slide = _blank(prs)
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = COR_TEXTO
    bg.line.fill.background()
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.5), SLIDE_H)
    bar.fill.solid(); bar.fill.fore_color.rgb = COR_ACENTO
    bar.line.fill.background()

    add_text(slide, Inches(1.2), Inches(3.0), Inches(11), Inches(0.5),
             "PERÍODO", font=FONT_CORPO, size=14, bold=True, color=COR_ACENTO_CLARO)
    add_text(slide, Inches(1.2), Inches(3.5), Inches(11), Inches(1.5),
             titulo, font=FONT_TITULO, size=54, color=COR_BG)
    add_text(slide, Inches(1.2), Inches(5.0), Inches(11), Inches(0.5),
             subtitulo, font=FONT_TITULO, size=22, italic=True, color=COR_ACENTO_CLARO)


def slide_comparativo_periodo(prs, dados_periodo, n, com_delta=False, dados_anterior=None):
    """Slide comparando as 5 unidades em UM período específico.
       Se com_delta=True e dados_anterior fornecido, mostra Δ vs período anterior."""
    slide = _blank(prs)
    p = dados_periodo["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}",
                f"COMPARATIVO ENTRE UNIDADES  ·  {p['label_curto']}")
    add_titulo_slide(slide, f"Sede e SGBs em {p['label_longo']}.")

    # Coleta KPIs de cada unidade
    dados_unidades = {chave: kpis_unidade(dados_periodo, chave) for chave, _ in UNIDADES}

    # Definição das linhas da tabela: (label, campo, sentido, fmt)
    especs = [
        ("Efetivo ativo",           "total",         "maior_melhor", "{}"),
        ("% empregado operacional", "op_pct",        "maior_melhor", "{}%"),
        ("% absenteísmo LTS",       "lts_pct",       "menor_melhor", "{}%"),
        ("Elogios (ELO)",           "elogios",       "maior_melhor", "{}"),
        ("LMP",                     "lmp",           "maior_melhor", "{}"),
        ("Viaturas — total",        "vtr_total",     "maior_melhor", "{}"),
        ("Viaturas operando",       "vtr_operando",  "maior_melhor", "{}"),
        ("% baixadas",              "pct_baixadas",  "menor_melhor", "{}%"),
        ("Frota — idade média",     "idade",         "menor_melhor", "{} anos"),
    ]

    cabecalhos = ["Indicador"] + [nome for _, nome in UNIDADES]
    linhas = []
    melhores = set()
    piores = set()

    for row_idx, (label, campo, sentido, fmt) in enumerate(especs):
        valores_num = [dados_unidades[chave][campo] for chave, _ in UNIDADES]
        # Formata pra tabela
        valores_str = [fmt.format(v) if v is not None else "—" for v in valores_num]
        linhas.append([label] + valores_str)

        # Identifica melhor/pior — só destaca se houver +1 valor válido
        idx_melhor, idx_pior = classificar(valores_num, sentido)
        if idx_melhor is not None and idx_melhor != idx_pior:
            # +1 porque coluna 0 é o label do indicador
            melhores.add((row_idx, idx_melhor + 1))
            piores.add((row_idx, idx_pior + 1))

    add_tabela_destacada(slide, MARGIN, Inches(1.9), SLIDE_W - 2 * MARGIN,
                         cabecalhos, linhas,
                         largura_col=[Inches(3.2), Inches(1.85), Inches(1.85),
                                      Inches(1.85), Inches(1.85), Inches(1.85)],
                         melhores=melhores, piores=piores)

    # Legenda de cores
    y_leg = Inches(1.9) + Inches(0.35 * (len(linhas) + 1)) + Inches(0.3)
    add_rect(slide, MARGIN, y_leg, Inches(0.3), Inches(0.2), fill=COR_MELHOR_BG,
             line=COR_LINHA)
    add_text(slide, MARGIN + Inches(0.4), y_leg - Inches(0.02),
             Inches(2), Inches(0.28),
             "melhor do período", font=FONT_CORPO, size=10, color=COR_TEXTO_DIM)
    add_rect(slide, MARGIN + Inches(2.5), y_leg, Inches(0.3), Inches(0.2),
             fill=COR_PIOR_BG, line=COR_LINHA)
    add_text(slide, MARGIN + Inches(2.9), y_leg - Inches(0.02),
             Inches(2), Inches(0.28),
             "atenção — pior do período", font=FONT_CORPO, size=10, color=COR_TEXTO_DIM)

    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_cobom_periodo(prs, dados_periodo, n):
    """Comparativo COBOM entre os 4 SGBs — sem Sede (não é área de atendimento)."""
    slide = _blank(prs)
    p = dados_periodo["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}",
                f"OPERACIONAL COBOM  ·  {p['label_curto']}")
    add_titulo_slide(slide, "Ocorrências e vítimas fatais por SGB (dados COBOM/CBI).")

    cb = dados_periodo.get("cobom")
    if not cb:
        add_text(slide, MARGIN, Inches(3.5), SLIDE_W - 2 * MARGIN, Inches(1),
                 f"Arquivo cobom_{p['ano']}-S{1 if p['num'] <= 2 and p['tipo']=='trimestre' and p['num']<=2 else p['num']}.xlsx indisponível.",
                 font=FONT_CORPO, size=14, color=COR_TEXTO_DIM, align=PP_ALIGN.CENTER)
        add_footer(slide, f"11º GB — {p['label_longo']}")
        return

    # 4 bignums no topo — totais do período
    card_w = Inches(3.0); card_h = Inches(1.4); gap = Inches(0.11)
    xs = [MARGIN + i * (card_w + gap) for i in range(4)]

    add_bignum(slide, xs[0], Inches(1.9), card_w, card_h,
               cb["ocorrencias_incendio"]["total"], "atendimentos",
               "Ocorrências de incêndio")
    cor_fi = COR_BOM if cb["fatais_incendio"]["total"] == 0 else COR_CRITICO
    add_bignum(slide, xs[1], Inches(1.9), card_w, card_h,
               cb["fatais_incendio"]["total"],
               f"{cb['letalidade_incendio_pct']}% letalidade",
               "Vítimas fatais — incêndio", cor=cor_fi)
    add_bignum(slide, xs[2], Inches(1.9), card_w, card_h,
               cb["ocorrencias_transito"]["total"], "atendimentos",
               "Ocorrências de trânsito")
    add_bignum(slide, xs[3], Inches(1.9), card_w, card_h,
               cb["fatais_transito"]["total"],
               f"{cb['letalidade_transito_pct']}% letalidade",
               "Vítimas fatais — trânsito", cor=COR_CRITICO)

    # Tabela por SGB (só 4 SGBs, sem Sede)
    cabecalhos = ["Indicador", "1º SGB", "2º SGB", "3º SGB", "4º SGB"]
    linhas_raw = [
        ("Ocorrências de incêndio",  "ocorrencias_incendio",  "maior_melhor"),
        ("Fatais em incêndio",        "fatais_incendio",       "menor_melhor"),
        ("Ocorrências de trânsito",  "ocorrencias_transito",  "maior_melhor"),
        ("Fatais em trânsito",        "fatais_transito",       "menor_melhor"),
    ]
    linhas = []
    melhores = set(); piores = set()
    for row_idx, (label, chave, sentido) in enumerate(linhas_raw):
        vs = [item["valor"] for item in cb[chave]["por_sgb"]]
        linhas.append([label] + [str(v) for v in vs])
        im, ip = classificar(vs, sentido)
        if im is not None and im != ip:
            melhores.add((row_idx, im + 1))
            piores.add((row_idx, ip + 1))

    add_tabela_destacada(slide, MARGIN, Inches(3.7), SLIDE_W - 2 * MARGIN,
                         cabecalhos, linhas,
                         largura_col=[Inches(4.0), Inches(2.08), Inches(2.08),
                                      Inches(2.08), Inches(2.08)],
                         melhores=melhores, piores=piores)

    # Nota rodapé
    add_text(slide, MARGIN, Inches(6.3), SLIDE_W - 2 * MARGIN, Inches(0.4),
             "Nota: ocorrências são despachadas por área geográfica — Sede/EM não figura como base operacional.",
             font=FONT_CORPO, size=10, italic=True, color=COR_TEXTO_MUTED)
    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_fechamento(prs, dados_s):
    slide = _blank(prs)
    p = dados_s["periodo"]
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = COR_TEXTO
    bg.line.fill.background()
    add_text(slide, Inches(1.5), Inches(2.6), Inches(10), Inches(2.5),
             '"A força da equipe está em cada membro.\nA força de cada membro está na equipe."',
             font=FONT_TITULO, size=32, italic=True, color=COR_BG)
    add_text(slide, Inches(1.5), Inches(4.8), Inches(10), Inches(0.4),
             "— Phil Jackson", font=FONT_CORPO, size=14, color=COR_ACENTO_CLARO)
    add_text(slide, Inches(1.5), Inches(6.5), Inches(10), Inches(0.4),
             f"11º GB — {p['label_longo']}  ·  gerado pelo Sistema de Comando Digital",
             font=FONT_CORPO, size=10, italic=True, color=COR_TEXTO_MUTED)


# ==========================================================================
# MAIN
# ==========================================================================

def gerar(ano, num_sem):
    trim_a = 2 * (num_sem - 1) + 1
    trim_b = trim_a + 1

    print(f">> Coletando dados 3× ({ano}: Q{trim_a}, Q{trim_b}, S{num_sem})...")
    dados_qa = carregar_tudo("trimestre", ano, trim_a)
    dados_qb = carregar_tudo("trimestre", ano, trim_b)
    dados_s  = carregar_tudo("semestre",  ano, num_sem)

    print(">> Montando apresentação...")
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    n = 1
    slide_capa(prs, ano, num_sem);                    n += 1
    slide_sumario(prs, dados_s, n, num_sem);          n += 1

    # 1º Trimestre
    slide_divisor(prs, f"Q{trim_a}/{ano}",
                  f"Como cada unidade se comportou no {trim_a}º trimestre.")
    slide_comparativo_periodo(prs, dados_qa, n);      n += 1
    slide_cobom_periodo(prs, dados_qa, n);            n += 1

    # 2º Trimestre
    slide_divisor(prs, f"Q{trim_b}/{ano}",
                  f"Como cada unidade se comportou no {trim_b}º trimestre.")
    slide_comparativo_periodo(prs, dados_qb, n);      n += 1
    slide_cobom_periodo(prs, dados_qb, n);            n += 1

    # Consolidado
    slide_divisor(prs, f"S{num_sem}/{ano} — Consolidado",
                  "Consolidado do semestre entre as unidades.")
    slide_comparativo_periodo(prs, dados_s, n);       n += 1
    slide_cobom_periodo(prs, dados_s, n);             n += 1

    slide_fechamento(prs, dados_s)

    arquivo = f"Relatorio_Comparativo_Unidades_{ano}-S{num_sem}_11GB.pptx"
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), arquivo)
    prs.save(caminho)
    print(f">> Gerado: {caminho}  ({len(prs.slides)} slides)")
    return caminho


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python gerar_comparativo_unidades.py <ANO> <NUM_SEM>")
        print("     python gerar_comparativo_unidades.py 2026 1")
        sys.exit(1)
    gerar(int(sys.argv[1]), int(sys.argv[2]))
