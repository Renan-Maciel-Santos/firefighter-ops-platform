# -*- coding: utf-8 -*-
"""Arquivo único para o My Maps: todas as 673 ocorrências na posição correta.

Regra de escolha da coordenada, por linha:

    tem coordenada corrigida  -> usa a corrigida
    não tem                   -> usa a lançada, que já conferia

O resultado é uma camada só com o mapa que a apuração inteira serviu para
produzir: onde as ocorrências realmente aconteceram.

DUAS RESSALVAS QUE VÃO NO PRÓPRIO ARQUIVO, em coluna e não em nota de rodapé:

  2 ocorrências não batem e não puderam ser corrigidas. Se entrassem caladas
  junto das que conferem, o mapa mostraria dois pontos errados com a mesma cara
  dos certos. Vão marcadas como "posição não confirmada".

  18 estão na via certa mas sem o numeral conferido — rodovia, onde o número é
  quilômetro, e via de nome genérico. O ponto está na via, não necessariamente
  no trecho. Vão marcadas como "via confirmada, trecho não".

A coluna ORIGEM DA POSIÇÃO existe para isso: quem abrir o mapa pode agrupar por
ela e ver, de relance, quanta confiança cada ponto merece.

Uso:
    python mapa_ocorrencias_corrigidas.py
"""

import os
import re
import sys

import pandas as pd

# Acima: o texto livre do despacho vem com quebra de linha DENTRO da célula, e
# com o "_x000D_" que o Excel escreve no lugar do carriage return. O CSV
# resultante é tecnicamente válido — o campo fica entre aspas —, mas o parser do
# My Maps quebra nele: o arquivo tem mais linhas físicas do que registros e a
# importação falha sem dizer por quê. Foi isto que impediu a importação.
RE_SUJEIRA = re.compile(r'(_x000D_|[\r\n\t\x00-\x1f])')


def limpar_texto(v):
    if pd.isna(v):
        return v
    return ' '.join(RE_SUJEIRA.sub(' ', str(v)).split())

BASE = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\dados\053-26 - enderecos x coordenadas (1).xlsx"
APURADO = r"C:\dados\053-26 - enderecos x coordenadas - APURADO.xlsx"
SAIDA = sys.argv[2] if len(sys.argv) > 2 else \
    r"C:\dados\053-26 - ocorrencias no mapa.csv"

LAT_I, LON_I = 'Latitude informada (col. J)', 'Longitude informada (col. K)'
LAT_C, LON_C = 'LATITUDE CORRETA', 'LONGITUDE CORRETA'
CHAVE = 'Linha na planilha original'


def main():
    d = pd.read_excel(BASE)

    # Acima: a planilha simplificada não distingue "conferia" de "não conferia e
    # não deu para corrigir" — as duas aparecem sem coordenada corrigida. Sem
    # este cruzamento, 2 pontos errados entrariam no mapa como se fossem certos.
    ressalva = {}
    if os.path.exists(APURADO):
        a = pd.read_excel(APURADO)
        for _, r in a.iterrows():
            b = str(r['BATE?'])
            if b.startswith('BATE (via'):
                ressalva[r[CHAVE]] = 'via confirmada, trecho não'
            elif b in ('NÃO BATE', 'SEM RESPOSTA') and pd.isna(r['LATITUDE CORRETA']):
                ressalva[r[CHAVE]] = 'posição NÃO confirmada'
    else:
        print("⚠️  APURADO não encontrado — as ressalvas por linha não entram.")

    lat, lon, origem, erro = [], [], [], []
    for _, r in d.iterrows():
        marca = ressalva.get(r[CHAVE])
        if pd.notna(r[LAT_C]):
            lat.append(r[LAT_C]); lon.append(r[LON_C])
            origem.append('Corrigida')
            erro.append(int(r['ERRO (m)']))
        else:
            lat.append(r[LAT_I]); lon.append(r[LON_I])
            origem.append(marca.capitalize() if marca else 'Conferida')
            erro.append(None)

    num = d['Nº / km (col. I)'].apply(lambda x: '' if pd.isna(x) else f", {str(x).split('.')[0]}")
    s = pd.DataFrame({
        'Endereço': d['Logradouro informado (col. H)'].astype(str) + num,
        'Latitude': lat,
        'Longitude': lon,
        'ORIGEM DA POSIÇÃO': origem,
        'Erro corrigido (m)': erro,
        'Ocr Num': d['Ocr Num'],
        'Data': pd.to_datetime(d['Data'], errors='coerce').dt.strftime('%d/%m/%Y'),
        'Referência': d['Referência do endereço (col. G)'],
        'Linha na planilha original': d[CHAVE],
    })

    for c in s.columns:
        if s[c].dtype == object:
            s[c] = s[c].map(limpar_texto)

    print(s['ORIGEM DA POSIÇÃO'].value_counts().to_string())
    fora = (~s['Latitude'].between(-24.5, -22.0)) | (~s['Longitude'].between(-46.5, -44.0))
    print(f"\nfora do Vale do Paraíba: {fora.sum()}   |   sem coordenada: {s['Latitude'].isna().sum()}")

    # Acima: ponto decimal e utf-8 sem BOM — o My Maps só aceita ponto, e a
    # planilha aberta e salva no Excel em pt-BR volta com vírgula.
    s.to_csv(SAIDA, index=False, encoding='utf-8', decimal='.')
    print(f"\n>> gravado: {SAIDA}  ({len(s)} pontos)")


if __name__ == "__main__":
    main()
