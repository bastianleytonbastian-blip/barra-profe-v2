"""Historial de planificaciones: un JSON por clase en data/planificaciones/."""
import json
import os
import re
from datetime import datetime

from nucleo import rutas


def _carpeta():
    return os.path.join(rutas.datos_usuario(), "planificaciones")


def guardar(registro):
    """registro: dict con meta y campos de la clase. Devuelve el nombre del archivo.

    Si la clase ya se guardó antes («archivo_historial»), se actualiza ese mismo archivo en vez de crear otro.
    """
    os.makedirs(_carpeta(), exist_ok=True)
    previo = os.path.basename(str(registro.get("archivo_historial") or ""))
    if previo.endswith(".json") and os.path.isfile(os.path.join(_carpeta(), previo)):
        nombre = previo
    else:
        base = re.sub(r"[^0-9A-Za-zÁÉÍÓÚáéíóúÑñ]+", "_", f"{registro.get('curso', '')}_{registro.get('nombre', '')}")[:70].strip("_")
        nombre = f"{datetime.now():%Y%m%d_%H%M%S}_{base}.json"
    registro = dict(registro, guardado=datetime.now().isoformat(timespec="seconds"), archivo_historial=nombre)
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


def unir(guardadas, creadas):
    """Una sola lista para la sección «Historial», de lo más reciente a lo más antiguo.

    guardadas: [(archivo, plan)] del historial; creadas: filas del registro de lo que el planificador creó en WebClass.
    Una clase enviada desde el planificador queda guardada con sus ids de WebClass (plan["webclass"]), así que aparece
    una sola vez, con su contenido y sus enlaces. Las filas del registro sin clase guardada (anteriores a 1.3.0) van solas.
    """
    items, vistas = [], set()
    for archivo, plan in guardadas:
        enlaces = [{"id_unidad": str(w.get("id_unidad", "")), "idclase": str(w.get("idclase", "")), "curso": w.get("curso", ""),
                    "unidad": w.get("unidad", ""), "fecha_clase": w.get("fecha", ""), "eliminada": bool(w.get("eliminada"))}
                   for w in (plan.get("webclass") or []) if isinstance(w, dict) and w.get("idclase")]
        vistas.update((e["id_unidad"], e["idclase"]) for e in enlaces)
        fecha_clase = str(plan.get("fecha") or "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha_clase):                 # la pantalla la guarda como 2026-10-14
            fecha_clase = "/".join(reversed(fecha_clase.split("-")))
        items.append({"clave": f"g:{archivo}", "archivo": archivo, "nombre": plan.get("nombre") or "Sin nombre",
                      "asignatura": plan.get("asignatura", ""), "curso": plan.get("curso", ""), "tema": plan.get("tema", ""),
                      "fecha": plan.get("guardado", ""), "fecha_clase": fecha_clase, "webclass": enlaces})
    for fila in creadas:
        par = (str(fila.get("idunidad", "")), str(fila.get("idclase", "")))
        if not par[1] or par in vistas:
            continue
        vistas.add(par)
        items.append({"clave": f"w:{par[0]}:{par[1]}", "archivo": "", "nombre": fila.get("clase") or "Sin nombre",
                      "asignatura": "", "curso": fila.get("curso", ""), "tema": "", "fecha": fila.get("fecha_creacion", ""),
                      "fecha_clase": fila.get("fecha_clase", ""),
                      "webclass": [{"id_unidad": par[0], "idclase": par[1], "curso": fila.get("curso", ""),
                                    "unidad": fila.get("unidad", ""), "fecha_clase": fila.get("fecha_clase", ""),
                                    "eliminada": False}]})
    items.sort(key=lambda it: it["fecha"] or "", reverse=True)
    return items
