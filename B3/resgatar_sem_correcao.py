# -*- coding: utf-8 -*-
"""Preenche as linhas que não batem e ficaram sem coordenada corrigida.

Por que elas ficaram vazias — e o erro de raciocínio que causou isso:

    O limite de plausibilidade de 5 km foi criado para um caso real: a busca com
    bairro devolvia pontos a 21 km e adotá-los seria trocar um erro por um maior.
    A regra supunha que a coordenada lançada estava aproximadamente certa, de
    modo que distância enorme só podia significar falha da busca.

    Para coordenada REUTILIZADA essa premissa é falsa. Ali o ponto é de outra
    ocorrência: a distância enorme é o sintoma esperado, não um sinal de que a
    busca errou. O guarda estava descartando a busca boa por causa da coordenada
    ruim — exatamente ao contrário do que deveria.

    A correção não é remover o guarda, é condicioná-lo: ele vale quando a
    coordenada é evidência; não vale quando ela é o que está sob suspeita.

Três estratégias, da mais forte para a mais fraca, e a confiança vai declarada
em coluna própria porque uma coordenada de eixo de via não é uma de porta:

  1. ENDEREÇO COMPLETO   logradouro + numeral + bairro       -> porta
  2. RODOVIA POR KM      logradouro + km da referência       -> trecho
     ou PONTO NOTÁVEL    referência do despacho              -> entorno
  3. EIXO DA VIA         logradouro + bairro, sem numeral    -> via

Nenhuma delas dispensa as guardas que continuam valendo: o retorno tem de estar
no município certo e o nome da via tem de corresponder ao informado. Essas duas
não dependem da coordenada lançada, então seguem em pé.

Uso:
    python resgatar_sem_correcao.py
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
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _env import exigir, opcional

ENTRADA = r"C:\dados\053-26 - enderecos x coordenadas - CRUZADO.xlsx"
# Acima: chamava-se "- COMPLETO.xlsx". O Windows ignora maiúsculas no nome de
# arquivo, então ele era o MESMO arquivo que a planilha de origem de 21/08,
# "- completo.xlsx", e a gravação sobrescreveu o original. Renomeado para
# APURADO para que a colisão não possa se repetir.
SAIDA = r"C:\dados\053-26 - enderecos x coordenadas - APURADO.xlsx"

URL = "https://maps.googleapis.com/maps/api/geocode/json"
PAUSA = 0.06
RE_KM = re.compile(r'\bKM\s*\.?\s*(\d{1,3})', re.I)
RE_RODOVIA = re.compile(r'\b(RODOVIA|ROD|ACESSO|SP[\s-]?\d|DUTRA|TAMOIOS|BR[\s-]?\d)\b', re.I)
RE_RUIDO = re.compile(r'\b(PROX(IMO)?|PRÓX(IMO)?|AO|AA|EM|FRENTE|SENT(IDO)?|N[ºO°]?)\b\.?', re.I)


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
               r'ALAMEDA|AL|VIADUTO|ACESSO|DE|DA|DO|DOS|DAS|E)\b', ' ', s)
    return {t for t in re.sub(r'[^A-Z0-9 ]', ' ', s).split() if len(t) > 2}


def nome_confere(pedido, devolvido):
    a, b = _tok(pedido), _tok(str(devolvido).split(' - ')[0].split(',')[0])
    return True if not a else len(a & b) / len(a) >= 0.5


def geo(chave, endereco, tentativas=4):
    for n in range(tentativas):
        try:
            d = requests.get(URL, params={'address': endereco, 'key': chave,
                                          'region': 'br', 'language': 'pt-BR'}, timeout=25).json()
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if n == tentativas - 1:
                return None
            time.sleep(2 ** n)
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


def ponto_notavel(ref):
    s = unicodedata.normalize('NFKD', str(ref)).encode('ascii', 'ignore').decode()
    melhor = max((p.strip() for p in re.split(r'[/,;]', s)), key=len, default='')
    return ' '.join(RE_RUIDO.sub(' ', melhor).split())


def contexto(df):
    conn = psycopg2.connect(host=opcional('PG_HOST', 'localhost'), port=int(opcional('PG_PORT', '5432')),
                            dbname=opcional('PG_DB', '11gb'), user=opcional('PG_USER', 'admin'),
                            password=exigir('PG_PASS'))
    cur = conn.cursor()
    dt = pd.to_datetime(df['Data'], errors='coerce', dayfirst=True)
    pares = [(int(n), d.date()) for n, d in zip(df['Ocr Num'], dt) if pd.notna(n) and pd.notna(d)]
    cur.execute("""
        SELECT o.ocrnum, o.ocrdat, o.bairro_inicial, o.referencia_inicial, t.municipio
          FROM b3.ocorrencias o
          LEFT JOIN b3.tempo_resposta t ON t.id_sdov = o.id
         WHERE (o.ocrnum, o.ocrdat) = ANY(%s)
    """, (pares,))
    m = {(r[0], r[1]): (r[2], r[3], r[4]) for r in cur.fetchall()}
    conn.close()
    return m, dt


def main():
    chave = exigir('GOOGLE_MAPS_API_KEY')
    df = pd.read_excel(ENTRADA)
    banco, dt = contexto(df)

    alvo = df.index[(df['BATE?'].isin(['NÃO BATE', 'SEM RESPOSTA'])) & df['LATITUDE CORRETA'].isna()]
    print(f"linhas sem coordenada corrigida: {len(alvo)}")

    conf = [None] * len(df)
    resolvidas = {}

    for c, i in enumerate(alvo, 1):
        r = df.loc[i]
        logr = str(r['Logradouro informado (col. H)']).strip()
        num = r['Nº / km (col. I)']
        num = '' if pd.isna(num) else str(num).split('.')[0]
        k = (int(r['Ocr Num']), dt.iloc[i].date()) if pd.notna(r['Ocr Num']) and pd.notna(dt.iloc[i]) else None
        bairro, ref, mun_bd = banco.get(k, (None, None, None))
        mun = mun_bd or 'São José dos Campos'

        planos = []
        if num and bairro:
            planos.append(('porta', f"{logr}, {num}, {bairro}, {mun}, SP, Brasil", True))
        if num:
            planos.append(('porta', f"{logr}, {num}, {mun}, SP, Brasil", True))
        if RE_RODOVIA.search(logr) and ref and RE_KM.search(str(ref)):
            planos.append(('trecho de rodovia',
                           f"{logr}, km {RE_KM.search(str(ref)).group(1)}, {mun}, SP, Brasil", True))
        if ref and len(ponto_notavel(ref)) > 6:
            planos.append(('entorno (ponto de referência do despacho)',
                           f"{ponto_notavel(ref)}, {mun}, SP, Brasil", False))
        if bairro:
            planos.append(('eixo da via', f"{logr}, {bairro}, {mun}, SP, Brasil", True))
        planos.append(('eixo da via', f"{logr}, {mun}, SP, Brasil", True))

        for rotulo, consulta, exige_nome in planos:
            g = geo(chave, consulta)
            if not g:
                continue
            # Acima: estas duas guardas NÃO dependem da coordenada lançada, então
            # continuam valendo mesmo quando ela é o dado sob suspeita.
            if g['municipio'] and mun.lower() not in g['municipio'].lower():
                continue
            if exige_nome and not nome_confere(logr, g['endereco']):
                continue

            d = round(hav((g['lat'], g['lon']),
                          (float(r['Latitude informada (col. J)']), float(r['Longitude informada (col. K)']))))
            df.at[i, 'LATITUDE CORRETA'] = round(g['lat'], 6)
            df.at[i, 'LONGITUDE CORRETA'] = round(g['lon'], 6)
            df.at[i, 'ERRO (m)'] = d
            df.at[i, 'Endereço localizado'] = g['endereco']
            df.at[i, 'Precisão da localização'] = g['precisao']
            conf[i] = rotulo
            df.at[i, 'MOTIVO'] = (
                f"{r['MOTIVO']} | Coordenada corrigida obtida por {rotulo}: "
                f"{g['endereco']} — a {d} m da lançada.")
            resolvidas[rotulo] = resolvidas.get(rotulo, 0) + 1
            break
        else:
            resolvidas['não resolvida'] = resolvidas.get('não resolvida', 0) + 1

        if c % 20 == 0:
            print(f"  {c} de {len(alvo)}...", flush=True)

    df['Confiança da coordenada corrigida'] = conf

    print("\n--- o que foi possível resgatar ---")
    for k, v in sorted(resolvidas.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    nb = df[df['BATE?'].isin(['NÃO BATE', 'SEM RESPOSTA'])]
    print(f"\nnão batem: {len(nb)}  |  com coordenada: {nb['LATITUDE CORRETA'].notna().sum()}  "
          f"|  sem: {nb['LATITUDE CORRETA'].isna().sum()}")

    df.to_excel(SAIDA, index=False, sheet_name='Endereços x coordenadas')

    wb = load_workbook(SAIDA); ws = wb.active
    cab = Font(bold=True, color='FFFFFF', size=10); fundo = PatternFill('solid', fgColor='9E1B1B')
    larg = [10, 18, 12, 11, 26, 32, 9, 14, 14, 22, 15, 15, 10, 78, 34, 15, 26, 20, 30, 26]
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
