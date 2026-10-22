# ==========================================
# ORQUESTRADOR DOS ETLS QUE LEEM ARQUIVO
# ==========================================
# Diferente dos coletores do SGP e do SIOPM, nada aqui precisa de navegador: estes
# ETLs leem planilha de share de rede ou de pasta local. Sem um agendador, carga
# que depende de alguém lembrar de rodar envelhece em silêncio.
#
# Cada domínio roda isolado: um que falhe não impede os outros. O código de saída
# distingue falha parcial de falha total, pra "Last Result" do Task Scheduler dizer algo.
#
# Uso:
#     python rodar_etl_arquivos.py                  → todos os domínios
#     python rodar_etl_arquivos.py viaturas uge     → só os domínios citados
#     python rodar_etl_arquivos.py --listar         → mostra os domínios e sai
# ==========================================

# Acima: Execução dos ETLs como subprocesso isolado
import subprocess

# Acima: Paths dos scripts e da raiz do projeto
import os

# Acima: Argumentos de linha de comando e código de saída
import sys

# Acima: Duração de cada domínio
import time

# Acima: Espelha a saída em logs/<nome>.log (mesma mecânica da captura)
from _log import iniciar_log, registrar_fim


def _nome_do_log():
    # Acima: --log=<nome> separa execuções frequentes do lote diário. O mapa de força roda
    # de 30 em 30 min (48x/dia); sem log próprio ele afogaria o log do lote, onde uma falha
    # do SJD ou da UGE precisa continuar visível.
    for a in sys.argv[1:]:
        if a.startswith("--log="):
            return a.split("=", 1)[1]
    return "etl_arquivos"


_CAMINHO_LOG = iniciar_log(_nome_do_log())

# Acima: Raiz do projeto — todos os caminhos abaixo saem dela
RAIZ = os.path.dirname(os.path.abspath(__file__))


# ==========================================
# DOMÍNIOS
# ==========================================
# 'args' fica explícito mesmo quando o script tem default próprio: assim o que roda
# agendado está escrito aqui, e não escondido num sys.argv[1] com valor padrão.

DOMINIOS = [
    {
        # Acima: Lê \\servidor\compartilhado\11GB\...\Viaturas do 11GB.xlsx (UNC, não precisa de drive mapeado)
        # Acima: 'requer' é checado antes de rodar. Fora da intranet da PMESP esse share não
        # resolve, e sem a checagem o pandas despeja 20 linhas de traceback por Errno 22 todo
        # dia no log. Melhor uma linha dizendo que o share está inacessível.
        "nome": "viaturas",
        "script": os.path.join(RAIZ, "B4", "viaturas.py"),
        "args": [],
        "requer": r"\\servidor\compartilhado",
    },
    {
        # Acima: Lê a planilha viva da B5 no share. Até 06/10/2026 lia uma cópia em
        # B5\NBI2026.xlsx, atualizada à mão, que parou em 24/08 e foi removida.
        "nome": "nbi",
        "script": os.path.join(RAIZ, "B5", "importar_nbi.py"),
        "args": [r"\\servidor\compartilhado\11GB\11GB5\N\NBI2026\NBI2026.xlsx"],
        "requer": r"\\servidor\compartilhado\11GB\11GB5\N\NBI2026\NBI2026.xlsx",
    },
    {
        # Acima: Planilha de controle da UGE — o script aceita [caminho] [ano]
        "nome": "uge",
        "script": os.path.join(RAIZ, "UGE", "importar_uge.py"),
        "args": [],
    },
    {
        # Acima: Usa o default do próprio script (dados_externos/sjd_<ano>-S1.xlsx e S2)
        "nome": "sjd",
        "script": os.path.join(RAIZ, "SJD", "sjd_etl.py"),
        "args": [],
    },
    {
        # Acima: Único domínio aqui que não lê planilha local — puxa o mapa de força do
        # Google Sheets via service account. Fica neste orquestrador, e não com os
        # coletores, porque não passa pelo SGP nem precisa de navegador.
        # Acima: 'requer' aponta pro JSON da service account. Se ele sumir, a checagem
        # vira "sem_acesso" no log em vez de stacktrace do gspread.
        # Acima: 'fora_do_lote' o exclui da execução sem argumentos. Ele tem tarefa própria
        # (11GB_MapaForca, de 30 em 30 min) porque o mapa de força é o quadro de serviço do
        # dia e muda ao longo do expediente — puxá-lo uma vez às 06:00 daria um retrato
        # desatualizado o resto do dia. Continua chamável por nome para rodada manual.
        "nome": "mapa_forca",
        "script": os.path.join(RAIZ, "B3", "mapa_operacional.py"),
        "args": [],
        "requer": os.environ.get("GOOGLE_SA_JSON") or os.path.join(RAIZ, "credentials", "service-account.json"),
        "fora_do_lote": True,
    },
]


