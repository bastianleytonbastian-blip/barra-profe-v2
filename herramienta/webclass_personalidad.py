"""
Informe de personalidad (Libro digital > Informes > Personalidad) desde la barra.

En WebClass es una grilla de alumnas por conductas con un selector diminuto en cada celda: en un curso de 42 alumnas y
31 conductas son 1302 selectores en una página de 6 MB. Aquí se lee entera de una vez para responderla alumna por alumna
en la barra, y al guardar se escribe solo lo que cambió.

  personalidad --curso 5BA [--periodo 2] --salida p.json      lee la encuesta y las observaciones (solo lectura)
  personalidad --datos cambios.json --simular                 muestra qué se guardaría, sin escribir
  personalidad --datos cambios.json [--seleccion s.json]      guarda (solo las alumnas marcadas) y lo comprueba

p.json (lo lee la barra):
  {"curso": "5BA", "curso_id": "237559", "periodo": "2", "periodo_nombre": "Segundo Semestre",
   "periodos": [["1", "Primer Semestre"], ["2", "Segundo Semestre"]], "leido": "DD/MM/AAAA HH:MM",
   "calificadores": [{"id": "1503", "sigla": "D", "nombre": "Desarrollo"}, ...],
   "areas": [{"nombre": "AUTOFORMACIÓN PERSONAL", "conductas": [{"id": "1095767", "numero": 1, "nombre": "..."}]}],
   "alumnas": [{"id": "1234567", "numero": 1, "nombre": "...", "valores": {"1095767": "1503"}, "observacion": "..."}]}
cambios.json (lo escribe la barra):
  {"curso", "curso_id", "periodo", "alumnas": [{"id", "nombre", "valores": {conducta: calificador},
   "observacion": "texto" o null si no cambia}]}
"""

from __future__ import annotations

import argparse
import base64
import datetime
import html
import json
import re
import sys

import barra_utiles as bu
import webclass_tareas as w

CARPETA = f"{w.BASE}/home/informes/conducta/"
# controlador.php también crea, renombra y BORRA conductas y calificadores (casos 2, 4, 5, 11, 13, 14, 15, 16…).
# Solo se permite esto: leer, guardar la calificación de una celda (3) y guardar la observación (9).
LECTURAS = {("filtros.php", 2), ("filtros.php", 3), ("controlador.php", 1), ("controlador.php", 7),
            ("controlador.php", 8), ("controlador.php", 10)}
ESCRITURAS = {("controlador.php", 3), ("controlador.php", 9)}


# ---------------------------------------------------------------- lógica pura
def _texto(fragmento: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragmento)).split())


def _opciones(pagina: str, ident: str) -> list[tuple[str, str]]:
    m = re.search(rf'<select[^>]*id=["\']{ident}["\'][^>]*>(.*?)</select>', pagina, re.S)
    if not m:
        return []
    return [(v, _texto(t)) for v, t in re.findall(r'<option[^>]*value=["\']([^"\']*)["\'][^>]*>(.*?)</option>',
                                                  m.group(1), re.S)]


def parsear_ocultos(pagina: str) -> dict[str, str]:
    """El colegio y el año que la página del informe manda en sus filtros."""
    return dict(re.findall(r"id=['\"](colegio|anio)['\"][^>]*value=['\"]([^'\"]*)", pagina))


def mismo_texto(a: str, b: str) -> bool:
    """WebClass puede devolver otros saltos de línea o espacios: eso no es un cambio."""
    return " ".join((a or "").split()) == " ".join((b or "").split())


def parsear_cursos(pagina: str) -> dict[str, str]:
    """{nombre: id} del selector de cursos (sin «--», que vale -1)."""
    return {t: v for v, t in _opciones(pagina, "ComboCurso") if v.isdigit()}


def parsear_periodos(pagina: str) -> list[tuple[str, str]]:
    return [(v, t) for v, t in _opciones(pagina, "ComboPeriodo") if v]


