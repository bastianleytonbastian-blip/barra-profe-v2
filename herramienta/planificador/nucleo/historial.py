"""Historial de planificaciones: un JSON por clase en data/planificaciones/."""
import json
import os
import re
from datetime import datetime

from nucleo import rutas


def _carpeta():
    return os.path.join(rutas.datos_usuario(), "planificaciones")


def guardar(registro):
    """registro: dict con meta y campos de la clase. Devuelve el nombre del archivo."""
    os.makedirs(_carpeta(), exist_ok=True)
    base = re.sub(r"[^0-9A-Za-zÁÉÍÓÚáéíóúÑñ]+", "_", f"{registro.get('curso', '')}_{registro.get('nombre', '')}")[:70].strip("_")
    nombre = f"{datetime.now():%Y%m%d_%H%M%S}_{base}.json"
    registro = dict(registro, guardado=datetime.now().isoformat(timespec="seconds"))
    with open(os.path.join(_carpeta(), nombre), "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=1)
    return nombre


def listar():
    """[(archivo, registro)] de la más reciente a la más antigua."""
    if not os.path.isdir(_carpeta()):
        return []
    salida = []
    for archivo in sorted(os.listdir(_carpeta()), reverse=True):
        if archivo.endswith(".json"):
            try:
                with open(os.path.join(_carpeta(), archivo), encoding="utf-8") as f:
                    salida.append((archivo, json.load(f)))
            except Exception:
                continue
    return salida


def eliminar(archivo):
    try:
        os.remove(os.path.join(_carpeta(), os.path.basename(archivo)))
    except OSError:
        pass
