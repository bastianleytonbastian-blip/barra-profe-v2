"""
Automatización de asignación de tareas (planificaciones) en Webclass
(proyecto.webescuela.cl) para el segundo semestre 2026.

Reemplaza el flujo manual de:
  entrar a cada unidad -> revisar cada clase -> abrir "Asignar alumno"
  -> tildar "Todos los Alumnos" -> completar instrucciones y fechas -> Guardar

Requiere: pip install requests
"""

from __future__ import annotations

import argparse
import csv
import datetime
import getpass
import html
import json
import os
import re
import sys

import keyring
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import rutas

KEYRING_SERVICE = "webclass-tareas"

# ------------------------------------------------------------------------ ítems
# Cada herramienta informa lo que considera con una línea `##ITEM {json}`; la
# barra la usa para las casillas de la vista previa y para contar después qué
# se hizo y qué no. Los scripts (libro, tareas, subir) comparten estas ayudas.
ITEMS: list[dict] = []


def item(clave: str, estado: str, titulo: str, grupo: str = "", que: str = "",
         detalle: str = "", motivo: str = "", opciones: list[dict] | None = None,
         sin_clase: dict | None = None) -> None:
    """Informa un ítem. estado: propuesto | hecho | ya | pendiente | error | omitido.

    `opciones` ([{"id", "texto"}]) son las clases entre las que el docente puede
    elegir cuando la herramienta no pudo decidir sola. `sin_clase` ({campo, clave,
    dia, titulo}) deja marcarlo «no hubo clase» desde la vista previa de la barra.
    """
    dato = {"clave": str(clave), "estado": estado, "titulo": titulo, "grupo": grupo,
            "que": que, "detalle": detalle, "motivo": motivo}
    if opciones:
        dato["opciones"] = opciones
    if sin_clase:
        dato["sin_clase"] = sin_clase
    ITEMS.append(dato)
    if sys.stdout:                  # con pythonw no hay consola
        print("##ITEM " + json.dumps(dato, ensure_ascii=False), flush=True)


def leer_seleccion(ruta: str | None) -> set[str] | None:
    """Claves que el docente marcó en la vista previa (None = todo)."""
    if not ruta:
        return None
    with open(ruta, encoding="utf-8") as f:
        return {str(c) for c in json.load(f).get("claves", [])}


def dias_de_meses(texto: str, hoy: datetime.date | None = None) -> set[str]:
    """«09/2026,10/2026» -> todos los días de esos meses hasta hoy, como «dd/mm/aaaa».

    Los días que todavía no llegan no cuentan: «lo pendiente» es lo que ya pasó.
    """
    hoy = hoy or datetime.date.today()
    dias: set[str] = set()
    for parte in texto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        try:
            mes, anio = (int(x) for x in parte.split("/"))
            dia = datetime.date(anio, mes, 1)
        except ValueError:
            raise ValueError(f"No entendí el mes «{parte}»: usa MM/AAAA (por ejemplo 09/2026).") from None
        while dia.month == mes and dia <= hoy:
            dias.add(dia.strftime("%d/%m/%Y"))
            dia += datetime.timedelta(days=1)
    if not dias:
        raise ValueError("Esos meses no tienen días que ya hayan pasado.")
    return dias


def leer_elecciones(ruta: str | None) -> dict[str, str]:
    """Clases que el docente escogió a mano: {clave del bloque: id de la clase}."""
    if not ruta:
        return {}
    with open(ruta, encoding="utf-8") as f:
        return {str(k): str(v) for k, v in json.load(f).get("elecciones", {}).items()}


def imprimir_resultado(items: list[dict], firmas: list[str] | tuple = (), vacio: str = "") -> None:
    """El cierre de la corrida: qué intenté, qué hice y qué no, en palabras simples."""
    if not sys.stdout:
        return
    import barra_utiles as bu
    bloques = bu.agrupar_items(items)
    propuestos = [it for it in items if it["estado"] == "propuesto"]
    intentados = sum(len(bloques[k]) for k in ("hecho", "ya", "no_pude"))
    print("\n=== Resultado ===")
    if propuestos:
        print(f"  Haría ({len(propuestos)}):")
        for it in propuestos:
            print(f"    - {it['titulo']}" + (f": {it['detalle']}" if it["detalle"] else ""))
    if not items:
        print(f"  {vacio or 'No había nada por hacer.'}")
    else:
        if intentados or bloques["omitido"]:
            print(f"  Intenté: {intentados}"
              + (f"  (omitiste {len(bloques['omitido'])})" if bloques["omitido"] else ""))
        if bloques["hecho"]:
            print(f"  Hice ({len(bloques['hecho'])}):")
            for it in bloques["hecho"]:
                print(f"    - {it['titulo']}" + (f": {it['detalle']}" if it["detalle"] else ""))
        if bloques["no_pude"]:
            print(f"  No pude ({len(bloques['no_pude'])}):")
            for it in bloques["no_pude"]:
                e = bu.explicar_motivo(it["motivo"] or it["detalle"])
                print(f"    - {it['titulo']}: {e['que']}")
                if e["hacer"]:
                    print(f"        Qué hacer: {e['hacer']}")
        if bloques["ya"]:
            print(f"  Ya estaba hecho ({len(bloques['ya'])}):")
            if len(bloques["ya"]) > 6:      # una lista larga tapa lo importante
                print("    (son muchos: no se detallan)")
            else:
                for it in bloques["ya"]:
                    print(f"    - {it['titulo']}")
        if bloques["omitido"]:
            print(f"  Omitido por ti ({len(bloques['omitido'])}):")
            for it in bloques["omitido"]:
                print(f"    - {it['titulo']}")
    if firmas:
        print("\n  FALTA TU FIRMA en:")
        for f in firmas:
            print(f"    {f}")


