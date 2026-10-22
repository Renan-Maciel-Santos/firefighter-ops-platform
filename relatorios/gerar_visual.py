"""
Gerador do Relatório Visual — 11º GB (inspirado no PPTX do Major, V.2).

Filosofia: bater o olho e entender.
    - Um KPI = um gráfico nativo do PowerPoint (barChart, lineChart)
    - Sempre com série histórica (2022..ano_atual) pra Cap enxergar tendência
    - Título grande da seção (B/1, B/3, B/5, UGE, PJMD, MOTOMEC, SAT)
    - Sem tabelas de números; a linha/coluna já conta a história

Uso:
    python gerar_visual.py 2026 1   → S1/2026
    python gerar_visual.py 2026     → Exercício 2026 (anual)
"""

import sys, os
from datetime import date
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_TICK_MARK

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dados import carregar_tudo
from dados_historico import HISTORICO, CATALOGO, ANOS_HIST, serie_completa

# ==========================================================================
# PALETA / TIPOGRAFIA / LAYOUT (mesma família do Major)
# ==========================================================================

COR_ACENTO       = RGBColor(0xB2, 0x22, 0x22)   # firebrick
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

FONT_TITULO = "Cambria"
FONT_CORPO  = "Calibri"

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN  = Inches(0.5)


# ==========================================================================
# HELPERS GERAIS
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


def add_eyebrow(slide, secao):
    """Chip grande à esquerda com nome da seção, estilo Major."""
    x, y = MARGIN, Inches(0.55)
    add_text(slide, x, y, Inches(3), Inches(0.6),
             secao, font=FONT_TITULO, size=44, bold=True, color=COR_ACENTO)


def add_footer(slide, texto):
    add_text(slide, MARGIN, SLIDE_H - Inches(0.32),
             SLIDE_W - 2 * MARGIN, Inches(0.22),
             texto, font=FONT_CORPO, size=9, color=COR_TEXTO_MUTED)


# ==========================================================================
# GRÁFICO NATIVO — o coração do relatório
# ==========================================================================

def _num_fmt(fmt):
    return {
        "pct": "0.0%",
        "int": "#,##0",
        "dec": "0.00",
        "brl": '"R$"#,##0',
    }.get(fmt, "General")


def add_chart_serie_anos(slide, x, y, w, h, titulo, serie_dict, *,
                          fmt="int", tipo="COLUMN", cor_serie=None):
    """
    Insere um gráfico nativo (barra vertical OU linha) com uma série temporal.
      serie_dict = {ano: valor}
    """
    anos = sorted(serie_dict.keys())
    valores = [serie_dict[a] for a in anos]

    cd = CategoryChartData()
    cd.categories = [str(a) for a in anos]
    cd.add_series("", valores)

    xl_type = XL_CHART_TYPE.LINE if tipo == "LINE" else XL_CHART_TYPE.COLUMN_CLUSTERED

    graphic = slide.shapes.add_chart(xl_type, x, y, w, h, cd)
    chart = graphic.chart

    # Título
    chart.has_title = True
    chart.chart_title.text_frame.text = titulo
    for para in chart.chart_title.text_frame.paragraphs:
        for run in para.runs:
            run.font.name = FONT_TITULO
            run.font.size = Pt(15)
            run.font.bold = False
            run.font.color.rgb = COR_TEXTO

    # Sem legenda (série única)
    chart.has_legend = False

    # Cor da série + rótulos de dados
    plot = chart.plots[0]
    ser = plot.series[0]
    cor = cor_serie or COR_ACENTO
    if tipo == "LINE":
        # Linha
        line = ser.format.line
        line.color.rgb = cor
        line.width = Pt(2.75)
        # Marcadores
        ser.marker.style = 8  # circle
        ser.marker.size = 7
        ser.marker.format.fill.solid()
        ser.marker.format.fill.fore_color.rgb = cor
        ser.marker.format.line.color.rgb = cor
    else:
        # Colunas
        fill = ser.format.fill
        fill.solid()
        fill.fore_color.rgb = cor
        ser.format.line.fill.background()

    # Rótulos de dados
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = _num_fmt(fmt)
    dl.font.name = FONT_CORPO
    dl.font.size = Pt(11)
    dl.font.bold = True
    dl.font.color.rgb = COR_TEXTO
    if tipo == "LINE":
        dl.position = XL_LABEL_POSITION.ABOVE
    else:
        dl.position = XL_LABEL_POSITION.OUTSIDE_END

    # Eixos discretos
    cat_axis = chart.category_axis
    cat_axis.tick_labels.font.name = FONT_CORPO
    cat_axis.tick_labels.font.size = Pt(11)
    cat_axis.tick_labels.font.color.rgb = COR_TEXTO_DIM

    val_axis = chart.value_axis
    val_axis.visible = False  # a etiqueta em cima da barra basta
    val_axis.major_tick_mark = XL_TICK_MARK.NONE
    val_axis.minor_tick_mark = XL_TICK_MARK.NONE

    return chart


