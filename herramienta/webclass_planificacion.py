"""
Planificaciones: crear clases en bloque, importarlas desde una planilla y marcar OA/habilidades/DUA.

Sin IA: la barra no escribe el contenido pedagógico; ordena, copia y completa lo que tú le das.
Todo se puede ver antes con --simular (no escribe nada) y con --seleccion se aplican solo las
casillas marcadas.

  planificar --plantilla                             deja una planilla de ejemplo (CSV) para rellenar
  planificar --catalogo --unidad ID                  OA y habilidades de la unidad (solo lectura)
  planificar --esqueleto --unidad ID --desde D --hasta H    una clase vacía por día que tienes clase
  planificar --importar planilla.csv|xlsx --unidad ID       crea las clases de la planilla
  planificar --marcar --unidad ID --clases 1,2 [--oa OA1;OA2] [--hab a;b] [--dua habitual|tic]

Columnas de la planilla: nombre, fecha (DD/MM/AAAA), inicio, desarrollo, cierre, recursos,
adecuaciones, evaluacion, oa (OA1;OA2), habilidades (a;b), dua (habitual|tic|ninguno).
"""

from __future__ import annotations

import argparse
import csv
import datetime
import html
import json
import os
import re
import sys
import unicodedata

import rutas
import webclass_tareas as w

COLUMNAS = ("nombre", "fecha", "inicio", "desarrollo", "cierre", "recursos",
            "adecuaciones", "evaluacion", "oa", "habilidades", "dua")
CAMPOS_TEXTO = ("inicio", "desarrollo", "cierre", "recursos", "adecuaciones", "evaluacion")
EJEMPLO = ("Clase 1: El ciclo del agua", "12/10/2026", "Activar conocimientos previos con una pregunta",
           "Experimento guiado\nRegistro en el cuaderno", "Ticket de salida", "Cuaderno y lápiz", "",
           "Formativa", "OA12", "a;b", "habitual")


# ---------------------------------------------------------------- lógica pura
def normal(texto: str) -> str:
    sin = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in sin if unicodedata.category(c) != "Mn").lower().strip()


def a_html(texto: str) -> str:
    """Texto plano de la planilla a HTML (un párrafo por línea). Si ya es HTML, se respeta."""
    texto = (texto or "").strip()
    if not texto:
        return ""
    if re.search(r"<\s*(p|br|ul|ol|li|div|strong|em|a)\b", texto, re.I):
        return texto
    return "".join(f"<p>{html.escape(linea.strip())}</p>" for linea in texto.splitlines() if linea.strip())


def parsear_fecha(texto) -> datetime.date:
    if isinstance(texto, datetime.datetime):
        return texto.date()
    if isinstance(texto, datetime.date):
        return texto
    return datetime.datetime.strptime(str(texto).strip(), "%d/%m/%Y").date()


def fecha_texto(fecha: datetime.date) -> str:
    return fecha.strftime("%d/%m/%Y")


def separar(texto) -> list[str]:
    return [p.strip() for p in re.split(r"[;,]", str(texto or "")) if p.strip()]


def filas_de_planilla(filas: list[dict]) -> tuple[list[dict], list[str]]:
    """Valida las filas de la planilla. Devuelve (filas limpias, problemas con su número de fila)."""
    limpias, problemas = [], []
    for n, bruta in enumerate(filas, 2):                       # la fila 1 es el encabezado
        fila = {normal(k): v for k, v in bruta.items() if k}
        if not any(str(v or "").strip() for v in fila.values()):
            continue                                           # fila vacía
        nombre = str(fila.get("nombre") or "").strip()
        if not nombre:
            problemas.append(f"fila {n}: falta el nombre de la clase")
            continue
        try:
            fecha = parsear_fecha(fila.get("fecha"))
        except (ValueError, TypeError):
            problemas.append(f"fila {n} ({nombre[:30]}): la fecha debe ser DD/MM/AAAA")
            continue
        limpia = {"nombre": nombre, "fecha": fecha_texto(fecha), "fila": n}
        for campo in CAMPOS_TEXTO:
            limpia[campo] = str(fila.get(campo) or "").strip()
        limpia["oa"] = separar(fila.get("oa"))
        limpia["habilidades"] = separar(fila.get("habilidades"))
        dua = normal(fila.get("dua") or "habitual")
        limpia["dua"] = dua if dua in ("habitual", "tic", "ninguno") else "habitual"
        limpias.append(limpia)
    return limpias, problemas


def etiqueta(texto: str) -> str:
    """«> OA12 Investigar…» -> «OA12»."""
    partes = str(texto).lstrip("> ").split()
    return partes[0] if partes else ""


