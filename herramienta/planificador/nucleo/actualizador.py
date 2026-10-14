"""Descarga los Objetivos de Aprendizaje oficiales de TODAS las asignaturas (curriculumnacional.cl, MINEDUC)
y los guarda en data/curriculo_oa.json. Sin Streamlit.

Uso desde la terminal:  python -m nucleo.actualizador
También se puede llamar a actualizar() desde la app (botón «Actualizar currículo»).
"""
import html
import json
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from nucleo import rutas

SALIDA = os.path.join(rutas.DATOS_COMUN, "curriculo_oa.json")   # el currículo oficial es el mismo para todas las cuentas
SITIO = "https://www.curriculumnacional.cl"
TRAMOS = ("1o-6o-basico", "7o-basico-2o-medio", "3o-4o-medio")


def bajar(url, intentos=3):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Planificador escolar)"})
    for i in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception:
            if i == intentos - 1:
                raise


def limpiar(fragmento):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragmento)).split())


def codigo_corto(oficial):
    """Código como lo muestra WebClass: 'HI07 OA 09' -> 'OA9'; 'HI06 OAH a' -> 'OAH a'; 'HI06 OAA B' -> 'OAA B'."""
    m = re.search(r"\b(OA[HAC]?)[\s-]*0*([0-9]+|[A-Za-z])\s*$", oficial)
    if not m:
        return oficial
    tipo, num = m.groups()
    return f"OA{num}" if tipo in ("OA", "OAC") else f"{tipo} {num}"


def leer_curso(ruta):
    """ruta: 'tramo/asignatura/curso' -> {fuente, oa[], habilidades[], actitudes[]}."""
    pagina = bajar(f"{SITIO}/curriculum/{ruta}")
    inicio = pagina.find("Explorar Base Curricular")
    pagina = pagina[inicio:] if inicio >= 0 else pagina
    # Cada objetivo es un bloque <div class="item-wrapper ...">; el eje es el último <h3> anterior al bloque
    ejes = [(m.start(), limpiar(m.group(1))) for m in re.finditer(r"<h3[^>]*>(.*?)</h3>", pagina, re.S)]
    inicios = [m.start() for m in re.finditer(r'<div class="item-wrapper[ "]', pagina)]
    cortes = sorted(inicios + [p for p, _ in ejes] + [len(pagina)])
    objetivos = []
    for pos in inicios:
        bloque = pagina[pos:cortes[cortes.index(pos) + 1]]
        cod = re.search(r'class="number-title">([^<]+)<', bloque)
        if not cod:
            continue
        cuerpo = bloque.split("</h4>", 1)[-1].split('class="link-more"', 1)[0]
        cuerpo = re.sub(r"<a [^>]*$", "", cuerpo)
        oficial = " ".join(cod.group(1).split())
        objetivos.append({
            "codigo": codigo_corto(oficial),
            "codigo_oficial": oficial,
            "eje": next((nombre for p, nombre in reversed(ejes) if p < pos), ""),
            "texto": limpiar(cuerpo),
            "priorizado": "prioritized" in bloque[:80],
        })
    return {
        "fuente": f"{SITIO}/curriculum/{ruta}",
        "oa": [o for o in objetivos if re.fullmatch(r"OA\d+", o["codigo"])],
        "habilidades": [o for o in objetivos if o["codigo"].startswith("OAH")],
        "actitudes": [o for o in objetivos if o["codigo"].startswith("OAA")],
    }


def _nombre_curso(slug):
    """'6-basico' -> '6° Básico'; '3-medio-hc' -> '3° Medio'; None si no es un curso."""
    m = re.match(r"(\d)-(basico|medio)", slug)
    return f"{m.group(1)}° {'Básico' if m.group(2) == 'basico' else 'Medio'}" if m else None


def _nombre_asignatura(h1):
    """'Matemática 3º medio' -> 'Matemática'."""
    return re.sub(r"\s+\d\s*[º°o]\s*(?:medio|básico)\s*$", "", limpiar(h1), flags=re.I).strip()


def listar():
    """[(tramo, slug_asignatura)] de todo el currículo."""
    pares = []
    for tramo in TRAMOS:
        pagina = bajar(f"{SITIO}/curriculum/{tramo}")
        for slug in sorted(set(re.findall(rf'href="/curriculum/{tramo}/([^"/#?]+)"', pagina))):
            pares.append((tramo, slug))
    return pares


def _leer_asignatura(par):
    tramo, slug = par
    pagina = bajar(f"{SITIO}/curriculum/{tramo}/{slug}")
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", pagina, re.S)
    nombre = _nombre_asignatura(h1.group(1)) if h1 else slug
    cursos = {}
    for curso_slug in sorted(set(re.findall(rf'href="/curriculum/{tramo}/{re.escape(slug)}/([^"#?/]+)"', pagina))):
        curso = _nombre_curso(curso_slug)
        if not curso:
            continue
        try:
            datos = leer_curso(f"{tramo}/{slug}/{curso_slug}")
        except Exception:
            continue
        if datos["oa"]:
            cursos[curso] = datos
    return nombre, cursos


def fusionar(asignaturas, nombre, cursos):
    """Agrega cursos a una asignatura; 'Lengua y literatura' y 'Lengua y Literatura' son la misma (sin distinguir
    mayúsculas), y se conserva la escritura que empieza con más mayúsculas de título."""
    existente = next((n for n in asignaturas if n.casefold() == nombre.casefold()), None)
    if existente is None:
        asignaturas[nombre] = {"cursos": dict(cursos)}
        return
    for c, d in cursos.items():
        asignaturas[existente]["cursos"].setdefault(c, d)


def actualizar(progreso=None):
    """Descarga todo y guarda el JSON. progreso(i, total, texto) es opcional. Devuelve el resumen {asignatura: n_cursos}."""
    pares = listar()
    base = {"actualizado": date.today().isoformat(), "asignaturas": {}}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for i, (nombre, cursos) in enumerate(pool.map(_leer_asignatura, pares), start=1):
            if cursos:
                fusionar(base["asignaturas"], nombre, cursos)
            if progreso:
                progreso(i, len(pares), nombre)
    base["asignaturas"] = dict(sorted(base["asignaturas"].items()))
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA + ".tmp", "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=1)
    os.replace(SALIDA + ".tmp", SALIDA)  # no deja un JSON a medias si se corta la descarga
    return {n: len(a["cursos"]) for n, a in base["asignaturas"].items()}


if __name__ == "__main__":
    resumen = actualizar(lambda i, t, n: print(f"[{i}/{t}] {n}"))
    print(f"Asignaturas: {len(resumen)}. Guardado en {SALIDA}")
