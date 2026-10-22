# -*- coding: utf-8 -*-
"""Reduz a apuração de coordenadas a uma planilha no formato da original.

O arquivo de trabalho acumulou 40+ colunas de rastro metodológico — necessário
para auditar, inútil para quem vai corrigir o lançamento. Aqui fica só o que a
pessoa precisa ver: as colunas originais, a situação, a coordenada certa quando
existe, o erro em metros e uma frase dizendo o que está errado.

As duas origens de coordenada correta entram unificadas:
  73 linhas  — corrigidas na apuração de 21/08 (marco quilométrico, Google)
  42 linhas  — corrigidas na conferência de 28/08 (Google, com guarda de nome)

Uma aba só, uma linha por ocorrência, na mesma ordem da planilha original.
"""

import os
import sys

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ENTRADA = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\dados\053-26 - VEREDITO CONSOLIDADO.xlsx"
SAIDA = sys.argv[2] if len(sys.argv) > 2 else \
    r"C:\dados\053-26 - enderecos x coordenadas - CORRIGIDO.xlsx"

VERMELHO = "9E1B1B"
AMARELO = "F8EEDC"
VERDE = "E4F1EB"
ROSA = "FBE9EA"

# Acima: veredito -> (situação curta, precisa de olhada humana)
MAPA = {
    'CERTA — confirmada por duas fontes':                     ('CERTA', False),
    'ERRADA — adotar a coordenada do Google':                 ('ERRADA', False),
    'PROVÁVEL ERRO — confirmar antes de adotar':              ('PROVÁVEL ERRO', True),
    'VIA EXTENSA — conferir pelo km':                         ('CONFERIR', True),
    'VIA CONFERE, NUMERAL NÃO — conferir':                    ('CONFERIR', True),
    'CONFERIR MANUALMENTE — nome genérico de via':            ('CONFERIR', True),
    'CONFERIR MANUALMENTE — retorno não corresponde à via':   ('CONFERIR', True),
    'CONFERIR MANUALMENTE — via homônima em outro município': ('CONFERIR', True),
    'CONFERIR MANUALMENTE — sem retorno utilizável':          ('CONFERIR', True),
}

# Acima: frase curta por veredito. O texto longo da justificativa fica no
# arquivo de trabalho; aqui entra o que cabe numa célula sem rolar.
CURTO = {
    'ERRADA — adotar a coordenada do Google':
        'Coordenada lançada está no trecho errado da via. Endereço localizado no número exato.',
    'PROVÁVEL ERRO — confirmar antes de adotar':
        'Coordenada provavelmente no trecho errado. Número estimado na quadra — confirmar antes de trocar.',
    'VIA EXTENSA — conferir pelo km':
        'Rodovia ou acesso: o numeral não é endereço, é referência de km. Conferir pelo marco quilométrico.',
    'VIA CONFERE, NUMERAL NÃO — conferir':
        'A via está certa; não foi possível localizar o número. Conferir o trecho.',
    'CONFERIR MANUALMENTE — nome genérico de via':
        'Nome genérico ("Rua Um", "Rua Sete") que se repete em vários bairros. Informar o bairro.',
    'CONFERIR MANUALMENTE — retorno não corresponde à via':
        'A busca devolveu via de outro nome. Pode ser rua renomeada ou erro de grafia no despacho.',
    'CONFERIR MANUALMENTE — via homônima em outro município':
        'Via encontrada em outro município. Confirmar de qual cidade é a ocorrência.',
    'CONFERIR MANUALMENTE — sem retorno utilizável':
        'Não foi possível localizar o endereço. Depende de consulta à guarnição.',
}

COLUNAS = [
    ('Linha na planilha original', 10),
    ('Município', 20),
    ('Data', 12),
    ('Ocr Num', 11),
    ('Referência do endereço (col. G)', 30),
    ('Logradouro informado (col. H)', 34),
    ('Nº / km (col. I)', 10),
    ('Latitude informada (col. J)', 14),
    ('Longitude informada (col. K)', 14),
    ('SITUAÇÃO', 15),
    ('LATITUDE CORRETA', 15),
    ('LONGITUDE CORRETA', 15),
    ('ERRO (m)', 11),
    ('O QUE ESTÁ ERRADO', 62),
    ('Como a coordenada correta foi obtida', 34),
]


