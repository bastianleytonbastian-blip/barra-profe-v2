@echo off
REM Abre la barra v2 (sin ventana de consola).
REM Si la barra anterior sigue abierta, cierrala antes (con su X): las dos usan
REM el mismo puerto y la segunda solo le avisa a la primera en vez de abrirse.
set "PYW="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\pythonw.exe" set "PYW=%%D\pythonw.exe"
if defined PYW (
    start "" "%PYW%" "%~dp0herramienta\barra_profe.pyw"
    exit /b
)
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" pythonw "%~dp0herramienta\barra_profe.pyw"
    exit /b
)
where pyw >nul 2>&1
if not errorlevel 1 (
    start "" pyw "%~dp0herramienta\barra_profe.pyw"
    exit /b
)
echo No se encontro Python. Instalalo desde python.org o con herramienta\INSTALAR.bat.
pause
