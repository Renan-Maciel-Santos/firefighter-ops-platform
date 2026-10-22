"""
Gera as capturas do painel usadas no README (docs/images/*.png).

Pré-requisito: a demonstração no ar (docker compose up + seed) e o Playwright
com Chromium (`pip install playwright && playwright install chromium`).

    python scripts/capturar_telas.py [--url http://127.0.0.1:8800] [--senha demo1234]

Entra como oficial (900004, sem pendências da UGE abertas, para o aviso de
pendências não cobrir a tela) e fotografa cada aba depois que os dados chegam.
"""

import argparse
import os

from playwright.sync_api import sync_playwright

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(RAIZ, "docs", "images")

# (aba do painel, arquivo, espera extra em ms para os gráficos animarem)
ABAS = [
    ("pessoal", "pessoal.png", 1500),
    ("mapa", "mapa_de_forca.png", 1500),
    ("ocorrencias", "ocorrencias.png", 2500),
    ("saude", "saude.png", 1500),
    ("viaturas", "viaturas.png", 1500),
    ("elogios", "elogios.png", 1500),
    ("auditoria_cobom", "auditoria_cobom.png", 1500),
    ("realocacao", "realocacao.png", 1500),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8800")
    ap.add_argument("--matricula", default="900004")
    ap.add_argument("--senha", default=os.environ.get("DEMO_SENHA", "demo1234"))
    a = ap.parse_args()
    os.makedirs(SAIDA, exist_ok=True)

    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        pag.goto(a.url)
        pag.fill("input[type=text]", a.matricula)
        pag.fill("input[type=password]", a.senha)
        pag.click("button[type=submit]")
        pag.wait_for_url("**/dashboard")
        pag.wait_for_load_state("networkidle")

        pag.goto(a.url + "/")  # login page redireciona; volta ao painel limpo
        pag.wait_for_url("**/dashboard")
        for aba, arquivo, espera in ABAS:
            pag.evaluate(f"showTab('{aba}')")
            pag.wait_for_load_state("networkidle")
            pag.wait_for_timeout(espera)
            destino = os.path.join(SAIDA, arquivo)
            pag.screenshot(path=destino)
            print("ok", os.path.relpath(destino, RAIZ))
        nav.close()


if __name__ == "__main__":
    main()
