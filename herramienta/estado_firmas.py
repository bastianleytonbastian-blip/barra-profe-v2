"""
Revisa el libro de clases del día y deja el resultado en un archivo JSON.

No escribe nada en Webclass: solo mira. Lo usa la barra flotante para avisar,
sin abrir nada, cuándo quedan bloques tuyos sin firmar.

Uso:
  pythonw estado_firmas.py            revisa hoy
  python  estado_firmas.py --fecha 28/09/2026
  python  estado_firmas.py --salida "D:\\otra carpeta\\estado_firmas.json"
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time

import barra_utiles as bu
import rutas
import webclass_libro as L
import webclass_tareas as w

SALIDA = rutas.dato("estado_firmas.json")
AUSENTE, ATRASADA = 4, 2  # códigos de estado_asistencia en Webclass


def asistencia_jefatura(s, token, fecha: datetime.date, perfil: dict) -> dict:
    """Quiénes faltaron hoy en el curso de jefatura, por apellido.

    Toma el primer bloque del día que tenga asistencia tomada y que cubra al
    curso completo; si ninguno califica, lo dice en vez de inventar.
    """
    jefatura = perfil.get("jefatura")
    if not jefatura or jefatura not in perfil.get("curso_ids", {}):
        return {"estado": "sin curso de jefatura en el perfil"}
    curso_id = perfil["curso_ids"][jefatura]
    dia = L.bloques_del_dia(s, curso_id, fecha, perfil["iduser"], token, solo_mios=False)
    con_asistencia = sorted([b for b in dia if b.get("val_asistencia")],
                            key=lambda b: b.get("inicio") or "")
    if not con_asistencia:
        return {"curso": jefatura, "estado": "nadie ha tomado asistencia todavía"}

    nomina = L.nomina_curso(s, curso_id, con_asistencia[0].get("nivel"), fecha,
                            fecha.year, token)
    activas = [a for a in nomina if a.get("retirado") != 1]
    por_id = {a["id"]: a for a in activas}
    for bloque in con_asistencia:
        contadas = sum(bloque.get(k) or 0 for k in
                       ("cnt_presente", "cnt_ausente", "cnt_atrasado", "cnt_retirado"))
        if contadas != len(activas):
            continue          # bloque de religión o electivo: no es el curso entero
        registros = L.asistencia_bloque(s, curso_id, bloque, fecha, perfil["iduser"], token)
        def apellido(alumna_id):
            a = por_id.get(alumna_id, {})
            entero = (a.get("apellido_paterno") or "").strip().title()
            return entero.split(" ")[0] if entero else "(sin nombre)"
        ausentes = sorted(apellido(r["alumno_id"]) for r in registros
                          if r["estado_asistencia"] == AUSENTE)
        atrasadas = sorted(apellido(r["alumno_id"]) for r in registros
                           if r["estado_asistencia"] == ATRASADA)
        return {"curso": jefatura, "total": len(activas),
                "bloque": f"{bloque['inicio']} {(bloque.get('nombreAsignatura') or '')[:18]}",
                "ausentes": ausentes, "atrasadas": atrasadas,
                "presentes": len(activas) - len(ausentes)}
    return {"curso": jefatura, "estado": "ningún bloque cubre al curso completo"}


DIAS_ATRAS = 7          # cuántos días hábiles anteriores se revisan en busca de pendientes


def faltante(b: dict) -> bool:
    """Un bloque propio al que le falta OA, leccionario, asistencia o firma."""
    return not (b.get("val_oa") and b.get("val_leccionario")
                and b.get("val_asistencia") and b.get("val_firma"))


def clave_dia(curso: str, b: dict, dia: datetime.date) -> str:
    """La clave de un bloque de Webclass con su fecha (la de «no hubo esta clase» y la vista previa)."""
    return bu.clave_con_fecha(L.clave_bloque(curso, f"{b['inicio']}-{b['termino']}", b.get("id_bloque_detalle")), dia)


def atrasados(s, token, perfil: dict, hoy: datetime.date, dias: int = DIAS_ATRAS,
              sin_clases: dict | None = None) -> list[dict]:
    """Bloques propios de los últimos días hábiles que quedaron sin registrar o sin firmar.

    Casi no cuesta: Webclass entrega el mes entero por curso y ya está en memoria
    por la revisión de hoy. Devuelve [{fecha, bloques, cursos, claves}] del más reciente al más antiguo.
    Los días y bloques marcados como «no hubo clases» no cuentan (ni gastan uno de los días revisados).
    """
    sin_clases = sin_clases or {}
    resultado, dia, revisados = [], hoy, 0
    while revisados < dias and (hoy - dia).days < dias * 3:
        dia -= datetime.timedelta(days=1)
        if dia.weekday() >= 5 or bu.dia_sin_clases(sin_clases, dia):
            continue
        revisados += 1
        por_curso = L.bloques_de_cursos(s, perfil["curso_ids"], dia, perfil["iduser"], token)
        pendientes = [(c, clave_dia(c, b, dia)) for c, bs in por_curso.items() for b in bs if faltante(b)]
        pendientes = [(c, k) for c, k in pendientes if k not in sin_clases.get("bloques", {})]
        resultado.append({"fecha": dia.strftime("%d/%m/%Y"), "bloques": len(pendientes),
                          "cursos": sorted({c for c, _ in pendientes}), "claves": [k for _, k in pendientes]})
    return [r for r in resultado if r["bloques"]]


def revisar(fecha: datetime.date, nombre_perfil: str = w.PERFIL_POR_DEFECTO) -> dict:
    perfil = w.PERFILES[nombre_perfil]
    sin_clases = bu.leer_sin_clases(rutas.sin_clases(nombre_perfil))
    hoy_sin_clases = bu.dia_sin_clases(sin_clases, fecha)
    s, token = L.sesion_libro(perfil)
    bloques = []
    por_curso = ({} if hoy_sin_clases else
                 L.bloques_de_cursos(s, perfil["curso_ids"], fecha, perfil["iduser"], token))
    for curso, del_curso in por_curso.items():
        for b in del_curso:
            if clave_dia(curso, b, fecha) in sin_clases["bloques"]:
                continue                  # el docente marcó que esa clase no se hizo
            bloques.append({
                "curso": curso,
                # Con el id de detalle cada bloque (y cada taller) tiene su casilla.
                "id": b.get("id_bloque_detalle"),
                "hora": f"{b['inicio']}-{b['termino']}",
                "asignatura": b.get("nombreAsignatura") or "",
                "oa": bool(b["val_oa"]),
                "leccionario": bool(b["val_leccionario"]),
                "asistencia": bool(b["val_asistencia"]),
                "firma": bool(b["val_firma"]),
            })
    bloques.sort(key=lambda x: x["hora"])
    estado = {
        "fecha": fecha.strftime("%d/%m/%Y"),
        "revisado": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "bloques": bloques,
        "sin_firmar": [b for b in bloques if not b["firma"]],
        "sin_registro": [b for b in bloques
                         if not (b["oa"] and b["leccionario"] and b["asistencia"])],
        "jefatura": ({"curso": perfil["jefatura"], "estado": "hoy sin clases"}
                     if hoy_sin_clases and perfil.get("jefatura")
                     else asistencia_jefatura(s, token, fecha, perfil)),
        "atrasados": atrasados(s, token, perfil, fecha, sin_clases=sin_clases),
    }
    if hoy_sin_clases:
        estado["sin_clases"] = True
    return estado


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fecha", metavar="DD/MM/YYYY")
    p.add_argument("--perfil", choices=sorted(w.PERFILES), default=w.PERFIL_POR_DEFECTO)
    p.add_argument("--salida", metavar="RUTA", default=SALIDA,
                   help="Dónde dejar el JSON que lee la barra flotante.")
    args = p.parse_args()
    salida = os.path.abspath(args.salida)
    fecha = (datetime.datetime.strptime(args.fecha, "%d/%m/%Y").date()
             if args.fecha else datetime.date.today())
    # Webclass a veces corta la conexión a media respuesta: se reintenta antes
    # de dar el estado por fallido.
    estado, ultimo_error = None, ""
    for intento in range(3):
        try:
            estado = revisar(fecha, args.perfil)
            break
        except Exception as exc:  # noqa: BLE001
            ultimo_error = str(exc)[:200]
            time.sleep(4 * (intento + 1))
    if estado is None:
        # La barra debe poder distinguir "no pude revisar" de "no hay pendientes".
        estado = {"fecha": fecha.strftime("%d/%m/%Y"),
                  "revisado": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                  "error": ultimo_error}
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=1)
    if sys.stdout:
        if "error" in estado:
            print("ERROR:", estado["error"])
        else:
            print(f"{len(estado['bloques'])} bloques hoy | "
                  f"{len(estado['sin_firmar'])} sin firmar | "
                  f"{len(estado['sin_registro'])} sin registro completo | "
                  f"{sum(a['bloques'] for a in estado['atrasados'])} de días anteriores")


if __name__ == "__main__":
    main()
