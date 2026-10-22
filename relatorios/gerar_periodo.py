"""
Gerador do Relatório Periódico do 11º GB (PPTX).

Uso:
    python gerar_periodo.py trimestre 2026 3   → 3º Trimestre de 2026
    python gerar_periodo.py semestre 2026 1    → 1º Semestre de 2026
    python gerar_periodo.py anual 2026 1       → Exercício 2026

Cobre os 18 KPIs demandados pelo Cap, com Sede + SGBs estratificados.
KPIs sem fonte no banco vêm marcados 'A INTEGRAR' com origem sugerida.
"""

import sys, os
from datetime import date
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dados import carregar_tudo

import re


# ==========================================================================
# PALETA E TIPOGRAFIA
# ==========================================================================

COR_ACENTO       = RGBColor(0xB2, 0x22, 0x22)
COR_ACENTO_ESC   = RGBColor(0x7A, 0x17, 0x17)
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

FONT_TITULO = "Cambria"
FONT_CORPO  = "Calibri"
FONT_DADOS  = "Consolas"

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN  = Inches(0.6)


# ==========================================================================
# NORMALIZAÇÃO DE SGB
# ==========================================================================

def norm_sgb(s):
    if not s:
        return None
    s = str(s).upper().replace("°", "º").strip()
    if "SEDE" in s or s == "EM":
        return "EM"
    m = re.match(r"(\d)\s*º?\s*S?GB", s)
    return f"{m.group(1)}_SGB" if m else s


def buscar_por_sgb(lista, chave_canonica, campo_sgb="lotacao"):
    for item in lista or []:
        if norm_sgb(item.get(campo_sgb)) == chave_canonica:
            return item
    return None


# ==========================================================================
# HELPERS DE SHAPES
# ==========================================================================

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
        run = p.add_run()
        run.text = line
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = color
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
    add_text(slide, x, y, Inches(9), Inches(0.28),
             f"{numero}   {texto}",
             font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y + Inches(0.30),
                                   Inches(0.8), Emu(15000))
    line.fill.solid(); line.fill.fore_color.rgb = COR_ACENTO
    line.line.fill.background()


def add_titulo_slide(slide, texto, y=Inches(0.9), size=30):
    add_text(slide, MARGIN, y, SLIDE_W - 2 * MARGIN, Inches(0.85),
             texto, font=FONT_TITULO, size=size, color=COR_TEXTO)


def add_footer(slide, texto):
    add_text(slide, MARGIN, SLIDE_H - Inches(0.35),
             SLIDE_W - 2 * MARGIN, Inches(0.25),
             texto, font=FONT_CORPO, size=9, color=COR_TEXTO_MUTED)


def add_bignum(slide, x, y, w, h, valor, unidade, label, cor=None,
               font_valor=None):
    add_rect(slide, x, y, w, h, fill=COR_BG_SUAVE)
    cor_valor = cor or COR_ACENTO

    pad_x     = Inches(0.25)
    pad_top   = Inches(0.15)
    pad_bot   = Inches(0.12)
    label_h   = Inches(0.28)
    unidade_h = Inches(0.24) if unidade else Inches(0)
    gap       = Inches(0.05)

    valor_h = h - label_h - unidade_h - pad_top - pad_bot - gap * (2 if unidade else 1)

    if font_valor is None:
        emu_per_inch = 914400
        h_emu = int(valor_h) if not hasattr(valor_h, 'emu') else valor_h.emu
        h_in = h_emu / emu_per_inch
        if   h_in < 0.55: font_valor = 22
        elif h_in < 0.75: font_valor = 28
        elif h_in < 0.95: font_valor = 34
        elif h_in < 1.15: font_valor = 40
        else:             font_valor = 46

    y_cursor = y + pad_top
    add_text(slide, x + pad_x, y_cursor, w - 2 * pad_x, valor_h,
             str(valor), font=FONT_TITULO, size=font_valor,
             color=cor_valor, anchor=MSO_ANCHOR.MIDDLE)
    y_cursor += valor_h + gap
    if unidade:
        add_text(slide, x + pad_x, y_cursor, w - 2 * pad_x, unidade_h,
                 unidade, font=FONT_CORPO, size=11, color=COR_TEXTO_DIM)
    add_text(slide, x + pad_x, y + h - pad_bot - label_h,
             w - 2 * pad_x, label_h,
             label.upper(), font=FONT_CORPO, size=9, bold=True,
             color=COR_TEXTO_MUTED)


