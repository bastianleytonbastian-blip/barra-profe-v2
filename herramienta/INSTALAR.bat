@echo off
REM ===================================================================
REM  Herramientas de Webclass - instalacion en un PC nuevo
REM
REM  Busca Python; si no esta, lo instala desde Microsoft (winget), que
REM  es la forma que el Control inteligente de aplicaciones de Windows 11
REM  acepta sin bloquear nada.
REM ===================================================================

chcp 65001 >nul
set PYTHONIOENCODING=utf-8
title Herramientas de Webclass
cd /d "%~dp0"

REM ---- 0. Musiquita, mientras dura la instalacion --------------------
REM Se calla sola al terminar. Si no hay archivo, no pasa nada.
set "MUSICA=%~dp0..\personal\inicio.mp3"
if not exist "%MUSICA%" set "MUSICA=%~dp0..\personal\inicio.wav"
set "PIDMUSICA=%TEMP%\webclass_musica.pid"
if exist "%MUSICA%" (
    del "%PIDMUSICA%" >nul 2>&1
    start "" /b powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden ^
          -File "%~dp0sonar.ps1" -Archivo "%MUSICA%" -ArchivoPid "%PIDMUSICA%"
)

echo.
echo ============================================
echo    HERRAMIENTAS DE WEBCLASS PARA DOCENTES
echo ============================================
echo.

REM La limpieza de versiones anteriores la hace instalar.py, que puede
REM comparar nombres de verdad. En batch salia mal y borraba todo.

REM ---- 1. Buscar Python ---------------------------------------------
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)

if defined PY goto :tengo_python

echo No hay Python en este equipo. Lo voy a instalar (tarda unos minutos).
echo Windows puede pedirte permiso: acepta.
echo.
winget install -e --id Python.Python.3.12 --scope user --silent ^
       --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :sin_python

REM winget no refresca el PATH de esta ventana: se apunta a la ruta conocida.
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PY%" goto :sin_python
echo.
echo Python instalado.

:tengo_python
echo.
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo Usando %%v
echo.

REM ---- 2. Complementos ----------------------------------------------
echo Instalando los complementos que se necesitan...
%PY% -m pip install --quiet --upgrade pip
%PY% -m pip install --quiet requests keyring tkinterdnd2
if errorlevel 1 (
    echo.
    echo No se pudieron instalar los complementos. Revisa la conexion a internet.
    echo.
    pause
    set ERRORES=1
    goto callar
)

REM ---- 2b. Complementos del planificador con IA ---------------------
REM El planificador viaja dentro de esta carpeta (herramienta\planificador).
REM Si algo falla aqui, la barra y el resto de las herramientas funcionan igual.
if exist "%~dp0planificador\requirements.txt" (
    echo Instalando los complementos del planificador con IA...
    %PY% -m pip install --quiet -r "%~dp0planificador\requirements.txt"
    if errorlevel 1 (
        echo.
        echo No se pudieron instalar los complementos del planificador con IA.
        echo La barra funciona igual. Para reintentar, usa ACTUALIZAR.bat con internet.
        echo.
    )
)

REM ---- 3. Instalador propio -----------------------------------------
echo.
%PY% instalar.py
echo.
pause
set ERRORES=0
goto callar

:sin_python
echo.
echo ===================================================================
echo  No pude instalar Python solo.
echo.
echo  Instalalo a mano desde:  https://www.python.org/downloads/
echo  IMPORTANTE: en la primera pantalla marca la casilla
echo              "Add python.exe to PATH".
echo.
echo  Despues vuelve a abrir este archivo (INSTALAR.bat).
echo ===================================================================
echo.
pause
set ERRORES=1
goto callar

:callar
REM Corta la musiquita al terminar, pase lo que pase.
if exist "%PIDMUSICA%" (
    for /f "usebackq delims=" %%p in ("%PIDMUSICA%") do taskkill /f /pid %%p >nul 2>&1
    del "%PIDMUSICA%" >nul 2>&1
)
exit /b %ERRORES%