def rodar(dominio):
    """Roda um ETL e devolve (status, segundos). Nunca levanta exceção."""
    nome = dominio["nome"]
    script = dominio["script"]
    inicio = time.monotonic()

    # Acima: Script ausente é erro de configuração, não falha de dado — vale distinguir no log
    if not os.path.exists(script):
        print(f"❌ {nome}: script não encontrado em {script}")
        return "sem_script", time.monotonic() - inicio

    # Acima: Pré-requisito de acesso (share de rede). Distinguir "sem acesso" de "falhou"
    # importa: o primeiro é a máquina fora da rede, o segundo é problema no dado ou no script.
    requer = dominio.get("requer")
    if requer and not os.path.exists(requer):
        print(f"⚠️  {nome}: {requer} inacessível — máquina provavelmente fora da intranet. Pulado.")
        return "sem_acesso", time.monotonic() - inicio

    env = os.environ.copy()
    # Acima: SJD passa por _comum.confirmar_com_usuario(), que faz input() e travaria a
    # tarefa agendada pra sempre. PULAR_CONFIRMACAO=1 é o modo batch que o _comum já prevê.
    env["PULAR_CONFIRMACAO"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    print(f"\n{'─' * 58}")
    print(f"▶️  {nome} — {os.path.basename(script)}")

    try:
        # Acima: Saída por PIPE e reimpressa pra cair no log (sob o agendador não há console)
        processo = subprocess.Popen(
            [sys.executable, script, *dominio["args"]],
            env=env,
            cwd=os.path.dirname(script),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        for linha in processo.stdout:
            print(f"   │ {linha.rstrip()}")
        codigo = processo.wait(timeout=1800)

    except subprocess.TimeoutExpired:
        # Acima: Share de rede fora do ar costuma travar a leitura em vez de dar erro
        processo.kill()
        print(f"❌ {nome}: passou de 30min e foi encerrado")
        return "timeout", time.monotonic() - inicio

    except Exception as e:
        print(f"❌ {nome}: erro inesperado — {e}")
        return "erro", time.monotonic() - inicio

    segundos = time.monotonic() - inicio
    if codigo != 0:
        print(f"❌ {nome}: falhou com código {codigo} ({segundos:.0f}s)")
        return "falhou", segundos

    print(f"✅ {nome}: ok ({segundos:.0f}s)")
    return "ok", segundos


def main():
    nomes_validos = [d["nome"] for d in DOMINIOS]

    if "--listar" in sys.argv:
        print("Domínios disponíveis: " + ", ".join(nomes_validos))
        return 0

    # Acima: Sem argumentos roda tudo; com argumentos roda só o subconjunto pedido
    pedidos = [a for a in sys.argv[1:] if not a.startswith("--")]
    if pedidos:
        desconhecidos = [p for p in pedidos if p not in nomes_validos]
        if desconhecidos:
            print(f"❌ Domínio desconhecido: {', '.join(desconhecidos)}")
            print(f"   Disponíveis: {', '.join(nomes_validos)}")
            return 1
        fila = [d for d in DOMINIOS if d["nome"] in pedidos]
    else:
        # Acima: O lote diário roda só o que não tem agendamento próprio
        fila = [d for d in DOMINIOS if not d.get("fora_do_lote")]

    print(f"🗂️  Log desta execução: {_CAMINHO_LOG}")
    print(f"📋 Domínios na fila: {', '.join(d['nome'] for d in fila)}")

    inicio = time.monotonic()
    resultados = {}
    for dominio in fila:
        status, _ = rodar(dominio)
        resultados[dominio["nome"]] = status

    # Acima: Mesmo esquema de código de saída dos coletores, de propósito —
    # duas tarefas agendadas com semântica diferente de "Last Result" seria armadilha.
    #   0 = todos ok | 2 = parcial | 3 = todos falharam | 1 = erro de uso
    duracao = time.monotonic() - inicio
    print("\n" + "=" * 58)
    print(f"Resumo ({duracao:.0f}s):")
    for nome, status in resultados.items():
        print(f"  {nome}: {status}")

    ok = [n for n, s in resultados.items() if s == "ok"]
    falhas = [n for n, s in resultados.items() if s != "ok"]

    if not falhas:
        print(f"✅ {len(ok)}/{len(resultados)} domínios atualizados.")
        return 0
    if not ok:
        print(f"❌ Todos falharam: {', '.join(falhas)}")
        return 3
    print(f"⚠️  Parcial — ok: {', '.join(ok)} | falhou: {', '.join(falhas)}")
    return 2


if __name__ == "__main__":
    codigo = main()
    registrar_fim(codigo)
    sys.exit(codigo)
