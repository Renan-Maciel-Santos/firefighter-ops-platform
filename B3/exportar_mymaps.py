# -*- coding: utf-8 -*-
"""Prepara a apuração de coordenadas para importar no Google My Maps.

O My Maps é exigente de um jeito específico, e quase todo problema de importação
vem de uma destas quatro coisas:

  Separador decimal. Ele só aceita PONTO. Planilha salva em Excel com locale
  pt-BR grava vírgula, e o mapa importa sem erro nenhum, plotando tudo no meio
  do oceano ou nada. Por isso a saída aqui é CSV escrito direto pelo pandas, e
  o arquivo NÃO deve ser aberto e salvo no Excel antes de subir.

  Uma camada por importação. Ele não separa categorias sozinho: cada arquivo
  vira uma camada. Daí a saída ser três CSVs e não um.

  Limite de 2.000 pontos por camada e 10.000 por mapa. Com 673 sobra folga.

  Coluna de título. Ele pergunta qual coluna nomeia o marcador; se for um
  código, o mapa fica ilegível. A primeira coluna de cada arquivo já é um rótulo
  pronto para leitura.

O KML de deslocamento é o que o My Maps não monta sozinho: uma linha ligando
onde a ocorrência foi lançada até onde ela realmente fica. Ver 147 riscos
cruzando o município comunica o problema melhor que qualquer tabela.

Uso:
    python exportar_mymaps.py [entrada.xlsx] [pasta_de_saida]
"""

import html
import os
import re
import sys

import pandas as pd

ENTRADA = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\dados\053-26 - enderecos x coordenadas (1).xlsx"
PASTA = sys.argv[2] if len(sys.argv) > 2 else \
    r"C:\dados\mymaps_053-26"

LAT_I, LON_I = 'Latitude informada (col. J)', 'Longitude informada (col. K)'
LAT_C, LON_C = 'LATITUDE CORRETA', 'LONGITUDE CORRETA'


# Acima: quebra de linha dentro da célula (e o "_x000D_" do Excel) faz o CSV
# ter mais linhas físicas que registros. O arquivo continua válido, mas o My
# Maps não importa e não explica.
RE_SUJEIRA = re.compile(r'(_x000D_|[\r\n\t\x00-\x1f])')


def limpar_texto(v):
    if pd.isna(v):
        return v
    return ' '.join(RE_SUJEIRA.sub(' ', str(v)).split())


def faixa(m):
    if pd.isna(m):
        return None
    if m < 500:
        return '1. até 500 m'
    if m < 1000:
        return '2. 500 m a 1 km'
    if m < 5000:
        return '3. 1 a 5 km'
    return '4. acima de 5 km'


def rotulo(r):
    num = r['Nº / km (col. I)']
    num = '' if pd.isna(num) else f", {str(num).split('.')[0]}"
    return f"{r['Logradouro informado (col. H)']}{num}"


def main():
    os.makedirs(PASTA, exist_ok=True)
    d = pd.read_excel(ENTRADA)
    d['Endereço'] = d.apply(rotulo, axis=1)
    d['Data'] = pd.to_datetime(d['Data'], errors='coerce').dt.strftime('%d/%m/%Y')
    d['Faixa do erro'] = d['ERRO (m)'].map(faixa)
    errada = d[LAT_C].notna()

    comuns = ['Endereço', 'Ocr Num', 'Data', 'Referência do endereço (col. G)',
              'Linha na planilha original']

    # ---- camada 1: as que conferem
    ok = d[~errada].copy()
    c1 = ok[comuns].copy()
    c1['Latitude'] = ok[LAT_I]
    c1['Longitude'] = ok[LON_I]
    c1 = c1.rename(columns={'Referência do endereço (col. G)': 'Referência'})

    # ---- camada 2: onde foi lançado (errado)
    er = d[errada].copy()
    c2 = er[comuns].copy()
    c2['Latitude'] = er[LAT_I]
    c2['Longitude'] = er[LON_I]
    c2['Erro (m)'] = er['ERRO (m)'].astype(int)
    c2['Faixa do erro'] = er['Faixa do erro']
    c2 = c2.rename(columns={'Referência do endereço (col. G)': 'Referência'})

    # ---- camada 3: onde deveria estar
    c3 = er[comuns].copy()
    c3['Latitude'] = er[LAT_C]
    c3['Longitude'] = er[LON_C]
    c3['Erro (m)'] = er['ERRO (m)'].astype(int)
    c3['Faixa do erro'] = er['Faixa do erro']
    c3 = c3.rename(columns={'Referência do endereço (col. G)': 'Referência'})

    arquivos = [
        ('1 - coordenadas conferidas.csv', c1),
        ('2 - erradas - onde foi lancado.csv', c2),
        ('3 - erradas - onde deveria estar.csv', c3),
    ]
    for nome, tabela in arquivos:
        for c in tabela.columns:
            if tabela[c].dtype == object:
                tabela[c] = tabela[c].map(limpar_texto)
        caminho = os.path.join(PASTA, nome)
        # Acima: utf-8 puro e ponto decimal. Sem BOM porque o My Maps engasga
        # com ele em alguns casos; se abrir no Excel, os acentos saem tortos —
        # é o preço de o mapa funcionar, e o destino aqui é o mapa.
        tabela.to_csv(caminho, index=False, encoding='utf-8', decimal='.')
        print(f"  {nome}: {len(tabela)} pontos")

    # ---- KML com as linhas de deslocamento
    linhas = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
              '<name>Deslocamento das coordenadas erradas</name>',
              '<Style id="desloc"><LineStyle><color>ff2222b2</color><width>2</width></LineStyle></Style>']
    for _, r in er.iterrows():
        nome = html.escape(limpar_texto(f"{r['Endereço']} — {int(r['ERRO (m)'])} m"))
        desc = html.escape(f"Ocorrência {r['Ocr Num']} de {r['Data']}. "
                           f"Lançada a {int(r['ERRO (m)'])} m do endereço.")
        linhas += [
            '<Placemark>', f'<name>{nome}</name>', f'<description>{desc}</description>',
            '<styleUrl>#desloc</styleUrl>',
            '<LineString><tessellate>1</tessellate><coordinates>',
            f"{r[LON_I]},{r[LAT_I]},0 {r[LON_C]},{r[LAT_C]},0",
            '</coordinates></LineString></Placemark>']
    linhas.append('</Document></kml>')

    kml = os.path.join(PASTA, '4 - linhas de deslocamento.kml')
    with open(kml, 'w', encoding='utf-8') as f:
        f.write('\n'.join(linhas))
    print(f"  4 - linhas de deslocamento.kml: {len(er)} linhas")

    print(f"\n>> pasta: {PASTA}")


if __name__ == "__main__":
    main()
