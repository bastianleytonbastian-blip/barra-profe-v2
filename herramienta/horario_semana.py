"""
Arma tu horario semanal de clases y lo deja en un JSON para la barra.

Solo lee: recorre los bloques de la semana en cada curso y se queda con los
que dictas tú, con su hora de entrada y salida. No escribe nada en Webclass.

Uso:
  pythonw horario_semana.py           semana actual
  python  horario_semana.py --ver     además lo imprime en pantalla
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time

import rutas
import webclass_libro as L
import webclass_tareas as w

SALIDA = rutas.dato("horario_semana.json")
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def semana_de(fecha: datetime.date) -> list[datetime.date]:
    lunes = fecha - datetime.timedelta(days=fecha.weekday())
    return [lunes + datetime.timedelta(days=n) for n in range(5)]


def armar(fecha: datetime.date, nombre_perfil: str = w.PERFIL_POR_DEFECTO) -> dict:
    perfil = w.PERFILES[nombre_perfil]
    s, token = L.sesion_libro(perfil)
    dias = semana_de(fecha)
    bloques: list[dict] = []
    # La semana puede caer entre dos meses (ej. 28/09 al 02/10): se piden ambos.
    meses = sorted({(d.year, d.month) for d in dias})
    for curso, curso_id in perfil["curso_ids"].items():
        del_curso = []
        for anio, mes in meses:
            datos = L.api_get(s, "getBlocksByCourseID",
                              {"courseID": curso_id, "anio": anio,
                               "mes": f"{mes:02d}", "courseVisible": 1}, token)
            # Los talleres vienen dentro del bloque que los agrupa: si no se
            # abren, las horas de taller no aparecen nunca en el horario.
            for b in datos.get("bloques", []):
                del_curso += L.abrir_electivos(b)
        for b in del_curso:
            if str(b.get("profesor_id")) != str(perfil["iduser"]):
                continue
            try:
                dia = datetime.date.fromisoformat(b["fecha"])
            except (KeyError, ValueError):
                continue
            if dia not in dias:
                continue
            asignatura = b.get("nombreAsignatura") or ""
            if b.get("es_electivo"):
                asignatura = b.get("electivo_nombre") or asignatura
            bloques.append({"dia": dia.weekday(), "inicio": b.get("inicio"),
                            "fin": b.get("termino"), "curso": curso,
                            "asignatura": asignatura})
    # Una misma clase puede repetirse en la semana; se deja una por celda.
    unicos = {(b["dia"], b["inicio"], b["curso"]): b for b in bloques}
    orden = sorted(unicos.values(), key=lambda b: (b["dia"], b["inicio"] or ""))
    return {"semana": f"{dias[0]:%d/%m} al {dias[-1]:%d/%m/%Y}",
            "generado": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "bloques": orden}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fecha", metavar="DD/MM/YYYY")
    p.add_argument("--ver", action="store_true", help="imprime el horario en pantalla")
    p.add_argument("--perfil", choices=sorted(w.PERFILES), default=w.PERFIL_POR_DEFECTO)
    p.add_argument("--salida", metavar="RUTA", default=SALIDA,
                   help="Dónde dejar el JSON que lee la barra flotante.")
    args = p.parse_args()
    salida = os.path.abspath(args.salida)
    fecha = (datetime.datetime.strptime(args.fecha, "%d/%m/%Y").date()
             if args.fecha else datetime.date.today())

    horario, ultimo_error = None, ""
    for intento in range(3):
        try:
            horario = armar(fecha, args.perfil)
            break
        except Exception as exc:  # noqa: BLE001
            ultimo_error = str(exc)[:200]
            time.sleep(4 * (intento + 1))
    if horario is None:
        horario = {"semana": "", "generado": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                   "error": ultimo_error, "bloques": []}

    os.makedirs(os.path.dirname(salida), exist_ok=True)
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(horario, f, ensure_ascii=False, indent=1)

    if sys.stdout and (args.ver or "error" in horario):
        if "error" in horario:
            print("ERROR:", horario["error"])
            return
        print(f"Semana {horario['semana']}")
        for dia in range(5):
            del_dia = [b for b in horario["bloques"] if b["dia"] == dia]
            if del_dia:
                print(f"\n{DIAS[dia].capitalize()}")
                for b in del_dia:
                    print(f"  {b['inicio']}-{b['fin']}  {b['curso']}  {b['asignatura'][:22]}")


if __name__ == "__main__":
    main()