def periodo_por_fecha(periodos: list[tuple[str, str]], hoy: datetime.date) -> str:
    """El periodo que probablemente se está evaluando: el año escolar (marzo a diciembre) repartido en partes iguales."""
    if not periodos:
        return ""
    indice = (hoy.month - 3) * len(periodos) // 10
    return periodos[max(0, min(len(periodos) - 1, indice))][0]


def parsear_areas(pagina: str) -> list[dict]:
    """La lista de ítems (caso=7): las áreas en orden, con los números de sus conductas (C1, C2…)."""
    areas: list[dict] = []
    for area, numero in re.findall(r"<th[^>]*>\s*<strong>(.*?)</strong>|<strong>\s*C\s*(\d+)\s*\.?-", pagina, re.S):
        if area:
            areas.append({"nombre": _texto(area), "numeros": []})
        elif areas:
            areas[-1]["numeros"].append(int(numero))
    return areas


def parsear_tabla(pagina: str) -> dict:
    """La grilla (caso=1): conductas en orden, calificadores y, por alumna, su valor y el vínculo de cada celda.

    El vínculo es lo que WebClass pide para guardar una celda. ValueError si no es la grilla (sesión vencida, error).
    """
    thead = re.search(r"<thead.*?</thead>", pagina, re.S)
    if not thead:
        raise ValueError("WebClass no entregó la tabla de personalidad.")
    conductas = []
    for th in re.findall(r"<th[^>]*>.*?</th>", thead.group(0), re.S):
        ident = re.search(r"editarNombreConducta\((\d+)\)", th)
        numero = re.search(r"<strong[^>]*>\s*C\s*(\d+)\s*</strong>", th)
        nombre = re.search(r'id=["\']Conducta_\d+["\'][^>]*value=["\']([^"\']*)', th)
        if ident:
            conductas.append({"id": ident.group(1), "numero": int(numero.group(1)) if numero else len(conductas) + 1,
                              "nombre": html.unescape(nombre.group(1)).strip() if nombre else ""})
    calificadores: list[tuple[str, str]] = []
    alumnas = []
    for fila in re.split(r'(?=<tr id="cuerpo_tabla_\d+")', pagina)[1:]:
        # El nombre es el enlace que abre la observación (con tamano_nombre alto, viene completo).
        ident = re.search(r'onclick="cargarObservacion\((\d+),\s*\d+\);"\s*>(.*?)</a>', fila, re.S)
        if not ident:
            continue
        numero = re.search(r'class="td-numero"[^>]*>\s*(\d+)', fila)
        valores, vinculos = {}, {}
        for conducta, vinculo, opciones in re.findall(
                r'<select[^>]*id="Combo_F\d+C(\d+)"[^>]*onchange="editarConductaAlumno\(\d+,\s*\d+,\s*(\d+)\)'
                r'[^>]*>(.*?)</select>', fila, re.S):
            elegida = re.search(r'<option[^>]*value="(\d+)"[^>]*selected|<option[^>]*selected[^>]*value="(\d+)"', opciones)
            valores[conducta] = (elegida.group(1) or elegida.group(2)) if elegida else ""
            vinculos[conducta] = vinculo
            if not calificadores:
                calificadores = [(v, _texto(t)) for v, t in re.findall(r'<option[^>]*value="(\d+)"[^>]*>(.*?)</option>',
                                                                       opciones, re.S)]
        nombre = _texto(ident.group(2))
        alumnas.append({"id": ident.group(1), "numero": int(numero.group(1)) if numero else len(alumnas) + 1,
                        "nombre": nombre.title() if nombre.isupper() else nombre, "valores": valores,
                        "vinculos": vinculos})
    return {"conductas": conductas, "calificadores": calificadores, "alumnas": alumnas}


def parsear_nombres_calificadores(pagina: str) -> dict[str, str]:
    """{sigla: nombre} de los calificadores del colegio (caso=10): «D» -> «Desarrollo»."""
    nombres = dict(re.findall(r'id=["\']enombcal_(\d+)["\'][^>]*value=["\']([^"\']*)', pagina))
    siglas = dict(re.findall(r'id=["\']enomccal_(\d+)["\'][^>]*value=["\']([^"\']*)', pagina))
    return {html.unescape(siglas[n]).strip(): html.unescape(nombres[n]).strip().capitalize()
            for n in nombres if n in siglas}