def add_placeholder(slide, x, y, w, h, titulo, motivo):
    add_rect(slide, x, y, w, h, fill=COR_BG_SUAVE, line=COR_LINHA)
    add_text(slide, x + Inches(0.25), y + Inches(0.2), w - Inches(0.5), Inches(0.3),
             titulo.upper(), font=FONT_CORPO, size=9, bold=True, color=COR_TEXTO_MUTED)
    add_text(slide, x + Inches(0.25), y + Inches(0.6),
             w - Inches(0.5), Inches(0.6),
             "A INTEGRAR", font=FONT_TITULO, size=22, italic=True, color=COR_INDISP)
    add_text(slide, x + Inches(0.25), y + h - Inches(0.5),
             w - Inches(0.5), Inches(0.35),
             motivo, font=FONT_CORPO, size=9, italic=True, color=COR_TEXTO_MUTED)


def add_tabela(slide, x, y, w, cabecalhos, linhas, largura_col=None,
               destacar_col=None):
    n_col = len(cabecalhos)
    n_row = len(linhas) + 1
    table = slide.shapes.add_table(n_row, n_col, x, y, w, Inches(0.32 * n_row)).table

    if largura_col:
        for i, lc in enumerate(largura_col):
            table.columns[i].width = lc

    for j, hh in enumerate(cabecalhos):
        cell = table.cell(0, j)
        cell.fill.solid(); cell.fill.fore_color.rgb = COR_BG_SUAVE
        cell.text_frame.text = str(hh)
        for p in cell.text_frame.paragraphs:
            for r in p.runs:
                r.font.name = FONT_CORPO
                r.font.size = Pt(10)
                r.font.bold = True
                r.font.color.rgb = COR_TEXTO_MUTED

    for i, linha in enumerate(linhas, start=1):
        for j, valor in enumerate(linha):
            cell = table.cell(i, j)
            cell.fill.solid(); cell.fill.fore_color.rgb = COR_BG
            cell.text_frame.text = str(valor)
            for p in cell.text_frame.paragraphs:
                for r in p.runs:
                    r.font.name = FONT_DADOS if j > 0 else FONT_CORPO
                    r.font.size = Pt(11)
                    r.font.color.rgb = COR_TEXTO
                    if destacar_col == j:
                        r.font.bold = True
                        r.font.color.rgb = COR_ACENTO


# ==========================================================================
# HELPERS DE CLASSIFICAÇÃO (semáforo)
# ==========================================================================

def cor_pct_operacional(pct):
    """Verde ≥70%, amarelo 50-70%, vermelho <50%."""
    if pct is None: return COR_INDISP
    p = float(pct)
    if p >= 70: return COR_BOM
    if p >= 50: return COR_ATENCAO
    return COR_CRITICO


def cor_pct_absenteismo(pct):
    """Menor é melhor. Verde <2%, amarelo 2-5%, vermelho >5%."""
    if pct is None: return COR_INDISP
    p = float(pct)
    if p < 2: return COR_BOM
    if p < 5: return COR_ATENCAO
    return COR_CRITICO


def cor_pct_baixadas(pct):
    """Menor é melhor. Verde <15%, amarelo 15-25%, vermelho >25%."""
    if pct is None: return COR_INDISP
    p = float(pct)
    if p < 15: return COR_BOM
    if p < 25: return COR_ATENCAO
    return COR_CRITICO


def cor_idade_frota(idade):
    """Menor é melhor. Verde <8, amarelo 8-12, vermelho >12."""
    if idade is None: return COR_INDISP
    i = float(idade)
    if i < 8:  return COR_BOM
    if i < 12: return COR_ATENCAO
    return COR_CRITICO


# ==========================================================================
# SLIDES
# ==========================================================================

