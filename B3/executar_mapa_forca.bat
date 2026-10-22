@echo off
REM ============================================================
REM Executa a captura do mapa de força e grava log com data/hora.
REM Usado pelo Task Scheduler do Windows para rodar em intervalos.
REM ============================================================

REM Vai para a pasta do script
cd /d "%~dp0"

REM Cria pasta de log se ainda não existe
if not exist "logs" mkdir "logs"

REM Nome do log: mapa_forca_YYYYMMDD.log (1 arquivo por dia, com todas as execuções)
set "LOGFILE=logs\mapa_forca_%date:~-4%%date:~3,2%%date:~0,2%.log"

REM Cabeçalho da execução com timestamp
echo. >> "%LOGFILE%"
echo ==================================================== >> "%LOGFILE%"
echo Execucao em %date% %time% >> "%LOGFILE%"
echo ==================================================== >> "%LOGFILE%"

REM Executa o script capturando stdout + stderr no log; UTF-8 para acentos
set PYTHONIOENCODING=utf-8
python mapa_operacional.py >> "%LOGFILE%" 2>&1

REM Registra código de saída
echo Exit code: %ERRORLEVEL% >> "%LOGFILE%"
exit /b %ERRORLEVEL%
