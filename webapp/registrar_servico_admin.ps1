# ============================================================
# Registra o webapp da B.I.A. como tarefa de SISTEMA.
#
# PRECISA SER EXECUTADO COMO ADMINISTRADOR.
#
# Por quê: hoje a tarefa 11GB_Webapp roda com gatilho "ao fazer logon",
# DENTRO da sessão interativa do usuário. Qualquer evento de sessão
# (logoff, troca de usuário, retorno de suspensão) manda um evento de
# console e mata o uvicorn — o Agendador registra isso como
# LastTaskResult 3221225786 (0xC000013A, STATUS_CONTROL_C_EXIT).
#
# Aconteceu 3x em 10-11/08/2026. O sintoma é o pior possível: a B.I.A.
# continua respondendo no WhatsApp, mas com as 20 ferramentas mortas —
# ela erra toda consulta sem nenhum sinal visível.
#
# Rodando como SYSTEM com gatilho no boot, o webapp deixa de depender
# de haver alguém logado na máquina.
#
# Duas coisas mudam junto com o principal, porque sem elas a troca sai pior
# que o defeito:
#   - a ACL da tarefa, para o BIA_Watchdog (que roda como usuario comum)
#     continuar conseguindo religar o webapp;
#   - o caminho do python.exe em iniciar_webapp.ps1, porque o Python esta
#     instalado por usuario e o SYSTEM nao o enxerga pelo PATH.
#
# Como rodar:
#   1) Menu Iniciar -> digite "powershell"
#   2) Botão direito em "Windows PowerShell" -> "Executar como administrador"
#   3) Cole:  powershell -ExecutionPolicy Bypass -File <raiz>\webapp\registrar_servico_admin.ps1
# ============================================================

$ErrorActionPreference = "Stop"

$ehAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $ehAdmin) {
    Write-Host "ERRO: rode este script como ADMINISTRADOR." -ForegroundColor Red
    Write-Host "Menu Iniciar -> PowerShell -> botao direito -> Executar como administrador"
    exit 1
}

$acao = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSScriptRoot\iniciar_webapp.ps1`"" `
    -WorkingDirectory $PSScriptRoot

$gatilho = New-ScheduledTaskTrigger -AtStartup

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# ExecutionTimeLimit 0 = sem limite (o processo fica vivo servindo).
# RestartCount/Interval: se o uvicorn morrer, o Agendador tenta de novo.
$config = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "11GB_Webapp" `
    -Action $acao -Trigger $gatilho -Principal $principal -Settings $config `
    -Description "Sobe o webapp FastAPI (:8000) que serve as 20 tools da B.I.A. Roda como SYSTEM no boot, independente de sessao de usuario." `
    -Force | Out-Null

Write-Host "Tarefa 11GB_Webapp registrada como SYSTEM / no boot." -ForegroundColor Green

# ============================================================
# QUEM PODE DISPARAR A TAREFA
# ============================================================
# Rodando como SYSTEM, a tarefa nasce com uma ACL em que so administradores e
# o proprio SYSTEM podem executa-la. So que quem religa o webapp na pratica e
# o BIA_Watchdog, que roda como usuario comum e chama
# `schtasks /Run /TN 11GB_Webapp`. Sem permissao explicita isso volta "acesso
# negado" e a recuperacao automatica morre calada -- o saldo seria pior que o
# problema original: em vez de "cai e volta em 5min", viraria "cai e fica fora
# ate alguem reparar".
#
# Register-ScheduledTask nesta versao do Windows nao aceita -SecurityDescriptor,
# entao a ACL vai depois, pela API COM do Agendador. E tem de ser depois mesmo:
# o -Force acima apaga e recria a tarefa, zerando qualquer ACL anterior.
#
# FRFX = leitura + execucao. O watchdog passa a poder disparar a tarefa, mas
# nao alterar nem apagar.
# ============================================================

$sidWatchdog = $null
$xmlWatchdog = Export-ScheduledTask -TaskName "BIA_Watchdog" -ErrorAction SilentlyContinue
if ($xmlWatchdog -match '<UserId>(S-1-[\d\-]+)</UserId>') {
    $sidWatchdog = $matches[1]
} else {
    # Fallback: watchdog ainda nao registrado, ou gravado com nome de conta em
    # vez de SID. Usa quem esta rodando este script -- com aviso, porque se a
    # elevacao foi feita com OUTRA conta o SID sai errado e a ACL nao serve.
    $sidWatchdog = ([Security.Principal.WindowsIdentity]::GetCurrent()).User.Value
    Write-Host "AVISO: nao achei o SID no BIA_Watchdog; usando o do usuario atual ($sidWatchdog)." -ForegroundColor Yellow
    Write-Host "       Se voce elevou com outra conta, confira a ACL no fim deste script." -ForegroundColor Yellow
}

$sddl = "D:P(A;;FA;;;BA)(A;;FA;;;SY)(A;;FRFX;;;BU)(A;;FRFX;;;$sidWatchdog)"

try {
    $servicoAgendador = New-Object -ComObject "Schedule.Service"
    $servicoAgendador.Connect()
    $tarefaCom = $servicoAgendador.GetFolder("\").GetTask("11GB_Webapp")
    $tarefaCom.SetSecurityDescriptor($sddl, 0)

    # Rele do Agendador em vez de confiar na variavel: o que vale e o que ficou
    # gravado. O 4 e DACL_SECURITY_INFORMATION.
    $sddlGravada = $tarefaCom.GetSecurityDescriptor(4)
    Write-Host "ACL gravada: $sddlGravada"

    if ($sddlGravada -match [regex]::Escape($sidWatchdog)) {
        Write-Host "OK: o BIA_Watchdog pode disparar a tarefa." -ForegroundColor Green
    } else {
        Write-Host "ATENCAO: o SID do watchdog nao aparece na ACL gravada." -ForegroundColor Yellow
        Write-Host "         O webapp sobe no boot, mas o watchdog nao vai conseguir religa-lo." -ForegroundColor Yellow
    }
} catch {
    Write-Host "ATENCAO: falha ao gravar a ACL: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "         A tarefa esta registrada, mas o watchdog nao vai conseguir religar o webapp." -ForegroundColor Yellow
}

# Derruba o uvicorn atual (se houver) e sobe pela tarefa nova, pra validar
# que o caminho de SYSTEM funciona de verdade — tarefa nao testada nao vale.
$pid8000 = (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue).OwningProcess |
    Select-Object -First 1
if ($pid8000) {
    Write-Host "derrubando uvicorn atual (PID $pid8000) pra testar..."
    Stop-Process -Id $pid8000 -Force
    Start-Sleep -Seconds 4
}

Start-ScheduledTask -TaskName "11GB_Webapp"
Start-Sleep -Seconds 15

if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "OK: webapp no ar em :8000, rodando como SYSTEM." -ForegroundColor Green
} else {
    Write-Host "ATENCAO: o webapp nao subiu. Veja logs\webapp_*_err.log" -ForegroundColor Yellow
    Write-Host "Confira tambem logs\webapp.log: se aparecer 'python.exe nao"
    Write-Host "encontrado', ajuste a variavel `$python no topo de iniciar_webapp.ps1."
}
