"""
Gerador do Relatório Anual do 11º GB (formato PPTX).

Uso:   python gerar_anual.py [ANO]
       (default: ano corrente)

Estrutura:
  Capa
  Sumário Executivo
  Parte I — SEDE (B/1, B/3, B/5, UGE, MOTOMEC, PJMD, SAT)
  Parte II — SGBs (comparativo + detalhe de cada)
  Fechamento

KPIs sem fonte no banco ficam marcados 'A INTEGRAR — próxima versão'.
"""

import sys, os
from datetime import date
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dados import carregar_tudo

import re

# ==========================================================================
# NORMALIZAÇÃO DE NOMES DE SGB
# Efetivo usa "1ºSgb", Motomec usa "1ºSGB", Elogios usa "1° SGB", etc.
# Este helper devolve sempre a mesma chave canônica pra qualquer variação.
# ==========================================================================

def norm_sgb(s):
    """Normaliza qualquer variação de nome de SGB pra chave canônica.
       Ex: '1ºSgb', '1º SGB', '1° SGB', '1SGB' → '1_SGB'
           'EM', 'Sede', 'SEDE'                → 'EM'
    """
    if not s:
        return None
    s = str(s).upper().replace("°", "º").strip()
    if "SEDE" in s or s == "EM":
        return "EM"
    m = re.match(r"(\d)\s*º?\s*S?GB", s)
    return f"{m.group(1)}_SGB" if m else s


def buscar_por_sgb(lista, chave_canonica, campo_sgb="lotacao"):
    """Encontra o item da lista cujo campo SGB normalizado bate com a chave."""
    for item in lista or []:
        if norm_sgb(item.get(campo_sgb)) == chave_canonica:
            return item
    return None


# ==========================================================================
# PALETA E TIPOGRAFIA
# ==========================================================================

# Cores derivadas do painel do app: firebrick + neutros
COR_ACENTO       = RGBColor(0xB2, 0x22, 0x22)   # firebrick — títulos e destaques
COR_ACENTO_ESC   = RGBColor(0x7A, 0x17, 0x17)   # vermelho escuro
COR_ACENTO_CLARO = RGBColor(0xE8, 0xB0, 0xB0)   # vermelho pastel — fundos suaves
COR_TEXTO        = RGBColor(0x1F, 0x23, 0x28)   # quase preto
COR_TEXTO_DIM    = RGBColor(0x6E, 0x77, 0x81)   # cinza médio
COR_TEXTO_MUTED  = RGBColor(0x8B, 0x94, 0x9E)   # cinza claro
COR_BG           = RGBColor(0xFF, 0xFF, 0xFF)   # branco
COR_BG_SUAVE     = RGBColor(0xF6, 0xF8, 0xFA)   # cinza-branco pra cards
COR_LINHA        = RGBColor(0xD0, 0xD7, 0xDE)   # divisores
COR_BOM          = RGBColor(0x1F, 0x88, 0x3D)   # verde — good
COR_ATENCAO      = RGBColor(0xBF, 0x83, 0x00)   # amarelo — warning
COR_CRITICO      = RGBColor(0xCF, 0x22, 0x2E)   # vermelho — critical
COR_INDISP       = RGBColor(0xB0, 0xB0, 0xB0)   # cinza — sem dado

FONT_TITULO   = "Cambria"           # serif institucional
FONT_CORPO    = "Calibri"           # sans padrão Office
FONT_DADOS    = "Consolas"          # mono pra números


# ==========================================================================
# DIMENSÕES (LAYOUT WIDE 13.3" × 7.5")
# ==========================================================================

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN  = Inches(0.6)


# ==========================================================================
# HELPERS DE CONSTRUÇÃO
# ==========================================================================

def _blank_slide(prs):
    """Adiciona um slide em branco (layout 6 = blank)."""
    return prs.slides.add_slide(prs.slide_layouts[6])


def add_text(slide, x, y, w, h, texto, *, font=FONT_CORPO, size=14,
             bold=False, color=COR_TEXTO, align=PP_ALIGN.LEFT,
             anchor=MSO_ANCHOR.TOP, italic=False):
    """Cria uma caixa de texto simples com estilos."""
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.margin_left = tf.margin_right = Emu(0)
    tf.margin_top = tf.margin_bottom = Emu(0)
    tf.word_wrap = True
    tf.vertical_anchor = anchor

    lines = str(texto).split("\n")
    for i, line in enumerate(lines):
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
    """Cria um retângulo simples (fundo)."""
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(0.5)
    shp.shadow.inherit = False
    return shp


def add_eyebrow(slide, x, y, numero, texto):
    """Sobretítulo tipo '01 / 15  ·  SEÇÃO' com filete vermelho embaixo."""
    add_text(slide, x, y, Inches(6), Inches(0.28),
             f"{numero}   {texto}",
             font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    # Filete vermelho
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y + Inches(0.30), Inches(0.8), Emu(15000))
    line.fill.solid(); line.fill.fore_color.rgb = COR_ACENTO
    line.line.fill.background()


