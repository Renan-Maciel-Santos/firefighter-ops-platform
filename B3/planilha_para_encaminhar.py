# -*- coding: utf-8 -*-
"""Monta a planilha de encaminhamento da apuração de coordenadas (053-26).

Diferente das anteriores, esta não é ferramenta de trabalho: é o documento que
sai da seção. Quem recebe não acompanhou a apuração e não vai ler método — abre,
entende o tamanho do problema e sabe o que fazer com cada linha.

Duas abas:
    Resumo       o número que responde o expediente, em cinco linhas
    Ocorrências  as 673, na ordem da planilha de origem

A ordem é a da planilha original de propósito. Ordenar por erro decrescente
mostraria melhor, mas quebraria a conferência linha a linha contra o documento
que originou o expediente — e é essa conferência que quem recebe vai querer
fazer primeiro.

Uso:
    python planilha_para_encaminhar.py
"""

import os
import re
import sys

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ENTRADA = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\dados\053-26 - enderecos x coordenadas - APURADO.xlsx"
SAIDA = sys.argv[2] if len(sys.argv) > 2 else \
    r"C:\dados\053-26 - Apuracao de coordenadas - 11GB.xlsx"

VERMELHO, CINZA, BRANCO = "9E1B1B", "F2F2F2", "FFFFFF"
CORES = {'Confere': 'E4F1EB', 'Corrigida': 'FBE9EA',
         'Via confere, trecho não': 'F8EEDC', 'Não confirmada': 'F8EEDC'}

RE_SUJEIRA = re.compile(r'(_x000D_|[\r\n\t\x00-\x1f])')


def limpar(v):
    return v if pd.isna(v) else ' '.join(RE_SUJEIRA.sub(' ', str(v)).split())


def situacao(r):
    b = str(r['BATE?'])
    if b.startswith('BATE (via'):
        return 'Via confere, trecho não'
    if b == 'BATE':
        return 'Confere'
    return 'Corrigida' if pd.notna(r['LATITUDE CORRETA']) else 'Não confirmada'


def observacao(r, sit):
    if sit == 'Confere':
        return None
    if sit == 'Via confere, trecho não':
        return ('A coordenada está na via informada, mas o trecho não pôde ser conferido — '
                'rodovia, onde o numeral é quilômetro, ou via de nome genérico.')
    if sit == 'Não confirmada':
        return ('A coordenada não corresponde ao endereço e o endereço não pôde ser localizado. '
                'Depende de consulta à guarnição.')
    c = str(r.get('Confiança da coordenada corrigida') or '')
    if c.startswith('entorno'):
        return ('Coordenada obtida pelo ponto de referência do despacho: localiza a região, '
                'não o número exato.')
    if c.startswith('eixo'):
        return 'Coordenada obtida no eixo da via: localiza a rua, não o número.'
    p = r.get('Precisão da localização')
    if p == 'RANGE_INTERPOLATED':
        return 'Número estimado dentro da quadra — confirmar antes de adotar.'
    return 'Endereço localizado no número exato.'