def parsear_observacion(pagina: str) -> dict:
    """La observación de una alumna en el periodo (caso=8): {"id": "0" si no tiene, "texto"}."""
    texto = re.search(r'<textarea[^>]*id="observacion"[^>]*>(.*?)</textarea>', pagina, re.S)
    ident = re.search(r"guardarObservacion\((\d+)\s*,", pagina)
    if texto is None or ident is None:
        raise ValueError("WebClass no entregó la observación.")
    return {"id": ident.group(1), "texto": html.unescape(texto.group(1)).strip()}


def armar_encuesta(tabla: dict, areas: list[dict], nombres: dict[str, str]) -> dict:
    """Lo que necesita la barra: conductas agrupadas por área, calificadores con nombre y los valores de cada alumna."""
    por_numero = {c["numero"]: c for c in tabla["conductas"]}
    agrupadas, usadas = [], set()
    for area in areas:
        conductas = [por_numero[n] for n in area["numeros"] if n in por_numero]
        usadas |= {c["id"] for c in conductas}
        if conductas:
            agrupadas.append({"nombre": area["nombre"], "conductas": conductas})
    sueltas = [c for c in tabla["conductas"] if c["id"] not in usadas]
    if sueltas:                       # una conducta nueva que la lista de ítems todavía no trae: que no se pierda
        agrupadas.append({"nombre": "OTRAS CONDUCTAS", "conductas": sueltas})
    return {"calificadores": [{"id": v, "sigla": s, "nombre": nombres.get(s, s)} for v, s in tabla["calificadores"]],
            "areas": agrupadas,
            "alumnas": [{k: a[k] for k in ("id", "numero", "nombre", "valores")} for a in tabla["alumnas"]]}


def celdas_a_cambiar(actual: dict, pedidos: dict[str, str], validos: set[str]) -> list[tuple[str, str, str]]:
    """[(conducta, vínculo, calificador)] de lo que pide la barra y todavía no está así en WebClass."""
    return [(c, actual["vinculos"][c], v) for c, v in pedidos.items()
            if v in validos and c in actual["vinculos"] and actual["valores"].get(c) != v]


def describir(celdas: list[tuple[str, str, str]], numeros: dict[str, int], siglas: dict[str, str],
              observacion: bool) -> str:
    """«3 conductas (C2 E/D, C7 N/D, C15 E/D) y la observación»."""
    partes = []
    if celdas:
        detalle = ", ".join(f"C{numeros.get(c, '?')} {siglas.get(v, v)}"
                            for c, _v, v in sorted(celdas, key=lambda x: numeros.get(x[0], 0)))
        partes.append(f"{len(celdas)} conducta{'s' if len(celdas) != 1 else ''} ({detalle})")
    if observacion:
        partes.append("la observación")
    return " y ".join(partes)


# ---------------------------------------------------------- consulta a Webclass
def pedir(s, archivo: str, datos: dict, escribir: bool = False) -> str:
    """Un POST a la carpeta del informe, solo si es una lectura (o una de las dos escrituras permitidas)."""
    permitidos = LECTURAS | ESCRITURAS if escribir else LECTURAS
    if (archivo, datos.get("caso")) not in permitidos:
        raise ValueError(f"Pedido no permitido a WebClass: {archivo} caso={datos.get('caso')}")
    r = s.post(CARPETA + archivo, data=datos, headers=w.HEADERS, timeout=120)
    r.raise_for_status()
    return r.text


