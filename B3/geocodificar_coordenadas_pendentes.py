# -*- coding: utf-8 -*-
"""Geocodifica as pendentes da validação de endereços x coordenadas (SJC).

Complementa o resolver_coordenadas_pendentes.py, que confirma por histórico
interno. Aqui a fonte é externa (Google Geocoding), o que dá duas coisas que o
histórico não dá:

  1. Resolve via SEM histórico — rua nova, estrada rural com uma ocorrência só.
  2. Serve de conferência independente para as que o histórico já confirmou.
     Sem isso a confirmação é circular: prova que a corporação sempre lançou
     naquele ponto, não que o ponto está certo.

DUAS ARMADILHAS DO GEOCODIFICADOR, tratadas explicitamente:

  Município errado. "Avenida das Indústrias, 687, São José dos Campos" volta em
  Jacareí, sem erro nenhum — o Google encontra a via homônima mais próxima e
  ignora o município pedido. Todo retorno é conferido contra o locality dos
  address_components; o que não for de SJC é descartado, não adotado.

  Precisão silenciosa. ROOFTOP é o número na porta; GEOMETRIC_CENTER é o meio
  da quadra; APPROXIMATE é o centro do bairro ou da cidade. Os três voltam com
  a mesma cara no JSON. A precisão vai para a planilha em coluna própria,
  porque adotar um APPROXIMATE como endereço exato seria pior que não ter nada.

Uso:
    python geocodificar_coordenadas_pendentes.py
"""

import math
import os
import re
import sys
import time
import unicodedata

import pandas as pd
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _env import exigir

# Acima: entrada, saida e quais SITUACOES processar vem por linha de comando,
# porque o mesmo cruzamento serve para lotes diferentes: primeiro as 57
# pendentes, depois as 543 marcadas CERTA — que nunca passaram por conferencia
# externa e, pelo que as pendentes mostraram, nao podem ser tomadas como certas
# so porque o historico interno concorda com elas.
ENTRADA = sys.argv[1] if len(sys.argv) > 1 else r"C:\dados\053-26 - enderecos x coordenadas - pendentes resolvidas.xlsx"
SAIDA = sys.argv[2] if len(sys.argv) > 2 else r"C:\dados\053-26 - enderecos x coordenadas - apurado final.xlsx"
SITUACOES = sys.argv[3].split("|") if len(sys.argv) > 3 else ['NÃO CONFIRMADA', 'CERTA (NUMERAL A CONFERIR)']

MUNICIPIO = "São José dos Campos"
URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Acima: Correções mecânicas de digitação observadas na própria planilha. Só
# entram trocas em que a forma errada não existe como palavra — nada de
# adivinhar nome de rua, que seria inventar endereço.
CORRECOES = {
    r'\bESTADA\b': 'ESTRADA',
    r'\bNMICIPAL\b': 'MUNICIPAL',
    r'\bDOUTRO\b': 'DOUTOR',
    r'\bEDIIMILSON\b': 'EDIMILSON',
    r'\bQUIMARAES\b': 'GUIMARAES',
    r'\bGLAUDSTON\b': 'GLADSTON',
    r'\bUBIRATAM\b': 'UBIRATAN',
}

# Acima: Prefixo de plus code do Google no meio do logradouro ("(588MRXXW+RR)")
# — lixo de copiar e colar, atrapalha a busca.
RE_PLUSCODE = re.compile(r'\(?\b[0-9A-Z]{4,8}\+[0-9A-Z]{2,3}\b\)?')

PAUSA = 0.06


def limpar(logradouro):
    """Devolve (consulta_limpa, o_que_mudou)."""
    s = str(logradouro).strip()
    mudou = []
    novo = RE_PLUSCODE.sub(' ', s)
    if novo != s:
        mudou.append('removido plus code')
        s = novo
    alto = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().upper()
    for errado, certo in CORRECOES.items():
        if re.search(errado, alto):
            s = re.sub(errado, certo, alto)
            alto = s
            mudou.append(f"{errado.strip(chr(92)+'b')} -> {certo}")
    return ' '.join(s.split()), '; '.join(mudou) or None


def haversine_m(a, b):
    (la1, lo1), (la2, lo2) = a, b
    r = 6371000.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def municipio_do_retorno(resultado):
    for c in resultado.get('address_components', []):
        if 'administrative_area_level_2' in c['types'] or 'locality' in c['types']:
            return c['long_name']
    return None


