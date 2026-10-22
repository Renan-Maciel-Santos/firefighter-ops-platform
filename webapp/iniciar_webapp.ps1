# ============================================================
# Sobe o webapp (FastAPI) do 11º GB na porta 8000.
# É este processo que serve as 20 tools da B.I.A. — se ele não
# estiver no ar, a B.I.A. conecta no WhatsApp mas erra toda consulta.
#
# Chamado pela tarefa agendada "11GB_Webapp" no boot.
# Para rodar na mão:  powershell -File <raiz>\webapp\iniciar_webapp.ps1
# ============================================================

$ErrorActionPreference = "Stop"
# Acima: Caminhos relativos a este script (webapp\), para o projeto rodar de qualquer pasta
$raiz = $PSScriptRoot
$logs = Join-Path (Split-Path $PSScriptRoot -Parent) "logs"
New-Item -ItemType Directory -Force $logs | Out-Null
$log  = Join-Path $logs "webapp.log"

# ============================================================
# QUAL PYTHON
# ============================================================
# Chamar so "python" funcionava enquanto a tarefa rodava na sessao do usuario.
# Rodando como SYSTEM nao funciona mais: o Python esta instalado por usuario,
# em AppData\Local, e so entra no PATH do proprio usuario -- o PATH da maquina
# nao tem nenhuma entrada de Python. Start-Process falharia com "arquivo nao
# encontrado", a tarefa terminaria em segundos e ninguem serviria a :8000.
# Caminho absoluto resolve; o Get-Command fica de rede de seguranca caso o
# Python seja movido ou reinstalado em outro lugar.
# ============================================================
$python = "python"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
}

Set-Location $raiz

function Registrar($msg) {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg" | Add-Content $log
}

if (-not $python) {
    # Falhar aqui e barulhento de proposito. Se seguisse adiante, o Start-Process
    # erraria calado e a tarefa terminaria com "sucesso" -- exatamente o tipo de
    # falha sem sintoma que este arquivo inteiro existe pra evitar.
    Registrar "FALHA: python.exe nao encontrado (nem no caminho fixo nem no PATH)"
    exit 1
}

# ============================================================
# GUARDA DE INSTÂNCIA ÚNICA
# ============================================================
# O critério aqui é ATENDER, não escutar. A versão anterior olhava só se a porta
# 8000 estava em escuta e, se estivesse, saía com "nada a fazer" e código 0.
#
# Em 18/08/2026 isso criou um estado do qual o sistema não saía sozinho: um uvicorn
# iniciado na mão com --reload teve o processo pai encerrado, e o processo filho
# herdou o socket. A porta seguia em escuta, então TODA execução desta tarefa
# desistia — e o BIA_Watchdog, que dispara justamente esta tarefa quando vê o
# webapp fora, ficava em laço a cada 5 minutos sem consertar nada. Naquele caso o
# filho ainda respondia; se não respondesse, o webapp ficaria fora indefinidamente
# com o watchdog "trabalhando".
#
# Agora: responde HTTP -> saudável, não faz nada. Escuta mas não responde -> o
# socket é lixo, limpa e sobe. Não conseguiu limpar -> sai com código != 0, para o
# "Last Result" da tarefa acusar problema em vez de sucesso silencioso.
# ============================================================

function Test-WebappSaudavel {
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:8000/" -TimeoutSec 5 -UseBasicParsing
        return ($r.StatusCode -lt 500)
    } catch {
        # Acima: 4xx também é sinal de vida — a aplicação está de pé e roteando.
        # Só timeout, conexão recusada ou 5xx contam como doente.
        $codigo = $_.Exception.Response.StatusCode.value__
        return ($null -ne $codigo -and $codigo -lt 500)
    }
}

function Get-ProcessosDaPorta8000 {
    # Acima: Junta o dono declarado do socket com os python.exe relacionados.
    # O filho do --reload NÃO tem "uvicorn" na linha de comando (é a string do
    # multiprocessing, com parent_pid=<pai>), então filtrar por texto o deixaria
    # vivo segurando a porta — foi exatamente o que aconteceu em 18/08.
    $donosSocket = @(
        Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object { [int]$_.OwningProcess }
    )

    $relacionados = @()
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        ForEach-Object {
            $cmd = $_.CommandLine
            if (-not $cmd) { return }
            $ehWebapp = ($cmd -match 'uvicorn')
            foreach ($d in $donosSocket) {
                if ($cmd -match "parent_pid=$d(\D|$)") { $ehWebapp = $true }
            }
            if ($ehWebapp) { $relacionados += [int]$_.ProcessId }
        }

    return @($donosSocket + $relacionados | Sort-Object -Unique)
}

if (Test-WebappSaudavel) {
    Registrar "porta 8000 respondendo HTTP - webapp saudavel, nada a fazer"
    exit 0
}

if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    Registrar "porta 8000 em escuta mas NAO responde - socket morto, limpando"

    foreach ($processo in (Get-ProcessosDaPorta8000)) {
        try {
            Stop-Process -Id $processo -Force -ErrorAction Stop
            Registrar "  encerrado pid $processo"
        } catch {
            # Acima: PID de socket órfão costuma não existir mais como processo.
            # Não é erro fatal: o que importa é a porta liberar.
            Registrar "  pid $processo nao encerrado: $($_.Exception.Message)"
        }
    }

    $limite = (Get-Date).AddSeconds(20)
    while ((Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) -and
           (Get-Date) -lt $limite) {
        Start-Sleep -Milliseconds 500
    }

    if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
        Registrar "FALHA: porta 8000 continua ocupada e sem responder - precisa de intervencao manual"
        exit 1
    }

    Registrar "porta 8000 liberada"
}

Registrar "iniciando uvicorn na porta 8000"

# O uvicorn escreve o log normal no stderr. Com ErrorActionPreference="Stop"
# o PowerShell interpreta isso como erro fatal e derruba o processo — por isso
# volta pra "Continue" antes de chamar.
$ErrorActionPreference = "Continue"

# Log com carimbo por execução. Motivo: com nome fixo, um handle preso de
# um uvicorn morto (ex: depois de Stop-Process) faz o Start-Process falhar ao
# abrir o arquivo, e a tarefa morre sem subir nada — falha silenciosa.
$carimbo = Get-Date -Format "yyyyMMdd_HHmmss"
$out = Join-Path $logs "webapp_${carimbo}_out.log"
$err = Join-Path $logs "webapp_${carimbo}_err.log"

# Mantém só os 20 logs mais recentes (o -Skip abaixo define quantos ficam).
Get-ChildItem (Join-Path $logs "webapp_2*_*.log") -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip 20 |
    Remove-Item -Force -ErrorAction SilentlyContinue

# --host 0.0.0.0 é necessário: o n8n chama de dentro do container,
# via host.docker.internal:8000. Só 127.0.0.1 não seria alcançável.
# --log-config carimba hora em cada linha. O padrão do uvicorn não tem hora, e sem ela
# meia hora de requisições espaçadas (watchdog de 5 em 5 min, dashboard de 1 em 1 min)
# parece uma rajada de um segundo — o que faz o log normal soar como problema.
# -Wait mantém a tarefa viva supervisionando: se o uvicorn morrer, a tarefa
# falha e o RestartCount do Agendador sobe de novo.
Start-Process -FilePath $python `
    -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8000",
                  "--log-config","log_config.json" `
    -WorkingDirectory $raiz `
    -RedirectStandardOutput $out `
    -RedirectStandardError  $err `
    -NoNewWindow -Wait