BASE ="https://proyecto.webescuela.cl/sistema/webclass"
# El formulario de login vive en un dominio distinto al de la app; el POST de
# autenticación debe ir contra este dominio o el servidor responde "Usuario
# incorrecto" aunque las credenciales sean correctas.
LOGIN_BASE = "https://plataforma.webescuela.cl/sistema/webclass"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Cada docente es un perfil independiente: su RUT, su id de usuario en Webclass
# y SUS unidades. Nunca se mezclan en una misma corrida: una corrida usa un
# solo perfil. Así el script no puede tocar las unidades de otro docente por
# error, que es el riesgo real al automatizar más de una cuenta.
#
# Los perfiles NO van escritos en el código (este archivo se reparte a otros
# docentes): cada uno vive en personal\perfiles\<clave>.json, que arma
# configurar.py. "iduser" es el seguro: al iniciar sesión se compara contra el
# usuario real de la sesión y, si no calzan, la corrida se aborta antes de
# escribir nada.
PERFILES: dict[str, dict] = {}
PERFIL_POR_DEFECTO = ""

# Cada docente corre configurar.py en su PC y queda un archivo en
# perfiles\<nombre>.json con su RUT, sus cursos y sus unidades. Así la
# herramienta sirve a cualquier profesor sin tocar este código.
def carpeta_datos() -> str:
    """Carpeta donde se escriben registros y logs (datos\\, o todo junto si no hay)."""
    return rutas.DATOS


CARPETA_PERFILES = rutas.PERFILES


def cargar_perfiles() -> None:
    """Suma a PERFILES lo que haya en la carpeta perfiles\\."""
    if not os.path.isdir(CARPETA_PERFILES):
        return
    for archivo in sorted(os.listdir(CARPETA_PERFILES)):
        if not archivo.endswith(".json"):
            continue
        ruta = os.path.join(CARPETA_PERFILES, archivo)
        try:
            # utf-8-sig: si el docente edita el perfil con el Bloc de notas,
            # Windows le deja una marca al principio que rompe json.load.
            with open(ruta, encoding="utf-8-sig") as f:
                perfil = json.load(f)
            faltan = {"rut", "iduser", "curso_ids", "unidades"} - set(perfil)
            if faltan:
                print(f"Perfil {archivo}: le faltan datos ({', '.join(sorted(faltan))}); "
                      "vuelve a correr configurar.py", file=sys.stderr)
                continue
            PERFILES[archivo[:-5]] = perfil
        except (OSError, ValueError) as exc:
            print(f"Perfil {archivo}: no se pudo leer ({exc})", file=sys.stderr)


cargar_perfiles()

# Quien esté activo en la barra manda. En los PC de sala de profesores, las
# tareas programadas y los accesos del escritorio quedaron con el perfil del
# docente que instaló: sin esto, lo que subiera cualquier otro se registraba
# a nombre de ese.
_activo = rutas.perfil_activo("")
if _activo in PERFILES:
    PERFIL_POR_DEFECTO = _activo
elif PERFILES:
    PERFIL_POR_DEFECTO = sorted(PERFILES)[0]

# El perfil por defecto conserva el CSV histórico; los demás escriben el suyo
# para no mezclar los registros de dos docentes en el mismo archivo.
REGISTRO_CSV = "registro_asignaciones.csv"

# Alias del perfil por defecto, para no romper la tarea programada ni los
# scripts auxiliares que importan estos nombres directamente.
# Sin ningún perfil (PC recién instalado, antes de configurar.py) quedan vacíos
# en vez de reventar al importar: configurar.py importa este módulo.
_PERFIL_INICIAL = PERFILES.get(PERFIL_POR_DEFECTO, {})
UNIDADES = _PERFIL_INICIAL.get("unidades", [])
CURSO_IDS = _PERFIL_INICIAL.get("curso_ids", {})
RUT_USUARIO = _PERFIL_INICIAL.get("rut", "")