def consultar(chave, endereco):
    r = requests.get(URL, params={'address': endereco, 'key': chave,
                                  'region': 'br', 'language': 'pt-BR'}, timeout=25)
    d = r.json()
    time.sleep(PAUSA)
    if d.get('status') == 'OVER_QUERY_LIMIT':
        raise SystemExit("❌ Cota do Google esgotada — interrompido para não gastar à toa.")
    if d.get('status') != 'OK' or not d.get('results'):
        return None
    res = d['results'][0]
    return {
        'endereco': res['formatted_address'],
        'lat': res['geometry']['location']['lat'],
        'lon': res['geometry']['location']['lng'],
        'precisao': res['geometry']['location_type'],
        'municipio': municipio_do_retorno(res),
    }


def main():
    chave = exigir('GOOGLE_MAPS_API_KEY')
    df = pd.read_excel(ENTRADA, sheet_name='Análise completa')
    alvo = df['SITUAÇÃO'].isin(SITUACOES)
    print(f"linhas a geocodificar: {alvo.sum()}")

    # Acima: parte do que ja existe na planilha, para o lote novo somar ao
    # anterior em vez de zerar o trabalho da rodada passada.
    mapa = {'g_end': 'Google — endereço (28/08)', 'g_lat': 'Google — latitude',
            'g_lon': 'Google — longitude', 'g_prec': 'Google — precisão',
            'g_mun': 'Google — município do retorno',
            'g_dist': 'Google — distância até a lançada (m)',
            'g_ok': 'Google — aproveitamento', 'g_consulta': 'Google — consulta enviada',
            'g_ajuste': 'Google — ajuste de grafia'}
    col = {k: (list(df[v]) if v in df.columns else [None] * len(df)) for k, v in mapa.items()}

    feitas = 0
    for i, r in df[alvo].iterrows():
        logr, ajuste = limpar(r['Logradouro informado (col. H)'])
        num = r['Nº / km (col. I)']
        num = '' if pd.isna(num) else str(num).split('.')[0]
        consulta = f"{logr}, {num}, {MUNICIPIO}, SP, Brasil" if num else f"{logr}, {MUNICIPIO}, SP, Brasil"

        g = consultar(chave, consulta)
        # Acima: sem o número o Google acha a via que com o número ele erra
        if g is None or (g['municipio'] and MUNICIPIO.lower() not in g['municipio'].lower()):
            g2 = consultar(chave, f"{logr}, {MUNICIPIO}, SP, Brasil")
            if g2 and g2['municipio'] and MUNICIPIO.lower() in g2['municipio'].lower():
                g = g2
                ajuste = '; '.join(filter(None, [ajuste, 'consultado sem o numeral']))

        feitas += 1
        col['g_consulta'][i] = consulta
        col['g_ajuste'][i] = ajuste
        if g is None:
            col['g_ok'][i] = 'NÃO ENCONTRADO'
            continue

        no_municipio = bool(g['municipio']) and MUNICIPIO.lower() in g['municipio'].lower()
        col['g_end'][i] = g['endereco']
        col['g_lat'][i] = round(g['lat'], 6)
        col['g_lon'][i] = round(g['lon'], 6)
        col['g_prec'][i] = g['precisao']
        col['g_mun'][i] = g['municipio']
        lat_i, lon_i = r['Latitude informada (col. J)'], r['Longitude informada (col. K)']
        if pd.notna(lat_i):
            col['g_dist'][i] = round(haversine_m((g['lat'], g['lon']), (float(lat_i), float(lon_i))))
        col['g_ok'][i] = 'OK' if no_municipio else 'FORA DO MUNICÍPIO — descartado'

        if feitas % 10 == 0:
            print(f"  {feitas} consultadas...")

    df['Google — endereço (28/08)'] = col['g_end']
    df['Google — latitude'] = col['g_lat']
    df['Google — longitude'] = col['g_lon']
    df['Google — precisão'] = col['g_prec']
    df['Google — município do retorno'] = col['g_mun']
    df['Google — distância até a lançada (m)'] = col['g_dist']
    df['Google — aproveitamento'] = col['g_ok']
    df['Google — consulta enviada'] = col['g_consulta']
    df['Google — ajuste de grafia'] = col['g_ajuste']

    res = df.loc[alvo]
    print("\n--- aproveitamento ---")
    print(res['Google — aproveitamento'].value_counts(dropna=False).to_string())
    print("\n--- precisão (só os aproveitados) ---")
    print(res[res['Google — aproveitamento'] == 'OK']['Google — precisão'].value_counts().to_string())

    with pd.ExcelWriter(SAIDA, engine='openpyxl') as w:
        df.to_excel(w, sheet_name='Análise completa', index=False)
        res.to_excel(w, sheet_name='Pendentes apuradas', index=False)
        for aba in ('Resumo', 'Coordenadas repetidas', 'Focos INPE x SIOPM'):
            pd.read_excel(ENTRADA, sheet_name=aba).to_excel(w, sheet_name=aba, index=False)
    print(f"\n>> gravado: {SAIDA}")


if __name__ == "__main__":
    main()
