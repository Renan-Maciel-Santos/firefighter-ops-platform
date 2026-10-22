# -*- coding: utf-8 -*-
"""Geocodificação REVERSA das 673 coordenadas: o que existe em cada ponto.

As passadas anteriores perguntavam "onde fica este endereço?". Esta pergunta é a
inversa — "o que há nesta coordenada?" — e é melhor para o que se quer saber,
por três motivos:

  1. Parte do objeto validado. A coordenada é o dado sob suspeita; o endereço é
     só o rótulo. Geocodificar o endereço testa o rótulo; reverter a coordenada
     testa a coordenada.

  2. Funciona onde a busca direta falha. Endereço que não existe em base
     cartográfica nenhuma — estrada rural, via informal, rua renomeada — não
     tem resposta na busca direta. Mas todo ponto do mapa tem uma via embaixo.

  3. Não tem ambiguidade de homônimo. "Rua Sete" existe em seis bairros e a
     busca direta escolhe um; a coordenada aponta para um lugar só.

O teste é simples: a via que existe no ponto é a mesma que o despacho informou?
  bate       -> a coordenada está na via certa
  não bate   -> a coordenada aponta para outra via; o endereço no ponto vai na
                planilha, que é justamente o que faltava para conferir à mão

Uso:
    python reverso_coordenadas.py [entrada.xlsx] [saida.xlsx]
"""

import os
import re
import sys
import time
import unicodedata

import pandas as pd
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _env import exigir

ENTRADA = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\dados\053-26 - enderecos x coordenadas - CORRIGIDO v2.xlsx"
SAIDA = sys.argv[2] if len(sys.argv) > 2 else \
    r"C:\dados\053-26 - enderecos x coordenadas - CONFERIDO.xlsx"

URL = "https://maps.googleapis.com/maps/api/geocode/json"
PAUSA = 0.06


def _tok(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'\b(RUA|R|AVENIDA|AV|ESTRADA|ESTR|EST|RODOVIA|ROD|TRAVESSA|TV|PRACA|PCA|'
               r'ALAMEDA|AL|VIADUTO|ACESSO|VIA|DE|DA|DO|DOS|DAS|E)\b', ' ', s)
    return {t for t in re.sub(r'[^A-Z0-9 ]', ' ', s).split() if len(t) > 2}


def comparar(informado, no_ponto):
    """Quanto do nome informado aparece na via encontrada no ponto."""
    a, b = _tok(informado), _tok(no_ponto)
    if not a or not b:
        return None
    return len(a & b) / len(a)


def reverter(chave, lat, lon, tentativas=4):
    # Acima: a primeira rodada morreu na linha ~60 com ConnectionResetError e
    # levou junto as 60 consultas já pagas, porque não havia nem retentativa nem
    # gravação parcial. Queda de conexão em lote de centenas não é exceção, é
    # rotina — tratar como erro fatal desperdiça cota e tempo.
    for n in range(tentativas):
        try:
            d = requests.get(URL, params={'latlng': f"{lat},{lon}", 'key': chave,
                                          'language': 'pt-BR'}, timeout=25).json()
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if n == tentativas - 1:
                return {'falhou': True}
            time.sleep(2 ** n)
    time.sleep(PAUSA)
    if d.get('status') == 'OVER_QUERY_LIMIT':
        raise SystemExit("❌ Cota do Google esgotada.")
    if d.get('status') != 'OK' or not d.get('results'):
        return None

    # Acima: o retorno vem do mais específico para o mais amplo. A via é o que
    # interessa, e ela só aparece nos primeiros resultados — os últimos são
    # bairro, cidade, estado e país, que responderiam "sim, está no Brasil".
    via = bairro = municipio = None
    endereco = d['results'][0]['formatted_address']
    for res in d['results'][:4]:
        for c in res.get('address_components', []):
            t = c['types']
            if 'route' in t and not via:
                via = c['long_name']
            if ('sublocality' in t or 'neighborhood' in t) and not bairro:
                bairro = c['long_name']
            if ('administrative_area_level_2' in t or 'locality' in t) and not municipio:
                municipio = c['long_name']
    return {'endereco': endereco, 'via': via, 'bairro': bairro, 'municipio': municipio}


