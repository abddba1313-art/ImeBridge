@echo off
rem ---------------------------------------------------------------
rem  Translation Service Launcher  (ASCII ONLY - no codepage issue)
rem  1) select a gguf model, listen on 127.0.0.1:1236
rem  2) wait until port is really LISTENING
rem  3) launch the input translation bridge exe
rem ---------------------------------------------------------------
setlocal EnableExtensions EnableDelayedExpansion
chcp 936 >nul 2>&1
title Input Translation Bridge Launcher

rem ===================== CONFIG =====================
set "DIR=%~dp0"
set "HOST=127.0.0.1"
set "PORT=1236"
set "CTX=2048"
set "WAIT_SEC=120"
set "RUNAS_ADMIN=0"
rem ==================================================

if "%RUNAS_ADMIN%"=="1" (
  fltmc >nul 2>&1
  if errorlevel 1 (
    echo Requesting administrator privilege...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
  )
)

cd /d "%DIR%" 2>nul
if errorlevel 1 (
  echo [ERROR] Folder not found: %DIR%
  echo         Edit the DIR line at the top of this .bat
  pause
  exit /b 1
)

rem ---- 1. select main model ----
set "MODEL_CHOICE=%~1"
if not defined MODEL_CHOICE (
  echo Select the translation model:
  echo   [1] Hy-MT3-1.8B-Q4_K_M  ^(smaller, faster^)
  echo   [2] Hy-MT3-1.8B-Q8_0    ^(default, highest quality^)
  echo   [3] Hy-MT3-1.8B-Q2_K    ^(smallest^)
  set /p "MODEL_CHOICE=Your choice [1/2/3, default=2]: "
)
if not defined MODEL_CHOICE set "MODEL_CHOICE=2"
call :SELECT_MODEL "%MODEL_CHOICE%"
if errorlevel 1 (
  echo [ERROR] Invalid model choice: %MODEL_CHOICE%
  echo         Use 1 or Q4_K_M, 2 or Q8_0, 3 or Q2_K.
  pause
  exit /b 1
)
if not exist "%MODEL%" (
  echo [ERROR] Model not found: %MODEL%
  pause
  exit /b 1
)

rem ---- 2. locate server binary ----
set "SERVER_EXE="
if exist "%DIR%llama-server.exe" set "SERVER_EXE=%DIR%llama-server.exe"
if not defined SERVER_EXE if exist "%DIR%server.exe" set "SERVER_EXE=%DIR%server.exe"
if not defined SERVER_EXE if exist "%DIR%llama.exe" set "SERVER_EXE=%DIR%llama.exe"
if not defined SERVER_EXE (
  echo [ERROR] No llama.exe / llama-server.exe in: %DIR%
  pause
  exit /b 1
)

rem ---- 3. locate bridge exe 12.0 (Windows resolves the Unicode filename) ----
set "BRIDGE_EXE="
for %%F in ("%DIR%*12.0.exe") do if not defined BRIDGE_EXE set "BRIDGE_EXE=%%~fF"
if not defined BRIDGE_EXE (
  echo [ERROR] Bridge exe 12.0 not found in: %DIR%
  pause
  exit /b 1
)

echo ------------------------------------------------
echo Model  : %MODEL%
echo Server : %SERVER_EXE%
echo Bridge : %BRIDGE_EXE%
echo Listen : %HOST%:%PORT%
echo ------------------------------------------------

rem ---- port already up? ask whether to keep or switch ----
netstat -ano | findstr ":%PORT%" | findstr /i "LISTENING" >nul
if not errorlevel 1 (
  echo [WARN] Port %PORT% is already in use.
  echo   [1] Keep the existing service ^(default^)
  echo   [2] Stop it and start the selected model
  set /p "PORT_ACTION=Your choice [1/2]: "
  if not "!PORT_ACTION!"=="2" (
    echo [INFO] Existing service kept; no new model server was started.
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
  echo [INFO] Stopping llama-server.exe on port %PORT% ^(PID !LISTENER_PID!^)...
  taskkill /PID !LISTENER_PID! /F
  ping -n 3 127.0.0.1 >nul
)

echo [1/2] Starting model server in a separate visible window...
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
  echo [WARN] Timeout. "%SERVER_EXE%" may be CLI-only and cannot serve an API.
  echo        Download llama-server.exe from llama.cpp release into:
  echo        %DIR%
  echo        Still launching the bridge, fix the server if it fails.
)

:START_BRIDGE
echo [2/2] Starting input translation bridge...
start "" "%BRIDGE_EXE%"

echo.
echo Done. The model service has its own window and keeps running.
echo Close the LlamaServer window to stop the service.
echo Press Enter to close this launcher window.
set /p "LAUNCHER_EXIT="
endlocal
exit /b 0

:SELECT_MODEL
set "MODEL="
if /i "%~1"=="1"    set "MODEL=%DIR%Hy-MT3-1.8B-Q4_K_M.gguf"
if /i "%~1"=="Q4"   set "MODEL=%DIR%Hy-MT3-1.8B-Q4_K_M.gguf"
if /i "%~1"=="Q4_K_M" set "MODEL=%DIR%Hy-MT3-1.8B-Q4_K_M.gguf"
if /i "%~1"=="2"    set "MODEL=%DIR%Hy-MT3-1.8B-Q8_0.gguf"
if /i "%~1"=="Q8"   set "MODEL=%DIR%Hy-MT3-1.8B-Q8_0.gguf"
if /i "%~1"=="Q8_0" set "MODEL=%DIR%Hy-MT3-1.8B-Q8_0.gguf"
if /i "%~1"=="3"    set "MODEL=%DIR%Hy-MT3-1.8B-Q2_K.gguf"
if /i "%~1"=="Q2"   set "MODEL=%DIR%Hy-MT3-1.8B-Q2_K.gguf"
if /i "%~1"=="Q2_K" set "MODEL=%DIR%Hy-MT3-1.8B-Q2_K.gguf"
if not defined MODEL exit /b 1
exit /b 0
