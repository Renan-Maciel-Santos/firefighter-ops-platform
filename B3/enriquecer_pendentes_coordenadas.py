# -*- coding: utf-8 -*-
"""Terceira passada nas 75 linhas que ficaram "a conferir".

As duas passadas anteriores buscaram só logradouro + número + cidade. O banco
guarda mais coisa sobre cada uma dessas ocorrências, e é isso que se usa aqui:

    bairro                75 de 75
    referência do despacho 73 de 75
    município do SDOV2     75 de 75

Três estratégias, aplicadas na ordem, parando na primeira que sustenta:

  1. BAIRRO — "Rua Sete, 61" é insolúvel; "Rua Sete, 61, Vila Paiva" não é. É o
     que desambigua nome genérico e via renomeada.

  2. REFERÊNCIA — para rodovia, onde o numeral é quilômetro e não endereço. O
     despacho registra ponto notável ("PRÓXIMO DO MERCADO AEROLESSA", "ENTRADA
     BAIRRO BUQUIRINHA II"), que geocodifica melhor do que o número jamais
     geocodificaria. Quando a referência traz KM explícito, ele vem antes.

  3. VIA + BAIRRO SEM NÚMERO — último recurso: localiza o trecho, não a porta.

O município buscado NÃO é fixo: vem do SDOV2. Quatro das seis "homônimas em
outro município" são de São José dos Campos e o geocodificador é que errava; uma
é de Monteiro Lobato de verdade — ali a coordenada está certa e quem errou foi a
planilha, que a classificou como SJC.

Uso:
    python enriquecer_pendentes_coordenadas.py
"""

import math
import os
import re
import sys
import time
import unicodedata

import pandas as pd
import psycopg2
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _env import exigir, opcional

ENTRADA = r"C:\dados\053-26 - enderecos x coordenadas - CORRIGIDO.xlsx"
SAIDA = r"C:\dados\053-26 - enderecos x coordenadas - CORRIGIDO v2.xlsx"

URL = "https://maps.googleapis.com/maps/api/geocode/json"
PAUSA = 0.06
PENDENTES = ('CONFERIR', 'PROVÁVEL ERRO')

# Acima: São José dos Campos tem cerca de 25 km de extensão urbana. Um ponto
# devolvido a mais de 5 km do lançado, JÁ com o bairro certo na busca, não é
# erro de despacho — é o geocodificador não tendo achado o endereço e devolvendo
# outra coisa. Adotar isso como correção seria trocar um erro por um pior.
# Ponto notável tem limite menor: ele localiza uma região, e região a mais de
# 3 km do lançamento não descreve a mesma ocorrência.
MAX_BAIRRO_M = 5000
MAX_REFERENCIA_M = 3000

RE_KM = re.compile(r'\bKM\s*\.?\s*(\d{1,3})', re.I)
RE_RODOVIA = re.compile(r'\b(RODOVIA|ROD|ACESSO|SP[\s-]?\d|DUTRA|TAMOIOS|BR[\s-]?\d)\b', re.I)
# Acima: ruído do texto livre do despacho que atrapalha a busca por ponto notável
RE_RUIDO = re.compile(r'\b(PROX(IMO)?|PRÓX(IMO)?|A|AO|AA|DA|DO|EM|FRENTE|SENT(IDO)?|N[ºO°]?)\b\.?', re.I)


def hav(a, b):
    (la1, lo1), (la2, lo2) = a, b
    R = 6371000.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _tok(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'\b(RUA|R|AVENIDA|AV|ESTRADA|ESTR|EST|RODOVIA|ROD|TRAVESSA|TV|PRACA|PCA|'
               r'ALAMEDA|AL|VIADUTO|DE|DA|DO|DOS|DAS|E)\b', ' ', s)
    return {t for t in re.sub(r'[^A-Z0-9 ]', ' ', s).split() if len(t) > 2}


def nome_confere(pedido, devolvido):
    a, b = _tok(pedido), _tok(str(devolvido).split(' - ')[0].split(',')[0])
    return True if not a else len(a & b) / len(a) >= 0.5