def crear_session() -> requests.Session:
    """Sesión HTTP con reintentos automáticos.

    Webclass corta conexiones a mitad de camino con cierta frecuencia
    (RemoteDisconnected, Read timed out). Sin reintentos, un solo hipo de red
    mata la corrida completa y deja clases sin asignar en silencio; fue lo que
    pasó el 19 y el 20 de agosto de 2026.

    Se reintentan también los POST (que urllib3 por defecto no reintenta, por
    no ser idempotentes) porque en esta API *todo* es POST. Reasignar una tarea
    ya asignada es inofensivo: Webclass la sobrescribe con los mismos datos en
    vez de duplicarla.
    """
    session = requests.Session()
    reintentos = Retry(
        total=3,
        backoff_factor=2,  # espera ~2s, 4s y 8s entre intentos
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adaptador = HTTPAdapter(max_retries=reintentos)
    session.mount("https://", adaptador)
    session.mount("http://", adaptador)
    return session


def login(session: requests.Session, rut: str, password: str) -> None:
    # Primero pisamos la portada de login para que el servidor emita PHPSESSID.
    session.get(f"{LOGIN_BASE}/", headers=HEADERS, timeout=30)

    login_headers = {
        **HEADERS,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{LOGIN_BASE}/",
        "Origin": "https://plataforma.webescuela.cl",
    }
    resp = session.post(
        f"{LOGIN_BASE}/autentificacion/controlador/controladorUsuario.php",
        data={
            "nombre": rut,
            "pass": password,
            "colegio": -1,
            "url": f"{LOGIN_BASE}/",
            "desaf": "/trainer/home/mantenedorcolegios",
            "caso": 1,
            "accion": 1,
        },
        headers=login_headers,
        timeout=30,
    )
    try:
        accion, texto = resp.json()
    except ValueError:
        raise RuntimeError(
            "Login fallido: el servidor no devolvió JSON. "
            f"HTTP {resp.status_code}. Respuesta cruda:\n{resp.text[:1000]}"
        ) from None

    if accion != 1:
        raise RuntimeError(
            f"Login fallido: {re.sub('<[^>]+>', '', texto)} (accion={accion})"
        )

    # Sigue la redirección final que entrega el login (deja la sesión lista).
    session.get(f"https://plataforma.webescuela.cl{texto}", headers=HEADERS, timeout=30)


def listar_clases(session: requests.Session, id_unidad: int) -> list[dict]:
    """Devuelve todas las clases de una unidad con su estado de asignación."""
    resp = session.post(
        f"{BASE}/home/planificacion/controladores/controladorPlanificacion.php",
        data={"caso": 2, "accion": 2, "idclase": 0, "idplan": id_unidad},
        headers=HEADERS,
        timeout=180,
    )
    text = resp.text

    marcas = list(
        re.finditer(
            r'data-clase="(\d+)"[^>]*data-autor="(\d+)"[^>]*data-nombre="([^"]+)"',
            text,
        )
    )

    clases = []
    for i, m in enumerate(marcas):
        inicio_chunk = m.start()
        fin_chunk = marcas[i + 1].start() if i + 1 < len(marcas) else len(text)
        chunk = text[inicio_chunk:fin_chunk]

        idclase = m.group(1)

        m_tarea = re.search(
            r"asignar_alumno\.php\?id=" + idclase + r"&unidad=\d+'\"[\s\S]{0,250}?<b>(\d+)</b>",
            chunk,
        )
        m_ini = re.search(r'id="fechainicio_\d+"[\s\S]*?value=\'([^\']+)\'', chunk)
        m_fin = re.search(r'id="fechatermino_\d+"[\s\S]*?value=\'([^\']+)\'', chunk)

        clases.append(
            {
                "idclase": idclase,
                "nombre": html.unescape(m.group(3)).strip(),
                "asignados": int(m_tarea.group(1)) if m_tarea else None,
                "fechaini": m_ini.group(1) if m_ini else None,
                "fechafin": m_fin.group(1) if m_fin else None,
            }
        )
    return clases


def datos_clase(session: requests.Session, idclase: str, id_unidad: int) -> dict:
    """Lee del formulario de asignación los ids de colegio/profesor/nivel/usuario."""
    resp = session.get(
        f"{BASE}/home/planificacion/asignar_alumno.php",
        params={"id": idclase, "unidad": id_unidad},
        headers=HEADERS,
        timeout=90,
    )
    text = resp.text

    def campo(nombre: str) -> str | None:
        m = re.search(rf'id="{nombre}"[^>]*value="([^"]*)"', text)
        return m.group(1) if m else None

    return {
        "idcolegio": campo("idcolegio"),
        "idprofesor": campo("idprofesor"),
        "idnivel": campo("idnivel"),
        "iduser": campo("iduser"),
    }


DESTINOS = os.path.join(rutas.PERSONAL, "destinos.json")


def elegir_destinos(session: requests.Session, perfil: dict, solo_nuevas: bool = True) -> None:
    """Pregunta, unidad por unidad, a dónde asignar sus clases.

    Se hace una vez y queda guardado en personal\\destinos.json. Las opciones
    son las que ofrece el propio Webclass, así que incluyen los talleres.
    """
    elegidos = destinos_elegidos()
    print("\n=== A dónde se asigna cada unidad ===")
    print("  Enter deja lo que ya está. «s» salta la unidad.\n")
    for info in perfil["unidades"]:
        id_unidad, curso = info["id"], info["curso"]
        actual = elegidos.get(str(id_unidad))
        if actual and solo_nuevas:
            print(f"  {curso}: {info['nombre'][:46]}\n      ya está: {actual['nombre']}\n")
            continue
        clases = listar_clases(session, id_unidad)
        if not clases:
            print(f"  {curso}: {info['nombre'][:46]} — sin clases, se salta.\n")
            continue
        datos = datos_clase(session, clases[0]["idclase"], id_unidad)
        opciones = destinos_de_clase(session, clases[0]["idclase"], id_unidad, datos)
        if not opciones:
            print(f"  {curso}: no pude leer los destinos, se salta.\n")
            continue
        por_defecto = actual["id"] if actual else perfil["curso_ids"].get(curso)
        print(f"  {curso}: {info['nombre'][:46]}")
        for n, o in enumerate(opciones, 1):
            marca = " (actual)" if o["id"] == por_defecto else ""
            print(f"      {n:>2}. {o['nombre']}{marca}")
        respuesta = input("      ¿A cuál? [Enter = dejar como está, s = saltar]: ").strip()
        if respuesta.lower() == "s" or not respuesta:
            print()
            continue
        try:
            destino = opciones[int(respuesta) - 1]
        except (ValueError, IndexError):
            print("      No entendí ese número; se deja como estaba.\n")
            continue
        guardar_destino(id_unidad, destino)
        print(f"      guardado: {destino['nombre']}\n")
    print(f"Queda en: {DESTINOS}")


def opciones_de_unidades(session: requests.Session, perfil: dict, ids: list[str]) -> None:
    """Escribe, por cada unidad pedida, las opciones de destino que ofrece Webclass.

    Una línea `##OPCIONES {json}` por unidad. Es para el editor de la barra:
    solo se consulta lo que el docente quiere cambiar, no todas las unidades.
    """
    por_id = {str(u["id"]): u for u in perfil["unidades"]}
    for n, id_unidad in enumerate(ids, 1):
        print(f"##PROGRESO {n - 1}/{len(ids)} unidad {id_unidad}", flush=True)
        info = por_id.get(str(id_unidad))
        salida = {"unidad": str(id_unidad), "opciones": [], "error": ""}
        if not info:
            salida["error"] = "esa unidad no está en tu perfil"
        else:
            try:
                clases = listar_clases(session, id_unidad)
                if not clases:
                    salida["error"] = "la unidad no tiene clases"
                else:
                    datos = datos_clase(session, clases[0]["idclase"], id_unidad)
                    opciones = destinos_de_clase(session, clases[0]["idclase"], id_unidad, datos)
                    salida["opciones"] = [{"id": o["id"], "nombre": o["nombre"]}
                                          for o in opciones]
                    if not opciones:
                        salida["error"] = "Webclass no devolvió destinos"
            except Exception as exc:  # noqa: BLE001
                salida["error"] = str(exc)[:160]
        print("##OPCIONES " + json.dumps(salida, ensure_ascii=False), flush=True)
    print(f"##PROGRESO {len(ids)}/{len(ids)}", flush=True)


def destinos_elegidos() -> dict:
    """Lo que el docente eligió para cada unidad: {id_unidad: {id, nombre}}.

    Se pregunta una sola vez por unidad y queda guardado, porque las
    excepciones (una unidad de 5BA que se asigna a 5BB, o un taller) son
    fijas durante el año.
    """
    try:
        with open(DESTINOS, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def guardar_destino(id_unidad: int, destino: dict) -> None:
    elegidos = destinos_elegidos()
    elegidos[str(id_unidad)] = {"id": destino["id"], "nombre": destino["nombre"]}
    os.makedirs(os.path.dirname(DESTINOS), exist_ok=True)
    with open(DESTINOS, "w", encoding="utf-8") as f:
        json.dump(elegidos, f, ensure_ascii=False, indent=1)


def destinos_de_clase(session: requests.Session, idclase: str, id_unidad: int,
                      datos: dict) -> list[dict]:
    """A dónde se puede asignar esa clase, según el propio Webclass.

    Es el desplegable que sale en «Asignar alumno»: los cursos del nivel y
    también los talleres (T.E: de estudio, T.J: de jornada). Hasta ahora se
    asignaba siempre al curso de la unidad, y por eso un taller de Química
    terminaba asignado al curso entero en vez de a su sección.
    """
    resp = session.post(
        f"{BASE}/home/planificacion/controladores/controladorAsignacion.php",
        data={"idClase": idclase, "idCurso": "", "idColegio": datos["idcolegio"],
              "idNivel": datos["idnivel"], "idProfesor": datos["idprofesor"],
              "idunidad": id_unidad, "caso": 1, "accion": 1},
        headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"}, timeout=90)
    salida = []
    for valor, texto in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)</option>',
                                   resp.text):
        nombre = html.unescape(texto).strip()
        if not valor.strip() or not nombre:
            continue
        salida.append({"id": int(valor), "nombre": nombre,
                       "es_taller": nombre.upper().startswith(("T.E", "T.J"))})
    return salida


def listar_alumnas(
    session: requests.Session, idclase: str, idcurso: int, idcolegio: str, idprofesor: str
) -> list[str]:
    resp = session.post(
        f"{BASE}/home/planificacion/controladores/controladorAsignacion.php",
        data={
            "idClase": idclase,
            "idCurso": idcurso,
            "idColegio": idcolegio,
            "idProfesor": idprofesor,
            "caso": 1,
            "accion": 2,
        },
        headers=HEADERS,
        timeout=90,
    )
    text = resp.text
    ids = re.findall(r'name="alumno_\d+"\s*\r?\n?\s*id="alumno_\d+"\s*value="(\d+)"', text)
    # El listado de Webclass a veces repite a la misma alumna en dos filas
    # (dato duplicado en la matrícula del curso); se deduplica preservando el orden.
    return list(dict.fromkeys(ids))


def asignar_tarea(
    session: requests.Session,
    *,
    idclase: str,
    idcurso: int,
    idcolegio: str,
    idprofesor: str,
    iduser: str,
    alumnas: list[str],
    instruccion: str,
    fechaini: str,
    fechafin: str,
) -> None:
    id_alumno = "".join(f"{a}," for a in alumnas)

    resp = session.post(
        f"{BASE}/home/planificacion/controladores/controladorAsignacion.php",
        data={
            "idClase": idclase,
            "idAlumno": id_alumno,
            "idCurso": idcurso,
            "idProfesor": idprofesor,
            "instruccion": instruccion,
            "fechaini": fechaini,
            "fechafin": fechafin,
            "iduser": iduser,
            "instruccion_pie": instruccion,
            "ver_planificacion": 0,
            "caso": 0,
            "accion": 1,
        },
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()


def finalizar_unidad(session: requests.Session, id_unidad: int, iduser: str) -> None:
    """Equivalente al botón 'Guardar y regresar' (cierra la unidad)."""
    session.post(
        f"{BASE}/home/planificacion/controladores/controladorAsignacion.php",
        data={"profesor": iduser, "ver_planificacion": 0, "caso": 3},
        headers=HEADERS,
        timeout=30,
    )


def archivo_registro(perfil: str) -> str:
    """CSV donde registrar: uno por docente, siempre dentro de datos\\.

    El docente a quien pertenece el histórico (ver rutas.registro) conserva
    `registro_asignaciones.csv`; los demás escriben el suyo, así no se mezclan
    en un PC compartido.
    """
    return rutas.registro(os.path.splitext(REGISTRO_CSV)[0], perfil)


def registrar_asignacion(
    *, unidad_nombre: str, id_unidad: int, curso: str, idclase: str,
    clase_nombre: str, fecha_clase: str, num_alumnas: int,
    archivo: str = REGISTRO_CSV,
) -> None:
    existe = os.path.exists(archivo)
    with open(archivo, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not existe:
            writer.writerow([
                "fecha_asignacion", "unidad", "idunidad", "curso", "idclase",
                "clase", "fecha_clase", "alumnas_asignadas",
            ])
        writer.writerow([
            datetime.date.today().isoformat(), unidad_nombre, id_unidad, curso,
            idclase, clase_nombre, fecha_clase, num_alumnas,
        ])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hoy",
        action="store_true",
        help="Solo asigna clases cuya fecha de inicio sea hoy.",
    )
    parser.add_argument(
        "--fecha",
        metavar="DD/MM/YYYY",
        help="Solo asigna clases cuya fecha de inicio sea esta (en vez de hoy).",
    )
    parser.add_argument(
        "--dias-atras",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Además de la fecha elegida, recupera las clases de los N días "
            "anteriores que sigan sin asignar. Existe porque la corrida diaria "
            "solo mira el día de hoy: una clase creada después de esa corrida, o "
            "creada más tarde para una fecha ya pasada, quedaba sin asignar para "
            "siempre. No cambia qué se asigna (siempre clases pendientes, con su "
            "propia fecha), solo hasta cuándo se mira hacia atrás."
        ),
    )
    parser.add_argument(
        "--unidades",
        metavar="5BA,6BB,...",
        help="Lista de cursos separados por coma a procesar (por defecto, todas).",
    )
    parser.add_argument(
        "--perfil",
        choices=sorted(PERFILES),
        default=PERFIL_POR_DEFECTO,
        help=(
            "Docente cuyo perfil se ejecuta: su RUT y SUS unidades. "
            f"Por defecto '{PERFIL_POR_DEFECTO}'. Una corrida usa un solo "
            "perfil; nunca se mezclan unidades de dos docentes."
        ),
    )
    parser.add_argument(
        "--guardar-clave",
        action="store_true",
        help=(
            "Guarda la contraseña en el llavero de Windows (Credential Manager) "
            "para que corridas futuras no la pidan por teclado. Pide la clave una "
            "sola vez y termina sin asignar nada."
        ),
    )
    parser.add_argument(
        "--destinos",
        action="store_true",
        help=(
            "Pregunta, unidad por unidad, a dónde asignar sus clases, con la "
            "misma lista que ofrece Webclass (cursos y talleres). Solo pregunta "
            "por las que no estén elegidas; con --rehacer-destinos pregunta todas."
        ),
    )
    parser.add_argument(
        "--rehacer-destinos",
        action="store_true",
        help="Como --destinos, pero vuelve a preguntar también por las ya elegidas.",
    )
    parser.add_argument(
        "--ver-destinos",
        action="store_true",
        help="Muestra a dónde se asigna hoy cada unidad. No escribe nada.",
    )
    parser.add_argument(
        "--simular",
        action="store_true",
        help="Muestra qué clases se asignarían, sin asignar nada (vista previa).",
    )
    parser.add_argument(
        "--seleccion",
        metavar="ARCHIVO.json",
        help="Solo asigna las clases cuyo id esté en {\"claves\": [...]} (lo que se "
             "marcó en la vista previa de la barra).",
    )
    parser.add_argument(
        "--meses",
        metavar="MM/AAAA,MM/AAAA",
        help="Solo asigna las clases pendientes cuya fecha caiga en esos meses (hasta "
             "hoy). Reemplaza a --hoy/--dias-atras.",
    )
    parser.add_argument(
        "--opciones-destino",
        metavar="ID,ID",
        help="Para esas unidades, escribe a dónde se pueden asignar (##OPCIONES). "
             "No escribe nada en Webclass.",
    )
    parser.add_argument(
        "--buscar-unidades",
        action="store_true",
        help="Busca en Webclass unidades que el perfil no conoce y las informa (##ITEM "
             "unidad:<id>). No escribe nada.",
    )
    parser.add_argument(
        "--guardar-unidades",
        action="store_true",
        help="Con --seleccion: las unidades nuevas marcadas (unidad:<id>) se suman al "
             "perfil y las demás se anotan como rechazadas.",
    )
    return parser.parse_args()


GRUPO_UNIDADES = "UNIDADES NUEVAS"
CLAVE_UNIDAD = "unidad:"


def informar_unidad_nueva(u: dict, pendientes: int | None, estado: str = "propuesto",
                          motivo: str = "") -> None:
    cuenta = ("no se pudo contar sus clases" if pendientes is None
              else f"{pendientes} clases pendientes")
    item(f"{CLAVE_UNIDAD}{u['id']}", estado, f"{u['curso']} · {u['nombre']}", GRUPO_UNIDADES,
         "unidad nueva", cuenta, motivo)


def pendientes_de(session: requests.Session, id_unidad: int) -> int | None:
    try:
        return sum(1 for c in listar_clases(session, id_unidad) if c["asignados"] == 0)
    except Exception:  # noqa: BLE001  (contar es solo informativo)
        return None


def unidades_nuevas(perfil_nombre: str, perfil: dict, cursos: set[str] | None = None,
                    forzar: bool = False) -> tuple[list[dict], bool]:
    """Unidades que Webclass ofrece y el perfil no conoce. Un fallo de red no frena la corrida."""
    import unidades
    try:
        nuevas, en_vivo = unidades.buscar_nuevas(perfil_nombre, perfil, forzar=forzar,
                                                 con_origen=True)
    except Exception as exc:  # noqa: BLE001
        print(f"(No pude buscar unidades nuevas: {str(exc)[:80]})")
        return [], False
    if cursos:
        nuevas = [u for u in nuevas if u["curso"] in cursos]
    return nuevas, en_vivo


def usuario_del_libro(session: requests.Session, rut: str) -> str:
    """El nombre de usuario con que se entra al libro de clases (webicp2).

    No se calcula: lo pone el propio Webclass en un formulario oculto de la
    portada del profesor, que es el que usa el botón del menú. Casi siempre es
    el RUT sin dígito verificador, pero no cuando la persona tiene más de una
    cuenta —una ex-alumna a la que después le crean perfil de profesora—:
    ahí el username es otro, y deducirlo del RUT manda al usuario equivocado.
    """
    try:
        pagina = session.get(f"{BASE}/home/portada_profesor.php",
                             headers=HEADERS, timeout=90).text
        m = re.search(r'loginFromWebclass"[^>]*>\s*<input\s+name="username"\s+value="([^"]+)"',
                      pagina)
        if m:
            return m.group(1)
    except requests.RequestException:
        pass
    return rut.split("-")[0]


def por_que_no_entro(resp, portada: str, resp_login=None) -> str:
    """Explica, con lo que devolvió Webclass, por qué no se llegó al libro.

    El libro de clases (webicp2) es un sistema aparte del de planificaciones:
    una cuenta puede entrar perfectamente a uno y no tener acceso al otro, y
    eso antes salía como un «¿cambió Webclass?» que no ayudaba a nadie.

    resp_login es lo que contestó loginFromWebclass, el paso anterior: cuando
    ese no prende, la portada del libro devuelve un redirect al sistema viejo
    y el problema está ahí, no en la portada.
    """
    rastro = os.path.join(carpeta_datos(), "diagnostico_libro.html")
    try:
        with open(rastro, "w", encoding="utf-8") as f:
            f.write("<!-- loginFromWebclass: "
                    f"HTTP {getattr(resp_login, 'status_code', '?')} -->\n"
                    f"{getattr(resp_login, 'text', '')}\n"
                    f"<!-- portada-profesor: HTTP {resp.status_code} {resp.url} -->\n"
                    f"{portada}")
    except OSError:
        rastro = "(no se pudo guardar)"

    texto = portada.lower()
    if resp.status_code >= 500:
        causa = "el libro de clases respondió con un error del servidor; suele ser pasajero."
    elif resp.status_code == 403 or "no tiene permiso" in texto:
        causa = "el libro dice que esa cuenta no tiene permiso para entrar."
    elif "portada_profesor.php" in texto and "location.href" in texto:
        # No es un rechazo: es el libro nuevo mandando de vuelta al antiguo.
        causa = ("el libro nuevo no tomó la sesión y devolvió al sistema antiguo. "
                 "Suele pasar cuando el usuario con que se entra al libro no es el "
                 "mismo con que se entró a Webclass: por ejemplo si esa persona "
                 "tiene más de un perfil (ex-alumna y profesora) con el mismo RUT.")
    elif "password" in texto or "contrase" in texto or "iniciar sesi" in texto:
        causa = ("el libro devolvió su propia pantalla de inicio de sesión. Esa cuenta "
                 "entra a Webclass pero no tiene habilitado el módulo Libro de Clases: "
                 "hay que pedírselo a UTP o a informática del colegio.")
    else:
        causa = ("el libro respondió algo que no reconozco; puede que Webclass haya "
                 "cambiado la página.")
    return (f"No pude entrar al libro de clases: {causa}\n"
            f"  (HTTP {resp.status_code}, terminó en {resp.url})\n"
            f"  Guardé lo que respondió en: {rastro}")


def obtener_password(rut: str = RUT_USUARIO) -> str:
    guardada = keyring.get_password(KEYRING_SERVICE, rut)
    if guardada:
        return guardada
    return getpass.getpass(f"Contraseña Webclass para el usuario {rut}: ")


def verificar_sesion(session: requests.Session, perfil: str, iduser_esperado: str) -> None:
    """Confirma que la sesión abierta es la del perfil que se va a ejecutar.

    Es el seguro contra el error más caro al manejar dos docentes: correr el
    perfil de uno con la sesión del otro y escribir en unidades ajenas. Aborta
    antes de tocar nada.
    """
    resp = session.get(
        f"{BASE}/home/planificacion/index.php", params={"wc": 1},
        headers=HEADERS, timeout=90,
    )
    m = re.search(r'id="iduser"[^>]*value="([^"]*)"', resp.text)
    if not m:
        raise RuntimeError(
            "No se pudo leer el usuario de la sesión para verificar el perfil. "
            "Puede que la sesión no se haya iniciado bien o que Webclass haya "
            "cambiado la página."
        )
    real = m.group(1)
    if real != iduser_esperado:
        raise RuntimeError(
            f"PERFIL EQUIVOCADO: se pidió el perfil '{perfil}' (usuario "
            f"{iduser_esperado}) pero la sesión abierta es del usuario {real}. "
            "Se aborta sin escribir nada para no tocar unidades de otro docente."
        )
    print(f"Perfil '{perfil}' verificado (usuario {real}).")


def main() -> None:
    args = parse_args()

    perfil_nombre = args.perfil
    perfil = PERFILES[perfil_nombre]
    rut = perfil["rut"]
    if not rut:
        raise ValueError(
            f"El perfil '{perfil_nombre}' todavía no tiene RUT configurado. "
            "Vuelve a correr configurar.py."
        )

    if args.guardar_clave:
        clave = getpass.getpass(
            f"Contraseña Webclass del usuario {rut} (perfil '{perfil_nombre}'; "
            "se guardará en el llavero de Windows): "
        )
        keyring.set_password(KEYRING_SERVICE, rut, clave)
        print("Contraseña guardada en el Credential Manager de Windows.")
        return

    if args.ver_destinos:
        elegidos = destinos_elegidos()
        print("\n=== A dónde se asigna cada unidad ===\n")
        for info in perfil["unidades"]:
            e = elegidos.get(str(info["id"]))
            donde = e["nombre"] if e else f"{info['curso']} (por defecto)"
            print(f"  {info['curso']:>14}  {info['nombre'][:44]:46} -> {donde}")
        print(f"\n  Elegidos a mano: {len(elegidos)}. Para cambiarlos: --destinos")
        return

    if args.destinos or args.rehacer_destinos:
        session = crear_session()
        login(session, rut, obtener_password(rut))
        verificar_sesion(session, perfil_nombre, perfil["iduser"])
        elegir_destinos(session, perfil, solo_nuevas=not args.rehacer_destinos)
        return

    if args.opciones_destino:
        session = crear_session()
        login(session, rut, obtener_password(rut))
        verificar_sesion(session, perfil_nombre, perfil["iduser"])
        opciones_de_unidades(session, perfil,
                             [i.strip() for i in args.opciones_destino.split(",") if i.strip()])
        return

    seleccion = leer_seleccion(args.seleccion)

    if args.guardar_unidades:
        import unidades as U
        nuevas, _ = unidades_nuevas(perfil_nombre, perfil)
        elegidas = [u["id"] for u in nuevas if f"{CLAVE_UNIDAD}{u['id']}" in (seleccion or set())]
        rechazadas = [u["id"] for u in nuevas if u["id"] not in elegidas]
        U.decidir(perfil_nombre, perfil, nuevas, elegidas, rechazadas)
        print(f"Unidades incluidas: {len(elegidas)} · rechazadas (no se vuelve a preguntar): "
              f"{len(rechazadas)}")
        return

    if args.buscar_unidades:
        session = crear_session()
        login(session, rut, obtener_password(rut))
        verificar_sesion(session, perfil_nombre, perfil["iduser"])
        nuevas, _ = unidades_nuevas(perfil_nombre, perfil, forzar=True)
        print(f"\n=== Unidades nuevas en Webclass: {len(nuevas)} ===")
        for u in nuevas:
            informar_unidad_nueva(u, pendientes_de(session, u["id"]))
            print(f"  {u['curso']} · {u['nombre']}")
        if not nuevas:
            print("  Tu perfil ya tiene todas las unidades que ofrece Webclass.")
        return

    unidades_perfil = perfil["unidades"]
    curso_ids = perfil["curso_ids"]
    if not unidades_perfil:
        raise ValueError(
            f"El perfil '{perfil_nombre}' no tiene unidades configuradas. "
            "Vuelve a correr configurar.py."
        )

    unidades = unidades_perfil
    if args.unidades:
        cursos = {c.strip().upper() for c in args.unidades.split(",")}
        desconocidos = cursos - {u["curso"] for u in unidades_perfil}
        if desconocidos:
            raise ValueError(
                f"Curso(s) desconocido(s) en el perfil '{perfil_nombre}': "
                f"{', '.join(sorted(desconocidos))}"
            )
        unidades = [u for u in unidades_perfil if u["curso"] in cursos]

    # Con --dias-atras, el filtro deja de ser una sola fecha y pasa a ser el
    # conjunto de días desde el que se recupera hacia atrás. El criterio sigue
    # siendo el mismo (clases pendientes, cada una con su propia fecha); lo
    # único que cambia es cuántos días se miran.
    fechas_filtro = None
    if args.meses:
        fechas_filtro = dias_de_meses(args.meses)
        print(f"Meses elegidos: {args.meses}")
    elif args.fecha or args.hoy:
        if args.fecha:
            base = datetime.datetime.strptime(args.fecha, "%d/%m/%Y").date()
        else:
            base = datetime.date.today()
        fechas_filtro = {
            (base - datetime.timedelta(days=n)).strftime("%d/%m/%Y")
            for n in range(max(args.dias_atras, 0) + 1)
        }

    inicio_corrida = datetime.datetime.now()
    print(f"=== Corrida iniciada: {inicio_corrida.strftime('%d/%m/%Y %H:%M:%S')} "
          f"| perfil: {perfil_nombre} ===")

    password = obtener_password(rut)

    session = crear_session()
    print("Iniciando sesión...")
    login(session, rut, password)
    verificar_sesion(session, perfil_nombre, perfil["iduser"])
    print("Sesión iniciada.\n")

    registro = archivo_registro(perfil_nombre)
    elegidos = destinos_elegidos()
    import barra_utiles as bu
    sin_clases = bu.leer_sin_clases(rutas.sin_clases(perfil_nombre))

    # Unidades que el perfil no conoce. En la vista previa se muestran todas con casilla;
    # en la corrida real solo entran las marcadas (y se guardan en el perfil). Sin vista
    # previa (corrida automática) no se incluye nada sin que el docente lo decida.
    nuevas, en_vivo = unidades_nuevas(perfil_nombre, perfil,
                                      {c.strip().upper() for c in args.unidades.split(",")}
                                      if args.unidades else None)
    curso_ids = dict(curso_ids)
    nuevas_ids = set()
    if nuevas and args.simular:
        incluidas = nuevas
    elif nuevas and seleccion is not None:
        import unidades as U
        marcadas = [u for u in nuevas if f"{CLAVE_UNIDAD}{u['id']}" in seleccion]
        # Lo no marcado se rechaza solo si es la misma lista de la vista previa (aún en caché).
        rechazadas = [] if en_vivo else [u["id"] for u in nuevas if u not in marcadas]
        U.decidir(perfil_nombre, perfil, nuevas, [u["id"] for u in marcadas], rechazadas)
        incluidas = marcadas
    else:
        incluidas = []
        for u in nuevas:
            informar_unidad_nueva(u, None, "pendiente",
                                  "unidad nueva sin revisar: usa «Asignar» con vista previa")
    for u in incluidas:
        curso_ids.setdefault(u["curso"], u.get("curso_id"))
        nuevas_ids.add(str(u["id"]))
    unidades = list(unidades) + [{"curso": u["curso"], "id": u["id"], "nombre": u["nombre"]}
                                 for u in incluidas]

    resumen = []

    for n_unidad, info in enumerate(unidades, 1):
        curso = info["curso"]
        id_unidad = info["id"]
        # La barra lee estas líneas para mover su barra de carga.
        print(f"##PROGRESO {n_unidad - 1}/{len(unidades)} {curso}", flush=True)
        # El destino puede no ser el curso de la unidad: hay unidades de un
        # curso que se asignan a otro, y talleres que son solo una sección.
        elegido = elegidos.get(str(id_unidad))
        idcurso = elegido["id"] if elegido else curso_ids[curso]
        donde = f" -> {elegido['nombre']}" if elegido else ""
        print(f"=== {curso}: {info['nombre']} (unidad {id_unidad}){donde} ===")

        clases = listar_clases(session, id_unidad)
        es_nueva = str(id_unidad) in nuevas_ids
        if es_nueva:
            informar_unidad_nueva(info, sum(1 for c in clases if c["asignados"] == 0),
                                  "propuesto" if args.simular else "hecho")
            if not clases:
                print("  (La unidad nueva aún no tiene clases.)")
                continue

        # Una unidad sin NINGUNA clase no es un caso normal: significa que la
        # sesión se cayó (Webclass devuelve la página de login) o que cambió el
        # HTML y los regex dejaron de calzar. Sin este chequeo el script
        # reportaría "0 pendientes" y terminaría "exitoso" sin asignar nada.
        if not clases:
            raise RuntimeError(
                f"La unidad {curso} ({info['nombre']}, id {id_unidad}) devolvió "
                "CERO clases. Esto casi siempre significa que la sesión expiró o "
                "que Webclass cambió el HTML; NO que esté todo asignado. "
                "Revisar manualmente antes de confiar en esta corrida."
            )

        pendientes = [c for c in clases if c["asignados"] == 0]
        if fechas_filtro:
            pendientes = [c for c in pendientes if c["fechaini"] in fechas_filtro]
        # Feriados, vacaciones…: lo que el docente marcó como «no hubo clase» no se asigna ni se vuelve a ofrecer.
        no_hubo = [c for c in pendientes if bu.clase_sin_tarea(sin_clases, c["idclase"], c["fechaini"])]
        for c in no_hubo:
            print(f"  [SIN CLASES] {c['nombre']}: marcaste que no hubo esa clase ({c['fechaini'] or 'sin fecha'}).")
        pendientes = [c for c in pendientes if c not in no_hubo]
        print(f"  {len(clases)} clases, {len(pendientes)} pendientes de asignar."
              + (f" ({len(no_hubo)} sin clase: no se asignan)" if no_hubo else ""))

        procesadas = 0
        for clase in pendientes:
            idclase = clase["idclase"]
            nombre = clase["nombre"]
            fechaini = clase["fechaini"]
            fechafin = clase["fechafin"]
            titulo = f"{curso} · {nombre}"
            dia = bu.fecha_de_estado(fechaini)
            marca = {"campo": "clases", "clave": str(idclase), "dia": dia.isoformat() if dia else "",
                     "titulo": f"{titulo} ({fechaini})" if fechaini else titulo}

            if seleccion is not None and str(idclase) not in seleccion:
                print(f"  Omitida por ti: {nombre}")
                item(idclase, "omitido", titulo, curso, "asignación")
                resumen.append((curso, nombre, "omitida por ti"))
                continue
            procesadas += 1

            if not fechaini or not fechafin:
                print(f"  [SALTADA] {nombre}: sin fecha de inicio/término definida.")
                item(idclase, "pendiente", titulo, curso, "asignación",
                     motivo="sin fecha de inicio/término definida", sin_clase=marca)
                resumen.append((curso, nombre, "SALTADA (sin fechas)"))
                continue

            datos = datos_clase(session, idclase, id_unidad)
            alumnas = listar_alumnas(
                session, idclase, idcurso, datos["idcolegio"], datos["idprofesor"]
            )

            if not alumnas:
                print(f"  [SALTADA] {nombre}: no se encontraron alumnas en {curso}.")
                item(idclase, "pendiente", titulo, curso, "asignación",
                     motivo=f"no se encontraron alumnas en {curso}", sin_clase=marca)
                resumen.append((curso, nombre, "SALTADA (sin alumnas)"))
                continue

            detalle = f"{len(alumnas)} alumnas ({fechaini} - {fechafin})"
            if args.simular:
                print(f"  [SIMULAR] {nombre}: se asignaría a {len(alumnas)} alumnas "
                      f"({fechaini} - {fechafin}).")
                item(idclase, "propuesto", titulo, curso, "asignación", detalle, sin_clase=marca)
                resumen.append((curso, nombre, f"se asignaría ({len(alumnas)} alumnas)"))
                continue

            asignar_tarea(
                session,
                idclase=idclase,
                idcurso=idcurso,
                idcolegio=datos["idcolegio"],
                idprofesor=datos["idprofesor"],
                iduser=datos["iduser"],
                alumnas=alumnas,
                instruccion=nombre,
                fechaini=fechaini,
                fechafin=fechafin,
            )
            print(f"  [OK] {nombre}: asignada a {len(alumnas)} alumnas ({fechaini} - {fechafin}).")
            item(idclase, "hecho", titulo, curso, "asignación", detalle)
            resumen.append((curso, nombre, f"OK ({len(alumnas)} alumnas)"))
            registrar_asignacion(
                unidad_nombre=info["nombre"], id_unidad=id_unidad, curso=curso,
                idclase=idclase, clase_nombre=nombre, fecha_clase=fechaini,
                num_alumnas=len(alumnas), archivo=registro,
            )

        if procesadas and not args.simular:
            iduser = datos_clase(session, pendientes[0]["idclase"], id_unidad)["iduser"]
            finalizar_unidad(session, id_unidad, iduser)

        print()
        print(f"##PROGRESO {n_unidad}/{len(unidades)} {curso}", flush=True)

    print("=== Resumen ===")
    for curso, nombre, estado in resumen:
        print(f"  {curso} | {nombre} -> {estado}")

    if not resumen:
        print("  No había clases pendientes de asignar en ninguna unidad.")
    if not args.simular:
        imprimir_resultado(ITEMS, vacio="No había clases pendientes de asignar en ninguna unidad.")

    fin_corrida = datetime.datetime.now()
    duracion = (fin_corrida - inicio_corrida).total_seconds()
    print(
        f"\n=== Corrida exitosa: {fin_corrida.strftime('%d/%m/%Y %H:%M:%S')} "
        f"(duró {duracion:.1f}s) ==="
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        momento = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        print(f"\n=== Corrida FALLIDA: {momento} — {exc} ===", file=sys.stderr)
        sys.exit(1)