def slide_capa(prs, dados):
    slide = _blank(prs)
    p = dados["periodo"]

    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.5), SLIDE_H)
    bar.fill.solid(); bar.fill.fore_color.rgb = COR_ACENTO
    bar.line.fill.background()

    add_text(slide, Inches(1.2), Inches(2.2), Inches(11), Inches(0.4),
             "11º GRUPAMENTO DE BOMBEIROS  ·  PMESP",
             font=FONT_CORPO, size=13, bold=True, color=COR_TEXTO_MUTED)

    add_text(slide, Inches(1.2), Inches(2.6), Inches(11), Inches(1.6),
             "Relatório Periódico",
             font=FONT_TITULO, size=60, color=COR_TEXTO)

    add_text(slide, Inches(1.2), Inches(4.2), Inches(11), Inches(1.0),
             p["label_longo"],
             font=FONT_TITULO, size=42, italic=True, color=COR_ACENTO)

    add_text(slide, Inches(1.2), Inches(5.4), Inches(11), Inches(0.4),
             f"Corte: {p['inicio'].strftime('%d/%m/%Y')} a {p['fim'].strftime('%d/%m/%Y')}",
             font=FONT_CORPO, size=13, color=COR_TEXTO_DIM)

    add_text(slide, Inches(1.2), Inches(6.5), Inches(11), Inches(0.4),
             f"Vale do Paraíba  ·  Litoral Norte  ·  emitido em {date.today().strftime('%d/%m/%Y')}",
             font=FONT_CORPO, size=11, color=COR_TEXTO_MUTED)


def slide_sumario(prs, dados, n):
    slide = _blank(prs)
    p = dados["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}", f"SUMÁRIO EXECUTIVO  ·  {p['label_curto']}")
    add_titulo_slide(slide, f"Foto do 11º GB no {p['label_longo'].lower()}.")

    ef = dados["efetivo"]
    ab = dados["absenteismo"]
    te = dados["territorio"]
    el = dados["elogios"]
    ug = dados["uge"]
    mm = dados["motomec"]

    card_w = Inches(4.0)
    card_h = Inches(1.7)
    gap = Inches(0.15)
    x0, x1, x2 = MARGIN, MARGIN + card_w + gap, MARGIN + 2 * (card_w + gap)

    add_bignum(slide, x0, Inches(1.9), card_w, card_h,
               ef["total_ativos"], "militares ativos", "Efetivo total")
    add_bignum(slide, x1, Inches(1.9), card_w, card_h,
               f"{ef['operacional_geral']['pct']}%", "operacional (cod ...1)",
               "Efetivo empregado", cor=cor_pct_operacional(ef['operacional_geral']['pct']))
    add_bignum(slide, x2, Inches(1.9), card_w, card_h,
               f"{ab['geral']['pct']}%", "em LTS no período",
               "Absenteísmo", cor=cor_pct_absenteismo(ab['geral']['pct']))

    add_bignum(slide, x0, Inches(3.85), card_w, card_h,
               f"{te['atendidos']}/{te['total_municipios']}", f"{te['pct']}%",
               "Cobertura territorial")
    add_bignum(slide, x1, Inches(3.85), card_w, card_h,
               el["geral"]["total"], "elogios+LMP+LOU", "Reconhecimento (período)")
    add_bignum(slide, x2, Inches(3.85), card_w, card_h,
               f"{mm['geral']['pct_baixadas']}%", f"{mm['geral']['baixada']} viaturas",
               "Taxa de baixadas", cor=cor_pct_baixadas(mm['geral']['pct_baixadas']))

    # Rodapé com nota de fonte
    add_text(slide, MARGIN, Inches(6.0), SLIDE_W - 2 * MARGIN, Inches(1.0),
             "Nota: KPIs de operações (ocorrências, vítimas fatais, atendimento ≤20min), disciplina (SJD/PJMD) "
             "e SAT (dias análise/vistoria) sinalizados 'A INTEGRAR' no corpo do relatório — fontes externas "
             "aguardando importação.",
             font=FONT_CORPO, size=11, italic=True, color=COR_TEXTO_MUTED)
    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_divisor(prs, titulo_parte, subtitulo):
    slide = _blank(prs)
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = COR_TEXTO
    bg.line.fill.background()

    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.5), SLIDE_H)
    bar.fill.solid(); bar.fill.fore_color.rgb = COR_ACENTO
    bar.line.fill.background()

    add_text(slide, Inches(1.2), Inches(3.0), Inches(11), Inches(0.5),
             titulo_parte.upper(),
             font=FONT_CORPO, size=14, bold=True, color=COR_ACENTO_CLARO)

    add_text(slide, Inches(1.2), Inches(3.5), Inches(11), Inches(1.5),
             subtitulo,
             font=FONT_TITULO, size=54, color=COR_BG)


# ==========================================================================
# SEDE — 7 slides (um por seção)
# ==========================================================================

