# -*- coding: utf-8 -*-
"""Consolida as quatro apurações numa conclusão por linha.

Fontes cruzadas, em ordem de entrada no processo:

  1. busca direta  — endereço -> coordenada (Google)
  2. histórico     — onde o 11º GB sempre atendeu aquela via (b3.ocorrencias)
  3. bairro/referência do despacho — desambiguação
  4. busca reversa — coordenada -> endereço (Google)

DUAS ARMADILHAS DA REVERSA, e são elas que ditam a regra final:

  Ela devolve a via MAIS PRÓXIMA do ponto, não a via do ponto. Uma coordenada a
  poucos metros do eixo de uma avenida gruda na transversal, e a reversa acusa
  divergência onde não há. Medido: das 132 linhas CERTA que a reversa reprovou,
  113 têm a busca direta a 50 m ou menos — ou seja, a coordenada está na via
  certa e quem errou foi a reversa. Só 6 divergem de verdade. Por isso a reversa
  NUNCA condena sozinha: ela só condena quando a busca direta concorda.

  Ela não distingue trecho. Numa rodovia de 40 km, dois pontos a 30 km um do
  outro devolvem o mesmo nome de via e a reversa diz "bate". Serve para saber se
  a via é aquela, não se o ponto é aquele.

O QUE A REVERSA REVELOU SOZINHA, e nenhuma outra fonte pegaria: coordenada
reutilizada. Um mesmo par lat/lon aparece em até 9 linhas com 9 logradouros
DIFERENTES. Não é imprecisão de lançamento — é ponto padrão copiado de outra
ocorrência, e a coordenada não descreve endereço nenhum. Endereço diferente
caindo no mesmo ponto é a assinatura disso.

Uso:
    python conferencia_final_coordenadas.py
"""

import os
import sys

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

REVERSA = r"C:\dados\053-26 - enderecos x coordenadas - CONFERIDO.xlsx"
DIRETA = r"C:\dados\053-26 - VEREDITO CONSOLIDADO.xlsx"
SAIDA = r"C:\dados\053-26 - enderecos x coordenadas - FINAL.xlsx"

# Acima: abaixo disto a busca direta põe o endereço praticamente em cima da
# coordenada lançada — evidência de que a reversa grudou numa via vizinha.
NA_VIA_CERTA_M = 50
DIVERGENCIA_REAL_M = 300


