"""Conexión con «Barra Profe v2» (la otra aplicación que maneja WebClass).

Solo se lee su código: nunca se modifica nada en su carpeta. Las operaciones se hacen en un proceso aparte
(barra_worker.py) para que la contraseña y la sesión de WebClass no pasen por este servidor.
"""
import json
import os
import subprocess
import sys

TRABAJADOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "barra_worker.py")
MARCA = "##RESULTADO "
_MODULOS = {}   # (ruta, fecha) -> módulo ya cargado


def modulo_de_barra(raiz, nombre):
    """Un módulo LIVIANO de Barra (p. ej. barra_utiles, sin red ni sesión) cargado desde su archivo, sin tocar sys.path.

    Sirve para leer tablas que deben ser las mismas en las dos apps (asignaturas, colores). None si no está.
    """
    if not raiz:
        return None                         # planificador suelto: no hay Barra de dónde leer
    ruta = os.path.join(raiz, "herramienta", f"{nombre}.py")
    try:
        fecha = os.path.getmtime(ruta)
    except OSError:
        return None
    if (ruta, fecha) not in _MODULOS:
        import importlib.util
        spec = importlib.util.spec_from_file_location(f"barra_{nombre}", ruta)
        modulo = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(modulo)
        except Exception:  # noqa: BLE001  (una Barra a medio actualizar no debe botar el planificador)
            return None
        _MODULOS[(ruta, fecha)] = modulo
    return _MODULOS[(ruta, fecha)]


def validar_ruta(ruta):
    """(ok, mensaje) para la carpeta de Barra Profe configurada."""
    ruta = (ruta or "").strip().strip('"')
    if not ruta:
        return False, "Falta indicar la carpeta de Barra Profe en «Mi perfil»."
    if not os.path.isdir(ruta):
        return False, "Esa carpeta no existe."
    if not os.path.exists(os.path.join(ruta, "herramienta", "webclass_clases.py")):
        return False, "No parece la carpeta de Barra Profe: no encuentro herramienta\\webclass_clases.py."
    return True, "Barra Profe encontrada."


def ejecutar(ruta, op, datos=None, timeout=360):
    """Corre una operación de Barra en un proceso aparte y devuelve su resultado (dict). Lanza RuntimeError si falla."""
    ok, mensaje = validar_ruta(ruta)
    if not ok:
        raise RuntimeError(mensaje)
    entrada = json.dumps({**(datos or {}), "op": op, "ruta_barra": ruta.strip().strip('"')}, ensure_ascii=False)
    entorno = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        r = subprocess.run([sys.executable, "-B", TRABAJADOR], input=entrada.encode("utf-8"), capture_output=True,
                           timeout=timeout, env=entorno, cwd=os.path.dirname(os.path.dirname(TRABAJADOR)),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise RuntimeError("WebClass tardó demasiado en responder. Revisa si la clase se creó antes de reintentar.")
    salida = r.stdout.decode("utf-8", errors="replace")
    for linea in reversed(salida.splitlines()):
        if linea.startswith(MARCA):
            resultado = json.loads(linea[len(MARCA):])
            if "error" in resultado:
                raise RuntimeError(resultado["error"])
            return resultado
    detalle = (r.stderr.decode("utf-8", errors="replace") or salida)[-400:]
    raise RuntimeError(f"No se pudo hablar con Barra Profe: {detalle.strip() or 'sin respuesta'}")
