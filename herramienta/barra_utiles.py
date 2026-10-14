"""
Funciones de la barra que no dependen de la ventana: se pueden probar solas.

barra_profe.pyw se ocupa de dibujar; aquí vive lo que se puede calcular sin
abrir ninguna ventana (horas, rutas, comandos, estados). Los tests están en
tests\\test_barra_utiles.py.
"""

from __future__ import annotations

import ctypes
import datetime
import json
import os
import re
import shlex


# -------------------------------------------------------------------- archivos
def escribir_atomico(ruta: str, texto: str) -> None:
    """Guarda un archivo sin dejarlo a medias si el PC se corta a mitad.

    Escribe en un temporal del mismo directorio y lo cambia por el original
    de una sola vez.
    """
    temporal = f"{ruta}.tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporal, ruta)


# ---------------------------------------------------------------------- horario
def minutos(hhmm: str) -> int:
    """'08:30' -> 510."""
    hora, _, minuto = hhmm.partition(":")
    return int(hora) * 60 + int(minuto or 0)


def ahora_y_luego(bloques: list[dict],
                  ahora: datetime.datetime | None = None) -> tuple[str, str]:
    """Qué está pasando y qué viene, para la cabecera de la barra."""
    ahora = ahora or datetime.datetime.now()
    minuto = ahora.hour * 60 + ahora.minute
    if not bloques:
        return "", "Hoy no hay clases"
    actual = siguiente = None
    for bloque in bloques:
        inicio, fin = minutos(bloque.get("inicio", "0:00")), minutos(bloque.get("fin", "0:00"))
        if inicio <= minuto < fin:
            actual = bloque
        elif inicio > minuto and siguiente is None:
            siguiente = bloque
    texto_ahora = f"{actual['titulo']} · hasta {actual['fin']}" if actual else "Libre"
    if siguiente:
        texto_luego = f"{siguiente['titulo']} {siguiente['inicio']}"
    else:
        texto_luego = "Nada más por hoy"
    return texto_ahora, texto_luego


def saludo_para(nombre: str, ahora: datetime.datetime | None = None) -> str:
    """Buenos días / tardes / noches, según la hora."""
    hora = (ahora or datetime.datetime.now()).hour
    if 5 <= hora < 12:
        momento = "Buenos días"
    elif 12 <= hora < 20:
        momento = "Buenas tardes"
    else:
        momento = "Buenas noches"
    return f"{momento}, {nombre}" if nombre else momento


# ----------------------------------------------------------------------- libro
def estado_vencido(estado: dict | None, edad_segundos: float, hoy: str,
                   minutos_validez: int = 20) -> bool:
    """True si hay que volver a revisar el libro de clases.

    `estado` es el contenido de estado_firmas.json (None si no se pudo leer),
    `edad_segundos` cuánto hace que se guardó y `hoy` la fecha como dd/mm/aaaa.
    Si la última revisión falló se reintenta mucho antes que en el ciclo normal.
    """
    if not isinstance(estado, dict) or estado.get("fecha") != hoy:
        return True
    return edad_segundos > (3 * 60 if estado.get("error") else minutos_validez * 60)


# ---------------------------------------------------------------------- botones
def leer_version(carpeta: str) -> str:
    """Versión del archivo VERSION de esa carpeta ('' si falta o no tiene el formato MAYOR.MENOR.PARCHE)."""
    try:
        with open(os.path.join(carpeta, "VERSION"), encoding="utf-8-sig") as f:
            texto = f.read().strip()
    except OSError:
        return ""
    return texto if re.fullmatch(r"\d+\.\d+\.\d+", texto) else ""


def reemplazar_variables(destino: str, variables: dict[str, str]) -> str:
    """Cambia %BARRA%, %WEBCLASS%… y después las variables de Windows."""
    for marca, valor in variables.items():
        destino = destino.replace(marca, valor)
    return os.path.expandvars(destino)


def partes_de_comando(texto: str) -> list[str]:
    """Parte «subcomando --opcion valor» respetando comillas (rutas con espacios)."""
    partes = [p.strip('"') for p in shlex.split(texto, posix=False)]
    if not partes:
        raise ValueError("el botón no indica qué subcomando de Webclass ejecutar")
    return partes


# ---------------------------------------------------------------------- consola
_SIN_PROBLEMA = re.compile(r"\b(0|cero|sin|ningun[oa]?)\s+(error|pendiente|falta|fallo)")
_LISTO = re.compile(r"\blisto\b")
_AVISO = re.compile(r"\b(pendiente|falta|faltan|blanco)")
_ERROR = re.compile(r"\b(error|errores|fallida|fallo)\b")


def etiqueta_de_linea(linea: str) -> str:
    """Color de una línea de la consola: 'ok', 'aviso', 'error' o '' (sin color)."""
    bajo = linea.lower()
    # "0 errores" o "sin pendientes" son buenas noticias: no se tiñen de alerta.
    if "[ok]" in bajo or "exitosa" in bajo or _LISTO.search(bajo) or _SIN_PROBLEMA.search(bajo):
        return "ok"
    if _AVISO.search(bajo):
        return "aviso"
    if _ERROR.search(bajo):
        return "error"
    return ""


# ------------------------------------------------------------------- actividades
# Estados de una actividad: lo que la barra le cuenta al docente al pulsar un botón.
ESTADOS = {
    "proceso":    {"icono": "◐", "texto": "En proceso"},
    "completado": {"icono": "✓", "texto": "Completado"},
    "avisos":     {"icono": "⚠", "texto": "Con avisos"},
    "error":      {"icono": "✕", "texto": "Con error"},
    "cancelado":  {"icono": "■", "texto": "Cancelado"},
}

_MARCA = re.compile(r"^\s*\[(OK|YA|SALTADA|PENDIENTE|ERROR|SIMULAR|ASISTENCIA EN BLANCO)\]",
                    re.IGNORECASE)
