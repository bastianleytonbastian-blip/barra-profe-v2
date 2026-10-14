"""Consulta de Objetivos de Aprendizaje oficiales (data/curriculo_oa.json, generado por nucleo.actualizador)."""
import json
import os
import re

from nucleo.actualizador import SALIDA as RUTA

_cache = {"mtime": None, "datos": {}}


def _base():
    """{asignatura: {curso: {oa[], habilidades[], actitudes[]}}}; se relee si el archivo cambió."""
    try:
        mtime = os.path.getmtime(RUTA)
    except OSError:
        return {}
    if _cache["mtime"] != mtime:
        try:
            with open(RUTA, encoding="utf-8") as f:
                crudo = json.load(f).get("asignaturas", {})
            _cache["datos"] = {a: v["cursos"] for a, v in crudo.items()}
        except Exception:
            _cache["datos"] = {}
        _cache["mtime"] = mtime
    return _cache["datos"]


def _orden_curso(curso):
    m = re.match(r"(\d)° (Básico|Medio)", curso)
    return (0 if m and m.group(2) == "Básico" else 1, int(m.group(1)) if m else 99)


def hay_curriculo():
    return bool(_base())


def asignaturas():
    return sorted(_base())


def cursos(asignatura=None):
    """Cursos de una asignatura; sin asignatura, todos los cursos de la base en orden (1° Básico … 4° Medio)."""
    base = _base()
    if asignatura:
        nombres = set(base.get(asignatura, {}))
    else:
        nombres = {c for v in base.values() for c in v}
    return sorted(nombres, key=_orden_curso)


def oa_del_curso(asignatura, curso):
    """Lista de OA oficiales: [{codigo, codigo_oficial, eje, texto, priorizado}, ...] (vacía si no existe)."""
    return _base().get(asignatura or "", {}).get(curso or "", {}).get("oa", [])


def lista_para_prompt(oas, largo_max=None):
    """'OA9 [Eje] texto' por línea; largo_max acorta cada texto (para proveedores con poco límite por minuto)."""
    lineas = []
    for o in oas:
        texto = o["texto"]
        if largo_max and len(texto) > largo_max:
            texto = texto[:largo_max].rsplit(" ", 1)[0] + "…"
        eje = f" [{o['eje']}]" if o.get("eje") else ""
        lineas.append(f"{o['codigo']}{eje} {texto}")
    return "\n".join(lineas)
