@echo off
rem ---------------------------------------------------------------
rem  Input Translation Bridge - local model launcher (ASCII ONLY)
rem
rem  Layout expected (all in this folder):
rem    llama-server.exe      (from llama.cpp win-cpu-x64 release)
rem    *.gguf                (translation model, e.g. Hy-MT2-1.8B-Q8_0.gguf)
rem    bridge.exe            (the translation bridge, any name)
rem
rem  Starts llama-server on 127.0.0.1:1236 (OpenAI-compatible API),
rem  waits until the port is LISTENING, then launches bridge.exe.
rem  To use a cloud API instead, skip this launcher entirely and set
rem  the endpoint in the bridge settings window.
rem ---------------------------------------------------------------
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Input Translation Bridge Launcher

set "DIR=%~dp0"
set "HOST=127.0.0.1"
set "PORT=1236"
set "CTX=2048"
set "WAIT_SEC=120"

rem ---- 1. pick model: first *.gguf alphabetically (edit to force one) ----
set "MODEL="
for %%F in ("%DIR%*.gguf") do if not defined MODEL set "MODEL=%%~fF"
if not defined MODEL (
  echo [ERROR] No .gguf model found in: %DIR%
  echo         Download one, e.g. Hy-MT2-1.8B-Q8_0.gguf, into this folder.
  pause
  exit /b 1
)

rem ---- 2. locate server binary ----
set "SERVER_EXE="
if exist "%DIR%llama-server.exe" set "SERVER_EXE=%DIR%llama-server.exe"
if not defined SERVER_EXE (
  echo [ERROR] llama-server.exe not found in: %DIR%
  echo         Download the llama.cpp win-cpu-x64 release and copy
  echo         llama-server.exe and its .dll files into this folder.
  pause
  exit /b 1
)

rem ---- 3. locate bridge exe ----
set "BRIDGE_EXE="
for %%F in ("%DIR%*.exe") do (
  echo %%~nxF | findstr /i /b "llama server ggml" >nul || (
    if not defined BRIDGE_EXE set "BRIDGE_EXE=%%~fF"
  )
)
if not defined BRIDGE_EXE (
  echo [ERROR] Bridge exe not found in: %DIR%
  pause
  exit /b 1
)

echo ------------------------------------------------
echo Model  : %MODEL%
echo Server : %SERVER_EXE%
echo Bridge : %BRIDGE_EXE%
echo Listen : %HOST%:%PORT%
echo ------------------------------------------------

rem ---- port already up? keep or restart ----
netstat -ano | findstr ":%PORT%" | findstr /i "LISTENING" >nul
if not errorlevel 1 (
  echo [WARN] Port %PORT% is already in use.
  echo   [1] Keep the existing service (default)
  echo   [2] Stop it and start the selected model
  set /p "PORT_ACTION=Your choice [1/2]: "
  if not "!PORT_ACTION!"=="2" (
    echo [INFO] Existing service kept.
    goto :START_BRIDGE
  )
  set "LISTENER_PID="
  for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT%" ^| findstr /i "LISTENING"') do if not defined LISTENER_PID set "LISTENER_PID=%%P"
  if not defined LISTENER_PID (
    echo [ERROR] Could not determine the process using port %PORT%.
    pause
    exit /b 1
  )
  tasklist /FI "PID eq !LISTENER_PID!" /NH | findstr /i "llama-server.exe" >nul
  if errorlevel 1 (
    echo [ERROR] Port %PORT% is used by another program ^(PID !LISTENER_PID!^); refusing to stop it.
    pause
    exit /b 1
  )
  echo [INFO] Stopping llama-server.exe ^(PID !LISTENER_PID!^)...
  taskkill /PID !LISTENER_PID! /F
  ping -n 3 127.0.0.1 >nul
)

echo [1/2] Starting model server in a separate window...
start "LlamaServer-%PORT%" "%ComSpec%" /k ""%SERVER_EXE%" -m "%MODEL%" --host %HOST% --port %PORT% -c %CTX% -t %NUMBER_OF_PROCESSORS%"

echo       Waiting for %HOST%:%PORT% (max %WAIT_SEC%s)...
set "READY=0"
for /l %%i in (1,1,%WAIT_SEC%) do (
  ping -n 2 127.0.0.1 >nul
  netstat -ano | findstr ":%PORT%" | findstr /i "LISTENING" >nul
  if not errorlevel 1 (
    set "READY=1"
    goto :READY_OK
  )
)
:READY_OK
if "%READY%"=="1" (
  echo       Server is ready.
) else (
  echo [WARN] Timeout - server may still be loading the model.
)

:START_BRIDGE
echo [2/2] Starting translation bridge...
start "" "%BRIDGE_EXE%"

echo.
echo Done. Close the LlamaServer window to stop the service.
pause
endlocal