def main():
    d = pd.read_excel(REVERSA)
    v = pd.read_excel(DIRETA, sheet_name='Análise completa')
    d = d.merge(v[['Linha na planilha original', 'Google — distância até a lançada (m)']],
                on='Linha na planilha original', how='left')
    d = d.rename(columns={'Google — distância até a lançada (m)': 'dir_m'})

    # ---- coordenada reutilizada
    d['par'] = (d['Latitude informada (col. J)'].round(6).astype(str) + ',' +
                d['Longitude informada (col. K)'].round(6).astype(str))
    logr_por_par = d.groupby('par')['Logradouro informado (col. H)'].nunique()
    d['logradouros_no_mesmo_ponto'] = d['par'].map(logr_por_par)

    conclusao, detalhe = [], []
    for _, r in d.iterrows():
        n = r['logradouros_no_mesmo_ponto']
        bate = r['A coordenada bate com o logradouro?']
        dm = r['dir_m']

        if n >= 2:
            conclusao.append('COORDENADA REUTILIZADA')
            detalhe.append(
                f"Esta coordenada aparece em {int(r['par'] and logr_por_par[r['par']])} logradouros "
                f"DIFERENTES da planilha. É ponto padrão copiado de outra ocorrência, não a "
                f"localização deste endereço. No ponto existe: {r['No ponto — endereço']}.")
        elif bate == 'OUTRO MUNICÍPIO':
            conclusao.append('CAI EM OUTRO MUNICÍPIO')
            detalhe.append(f"A coordenada cai em {r['No ponto — município']}. Confirmar de qual "
                           f"município é a ocorrência antes de qualquer correção.")
        elif bate == 'BATE':
            conclusao.append('NA VIA INFORMADA')
            detalhe.append(f"A via existente no ponto é a informada no despacho "
                           f"({r['No ponto — via']}).")
        elif bate == 'NÃO BATE' and pd.notna(dm) and dm <= NA_VIA_CERTA_M:
            conclusao.append('NA VIA INFORMADA')
            detalhe.append(
                f"A busca reversa apontou '{r['No ponto — via']}', mas o endereço informado "
                f"geocodifica a {int(dm)} m desta coordenada — a reversa grudou numa via vizinha. "
                f"A coordenada está na via certa.")
        elif bate == 'NÃO BATE' and pd.notna(dm) and dm > DIVERGENCIA_REAL_M:
            conclusao.append('APONTA PARA OUTRA VIA')
            detalhe.append(
                f"As duas buscas concordam que a coordenada não está na via informada: no ponto "
                f"existe {r['No ponto — via']}"
                f"{', bairro ' + str(r['No ponto — bairro']) if pd.notna(r['No ponto — bairro']) else ''}, "
                f"e o endereço informado fica a {int(dm)} m dali.")
        elif bate == 'NÃO BATE':
            conclusao.append('DÚVIDA — conferir no mapa')
            detalhe.append(
                f"A reversa aponta '{r['No ponto — via']}' e a busca direta não deu evidência "
                f"suficiente para confirmar nem descartar. Conferir no mapa.")
        elif bate == 'SEM VIA NO PONTO':
            conclusao.append('SEM VIA MAPEADA NO PONTO')
            detalhe.append(f"Não há via mapeada no ponto. O local é descrito como: "
                           f"{r['No ponto — endereço']}. Típico de área rural ou gleba.")
        else:
            conclusao.append('DÚVIDA — conferir no mapa')
            detalhe.append('Sem evidência suficiente nas fontes consultadas.')

    d['CONCLUSÃO'] = conclusao
    d['POR QUE'] = detalhe
    d = d.drop(columns=['par', 'dir_m'])

    print("--- conclusão final das 673 ---")
    print(d['CONCLUSÃO'].value_counts().to_string())
    print("\n--- cruzando com a situação apurada antes ---")
    print(pd.crosstab(d['SITUAÇÃO'], d['CONCLUSÃO']).to_string())

    d.to_excel(SAIDA, index=False, sheet_name='Endereços x coordenadas')

    # ---- formatação
    wb = load_workbook(SAIDA)
    ws = wb.active
    cab = Font(bold=True, color='FFFFFF', size=10)
    fundo = PatternFill('solid', fgColor='9E1B1B')
    larguras = {'Logradouro informado (col. H)': 34, 'Referência do endereço (col. G)': 28,
                'O QUE ESTÁ ERRADO': 50, 'POR QUE': 62, 'No ponto — endereço': 40,
                'No ponto — via': 28, 'Município': 18, 'CONCLUSÃO': 24,
                'O que há na coordenada': 46, 'Referência (despacho)': 34}
    cabecalhos = [c.value for c in ws[1]]
    for i, nome in enumerate(cabecalhos, start=1):
        c = ws.cell(row=1, column=i)
        c.font = cab; c.fill = fundo
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = larguras.get(nome, 15)
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions

    cores = {'NA VIA INFORMADA': 'E4F1EB', 'COORDENADA REUTILIZADA': 'FBE9EA',
             'APONTA PARA OUTRA VIA': 'FBE9EA', 'CAI EM OUTRO MUNICÍPIO': 'F8EEDC',
             'DÚVIDA — conferir no mapa': 'F8EEDC', 'SEM VIA MAPEADA NO PONTO': 'F8EEDC'}
    col_conc = cabecalhos.index('CONCLUSÃO') + 1
    col_pq = cabecalhos.index('POR QUE') + 1
    for l in range(2, ws.max_row + 1):
        cor = cores.get(ws.cell(row=l, column=col_conc).value)
        if not cor:
            continue
        f = PatternFill('solid', fgColor=cor)
        for c in range(1, ws.max_column + 1):
            ws.cell(row=l, column=c).fill = f
        ws.cell(row=l, column=col_pq).alignment = Alignment(wrap_text=True, vertical='top')
    wb.save(SAIDA)
    print(f"\n>> gravado: {SAIDA}")


if __name__ == "__main__":
    main()
