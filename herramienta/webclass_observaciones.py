"""
Observaciones de estudiantes (Libro digital > Observaciones) desde la barra.

Una misma observación para varias alumnas, con vista previa y casillas. Cada alumna
recibe su propia observación, así el informe dice cuáles se guardaron y cuáles no.

  observar --curso 5BA --formulario            lista alumnas y asignaturas del curso (solo lectura)
  observar --datos obs.json --simular          muestra qué se guardaría, sin escribir
  observar --datos obs.json [--seleccion s.json]   guarda (solo las alumnas marcadas)
  observar --cursos                            lista los cursos del colegio (solo lectura)
  observar --vigilar 5BA,6BB --salida v.json   busca observaciones nuevas en esos cursos (solo lectura)

obs.json: {"curso": "5BA", "alumnas": ["6042943", ...], "tipo": 1|2|3, "fecha": "DD/MM/AAAA",
           "texto": "...", "asignatura": "-172", "visible": "equipo" | "todos"}
tipo: 1 positiva, 2 negativa, 3 neutra.

v.json (lo escribe --vigilar y lo lee la barra):
  {"revisado": "DD/MM/AAAA HH:MM", "error": "", "cursos": {"5BA": {"id": 237559, "total": 118, "vistas": ["5550001", ...]}},
   "nuevas": [{"id": "obs-5550001", "curso", "tipo", "alumnas": [...], "profesor", "asignatura", "fecha", "texto", "creado"}]}
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import re
import sys
import unicodedata

import barra_utiles as bu
import webclass_tareas as w

URL = f"{w.BASE}/home/anotaciones/controlador/controladorNew_Edit.php"
# Aquí vive la lista. OJO: este mismo archivo BORRA con caso=4; solo se usan caso=2 (lista) y caso=5 (cursos).
URL_LISTA = f"{w.BASE}/home/anotaciones/controlador/controlador.php"
TIPOS = {1: "positiva", 2: "negativa", 3: "neutra"}
# Valor de cada casilla «visible para» del formulario (visto_N). Alumno y apoderado:
ROLES_FAMILIA = {"31", "21"}
LARGO_MAXIMO = 1500
MAX_PAGINAS = 100          # la lista va de a 15: alcanza para 1500 observaciones de un curso
MAX_NUEVAS = 50            # cuántas observaciones nuevas se guardan para mostrar (las más viejas se olvidan)


# ---------------------------------------------------------------- lógica pura
def _texto(fragmento: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragmento)).split())


def _norma(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn").strip()


def parsear_formulario(pagina: str) -> dict:
    """Del HTML del formulario: asignaturas, alumnas, roles y fecha por defecto."""
    def opciones(id_select: str) -> list[tuple[str, str]]:
        m = re.search(rf'<select[^>]*id="{id_select}"[^>]*>(.*?)</select>', pagina, re.S)
        if not m:
            return []
        return [(v, _texto(t)) for v, t in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>',
                                                      m.group(1), re.S)]
    alumnas = [(v, t) for v, t in opciones("combo_alumnos") if v.isdigit() and int(v) > 0]
    asignaturas = [(v, t) for v, t in opciones("combo_asignatura") if t]
    roles = re.findall(r'id="visto_(\d+)"[^>]*value="(\d+)"', pagina)
    fecha = re.search(r'id="fechaanot"[^>]*value=[\'"](\d{4}-\d\d-\d\d)', pagina)
    return {"alumnas": alumnas, "asignaturas": asignaturas, "roles": roles,
            "fecha": fecha.group(1) if fecha else ""}


def valores_visibles(roles: list[tuple[str, str]], visible: str) -> str:
    """«31;21;…;» con los roles que verán la observación. «equipo» deja fuera a familia."""
    valores = [v for _n, v in roles]
    if visible != "todos":
        valores = [v for v in valores if v not in ROLES_FAMILIA]
    return "".join(f"{v};" for v in valores)


def validar(datos: dict) -> list[str]:
    """Problemas de la observación; vacío si se puede guardar."""
    problemas = []
    if int(datos.get("tipo", -1)) not in TIPOS:
        problemas.append("falta el tipo (positiva, negativa o neutra)")
    if not (datos.get("texto") or "").strip():
        problemas.append("falta la descripción")
    elif len(datos["texto"]) > LARGO_MAXIMO:
        problemas.append(f"la descripción pasa de {LARGO_MAXIMO} letras")
    if not datos.get("alumnas"):
        problemas.append("no hay alumnas elegidas")
    if not datos.get("asignatura"):
        problemas.append("falta la asignatura")
    try:
        parsear_fecha(datos.get("fecha", ""))
    except ValueError:
        problemas.append("la fecha no es válida (DD/MM/AAAA)")
    return problemas


def parsear_fecha(texto: str) -> datetime.date:
    return datetime.datetime.strptime(texto.strip(), "%d/%m/%Y").date()


def asignatura_probable(asignaturas: list[tuple[str, str]], conocidas: set[str]) -> str:
    """El valor de la asignatura del docente si coincide con alguna de las suyas, o vacío."""
    mias = {_norma(c) for c in conocidas}
    for valor, texto in asignaturas:
        if _norma(texto) in mias:
            return valor
    return ""


def cuerpo_de_envio(datos: dict, alumna: str, curso_id: int, periodo: str,
                    profesor: str, visibles: str) -> dict:
    """Los campos que manda el botón Guardar (GuardarLaAnotacion) para UNA alumna."""
    return {"caso": 2, "accion": 1, "seleccionados": f"{alumna}::", "solo_curso": 0,
            "tipo_anot": datos["tipo"], "anotacion_tipo": datos["tipo"], "id_relacion": "null",
            "fecha_anot": parsear_fecha(datos["fecha"]).strftime("%Y-%m-%d"),
            "anotacion": datos["texto"].strip(), "verSolo": visibles, "curso": curso_id,
            "sector": datos["asignatura"], "t_periodo": periodo, "profesor": profesor}


def _celda(fila: str, columna: int) -> str:
    """El texto de una columna de la lista. Se lee el span: el atributo title puede traer comillas sin escapar."""
    m = re.search(rf'col-obs-{columna}".*?<span class="i-label-clear">(.*?)</span>', fila, re.S)
    return _texto(m.group(1)) if m else ""


def parsear_lista(pagina: str) -> tuple[list[dict], int]:
    """Una página de la lista de observaciones de un curso: sus filas y el total del curso.

    ValueError si no es la lista (sesión vencida, página de error): así no se toma por «no hay observaciones».
    """
    total = re.search(r'value="(\d+)"[^>]*id="totalObs"', pagina)
    if not total:
        raise ValueError("Webclass no entregó la lista de observaciones.")
    filas = []
    for trozo in re.split(r'(?=<div class="i-row i-center i-table-body)', pagina)[1:]:
        accion = re.search(r"(?:imprimirObservacion|EditarAnotacion|BorrarAnotacion)\((\d+)", trozo)
        numero = _celda(trozo, 1)
        if not accion and not numero:
            continue                    # el pie con el paginador tiene la misma clase, pero no es una fila
        tipo = re.search(r'col-obs-5"[^>]*title="([^"]*)"', trozo)
        filas.append({"id": accion.group(1) if accion else f"n{numero}", "asignatura": _celda(trozo, 2),
                      "profesor": _celda(trozo, 3).title(), "alumna": _celda(trozo, 4).title(),
                      "tipo": tipo.group(1) if tipo else "", "fecha": _celda(trozo, 6), "texto": _celda(trozo, 8)})
    return filas, int(total.group(1))


def parsear_cursos(pagina: str) -> dict[str, int]:
    """Los cursos del selector de la página: {nombre: id}, sin «Todos» (que vale -1)."""
    return {_texto(t): int(v) for v, t in re.findall(r'<option[^>]*value="(\d+)"[^>]*>(.*?)</option>', pagina, re.S)}


def es_propia(fila: dict, nombre_docente: str) -> bool:
    """¿La registró este docente? La lista trae el nombre del profesor, no su id (si no calza, se avisa igual)."""
    autor, mias = _norma(fila["profesor"]).split(), _norma(nombre_docente).split()
    return bool(autor) and all(p in mias for p in autor)


def agrupar(filas: list[dict], ahora: datetime.datetime) -> list[dict]:
    """Webclass guarda una observación por alumna: la misma para varias se avisa una sola vez."""
    grupos: dict = {}
    for f in filas:
        llave = (f["curso"], f["tipo"], f["fecha"], f["profesor"], f["asignatura"], f["texto"])
        grupo = grupos.setdefault(llave, {"id": f"obs-{f['id']}", "curso": f["curso"], "tipo": f["tipo"], "alumnas": [],
                                          "profesor": f["profesor"], "asignatura": f["asignatura"], "fecha": f["fecha"],
                                          "texto": f["texto"], "creado": f"{ahora:%Y-%m-%d %H:%M}"})
        grupo["alumnas"].append(f["alumna"])
    return list(grupos.values())


# ---------------------------------------------------------- consulta a Webclass
def abrir_sesion(perfil_nombre: str):
    perfil = w.PERFILES[perfil_nombre]
    s = w.crear_session()
    w.login(s, perfil["rut"], w.obtener_password(perfil["rut"]))
    w.verificar_sesion(s, perfil_nombre, perfil["iduser"])
    return s, perfil


def leer_formulario(s, curso_id: int) -> dict:
    r = s.post(URL, data={"caso": 1, "accion": 1, "curso": curso_id, "alumno": ""},
               headers=w.HEADERS, timeout=60)
    r.raise_for_status()
    return parsear_formulario(r.text)


def periodo_de_pagina(s, curso_id: int) -> str:
    """El valor t_periodo que la página de observaciones envía al guardar (por defecto «1»)."""
    import base64
    clave = base64.b64encode(str(curso_id).encode()).decode()
    try:
        r = s.get(f"{w.BASE}/home/anotaciones/index.php", params={"curso": clave},
                  headers=w.HEADERS, timeout=60)
        m = re.search(r'id="t_periodo"[^>]*value="([^"]*)"', r.text)
        return m.group(1) if m else "1"
    except Exception:  # noqa: BLE001
        return "1"


def guardar_una(s, cuerpo: dict) -> int:
    """Envía una observación. Devuelve el número que responde Webclass (>0 = guardada)."""
    r = s.post(URL, data=cuerpo, headers=w.HEADERS, timeout=60)
    r.raise_for_status()
    m = re.match(r"\s*(\d+)\s*$", r.text)
    return int(m.group(1)) if m else 0


def leer_cursos(s) -> dict[str, int]:
    """Todos los cursos del año que el colegio deja ver a este docente, no solo los que tiene en su perfil."""
    r = s.post(URL_LISTA, data={"caso": 5, "accion": 2, "anio": -1, "tab": 1}, headers=w.HEADERS, timeout=60)
    r.raise_for_status()
    return parsear_cursos(r.text)


def leer_lista(s, curso_id: int, pagina: int = 0) -> tuple[list[dict], int]:
    """Una página de las observaciones del curso, este año (anio=-1) y de todas las alumnas (student=-1)."""
    r = s.post(URL_LISTA, data={"caso": 2, "accion": 1, "curso": curso_id, "anio": -1, "correlativo": -1,
                                "student": -1, "pagFin": pagina}, headers=w.HEADERS, timeout=60)
    r.raise_for_status()
    return parsear_lista(r.text)


def revisar_curso(s, curso_id: int, previo: dict | None) -> tuple[dict, list[dict]]:
    """(lo que queda anotado del curso, filas nuevas). `previo` es lo anotado la vez pasada (None: es la primera vez).

    La lista va ordenada por la fecha de la observación, no por cuándo se registró: una con fecha atrasada no sale en la
    primera página. Por eso, si cambió algo, se lee entera. Si no, basta una consulta.
    Lo visto solo crece: si Webclass entregara una lista vacía por un rato, al volver no salta todo como nuevo.
    """
    filas, total = leer_lista(s, curso_id)
    vistas = set(previo.get("vistas") or []) if previo else set()
    if previo and total == previo.get("total") and all(f["id"] in vistas for f in filas):
        return previo, []
    for pagina in range(1, MAX_PAGINAS):
        if len(filas) >= total:
            break
        mas, _total = leer_lista(s, curso_id, pagina)
        if not mas:
            break
        filas += mas
    # Si alguien registra mientras se lee, una fila se corre de página y sale repetida: se cuentan las distintas.
    por_id = {f["id"]: f for f in filas}
    nuevas = [f for i, f in por_id.items() if i not in vistas] if previo else []
    return {"id": curso_id, "total": len(por_id), "vistas": sorted(vistas | set(por_id))}, nuevas


def vigilar(s, cursos: list[str], ids: dict[str, int], estado: dict, nombre_docente: str,
            ahora: datetime.datetime) -> dict:
    """El estado al día: lo visto de cada curso y, sumado a lo que ya había, lo nuevo que registraron otros.

    Un curso recién elegido solo se anota, sin avisar de lo que ya tenía. Lo mismo un curso que cambió de id (año nuevo).
    Los que ya no se vigilan salen del estado: si se vuelven a elegir, parten de cero.
    """
    anotados = estado.get("cursos") or {}
    al_dia, filas, faltan = {}, [], []
    for curso in cursos:
        if curso not in ids:
            faltan.append(curso)
            continue
        previo = anotados.get(curso)
        previo = previo if isinstance(previo, dict) and previo.get("id") == ids[curso] else None
        al_dia[curso], nuevas = revisar_curso(s, ids[curso], previo)
        filas += [{**f, "curso": curso} for f in nuevas if not es_propia(f, nombre_docente)]
    return {"revisado": f"{ahora:%d/%m/%Y %H:%M}", "error": f"No encontré {', '.join(faltan)} en Webclass." if faltan else "",
            "cursos": al_dia, "nuevas": ((estado.get("nuevas") or []) + agrupar(filas, ahora))[-MAX_NUEVAS:]}


def vigilar_y_guardar(nombre: str, cursos: list[str], salida: str) -> dict:
    """Corre vigilar() y deja el resultado en `salida`. Si falla, lo ya anotado queda igual: se reintenta la próxima vez."""
    estado = bu.leer_json(salida)
    ahora = datetime.datetime.now()
    try:
        s, perfil = abrir_sesion(nombre)
        ids = {**perfil.get("curso_ids", {}), **leer_cursos(s)}
        nuevo = vigilar(s, cursos, ids, estado, perfil.get("nombre") or "", ahora)
    except Exception as exc:  # noqa: BLE001
        nuevo = {**estado, "revisado": f"{ahora:%d/%m/%Y %H:%M}", "error": str(exc)[:200]}
    bu.escribir_atomico(salida, json.dumps(nuevo, ensure_ascii=False, indent=1))
    return nuevo


# ------------------------------------------------------------------------ main
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--perfil", choices=sorted(w.PERFILES), default=w.PERFIL_POR_DEFECTO)
    p.add_argument("--curso", help="Curso (5BA) para --formulario.")
    p.add_argument("--formulario", action="store_true",
                   help="Lista las alumnas y asignaturas del curso. No escribe nada.")
    p.add_argument("--datos", metavar="obs.json", help="La observación a registrar.")
    p.add_argument("--simular", action="store_true", help="Muestra qué se guardaría.")
    p.add_argument("--seleccion", metavar="ARCHIVO.json", help="Solo las alumnas marcadas.")
    p.add_argument("--cursos", action="store_true", help="Lista los cursos del colegio. No escribe nada.")
    p.add_argument("--vigilar", metavar="5BA,6BB", help="Busca observaciones nuevas en esos cursos. No escribe en Webclass.")
    p.add_argument("--salida", metavar="ARCHIVO.json", help="Con --vigilar: dónde se anota lo visto y lo nuevo.")
    args = p.parse_args()
    nombre = args.perfil
    perfil = w.PERFILES[nombre]

    if args.vigilar:
        if not args.salida:
            raise ValueError("--vigilar necesita --salida.")
        cursos = [c.strip().upper() for c in args.vigilar.split(",") if c.strip()]
        resultado = vigilar_y_guardar(nombre, cursos, args.salida)
        print(resultado["error"] or f"Revisados: {', '.join(cursos)}.")
        return

    if args.cursos:
        s, perfil = abrir_sesion(nombre)
        cursos = leer_cursos(s) or perfil["curso_ids"]
        for curso in cursos:
            w.item(curso, "propuesto", curso, "CURSOS", "curso")
        print(f"{len(cursos)} cursos en el colegio.")
        return

    if args.formulario:
        curso = (args.curso or "").upper()
        if curso not in perfil["curso_ids"]:
            raise ValueError(f"El curso «{curso}» no está en tu perfil.")
        s, perfil = abrir_sesion(nombre)
        f = leer_formulario(s, perfil["curso_ids"][curso])
        conocidas = {u["asignatura"] for u in perfil.get("unidades", [])
                     if u.get("curso") == curso and u.get("asignatura")}
        sugerida = asignatura_probable(f["asignaturas"], conocidas)
        for valor, texto in f["asignaturas"]:
            w.item(valor, "propuesto", texto, "ASIGNATURAS", "asignatura",
                   "sugerida" if valor == sugerida else "")
        for valor, texto in f["alumnas"]:
            w.item(valor, "propuesto", texto.title(), curso, "alumna")
        print(f"{len(f['alumnas'])} alumnas y {len(f['asignaturas'])} asignaturas en {curso}.")
        return

    if not args.datos:
        raise ValueError("Indica --datos obs.json o --formulario.")
    with open(args.datos, encoding="utf-8") as f:
        datos = json.load(f)
    problemas = validar(datos)
    if problemas:
        raise ValueError("No se puede guardar: " + "; ".join(problemas))
    curso = datos["curso"].upper()
    if curso not in perfil["curso_ids"]:
        raise ValueError(f"El curso «{curso}» no está en tu perfil.")
    elegidas = w.leer_seleccion(args.seleccion)
    s, perfil = abrir_sesion(nombre)
    curso_id = perfil["curso_ids"][curso]
    formulario = leer_formulario(s, curso_id)
    nombres = dict(formulario["alumnas"])
    visibles = valores_visibles(formulario["roles"], datos.get("visible", "equipo"))
    periodo = periodo_de_pagina(s, curso_id)
    tipo = TIPOS[int(datos["tipo"])]
    resumen = f"{tipo} · {datos['fecha']} · «{datos['texto'].strip()[:40]}»"
    total = len(datos["alumnas"])
    for n, alumna in enumerate(datos["alumnas"], 1):
        alumna = str(alumna)
        titulo = f"{curso} · {nombres.get(alumna, alumna).title()}"
        if alumna not in nombres:
            w.item(alumna, "pendiente", titulo, curso, "observación",
                   motivo="la alumna no está en la lista del curso")
            continue
        if elegidas is not None and alumna not in elegidas:
            w.item(alumna, "omitido", titulo, curso, "observación")
            continue
        print(f"##PROGRESO {n - 1}/{total} {curso}", flush=True)
        if args.simular:
            print(f"  [SIMULAR] {titulo}: {resumen}")
            w.item(alumna, "propuesto", titulo, curso, "observación", resumen)
            continue
        cuerpo = cuerpo_de_envio(datos, alumna, curso_id, periodo, perfil["iduser"], visibles)
        try:
            numero = guardar_una(s, cuerpo)
        except Exception as exc:  # noqa: BLE001
            w.item(alumna, "error", titulo, curso, "observación", motivo=str(exc)[:120])
            continue
        if numero > 0:
            print(f"  [OK] {titulo}")
            w.item(alumna, "hecho", titulo, curso, "observación", resumen)
        else:
            w.item(alumna, "pendiente", titulo, curso, "observación",
                   motivo="Webclass no confirmó que se guardara la observación")
    print(f"##PROGRESO {total}/{total} {curso}", flush=True)
    if not args.simular:
        w.imprimir_resultado(w.ITEMS, vacio="No había observaciones que guardar.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