def semaforo(chave, valor_novo):
    """Compara valor novo com média histórica → devolve cor da série."""
    meta = CATALOGO.get(chave, {})
    hist = HISTORICO.get(chave, {})
    if valor_novo is None or not hist:
        return COR_ACENTO
    media = sum(hist.values()) / len(hist)
    melhor = meta.get("menor_melhor", False)
    if melhor:
        return COR_BOM if valor_novo <= media else COR_CRITICO
    else:
        return COR_BOM if valor_novo >= media else COR_ATENCAO


# ==========================================================================
# EXTRATOR — pega valor 2026 dos dados atuais do banco
# ==========================================================================

def valor_atual_por_kpi(dados):
    """Mapeia dict `dados` (retorno de carregar_tudo) → {chave_kpi: valor_2026}."""
    ef = dados["efetivo"]; ab = dados["absenteismo"]
    te = dados["territorio"]; el = dados["elogios"]
    ug = dados["uge"]; mm = dados["motomec"]
    cb = dados.get("cobom") or {}
    sj = dados.get("sjd") or {}

    # Ajuste SAT: 12 Sub/Sgt lotados como admin (cod_opm terminado em 0) mas que
    # exercem fiscalização, portanto contam como operacional (decisão do comando).
    op_geral = ef.get("operacional_geral") or {}
    op_num = (op_geral.get("operacional") or 0) + 12
    op_den = op_geral.get("total") or 0
    op_pct = round(100 * op_num / op_den, 1) if op_den else None

    return {
        "absenteismo_lts_pct":       ab["geral"]["pct"] / 100 if ab.get("geral") else None,
        "efetivo_operacional_pct":   op_pct / 100 if op_pct is not None else None,
        "cobertura_territorial_pct": te["pct"] / 100 if te else None,
        # Especialização 2026: 10 militares (S1) + 23 adicionais = 33 no ano (Cap, 17/jul)
        "especializacao_pct":        round(33 / ef["total_ativos"], 4) if ef.get("total_ativos") else None,
        "atendimento_20min_pct":     None,  # COBOM (ainda não temos tempo de resposta)
        "fatais_incendio":           cb.get("fatais_incendio", {}).get("total"),
        "fatais_transito":           cb.get("fatais_transito", {}).get("total"),
        "elogios_por_bombeiro":      round(el["geral"]["elogios"] / ef["total_ativos"], 2) if el.get("geral") and ef.get("total_ativos") else None,
        "lmp_outorgadas":            el["geral"]["lmp"] if el.get("geral") else None,
        "turmas_bombeiro_escola":    None,  # dado externo B/5
        "uge_processos":             ug["geral"]["total"] if ug.get("geral") else None,
        # Custeio e investimento são NATUREZAS DE DESPESA, não fases (empenhado/liquidado).
        # Valores fornecidos pelo Cap (17/jul); enquanto não houver campo natureza no
        # b.uge_processos, mantemos hardcode manual pra S1/2026.
        "uge_valor_custeio":         876958.12,
        "uge_valor_investimento":    2057092.12,
        "reclamacoes_denuncias":     sj.get("reclamacoes_denuncias"),
        "pms_punidos_pd":            sj.get("pms_punidos_pd"),
        "acidentes_folga_bombeiro":  sj.get("acidentes_folga_bombeiro"),
        "acidentes_viatura_vitima":  sj.get("acidentes_viatura_vitima"),
        "idade_media_veicular":      float(mm["geral"]["idade_media"]) if mm.get("geral") and mm["geral"].get("idade_media") else None,
        "viaturas_baixadas_pct":     mm["geral"]["pct_baixadas"] / 100 if mm.get("geral") else None,
        # Dados SAT do S1/2026 (dado do Cap, 17/jul)
        "dias_analise":              0,
        "dias_vistoria":             7,
        "dias_analise_fat":          0,
        "fiscalizacoes":             343,
    }


# ==========================================================================
# SLIDES
# ==========================================================================