def add_titulo_slide(slide, texto, y=Inches(0.9), size=32):
    """Título principal do slide (serif grande)."""
    add_text(slide, MARGIN, y, SLIDE_W - 2 * MARGIN, Inches(0.85),
             texto, font=FONT_TITULO, size=size, bold=False,
             color=COR_TEXTO, align=PP_ALIGN.LEFT)


def add_footer(slide, texto="11º GB — Relatório Anual"):
    """Rodapé discreto."""
    add_text(slide, MARGIN, SLIDE_H - Inches(0.35),
             SLIDE_W - 2 * MARGIN, Inches(0.25),
             texto, font=FONT_CORPO, size=9, color=COR_TEXTO_MUTED)


def add_bignum(slide, x, y, w, h, valor, unidade, label, cor=None,
               font_valor=None):
    """Card com número grande + unidade + rótulo pequeno.
    Layout responsivo à altura do card — evita sobreposição."""
    add_rect(slide, x, y, w, h, fill=COR_BG_SUAVE)
    cor_valor = cor or COR_ACENTO

    pad_x     = Inches(0.25)
    pad_top   = Inches(0.15)
    pad_bot   = Inches(0.12)
    label_h   = Inches(0.28)
    unidade_h = Inches(0.24) if unidade else Inches(0)
    gap       = Inches(0.05)

    # Valor ocupa espaço restante
    valor_h = h - label_h - unidade_h - pad_top - pad_bot - gap * (2 if unidade else 1)

    # Auto-scale da fonte do valor com base na altura disponível
    if font_valor is None:
        # Arithmetic com Length em python-pptx pode retornar int EMU — normaliza:
        emu_per_inch = 914400
        h_emu = int(valor_h) if not hasattr(valor_h, 'emu') else valor_h.emu
        h_in = h_emu / emu_per_inch
        if   h_in < 0.55: font_valor = 22
        elif h_in < 0.75: font_valor = 28
        elif h_in < 0.95: font_valor = 34
        elif h_in < 1.15: font_valor = 40
        else:             font_valor = 46

    # Valor (centralizado verticalmente no seu box)
    y_cursor = y + pad_top
    add_text(slide, x + pad_x, y_cursor, w - 2 * pad_x, valor_h,
             str(valor), font=FONT_TITULO, size=font_valor,
             color=cor_valor, anchor=MSO_ANCHOR.MIDDLE)
    y_cursor += valor_h + gap

    if unidade:
        add_text(slide, x + pad_x, y_cursor, w - 2 * pad_x, unidade_h,
                 unidade, font=FONT_CORPO, size=11, color=COR_TEXTO_DIM)

    # Label sempre encostado no fundo do card
    add_text(slide, x + pad_x, y + h - pad_bot - label_h,
             w - 2 * pad_x, label_h,
             label.upper(), font=FONT_CORPO, size=9, bold=True,
             color=COR_TEXTO_MUTED)


def add_semaforo(slide, x, y, label, valor_str, cor):
    """Bolinha colorida + texto — indicador visual de status."""
    ball = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y + Inches(0.06),
                                    Inches(0.16), Inches(0.16))
    ball.fill.solid(); ball.fill.fore_color.rgb = cor
    ball.line.fill.background()
    add_text(slide, x + Inches(0.25), y, Inches(3), Inches(0.3),
             f"{label}: {valor_str}", font=FONT_CORPO, size=11, bold=True,
             color=COR_TEXTO)


def add_chart_barras(slide, x, y, w, h, titulo, categorias, valores,
                     cor=None, formato="normal"):
    """Adiciona chart de barras verticais com título embutido."""
    chart_data = CategoryChartData()
    chart_data.categories = [str(c) for c in categorias]
    chart_data.add_series("", valores)
    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, x, y, w, h, chart_data
    )
    chart = chart_frame.chart
    chart.has_title = True
    chart.chart_title.text_frame.text = titulo
    for p in chart.chart_title.text_frame.paragraphs:
        for r in p.runs:
            r.font.size = Pt(12)
            r.font.name = FONT_CORPO
            r.font.bold = True
            r.font.color.rgb = COR_TEXTO
    chart.has_legend = False

    plot = chart.plots[0]
    plot.has_data_labels = True
    plot.data_labels.font.size = Pt(10)
    plot.data_labels.font.name = FONT_CORPO
    plot.data_labels.font.color.rgb = COR_TEXTO

    if formato == "pct":
        plot.data_labels.number_format = "0.0%"
    elif formato == "moeda":
        plot.data_labels.number_format = 'R$ #,##0'
    else:
        plot.data_labels.number_format = "0"

    # Cor da série
    fill = plot.series[0].format.fill
    fill.solid()
    fill.fore_color.rgb = cor or COR_ACENTO