def abrir_sesion(perfil_nombre: str, curso_id: str):
    """(sesión, perfil, {colegio, anio}). Entrar a la página del informe, como el navegador, deja lista la sesión."""
    perfil = w.PERFILES[perfil_nombre]
    s = w.crear_session()
    w.login(s, perfil["rut"], w.obtener_password(perfil["rut"]))
    w.verificar_sesion(s, perfil_nombre, perfil["iduser"])
    r = s.get(CARPETA + "index.php", params={"c": base64.b64encode(str(curso_id).encode()).decode()},
              headers=w.HEADERS, timeout=60)
    return s, perfil, parsear_ocultos(r.text)


def id_del_curso(s, perfil: dict, filtros: dict, curso: str) -> str:
    cursos = parsear_cursos(pedir(s, "filtros.php", {"caso": 2, "accion": 1, "colegio": filtros.get("colegio", ""),
                                                     "anio": filtros.get("anio") or datetime.date.today().year}))
    ident = cursos.get(curso) or str(perfil.get("curso_ids", {}).get(curso) or "")
    if not ident:
        raise ValueError(f"No encontré el curso «{curso}» en el informe de personalidad.")
    return ident


def leer_tabla(s, curso_id: str, periodo: str) -> dict:
    return parsear_tabla(pedir(s, "controlador.php", {"caso": 1, "accion": 1, "tamano_nombre": 120,
                                                      "curso": curso_id, "periodo": periodo}))


def leer_observacion(s, alumna: str, periodo: str) -> dict:
    return parsear_observacion(pedir(s, "controlador.php", {"caso": 8, "accion": 8, "periodo": periodo, "alumno": alumna}))