def _gravar(df, cols, caminho):
    saida = df.copy()
    saida['No ponto — endereço'] = cols['end']
    saida['No ponto — via'] = cols['via']
    saida['No ponto — bairro'] = cols['bai']
    saida['No ponto — município'] = cols['mun']
    saida['A coordenada bate com o logradouro?'] = cols['bate']
    saida['O que há na coordenada'] = cols['nota']
    saida.to_excel(caminho, index=False, sheet_name='Endereços x coordenadas')
    return saida


def main():
    chave = exigir('GOOGLE_MAPS_API_KEY')
    df = pd.read_excel(ENTRADA)
    print(f"coordenadas a reverter: {len(df)}")

    cols = {c: [None] * len(df) for c in ('end', 'via', 'bai', 'mun', 'bate', 'nota')}

    for n, (i, r) in enumerate(df.iterrows(), 1):
        lat, lon = r['Latitude informada (col. J)'], r['Longitude informada (col. K)']
        if pd.isna(lat) or pd.isna(lon):
            cols['bate'][i] = 'SEM COORDENADA'
            continue
        g = reverter(chave, float(lat), float(lon))
        if g and g.get('falhou'):
            cols['bate'][i] = 'FALHA DE CONEXÃO'
            continue
        if not g:
            cols['bate'][i] = 'SEM RETORNO'
            continue

        cols['end'][i] = g['endereco']
        cols['via'][i] = g['via']
        cols['bai'][i] = g['bairro']
        cols['mun'][i] = g['municipio']

        sim = comparar(r['Logradouro informado (col. H)'], g['via']) if g['via'] else None
        mun_ok = (not g['municipio']) or ('josé dos campos' in str(g['municipio']).lower())

        if not mun_ok:
            cols['bate'][i] = 'OUTRO MUNICÍPIO'
            cols['nota'][i] = (f"A coordenada cai em {g['municipio']}, não em São José dos Campos. "
                               f"Ou a coordenada está errada, ou a ocorrência não é deste município.")
        elif sim is None:
            cols['bate'][i] = 'SEM VIA NO PONTO'
            cols['nota'][i] = (f"Não há via mapeada exatamente neste ponto. O Google descreve o "
                               f"local como: {g['endereco']}.")
        elif sim >= 0.5:
            cols['bate'][i] = 'BATE'
            cols['nota'][i] = f"A via no ponto é a mesma informada no despacho ({g['via']})."
        else:
            cols['bate'][i] = 'NÃO BATE'
            cols['nota'][i] = (f"A coordenada aponta para {g['via']}"
                               f"{', bairro ' + g['bairro'] if g['bairro'] else ''}, e não para "
                               f"'{r['Logradouro informado (col. H)']}' como diz o despacho.")

        if n % 100 == 0:
            print(f"  {n} revertidas...", flush=True)
            # Acima: checkpoint a cada 100. Uma queda no meio não pode custar
            # tudo de novo — a cota gasta não volta.
            _gravar(df, cols, SAIDA + '.parcial.xlsx')

    df = _gravar(df, cols, SAIDA)

    print("\n--- a coordenada bate com o logradouro informado? ---")
    print(df['A coordenada bate com o logradouro?'].value_counts(dropna=False).to_string())
    print("\n--- cruzando com a situação apurada ---")
    print(pd.crosstab(df['SITUAÇÃO'], df['A coordenada bate com o logradouro?']).to_string())

    df.to_excel(SAIDA, index=False, sheet_name='Endereços x coordenadas')
    print(f"\n>> gravado: {SAIDA}")


if __name__ == "__main__":
    main()