def add_placeholder_a_integrar(slide, x, y, w, h, titulo, motivo="Fonte a ser integrada"):
    """Placeholder pra KPIs que não temos dado ainda."""
    add_rect(slide, x, y, w, h, fill=COR_BG_SUAVE, line=COR_LINHA)
    add_text(slide, x + Inches(0.3), y + Inches(0.3), w - Inches(0.6), Inches(0.3),
             titulo.upper(), font=FONT_CORPO, size=10, bold=True,
             color=COR_TEXTO_MUTED)
    add_text(slide, x + Inches(0.3), y + Inches(0.7), w - Inches(0.6), Inches(0.6),
             "A INTEGRAR", font=FONT_TITULO, size=28, italic=True,
             color=COR_INDISP)
    add_text(slide, x + Inches(0.3), y + h - Inches(0.55),
             w - Inches(0.6), Inches(0.4),
             motivo, font=FONT_CORPO, size=10, italic=True,
             color=COR_TEXTO_MUTED)


def add_tabela_simples(slide, x, y, w, cabecalhos, linhas, largura_col=None):
    """Tabela minimalista alinhada à esquerda."""
    n_col = len(cabecalhos)
    n_row = len(linhas) + 1
    table = slide.shapes.add_table(n_row, n_col, x, y, w, Inches(0.35 * n_row)).table

    if largura_col:
        for i, lc in enumerate(largura_col):
            table.columns[i].width = lc

    # Cabeçalho
    for j, h in enumerate(cabecalhos):
        cell = table.cell(0, j)
        cell.fill.solid(); cell.fill.fore_color.rgb = COR_BG_SUAVE
        cell.text_frame.text = str(h)
        for p in cell.text_frame.paragraphs:
            for r in p.runs:
                r.font.name = FONT_CORPO
                r.font.size = Pt(10)
                r.font.bold = True
                r.font.color.rgb = COR_TEXTO_MUTED

    # Linhas
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


# ==========================================================================
# SLIDES
# ==========================================================================

def slide_capa(prs, ano):
    slide = _blank_slide(prs)

    # Barra vertical vermelha à esquerda
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.5), SLIDE_H)
    bar.fill.solid(); bar.fill.fore_color.rgb = COR_ACENTO
    bar.line.fill.background()

    add_text(slide, Inches(1.2), Inches(2.4), Inches(11), Inches(0.4),
             "11º GRUPAMENTO DE BOMBEIROS  ·  PMESP",
             font=FONT_CORPO, size=13, bold=True, color=COR_TEXTO_MUTED)

    add_text(slide, Inches(1.2), Inches(2.8), Inches(11), Inches(1.4),
             "Relatório Anual",
             font=FONT_TITULO, size=64, color=COR_TEXTO)

    add_text(slide, Inches(1.2), Inches(4.3), Inches(11), Inches(0.9),
             f"Exercício {ano}",
             font=FONT_TITULO, size=42, italic=True, color=COR_ACENTO)

    add_text(slide, Inches(1.2), Inches(6.5), Inches(11), Inches(0.4),
             f"Vale do Paraíba  ·  Litoral Norte  ·  emitido em {date.today().strftime('%d/%m/%Y')}",
             font=FONT_CORPO, size=11, color=COR_TEXTO_MUTED)