def leer(perfil_nombre: str, curso: str, periodo: str | None) -> dict:
    """Todo lo de un curso y periodo, para responderlo en la barra (solo lectura)."""
    s, perfil, filtros = abrir_sesion(perfil_nombre, w.PERFILES[perfil_nombre].get("curso_ids", {}).get(curso, ""))
    curso_id = id_del_curso(s, perfil, filtros, curso)
    periodos = parsear_periodos(pedir(s, "filtros.php", {"caso": 3, "accion": 1, "curso": curso_id}))
    if not periodos:
        raise ValueError(f"El curso {curso} no tiene periodos para el informe de personalidad.")
    if periodo not in dict(periodos):
        periodo = periodo_por_fecha(periodos, datetime.date.today())
    tabla = leer_tabla(s, curso_id, periodo)
    areas = parsear_areas(pedir(s, "controlador.php", {"caso": 7, "curso": curso_id}))
    nombres = parsear_nombres_calificadores(pedir(s, "controlador.php", {"caso": 10}))
    encuesta = armar_encuesta(tabla, areas, nombres)
    for n, alumna in enumerate(encuesta["alumnas"], 1):
        print(f"##PROGRESO {n - 1}/{len(encuesta['alumnas'])} observaciones", flush=True)
        alumna["observacion"] = leer_observacion(s, alumna["id"], periodo)["texto"]
    return {"curso": curso, "curso_id": curso_id, "periodo": periodo, "periodo_nombre": dict(periodos)[periodo],
            "periodos": periodos, "leido": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"), **encuesta}


def guardar(perfil_nombre: str, datos: dict, simular: bool, elegidas: set[str] | None) -> None:
    """Escribe en WebClass lo que cambió, alumna por alumna, y después lo vuelve a leer para comprobarlo."""
    curso, periodo = datos["curso"], str(datos["periodo"])
    s, _perfil, _filtros = abrir_sesion(perfil_nombre, datos["curso_id"])
    tabla = leer_tabla(s, datos["curso_id"], periodo)
    actuales = {a["id"]: a for a in tabla["alumnas"]}
    numeros = {c["id"]: c["numero"] for c in tabla["conductas"]}
    siglas = dict(tabla["calificadores"])
    pendientes: dict[str, tuple] = {}
    total = len(datos["alumnas"])
    for n, pedida in enumerate(datos["alumnas"], 1):
        ident, titulo = str(pedida["id"]), f"{curso} · {pedida.get('nombre') or pedida['id']}"
        actual = actuales.get(ident)
        if actual is None:
            w.item(ident, "pendiente", titulo, curso, "alumna", motivo="ya no está en la lista del curso en WebClass")
            continue
        celdas = celdas_a_cambiar(actual, pedida.get("valores") or {}, set(siglas))
        observacion = (pedida.get("observacion") or "").strip()      # WebClass no deja guardarla vacía
        previa = leer_observacion(s, ident, periodo) if observacion else None
        if previa and mismo_texto(previa["texto"], observacion):
            observacion = ""
        resumen = describir(celdas, numeros, siglas, bool(observacion))
        if not resumen:
            w.item(ident, "ya", titulo, curso, "alumna", "ya estaba así en WebClass")
            continue
        if elegidas is not None and ident not in elegidas:
            w.item(ident, "omitido", titulo, curso, "alumna", resumen)
            continue
        print(f"##PROGRESO {n - 1}/{total} {curso}", flush=True)
        if simular:
            w.item(ident, "propuesto", titulo, curso, "alumna", resumen)
            continue
        try:
            for _conducta, vinculo, calificador in celdas:
                pedir(s, "controlador.php", {"caso": 3, "accion": 1, "calificacion": calificador, "idVinculo": vinculo},
                      escribir=True)
            if observacion:
                pedir(s, "controlador.php", {"caso": 9, "periodo": periodo, "alumno": ident,
                                             "idobservacion": previa["id"], "observacion": observacion}, escribir=True)
        except Exception as exc:  # noqa: BLE001
            w.item(ident, "error", titulo, curso, "alumna", resumen, motivo=str(exc)[:120])
            continue
        pendientes[ident] = (celdas, observacion, titulo, resumen)
    print(f"##PROGRESO {total}/{total} {curso}", flush=True)
    if simular:
        return
    if pendientes:                         # comprobar: se vuelve a leer lo que quedó en WebClass
        despues = {a["id"]: a for a in leer_tabla(s, datos["curso_id"], periodo)["alumnas"]}
        for ident, (celdas, observacion, titulo, resumen) in pendientes.items():
            fallan = [c for c, _v, valor in celdas if despues.get(ident, {}).get("valores", {}).get(c) != valor]
            if observacion and not mismo_texto(leer_observacion(s, ident, periodo)["texto"], observacion):
                fallan.append("observación")
            if fallan:
                w.item(ident, "pendiente", titulo, curso, "alumna", resumen,
                       motivo=f"WebClass no muestra {len(fallan)} de los cambios: vuelve a intentarlo")
            else:
                w.item(ident, "hecho", titulo, curso, "alumna", resumen)
    w.imprimir_resultado(w.ITEMS, vacio="No había cambios que guardar.")


# ------------------------------------------------------------------------ main
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--perfil", choices=sorted(w.PERFILES), default=w.PERFIL_POR_DEFECTO)
    p.add_argument("--curso", help="Curso (5BA) que se lee.")
    p.add_argument("--periodo", help="Periodo (el número de WebClass: 1, 2…). Sin él, el de la fecha.")
    p.add_argument("--salida", metavar="p.json", help="Dónde deja lo leído.")
    p.add_argument("--datos", metavar="cambios.json", help="Lo que se guarda.")
    p.add_argument("--simular", action="store_true", help="Muestra qué se guardaría.")
    p.add_argument("--seleccion", metavar="ARCHIVO.json", help="Solo las alumnas marcadas.")
    args = p.parse_args()
    if args.datos:
        with open(args.datos, encoding="utf-8") as f:
            datos = json.load(f)
        guardar(args.perfil, datos, args.simular, w.leer_seleccion(args.seleccion))
        return
    if not (args.curso and args.salida):
        raise ValueError("Indica --curso y --salida para leer, o --datos para guardar.")
    encuesta = leer(args.perfil, args.curso.upper(), args.periodo)
    bu.escribir_atomico(args.salida, json.dumps(encuesta, ensure_ascii=False))
    print(f"{len(encuesta['alumnas'])} alumnas y {sum(len(a['conductas']) for a in encuesta['areas'])} conductas en "
          f"{encuesta['curso']}, {encuesta['periodo_nombre']}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
