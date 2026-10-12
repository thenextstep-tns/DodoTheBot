@echo off
REM ---------------------------------------------------------------------------
REM  DodoTheBot launcher
REM  Double-click this file (or run it from a terminal) to start the bot.
REM  Close the window or press Ctrl+C to stop it. Only run ONE at a time.
REM ---------------------------------------------------------------------------

cd /d "%~dp0"

REM Refuse to start if another bot.py instance is already running, so we never
REM end up with two bots logged in and double-responding to commands.
for /f %%P in ('powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='py.exe'\" | Where-Object { $_.CommandLine -like '*bot.py*' -and $_.ProcessId -ne $PID }).Count"') do set RUNNING=%%P
if not "%RUNNING%"=="0" (
    echo.
    echo  A Dodo bot instance is already running. Close it first to avoid
    echo  duplicate responses. Aborting.
    echo.
    pause
    exit /b 1
)

echo Starting DodoTheBot...  (press Ctrl+C to stop)
py -3.13 -u bot.py

echo.
echo Bot has stopped.
pause