def consultar(chave, endereco):
    d = requests.get(URL, params={'address': endereco, 'key': chave,
                                  'region': 'br', 'language': 'pt-BR'}, timeout=25).json()
    time.sleep(PAUSA)
    if d.get('status') == 'OVER_QUERY_LIMIT':
        raise SystemExit("❌ Cota do Google esgotada.")
    if d.get('status') != 'OK' or not d.get('results'):
        return None
    r = d['results'][0]
    mun = None
    for c in r.get('address_components', []):
        if 'administrative_area_level_2' in c['types'] or 'locality' in c['types']:
            mun = c['long_name']
            break
    return {'endereco': r['formatted_address'], 'lat': r['geometry']['location']['lat'],
            'lon': r['geometry']['location']['lng'],
            'precisao': r['geometry']['location_type'], 'municipio': mun}


def limpar_referencia(ref):
    """Extrai o ponto notável do texto livre do despacho."""
    s = unicodedata.normalize('NFKD', str(ref)).encode('ascii', 'ignore').decode()
    s = re.split(r'[/,;]', s)
    # Acima: fica com o trecho mais longo, que costuma ser o ponto notável e não
    # o "sentido litoral" ou o "em frente"
    melhor = max((p.strip() for p in s), key=len, default='')
    melhor = RE_RUIDO.sub(' ', melhor)
    return ' '.join(melhor.split())


def carregar_banco(df):
    conn = psycopg2.connect(host=opcional('PG_HOST', 'localhost'), port=int(opcional('PG_PORT', '5432')),
                            dbname=opcional('PG_DB', '11gb'), user=opcional('PG_USER', 'admin'),
                            password=exigir('PG_PASS'))
    cur = conn.cursor()
    pares = [(int(r['Ocr Num']), r['dt'].date()) for _, r in df.iterrows()
             if pd.notna(r['Ocr Num']) and pd.notna(r['dt'])]
    cur.execute("""
        SELECT o.ocrnum, o.ocrdat, o.bairro_inicial, o.referencia_inicial, t.municipio
          FROM b3.ocorrencias o
          LEFT JOIN b3.tempo_resposta t ON t.id_sdov = o.id
         WHERE (o.ocrnum, o.ocrdat) = ANY(%s)
    """, (pares,))
    dados = {(r[0], r[1]): r for r in cur.fetchall()}
    conn.close()
    return dados


