"""Versiones del planificador y de Barra Profe, y si son compatibles. Sin Streamlit ni red."""
import os
import re

from nucleo import rutas

BARRA_MINIMA = "2.6.0"   # versión de Barra que necesita esta versión del planificador (sube junto con las funciones que use)
# 2.6.0: los colores de la barra (tema.py) y la tabla única de asignaturas.
_FORMATO = re.compile(r"\d+\.\d+\.\d+")


def leer(carpeta):
    """Versión escrita en el archivo VERSION de la carpeta ('' si falta o no tiene el formato MAYOR.MENOR.PARCHE)."""
    try:
        with open(os.path.join(carpeta, "VERSION"), encoding="utf-8-sig") as f:
            texto = f.read().strip()
    except OSError:
        return ""
    return texto if _FORMATO.fullmatch(texto) else ""


def version_planificador():
    return leer(rutas.CODIGO)


def version_barra():
    return leer(os.path.join(rutas.BARRA, "herramienta")) if rutas.EN_BARRA else ""


def _tupla(version):
    return tuple(int(n) for n in version.split("."))


def compatibilidad():
    """(ok, mensaje). Fuera de Barra no aplica. Si Barra es más vieja de lo que el planificador necesita, no se escribe nada."""
    if not rutas.EN_BARRA:
        return True, ""
    vb = version_barra()
    if not vb:
        return False, ("No encuentro la versión de Barra Profe (falta herramienta\\VERSION). "
                       "Actualiza Barra con herramienta\\ACTUALIZAR.bat.")
    if _tupla(vb) < _tupla(BARRA_MINIMA):
        return False, (f"Esta versión del planificador necesita Barra Profe {BARRA_MINIMA} o más nueva y tienes la {vb}. "
                       "Actualiza Barra con herramienta\\ACTUALIZAR.bat. No se hizo nada.")
    return True, ""


def resumen():
    ok, mensaje = compatibilidad()
    return {"planificador": version_planificador(), "barra": version_barra(), "barra_minima": BARRA_MINIMA,
            "compatible": ok, "mensaje": mensaje}