_PROGRESO = re.compile(r"^\s*##PROGRESO\s+(\d+)\s*/\s*(\d+)\s*(.*)$")


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def resumir_ejecucion(codigo: int | None, lineas: list[str],
                      cancelada: bool = False, items: list[dict] | None = None) -> dict:
    """Estado final y resumen en lenguaje simple de lo que hizo un script.

    Cuenta las marcas [OK] / [YA] / [SALTADA] / [PENDIENTE] / [ERROR] que
    imprimen las herramientas de Webclass; si el script informó `##ITEM`
    (ver `parsear_item`), se cuenta por ítems, que es más preciso. El estado
    sale del código de salida y de eso: si algo quedó sin hacer no se dice
    "Completado", y si el script falló tampoco.
    """
    cuentas = {"ok": 0, "ya": 0, "saltada": 0, "pendiente": 0, "error": 0, "omitida": 0}
    if items:
        equivalente = {"hecho": "ok", "ya": "ya", "pendiente": "pendiente",
                       "error": "error", "omitido": "omitida"}
        for it in items:
            if it["estado"] in equivalente:
                cuentas[equivalente[it["estado"]]] += 1
    else:
        for linea in lineas:
            m = _MARCA.match(linea)
            if m:
                clave = m.group(1).lower()
                clave = "pendiente" if clave == "asistencia en blanco" else clave
                if clave in cuentas:
                    cuentas[clave] += 1
    if cancelada:
        estado = "cancelado"
    elif (codigo not in (0, None)) or cuentas["error"]:
        estado = "error"
    elif cuentas["saltada"] or cuentas["pendiente"]:
        estado = "avisos"
    else:
        estado = "completado"

    partes = []
    if cuentas["ok"]:
        partes.append(_plural(cuentas["ok"], "correcta", "correctas"))
    if cuentas["ya"]:
        partes.append(_plural(cuentas["ya"], "ya estaba", "ya estaban"))
    if cuentas["saltada"]:
        partes.append(_plural(cuentas["saltada"], "saltada", "saltadas"))
    if cuentas["pendiente"]:
        partes.append(_plural(cuentas["pendiente"], "pendiente", "pendientes"))
    if cuentas["omitida"]:
        partes.append(_plural(cuentas["omitida"], "omitida por ti", "omitidas por ti"))
    if cuentas["error"]:
        partes.append(_plural(cuentas["error"], "con error", "con error"))
    if estado == "cancelado":
        resumen = "Detenido antes de terminar"
    elif estado == "error" and codigo not in (0, None) and not cuentas["error"]:
        resumen = f"Terminó con error (código {codigo})"
    elif partes:
        resumen = " · ".join(partes)
    else:
        resumen = "Terminó sin novedades"
    return {"estado": estado, "resumen": resumen, **cuentas}


def parsear_progreso(linea: str) -> tuple[int, int, str] | None:
    """'##PROGRESO 3/8 6BA' -> (3, 8, '6BA'); None si la línea no es de progreso."""
    m = _PROGRESO.match(linea)
    if not m:
        return None
    hecho, total = int(m.group(1)), int(m.group(2))
    if total <= 0:
        return None
    return min(hecho, total), total, m.group(3).strip()


# Causa conocida -> qué le pasó y qué hacer, sin jerga.
_ERRORES = (
    (re.compile(r"usuario incorrecto|contrase[ñn]a incorrecta|credenciales", re.I),
     "Webclass no aceptó tu usuario o contraseña. Revisa tu RUT y tu clave "
     "(botón «Cambiar de profesor» o configurar.py)."),
    (re.compile(r"iduser|no calza|no coincide", re.I),
     "La sesión de Webclass no es la del docente activo. Cambia de profesor "
     "o vuelve a configurar el perfil."),
    (re.compile(r"timed? ?out|connection|conexi[oó]n|max retries|reset by peer|"
                r"remotedisconnected|name resolution", re.I),
     "Webclass no respondió o se cortó la conexión. Revisa tu internet y "
     "vuelve a intentarlo en un momento."),
    (re.compile(r"no se encontr[oó]|no existe|filenotfound|no such file", re.I),
     "Falta un archivo o carpeta que la herramienta necesita. Revisa el "
     "registro para ver cuál."),
    (re.compile(r"permission|permiso|access is denied|acceso denegado", re.I),
     "Windows no dejó acceder a un archivo. Ciérralo si lo tienes abierto "
     "(por ejemplo un .csv en Excel) y reintenta."),
)


def traducir_error(lineas: list[str]) -> str | None:
    """Explicación amable de un fallo conocido, mirando las últimas líneas."""
    texto = "\n".join(lineas[-40:])
    for patron, mensaje in _ERRORES:
        if patron.search(texto):
            return mensaje
    return None


def formatear_duracion(segundos: float) -> str:
    """45 -> '45 s'; 125 -> '2 min 5 s'."""
    segundos = max(0, int(round(segundos)))
    if segundos < 60:
        return f"{segundos} s"
    minutos_, resto = divmod(segundos, 60)
    return f"{minutos_} min" + (f" {resto} s" if resto else "")


def hace_cuanto(momento: datetime.datetime,
                ahora: datetime.datetime | None = None) -> str:
    """'hace 5 min', 'hoy 14:32', 'ayer 18:10' o '03/10 14:32'."""
    ahora = ahora or datetime.datetime.now()
    diferencia = (ahora - momento).total_seconds()
    if diferencia < 45:
        return "hace un momento"
    if diferencia < 3600:
        return f"hace {int(diferencia // 60) or 1} min"
    dias = (ahora.date() - momento.date()).days
    if dias == 0:
        return f"hoy {momento:%H:%M}"
    if dias == 1:
        return f"ayer {momento:%H:%M}"
    return f"{momento:%d/%m} {momento:%H:%M}"


def cargar_ejecuciones(ruta: str) -> dict:
    """Últimos resultados por botón ({} si el archivo no existe o está dañado)."""
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar_ejecucion(ruta: str, boton: str, estado: str, resumen: str,
                      duracion: float, momento: datetime.datetime | None = None) -> dict:
    """Anota el último resultado de un botón y devuelve todo el registro."""
    datos = cargar_ejecuciones(ruta)
    datos[boton] = {"estado": estado, "resumen": resumen,
                    "duracion": round(duracion, 1),
                    "hora": (momento or datetime.datetime.now()).isoformat(timespec="seconds")}
    escribir_atomico(ruta, json.dumps(datos, ensure_ascii=False, indent=1))
    return datos