def slide_capa(prs, ano, subtitulo):
    slide = _blank(prs)
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.5), SLIDE_H)
    bar.fill.solid(); bar.fill.fore_color.rgb = COR_ACENTO
    bar.line.fill.background()

    add_text(slide, Inches(1.2), Inches(2.4), Inches(11), Inches(0.4),
             "11º GRUPAMENTO DE BOMBEIROS  ·  PMESP",
             font=FONT_CORPO, size=14, bold=True, color=COR_TEXTO_MUTED)
    add_text(slide, Inches(1.2), Inches(2.9), Inches(11), Inches(1.6),
             "RELATÓRIO", font=FONT_TITULO, size=72, color=COR_TEXTO)
    add_text(slide, Inches(1.2), Inches(4.1), Inches(11), Inches(0.9),
             subtitulo, font=FONT_TITULO, size=44, italic=True, color=COR_ACENTO)
    add_text(slide, Inches(1.2), Inches(5.2), Inches(11), Inches(0.4),
             "Série histórica 2022 – " + str(ano) + "  ·  visão executiva",
             font=FONT_CORPO, size=15, color=COR_TEXTO_DIM)
    add_text(slide, Inches(1.2), Inches(6.6), Inches(11), Inches(0.4),
             f"Vale do Paraíba  ·  Litoral Norte  ·  emitido em {date.today().strftime('%d/%m/%Y')}",
             font=FONT_CORPO, size=11, color=COR_TEXTO_MUTED)


def slide_secao_2charts(prs, secao, kpis, valores_atuais, ano_atual, periodo_label):
    """Slide padrão: 2 gráficos lado a lado (esquerda e direita)."""
    slide = _blank(prs)
    add_eyebrow(slide, secao)

    # Título descritivo pequeno abaixo do chip
    add_text(slide, MARGIN, Inches(1.3), Inches(12), Inches(0.35),
             "Série histórica " + str(ANOS_HIST[0]) + f"–{ano_atual}",
             font=FONT_CORPO, size=12, italic=True, color=COR_TEXTO_DIM)

    largura = Inches(6.0); altura = Inches(5.2); gap = Inches(0.3)
    x_esq = MARGIN
    x_dir = MARGIN + largura + gap
    y = Inches(1.75)

    for i, chave in enumerate(kpis[:2]):
        meta = CATALOGO[chave]
        v_novo = valores_atuais.get(chave)
        s = serie_completa(chave, v_novo, ano_atual)
        # tipo de gráfico por natureza do KPI: % e taxa como linha, contagens como barra
        tipo = "LINE" if meta["fmt"] == "pct" else "COLUMN"
        cor = semaforo(chave, v_novo)
        x = x_esq if i == 0 else x_dir
        add_chart_serie_anos(slide, x, y, largura, altura,
                             meta["titulo"], s,
                             fmt=meta["fmt"], tipo=tipo, cor_serie=cor)
        # Rodapé: nota metodológica, ou aviso de dado pendente
        nota = meta.get("nota")
        if v_novo is None:
            add_text(slide, x, y + altura + Inches(0.02),
                     largura, Inches(0.3),
                     f"* {ano_atual} aguardando dado",
                     font=FONT_CORPO, size=9, italic=True, color=COR_TEXTO_MUTED,
                     align=PP_ALIGN.CENTER)
        elif nota:
            add_text(slide, x, y + altura + Inches(0.02),
                     largura, Inches(0.35),
                     f"* {nota}",
                     font=FONT_CORPO, size=9, italic=True, color=COR_TEXTO_MUTED,
                     align=PP_ALIGN.CENTER)

    add_footer(slide, f"11º GB — {periodo_label}")


def slide_secao_1chart(prs, secao, chave, valores_atuais, ano_atual, periodo_label):
    """Slide padrão: 1 gráfico grande centralizado."""
    slide = _blank(prs)
    add_eyebrow(slide, secao)
    add_text(slide, MARGIN, Inches(1.3), Inches(12), Inches(0.35),
             "Série histórica " + str(ANOS_HIST[0]) + f"–{ano_atual}",
             font=FONT_CORPO, size=12, italic=True, color=COR_TEXTO_DIM)

    meta = CATALOGO[chave]
    v_novo = valores_atuais.get(chave)
    s = serie_completa(chave, v_novo, ano_atual)
    tipo = "LINE" if meta["fmt"] == "pct" else "COLUMN"
    cor = semaforo(chave, v_novo)
    add_chart_serie_anos(slide, Inches(1.8), Inches(1.75), Inches(9.7), Inches(5.2),
                         meta["titulo"], s,
                         fmt=meta["fmt"], tipo=tipo, cor_serie=cor)
    nota = meta.get("nota")
    if v_novo is None:
        add_text(slide, Inches(1.8), Inches(6.95), Inches(9.7), Inches(0.3),
                 f"* {ano_atual} aguardando dado",
                 font=FONT_CORPO, size=9, italic=True, color=COR_TEXTO_MUTED,
                 align=PP_ALIGN.CENTER)
    elif nota:
        add_text(slide, Inches(1.8), Inches(6.95), Inches(9.7), Inches(0.3),
                 f"* {nota}",
                 font=FONT_CORPO, size=9, italic=True, color=COR_TEXTO_MUTED,
                 align=PP_ALIGN.CENTER)
    add_footer(slide, f"11º GB — {periodo_label}")


