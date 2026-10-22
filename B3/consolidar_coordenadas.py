# -*- coding: utf-8 -*-
"""Consolida as duas apurações das pendentes num veredito por linha.

Entram duas fontes que discordam com frequência, e o ponto deste script é
arbitrar entre elas com regra escrita, em vez de escolher a que agrada:

  histórico interno (b3.ocorrencias)  — onde o 11º GB sempre atendeu a via
  Google Geocoding                    — onde a via está na base cartográfica

Medido nas 57 pendentes, a mediana da distância entre a coordenada lançada e o
Google é de 2,9 km. Isso derruba a leitura ingênua de que "o histórico
confirma": ele confirma que o lançamento é REPETIDO, não que é correto. Onde a
corporação sempre lançou no mesmo lugar errado, o histórico ratifica o erro.

REGRA DE ARBITRAGEM — a precisão do Google decide o peso:

  ROOFTOP              número na porta. É a única evidência forte o bastante
                       para contrariar o histórico e propor troca.
  RANGE_INTERPOLATED   número estimado dentro da quadra. Serve em via urbana;
                       em RODOVIA é lixo — o Google trata o "nº 7" de uma
                       rodovia como posição interpolada ao longo de dezenas de
                       quilômetros e devolve pontos a 6 km do certo. Por isso
                       rodovia e acesso são excluídos da arbitragem automática.
  GEOMETRIC_CENTER     meio da via. Localiza a rua, não o número — vale para
                       dizer "a via é esta", não para adotar coordenada.

Nada é sobrescrito: o veredito e a coordenada sugerida entram em colunas novas,
e a decisão de adotar continua sendo de quem assina.
"""

import math
import os
import re
import sys

import unicodedata

import pandas as pd

import sys as _sys
ENTRADA = _sys.argv[1] if len(_sys.argv) > 1 else r"C:\dados\053-26 - enderecos x coordenadas - apurado final.xlsx"
SAIDA = _sys.argv[2] if len(_sys.argv) > 2 else r"C:\dados\053-26 - enderecos x coordenadas - VEREDITO.xlsx"
# Acima: o lote das 543 CERTA entra pelo mesmo arbitro. A unica diferenca e que
# ali o ponto de partida nao e "nao sabemos", e sim "alguem ja disse que esta
# certo" — por isso a divergencia pesa mais, nao menos.
SITUACOES = _sys.argv[3].split("|") if len(_sys.argv) > 3 else ['NÃO CONFIRMADA', 'CERTA (NUMERAL A CONFERIR)']

RAIO_ACORDO_M = 300

# Acima: Em rodovia o numeral não é endereço, é referência de quilômetro. O
# geocodificador não sabe disso e interpola ao longo de toda a via.
RE_RODOVIA = re.compile(r'\b(RODOVIA|ROD|ACESSO|SP[\s-]?\d|DUTRA|TAMOIOS|ANCHIETA|MONTEIRO LOBATO)\b', re.I)


def eh_rodovia(logradouro):
    return bool(RE_RODOVIA.search(str(logradouro)))


# Acima: Nome genérico ("Rua Sete", "Rua Um") existe em vários bairros. O
# geocodificador escolhe um deles sem avisar, e a precisão volta ROOFTOP do
# mesmo jeito — foi assim que "RUA SETE, 61" devolveu um ponto a 19,8 km, numa
# via com OUTRO nome. Sem esta checagem eu entregaria essas trocas como correção.
RE_GENERICO = re.compile(r'^\s*(RUA|R|AVENIDA|AV|TRAVESSA|VIA)?\s*'
                         r'(UM|DOIS|TRES|TRÊS|QUATRO|CINCO|SEIS|SETE|OITO|NOVE|DEZ|'
                         r'ONZE|DOZE|[0-9]{1,2})\s*$', re.I)


def _tokens(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'(RUA|R|AVENIDA|AV|ESTRADA|ESTR|EST|RODOVIA|ROD|TRAVESSA|TV|PRACA|'
               r'PCA|ALAMEDA|AL|VIADUTO|DE|DA|DO|DOS|DAS|E)', ' ', s)
    return {t for t in re.sub(r'[^A-Z0-9 ]', ' ', s).split() if len(t) > 2}


def nome_confere(pedido, devolvido):
    """O Google devolveu a MESMA via que foi pedida?

    Compara só o miolo do nome, ignorando tipo de via e conectivos. Sem isto,
    um retorno de via completamente diferente passa como se fosse correção.
    """
    a, b = _tokens(pedido), _tokens(str(devolvido).split(' - ')[0].split(',')[0])
    if not a:
        return True
    return len(a & b) / len(a) >= 0.5