# ------------------------------------------------------------- vista previa
# Antes de escribir en Webclass, la barra le muestra al docente qué va a pasar.
# Cada función devuelve {"titulo", "puntos", "aviso", "hay_trabajo"}:
#   puntos       lista de frases cortas ("5BA 09:40 · falta OA")
#   aviso        una frase de contexto o advertencia ("" si no hay)
#   hay_trabajo  True / False, o None si no se puede saber de antemano
# Debe coincidir con webclass_recursos.SUBCATEGORIA (una prueba lo comprueba): lo que la barra se anima a subir.
EXTENSIONES_RECURSOS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                        ".jpg", ".jpeg", ".png", ".mp3", ".wav", ".mp4")


def _item(clave: str, titulo: str, grupo: str = "", detalle: str = "") -> dict:
    return {"clave": clave, "titulo": titulo, "grupo": grupo, "detalle": detalle}


def clave_de_bloque(b: dict) -> str:
    """La clave que usan la casilla y la herramienta para el mismo bloque."""
    base = f"{b.get('curso', '?')}|{b.get('hora', '')}"
    return f"{base}|{b['id']}" if b.get("id") not in (None, "") else base


def vista_previa_libro(estado: dict | None, hoy: str) -> dict:
    """Qué completaría «Registrar libro», según la última revisión del libro."""
    titulo = "Registrar el libro de hoy"
    if not isinstance(estado, dict) or estado.get("fecha") != hoy or estado.get("error"):
        return {"titulo": titulo, "puntos": [], "items": [], "hay_trabajo": None,
                "aviso": "Todavía no tengo una revisión de hoy. La herramienta "
                         "revisará los bloques al empezar."}
    revisado = str(estado.get("revisado", ""))
    hora = revisado.split(" ")[-1] if " " in revisado else ""
    origen = f"Según la revisión de las {hora}." if hora else "Según la última revisión."
    puntos, items = [], []
    for b in estado.get("sin_registro", []):
        faltan = []
        if not b.get("oa", True):
            faltan.append("OA")
        if not b.get("leccionario", True):
            faltan.append("leccionario")
        if not b.get("asistencia", True):
            faltan.append("asistencia (se copia del bloque anterior)")
        inicio = str(b.get("hora", "")).split("-")[0]
        detalle = f"se completará: {', '.join(faltan) or 'revisión'}"
        puntos.append(f"{b.get('curso', '?')} {inicio} · {detalle}")
        asignatura = str(b.get("asignatura", "") or "")
        items.append(_item(clave_de_bloque(b),
                           f"{b.get('curso', '?')} {inicio}" + (f" · {asignatura}" if asignatura else ""),
                           str(b.get("curso", "")), detalle))
    por_firmar = len(estado.get("sin_firmar", []))
    firma = (f" Quedarán {por_firmar} bloque{'s' if por_firmar != 1 else ''} por firmar: "
             "la firma la haces tú." if por_firmar else "")
    if not puntos:
        return {"titulo": titulo, "puntos": ["Todo lo de hoy ya está registrado."], "items": [],
                "hay_trabajo": False, "aviso": origen + firma}
    return {"titulo": titulo, "puntos": puntos, "items": items, "hay_trabajo": True,
            "aviso": origen + firma}


# Asignaturas con que se puede firmar un recurso al subirlo (la clave es la de webclass_recursos.ASIGNATURAS).
ASIGNATURAS_SUBIDA = (("ciencias", "Ciencias Naturales"), ("matematica", "Matemática"),
                      ("lenguaje", "Lenguaje y Comunicación"), ("historia", "Historia, Geografía y Cs. Sociales"),
                      ("orientacion", "Orientación"), ("tecnologia", "Tecnología"), ("biologia", "Biología"),
                      ("quimica", "Química"), ("fisica", "Física"))