def slide_sumario_executivo(prs, dados, num_slide):
    slide = _blank_slide(prs)
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{num_slide:02d}", "SUMÁRIO EXECUTIVO")
    add_titulo_slide(slide, "Foto do 11º GB.")

    # 6 bignums em 2 linhas × 3 colunas
    ef = dados["efetivo"]
    sa = dados["saude"]
    mm = dados["motomec"]
    mf = dados["mapa_forca"]
    ug = dados["uge"]
    el = dados["elogios"]

    total_ativos = ef["total_ativos"]
    ias_em_dia = next((r for r in sa["ias_por_situacao"] if r["situacao_ias"] == "EM DIA"), None)
    pct_em_dia = f"{ias_em_dia['percentual']}%" if ias_em_dia else "—"

    op = mf.get("geral", {}).get("operando", "—") if mf.get("disponivel") else "—"

    card_w = Inches(4.0)
    card_h = Inches(1.8)
    gap = Inches(0.15)
    row_y1 = Inches(2.1)
    row_y2 = Inches(4.05)

    x0 = MARGIN
    x1 = x0 + card_w + gap
    x2 = x1 + card_w + gap

    add_bignum(slide, x0, row_y1, card_w, card_h, total_ativos, "militares", "Efetivo ativo")
    add_bignum(slide, x1, row_y1, card_w, card_h, pct_em_dia, "IAS em dia", "Saúde")
    add_bignum(slide, x2, row_y1, card_w, card_h, sa["total_restricoes"], "vigentes", "Restrições")

    add_bignum(slide, x0, row_y2, card_w, card_h, op, "viaturas hoje", "Operacional")
    add_bignum(slide, x1, row_y2, card_w, card_h, mm["geral"]["total"], "na frota", "Motomec")
    add_bignum(slide, x2, row_y2, card_w, card_h, el["geral"]["total"], "no ano", "Elogios / Láureas")

    # Rodapé com destaque + atenção (semáforos)
    y = Inches(6.05)
    add_text(slide, MARGIN, y, Inches(3), Inches(0.3),
             "DESTAQUES", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    add_semaforo(slide, MARGIN, y + Inches(0.35), "IAS em dia", pct_em_dia, COR_BOM)
    add_semaforo(slide, MARGIN, y + Inches(0.65), "Viaturas operando", str(op), COR_BOM)

    add_text(slide, Inches(6.8), y, Inches(3), Inches(0.3),
             "PONTOS DE ATENÇÃO", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    add_semaforo(slide, Inches(6.8), y + Inches(0.35),
                 "IAS atrasadas/sem IAS",
                 str(sum(r["quantidade"] for r in sa["ias_por_situacao"]
                         if r["situacao_ias"] in ("ATRASADA", "SEM IAS"))),
                 COR_ATENCAO)
    add_semaforo(slide, Inches(6.8), y + Inches(0.65),
                 "Idade média frota",
                 f"{mm['geral']['idade_media']} anos", COR_ATENCAO)

    add_footer(slide)


# ==========================================================================
# DIVISOR DE PARTE
# ==========================================================================

def slide_divisor(prs, titulo_parte, subtitulo):
    slide = _blank_slide(prs)
    # Fundo pintado
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = COR_TEXTO
    bg.line.fill.background()

    # Barra vertical vermelha
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.5), SLIDE_H)
    bar.fill.solid(); bar.fill.fore_color.rgb = COR_ACENTO
    bar.line.fill.background()

    add_text(slide, Inches(1.2), Inches(3.0), Inches(11), Inches(0.5),
             titulo_parte.upper(),
             font=FONT_CORPO, size=14, bold=True,
             color=COR_ACENTO_CLARO)

    add_text(slide, Inches(1.2), Inches(3.5), Inches(11), Inches(1.5),
             subtitulo,
             font=FONT_TITULO, size=54, color=COR_BG)


# ==========================================================================
# SLIDES POR SETOR (SEDE)
# ==========================================================================

def slide_sede_b1(prs, dados, num_slide):
    slide = _blank_slide(prs)
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{num_slide:02d}", "SEDE / B-1  ·  PESSOAL")
    add_titulo_slide(slide, "Efetivo e saúde do Estado-Maior.")

    em = next((r for r in dados["efetivo"]["por_lotacao"] if r["lotacao"] == "EM"), None)
    em_ias = next((r for r in dados["saude"]["ias_por_sgb"] if r["lotacao"] == "EM"), None)
    em_restr = next((r for r in dados["saude"]["restricoes_por_sgb"] if r["lotacao"] == "EM"), None)

    # 3 bignums no topo
    add_bignum(slide, MARGIN, Inches(1.9), Inches(3.9), Inches(1.7),
               em["qtd"] if em else "—", "militares no EM", "Efetivo ativo")
    if em_ias:
        pct_dia = round(100 * em_ias["em_dia"] / max(em_ias["total"], 1), 1)
        cor_ias = COR_BOM if pct_dia >= 90 else COR_ATENCAO if pct_dia >= 75 else COR_CRITICO
        add_bignum(slide, MARGIN + Inches(4.1), Inches(1.9), Inches(3.9), Inches(1.7),
                   f"{pct_dia}%", "IAS em dia", "Saúde do EM", cor=cor_ias)
    add_bignum(slide, MARGIN + Inches(8.2), Inches(1.9), Inches(3.9), Inches(1.7),
               em_restr["qtd"] if em_restr else 0, "militares",
               "Restrições vigentes",
               cor=COR_CRITICO if (em_restr and em_restr["qtd"] > 5) else COR_ATENCAO)

    # Tabela detalhada
    add_text(slide, MARGIN, Inches(3.7), Inches(6), Inches(0.3),
             "DETALHAMENTO DE IAS — EM", font=FONT_CORPO, size=10, bold=True,
             color=COR_TEXTO_MUTED)
    if em_ias:
        add_tabela_simples(slide, MARGIN, Inches(4.0), Inches(6),
                           ["Situação", "Qtd"],
                           [("EM DIA", em_ias["em_dia"]),
                            ("ATRASADA", em_ias["atrasada"]),
                            ("SEM IAS", em_ias["sem_ias"])])

    # Placeholder pra taxa absenteísmo
    add_placeholder_a_integrar(slide, Inches(7.4), Inches(4.0), Inches(5.3), Inches(2.0),
                                "Taxa de absenteísmo LTS",
                                "Requer histórico mensal — importar SIGS/afastamentos")
    add_footer(slide)


