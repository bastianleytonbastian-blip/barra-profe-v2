"""
Observaciones de estudiantes (Libro digital > Observaciones) desde la barra.

Una misma observación para varias alumnas, con vista previa y casillas. Cada alumna
recibe su propia observación, así el informe dice cuáles se guardaron y cuáles no.

  observar --curso 5BA --formulario            lista alumnas y asignaturas del curso (solo lectura)
  observar --datos obs.json --simular          muestra qué se guardaría, sin escribir
  observar --datos obs.json [--seleccion s.json]   guarda (solo las alumnas marcadas)

obs.json: {"curso": "5BA", "alumnas": ["6042943", ...], "tipo": 1|2|3, "fecha": "DD/MM/AAAA",
           "texto": "...", "asignatura": "-172", "visible": "equipo" | "todos"}
tipo: 1 positiva, 2 negativa, 3 neutra.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import re
import sys
import unicodedata

import webclass_tareas as w

URL = f"{w.BASE}/home/anotaciones/controlador/controladorNew_Edit.php"
TIPOS = {1: "positiva", 2: "negativa", 3: "neutra"}
# Valor de cada casilla «visible para» del formulario (visto_N). Alumno y apoderado:
ROLES_FAMILIA = {"31", "21"}
LARGO_MAXIMO = 1500


# ---------------------------------------------------------------- lógica pura
def _texto(fragmento: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragmento)).split())


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
    def norma(t: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFD", t.lower())
                       if unicodedata.category(c) != "Mn").strip()
    mias = {norma(c) for c in conocidas}
    for valor, texto in asignaturas:
        if norma(texto) in mias:
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
    args = p.parse_args()
    nombre = args.perfil
    perfil = w.PERFILES[nombre]

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
