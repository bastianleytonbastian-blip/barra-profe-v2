"""
Unidades de planificación del docente: cuáles hay en Webclass y cuáles conoce su perfil.

«Asignar» trabaja con las unidades guardadas en el perfil (personal\\perfiles\\<clave>.json),
que arma configurar.py una sola vez. Si el docente crea una unidad nueva, el perfil no
se entera solo. Este módulo la busca en Webclass, la compara con lo que el perfil ya
conoce (o rechazó antes) y deja que el docente decida si la incluye. Nada se incluye
sin que lo decida: lo rechazado se anota para no volver a preguntar.

Lo que ofrece Webclass se guarda por unas horas (datos\\unidades_ofrecidas_<perfil>.json)
para no repetir las consultas cada vez que se abre una vista previa.
"""

from __future__ import annotations

import datetime
import json
import os
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import rutas
import webclass_tareas as w

HORAS_VIGENCIA = 2          # cuánto vale lo que ofreció Webclass antes de volver a preguntar


# ---------------------------------------------------------------- lógica pura
def _normal(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn").lower().strip()


def conocidas(perfil: dict) -> set[str]:
    """Ids de unidades que el perfil ya tiene o que el docente decidió no incluir."""
    return ({str(u["id"]) for u in perfil.get("unidades", [])}
            | {str(i) for i in perfil.get("unidades_ignoradas", [])})


def nuevas_entre(perfil: dict, ofrecidas: list[dict]) -> list[dict]:
    """De lo que ofrece Webclass, lo que el perfil no conoce ni rechazó (sin repetir)."""
    vistas, nuevas = conocidas(perfil), []
    for u in ofrecidas:
        if str(u["id"]) not in vistas:
            vistas.add(str(u["id"]))
            nuevas.append(u)
    return nuevas


def asignaturas_por_curso(perfil: dict) -> dict[str, set[str]]:
    """{curso: asignaturas} que se conocen por las unidades del perfil (puede faltar alguna)."""
    por_curso: dict[str, set[str]] = {}
    for u in perfil.get("unidades", []):
        if u.get("asignatura"):
            por_curso.setdefault(u["curso"], set()).add(_normal(u["asignatura"]))
    return por_curso


def fresco(cache: dict | None, ahora: datetime.datetime | None = None) -> bool:
    """¿Lo que se guardó de Webclass sigue valiendo (menos de HORAS_VIGENCIA)?"""
    ahora = ahora or datetime.datetime.now()
    try:
        revisado = datetime.datetime.fromisoformat(cache["revisado"])
    except (KeyError, TypeError, ValueError):
        return False
    return datetime.timedelta(0) <= ahora - revisado < datetime.timedelta(hours=HORAS_VIGENCIA)


def aplicar_decision(perfil: dict, incluir: list[dict], ignorar_ids: list[str]) -> dict:
    """Copia del perfil con las unidades incluidas sumadas y las rechazadas anotadas.

    Una unidad de un curso que el perfil no tenía suma también el curso (con su id y su nivel).
    """
    nuevo = json.loads(json.dumps(perfil))                     # copia profunda
    existentes = {str(u["id"]) for u in nuevo.setdefault("unidades", [])}
    for u in incluir:
        if str(u["id"]) in existentes:
            continue
        nuevo["unidades"].append({"curso": u["curso"], "id": u["id"], "nombre": u.get("nombre", ""),
                                  "asignatura": u.get("asignatura", "")})
        existentes.add(str(u["id"]))
        if u.get("curso_id") and u["curso"] not in nuevo.setdefault("curso_ids", {}):
            nuevo["curso_ids"][u["curso"]] = u["curso_id"]
            if u.get("nivel") is not None:
                nuevo.setdefault("curso_niveles", {})[u["curso"]] = u["nivel"]
    elegidas = {str(u["id"]) for u in incluir}
    ignoradas = {str(i) for i in nuevo.get("unidades_ignoradas", [])} - elegidas
    ignoradas |= {str(i) for i in ignorar_ids} - existentes
    nuevo["unidades_ignoradas"] = sorted(ignoradas)
    return nuevo


def enriquecer(perfil: dict, ofrecidas: list[dict]) -> tuple[dict, bool]:
    """Anota la asignatura en las unidades del perfil que no la traían (perfiles armados a mano).

    Así la siguiente búsqueda consulta solo las asignaturas del docente, no todas las del curso.
    Devuelve (perfil, hubo_cambios).
    """
    por_id = {str(o["id"]): o for o in ofrecidas}
    cambio = False
    for u in perfil.get("unidades", []):
        o = por_id.get(str(u["id"]))
        if o and not u.get("asignatura") and o.get("asignatura"):
            u["asignatura"] = o["asignatura"]
            cambio = True
    return perfil, cambio


# ------------------------------------------------------- archivos del perfil
def ruta_perfil(clave: str) -> str:
    return os.path.join(rutas.PERFILES, f"{clave}.json")


def ruta_cache(clave: str) -> str:
    return rutas.dato(f"unidades_ofrecidas_{clave}.json")


def _leer(ruta: str, por_defecto):
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            dato = json.load(f)
        return dato if isinstance(dato, type(por_defecto)) else por_defecto
    except (OSError, ValueError):
        return por_defecto


def guardar_perfil(clave: str, perfil: dict) -> None:
    """Escribe el perfil de forma atómica y actualiza el que está en memoria."""
    ruta = ruta_perfil(clave)
    temporal = ruta + ".tmp"
    perfil["actualizado"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(perfil, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporal, ruta)
    w.PERFILES[clave] = perfil


# ----------------------------------------------------------- consulta a Webclass
def ofrecidas_por_webclass(perfil: dict, trabajadores: int = 4) -> list[dict]:
    """Todas las unidades que Webclass ofrece hoy a este docente en las asignaturas que dicta.

    Consulta los cursos del docente y, por cada curso, solo las asignaturas que ya aparecen en
    su perfil (si no se conocen, todas las del curso: pasa una vez y queda anotado). Solo se
    miran los cursos que el perfil ya tiene: Webclass lista todos los del colegio.
    """
    import webclass_libro as L

    s, token = L.sesion_libro(perfil)
    colegio, rol = L.COLEGIO, perfil.get("rol", 13)
    hoy = datetime.date.today()
    cursos = L.api_get(s, "getCourses", {"idColegio": colegio, "anio": hoy.year,
                                         "idUsuario": perfil["iduser"]}, token).get("courses", [])
    conocidas_por_curso = asignaturas_por_curso(perfil)
    tareas: list[tuple[dict, dict]] = []
    propios = set(perfil.get("curso_ids", {}))
    for c in cursos:
        if c["cur_nom"] not in propios:          # getCourses trae todo el colegio: solo sus cursos
            continue
        subs = L.api_get(s, "get-plan-subjects",
                         {"schoolID": colegio, "gradeID": c["id"], "levelID": c["niv_id"]},
                         token).get("subjects", [])
        interesan = conocidas_por_curso.get(c["cur_nom"])
        for sub in subs:
            if interesan is None or _normal(sub.get("sectornombre", "")) in interesan:
                tareas.append((c, sub))

    def unidades_de(par: tuple[dict, dict]) -> list[dict]:
        c, sub = par
        datos = L.api_get(s, "get-plan-units",
                          {"subjectID": sub["id"], "schoolID": colegio, "profesorID": perfil["iduser"],
                           "rolID": rol, "cursoID": c["id"], "levelID": c["niv_id"],
                           "date": hoy.strftime("%Y-%m-%d")}, token)
        return [{"curso": c["cur_nom"], "curso_id": c["id"], "nivel": c["niv_id"], "id": u["id"],
                 "nombre": u.get("nombre", ""), "asignatura": sub.get("sectornombre", "")}
                for u in datos.get("units", [])]

    with ThreadPoolExecutor(max_workers=max(1, trabajadores)) as pool:
        return [u for lista in pool.map(unidades_de, tareas) for u in lista]


def ofrecidas(clave: str, perfil: dict, forzar: bool = False,
              consultar=ofrecidas_por_webclass) -> tuple[list[dict], bool]:
    """(unidades que ofrece Webclass, ¿se consultó ahora?). Usa lo guardado si aún vale."""
    cache = _leer(ruta_cache(clave), {})
    if not forzar and fresco(cache) and isinstance(cache.get("unidades"), list):
        return cache["unidades"], False
    unidades = consultar(perfil)
    try:
        rutas.dato("")                                   # asegura la carpeta
        with open(ruta_cache(clave), "w", encoding="utf-8") as f:
            json.dump({"revisado": datetime.datetime.now().isoformat(timespec="seconds"),
                       "unidades": unidades}, f, ensure_ascii=False)
    except OSError:
        pass
    return unidades, True


def buscar_nuevas(clave: str, perfil: dict, forzar: bool = False,
                  consultar=ofrecidas_por_webclass, con_origen: bool = False):
    """Las unidades nuevas del docente. De paso anota la asignatura que faltaba en su perfil.

    Con con_origen devuelve (nuevas, ¿se consultó Webclass ahora?): sirve para saber si
    la lista es la misma que vio el docente en la vista previa o una más reciente.
    """
    todas, consultado = ofrecidas(clave, perfil, forzar, consultar)
    perfil, cambio = enriquecer(perfil, todas)
    if cambio:
        guardar_perfil(clave, perfil)
    nuevas = nuevas_entre(perfil, todas)
    return (nuevas, consultado) if con_origen else nuevas


def decidir(clave: str, perfil: dict, nuevas: list[dict], incluir_ids: list[str],
            ignorar_ids: list[str]) -> dict:
    """Guarda la decisión del docente en su perfil y devuelve el perfil actualizado."""
    incluir = [u for u in nuevas if str(u["id"]) in {str(i) for i in incluir_ids}]
    if not incluir and not ignorar_ids:
        return perfil
    nuevo = aplicar_decision(perfil, incluir, ignorar_ids)
    guardar_perfil(clave, nuevo)
    return nuevo