def slide_sede_b3(prs, num_slide):
    slide = _blank_slide(prs)
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{num_slide:02d}", "SEDE / B-3  ·  OPERAÇÕES")
    add_titulo_slide(slide, "Indicadores operacionais.")

    # 3 placeholders — dados não integrados ainda
    add_placeholder_a_integrar(slide, MARGIN, Inches(1.9), Inches(4.0), Inches(2.4),
                                "Taxa de ocupação territorial",
                                "Importar base de ocorrências (CBI)")
    add_placeholder_a_integrar(slide, MARGIN + Inches(4.2), Inches(1.9), Inches(4.0), Inches(2.4),
                                "Atendimento ≤ 20 min",
                                "Requer dado histórico de ocorrências")
    add_placeholder_a_integrar(slide, MARGIN + Inches(8.4), Inches(1.9), Inches(4.0), Inches(2.4),
                                "Vítimas fatais",
                                "Trânsito e incêndio — base COBOM")

    add_text(slide, MARGIN, Inches(4.7), Inches(10), Inches(0.5),
             "Nota:", font=FONT_CORPO, size=12, bold=True, color=COR_TEXTO)
    add_text(slide, MARGIN, Inches(5.0), Inches(11.5), Inches(1.5),
             "Os KPIs históricos de operações (2022–2025) constam da versão anterior deste relatório. "
             "Nesta versão automatizada, estes indicadores serão preenchidos a partir da próxima "
             "integração com o SGB Ocorrências e COBOM. Consultas ao vivo já disponíveis pela B.I.A. "
             "e pelo mapa de força operacional (Parte II).",
             font=FONT_CORPO, size=13, italic=True, color=COR_TEXTO_DIM)
    add_footer(slide)