def main():
    d = pd.read_excel(ENTRADA)
    d['sit'] = d.apply(situacao, axis=1)
    d['obs'] = d.apply(lambda r: observacao(r, r['sit']), axis=1)

    s = pd.DataFrame({
        'Linha': d['Linha na planilha original'],
        'Ocorrência': d['Ocr Num'],
        'Data': pd.to_datetime(d['Data'], errors='coerce').dt.strftime('%d/%m/%Y'),
        'Logradouro': d['Logradouro informado (col. H)'].map(limpar),
        'Nº / km': d['Nº / km (col. I)'],
        'Referência do despacho': d['Referência do endereço (col. G)'].map(limpar),
        'SITUAÇÃO': d['sit'],
        'Latitude lançada': d['Latitude informada (col. J)'],
        'Longitude lançada': d['Longitude informada (col. K)'],
        'Latitude correta': d['LATITUDE CORRETA'],
        'Longitude correta': d['LONGITUDE CORRETA'],
        'Erro (m)': d['ERRO (m)'],
        'Observação': d['obs'].map(limpar),
    })

    cont = s['SITUAÇÃO'].value_counts()
    n = len(s)
    resumo = pd.DataFrame({
        'Apuração': [
            'Ocorrências analisadas',
            'Coordenada confere com o endereço',
            'Coordenada errada — corrigida nesta apuração',
            'Na via certa, trecho não conferido',
            'Posição não confirmada',
            '',
            'Erro mediano das corrigidas',
            'Maior erro encontrado',
        ],
        'Valor': [
            n,
            int(cont.get('Confere', 0)),
            int(cont.get('Corrigida', 0)),
            int(cont.get('Via confere, trecho não', 0)),
            int(cont.get('Não confirmada', 0)),
            '',
            f"{int(s['Erro (m)'].median())} m",
            f"{int(s['Erro (m)'].max()):,} m".replace(',', '.'),
        ],
    })

    print(resumo.to_string(index=False))

    with pd.ExcelWriter(SAIDA, engine='openpyxl') as w:
        resumo.to_excel(w, sheet_name='Resumo', index=False)
        s.to_excel(w, sheet_name='Ocorrências', index=False)

    wb = load_workbook(SAIDA)
    fina = Side(style='thin', color='D0D7DE')

    # ---- Resumo
    ws = wb['Resumo']
    ws.column_dimensions['A'].width = 46
    ws.column_dimensions['B'].width = 16
    ws['A1'].value = 'APURAÇÃO DE ENDEREÇOS E COORDENADAS — EXPEDIENTE 053-26'
    ws['B1'].value = None
    ws.merge_cells('A1:B1')
    ws['A1'].font = Font(bold=True, color=BRANCO, size=11)
    ws['A1'].fill = PatternFill('solid', fgColor=VERMELHO)
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 26
    for l in range(2, ws.max_row + 1):
        ws.cell(row=l, column=1).font = Font(bold=(l in (2, 3)))
        ws.cell(row=l, column=2).alignment = Alignment(horizontal='right')
        for c in (1, 2):
            ws.cell(row=l, column=c).border = Border(bottom=fina)
    ws.cell(row=ws.max_row + 2, column=1).value = (
        'Método: cada endereço (logradouro e numeral) foi localizado e comparado com a '
        'coordenada lançada. Diferença de até 150 m foi aceita como coincidente.')
    ws.cell(row=ws.max_row, column=1).alignment = Alignment(wrap_text=True, vertical='top')
    ws.cell(row=ws.max_row, column=1).font = Font(size=9, italic=True, color='6E7781')
    ws.merge_cells(start_row=ws.max_row, start_column=1, end_row=ws.max_row, end_column=2)
    ws.row_dimensions[ws.max_row].height = 42

    # ---- Ocorrências
    ws = wb['Ocorrências']
    larguras = [8, 11, 11, 34, 9, 34, 20, 15, 15, 15, 15, 10, 58]
    cab = Font(bold=True, color=BRANCO, size=10)
    fundo = PatternFill('solid', fgColor=VERMELHO)
    for i, larg in enumerate(larguras, start=1):
        c = ws.cell(row=1, column=i)
        c.font = cab
        c.fill = fundo
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = larg
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = 'D2'
    ws.auto_filter.ref = ws.dimensions

    col_sit = 7
    for l in range(2, ws.max_row + 1):
        cor = CORES.get(ws.cell(row=l, column=col_sit).value)
        for c in range(1, len(larguras) + 1):
            cel = ws.cell(row=l, column=c)
            cel.border = Border(bottom=fina)
            if cor:
                cel.fill = PatternFill('solid', fgColor=cor)
        ws.cell(row=l, column=13).alignment = Alignment(wrap_text=True, vertical='top')
        for c in (8, 9, 10, 11):
            ws.cell(row=l, column=c).number_format = '0.000000'
        ws.cell(row=l, column=12).number_format = '#,##0'

    wb.save(SAIDA)
    print(f"\n>> gravado: {SAIDA}")


if __name__ == "__main__":
    main()