def _sin_tildes(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn").lower()


def asignatura_sugerida(perfil: dict) -> str:
    """Clave de la asignatura que más dicta el docente (la de su perfil); «ciencias» si no se sabe."""
    cuenta: dict[str, int] = {}
    for nombre in (perfil.get("curso_asignaturas") or {}).values():
        n = _sin_tildes(nombre)
        cuenta[n] = cuenta.get(n, 0) + 1
    principal = max(cuenta, key=cuenta.get) if cuenta else ""
    # La palabra que aparece primero manda: «Historia, Geografía y Ciencias Sociales» es Historia, no Ciencias.
    encontradas = [(principal.index(clave), clave) for clave, _ in ASIGNATURAS_SUBIDA if clave in principal]
    return min(encontradas)[1] if encontradas else "ciencias"


def ruta_preferencia_subida(personal: str, perfil: str) -> str:
    """Un archivo por cuenta: así lo que elige un docente no cambia lo de otro."""
    return os.path.join(personal, f"subida_{perfil}.json")


def leer_preferencia_subida(ruta: str) -> dict:
    """{'asignatura': clave o '', 'preguntar': bool}. Sin archivo o roto: no hay preferencia y se pregunta."""
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        datos = {}
    if not isinstance(datos, dict):
        datos = {}
    clave = datos.get("asignatura") if datos.get("asignatura") in dict(ASIGNATURAS_SUBIDA) else ""
    return {"asignatura": clave, "preguntar": not (clave and datos.get("preguntar") is False)}


def guardar_preferencia_subida(ruta: str, asignatura: str, preguntar: bool) -> None:
    if asignatura not in dict(ASIGNATURAS_SUBIDA):
        raise ValueError(f"Asignatura desconocida: {asignatura}")
    escribir_atomico(ruta, json.dumps({"asignatura": asignatura, "preguntar": bool(preguntar)}, ensure_ascii=False, indent=2))


def vista_previa_subir(buzon: str) -> dict:
    """Qué subiría «Subir recursos»: los archivos que hay en cada carpeta de nivel."""
    titulo = "Subir recursos a Webclass"
    puntos, items, no_admitidos = [], [], 0
    try:
        niveles = sorted(d for d in os.listdir(buzon)
                         if not d.startswith("_") and os.path.isdir(os.path.join(buzon, d)))
    except OSError:
        return {"titulo": titulo, "puntos": [], "items": [], "hay_trabajo": None,
                "aviso": "No encuentro la carpeta «Subir a Webclass»."}
    for nivel in niveles:
        archivos = [a for a in os.listdir(os.path.join(buzon, nivel))
                    if os.path.isfile(os.path.join(buzon, nivel, a))
                    and not a.startswith(("~$", "."))]
        buenos = [a for a in archivos if a.lower().endswith(EXTENSIONES_RECURSOS)]
        no_admitidos += len(archivos) - len(buenos)
        if buenos:
            muestra = ", ".join(buenos[:2]) + (f" y {len(buenos) - 2} más" if len(buenos) > 2 else "")
            puntos.append(f"{nivel}: {_plural(len(buenos), 'archivo', 'archivos')} ({muestra})")
            items += [_item(f"{nivel}/{a}", a, nivel) for a in buenos]
    aviso = (f"{_plural(no_admitidos, 'archivo tiene', 'archivos tienen')} un formato que no "
             f"se sube (se aceptan {', '.join(e[1:] for e in EXTENSIONES_RECURSOS)})." if no_admitidos else "")
    if not puntos:
        return {"titulo": titulo, "puntos": ["No hay archivos nuevos para subir."], "items": [],
                "hay_trabajo": False, "aviso": aviso}
    return {"titulo": titulo, "puntos": puntos, "items": items, "hay_trabajo": True,
            "aviso": aviso}


def vista_previa_simulacion(titulo: str, lineas: list[str], codigo: int | None = 0,
                            items: list[dict] | None = None) -> dict:
    """Vista previa a partir de la salida de una herramienta en modo `--simular`.

    Si la herramienta informó `##ITEM propuesto`, esos son los ítems que se
    pueden marcar o desmarcar; si no, solo se listan las líneas [SIMULAR].
    """
    puntos, saltadas = [], 0
    for linea in lineas:
        m = re.match(r"^\s*\[SIMULAR\]\s*(.*)$", linea, re.IGNORECASE)
        if m:
            puntos.append(m.group(1).strip()[:90])
        elif re.match(r"^\s*\[SALTADA\]", linea, re.IGNORECASE):
            saltadas += 1
    propuestos = [_item(i["clave"], i["titulo"], i["grupo"], i["detalle"])
                  for i in (items or []) if i["estado"] == "propuesto"]
    no_pude = [i for i in (items or []) if i["estado"] in ("pendiente", "error")]
    if codigo not in (0, None):
        return {"titulo": titulo, "puntos": [], "items": [], "hay_trabajo": None,
                "aviso": traducir_error(lineas) or "No pude calcular la vista previa."}
    if items:
        puntos = [f"{i['titulo']}: {i['detalle']}" if i["detalle"] else i["titulo"]
                  for i in propuestos]
        saltadas = len(no_pude)
    aviso = f"{_plural(saltadas, 'clase se saltará', 'clases se saltarán')} (falta algún dato)." \
        if saltadas else ""
    firmas = contar_firmas(lineas)
    if firmas and propuestos:
        aviso = (aviso + " " if aviso else "") + (
            f"Quedarán {_plural(firmas, 'bloque', 'bloques')} por firmar: la firma la haces tú.")
    if not puntos:
        return {"titulo": titulo, "puntos": ["No hay nada pendiente por hacer."], "items": [],
                "hay_trabajo": False, "aviso": aviso}
    return {"titulo": titulo, "puntos": puntos, "items": propuestos, "hay_trabajo": True,
            "aviso": aviso}


def contar_firmas(lineas: list[str]) -> int:
    """Cuántos bloques lista la herramienta bajo «FALTA TU FIRMA en:»."""
    cuenta, leyendo = 0, False
    for linea in lineas:
        if linea.strip() == "FALTA TU FIRMA en:":
            leyendo = True
        elif leyendo:
            if linea.startswith("    ") and linea.strip():
                cuenta += 1
            elif linea.strip():
                leyendo = False
    return cuenta


# ------------------------------------------------------------------------- tour
TOUR_VERSION = 1
TOUR_PASOS = (
    {"id": "barra", "titulo": "Tu barra",
     "texto": "Se esconde en el borde de la pantalla. Un clic en la lengüeta la abre, "
              "Escape la esconde y la ✕ la cierra. Arrastra esta cabecera para moverla."},
    {"id": "hoy", "titulo": "Tu día",
     "texto": "Aquí ves qué clase tienes ahora y cuál viene. Debajo está el estado de tu "
              "libro: bloques sin firmar o sin registrar."},
    {"id": "lista", "titulo": "Tu lista",
     "texto": "Anota pendientes, márcalos con un clic y bórralos con la ✕. Se guarda sola "
              "en este equipo."},
    {"id": "notas", "titulo": "Notas rápidas",
     "texto": "Escribe aquí algo para tu asistente y aprieta Enter: él lo agenda o lo "
              "anota como tarea."},
    {"id": "botones", "titulo": "Los botones",
     "texto": "Cada botón hace una tarea. Al pulsarlo ves una barra de carga y su estado: "
              "◐ en proceso, ✓ listo, ⚠ con avisos, ✕ error. Antes de escribir en Webclass "
              "te muestro una vista previa con casillas: marcas lo que quieres que se aplique "
              "y lo demás no se toca."},
    {"id": "pie", "titulo": "Si algo falla",
     "texto": "«Ver registro» y «Editar botones» ayudan cuando algo no sale. Puedes repetir "
              "este recorrido cuando quieras con «Ver tour»."},
)


def tour_pendiente(ruta: str, version: int = TOUR_VERSION) -> bool:
    """True si este docente todavía no vio el recorrido (o hay uno más nuevo)."""
    try:
        with open(ruta, encoding="utf-8") as f:
            return int(json.load(f).get("version", 0)) < version
    except (OSError, ValueError, TypeError, AttributeError):
        return True


def marcar_tour_visto(ruta: str, version: int = TOUR_VERSION) -> None:
    escribir_atomico(ruta, json.dumps({"version": version,
                                       "visto": datetime.datetime.now().isoformat(timespec="seconds")}))


# ------------------------------------------------------- ítems y selección
# Cada herramienta informa lo que considera con una línea:
#   ##ITEM {"clave": "5BA|09:40-11:10|Ciencias", "estado": "hecho", ...}
# La barra usa la misma `clave` para las casillas de la vista previa y para
# mostrar después qué se hizo y qué no.
ESTADOS_ITEM = ("propuesto", "hecho", "ya", "pendiente", "error", "omitido")
_ITEM = re.compile(r"^\s*##ITEM\s+(\{.*\})\s*$")


def parsear_item(linea: str) -> dict | None:
    """'##ITEM {...}' -> dict con clave, estado, titulo, grupo, que, detalle, motivo."""
    m = _ITEM.match(linea)
    if not m:
        return None
    try:
        dato = json.loads(m.group(1))
    except ValueError:
        return None
    if not isinstance(dato, dict) or not dato.get("clave") or dato.get("estado") not in ESTADOS_ITEM:
        return None
    opciones = [{"id": str(o["id"]), "texto": str(o.get("texto") or o["id"])}
                for o in dato.get("opciones") or [] if isinstance(o, dict) and o.get("id")]
    return {"clave": str(dato["clave"]), "estado": dato["estado"],
            "titulo": str(dato.get("titulo") or dato["clave"]),
            "grupo": str(dato.get("grupo") or ""), "que": str(dato.get("que") or ""),
            "detalle": str(dato.get("detalle") or ""), "motivo": str(dato.get("motivo") or ""),
            "opciones": opciones}


def agrupar_items(items: list[dict]) -> dict[str, list[dict]]:
    """Reparte los ítems en los bloques del resultado.

    hecho · ya (ya estaba) · no_pude (pendientes y errores) · omitido (el
    docente los desmarcó). Si un mismo ítem se informa dos veces (p. ej. OA y
    asistencia del mismo bloque), el último estado manda para la misma clave y
    acción.
    """
    ultimo: dict[tuple[str, str], dict] = {}
    for it in items:
        ultimo[(it["clave"], it["que"])] = it
    bloques: dict[str, list[dict]] = {"hecho": [], "ya": [], "no_pude": [], "omitido": []}
    for it in ultimo.values():
        destino = {"hecho": "hecho", "ya": "ya", "pendiente": "no_pude", "error": "no_pude",
                   "omitido": "omitido"}.get(it["estado"])
        if destino:
            bloques[destino].append(it)
    return bloques


_MOTIVOS = (
    (re.compile(r"unidad nueva sin revisar", re.I),
     "Webclass tiene una unidad que tu perfil no conoce y no la incluí sin preguntarte.",
     "Abre «Asignar» con vista previa y marca la unidad nueva, o usa «A dónde asigno cada unidad»."),
    (re.compile(r"estado que la barra no conoce", re.I),
     "La asistencia de origen trae un estado que la barra no sabe copiar; no la envié en blanco.",
     "Pasa la lista de este bloque a mano en Webclass."),
    (re.compile(r"Webclass guard[oó] distinto|no pude comprobarla", re.I),
     "Envié la asistencia pero Webclass no quedó igual que el origen (o no pude comprobarlo).",
     "Revisa la lista de este bloque en Webclass y corrige las ausentes."),
    (re.compile(r"no hay clase con esa fecha", re.I),
     "Tu planificación no tiene una clase con esa fecha.",
     "Agrega la clase en Webclass o ponle fecha, y vuelve a intentar."),
    (re.compile(r"\d+ clases con esa fecha|no s[ée] cu[aá]l usar", re.I),
     "Hay varias clases con esa fecha en tu planificación y no sé cuál corresponde.",
     "Deja una sola con esa fecha o declara este bloque a mano."),
    (re.compile(r"sin bloque anterior con el curso completo", re.I),
     "No hay un bloque anterior con la asistencia del curso completo para copiar.",
     "Toma la asistencia de este bloque a mano."),
    (re.compile(r"taller", re.I),
     "Es un taller: tiene solo una parte del curso, por eso no se copia la asistencia.",
     "Toma la asistencia a mano."),
    (re.compile(r"no se pudo leer la n[óo]mina", re.I),
     "No pude leer la lista de alumnas del curso.",
     "Reintenta en un momento; si sigue igual, revisa el curso en Webclass."),
    (re.compile(r"n[óo]mina y el bloque anterior no calzan", re.I),
     "La lista de alumnas no coincide con la del bloque anterior.",
     "Toma la asistencia a mano."),
    (re.compile(r"sin fecha de inicio|sin fechas", re.I),
     "La clase no tiene fecha de inicio y término.",
     "Ponle las fechas en la planificación."),
    (re.compile(r"no se encontraron alumnas|sin alumnas", re.I),
     "No encontré alumnas en el curso de destino.",
     "Revisa a qué curso se asigna esa unidad («A dónde asigno cada unidad»)."),
)


def explicar_motivo(texto: str) -> dict:
    """Pasa el motivo técnico de un script a una explicación y un qué hacer."""
    for patron, que, hacer in _MOTIVOS:
        if patron.search(texto or ""):
            return {"que": que, "hacer": hacer}
    explicacion = traducir_error([texto or ""])
    return {"que": explicacion or (texto or "No se pudo completar."), "hacer": ""}


def vacio_del_dia(items: list[dict], tiene_clases: bool = True) -> str:
    """Por qué no hubo nada que hacer, en una frase."""
    bloques = agrupar_items(items)
    if not tiene_clases and not items:
        return "No tienes clases ese día."
    if items and not bloques["hecho"] and not bloques["no_pude"] and bloques["ya"]:
        return "Todo ya estaba registrado."
    if bloques["no_pude"] and not bloques["hecho"]:
        return "Había cosas por hacer, pero no se pudieron completar."
    if not items:
        return "No había nada por hacer."
    return ""


# ------------------------------------------------------------- destinos de unidades
_OPCIONES = re.compile(r"^\s*##OPCIONES\s+(\{.*\})\s*$")


def parsear_opciones(linea: str) -> dict | None:
    """'##OPCIONES {"unidad": "123", "opciones": [...], "error": ""}' -> dict o None."""
    m = _OPCIONES.match(linea)
    if not m:
        return None
    try:
        dato = json.loads(m.group(1))
    except ValueError:
        return None
    if not isinstance(dato, dict) or "unidad" not in dato:
        return None
    return {"unidad": str(dato["unidad"]),
            "opciones": [{"id": o["id"], "nombre": str(o["nombre"])}
                         for o in dato.get("opciones", []) if isinstance(o, dict) and "id" in o],
            "error": str(dato.get("error") or "")}


def filas_de_destinos(unidades: list[dict], elegidos: dict, curso_ids: dict | None = None,
                      filtro: str = "", solo_cambiadas: bool = False) -> list[dict]:
    """Una fila por unidad para el editor: clave, grupo (curso), título y destino actual.

    `elegidos` es lo que hay en destinos.json ({id_unidad: {id, nombre}}). Si la
    unidad no tiene excepción, se asigna al curso de la unidad («por defecto»).
    """
    filtro = filtro.strip().lower()
    filas = []
    for u in unidades:
        clave = str(u["id"])
        elegido = elegidos.get(clave)
        if solo_cambiadas and not elegido:
            continue
        curso = str(u.get("curso", ""))
        texto = f"{curso} {u.get('nombre', '')}".lower()
        if filtro and filtro not in texto and filtro not in (elegido or {}).get("nombre", "").lower():
            continue
        if elegido:
            detalle = f"Se asigna a: {elegido['nombre']}"
        else:
            detalle = f"Por defecto: el curso {curso}"
        filas.append({"clave": clave, "grupo": curso, "titulo": str(u.get("nombre", clave)),
                      "detalle": detalle, "cambiada": bool(elegido)})
    return filas


def aplicar_destinos(elegidos: dict, cambios: dict) -> dict:
    """Copia de `elegidos` con los cambios: {id_unidad: {id, nombre}} o None para volver al por defecto."""
    nuevo = {k: dict(v) for k, v in elegidos.items()}
    for unidad, destino in cambios.items():
        if destino is None:
            nuevo.pop(str(unidad), None)
        else:
            nuevo[str(unidad)] = {"id": destino["id"], "nombre": destino["nombre"]}
    return nuevo


def lineas_de_resultado(items: list[dict], firmas: list[str] | tuple = (),
                        vacio: str = "") -> list[tuple[str, str]]:
    """El resultado de una actividad como lista de (texto, estilo) para mostrarla.

    Estilos: 'resumen', 'titulo_ok', 'titulo_aviso', 'titulo_gris', 'item',
    'detalle', 'hacer', 'vacio'. Es lo mismo que la herramienta imprime al
    cerrar, pero en bloques que la ventana de actividad puede pintar.
    """
    bloques = agrupar_items(items)
    lineas: list[tuple[str, str]] = []
    if not items:
        return [(vacio or "No había nada por hacer.", "vacio")]
    intentados = sum(len(bloques[k]) for k in ("hecho", "ya", "no_pude"))
    partes = [f"Intenté {intentados}"]
    if bloques["hecho"]:
        partes.append(f"hice {len(bloques['hecho'])}")
    if bloques["no_pude"]:
        partes.append(f"no pude {len(bloques['no_pude'])}")
    if bloques["ya"]:
        partes.append(f"ya estaban {len(bloques['ya'])}")
    if bloques["omitido"]:
        partes.append(f"omitiste {len(bloques['omitido'])}")
    lineas.append((" · ".join(partes), "resumen"))
    if bloques["hecho"]:
        lineas.append((f"✓ Hice ({len(bloques['hecho'])})", "titulo_ok"))
        for it in bloques["hecho"]:
            lineas.append((f"{it['titulo']}" + (f" — {it['detalle']}" if it["detalle"] else ""), "item"))
    if bloques["no_pude"]:
        lineas.append((f"⚠ No pude ({len(bloques['no_pude'])})", "titulo_aviso"))
        for it in bloques["no_pude"]:
            e = explicar_motivo(it["motivo"] or it["detalle"])
            lineas.append((it["titulo"], "item"))
            lineas.append((e["que"], "detalle"))
            if e["hacer"]:
                lineas.append((f"→ {e['hacer']}", "hacer"))
    if bloques["ya"]:
        lineas.append((f"○ Ya estaba hecho ({len(bloques['ya'])})", "titulo_gris"))
        if len(bloques["ya"]) > 6:          # una lista larga tapa lo importante
            lineas.append(("son muchos: no se detallan", "detalle"))
        else:
            for it in bloques["ya"]:
                lineas.append((it["titulo"], "item"))
    if bloques["omitido"]:
        lineas.append((f"– Omitido por ti ({len(bloques['omitido'])})", "titulo_gris"))
        for it in bloques["omitido"]:
            lineas.append((it["titulo"], "item"))
    if firmas:
        lineas.append((f"✍ Te falta firmar ({len(firmas)})", "titulo_aviso"))
        for f in firmas:
            lineas.append((f, "item"))
    return lineas


def escribir_seleccion(carpeta: str, claves: list[str], elecciones: dict | None = None) -> str:
    """Guarda las claves elegidas (y las clases escogidas a mano) y devuelve su ruta.

    `elecciones` es {clave de bloque: id de la clase de la planificación}: lo que el
    docente eligió cuando la herramienta no pudo decidir sola.
    """
    os.makedirs(carpeta, exist_ok=True)
    for viejo in os.listdir(carpeta):          # se limpian las de hace más de dos días
        ruta_vieja = os.path.join(carpeta, viejo)
        try:
            if (viejo.startswith("seleccion_")
                    and datetime.datetime.now().timestamp() - os.path.getmtime(ruta_vieja) > 2 * 86400):
                os.remove(ruta_vieja)
        except OSError:
            pass
    ruta = os.path.join(carpeta, f"seleccion_{os.getpid()}_{int(datetime.datetime.now().timestamp() * 1000)}.json")
    contenido = {"claves": list(claves)}
    if elecciones:
        contenido["elecciones"] = {str(k): str(v) for k, v in elecciones.items()}
    escribir_atomico(ruta, json.dumps(contenido, ensure_ascii=False))
    return ruta


def argumentos_de_seleccion(claves: list[str], todas: list[str], carpeta: str,
                            elecciones: dict | None = None) -> list[str]:
    """Argumentos para la herramienta: nada si se marcó todo, o `--seleccion RUTA`.

    Si se marcó todo no se pasa nada: la herramienta hace lo de siempre y
    también incluye lo que haya aparecido después de calcular la vista previa. Con
    unidades nuevas (`unidad:<id>`) siempre se pasa: sin selección la herramienta no
    las incluye, porque una unidad nueva solo entra si el docente la marcó.
    """
    con_unidades = any(str(c).startswith("unidad:") for c in todas)
    if not elecciones and not con_unidades and (not todas or set(claves) >= set(todas)):
        return []
    return ["--seleccion", escribir_seleccion(carpeta, claves, elecciones)]


def comando_con_seleccion(comando: list[str], claves: list[str], carpeta: str,
                          elecciones: dict | None = None) -> list[str]:
    """El mismo comando, pero con otra selección (se saca la `--seleccion` anterior)."""
    limpio, saltar = [], False
    for parte in comando:
        if saltar:
            saltar = False
        elif parte == "--seleccion":
            saltar = True
        else:
            limpio.append(parte)
    return limpio + ["--seleccion", escribir_seleccion(carpeta, claves, elecciones)]


# ------------------------------------------------------- registrar hacia atrás
MAX_DIAS_ATRAS = 62
ATAJOS_ATRAS = (("ayer", "Ayer"), ("7", "Últimos 7 días"), ("15", "Últimos 15 días"),
                ("mes", "Este mes"), ("fecha", "Desde una fecha…"))


def parsear_fecha(texto: str, hoy: datetime.date | None = None) -> datetime.date:
    """'06/10/2026', '6-10-26' o '06/10' (con el año de hoy) -> date. ValueError si no se entiende."""
    hoy = hoy or datetime.date.today()
    m = re.fullmatch(r"\s*(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2}|\d{4}))?\s*", texto or "")
    if not m:
        raise ValueError("Escribe la fecha así: 06/10/2026 (día/mes/año).")
    dia, mes = int(m.group(1)), int(m.group(2))
    anio = hoy.year if not m.group(3) else int(m.group(3))
    if anio < 100:
        anio += 2000
    try:
        return datetime.date(anio, mes, dia)
    except ValueError:
        raise ValueError("Esa fecha no existe en el calendario.") from None


def rango_de_atajo(atajo: str, hoy: datetime.date | None = None,
                   fecha_texto: str = "") -> tuple[datetime.date, datetime.date]:
    """(desde, hasta) para «Ayer», «Últimos N días», «Este mes» o «Desde una fecha».

    Nunca llega más allá de hoy ni a más de 62 días atrás: así lo que se
    registra es siempre pasado y acotado. ValueError con un mensaje claro si no sirve.
    """
    hoy = hoy or datetime.date.today()
    if atajo == "ayer":
        desde = hasta = hoy - datetime.timedelta(days=1)
    elif atajo in ("7", "15", "30"):
        desde, hasta = hoy - datetime.timedelta(days=int(atajo)), hoy
    elif atajo == "mes":
        desde, hasta = hoy.replace(day=1), hoy
    elif atajo == "fecha":
        desde, hasta = parsear_fecha(fecha_texto, hoy), hoy
    else:
        raise ValueError("No entendí ese período.")
    if desde > hoy:
        raise ValueError("Esa fecha todavía no llega: elige un día que ya pasó.")
    if (hasta - desde).days > MAX_DIAS_ATRAS:
        raise ValueError(f"Es mucho tiempo: elige como máximo {MAX_DIAS_ATRAS} días hacia atrás "
                         f"(desde el {hoy - datetime.timedelta(days=MAX_DIAS_ATRAS):%d/%m/%Y}).")
    return desde, hasta


def dias_habiles(desde: datetime.date, hasta: datetime.date) -> list[datetime.date]:
    """Los días de lunes a viernes entre dos fechas, ambas incluidas."""
    dias, d = [], desde
    while d <= hasta:
        if d.weekday() < 5:
            dias.append(d)
        d += datetime.timedelta(days=1)
    return dias


# ------------------------------------------------- períodos con tickets (casillas)
MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
            "septiembre", "octubre", "noviembre", "diciembre"]
