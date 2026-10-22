# -*- coding: utf-8 -*-
"""Resolve as 57 linhas pendentes da validação de endereços x coordenadas.

Contexto: a chave do Google Maps está restrita por IP e esta máquina não é
autorizada, então a rota que a sessão de 21/08 usou para preencher as ERRADA
está fechada. Este script troca a fonte externa por uma interna.

Método — confirmação por histórico:
    Para cada logradouro pendente, procura em b3.ocorrencias todas as demais
    ocorrências lançadas no MESMO logradouro que têm coordenada. Se elas formam
    um aglomerado coerente, esse aglomerado é onde o próprio Corpo de Bombeiros
    historicamente localiza aquela via.

O que o método prova e o que NÃO prova:
    Prova CONSISTÊNCIA — que a coordenada lançada está onde a corporação sempre
    atendeu aquela via. NÃO prova correção geográfica: se a via inteira sempre
    foi lançada no lugar errado, o histórico repete o erro em vez de denunciá-lo.
    Por isso a coluna de situação criada aqui diz "CONFIRMADA POR HISTÓRICO", e
    não "CERTA" — a distinção precisa sobreviver a quem ler a planilha depois.

Vantagem sobre o geocodificador: funciona para via informal, estrada rural e
grafia local, que é justamente o caso das 32 NÃO CONFIRMADA — elas não estão no
Google porque não estão em base cartográfica nenhuma, mas estão no histórico.
"""

import math
import re
import os
import sys
import unicodedata
from collections import defaultdict

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _env import exigir, opcional
import psycopg2

ORIGEM = r"C:\dados\053-26 - enderecos x coordenadas - completo.xlsx"
SAIDA = r"C:\dados\053-26 - enderecos x coordenadas - pendentes resolvidas.xlsx"

# Acima: 300 m é o raio adotado para dizer que a coordenada lançada está no
# mesmo lugar do histórico. É a ordem de grandeza de uma quadra longa em SJC —
# maior que isso já muda a referência de quem vai atender.
RAIO_CONFIRMA_M = 300

# Acima: Abaixo de 3 pontos o "aglomerado" é anedota, não histórico.
MIN_PONTOS = 3

# Acima: Aglomerado muito espalhado descreve uma via extensa (rodovia, estrada
# rural), onde o centroide não representa ponto algum. Nesses casos o script
# informa, mas não propõe coordenada.
DISPERSAO_MAX_M = 2000

# Acima: 'VIA' saiu da lista. Removê-la transformava "Rua Via Oeste" em
# "OESTE", que casa com qualquer via de mesmo sufixo em outra cidade — foi
# assim que a linha 709 apontou um histórico a 7 km.
PREFIXOS = r'\b(RUA|R|AVENIDA|AV|ESTRADA|ESTADA|EST|RODOVIA|ROD|VIADUTO|TRAVESSA|TV|PRACA|ALAMEDA|AL)\b'


def normalizar(s):
    """Reduz o logradouro ao seu miolo, para casar grafias diferentes."""
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().upper()
    s = re.sub(PREFIXOS, ' ', s)
    s = re.sub(r'[^A-Z0-9 ]', ' ', s)
    return ' '.join(s.split())