def main():
    chave = exigir('GOOGLE_MAPS_API_KEY')
    df = pd.read_excel(ENTRADA)
    df['dt'] = pd.to_datetime(df['Data'], errors='coerce', dayfirst=True)
    alvo = df['SITUAÇÃO'].isin(PENDENTES)
    print(f"linhas a reprocessar: {alvo.sum()}")

    banco = carregar_banco(df[alvo])
    print(f"casadas no banco: {len(banco)}")

    novas = {c: [None] * len(df) for c in ('sit', 'lat', 'lon', 'erro', 'oque', 'como', 'bairro', 'ref')}
    contagem = {}

    for i, r in df[alvo].iterrows():
        k = (int(r['Ocr Num']), r['dt'].date()) if pd.notna(r['dt']) and pd.notna(r['Ocr Num']) else None
        _, _, bairro, ref, mun_bd = banco.get(k, (None, None, None, None, None))
        alvo_mun = mun_bd or 'São José dos Campos'
        logr = str(r['Logradouro informado (col. H)']).strip()
        num = r['Nº / km (col. I)']
        num = '' if pd.isna(num) else str(num).split('.')[0]
        novas['bairro'][i] = bairro
        novas['ref'][i] = ref

        eh_rod = bool(RE_RODOVIA.search(logr))
        tentativas = []

        km = RE_KM.search(str(ref)) if ref else None
        if eh_rod and km:
            tentativas.append(('km da referência', f"{logr}, km {km.group(1)}, {alvo_mun}, SP, Brasil", False))
        if eh_rod and ref:
            ponto = limpar_referencia(ref)
            if len(ponto) > 6:
                tentativas.append(('ponto de referência', f"{ponto}, {alvo_mun}, SP, Brasil", False))
        if bairro and num:
            tentativas.append(('logradouro + nº + bairro', f"{logr}, {num}, {bairro}, {alvo_mun}, SP, Brasil", True))
        if bairro:
            tentativas.append(('logradouro + bairro', f"{logr}, {bairro}, {alvo_mun}, SP, Brasil", True))

        achou = None
        for rotulo, consulta, exige_nome in tentativas:
            g = consultar(chave, consulta)
            if not g:
                continue
            if g['municipio'] and alvo_mun.lower() not in g['municipio'].lower():
                continue
            if exige_nome and not nome_confere(logr, g['endereco']):
                continue
            achou = (rotulo, g)
            break

        contagem[achou[0] if achou else 'não resolvida'] = contagem.get(
            achou[0] if achou else 'não resolvida', 0) + 1

        if not achou:
            novas['sit'][i] = 'CONFERIR'
            novas['oque'][i] = ('Não foi possível localizar mesmo com bairro e referência do '
                                'despacho. Depende de consulta à guarnição.')
            continue

        rotulo, g = achou
        d = round(hav((g['lat'], g['lon']),
                      (float(r['Latitude informada (col. J)']), float(r['Longitude informada (col. K)']))))

        limite = MAX_REFERENCIA_M if rotulo in ('km da referência', 'ponto de referência') else MAX_BAIRRO_M
        if d > limite:
            novas['sit'][i] = 'CONFERIR'
            novas['oque'][i] = (
                f'A busca com {rotulo} devolveu ponto a {d/1000:.1f} km da coordenada lançada — '
                f'distância grande demais para ser erro de despacho dentro do mesmo município. '
                f'O endereço provavelmente não existe na base cartográfica; conferir com a guarnição.')
            continue

        if d <= 300:
            novas['sit'][i] = 'CERTA'
            novas['oque'][i] = f'Confirmada com o bairro do despacho ({bairro}); diferença de {d} m.'
        elif rotulo in ('km da referência', 'ponto de referência'):
            # Acima: ponto notável localiza a região, não a porta — nunca vira
            # "ERRADA" sozinho, porque trocar coordenada por região seria piorar.
            novas['sit'][i] = 'CONFERIR'
            novas['lat'][i] = round(g['lat'], 6); novas['lon'][i] = round(g['lon'], 6)
            novas['erro'][i] = d
            novas['oque'][i] = (f'Coordenada estimada pelo {rotulo} do despacho, a {d} m da lançada. '
                                f'Localiza a região, não o endereço exato — conferir antes de adotar.')
        elif g['precisao'] == 'ROOFTOP':
            novas['sit'][i] = 'ERRADA'
            novas['lat'][i] = round(g['lat'], 6); novas['lon'][i] = round(g['lon'], 6)
            novas['erro'][i] = d
            novas['oque'][i] = (f'Com o bairro do despacho ({bairro}), o endereço foi localizado no '
                                f'número exato, a {d} m da coordenada lançada.')
        else:
            novas['sit'][i] = 'PROVÁVEL ERRO'
            novas['lat'][i] = round(g['lat'], 6); novas['lon'][i] = round(g['lon'], 6)
            novas['erro'][i] = d
            novas['oque'][i] = (f'Com o bairro do despacho ({bairro}), a via foi localizada a {d} m '
                                f'da lançada, mas sem precisão de porta. Confirmar antes de adotar.')
        novas['como'][i] = f'Geocodificação com {rotulo} — conferência de 28/08'

    print("\n--- estratégia que resolveu ---")
    for k, v in sorted(contagem.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    for i in df.index[alvo]:
        df.at[i, 'SITUAÇÃO'] = novas['sit'][i]
        if novas['sit'][i] == 'CERTA':
            # Acima: linha confirmada não carrega coordenada de correção. Deixar
            # os dois campos preenchidos convidaria alguém a adotar uma troca
            # onde não há erro nenhum a corrigir.
            df.at[i, 'LATITUDE CORRETA'] = None
            df.at[i, 'LONGITUDE CORRETA'] = None
            df.at[i, 'ERRO (m)'] = None
        if novas['lat'][i] is not None and novas['sit'][i] != 'CERTA':
            df.at[i, 'LATITUDE CORRETA'] = novas['lat'][i]
            df.at[i, 'LONGITUDE CORRETA'] = novas['lon'][i]
            df.at[i, 'ERRO (m)'] = novas['erro'][i]
        df.at[i, 'O QUE ESTÁ ERRADO'] = novas['oque'][i]
        if novas['como'][i]:
            df.at[i, 'Como a coordenada correta foi obtida'] = novas['como'][i]

    df['Bairro (despacho)'] = novas['bairro']
    df['Referência (despacho)'] = novas['ref']
    df = df.drop(columns=['dt'])

    print("\n--- situação final das 673 ---")
    print(df['SITUAÇÃO'].value_counts().to_string())
    print(f"\ncom coordenada correta: {df['LATITUDE CORRETA'].notna().sum()}")

    df.to_excel(SAIDA, index=False, sheet_name='Endereços x coordenadas')
    print(f"\n>> gravado: {SAIDA}")


if __name__ == "__main__":
    main()