MAX_DIAS_DIAGNOSTICO = 250


def inicio_ano_escolar(hoy: datetime.date) -> datetime.date:
    """1 de marzo del año escolar en curso (si es enero o febrero, el del año anterior)."""
    return datetime.date(hoy.year if hoy.month >= 3 else hoy.year - 1, 3, 1)


def meses_escolares(hoy: datetime.date | None = None) -> list[dict]:
    """Los meses del año escolar hasta hoy (marzo … mes actual), del más reciente al más antiguo.

    Cada uno: {"clave": "10/2026", "texto": "Octubre 2026 (este mes)", "anio", "mes"}.
    """
    hoy = hoy or datetime.date.today()
    anio, mes = inicio_ano_escolar(hoy).year, 3
    meses = []
    while (anio, mes) <= (hoy.year, hoy.month):
        meses.append({"clave": f"{mes:02d}/{anio}", "anio": anio, "mes": mes,
                      "texto": f"{MESES_ES[mes - 1].capitalize()} {anio}"})
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    if meses:
        meses[-1]["texto"] += " (este mes)"
    if len(meses) > 1:
        meses[-2]["texto"] += " (mes anterior)"
    return list(reversed(meses))


def periodos_de_revision(hoy: datetime.date | None = None) -> list[dict]:
    """Los períodos que se pueden marcar al revisar el libro: cada uno con sus días hábiles.

    Hoy · Ayer · Esta semana · Semana anterior · Este mes · Mes anterior · Todo el año
    (desde marzo). Nunca incluye días que todavía no llegan.
    """
    hoy = hoy or datetime.date.today()
    lunes = hoy - datetime.timedelta(days=hoy.weekday())
    lunes_anterior = lunes - datetime.timedelta(days=7)
    primero_del_mes = hoy.replace(day=1)
    fin_mes_anterior = primero_del_mes - datetime.timedelta(days=1)
    rangos = [
        ("hoy", "Hoy", hoy, hoy),
        ("ayer", "Ayer", hoy - datetime.timedelta(days=1), hoy - datetime.timedelta(days=1)),
        ("esta_semana", "Esta semana", lunes, hoy),
        ("semana_anterior", "Semana anterior", lunes_anterior, lunes_anterior + datetime.timedelta(days=4)),
        ("este_mes", "Este mes", primero_del_mes, hoy),
        ("mes_anterior", "Mes anterior", fin_mes_anterior.replace(day=1), fin_mes_anterior),
        ("todo", "Todo el año (desde marzo)", inicio_ano_escolar(hoy), hoy),
    ]
    periodos = []
    for clave, texto, desde, hasta in rangos:
        dias = dias_habiles(desde, min(hasta, hoy))
        periodos.append({"clave": clave, "texto": texto, "dias": dias,
                         "detalle": (f"{len(dias)} día{'s' if len(dias) != 1 else ''} hábil"
                                     f"{'es' if len(dias) != 1 else ''}") if dias else "sin días hábiles"})
    return periodos