def haversine_m(a, b):
    (la1, lo1), (la2, lo2) = a, b
    r = 6371000.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp = math.radians(la2 - la1)
    dl = math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def mediana(v):
    v = sorted(v)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def main():
    df = pd.read_excel(ORIGEM, sheet_name="Análise completa")
    pendentes = df['SITUAÇÃO'].isin(['NÃO CONFIRMADA', 'CERTA (NUMERAL A CONFERIR)'])
    print(f"linhas na planilha : {len(df)}")
    print(f"pendentes a resolver: {pendentes.sum()}")

    conn = psycopg2.connect(host=opcional('PG_HOST', 'localhost'), port=int(opcional('PG_PORT', '5432')),
                            dbname=opcional('PG_DB', '11gb'), user=opcional('PG_USER', 'admin'),
                            password=exigir('PG_PASS'))
    cur = conn.cursor()
    # Acima: recorte no Vale do Paraíba para descartar coordenada absurda da
    # própria base, que existe e contaminaria o centroide.
    # Acima: o histórico precisa ser DO MESMO MUNICÍPIO. b3.ocorrencias guarda o
    # município como código, não como nome, mas b3.tempo_resposta guarda o nome
    # e casa 1:1 pelo id do SDOV2 — é essa junção que dá o filtro. Sem ela,
    # "Avenida das Indústrias" casava com a homônima de outra cidade e o método
    # apontava divergência de 21 km que não existia.
    cur.execute("""
        SELECT DISTINCT o.id, o.logradouro_inicial, o.lat_inicial, o.lon_inicial
          FROM b3.ocorrencias o
          JOIN b3.tempo_resposta t ON t.id_sdov = o.id
         WHERE o.lat_inicial IS NOT NULL AND o.lon_inicial IS NOT NULL
           AND o.logradouro_inicial IS NOT NULL
           AND t.municipio = 'São José dos Campos'
           AND o.lat_inicial BETWEEN -24.5 AND -22.0
           AND o.lon_inicial BETWEEN -46.5 AND -44.0
    """)
    indice = defaultdict(list)
    for _oid, log, la, lo in cur.fetchall():
        indice[normalizar(log)].append((float(la), float(lo)))
    conn.close()
    print(f"logradouros distintos georreferenciados em SJC: {len(indice):,}".replace(",", "."))

    novas = {c: [] for c in ('sit', 'lat', 'lon', 'como', 'fonte', 'obs', 'n', 'disp', 'dist')}

    for _, r in df.iterrows():
        if not r['SITUAÇÃO'] in ('NÃO CONFIRMADA', 'CERTA (NUMERAL A CONFERIR)'):
            for k in novas:
                novas[k].append(None)
            continue

        chave = normalizar(r['Logradouro informado (col. H)'])
        pontos = indice.get(chave, [])
        lat_i, lon_i = r['Latitude informada (col. J)'], r['Longitude informada (col. K)']

        if len(pontos) < MIN_PONTOS:
            novas['sit'].append('SEM HISTÓRICO SUFICIENTE')
            novas['lat'].append(None); novas['lon'].append(None)
            novas['como'].append(None)
            novas['fonte'].append('b3.ocorrencias')
            novas['obs'].append(f"Apenas {len(pontos)} ocorrência(s) georreferenciada(s) neste "
                                f"logradouro — insuficiente para formar referência. "
                                f"Precisa de conferência externa ou consulta à guarnição.")
            novas['n'].append(len(pontos)); novas['disp'].append(None); novas['dist'].append(None)
            continue

        cen = (mediana([p[0] for p in pontos]), mediana([p[1] for p in pontos]))
        disp = round(mediana([haversine_m(cen, p) for p in pontos]))
        dist = round(haversine_m(cen, (float(lat_i), float(lon_i)))) if pd.notna(lat_i) else None

        extensa = disp > DISPERSAO_MAX_M
        if dist is not None and dist <= RAIO_CONFIRMA_M:
            novas['sit'].append('CONFIRMADA POR HISTÓRICO')
            novas['lat'].append(None); novas['lon'].append(None)
            novas['como'].append('Coordenada lançada coincide com o histórico da via')
            novas['obs'].append(
                f"{len(pontos)} ocorrências anteriores neste logradouro formam referência a "
                f"{dist} m da coordenada lançada (dispersão mediana {disp} m). A coordenada é "
                f"consistente com onde a corporação sempre atendeu esta via.")
        elif extensa:
            novas['sit'].append('VIA EXTENSA — TRECHO A CONFERIR')
            novas['lat'].append(None); novas['lon'].append(None)
            novas['como'].append(None)
            novas['obs'].append(
                f"{len(pontos)} ocorrências espalhadas por {disp} m — via extensa (rodovia ou "
                f"estrada rural). Não há ponto único que a represente; conferir o trecho pelo "
                f"km ou pela referência do despacho.")
        elif dist is not None and dist <= disp:
            # Acima: comparar a distância com um raio fixo é injusto em via
            # longa. Se a coordenada está mais perto do centro do que o próprio
            # espalhamento das ocorrências daquela via, ela cai dentro do
            # traçado — é outro trecho da mesma rua, não outro lugar.
            novas['sit'].append('CONSISTENTE — OUTRO TRECHO DA VIA')
            novas['lat'].append(None); novas['lon'].append(None)
            novas['como'].append('Dentro da dispersão histórica da própria via')
            novas['obs'].append(
                f"Coordenada a {dist} m do centro do histórico, com as {len(pontos)} ocorrências "
                f"da via espalhadas por {disp} m. Está dentro do traçado — indica outro trecho da "
                f"mesma via, não outro local. Só o numeral segue por conferir.")
        else:
            novas['sit'].append('DIVERGENTE DO HISTÓRICO')
            novas['lat'].append(round(cen[0], 6)); novas['lon'].append(round(cen[1], 6))
            novas['como'].append('Centro do aglomerado histórico da via (b3.ocorrencias)')
            novas['obs'].append(
                f"Coordenada lançada está a {dist} m do ponto onde {len(pontos)} ocorrências "
                f"anteriores desta via se concentram (dispersão mediana {disp} m). Sugerida a "
                f"coordenada do aglomerado; confirmar antes de adotar.")

        novas['fonte'].append('b3.ocorrencias — histórico do próprio 11º GB')
        novas['n'].append(len(pontos)); novas['disp'].append(disp); novas['dist'].append(dist)

    df['SITUAÇÃO APURADA (28/08)'] = novas['sit']
    df['LATITUDE SUGERIDA'] = novas['lat']
    df['LONGITUDE SUGERIDA'] = novas['lon']
    df['Como foi apurada'] = novas['como']
    df['Fonte da apuração'] = novas['fonte']
    df['Ocorrências históricas na via'] = novas['n']
    df['Dispersão do histórico (m)'] = novas['disp']
    df['Distância até o histórico (m)'] = novas['dist']
    df['Observação da apuração'] = novas['obs']

    res = df.loc[pendentes]
    print("\n--- resultado das 57 pendentes ---")
    print(res['SITUAÇÃO APURADA (28/08)'].value_counts().to_string())

    # Acima: a planilha de origem está aberta no Excel; grava em arquivo novo.
    with pd.ExcelWriter(SAIDA, engine='openpyxl') as w:
        df.to_excel(w, sheet_name='Análise completa', index=False)
        res.to_excel(w, sheet_name='Pendentes apuradas', index=False)
        for aba in ('Resumo', 'Coordenadas repetidas', 'Focos INPE x SIOPM'):
            pd.read_excel(ORIGEM, sheet_name=aba).to_excel(w, sheet_name=aba, index=False)
    print(f"\n>> gravado: {SAIDA}")


if __name__ == "__main__":
    main()