def slide_sede_b1(prs, dados, n):
    slide = _blank(prs)
    p = dados["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}", "SEDE / B-1  ·  PESSOAL")
    add_titulo_slide(slide, "Efetivo, empregabilidade e absenteísmo — Sede.")

    ef_em = buscar_por_sgb(dados["efetivo"]["operacional_por_sgb"], "EM", "lotacao")
    ab_em = buscar_por_sgb(dados["absenteismo"]["por_sgb"], "EM", "lotacao")

    card_h = Inches(1.7)
    if ef_em:
        add_bignum(slide, MARGIN, Inches(1.9), Inches(3.9), card_h,
                   ef_em["total"], "militares no EM", "Efetivo ativo")
        add_bignum(slide, MARGIN + Inches(4.1), Inches(1.9), Inches(3.9), card_h,
                   f"{ef_em['pct']}%", f"{ef_em['operacional']}/{ef_em['total']}",
                   "Empregado operacional",
                   cor=cor_pct_operacional(ef_em['pct']))
    if ab_em:
        add_bignum(slide, MARGIN + Inches(8.2), Inches(1.9), Inches(3.9), card_h,
                   f"{ab_em['pct']}%", f"{ab_em['em_lts']} em LTS",
                   "Absenteísmo no período",
                   cor=cor_pct_absenteismo(ab_em['pct']))

    # Placeholder especialização
    add_placeholder(slide, MARGIN, Inches(3.9), Inches(6), Inches(2.4),
                    "Taxa anual de especialização de Bombeiros",
                    "Fonte a ser providenciada pela Sede B/1")

    # Tabela comparativa Sede vs total
    add_text(slide, Inches(7.0), Inches(3.9), Inches(6), Inches(0.3),
             "COMPARATIVO SEDE VS GERAL", font=FONT_CORPO, size=10, bold=True,
             color=COR_TEXTO_MUTED)
    add_tabela(slide, Inches(7.0), Inches(4.2), Inches(5.7),
               ["Indicador", "Sede (EM)", "GB total"],
               [("Efetivo ativo",
                 ef_em["total"] if ef_em else "—",
                 dados["efetivo"]["total_ativos"]),
                ("% Operacional",
                 f"{ef_em['pct']}%" if ef_em else "—",
                 f"{dados['efetivo']['operacional_geral']['pct']}%"),
                ("% LTS no período",
                 f"{ab_em['pct']}%" if ab_em else "—",
                 f"{dados['absenteismo']['geral']['pct']}%")])
    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_sede_b3(prs, dados, n):
    slide = _blank(prs)
    p = dados["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}", "SEDE / B-3  ·  OPERAÇÕES")
    add_titulo_slide(slide, "Cobertura territorial e atendimento operacional.")

    te = dados["territorio"]
    cb = dados.get("cobom")

    card_w = Inches(3.0); card_h = Inches(1.6); gap = Inches(0.1)
    x0 = MARGIN
    x1 = x0 + card_w + gap
    x2 = x1 + card_w + gap
    x3 = x2 + card_w + gap

    cor_terr = COR_BOM if te["pct"] >= 80 else COR_ATENCAO if te["pct"] >= 60 else COR_CRITICO
    add_bignum(slide, x0, Inches(1.9), card_w, card_h,
               f"{te['atendidos']}/{te['total_municipios']}", f"{te['pct']}% do Vale",
               "Cobertura territorial", cor=cor_terr)

    if cb:
        add_bignum(slide, x1, Inches(1.9), card_w, card_h,
                   cb["ocorrencias_incendio"]["total"], "ocorrências",
                   "Atendimento a incêndio")
        cor_fat_inc = COR_BOM if cb["fatais_incendio"]["total"] == 0 else COR_CRITICO
        add_bignum(slide, x2, Inches(1.9), card_w, card_h,
                   cb["fatais_incendio"]["total"],
                   f"{cb['letalidade_incendio_pct']}% letalidade",
                   "Vítimas fatais — incêndio", cor=cor_fat_inc)
        add_bignum(slide, x3, Inches(1.9), card_w, card_h,
                   cb["ocorrencias_transito"]["total"], "ocorrências",
                   "Atendimento a trânsito")

        # Segunda linha: fatais trânsito + tabela por SGB
        add_bignum(slide, x0, Inches(3.7), card_w, card_h,
                   cb["fatais_transito"]["total"],
                   f"{cb['letalidade_transito_pct']}% letalidade",
                   "Vítimas fatais — trânsito", cor=COR_CRITICO)

        linhas_sgb = []
        for i, sgb_key in enumerate(["1_SGB", "2_SGB", "3_SGB", "4_SGB"]):
            oc_inc = cb["ocorrencias_incendio"]["por_sgb"][i]["valor"]
            fa_inc = cb["fatais_incendio"]["por_sgb"][i]["valor"]
            oc_tr  = cb["ocorrencias_transito"]["por_sgb"][i]["valor"]
            fa_tr  = cb["fatais_transito"]["por_sgb"][i]["valor"]
            linhas_sgb.append((sgb_key.replace("_", "º "),
                               oc_inc, fa_inc, oc_tr, fa_tr))
        add_tabela(slide, x1, Inches(3.7), card_w * 3 + gap * 2,
                   ["Unidade", "Oc. incêndio", "Fatais inc.",
                    "Oc. trânsito", "Fatais tr."],
                   linhas_sgb)
    else:
        add_placeholder(slide, x1, Inches(1.9), card_w * 3 + gap * 2, Inches(1.6),
                        "Ocorrências e vítimas",
                        "cobom_<ano>-S<n>.xlsx não encontrado")
    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_sede_b5(prs, dados, n):
    slide = _blank(prs)
    p = dados["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}", "SEDE / B-5  ·  ELOGIOS E LÁUREAS")
    add_titulo_slide(slide, f"Reconhecimento — {p['label_longo']}.")

    el = dados["elogios"]["geral"]
    el_em = buscar_por_sgb(dados["elogios"]["por_sgb"], "EM", "sgb")

    total_militares = dados["efetivo"]["total_ativos"] or 1
    total_em = 77  # aproximado — poderíamos calcular do efetivo por lotação

    ef_em = buscar_por_sgb(dados["efetivo"]["operacional_por_sgb"], "EM", "lotacao")
    if ef_em:
        total_em = ef_em["total"]

    elog_geral = round(el["elogios"] / total_militares, 2) if el["elogios"] else 0
    elog_em    = round((el_em["elogios"] if el_em else 0) / max(total_em, 1), 2)

    card_h = Inches(1.7)
    add_bignum(slide, MARGIN, Inches(1.9), Inches(3.9), card_h,
               el["elogios"], "elogios (ELO)", "Total no período")
    add_bignum(slide, MARGIN + Inches(4.1), Inches(1.9), Inches(3.9), card_h,
               elog_geral, "por bombeiro (GB)", "Índice geral")
    add_bignum(slide, MARGIN + Inches(8.2), Inches(1.9), Inches(3.9), card_h,
               el["lmp"], "LMP", "Láureas de Mérito Pessoal")

    # Tabela por SGB (inclui SEDE)
    add_text(slide, MARGIN, Inches(3.85), Inches(6), Inches(0.3),
             f"ELOGIOS POR UNIDADE — {p['label_curto']}",
             font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    linhas = [(r["sgb"], r["total"], r["elogios"], r["lmp"], r["louvor"])
              for r in dados["elogios"]["por_sgb"]]
    add_tabela(slide, MARGIN, Inches(4.15), Inches(6),
               ["Unidade", "Total", "ELO", "LMP", "LOU"], linhas)

    # Sede em foco
    add_text(slide, Inches(7.0), Inches(3.85), Inches(6), Inches(0.3),
             "SEDE (EM) — DESTAQUES",
             font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    if el_em:
        add_tabela(slide, Inches(7.0), Inches(4.15), Inches(5.7),
                   ["Indicador", "Valor"],
                   [("Elogios/bombeiro Sede", elog_em),
                    ("LMP na Sede",           el_em["lmp"]),
                    ("Louvor na Sede",        el_em["louvor"])])
    else:
        add_text(slide, Inches(7.0), Inches(4.15), Inches(5.7), Inches(0.4),
                 "Sem registros de elogios da Sede no período.",
                 font=FONT_CORPO, size=12, italic=True, color=COR_TEXTO_DIM)
    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_sede_uge(prs, dados, n):
    slide = _blank(prs)
    p = dados["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}", "SEDE / UGE  ·  CONTROLE DE PROCESSOS")
    add_titulo_slide(slide, "Processos administrativos e financeiro.")

    add_text(slide, MARGIN, Inches(1.6), Inches(11), Inches(0.35),
             "A UGE existe apenas na Sede — indicadores não são estratificados por SGB.",
             font=FONT_CORPO, size=12, italic=True, color=COR_TEXTO_MUTED)

    u = dados["uge"]["geral"]
    card_h = Inches(1.7)

    add_bignum(slide, MARGIN, Inches(2.1), Inches(3.9), card_h,
               u["total"], "processos", "Total no ano")
    add_bignum(slide, MARGIN + Inches(4.1), Inches(2.1), Inches(3.9), card_h,
               u["em_andamento"], "em andamento", "Em curso",
               cor=COR_ATENCAO if u["em_andamento"] > 5 else COR_BOM)
    add_bignum(slide, MARGIN + Inches(8.2), Inches(2.1), Inches(3.9), card_h,
               f"R$ {float(u['total_empenhado'])/1000:.0f}k",
               "empenhado", "Valor total")

    add_text(slide, MARGIN, Inches(4.05), Inches(6), Inches(0.3),
             "PROCESSOS POR STATUS", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    add_tabela(slide, MARGIN, Inches(4.35), Inches(6),
               ["Status", "Qtd"],
               [("Em andamento", u["em_andamento"]),
                ("Encerrado",    u["encerrado"]),
                ("Cancelado",    u["cancelado"]),
                ("Vencidos (s/entrega)", u.get("vencidos", 0))])

    add_text(slide, Inches(7.0), Inches(4.05), Inches(6), Inches(0.3),
             "FINANCEIRO (R$)", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    add_tabela(slide, Inches(7.0), Inches(4.35), Inches(5.7),
               ["Rubrica", "Valor"],
               [("Empenhado",  f"R$ {float(u['total_empenhado']):,.2f}"),
                ("Liquidado",  f"R$ {float(u['total_liquidado']):,.2f}"),
                ("Execução",
                 f"{100 * float(u['total_liquidado']) / max(float(u['total_empenhado']), 1):.1f}%")])
    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_sede_sjd(prs, dados, n):
    slide = _blank(prs)
    p = dados["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}", "SEDE / SJD  ·  JUSTIÇA E DISCIPLINA")
    add_titulo_slide(slide, "Denúncias e procedimentos disciplinares.")

    add_placeholder(slide, MARGIN, Inches(1.9), Inches(6.0), Inches(2.6),
                    "Índice de reclamações / denúncias (CORREG PM, OPM, COPOM)",
                    "Base SJD — a integrar")
    add_placeholder(slide, Inches(7.0), Inches(1.9), Inches(5.7), Inches(2.6),
                    "Índice de PMs punidos via Procedimento Disciplinar (PD)",
                    "Base SJD — a integrar")
    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_sede_pjmd(prs, dados, n):
    slide = _blank(prs)
    p = dados["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}", "SEDE / PJMD  ·  ACIDENTES COM BOMBEIROS")
    add_titulo_slide(slide, "Acidentes de trânsito envolvendo militares.")

    add_placeholder(slide, MARGIN, Inches(1.9), Inches(6.0), Inches(2.6),
                    "Acidentes com bombeiro na folga / in itinere",
                    "Base PJMD — a integrar")
    add_placeholder(slide, Inches(7.0), Inches(1.9), Inches(5.7), Inches(2.6),
                    "Acidentes envolvendo viatura com vítima bombeiro",
                    "Base PJMD — a integrar")
    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_sede_motomec(prs, dados, n):
    slide = _blank(prs)
    p = dados["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}", "SEDE / MOTOMEC  ·  FROTA")
    add_titulo_slide(slide, "Idade veicular e taxa de baixadas.")

    mm = dados["motomec"]["geral"]
    card_h = Inches(1.7)

    add_bignum(slide, MARGIN, Inches(1.9), Inches(3.0), card_h,
               mm["total"], "viaturas", "Frota total")
    add_bignum(slide, MARGIN + Inches(3.2), Inches(1.9), Inches(3.0), card_h,
               mm["operando"], "operando", "Em operação", cor=COR_BOM)
    add_bignum(slide, MARGIN + Inches(6.4), Inches(1.9), Inches(3.0), card_h,
               f"{mm['pct_baixadas']}%", f"{mm['baixada']} viaturas",
               "Taxa de baixadas", cor=cor_pct_baixadas(mm['pct_baixadas']))
    add_bignum(slide, MARGIN + Inches(9.6), Inches(1.9), Inches(3.0), card_h,
               f"{mm['idade_media']}", "anos", "Idade média",
               cor=cor_idade_frota(mm['idade_media']))

    # Tabela idade + baixadas por SGB
    add_text(slide, MARGIN, Inches(3.85), Inches(12), Inches(0.3),
             "FROTA POR UNIDADE", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    linhas = [(r["sgb"], r["total"], r["operando"], r["baixada"],
               f"{r['pct_baixadas']}%", f"{r['idade_media']} anos")
              for r in dados["motomec"]["por_sgb"]]
    add_tabela(slide, MARGIN, Inches(4.15), SLIDE_W - 2 * MARGIN,
               ["Unidade", "Total", "Operando", "Baixadas", "% Baixadas", "Idade média"],
               linhas)
    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_sede_sat(prs, dados, n):
    slide = _blank(prs)
    p = dados["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}", "SEDE / SAT  ·  ATIVIDADE TÉCNICA")
    add_titulo_slide(slide, "Análises e vistorias.")

    add_placeholder(slide, MARGIN, Inches(1.9), Inches(6.0), Inches(2.6),
                    "Quantidade de dias para realização de análise",
                    "Base SAT — a integrar")
    add_placeholder(slide, Inches(7.0), Inches(1.9), Inches(5.7), Inches(2.6),
                    "Quantidade de dias para realização de vistoria",
                    "Base SAT — a integrar")
    add_footer(slide, f"11º GB — {p['label_longo']}")


# ==========================================================================
# SGBs
# ==========================================================================

def slide_sgb_comparativo(prs, dados, n):
    slide = _blank(prs)
    p = dados["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}", "SGBs  ·  COMPARATIVO GERAL")
    add_titulo_slide(slide, "Quatro subgrupamentos, lado a lado.")

    sgbs = [("1_SGB", "1º SGB"),
            ("2_SGB", "2º SGB"),
            ("3_SGB", "3º SGB"),
            ("4_SGB", "4º SGB")]

    ef_op = dados["efetivo"]["operacional_por_sgb"]
    ab    = dados["absenteismo"]["por_sgb"]
    el    = dados["elogios"]["por_sgb"]
    mm    = dados["motomec"]["por_sgb"]

    cabecalhos = ["Indicador"] + [s[1] for s in sgbs]
    linhas = []

    # Efetivo total
    row = ["Efetivo ativo"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(ef_op, chave, "lotacao")
        row.append(r["total"] if r else "—")
    linhas.append(row)

    # % Operacional
    row = ["% empregado operacional"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(ef_op, chave, "lotacao")
        row.append(f"{r['pct']}%" if r else "—")
    linhas.append(row)

    # % Absenteísmo LTS
    row = ["% absenteísmo LTS"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(ab, chave, "lotacao")
        row.append(f"{r['pct']}%" if r else "—")
    linhas.append(row)

    # Elogios
    row = ["Elogios (período)"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(el, chave, "sgb")
        row.append(r["elogios"] if r else 0)
    linhas.append(row)

    # LMP
    row = ["LMP (período)"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(el, chave, "sgb")
        row.append(r["lmp"] if r else 0)
    linhas.append(row)

    # Viaturas total
    row = ["Viaturas — total"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(mm, chave, "sgb")
        row.append(r["total"] if r else "—")
    linhas.append(row)

    # % Baixadas
    row = ["% baixadas"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(mm, chave, "sgb")
        row.append(f"{r['pct_baixadas']}%" if r else "—")
    linhas.append(row)

    # Idade média
    row = ["Frota — idade média"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(mm, chave, "sgb")
        row.append(f"{r['idade_media']} anos" if r and r["idade_media"] else "—")
    linhas.append(row)

    add_tabela(slide, MARGIN, Inches(1.8), SLIDE_W - 2 * MARGIN,
               cabecalhos, linhas,
               largura_col=[Inches(3.5), Inches(2.15), Inches(2.15),
                            Inches(2.15), Inches(2.15)])

    add_text(slide, MARGIN, Inches(6.4), SLIDE_W - 2 * MARGIN, Inches(0.6),
             "Detalhamento individual de cada SGB nas próximas páginas.",
             font=FONT_CORPO, size=11, italic=True, color=COR_TEXTO_MUTED)
    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_sgb_detalhe(prs, chave, nome, dados, n):
    slide = _blank(prs)
    p = dados["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}", f"SGBs  ·  {nome}")
    add_titulo_slide(slide, f"{nome} em detalhe.")

    ef_op = buscar_por_sgb(dados["efetivo"]["operacional_por_sgb"], chave, "lotacao")
    ab    = buscar_por_sgb(dados["absenteismo"]["por_sgb"], chave, "lotacao")
    el    = buscar_por_sgb(dados["elogios"]["por_sgb"], chave, "sgb")
    mm    = buscar_por_sgb(dados["motomec"]["por_sgb"], chave, "sgb")

    card_h = Inches(1.7)
    card_w = Inches(3.0)

    add_bignum(slide, MARGIN, Inches(1.9), card_w, card_h,
               ef_op["total"] if ef_op else "—", "militares", "Efetivo")

    if ef_op:
        add_bignum(slide, MARGIN + Inches(3.2), Inches(1.9), card_w, card_h,
                   f"{ef_op['pct']}%", "operacional", "Empregabilidade",
                   cor=cor_pct_operacional(ef_op['pct']))
    if ab:
        add_bignum(slide, MARGIN + Inches(6.4), Inches(1.9), card_w, card_h,
                   f"{ab['pct']}%", f"{ab['em_lts']} em LTS", "Absenteísmo",
                   cor=cor_pct_absenteismo(ab['pct']))
    if mm:
        add_bignum(slide, MARGIN + Inches(9.6), Inches(1.9), card_w, card_h,
                   mm["operando"], f"de {mm['total']}", "Viaturas operando",
                   cor=COR_BOM)

    # Tabelas: reconhecimento + frota
    add_text(slide, MARGIN, Inches(3.85), Inches(6), Inches(0.3),
             "RECONHECIMENTO NO PERÍODO", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    add_tabela(slide, MARGIN, Inches(4.15), Inches(6),
               ["Tipo", "Qtd"],
               [("Elogios (ELO)", el["elogios"] if el else 0),
                ("LMP",           el["lmp"]     if el else 0),
                ("Louvor",        el["louvor"]  if el else 0)])

    add_text(slide, Inches(7.0), Inches(3.85), Inches(5.7), Inches(0.3),
             "FROTA DO SGB", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    if mm:
        add_tabela(slide, Inches(7.0), Inches(4.15), Inches(5.7),
                   ["Indicador", "Valor"],
                   [("Total de viaturas",  mm["total"]),
                    ("Operando",           mm["operando"]),
                    ("Baixadas",           mm["baixada"]),
                    ("% Baixadas",         f"{mm['pct_baixadas']}%"),
                    ("Idade média",        f"{mm['idade_media']} anos")])
    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_fechamento(prs, dados):
    slide = _blank(prs)
    p = dados["periodo"]
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

def gerar(tipo, ano, num):
    print(f">> Coletando dados ({tipo} {ano}-{num})...")
    dados = carregar_tudo(tipo, ano, num)
    p = dados["periodo"]

    print(">> Montando apresentação...")
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    n = 0
    slide_capa(prs, dados)
    n += 1
    slide_sumario(prs, dados, n + 1)
    n += 1

    slide_divisor(prs, "PARTE I", "Sede — Estado-Maior")
    n += 1
    slide_sede_b1(prs, dados, n + 1); n += 1
    slide_sede_b3(prs, dados, n + 1); n += 1
    slide_sede_b5(prs, dados, n + 1); n += 1
    slide_sede_uge(prs, dados, n + 1); n += 1
    slide_sede_sjd(prs, dados, n + 1); n += 1
    slide_sede_pjmd(prs, dados, n + 1); n += 1
    slide_sede_motomec(prs, dados, n + 1); n += 1
    slide_sede_sat(prs, dados, n + 1); n += 1

    slide_divisor(prs, "PARTE II", "Subgrupamentos de Bombeiros")
    n += 1
    slide_sgb_comparativo(prs, dados, n + 1); n += 1

    for chave, nome in [("1_SGB", "1º SGB"), ("2_SGB", "2º SGB"),
                        ("3_SGB", "3º SGB"), ("4_SGB", "4º SGB")]:
        slide_sgb_detalhe(prs, chave, nome, dados, n + 1)
        n += 1

    slide_fechamento(prs, dados)
    n += 1

    arquivo = f"Relatorio_{p['label_curto']}_11GB.pptx"
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), arquivo)
    prs.save(caminho)
    print(f">> Gerado: {caminho}  ({n} slides)")
    return caminho


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python gerar_periodo.py <trimestre|semestre|anual> <ANO> <NUM>")
        print("     python gerar_periodo.py trimestre 2026 3")
        print("     python gerar_periodo.py semestre 2026 1")
        sys.exit(1)
    tipo = sys.argv[1]
    ano  = int(sys.argv[2])
    num  = int(sys.argv[3])
    gerar(tipo, ano, num)
