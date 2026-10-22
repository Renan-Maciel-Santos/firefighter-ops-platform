"""
Gerador do Relatório Semestral COMPARATIVO do 11º GB (PPTX).

Cada entidade (Sede + 4 SGBs) recebe 3 slides em sequência:
    1) KPIs do 1º Trimestre do semestre
    2) KPIs do 2º Trimestre do semestre
    3) Consolidado com Q1 vs Q2 vs Semestre (comparativo lado a lado + delta)

Uso:
    python gerar_semestre_comparativo.py 2026 1    → 1º Sem (Q1 + Q2)
    python gerar_semestre_comparativo.py 2026 2    → 2º Sem (Q3 + Q4)
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
# PALETA / TIPOGRAFIA / LAYOUT (mesma do gerar_periodo.py)
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
COR_DELTA_POS    = RGBColor(0x1F, 0x88, 0x3D)
COR_DELTA_NEG    = RGBColor(0xCF, 0x22, 0x2E)

FONT_TITULO = "Cambria"
FONT_CORPO  = "Calibri"
FONT_DADOS  = "Consolas"

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN  = Inches(0.6)


# ==========================================================================
# NORMALIZAÇÃO SGB (idem ao gerar_periodo.py)
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


# ==========================================================================
# HELPERS DE SHAPES (idem)
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
    add_text(slide, x, y, Inches(11), Inches(0.28),
             f"{numero}   {texto}",
             font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y + Inches(0.30),
                                    Inches(0.8), Emu(15000))
    line.fill.solid(); line.fill.fore_color.rgb = COR_ACENTO
    line.line.fill.background()


def add_titulo_slide(slide, texto, size=30):
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
    if   h_in < 0.55: fs = 22
    elif h_in < 0.75: fs = 28
    elif h_in < 0.95: fs = 34
    elif h_in < 1.15: fs = 40
    else:             fs = 46
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


def add_placeholder(slide, x, y, w, h, titulo, motivo):
    add_rect(slide, x, y, w, h, fill=COR_BG_SUAVE, line=COR_LINHA)
    add_text(slide, x + Inches(0.25), y + Inches(0.15), w - Inches(0.5), Inches(0.28),
             titulo.upper(), font=FONT_CORPO, size=9, bold=True, color=COR_TEXTO_MUTED)
    add_text(slide, x + Inches(0.25), y + Inches(0.5),
             w - Inches(0.5), Inches(0.55),
             "A INTEGRAR", font=FONT_TITULO, size=20, italic=True, color=COR_INDISP)
    add_text(slide, x + Inches(0.25), y + h - Inches(0.45),
             w - Inches(0.5), Inches(0.35),
             motivo, font=FONT_CORPO, size=9, italic=True, color=COR_TEXTO_MUTED)


def add_tabela(slide, x, y, w, cabecalhos, linhas, largura_col=None):
    n_col = len(cabecalhos); n_row = len(linhas) + 1
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
                r.font.name = FONT_CORPO; r.font.size = Pt(10)
                r.font.bold = True; r.font.color.rgb = COR_TEXTO_MUTED
    for i, linha in enumerate(linhas, start=1):
        for j, valor in enumerate(linha):
            cell = table.cell(i, j)
            cell.fill.solid(); cell.fill.fore_color.rgb = COR_BG
            cell.text_frame.text = str(valor)
            for p in cell.text_frame.paragraphs:
                for r in p.runs:
                    r.font.name = FONT_DADOS if j > 0 else FONT_CORPO
                    r.font.size = Pt(11); r.font.color.rgb = COR_TEXTO


# ==========================================================================
# SEMÁFORO
# ==========================================================================

def cor_pct_operacional(pct):
    if pct is None: return COR_INDISP
    p = float(pct)
    return COR_BOM if p >= 70 else COR_ATENCAO if p >= 50 else COR_CRITICO


def cor_pct_absenteismo(pct):
    if pct is None: return COR_INDISP
    p = float(pct)
    return COR_BOM if p < 2 else COR_ATENCAO if p < 5 else COR_CRITICO


def cor_pct_baixadas(pct):
    if pct is None: return COR_INDISP
    p = float(pct)
    return COR_BOM if p < 15 else COR_ATENCAO if p < 25 else COR_CRITICO


def cor_idade(idade):
    if idade is None: return COR_INDISP
    i = float(idade)
    return COR_BOM if i < 8 else COR_ATENCAO if i < 12 else COR_CRITICO


def delta_str(v_novo, v_antigo, unidade="", pct=False):
    """Formata delta com sinal + cor sugerida.
       Retorna (texto, cor)."""
    try:
        vn = float(v_novo); va = float(v_antigo)
    except (TypeError, ValueError):
        return ("—", COR_TEXTO_MUTED)
    d = vn - va
    if abs(d) < 0.05:
        return ("=", COR_TEXTO_MUTED)
    sinal = "+" if d > 0 else ""
    if pct:
        return (f"{sinal}{d:.1f} p.p.", COR_DELTA_POS if d > 0 else COR_DELTA_NEG)
    return (f"{sinal}{d:.0f}{unidade}", COR_DELTA_POS if d > 0 else COR_DELTA_NEG)


# ==========================================================================
# EXTRAI KPIs DE UMA ENTIDADE (Sede OU um SGB) A PARTIR DO PAYLOAD
# ==========================================================================

def kpis_entidade(dados, chave):
    """Dado o payload completo + chave canônica (EM ou N_SGB), retorna dict resumido:
       total, operacional_pct, absenteismo_pct, elogios, lmp, viaturas_total,
       viaturas_operando, pct_baixadas, idade_media
    """
    ef_op = buscar_por_sgb(dados["efetivo"]["operacional_por_sgb"], chave, "lotacao")
    ab    = buscar_por_sgb(dados["absenteismo"]["por_sgb"], chave, "lotacao")
    el    = buscar_por_sgb(dados["elogios"]["por_sgb"], chave, "sgb")
    mm    = buscar_por_sgb(dados["motomec"]["por_sgb"], chave, "sgb")

    return {
        "total":            ef_op["total"] if ef_op else None,
        "operacional":      ef_op["operacional"] if ef_op else None,
        "operacional_pct":  ef_op["pct"] if ef_op else None,
        "em_lts":           ab["em_lts"] if ab else 0,
        "absenteismo_pct":  ab["pct"] if ab else 0,
        "elogios":          el["elogios"] if el else 0,
        "lmp":              el["lmp"] if el else 0,
        "louvor":           el["louvor"] if el else 0,
        "elogios_total":    el["total"] if el else 0,
        "viaturas_total":   mm["total"] if mm else None,
        "viaturas_operando": mm["operando"] if mm else None,
        "viaturas_baixadas": mm["baixada"] if mm else None,
        "pct_baixadas":     mm["pct_baixadas"] if mm else None,
        "idade_media":      mm["idade_media"] if mm else None,
    }


# ==========================================================================
# SLIDES BÁSICOS
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
             "Relatório Semestral",
             font=FONT_TITULO, size=60, color=COR_TEXTO)
    add_text(slide, Inches(1.2), Inches(4.0), Inches(11), Inches(0.7),
             f"{num_sem}º Semestre de {ano}",
             font=FONT_TITULO, size=40, italic=True, color=COR_ACENTO)
    add_text(slide, Inches(1.2), Inches(4.9), Inches(11), Inches(0.4),
             "Comparativo trimestre a trimestre por unidade",
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
    te = dados_s["territorio"]; el = dados_s["elogios"]
    mm = dados_s["motomec"]

    card_w = Inches(4.0); card_h = Inches(1.7); gap = Inches(0.15)
    x0, x1, x2 = MARGIN, MARGIN + card_w + gap, MARGIN + 2 * (card_w + gap)

    add_bignum(slide, x0, Inches(1.9), card_w, card_h,
               ef["total_ativos"], "militares ativos", "Efetivo total")
    add_bignum(slide, x1, Inches(1.9), card_w, card_h,
               f"{ef['operacional_geral']['pct']}%", "operacional (cod ...1)",
               "Efetivo empregado", cor=cor_pct_operacional(ef['operacional_geral']['pct']))
    add_bignum(slide, x2, Inches(1.9), card_w, card_h,
               f"{ab['geral']['pct']}%", "em LTS no semestre",
               "Absenteísmo", cor=cor_pct_absenteismo(ab['geral']['pct']))

    add_bignum(slide, x0, Inches(3.85), card_w, card_h,
               f"{te['atendidos']}/{te['total_municipios']}", f"{te['pct']}%",
               "Cobertura territorial")
    add_bignum(slide, x1, Inches(3.85), card_w, card_h,
               el["geral"]["total"], "reconhecimentos", "Elogios + LMP + LOU (semestre)")
    add_bignum(slide, x2, Inches(3.85), card_w, card_h,
               f"{mm['geral']['pct_baixadas']}%", f"{mm['geral']['baixada']} viaturas",
               "Taxa de baixadas", cor=cor_pct_baixadas(mm['geral']['pct_baixadas']))

    add_text(slide, MARGIN, Inches(6.0), SLIDE_W - 2 * MARGIN, Inches(1.0),
             "Nas próximas páginas: cada unidade (Sede + 4 SGBs) mostra Q1 → Q2 → Consolidado do semestre.",
             font=FONT_CORPO, size=11, italic=True, color=COR_TEXTO_MUTED)
    add_footer(slide, f"11º GB — {p['label_longo']}")


def slide_divisor(prs, nome_entidade, subtitulo):
    slide = _blank(prs)
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = COR_TEXTO
    bg.line.fill.background()
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.5), SLIDE_H)
    bar.fill.solid(); bar.fill.fore_color.rgb = COR_ACENTO
    bar.line.fill.background()

    add_text(slide, Inches(1.2), Inches(3.0), Inches(11), Inches(0.5),
             "UNIDADE", font=FONT_CORPO, size=14, bold=True, color=COR_ACENTO_CLARO)
    add_text(slide, Inches(1.2), Inches(3.5), Inches(11), Inches(1.5),
             nome_entidade, font=FONT_TITULO, size=54, color=COR_BG)
    add_text(slide, Inches(1.2), Inches(5.0), Inches(11), Inches(0.5),
             subtitulo, font=FONT_TITULO, size=22, italic=True, color=COR_ACENTO_CLARO)


# ==========================================================================
# SLIDE POR ENTIDADE + PERÍODO (1 slide por trimestre)
# ==========================================================================

def slide_entidade_trimestre(prs, dados_q, entidade_chave, entidade_nome, n):
    slide = _blank(prs)
    p = dados_q["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}",
                f"{entidade_nome.upper()}  ·  {p['label_longo'].upper()}")
    add_titulo_slide(slide, f"{entidade_nome} — {p['label_longo']}.")

    k = kpis_entidade(dados_q, entidade_chave)

    card_h = Inches(1.7); card_w = Inches(3.0); gap = Inches(0.15)

    # Linha 1 — Efetivo, Operacional, Absenteísmo, Viaturas Operando
    add_bignum(slide, MARGIN, Inches(1.9), card_w, card_h,
               k["total"] if k["total"] else "—", "militares", "Efetivo ativo")
    add_bignum(slide, MARGIN + card_w + gap, Inches(1.9), card_w, card_h,
               f"{k['operacional_pct']}%" if k["operacional_pct"] else "—",
               "operacional", "Empregabilidade",
               cor=cor_pct_operacional(k["operacional_pct"]))
    add_bignum(slide, MARGIN + 2*(card_w + gap), Inches(1.9), card_w, card_h,
               f"{k['absenteismo_pct']}%" if k["absenteismo_pct"] is not None else "—",
               f"{k['em_lts']} em LTS", "Absenteísmo",
               cor=cor_pct_absenteismo(k["absenteismo_pct"]))
    if k["viaturas_operando"] is not None:
        add_bignum(slide, MARGIN + 3*(card_w + gap), Inches(1.9), card_w, card_h,
                   k["viaturas_operando"], f"de {k['viaturas_total']}", "Viaturas operando",
                   cor=COR_BOM)
    else:
        add_placeholder(slide, MARGIN + 3*(card_w + gap), Inches(1.9), card_w, card_h,
                        "Viaturas", "Frota não estratificada por Sede")

    # Linha 2 — Elogios, LMP, Idade média frota
    y2 = Inches(3.85)
    add_bignum(slide, MARGIN, y2, card_w, card_h,
               k["elogios"], "ELO", "Elogios no trimestre")
    add_bignum(slide, MARGIN + card_w + gap, y2, card_w, card_h,
               k["lmp"], "LMP", "Láureas no trimestre")
    if k["idade_media"] is not None:
        add_bignum(slide, MARGIN + 2*(card_w + gap), y2, card_w, card_h,
                   f"{k['idade_media']}", "anos", "Idade média frota",
                   cor=cor_idade(k["idade_media"]))
    if k["pct_baixadas"] is not None:
        add_bignum(slide, MARGIN + 3*(card_w + gap), y2, card_w, card_h,
                   f"{k['pct_baixadas']}%", f"{k['viaturas_baixadas']} vtr",
                   "Taxa de baixadas",
                   cor=cor_pct_baixadas(k["pct_baixadas"]))

    add_footer(slide, f"{entidade_nome} — {p['label_longo']}")


# ==========================================================================
# SLIDE CONSOLIDADO Q1 vs Q2 vs SEMESTRE
# ==========================================================================

def slide_entidade_consolidado(prs, dados_qa, dados_qb, dados_s,
                                entidade_chave, entidade_nome, n):
    slide = _blank(prs)
    p_s = dados_s["periodo"]
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{n:02d}",
                f"{entidade_nome.upper()}  ·  CONSOLIDADO {p_s['label_curto']}")
    add_titulo_slide(slide, f"{entidade_nome} — comparativo {p_s['label_longo'].lower()}.")

    ka = kpis_entidade(dados_qa, entidade_chave)
    kb = kpis_entidade(dados_qb, entidade_chave)
    ks = kpis_entidade(dados_s, entidade_chave)

    la = dados_qa["periodo"]["label_curto"]
    lb = dados_qb["periodo"]["label_curto"]
    ls = p_s["label_curto"]

    # Tabela comparativa Q1 | Q2 | Semestre | Δ (Q2-Q1)
    linhas = []

    def _fmt(v, sufixo=""):
        if v is None: return "—"
        return f"{v}{sufixo}"

    # Efetivo ativo (foto no fim de cada período — mesma coisa se snapshot)
    linhas.append(["Efetivo ativo",
                   _fmt(ka["total"]), _fmt(kb["total"]), _fmt(ks["total"]),
                   delta_str(kb["total"], ka["total"])[0]])

    # % Operacional (cod ...1) — foto atual
    linhas.append(["% empregado operacional",
                   _fmt(ka["operacional_pct"], "%"),
                   _fmt(kb["operacional_pct"], "%"),
                   _fmt(ks["operacional_pct"], "%"),
                   delta_str(kb["operacional_pct"], ka["operacional_pct"], pct=True)[0]])

    # Absenteísmo LTS
    linhas.append(["% absenteísmo LTS",
                   _fmt(ka["absenteismo_pct"], "%"),
                   _fmt(kb["absenteismo_pct"], "%"),
                   _fmt(ks["absenteismo_pct"], "%"),
                   delta_str(kb["absenteismo_pct"], ka["absenteismo_pct"], pct=True)[0]])

    # Elogios (soma de fluxo → semestre = soma dos trimestres)
    linhas.append(["Elogios (ELO)",
                   _fmt(ka["elogios"]), _fmt(kb["elogios"]), _fmt(ks["elogios"]),
                   delta_str(kb["elogios"], ka["elogios"])[0]])
    linhas.append(["LMP",
                   _fmt(ka["lmp"]), _fmt(kb["lmp"]), _fmt(ks["lmp"]),
                   delta_str(kb["lmp"], ka["lmp"])[0]])

    # Frota (foto — trimestre e semestre são iguais)
    if ka["viaturas_total"] is not None:
        linhas.append(["Viaturas — total",
                       _fmt(ka["viaturas_total"]), _fmt(kb["viaturas_total"]),
                       _fmt(ks["viaturas_total"]), "="])
        linhas.append(["% baixadas",
                       _fmt(ka["pct_baixadas"], "%"), _fmt(kb["pct_baixadas"], "%"),
                       _fmt(ks["pct_baixadas"], "%"),
                       delta_str(kb["pct_baixadas"], ka["pct_baixadas"], pct=True)[0]])
        linhas.append(["Frota — idade média (anos)",
                       _fmt(ka["idade_media"]), _fmt(kb["idade_media"]),
                       _fmt(ks["idade_media"]),
                       delta_str(kb["idade_media"], ka["idade_media"])[0]])

    add_tabela(slide, MARGIN, Inches(1.9), SLIDE_W - 2 * MARGIN,
               ["Indicador", la, lb, ls, f"Δ ({lb} vs {la})"],
               linhas,
               largura_col=[Inches(4.3), Inches(2.0), Inches(2.0),
                            Inches(2.0), Inches(1.8)])

    # Nota interpretativa
    y_nota = Inches(1.9) + Inches(0.32 * (len(linhas) + 1)) + Inches(0.4)
    add_text(slide, MARGIN, y_nota, SLIDE_W - 2 * MARGIN, Inches(1.2),
             "Notas de leitura:\n"
             "  • Indicadores de FOTO (efetivo, operacional, frota) refletem o estado ao final de cada período.\n"
             "  • Indicadores de FLUXO (elogios, LMP, LTS) somam ocorrências dentro do período — o semestre é a soma dos dois trimestres.\n"
             "  • Δ compara o Q2 contra o Q1. Verde = evolução positiva, vermelho = piora.",
             font=FONT_CORPO, size=10, italic=True, color=COR_TEXTO_MUTED)
    add_footer(slide, f"{entidade_nome} — Consolidado {p_s['label_longo']}")


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

    entidades = [
        ("EM",    "Sede — Estado-Maior"),
        ("1_SGB", "1º SGB"),
        ("2_SGB", "2º SGB"),
        ("3_SGB", "3º SGB"),
        ("4_SGB", "4º SGB"),
    ]

    for chave, nome in entidades:
        subtitulo = f"Q{trim_a} → Q{trim_b} → Consolidado S{num_sem}/{ano}"
        slide_divisor(prs, nome, subtitulo)
        # nota: divisor não conta no número de slide "operacional"

        slide_entidade_trimestre(prs, dados_qa, chave, nome, n);      n += 1
        slide_entidade_trimestre(prs, dados_qb, chave, nome, n);      n += 1
        slide_entidade_consolidado(prs, dados_qa, dados_qb, dados_s,
                                   chave, nome, n);                   n += 1

    slide_fechamento(prs, dados_s)

    arquivo = f"Relatorio_Semestral_Comparativo_{ano}-S{num_sem}_11GB.pptx"
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), arquivo)
    prs.save(caminho)
    total_slides = len(prs.slides)
    print(f">> Gerado: {caminho}  ({total_slides} slides)")
    return caminho


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python gerar_semestre_comparativo.py <ANO> <NUM_SEM>")
        print("     python gerar_semestre_comparativo.py 2026 1")
        sys.exit(1)
    gerar(int(sys.argv[1]), int(sys.argv[2]))