def resolver_atributos(pedidos: list[str], catalogo: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """Convierte «OA12», «Hab_d» o solo «d» en ids del catálogo de la unidad.

    Cada fila del catálogo empieza con su etiqueta («> OA1 Reconocer…», «> Hab_d Medir…»).
    Se compara la etiqueta completa, nunca por prefijo: «OA1» no puede ser «OA12».
    Devuelve (ids, pedidos que no están en la unidad).
    """
    etiquetas = {}
    for id_, texto in catalogo:
        partes = normal(texto).lstrip("> ").split()
        if partes:
            etiquetas[partes[0]] = id_
    ids, faltan = [], []
    for pedido in pedidos:
        clave = normal(pedido)
        id_ = etiquetas.get(clave) or etiquetas.get(f"hab_{clave}")
        if id_ and id_ not in ids:
            ids.append(id_)
        elif not id_:
            faltan.append(pedido)
    return ids, faltan


def dias_con_clase(bloques_por_dia: dict[datetime.date, list[dict]], asignatura: str) -> list[dict]:
    """Un bloque por día en que el docente tiene esa asignatura (el primero del día).

    Si la asignatura no se conoce se aceptan todos los bloques propios del curso.
    """
    quiero = normal(asignatura)
    dias = []
    for fecha in sorted(bloques_por_dia):
        propios = [b for b in bloques_por_dia[fecha]
                   if not quiero or normal(b.get("nombreAsignatura")) == quiero]
        if propios:
            primero = sorted(propios, key=lambda b: b.get("inicio") or "")[0]
            dias.append({"fecha": fecha, "hora": (primero.get("inicio") or "08:00")[:5],
                         "bloques": len(propios)})
    return dias


def esqueleto(dias: list[dict], existentes: list[dict], prefijo: str = "Clase") -> list[dict]:
    """Clases vacías a crear: los días con clase que la unidad aún no tiene, numeradas a continuación."""
    ocupadas = {c["fechaini"] for c in existentes}
    siguiente = len(existentes) + 1
    nuevas = []
    for d in dias:
        texto = fecha_texto(d["fecha"])
        if texto in ocupadas:
            continue
        nuevas.append({"nombre": f"{prefijo} {siguiente}", "fecha": texto, "hora": d["hora"],
                       "horas": "2" if d["bloques"] > 1 else "1"})
        siguiente += 1
    return nuevas


def leer_planilla(ruta: str) -> list[dict]:
    """Filas de un .csv (UTF-8, separado por ; o ,) o de un .xlsx (primera hoja)."""
    if ruta.lower().endswith((".xlsx", ".xlsm")):
        try:
            import openpyxl
        except ImportError as exc:
            raise RuntimeError("Para leer Excel hace falta instalar openpyxl (pip install openpyxl); "
                               "o guarda la planilla como CSV.") from exc
        hoja = openpyxl.load_workbook(ruta, data_only=True).worksheets[0]
        filas = list(hoja.iter_rows(values_only=True))
        if not filas:
            return []
        encabezado = [str(c or "").strip() for c in filas[0]]
        return [dict(zip(encabezado, fila)) for fila in filas[1:]]
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        muestra = f.read(4096)
        f.seek(0)
        separador = ";" if muestra.count(";") >= muestra.count(",") else ","
        return list(csv.DictReader(f, delimiter=separador))


def escribir_plantilla(ruta: str) -> str:
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.writer(f, delimiter=";")
        escritor.writerow(COLUMNAS)
        escritor.writerow(EJEMPLO)
    return ruta


# ---------------------------------------------------------- consulta a Webclass
def abrir_sesion(perfil_nombre: str):
    perfil = w.PERFILES[perfil_nombre]
    s = w.crear_session()
    w.login(s, perfil["rut"], w.obtener_password(perfil["rut"]))
    w.verificar_sesion(s, perfil_nombre, perfil["iduser"])
    return s, perfil


def unidad_del_perfil(perfil: dict, id_unidad: str) -> dict:
    for u in perfil.get("unidades", []):
        if str(u["id"]) == str(id_unidad):
            return u
    raise ValueError(f"La unidad {id_unidad} no está en tu perfil.")


def catalogos(s, id_unidad: int, id_clase: str) -> tuple[list, list]:
    import webclass_clases as c
    return (c.catalogo(s, id_unidad=id_unidad, idclase=id_clase, tipo="oft"),
            c.catalogo(s, id_unidad=id_unidad, idclase=id_clase, tipo="hab"))


def bloques_del_rango(s, perfil: dict, curso: str, desde: datetime.date, hasta: datetime.date, token: str):
    import webclass_libro as L
    por_dia = {}
    dia = desde
    while dia <= hasta:
        if dia.weekday() < 5:
            propios = L.bloques_del_dia(s, perfil["curso_ids"][curso], dia, perfil["iduser"], token)
            if propios:
                por_dia[dia] = propios
        dia += datetime.timedelta(days=1)
    return por_dia


def dua_de(nombre: str):
    import webclass_clases as c
    return {"habitual": c.DUA_HABITUAL, "tic": c.DUA_CON_TIC}.get(nombre)


# ------------------------------------------------------------------------ main
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--perfil", choices=sorted(w.PERFILES), default=w.PERFIL_POR_DEFECTO)
    p.add_argument("--unidad", help="Id de la unidad (de tu perfil).")
    p.add_argument("--plantilla", action="store_true")
    p.add_argument("--catalogo", action="store_true")
    p.add_argument("--esqueleto", action="store_true")
    p.add_argument("--desde", metavar="DD/MM/AAAA")
    p.add_argument("--hasta", metavar="DD/MM/AAAA")
    p.add_argument("--prefijo", default="Clase")
    p.add_argument("--importar", metavar="PLANILLA")
    p.add_argument("--marcar", action="store_true")
    p.add_argument("--clases", help="Ids de clase separados por coma (para --marcar).")
    p.add_argument("--oa", default="")
    p.add_argument("--hab", default="")
    p.add_argument("--dua", default="habitual", choices=("habitual", "tic", "ninguno"))
    p.add_argument("--simular", action="store_true")
    p.add_argument("--seleccion", metavar="ARCHIVO.json")
    a = p.parse_args()
    nombre = a.perfil
    perfil = w.PERFILES[nombre]

    if a.plantilla:
        ruta = escribir_plantilla(rutas.dato(os.path.join("planificacion", "plantilla_clases.csv")))
        print(f"Plantilla lista: {ruta}")
        print(f"##RUTA {ruta}")
        return
    if not a.unidad:
        raise ValueError("Indica la unidad con --unidad ID.")
    unidad = unidad_del_perfil(perfil, a.unidad)
    id_unidad, curso = int(unidad["id"]), unidad["curso"]
    elegidas = w.leer_seleccion(a.seleccion)
    s, perfil = abrir_sesion(nombre)
    existentes = w.listar_clases(s, id_unidad)
    ref = existentes[0]["idclase"] if existentes else ""
    grupo = f"{curso} · {unidad['nombre'][:40]}"

    if a.catalogo:
        if not ref:
            raise ValueError("La unidad aún no tiene ninguna clase: crea una y vuelve a intentar.")
        oa, hab = catalogos(s, id_unidad, ref)
        for id_, texto in oa:
            w.item(id_, "propuesto", texto[:90], "OBJETIVOS DE APRENDIZAJE", "oa", etiqueta(texto))
        for id_, texto in hab:
            w.item(id_, "propuesto", texto[:90], "HABILIDADES", "habilidad", etiqueta(texto))
        for c in existentes:
            w.item(c["idclase"], "propuesto", c["nombre"], "CLASES", "clase", c["fechaini"])
        print(f"{len(oa)} OA, {len(hab)} habilidades y {len(existentes)} clases en la unidad.")
        return

    import webclass_clases as c
    hechos = 0

    def crear(item_clave, titulo, cuerpo, marcas):
        """Crea una clase (o la simula) y marca OA/habilidades/DUA. Informa un ítem."""
        nonlocal hechos
        detalle = f"{cuerpo['fecha']}"
        if elegidas is not None and item_clave not in elegidas:
            w.item(item_clave, "omitido", titulo, grupo, "clase")
            return
        if a.simular:
            w.item(item_clave, "propuesto", titulo, grupo, "clase", detalle)
            return
        try:
            idclase = c.crear_clase(s, id_unidad=id_unidad, **cuerpo)
            if marcas.get("oa"):
                c.marcar_atributos(s, idclase=idclase, ids=marcas["oa"], tipo="oft")
            if marcas.get("hab"):
                c.marcar_atributos(s, idclase=idclase, ids=marcas["hab"], tipo="hab")
            if marcas.get("dua") is not None:
                c.marcar_dua(s, idclase=idclase, casillas=marcas["dua"])
        except Exception as exc:  # noqa: BLE001
            w.item(item_clave, "error", titulo, grupo, "clase", motivo=str(exc)[:140])
            return
        hechos += 1
        w.item(item_clave, "hecho", titulo, grupo, "clase", detalle)

    if a.esqueleto:
        desde, hasta = parsear_fecha(a.desde), parsear_fecha(a.hasta)
        if hasta < desde:
            raise ValueError("«hasta» es anterior a «desde».")
        import webclass_libro as L
        _s, token = L.sesion_libro(perfil)
        por_dia = bloques_del_rango(_s, perfil, curso, desde, hasta, token)
        dias = dias_con_clase(por_dia, unidad.get("asignatura", ""))
        if not unidad.get("asignatura"):
            print("(La unidad no tiene asignatura anotada: se usan todos tus bloques de ese curso.)")
        nuevas = esqueleto(dias, existentes, a.prefijo)
        ya = len(dias) - len(nuevas)
        print(f"{len(dias)} días con clase entre {a.desde} y {a.hasta}; {ya} ya tienen clase.")
        for n in nuevas:
            cuerpo = {"nombre": n["nombre"], "fecha": n["fecha"], "hora": n["hora"], "horas": n["horas"]}
            crear(n["fecha"], f"{n['nombre']} · {n['fecha']}", cuerpo, {})
        if not nuevas:
            print("No falta crear ninguna clase en ese período.")
    elif a.importar:
        filas, problemas = filas_de_planilla(leer_planilla(a.importar))
        for texto in problemas:
            print(f"  [SALTADA] {texto}")
            w.item(f"fila:{texto.split(':')[0]}", "pendiente", texto.split(":")[0], grupo, "clase",
                   motivo=texto.split(":", 1)[1].strip())
        if not ref and any(f["oa"] or f["habilidades"] for f in filas):
            raise ValueError("La unidad no tiene clases todavía y la planilla pide OA o habilidades: "
                             "crea una clase a mano primero.")
        oa_cat, hab_cat = catalogos(s, id_unidad, ref) if ref else ([], [])
        ocupadas = {(c_["fechaini"], normal(c_["nombre"])) for c_ in existentes}
        for f in filas:
            clave = f"fila:{f['fila']}"
            titulo = f"{f['nombre']} · {f['fecha']}"
            if (f["fecha"], normal(f["nombre"])) in ocupadas:
                w.item(clave, "ya", titulo, grupo, "clase", "ya existe una clase igual en esa fecha")
                continue
            oa, faltan_oa = resolver_atributos(f["oa"], oa_cat)
            hab, faltan_hab = resolver_atributos(f["habilidades"], hab_cat)
            if faltan_oa or faltan_hab:
                w.item(clave, "pendiente", titulo, grupo, "clase",
                       motivo="no encontré en la unidad: " + ", ".join(faltan_oa + faltan_hab))
                continue
            cuerpo = {"nombre": f["nombre"], "fecha": f["fecha"]}
            cuerpo.update({k: a_html(f[k]) for k in CAMPOS_TEXTO})
            crear(clave, titulo, cuerpo, {"oa": oa, "hab": hab, "dua": dua_de(f["dua"])})
    elif a.marcar:
        ids = [i for i in (a.clases or "").split(",") if i.strip()]
        por_id = {c_["idclase"]: c_ for c_ in existentes}
        if not ids:
            raise ValueError("Indica las clases con --clases ID,ID.")
        oa_cat, hab_cat = catalogos(s, id_unidad, ref)
        oa, faltan_oa = resolver_atributos(separar(a.oa), oa_cat)
        hab, faltan_hab = resolver_atributos(separar(a.hab), hab_cat)
        if faltan_oa or faltan_hab:
            raise ValueError("No encontré en la unidad: " + ", ".join(faltan_oa + faltan_hab))
        casillas = dua_de(a.dua)
        for idclase in ids:
            clase = por_id.get(idclase.strip())
            if not clase:
                w.item(idclase, "pendiente", idclase, grupo, "marcas", motivo="la clase no es de esa unidad")
                continue
            titulo = f"{clase['nombre']} · {clase['fechaini']}"
            if elegidas is not None and idclase not in elegidas:
                w.item(idclase, "omitido", titulo, grupo, "marcas")
                continue
            resumen = f"{len(oa)} OA · {len(hab)} habilidades · DUA {a.dua}"
            if a.simular:
                w.item(idclase, "propuesto", titulo, grupo, "marcas", resumen)
                continue
            try:
                if oa:
                    c.marcar_atributos(s, idclase=idclase, ids=oa, tipo="oft")
                if hab:
                    c.marcar_atributos(s, idclase=idclase, ids=hab, tipo="hab")
                if casillas is not None:
                    c.marcar_dua(s, idclase=idclase, casillas=casillas)
            except Exception as exc:  # noqa: BLE001
                w.item(idclase, "error", titulo, grupo, "marcas", motivo=str(exc)[:140])
                continue
            w.item(idclase, "hecho", titulo, grupo, "marcas", resumen)
    else:
        raise ValueError("Indica qué hacer: --esqueleto, --importar, --marcar o --catalogo.")

    if not a.simular:
        # Comprobación: las clases creadas deben aparecer ahora en la unidad.
        if a.esqueleto or a.importar:
            despues = w.listar_clases(s, id_unidad)
            print(f"La unidad pasó de {len(existentes)} a {len(despues)} clases.")
        w.imprimir_resultado(w.ITEMS, vacio="No había nada que hacer.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
