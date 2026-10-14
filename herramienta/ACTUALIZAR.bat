@echo off
REM ===================================================================
REM  Actualizar las herramientas sin perder tu configuracion
REM
REM  Se usa DESPUES de copiar una version nueva encima de la que habia.
REM  No pregunta nada, no toca tu perfil, tus botones, tus registros ni
REM  tus accesos del escritorio: solo deja el codigo al dia.
REM
REM  Para instalar por primera vez, usa INSTALAR.bat.
REM ===================================================================

chcp 65001 >nul
set PYTHONIOENCODING=utf-8
title Actualizar herramientas de Webclass
cd /d "%~dp0"

echo.
echo ============================================
echo    ACTUALIZAR HERRAMIENTAS DE WEBCLASS
echo ============================================
echo.
echo  Tu perfil, tus botones y tus registros no se tocan.
echo.

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo  No encuentro Python en este equipo.
    echo  Usa INSTALAR.bat, que lo instala.
    echo.
    pause
    exit /b 1
)

echo Revisando complementos...
%PY% -m pip install --quiet --upgrade requests keyring tkinterdnd2
if exist "%~dp0planificador\requirements.txt" (
    echo Revisando complementos del planificador con IA...
    %PY% -m pip install --quiet -r "%~dp0planificador\requirements.txt"
)

echo.
%PY% instalar.py --actualizar
echo.
echo  Listo. Cierra la barra y vuelve a abrirla para que tome los cambios.
echo.
pause