def slide_fechamento(prs, periodo_label):
    slide = _blank(prs)
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = COR_TEXTO
    bg.line.fill.background()
    add_text(slide, Inches(1.5), Inches(2.5), Inches(10), Inches(2.5),
             '"A força da equipe está em cada membro.\nA força de cada membro está na equipe."',
             font=FONT_TITULO, size=32, italic=True, color=COR_BG, align=PP_ALIGN.CENTER)
    add_text(slide, Inches(1.5), Inches(4.8), Inches(10), Inches(0.4),
             "— Phil Jackson", font=FONT_CORPO, size=14,
             color=COR_ACENTO_CLARO, align=PP_ALIGN.CENTER)
    add_text(slide, Inches(1.5), Inches(5.7), Inches(10), Inches(1.0),
             "OBRIGADO!", font=FONT_TITULO, size=48, bold=True,
             color=COR_BG, align=PP_ALIGN.CENTER)
    add_text(slide, Inches(1.5), Inches(6.9), Inches(10), Inches(0.3),
             f"11º GB — {periodo_label}",
             font=FONT_CORPO, size=10, italic=True, color=COR_TEXTO_MUTED,
             align=PP_ALIGN.CENTER)


# ==========================================================================
# MAIN
# ==========================================================================

def gerar(ano, num_sem=None):
    if num_sem:
        dados = carregar_tudo("semestre", ano, num_sem)
        subtitulo = f"{num_sem}º Semestre de {ano}"
    else:
        dados = carregar_tudo("anual", ano, 1)
        subtitulo = f"Exercício {ano}"

    p = dados["periodo"]
    periodo_label = p["label_longo"]
    val_atuais = valor_atual_por_kpi(dados)

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # Capa
    slide_capa(prs, ano, subtitulo)

    # Seções (segue exatamente a ordem do Major)
    # B/1: 2 charts
    slide_secao_2charts(prs, "B/1",
        ["absenteismo_lts_pct", "efetivo_operacional_pct"],
        val_atuais, ano, periodo_label)

    # B/3: 3 slides (2+1+2)
    slide_secao_2charts(prs, "B/3",
        ["cobertura_territorial_pct", "especializacao_pct"],
        val_atuais, ano, periodo_label)
    slide_secao_1chart(prs, "B/3", "atendimento_20min_pct",
        val_atuais, ano, periodo_label)
    slide_secao_2charts(prs, "B/3",
        ["fatais_incendio", "fatais_transito"],
        val_atuais, ano, periodo_label)

    # B/5: 2 slides (2+1)
    slide_secao_2charts(prs, "B/5",
        ["elogios_por_bombeiro", "lmp_outorgadas"],
        val_atuais, ano, periodo_label)
    slide_secao_1chart(prs, "B/5", "turmas_bombeiro_escola",
        val_atuais, ano, periodo_label)

    # UGE: 2 slides
    slide_secao_1chart(prs, "UGE", "uge_processos",
        val_atuais, ano, periodo_label)
    slide_secao_2charts(prs, "UGE",
        ["uge_valor_custeio", "uge_valor_investimento"],
        val_atuais, ano, periodo_label)

    # PJMD: 2 slides
    slide_secao_2charts(prs, "PJMD",
        ["reclamacoes_denuncias", "pms_punidos_pd"],
        val_atuais, ano, periodo_label)
    slide_secao_2charts(prs, "PJMD",
        ["acidentes_folga_bombeiro", "acidentes_viatura_vitima"],
        val_atuais, ano, periodo_label)

    # MOTOMEC: 1 slide
    slide_secao_2charts(prs, "MOTOMEC",
        ["idade_media_veicular", "viaturas_baixadas_pct"],
        val_atuais, ano, periodo_label)

    # SAT: 2 slides
    slide_secao_2charts(prs, "SAT",
        ["dias_analise", "dias_vistoria"],
        val_atuais, ano, periodo_label)
    slide_secao_2charts(prs, "SAT",
        ["dias_analise_fat", "fiscalizacoes"],
        val_atuais, ano, periodo_label)

    # Fechamento
    slide_fechamento(prs, periodo_label)

    nome = f"Relatorio_Visual_{ano}" + (f"-S{num_sem}" if num_sem else "") + "_11GB.pptx"
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), nome)
    prs.save(caminho)
    print(f">> Gerado: {caminho}  ({len(prs.slides)} slides)")
    return caminho


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python gerar_visual.py <ANO> [<NUM_SEM>]")
        print("     python gerar_visual.py 2026        (anual)")
        print("     python gerar_visual.py 2026 1      (S1)")
        sys.exit(1)
    ano = int(sys.argv[1])
    num_sem = int(sys.argv[2]) if len(sys.argv) > 2 else None
    gerar(ano, num_sem)