def dias_de_periodos(claves: list[str], hoy: datetime.date | None = None,
                     fecha_texto: str = "") -> list[datetime.date]:
    """Une los días de los períodos marcados (y de una fecha escrita), sin repetir y en orden.

    ValueError si la fecha escrita no sirve, si es futura o si son demasiados días.
    """
    hoy = hoy or datetime.date.today()
    por_clave = {p["clave"]: p["dias"] for p in periodos_de_revision(hoy)}
    dias: set[datetime.date] = set()
    for clave in claves:
        dias.update(por_clave.get(clave, []))
    if fecha_texto.strip():
        dia = parsear_fecha(fecha_texto, hoy)
        if dia > hoy:
            raise ValueError("Esa fecha todavía no llega: elige un día que ya pasó.")
        if dia.weekday() >= 5:
            raise ValueError("Ese día es fin de semana: no hay clases.")
        dias.add(dia)
    if not dias:
        raise ValueError("Marca al menos un período con días hábiles.")
    if len(dias) > MAX_DIAS_DIAGNOSTICO:
        raise ValueError(f"Son demasiados días ({len(dias)}): como máximo {MAX_DIAS_DIAGNOSTICO}.")
    return sorted(dias)


def formatear_fechas(dias: list[datetime.date]) -> str:
    """[05/10, 06/10] -> '05/10/2026,06/10/2026' (el formato que reciben las herramientas)."""
    return ",".join(d.strftime("%d/%m/%Y") for d in dias)


