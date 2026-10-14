"""Actualizaciones en línea de Barra Profe (y del planificador que viaja dentro) desde un «release» de GitHub.

Cómo funciona:
  1. `buscar_nueva()` pregunta a GitHub cuál es el último release y lo compara con `herramienta\\VERSION`.
  2. `actualizar()` baja el zip, comprueba su suma SHA-256, guarda una copia de seguridad del código actual y copia
     encima solo lo que trae el release (carpeta `herramienta\\`). Nunca toca `personal\\` ni `datos\\`.
  3. Después se corren los mismos pasos de ACTUALIZAR.bat (complementos y botones).

Cada release tiene tres archivos: `barra-profe-X.Y.Z.zip`, `barra-profe-X.Y.Z.zip.sha256` y `version.json` (los arma `publicar.py`).
Solo se descarga desde GitHub, y solo del repositorio fijo `REPO`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

REPO = "bastianleytonbastian-blip/barra-profe-v2"
# «latest/download» redirige al último release y no tiene el límite de consultas de la API (que en un colegio, con una sola IP, se agota).
MANIFIESTO = "https://github.com/{repo}/releases/latest/download/version.json"
HOSTS_PERMITIDOS = ("https://github.com/",)
# Archivos de esta carpeta que son del docente y jamás se reemplazan ni se borran.
PROTEGIDOS = ("registro_asignaciones.csv",)
IGNORAR = ("__pycache__",)


# Motivo técnico de la última consulta que falló (vacío si salió bien); la barra lo muestra para diagnosticar.
ULTIMO_ERROR = ""


class ErrorActualizacion(Exception):
    """Algo salió mal; el mensaje está escrito para mostrárselo al docente."""


def tupla(version: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (version or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def es_mas_nueva(actual: str, otra: str) -> bool:
    a, b = tupla(actual), tupla(otra)
    return bool(a and b and b > a)


def _url_segura(url: str) -> bool:
    return isinstance(url, str) and url.startswith(HOSTS_PERMITIDOS)


def _abrir(url: str, abrir=None, timeout: int = 8):
    if not _url_segura(url):
        raise ErrorActualizacion("La dirección de descarga no es de GitHub; no se usa.")
    pedido = urllib.request.Request(url, headers={"User-Agent": "BarraProfe-actualizador", "Accept": "*/*"})
    return (abrir or urllib.request.urlopen)(pedido, timeout=timeout)


def interpretar_manifiesto(datos: dict, repo: str = REPO) -> dict | None:
    """Valida el `version.json` del release: versión, zip y suma deben ser de ESTE repositorio. None si no sirve."""
    if not isinstance(datos, dict):
        return None
    version = str(datos.get("version") or "").lstrip("v")
    base = f"https://github.com/{repo}/releases/download/v{version}/"
    zip_url, sha_url = datos.get("zip", ""), datos.get("sha256", "")
    if not tupla(version) or not (isinstance(zip_url, str) and zip_url.startswith(base) and zip_url.endswith(".zip")
                                  and isinstance(sha_url, str) and sha_url.startswith(base) and sha_url.endswith(".sha256")):
        return None
    return {"version": version, "zip": zip_url, "sha256": sha_url, "notas": str(datos.get("notas") or "").strip()}


def consultar(actual: str, repo: str = REPO, abrir=None) -> tuple[dict | None, bool]:
    """(release más nuevo si es mayor que `actual` o None, si se pudo consultar). Sirve para distinguir «al día» de «sin red»."""
    global ULTIMO_ERROR
    ULTIMO_ERROR = ""
    try:
        with _abrir(MANIFIESTO.format(repo=repo), abrir) as r:
            datos = json.loads(r.read().decode("utf-8-sig"))
    except (OSError, ValueError, ErrorActualizacion) as exc:
        ULTIMO_ERROR = f"{type(exc).__name__}: {exc}"[:200]        # para que «sin conexión» diga por qué
        return None, False
    info = interpretar_manifiesto(datos, repo)
    return (info if info and es_mas_nueva(actual, info["version"]) else None), info is not None


def buscar_nueva(actual: str, repo: str = REPO, abrir=None) -> dict | None:
    """Datos del release más nuevo si es mayor que `actual`; None si está al día o no se pudo consultar (sin red, etc.)."""
    return consultar(actual, repo, abrir)[0]


def _bajar(url: str, destino: str, abrir=None) -> None:
    with _abrir(url, abrir, timeout=60) as r, open(destino, "wb") as f:
        shutil.copyfileobj(r, f)


def suma_sha256(ruta: str) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _nombres_seguros(zf: zipfile.ZipFile) -> list[str]:
    """Rutas del zip que se pueden copiar: solo dentro de `herramienta/`, sin `..` ni rutas absolutas."""
    nombres = []
    for info in zf.infolist():
        n = info.filename.replace("\\", "/")
        if info.is_dir():
            continue
        if n.startswith("/") or re.match(r"^[A-Za-z]:", n) or ".." in n.split("/") or not n.startswith("herramienta/"):
            raise ErrorActualizacion(f"El paquete trae una ruta que no corresponde ({n}); no se instala.")
        if any(p in IGNORAR for p in n.split("/")) or os.path.basename(n) in PROTEGIDOS:
            continue
        nombres.append(n)
    return nombres


def respaldar(carpeta_herramienta: str, carpeta_respaldo: str, version: str) -> str:
    """Zip con el código actual (sin __pycache__ ni archivos del docente) para poder volver atrás."""
    os.makedirs(carpeta_respaldo, exist_ok=True)
    ruta = os.path.join(carpeta_respaldo, f"herramienta-{version or 'sin-version'}.zip")
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, archivos in os.walk(carpeta_herramienta):
            dirs[:] = [d for d in dirs if d not in IGNORAR]
            for a in archivos:
                completo = os.path.join(base, a)
                z.write(completo, os.path.join("herramienta", os.path.relpath(completo, carpeta_herramienta)))
    return ruta


def aplicar_zip(ruta_zip: str, sha_esperado: str, version: str, carpeta_herramienta: str, carpeta_respaldo: str) -> list[str]:
    """Comprueba la suma, respalda y copia encima el contenido del zip. Devuelve los archivos escritos."""
    if suma_sha256(ruta_zip) != sha_esperado.strip().lower():
        raise ErrorActualizacion("La descarga llegó dañada (la suma de verificación no coincide). No se instaló nada.")
    try:
        zf = zipfile.ZipFile(ruta_zip)
    except zipfile.BadZipFile as exc:
        raise ErrorActualizacion("El paquete descargado no es un zip válido.") from exc
    with zf:
        nombres = _nombres_seguros(zf)
        if "herramienta/VERSION" not in nombres or zf.read("herramienta/VERSION").decode("utf-8-sig").strip() != version:
            raise ErrorActualizacion("El paquete no corresponde a la versión anunciada. No se instaló nada.")
        actual = ""
        try:
            with open(os.path.join(carpeta_herramienta, "VERSION"), encoding="utf-8-sig") as f:
                actual = f.read().strip()
        except OSError:
            pass
        respaldar(carpeta_herramienta, carpeta_respaldo, actual)
        escritos = []
        for n in nombres:
            destino = os.path.join(carpeta_herramienta, *n.split("/")[1:])
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            temporal = destino + ".nuevo"
            with zf.open(n) as origen, open(temporal, "wb") as f:
                shutil.copyfileobj(origen, f)
            os.replace(temporal, destino)
            escritos.append(n)
    return escritos


def pasos_posteriores(carpeta_herramienta: str) -> list[str]:
    """Los mismos pasos de ACTUALIZAR.bat: complementos de Python y migración de botones. Devuelve avisos."""
    avisos = []
    sin_ventana = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    py = sys.executable
    if py.lower().endswith("pythonw.exe"):
        py = py[:-len("pythonw.exe")] + "python.exe"
    comandos = [[py, "-m", "pip", "install", "--quiet", "--upgrade", "requests", "keyring", "tkinterdnd2"]]
    req = os.path.join(carpeta_herramienta, "planificador", "requirements.txt")
    if os.path.isfile(req):
        comandos.append([py, "-m", "pip", "install", "--quiet", "-r", req])
    comandos.append([py, os.path.join(carpeta_herramienta, "instalar.py"), "--actualizar"])
    for c in comandos:
        try:
            r = subprocess.run(c, cwd=carpeta_herramienta, capture_output=True, timeout=600, creationflags=sin_ventana)
            if r.returncode != 0:
                avisos.append("Un paso posterior no terminó bien; ejecuta ACTUALIZAR.bat para completarlo.")
                break
        except (OSError, subprocess.SubprocessError):
            avisos.append("No pude correr los pasos finales; ejecuta ACTUALIZAR.bat para completarlos.")
            break
    return avisos


def actualizar(info: dict, carpeta_herramienta: str, carpeta_respaldo: str, abrir=None, con_pasos: bool = True) -> dict:
    """Baja e instala el release `info` (de `buscar_nueva`). Devuelve {"version", "avisos"} o lanza ErrorActualizacion."""
    tmp = tempfile.mkdtemp(prefix="barra_actualizacion_")
    try:
        ruta_zip, ruta_sha = os.path.join(tmp, "paquete.zip"), os.path.join(tmp, "paquete.sha256")
        try:
            _bajar(info["zip"], ruta_zip, abrir)
            _bajar(info["sha256"], ruta_sha, abrir)
        except OSError as exc:
            raise ErrorActualizacion(f"No pude descargar la actualización (¿sin internet?). No se cambió nada. ({exc})") from exc
        with open(ruta_sha, encoding="utf-8") as f:
            sha = (f.read().split() or [""])[0]
        aplicar_zip(ruta_zip, sha, info["version"], carpeta_herramienta, carpeta_respaldo)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"version": info["version"], "avisos": pasos_posteriores(carpeta_herramienta) if con_pasos else []}