def veredito(r):
    """Devolve (veredito, lat_sugerida, lon_sugerida, justificativa)."""
    aprov = r.get('Google — aproveitamento')
    prec = r.get('Google — precisão')
    dist = r.get('Google — distância até a lançada (m)')
    hist = r.get('SITUAÇÃO APURADA (28/08)')
    logr = r.get('Logradouro informado (col. H)')
    glat, glon = r.get('Google — latitude'), r.get('Google — longitude')
    mun_ret = r.get('Google — município do retorno')

    # Acima: o histórico interno só foi apurado para as 57 pendentes. No lote
    # das CERTA ele não existe, e a justificativa não pode sair dizendo 'nan'.
    tem_hist = isinstance(hist, str) and hist.strip()
    nota_hist = (f" Histórico interno da via: '{hist}'." if tem_hist else
                 " Esta linha estava marcada CERTA na apuração original, sem conferência externa.")

    if isinstance(aprov, str) and aprov.startswith('FORA'):
        return ('CONFERIR MANUALMENTE — via homônima em outro município', None, None,
                f"O Google localizou esta via em {mun_ret}, não em São José dos Campos. "
                f"Existe homônima na região; nenhuma coordenada externa pode ser adotada sem "
                f"confirmar de qual município é a ocorrência.")

    if aprov != 'OK' or pd.isna(dist):
        return ('CONFERIR MANUALMENTE — sem retorno utilizável', None, None,
                "O geocodificador não devolveu resultado aproveitável e o histórico interno "
                "não tem pontos suficientes. Depende de consulta à guarnição ou ao despacho.")

    if dist <= RAIO_ACORDO_M:
        return ('CERTA — confirmada por duas fontes', None, None,
                f"Google e coordenada lançada convergem ({int(dist)} m de diferença), e o "
                f"as duas fontes apontam o mesmo ponto — é a evidência mais forte possível "
                f"neste conjunto." + nota_hist)

    if eh_rodovia(logr):
        return ('VIA EXTENSA — conferir pelo km', None, None,
                f"Divergência de {int(dist)} m, mas o logradouro é rodovia ou acesso: o "
                f"geocodificador interpreta o numeral como posição interpolada ao longo de toda "
                f"a via e erra por quilômetros. O retorno do Google NÃO serve aqui. "
                f"Conferir pelo marco quilométrico ou pela referência do despacho.")

    if RE_GENERICO.match(str(logr)):
        return ('CONFERIR MANUALMENTE — nome genérico de via', None, None,
                f"O logradouro tem nome genérico, que se repete em vários bairros do município. "
                f"O geocodificador escolhe uma das homônimas sem sinalizar ambiguidade — aqui "
                f"devolveu um ponto a {int(dist)} m. Não é evidência de erro no lançamento; "
                f"precisa do bairro para desambiguar.")

    if not nome_confere(logr, r.get('Google — endereço (28/08)')):
        return ('CONFERIR MANUALMENTE — retorno não corresponde à via', None, None,
                f"Foi pedido '{logr}' e o Google devolveu '{r.get('Google — endereço (28/08)')}', "
                f"a {int(dist)} m. O nome não corresponde: pode ser via renomeada, homônima ou "
                f"erro do geocodificador. A coordenada dele NÃO pode ser adotada.")

    if prec == 'ROOFTOP':
        return ('ERRADA — adotar a coordenada do Google', round(glat, 6), round(glon, 6),
                f"O Google localizou o número exato na porta (ROOFTOP) a {int(dist)} m da "
                f"coordenada lançada. Evidência forte de que o lançamento está no trecho errado "
                f"da via." + nota_hist)

    if prec == 'RANGE_INTERPOLATED':
        return ('PROVÁVEL ERRO — confirmar antes de adotar', round(glat, 6), round(glon, 6),
                f"O Google estimou o número dentro da quadra (interpolado) a {int(dist)} m da "
                f"coordenada lançada. Indica trecho errado, mas a precisão não é de porta: "
                f"confirmar o numeral antes de trocar.")

    return ('VIA CONFERE, NUMERAL NÃO — conferir', None, None,
            f"O Google só localizou o meio da via (não o número), a {int(dist)} m do lançado. "
            f"Confirma que a via existe e é esta; não resolve em que trecho a ocorrência foi."
            + nota_hist)


def main():
    df = pd.read_excel(ENTRADA, sheet_name='Análise completa')
    alvo = df['SITUAÇÃO'].isin(SITUACOES)

    ver, la, lo, jus = [], [], [], []
    for _, r in df.iterrows():
        if r['SITUAÇÃO'] not in SITUACOES:
            ver.append(None); la.append(None); lo.append(None); jus.append(None)
            continue
        v, a, b, j = veredito(r)
        ver.append(v); la.append(a); lo.append(b); jus.append(j)

    df['VEREDITO FINAL'] = ver
    df['COORDENADA SUGERIDA — LAT'] = la
    df['COORDENADA SUGERIDA — LON'] = lo
    df['Justificativa do veredito'] = jus

    res = df.loc[alvo]
    print(f"pendentes arbitradas: {len(res)}\n")
    print(res['VEREDITO FINAL'].value_counts().to_string())
    print(f"\ncom coordenada sugerida: {res['COORDENADA SUGERIDA — LAT'].notna().sum()}")

    with pd.ExcelWriter(SAIDA, engine='openpyxl') as w:
        res.to_excel(w, sheet_name='VEREDITO', index=False)
        df.to_excel(w, sheet_name='Análise completa', index=False)
        for aba in ('Resumo', 'Coordenadas repetidas', 'Focos INPE x SIOPM'):
            pd.read_excel(ENTRADA, sheet_name=aba).to_excel(w, sheet_name=aba, index=False)
    print(f"\n>> gravado: {SAIDA}")


if __name__ == "__main__":
    main()
