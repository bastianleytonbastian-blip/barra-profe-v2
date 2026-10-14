@echo off
chcp 65001 >nul
cd /d "%~dp0herramienta"
python probar_red.py
echo.
pause