def version_del_codigo(carpeta: str) -> int:
    """Marca de «qué tan nuevo» es el código de la barra: el mayor mtime de sus .py y .pyw.

    Sirve para que una barra abierta se reinicie sola cuando se abre una copia con
    código más nuevo (si no, la barra vieja seguía corriendo con el programa viejo).
    """
    mayor = 0
    try:
        for nombre in os.listdir(carpeta):
            if nombre.endswith((".py", ".pyw")):
                mayor = max(mayor, int(os.path.getmtime(os.path.join(carpeta, nombre))))
    except OSError:
        pass
    return mayor


# --------------------------------------------------------------------- monitores
def monitores() -> list[tuple[int, int, int, int]]:
    """Área útil (izq, arriba, der, abajo) de cada monitor, el principal primero.

    Tk solo informa del monitor principal; con dos pantallas hay que preguntarle
    a Windows. Si algo falla, se devuelve una lista vacía.
    """
    try:
        from ctypes import wintypes

        class Info(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        hallados: list[tuple[int, int, int, int, bool]] = []
        firma = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.POINTER(wintypes.RECT), ctypes.c_void_p)

        def recoger(monitor, _dc, _rect, _datos) -> int:
            info = Info()
            info.cbSize = ctypes.sizeof(Info)
            if ctypes.windll.user32.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
                r = info.rcWork
                hallados.append((r.left, r.top, r.right, r.bottom, bool(info.dwFlags & 1)))
            return 1

        ctypes.windll.user32.EnumDisplayMonitors(None, None, firma(recoger), 0)
        hallados.sort(key=lambda m: not m[4])
        if hallados:
            return [m[:4] for m in hallados]
    except Exception:        # noqa: BLE001  (sin Windows o sin permisos: se usa Tk)
        pass
    return []


