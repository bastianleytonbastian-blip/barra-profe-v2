"""Convierte una guía HTML a PDF con Chrome o Edge en modo invisible (incluye pictogramas e imágenes de internet)."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CANDIDATOS = [
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
]


def navegador():
    for ruta in CANDIDATOS:
        ruta = os.path.expandvars(ruta)
        if os.path.exists(ruta):
            return ruta
    return shutil.which("chrome") or shutil.which("msedge")


def html_a_pdf(html_texto, espera_ms=20000):
    """Devuelve los bytes del PDF. espera_ms: tiempo que se deja para cargar pictogramas e imágenes."""
    exe = navegador()
    if not exe:
        raise RuntimeError("No se encontró Chrome ni Edge para crear el PDF.")
    with tempfile.TemporaryDirectory() as tmp:
        entrada = Path(tmp) / "guia.html"
        salida = Path(tmp) / "guia.pdf"
        entrada.write_text(html_texto, encoding="utf-8")
        comando = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer",
                   f"--user-data-dir={Path(tmp) / 'perfil'}", f"--virtual-time-budget={espera_ms}",
                   "--run-all-compositor-stages-before-draw", f"--print-to-pdf={salida}", entrada.as_uri()]
        subprocess.run(comando, capture_output=True, timeout=espera_ms / 1000 + 90,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if not salida.exists() or salida.stat().st_size == 0:
            raise RuntimeError("El navegador no generó el PDF.")
        return salida.read_bytes()