def slide_sede_b5(prs, dados, num_slide):
    slide = _blank_slide(prs)
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{num_slide:02d}", "SEDE / B-5  ·  COMUNICAÇÃO E ENSINO")
    add_titulo_slide(slide, "Elogios, láureas e formação.")

    el = dados["elogios"]["geral"]
    # bignums
    total_militares = dados["efetivo"]["total_ativos"] or 1
    elog_por_bombeiro = round(el["elogios"] / total_militares, 2)

    add_bignum(slide, MARGIN, Inches(1.9), Inches(3.9), Inches(1.7),
               el["elogios"], "elogios", "Total ELO no ano")
    add_bignum(slide, MARGIN + Inches(4.1), Inches(1.9), Inches(3.9), Inches(1.7),
               f"{elog_por_bombeiro}", "por bombeiro", "Índice de reconhecimento")
    add_bignum(slide, MARGIN + Inches(8.2), Inches(1.9), Inches(3.9), Inches(1.7),
               el["lmp"], "LMP", "Láureas de mérito pessoal")

    # Tabela por SGB
    add_text(slide, MARGIN, Inches(3.7), Inches(6), Inches(0.3),
             "ELOGIOS POR SGB — ANO", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    linhas = [(r["sgb"], r["total"], r["elogios"], r["lmp"], r["louvor"])
              for r in dados["elogios"]["por_sgb"]]
    add_tabela_simples(slide, MARGIN, Inches(4.0), Inches(6),
                       ["SGB", "Total", "ELO", "LMP", "LOU"], linhas)

    # Placeholder BB Escola
    add_placeholder_a_integrar(slide, Inches(7.4), Inches(4.0), Inches(5.3), Inches(2.0),
                                "Programa Bombeiro na Escola",
                                "Requer base de turmas/alunos — B/5")
    add_footer(slide)


def slide_sede_uge(prs, dados, num_slide):
    slide = _blank_slide(prs)
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{num_slide:02d}", "SEDE / UGE  ·  CONTROLE DE PROCESSOS")
    add_titulo_slide(slide, "Processos administrativos e financeiro.")

    u = dados["uge"]["geral"]
    add_bignum(slide, MARGIN, Inches(1.9), Inches(3.9), Inches(1.7),
               u["total"], "processos", "Total no ano")
    add_bignum(slide, MARGIN + Inches(4.1), Inches(1.9), Inches(3.9), Inches(1.7),
               u["em_andamento"], "em andamento", "Andamento",
               cor=COR_ATENCAO if u["em_andamento"] > 5 else COR_BOM)
    add_bignum(slide, MARGIN + Inches(8.2), Inches(1.9), Inches(3.9), Inches(1.7),
               f"R$ {float(u['total_empenhado'])/1000:.0f}k",
               "empenhado", "Valor total")

    # Tabela status
    add_text(slide, MARGIN, Inches(3.7), Inches(6), Inches(0.3),
             "PROCESSOS POR STATUS", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    add_tabela_simples(slide, MARGIN, Inches(4.0), Inches(6),
                       ["Status", "Qtd"],
                       [("Em andamento", u["em_andamento"]),
                        ("Encerrado",    u["encerrado"]),
                        ("Cancelado",    u["cancelado"])])

    add_text(slide, Inches(7.4), Inches(3.7), Inches(6), Inches(0.3),
             "FINANCEIRO (R$)", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    add_tabela_simples(slide, Inches(7.4), Inches(4.0), Inches(5.3),
                       ["Rubrica", "Valor"],
                       [("Empenhado",  f"R$ {float(u['total_empenhado']):,.2f}"),
                        ("Liquidado",  f"R$ {float(u['total_liquidado']):,.2f}")])

    add_footer(slide)


def slide_sede_pjmd(prs, num_slide):
    slide = _blank_slide(prs)
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{num_slide:02d}", "SEDE / PJMD  ·  JUSTIÇA E DISCIPLINA")
    add_titulo_slide(slide, "Ocorrências disciplinares.")

    add_placeholder_a_integrar(slide, MARGIN, Inches(1.9), Inches(6.0), Inches(2.6),
                                "Acidentes de trânsito com bombeiro na folga",
                                "Integrar base PJMD")
    add_placeholder_a_integrar(slide, Inches(7.0), Inches(1.9), Inches(5.7), Inches(2.6),
                                "Acidentes envolvendo viatura",
                                "Integrar base PJMD")
    add_footer(slide)


def slide_sede_motomec(prs, dados, num_slide):
    slide = _blank_slide(prs)
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{num_slide:02d}", "SEDE / MOTOMEC  ·  FROTA")
    add_titulo_slide(slide, "Viaturas: composição e idade da frota.")

    mm = dados["motomec"]["geral"]

    add_bignum(slide, MARGIN, Inches(1.9), Inches(3.0), Inches(1.7),
               mm["total"], "viaturas", "Frota total")
    add_bignum(slide, MARGIN + Inches(3.2), Inches(1.9), Inches(3.0), Inches(1.7),
               mm["operando"], "operando", "Em operação",
               cor=COR_BOM)
    add_bignum(slide, MARGIN + Inches(6.4), Inches(1.9), Inches(3.0), Inches(1.7),
               mm["baixada"], "baixadas", "Baixa",
               cor=COR_ATENCAO if mm["pct_baixadas"] >= 15 else COR_TEXTO)
    add_bignum(slide, MARGIN + Inches(9.6), Inches(1.9), Inches(3.0), Inches(1.7),
               f"{mm['idade_media']}", "anos", "Idade média",
               cor=COR_ATENCAO if mm["idade_media"] >= 10 else COR_BOM)

    # Chart por SGB
    sgb_data = dados["motomec"]["por_sgb"]
    cats = [r["sgb"] for r in sgb_data]
    vals = [r["baixada"] for r in sgb_data]
    add_chart_barras(slide, MARGIN, Inches(3.7), Inches(6), Inches(3.2),
                     "Viaturas baixadas por SGB", cats, vals,
                     cor=COR_ACENTO)

    # Tabela idade por SGB
    add_text(slide, Inches(7.4), Inches(3.7), Inches(5.3), Inches(0.3),
             "IDADE MÉDIA POR SGB", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    linhas = [(r["sgb"], f"{r['idade_media']} anos", r["operando"], r["total"])
              for r in sgb_data]
    add_tabela_simples(slide, Inches(7.4), Inches(4.0), Inches(5.3),
                       ["SGB", "Idade média", "Operando", "Total"], linhas)
    add_footer(slide)


def slide_sede_sat(prs, num_slide):
    slide = _blank_slide(prs)
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{num_slide:02d}", "SEDE / SAT  ·  ATIVIDADE TÉCNICA")
    add_titulo_slide(slide, "Fiscalizações e análises.")

    add_placeholder_a_integrar(slide, MARGIN, Inches(1.9), Inches(4.0), Inches(2.4),
                                "Dias para análise", "Base SAT")
    add_placeholder_a_integrar(slide, MARGIN + Inches(4.2), Inches(1.9), Inches(4.0), Inches(2.4),
                                "Dias para vistoria", "Base SAT")
    add_placeholder_a_integrar(slide, MARGIN + Inches(8.4), Inches(1.9), Inches(4.0), Inches(2.4),
                                "Fiscalizações realizadas", "Base SAT")
    add_footer(slide)


# ==========================================================================
# SGBs
# ==========================================================================

def slide_sgb_comparativo(prs, dados, num_slide):
    slide = _blank_slide(prs)
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{num_slide:02d}", "SGBs  ·  COMPARATIVO GERAL")
    add_titulo_slide(slide, "Quatro subgrupamentos, lado a lado.")

    # 4 SGBs (na ordem correta), chaves canônicas normalizadas
    sgbs = [("1_SGB", "1º SGB"),
            ("2_SGB", "2º SGB"),
            ("3_SGB", "3º SGB"),
            ("4_SGB", "4º SGB")]

    ef    = dados["efetivo"]["por_lotacao"]
    ias   = dados["saude"]["ias_por_sgb"]
    restr = dados["saude"]["restricoes_por_sgb"]
    mm    = dados["motomec"]["por_sgb"]
    el    = dados["elogios"]["por_sgb"]

    cabecalhos = ["Indicador"] + [t[1] for t in sgbs]
    linhas = []

    # Efetivo ativo
    row = ["Efetivo ativo"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(ef, chave, "lotacao")
        row.append(str(r["qtd"]) if r else "—")
    linhas.append(row)

    # IAS em dia
    row = ["IAS em dia"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(ias, chave, "lotacao")
        if r and r["total"]:
            row.append(f"{round(100 * r['em_dia'] / r['total'], 1)}%")
        else:
            row.append("—")
    linhas.append(row)

    # IAS atrasada + sem IAS
    row = ["IAS atrasada + sem IAS"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(ias, chave, "lotacao")
        row.append(str((r["atrasada"] + r["sem_ias"]) if r else 0))
    linhas.append(row)

    # Restrições vigentes
    row = ["Restrições vigentes"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(restr, chave, "lotacao")
        row.append(str(r["qtd"] if r else 0))
    linhas.append(row)

    # Viaturas total
    row = ["Viaturas total"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(mm, chave, "sgb")
        row.append(str(r["total"]) if r else "—")
    linhas.append(row)

    # Viaturas operando
    row = ["Viaturas operando"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(mm, chave, "sgb")
        row.append(str(r["operando"]) if r else "—")
    linhas.append(row)

    # Idade média frota
    row = ["Frota — idade média"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(mm, chave, "sgb")
        row.append(f"{r['idade_media']} anos" if r and r["idade_media"] else "—")
    linhas.append(row)

    # Elogios no ano
    row = ["Elogios no ano"]
    for chave, _ in sgbs:
        r = buscar_por_sgb(el, chave, "sgb")
        row.append(str(r["total"]) if r else "—")
    linhas.append(row)

    add_tabela_simples(slide, MARGIN, Inches(1.9), SLIDE_W - 2 * MARGIN,
                       cabecalhos, linhas,
                       largura_col=[Inches(3.5), Inches(2.15), Inches(2.15),
                                    Inches(2.15), Inches(2.15)])
    add_footer(slide)


def slide_sgb_detalhe(prs, sgb_chave, sgb_completo, dados, num_slide):
    """1 slide de detalhe por SGB. sgb_chave = chave canônica (ex: '1_SGB')."""
    slide = _blank_slide(prs)
    add_eyebrow(slide, MARGIN, Inches(0.5), f"{num_slide:02d}", f"SGBs  ·  {sgb_completo}")
    add_titulo_slide(slide, f"{sgb_completo} em detalhe.")

    ef    = buscar_por_sgb(dados["efetivo"]["por_lotacao"], sgb_chave, "lotacao")
    ias   = buscar_por_sgb(dados["saude"]["ias_por_sgb"], sgb_chave, "lotacao")
    restr = buscar_por_sgb(dados["saude"]["restricoes_por_sgb"], sgb_chave, "lotacao")
    mm    = buscar_por_sgb(dados["motomec"]["por_sgb"], sgb_chave, "sgb")
    el    = buscar_por_sgb(dados["elogios"]["por_sgb"], sgb_chave, "sgb")

    # Linha superior: 4 bignums (altura maior pra caber)
    card_h = Inches(1.7)
    add_bignum(slide, MARGIN, Inches(1.9), Inches(3.0), card_h,
               ef["qtd"] if ef else "—", "militares", "Efetivo")
    if ias and ias["total"]:
        pct = round(100 * ias["em_dia"] / ias["total"], 1)
        cor = COR_BOM if pct >= 90 else COR_ATENCAO if pct >= 75 else COR_CRITICO
        add_bignum(slide, MARGIN + Inches(3.2), Inches(1.9), Inches(3.0), card_h,
                   f"{pct}%", "IAS em dia", "Saúde", cor=cor)
    else:
        add_bignum(slide, MARGIN + Inches(3.2), Inches(1.9), Inches(3.0), card_h,
                   "—", "IAS em dia", "Saúde")
    add_bignum(slide, MARGIN + Inches(6.4), Inches(1.9), Inches(3.0), card_h,
               restr["qtd"] if restr else 0, "com restrição", "Indisponíveis",
               cor=COR_ATENCAO if (restr and restr["qtd"] > 3) else COR_TEXTO)
    add_bignum(slide, MARGIN + Inches(9.6), Inches(1.9), Inches(3.0), card_h,
               mm["operando"] if mm else "—", "operando", "Viaturas hoje",
               cor=COR_BOM)

    # Linha do meio: detalhe IAS + Motomec
    add_text(slide, MARGIN, Inches(3.7), Inches(6), Inches(0.3),
             "SITUAÇÃO DA IAS", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    if ias:
        add_tabela_simples(slide, MARGIN, Inches(4.0), Inches(6),
                           ["Situação", "Qtd", "%"],
                           [("EM DIA", ias["em_dia"], f"{round(100*ias['em_dia']/max(ias['total'],1),1)}%"),
                            ("ATRASADA", ias["atrasada"], f"{round(100*ias['atrasada']/max(ias['total'],1),1)}%"),
                            ("SEM IAS", ias["sem_ias"], f"{round(100*ias['sem_ias']/max(ias['total'],1),1)}%")])

    add_text(slide, Inches(7.4), Inches(3.7), Inches(5.3), Inches(0.3),
             "FROTA DO SGB", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    if mm:
        add_tabela_simples(slide, Inches(7.4), Inches(4.0), Inches(5.3),
                           ["Indicador", "Valor"],
                           [("Total de viaturas",     mm["total"]),
                            ("Operando",              mm["operando"]),
                            ("Baixadas",              mm["baixada"]),
                            ("Em descarga",           mm["descarga"]),
                            ("Idade média",           f"{mm['idade_media']} anos")])

    # Rodapé com elogios
    add_text(slide, MARGIN, Inches(6.4), Inches(6), Inches(0.3),
             "RECONHECIMENTO", font=FONT_CORPO, size=10, bold=True, color=COR_TEXTO_MUTED)
    if el:
        add_text(slide, MARGIN, Inches(6.65), Inches(6), Inches(0.4),
                 f"{el['total']} registros no ano — {el['elogios']} elogios, {el['lmp']} LMP, {el['louvor']} louvor",
                 font=FONT_CORPO, size=13, color=COR_TEXTO)
    add_footer(slide)


def slide_fechamento(prs, num_slide):
    slide = _blank_slide(prs)
    # Fundo escuro
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = COR_TEXTO
    bg.line.fill.background()

    add_text(slide, Inches(1.5), Inches(2.6), Inches(10), Inches(2.5),
             "\"A força da equipe está em cada membro.\nA força de cada membro está na equipe.\"",
             font=FONT_TITULO, size=32, italic=True, color=COR_BG)
    add_text(slide, Inches(1.5), Inches(4.8), Inches(10), Inches(0.4),
             "— Phil Jackson", font=FONT_CORPO, size=14, color=COR_ACENTO_CLARO)
    add_text(slide, Inches(1.5), Inches(6.5), Inches(10), Inches(0.4),
             "11º GB — Relatório Anual gerado automaticamente pelo Sistema de Comando Digital",
             font=FONT_CORPO, size=10, italic=True, color=COR_TEXTO_MUTED)


# ==========================================================================
# MAIN
# ==========================================================================

def gerar(ano=None, arquivo=None):
    ano = ano or date.today().year
    print(f">> Coletando dados do banco (ano de referência {ano})...")
    dados = carregar_tudo(ano_referencia=ano)

    print(">> Montando apresentação...")
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    n = 1
    slide_capa(prs, ano); n_capa = n; n += 1
    slide_sumario_executivo(prs, dados, n); n += 1

    # Divisor Parte I
    slide_divisor(prs, "PARTE I", "Sede — Estado-Maior"); n += 1

    slide_sede_b1(prs, dados, n); n += 1
    slide_sede_b3(prs, n); n += 1
    slide_sede_b5(prs, dados, n); n += 1
    slide_sede_uge(prs, dados, n); n += 1
    slide_sede_motomec(prs, dados, n); n += 1
    slide_sede_pjmd(prs, n); n += 1
    slide_sede_sat(prs, n); n += 1

    # Divisor Parte II
    slide_divisor(prs, "PARTE II", "Subgrupamentos de Bombeiros"); n += 1

    slide_sgb_comparativo(prs, dados, n); n += 1

    sgbs = [("1_SGB", "1º SGB"),
            ("2_SGB", "2º SGB"),
            ("3_SGB", "3º SGB"),
            ("4_SGB", "4º SGB")]
    for chave, completo in sgbs:
        slide_sgb_detalhe(prs, chave, completo, dados, n)
        n += 1

    slide_fechamento(prs, n); n += 1

    arquivo = arquivo or f"Relatorio_Anual_{ano}_11GB.pptx"
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), arquivo)
    prs.save(caminho)
    print(f">> Gerado: {caminho}  ({n-1} slides)")
    return caminho


if __name__ == "__main__":
    ano = int(sys.argv[1]) if len(sys.argv) > 1 else None
    gerar(ano)