def texto_atrasados(atrasados: list[dict]) -> str:
    """«3 bloques de días anteriores sin registrar (06/10, 05/10)», o vacío si no hay."""
    total = sum(int(a.get("bloques", 0)) for a in atrasados or [])
    if not total:
        return ""
    dias = ", ".join(a["fecha"][:5] for a in atrasados[:3])
    mas = f" y {len(atrasados) - 3} días más" if len(atrasados) > 3 else ""
    return (f"{total} bloque{'s' if total != 1 else ''} de días anteriores sin registrar "
            f"({dias}{mas})")


def problemas_de_observacion(curso: str, alumnas: list[str], tipo: int, fecha: str,
                             texto: str, asignatura: str) -> list[str]:
    """Qué falta para poder registrar una observación (vacío si está lista)."""
    problemas = []
    if not curso:
        problemas.append("elige el curso")
    if not alumnas:
        problemas.append("marca al menos una alumna")
    if tipo not in (1, 2, 3):
        problemas.append("elige el tipo: positiva, negativa o neutra")
    if not (texto or "").strip():
        problemas.append("escribe la descripción")
    elif len(texto) > 1500:
        problemas.append("la descripción es demasiado larga (máximo 1500 letras)")
    if not asignatura:
        problemas.append("elige la asignatura")
    try:
        datetime.datetime.strptime((fecha or "").strip(), "%d/%m/%Y")
    except ValueError:
        problemas.append("la fecha debe ser DD/MM/AAAA")
    return problemas


_CURSO_EN_NOMBRE = re.compile(r"(?<![A-Za-z0-9])(?:[1-8]B[AB]|[1-4]M[AB]|PKA|KA)(?![A-Za-z0-9])", re.I)


def cursos_en_nombres(nombres: list[str]) -> str:
    """«5BA, 5BB» a partir de los cursos que aparecen escritos en los nombres de archivo."""
    vistos: list[str] = []
    for nombre in nombres:
        for c in _CURSO_EN_NOMBRE.findall(os.path.splitext(nombre)[0]):
            if c.upper() not in vistos:
                vistos.append(c.upper())
    return ", ".join(vistos)


def titulo_de_guia(nombre: str) -> str:
    """El título de la guía: el nombre del archivo sin extensión ni curso."""
    base = _CURSO_EN_NOMBRE.sub(" ", os.path.splitext(nombre)[0]).replace("_", " ")
    return " ".join(base.split()).strip(" -–.,") or os.path.splitext(nombre)[0]


def asunto_de_correo(nombres: list[str], curso: str = "") -> str:
    """«Guía NEEP <título> <curso>» (o «Guías NEEP t1, t2 <curso>» con varios archivos)."""
    titulos = [titulo_de_guia(n) for n in nombres]
    base = (f"Guía NEEP {titulos[0]}" if len(titulos) == 1
            else f"Guías NEEP {', '.join(titulos)}")
    return f"{base} {curso.strip()}".strip()


def texto_de_correo(nombres: list[str], docente: str) -> tuple[str, str]:
    """(asunto, cuerpo) de partida para enviar guías al equipo PIE."""
    lista = "\n".join(f"- {n}" for n in nombres)
    cuerpo = f"Estimado equipo PIE:\n\n{lista}\n\nSaludos cordiales,\n{docente}"
    return asunto_de_correo(nombres, cursos_en_nombres(nombres)), cuerpo.strip()
