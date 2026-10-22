# -*- coding: utf-8 -*-
"""Cruza as quatro apurações e tenta zerar as linhas sem resposta.

Cada passada anterior respondeu uma pergunta diferente sobre a mesma linha, e
nenhuma delas foi confrontada com as outras. Aqui elas são:

  DIRETA    geocodifica logradouro + numeral + bairro -> onde fica o endereço
  REVERSA   geocodifica a coordenada -> que via existe naquele ponto
  HISTÓRICO onde o 11º GB sempre atendeu aquela via
  REPETIÇÃO o mesmo par lat/lon aparece em quantos logradouros diferentes

O ponto do cruzamento é que as fraquezas não coincidem. Onde a direta falha por
homônimo — "Rua Sete" existe em seis bairros —, a reversa não tem ambiguidade
nenhuma: o ponto aponta para um lugar só. Onde a reversa falha por grudar na
transversal, a direta põe o endereço em cima da coordenada e desmente. Onde as
duas falham, a repetição ainda denuncia ponto padrão copiado.

DUAS COISAS DIFERENTES QUE NÃO PODEM SER CONFUNDIDAS:

  "não sei se está certo"  -> isto o cruzamento resolve, e é o que se zera aqui
  "sei que está errado e sei o certo" -> isto depende de o endereço existir em
      base cartográfica, e para estrada rural, via informal e rodovia com
      numeral de quilômetro simplesmente não existe

Por isso a saída tem DUAS colunas e não uma: BATE? diz se a coordenada
corresponde ao endereço, e a coordenada corrigida só aparece quando há evidência
que a sustente. Fundir as duas produziria uma planilha que parece completa.

Uso:
    python cruzamento_final_coordenadas.py
"""

import os
import sys

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

DIRETA = r"C:\dados\053-26 - enderecos x coordenadas - BATE OU NAO.xlsx"
REVERSA = r"C:\dados\053-26 - enderecos x coordenadas - CONFERIDO.xlsx"
CONSOL = r"C:\dados\053-26 - VEREDITO CONSOLIDADO.xlsx"
SAIDA = r"C:\dados\053-26 - enderecos x coordenadas - CRUZADO.xlsx"

CHAVE = 'Linha na planilha original'