def main():
    d = pd.read_excel(ENTRADA, sheet_name='Análise completa')
    s = pd.DataFrame()

    for c in ('Linha na planilha original', 'Município', 'Data', 'Ocr Num',
              'Referência do endereço (col. G)', 'Logradouro informado (col. H)',
              'Nº / km (col. I)', 'Latitude informada (col. J)', 'Longitude informada (col. K)'):
        s[c] = d[c]

    sit, lat, lon, erro, oque, como = [], [], [], [], [], []
    for _, r in d.iterrows():
        v = r.get('VEREDITO FINAL')

        # Acima: as 73 ERRADA já vieram resolvidas de 21/08 e não foram
        # reprocessadas — passam adiante como estão, sem serem reavaliadas.
        if r['SITUAÇÃO'] == 'ERRADA':
            sit.append('ERRADA')
            lat.append(r['LATITUDE CORRETA']); lon.append(r['LONGITUDE CORRETA'])
            erro.append(r['ERRO (m)'])
            oque.append(r['MOTIVO / O QUE ESTÁ ERRADO'])
            como.append(r['Como a coordenada correta foi obtida'])
            continue

        curto, _precisa = MAPA.get(v, ('CONFERIR', True))
        sit.append(curto)
        gl, go = r.get('COORDENADA SUGERIDA — LAT'), r.get('COORDENADA SUGERIDA — LON')
        tem = pd.notna(gl)
        lat.append(gl if tem else None)
        lon.append(go if tem else None)
        # Acima: erro só faz sentido quando existe coordenada certa para comparar
        erro.append(r.get('Google — distância até a lançada (m)') if tem else None)
        oque.append(CURTO.get(v))
        como.append('Geocodificação (Google) — conferência de 28/08' if tem else None)

    s['SITUAÇÃO'] = sit
    s['LATITUDE CORRETA'] = lat
    s['LONGITUDE CORRETA'] = lon
    s['ERRO (m)'] = erro
    s['O QUE ESTÁ ERRADO'] = oque
    s['Como a coordenada correta foi obtida'] = como

    print(s['SITUAÇÃO'].value_counts().to_string())
    print(f"\ncom coordenada correta preenchida: {s['LATITUDE CORRETA'].notna().sum()}")

    with pd.ExcelWriter(SAIDA, engine='openpyxl') as w:
        s.to_excel(w, sheet_name='Endereços x coordenadas', index=False)
        ws = w.sheets['Endereços x coordenadas']

        cab = Font(bold=True, color='FFFFFF', size=10)
        fundo = PatternFill('solid', fgColor=VERMELHO)
        for i, (nome, larg) in enumerate(COLUNAS, start=1):
            c = ws.cell(row=1, column=i)
            c.font = cab; c.fill = fundo
            c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            ws.column_dimensions[get_column_letter(i)].width = larg
        ws.row_dimensions[1].height = 30
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions

        # Acima: a cor carrega a mesma informação da coluna SITUAÇÃO. É
        # redundância proposital — quem filtra usa a coluna, quem folheia usa a cor.
        cores = {'ERRADA': ROSA, 'PROVÁVEL ERRO': AMARELO, 'CONFERIR': AMARELO, 'CERTA': VERDE}
        for linha in range(2, ws.max_row + 1):
            cor = cores.get(ws.cell(row=linha, column=10).value)
            if not cor:
                continue
            f = PatternFill('solid', fgColor=cor)
            for col in range(1, len(COLUNAS) + 1):
                ws.cell(row=linha, column=col).fill = f
            ws.cell(row=linha, column=14).alignment = Alignment(wrap_text=True, vertical='top')

    print(f"\n>> gravado: {SAIDA}")


if __name__ == "__main__":
    main()
