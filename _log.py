# ==========================================
# LOG EM ARQUIVO PARA OS SCRIPTS AGENDADOS
# ==========================================
# Rodando na mão, print no console basta. Agendado no Task Scheduler NÃO EXISTE
# console: sem isto, uma falha às 5h da manhã fica invisível — que é exatamente
# o problema que a automação da captura poderia criar.
#
# Espelha stdout e stderr num arquivo (tee) e faz rotação por tamanho, pra não
# repetir o caso do bia_watchdog.log, que chegou a 964 KB sem nunca rotacionar.
#
# Uso:
#     from _log import iniciar_log
#     iniciar_log("captura_sgp")
# ==========================================

# Acima: Carimbo de data/hora nos cabeçalhos de execução
from datetime import datetime

# Acima: Paths e criação da pasta de logs
import os

# Acima: Substituição de sys.stdout/sys.stderr
import sys


# Acima: Pasta de logs do projeto (mesma usada pelo watchdog e pelo webapp)
PASTA_LOGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# Acima: Acima deste tamanho o log vira .1 e um novo começa
LOG_MAX_BYTES = 5 * 1024 * 1024


class _Tee:
    """Escreve no destino original (console) e no arquivo de log ao mesmo tempo."""

    def __init__(self, original, arquivo):
        self._original = original
        self._arquivo = arquivo

    def write(self, texto):
        # Acima: Sob o Task Scheduler o handle do console pode ser inválido.
        # O log NÃO pode morrer por causa disso — é justamente quando ele importa.
        try:
            if self._original is not None:
                self._original.write(texto)
        except Exception:
            pass
        # Acima: Idem na outra ponta — se o arquivo já foi fechado (finalização do
        # interpretador), engolir aqui evita o clássico "erro ao dar flush no stdout",
        # que faz o processo sair com código 120 e mascara o código de saída real.
        try:
            self._arquivo.write(texto)
        except Exception:
            pass
        return len(texto)

    def flush(self):
        try:
            if self._original is not None:
                self._original.flush()
        except Exception:
            pass
        try:
            self._arquivo.flush()
        except Exception:
            pass

    # Acima: Bibliotecas checam isatty() antes de colorir saída — sem console, nunca é tty
    def isatty(self):
        return False


def _rotacionar(caminho):
    # Acima: Mantém apenas a geração anterior (.1); histórico maior que isso não ajuda diagnóstico
    try:
        if os.path.getsize(caminho) > LOG_MAX_BYTES:
            anterior = caminho + ".1"
            if os.path.exists(anterior):
                os.remove(anterior)
            os.replace(caminho, anterior)
    except FileNotFoundError:
        pass


def iniciar_log(nome):
    """Liga o espelhamento de stdout/stderr para logs/<nome>.log e devolve o caminho."""
    os.makedirs(PASTA_LOGS, exist_ok=True)
    caminho = os.path.join(PASTA_LOGS, f"{nome}.log")
    _rotacionar(caminho)

    # Acima: buffering=1 (linha a linha) garante que o log fica íntegro mesmo se o processo morrer.
    # Acima: De propósito NÃO fechamos o arquivo via atexit: os handlers de atexit rodam ANTES
    # do flush final de sys.stdout, então fechar ali faz o tee escrever em arquivo fechado e o
    # processo sair com 120 em vez do código real. Quem fecha é o SO, no fim do processo.
    arquivo = open(caminho, "a", encoding="utf-8", buffering=1)
    arquivo.write(f"\n{'=' * 62}\n")
    arquivo.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] início — {' '.join(sys.argv)}\n")

    sys.stdout = _Tee(sys.stdout, arquivo)
    sys.stderr = _Tee(sys.stderr, arquivo)
    return caminho


def registrar_fim(codigo):
    # Acima: Fecha o bloco no log com o código de saída, pra casar com o "Last Result" do agendador
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] fim — código de saída {codigo}")