def main():
    d = pd.read_excel(DIRETA)
    rev = pd.read_excel(REVERSA)[[CHAVE, 'No ponto — via', 'No ponto — bairro',
                                  'No ponto — município', 'No ponto — endereço',
                                  'A coordenada bate com o logradouro?']]
    d = d.merge(rev, on=CHAVE, how='left')

    # ---- repetição de coordenada
    par = (d['Latitude informada (col. J)'].round(6).astype(str) + ',' +
           d['Longitude informada (col. K)'].round(6).astype(str))
    logr_por_par = d.assign(par=par).groupby('par')['Logradouro informado (col. H)'].nunique()
    d['logradouros_no_ponto'] = par.map(logr_por_par)

    bate, motivo, origem = [], [], []
    for _, r in d.iterrows():
        b = r['BATE?']
        revb = r['A coordenada bate com o logradouro?']
        n_logr = r['logradouros_no_ponto']

        # Acima: já resolvidas pela direta — o numeral bateu ou o erro é conhecido
        if b in ('BATE', 'NÃO BATE'):
            bate.append(b)
            motivo.append(r['MOTIVO'])
            origem.append('busca direta (logradouro + numeral)')
            continue

        # --- daqui para baixo, as 105 que a direta não resolveu ---

        # Acima: ponto reutilizado por vários endereços não descreve nenhum
        # deles. Nem a direta nem a reversa consertam isso: a coordenada não é
        # imprecisa, é de outra ocorrência.
        if n_logr >= 2:
            bate.append('NÃO BATE')
            motivo.append(f"Esta coordenada é usada por {int(n_logr)} logradouros DIFERENTES da "
                          f"planilha — é ponto padrão copiado de outra ocorrência, não a "
                          f"localização deste endereço. Não há coordenada correta a propor: o "
                          f"endereço precisa ser localizado do zero.")
            origem.append('coordenada reutilizada')
            continue

        if revb == 'BATE':
            # Acima: a reversa não sofre ambiguidade de homônimo — o ponto tem
            # uma via só embaixo. Se ela é a informada, a coordenada está na via
            # certa e quem falhou foi a busca direta.
            bate.append('BATE (via, não o numeral)')
            motivo.append(f"A via existente no ponto é a informada no despacho "
                          f"({r['No ponto — via']}). A busca por endereço falhou, mas a coordenada "
                          f"está na via certa. O numeral não pôde ser conferido.")
            origem.append('busca reversa (coordenada -> via)')
            continue

        if revb == 'NÃO BATE' and pd.notna(r['No ponto — via']):
            bate.append('NÃO BATE')
            motivo.append(f"A coordenada aponta para {r['No ponto — via']}"
                          f"{', bairro ' + str(r['No ponto — bairro']) if pd.notna(r['No ponto — bairro']) else ''}, "
                          f"e não para '{r['Logradouro informado (col. H)']}'. O endereço informado "
                          f"não pôde ser localizado com precisão suficiente para propor a "
                          f"coordenada correta.")
            origem.append('busca reversa (coordenada -> via)')
            continue

        if revb == 'OUTRO MUNICÍPIO':
            bate.append('NÃO BATE')
            motivo.append(f"A coordenada cai em {r['No ponto — município']}, não em São José dos "
                          f"Campos. Ou a coordenada está errada, ou a ocorrência não é deste "
                          f"município — confirmar antes de corrigir.")
            origem.append('busca reversa (município do ponto)')
            continue

        if revb == 'SEM VIA NO PONTO':
            bate.append('SEM RESPOSTA')
            motivo.append(f"Não há via mapeada no ponto e o endereço informado não foi localizado. "
                          f"O local é descrito como: {r['No ponto — endereço']}. Típico de gleba ou "
                          f"área rural — só a guarnição resolve.")
            origem.append('nenhuma fonte resolveu')
            continue

        bate.append('SEM RESPOSTA')
        motivo.append(r['MOTIVO'])
        origem.append('nenhuma fonte resolveu')

    d['BATE?'] = bate
    d['MOTIVO'] = motivo
    d['Como foi decidido'] = origem

    cols = [CHAVE, 'Município', 'Data', 'Ocr Num', 'Referência do endereço (col. G)',
            'Logradouro informado (col. H)', 'Nº / km (col. I)',
            'Latitude informada (col. J)', 'Longitude informada (col. K)',
            'BATE?', 'LATITUDE CORRETA', 'LONGITUDE CORRETA', 'ERRO (m)', 'MOTIVO',
            'Endereço localizado', 'Precisão da localização',
            'No ponto — via', 'No ponto — bairro', 'Como foi decidido']
    s = d[cols]

    print("--- resultado do cruzamento ---")
    print(s['BATE?'].value_counts().to_string())
    print("\n--- o que resolveu cada linha ---")
    print(s['Como foi decidido'].value_counts().to_string())
    print(f"\nsem resposta: {(s['BATE?'] == 'SEM RESPOSTA').sum()}")
    print(f"NÃO BATE com coordenada correta: "
          f"{s[s['BATE?'] == 'NÃO BATE']['LATITUDE CORRETA'].notna().sum()} de "
          f"{(s['BATE?'] == 'NÃO BATE').sum()}")

    s.to_excel(SAIDA, index=False, sheet_name='Endereços x coordenadas')

    wb = load_workbook(SAIDA); ws = wb.active
    larg = [10, 18, 12, 11, 26, 32, 9, 14, 14, 22, 15, 15, 10, 72, 34, 15, 26, 20, 30]
    cab = Font(bold=True, color='FFFFFF', size=10); fundo = PatternFill('solid', fgColor='9E1B1B')
    for i in range(1, ws.max_column + 1):
        c = ws.cell(row=1, column=i)
        c.font = cab; c.fill = fundo
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = larg[i - 1] if i <= len(larg) else 20
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = 'A2'; ws.auto_filter.ref = ws.dimensions
    cores = {'BATE': 'E4F1EB', 'BATE (via, não o numeral)': 'EAF4EE',
             'NÃO BATE': 'FBE9EA', 'SEM RESPOSTA': 'F8EEDC'}
    for l in range(2, ws.max_row + 1):
        cor = cores.get(ws.cell(row=l, column=10).value)
        if not cor:
            continue
        f = PatternFill('solid', fgColor=cor)
        for c in range(1, ws.max_column + 1):
            ws.cell(row=l, column=c).fill = f
        ws.cell(row=l, column=14).alignment = Alignment(wrap_text=True, vertical='top')
    wb.save(SAIDA)
    print(f"\n>> gravado: {SAIDA}")


if __name__ == "__main__":
    main()
