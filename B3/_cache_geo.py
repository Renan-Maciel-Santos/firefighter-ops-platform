# -*- coding: utf-8 -*-
"""Cache em disco das respostas do geocodificador.

Existe por causa de um prejuízo concreto: em 28/08 as planilhas geradas foram
apagadas da pasta Downloads e, para reconstruí-las, seria preciso repetir cerca
de 1.350 consultas ao Google — todas já pagas uma vez. Nenhum dos scripts
guardava a resposta, então o custo era integralmente refeito a cada rodada.

A consulta é determinística: mesmo endereço, mesma chave, mesma resposta. Não há
razão para pagar duas vezes pela mesma pergunta. O cache é um JSON por consulta,
nomeado pelo hash do texto, e sobrevive a qualquer rerun ou arquivo perdido.

Uso:
    from _cache_geo import consultar_com_cache
    g = consultar_com_cache(chave, "Rua X, 10, São José dos Campos, SP, Brasil")

Para forçar consulta nova (endereço que mudou na base do Google), apague o
arquivo correspondente ou a pasta inteira.
"""

import hashlib
import json
import os
import time

import requests

URL = "https://maps.googleapis.com/maps/api/geocode/json"
PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache_geo")
PAUSA = 0.06


def _caminho(consulta):
    h = hashlib.sha256(consulta.encode("utf-8")).hexdigest()[:32]
    return os.path.join(PASTA, f"{h}.json")


def consultar_com_cache(chave, consulta, reverso=False, tentativas=4):
    """Devolve o JSON bruto do Google, do disco quando já perguntado antes."""
    os.makedirs(PASTA, exist_ok=True)
    arq = _caminho(("REV:" if reverso else "DIR:") + consulta)

    if os.path.exists(arq):
        try:
            with open(arq, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # Acima: cache corrompido é ruído, não erro fatal — refaz a consulta
            pass

    params = {"key": chave, "language": "pt-BR"}
    params["latlng" if reverso else "address"] = consulta
    if not reverso:
        params["region"] = "br"

    for n in range(tentativas):
        try:
            d = requests.get(URL, params=params, timeout=25).json()
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if n == tentativas - 1:
                return None
            time.sleep(2 ** n)
    time.sleep(PAUSA)

    # Acima: só grava resposta conclusiva. Erro de cota ou de rede não pode
    # virar cache, senão o próximo run herda a falha sem poder tentar de novo.
    if d.get("status") in ("OK", "ZERO_RESULTS"):
        try:
            with open(arq, "w", encoding="utf-8") as f:
                json.dump(d, f)
        except OSError:
            pass
    return d


def estatisticas():
    if not os.path.isdir(PASTA):
        return 0, 0
    arquivos = [f for f in os.listdir(PASTA) if f.endswith(".json")]
    tamanho = sum(os.path.getsize(os.path.join(PASTA, f)) for f in arquivos)
    return len(arquivos), tamanho
