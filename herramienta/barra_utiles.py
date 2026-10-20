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


def leer_json(ruta: str) -> dict:
    """El contenido de un JSON como diccionario ({} si falta, está roto o no es un diccionario)."""
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def bloques_de_horario_webclass(horario: dict, fecha: datetime.date) -> list[dict]:
    """Bloques de ese día según el horario de WebClass («Mi horario»), para «Ahora / Luego» sin asistente.

    El horario es el de una semana: se toma como la semana tipo (lunes = 0). Devuelve [{titulo, inicio, fin}] en orden.
    """
    salida = []
    for b in horario.get("bloques") or []:
        if not isinstance(b, dict) or b.get("dia") != fecha.weekday():
            continue
        inicio, fin = str(b.get("inicio") or ""), str(b.get("fin") or "")
        if not (re.fullmatch(r"\d{1,2}:\d{2}", inicio) and re.fullmatch(r"\d{1,2}:\d{2}", fin)):
            continue
        titulo = " · ".join(x for x in (str(b.get("curso") or "").strip(), asignatura_corta(b.get("asignatura") or "")) if x)
        salida.append({"titulo": titulo or "Clase", "inicio": inicio, "fin": fin})
    return sorted(salida, key=lambda b: minutos(b["inicio"]))


def horario_vencido(horario: dict, hoy: datetime.date, dias: int = 7) -> bool:
    """¿Hay que volver a leer «Mi horario» de WebClass? Sí si nunca se leyó, falló o tiene más de `dias` días."""
    if not horario.get("bloques") or horario.get("error"):
        return True
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(horario.get("generado") or ""))
    if not m:
        return True
    try:
        leido = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return True
    return (hoy - leido).days > dias


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


def opciones_de_pregunta(opciones, hoy: datetime.date | None = None) -> list[dict]:
    """Opciones ([{texto, valor}]) de un botón «preguntar».

    Con "meses" se calculan: los meses del año escolar hasta hoy, del más reciente al más antiguo. Así la plantilla
    no lleva fechas escritas a mano (antes decía «Octubre (este mes)» todo el año).
    """
    if opciones == "meses":
        return [{"texto": m["texto"], "valor": m["clave"]} for m in meses_escolares(hoy)]
    return [o for o in (opciones or []) if isinstance(o, dict) and "texto" in o and "valor" in o]


def leer_botones(ruta: str) -> tuple[list[dict], dict]:
    """Lee un herramientas.json y su formato ({"bom", "crlf"}), para guardarlo después igual que estaba.

    Lanza OSError si no se puede leer y ValueError si no es una lista de botones.
    """
    with open(ruta, "rb") as f:
        crudo = f.read()
    botones = json.loads(crudo.decode("utf-8-sig"))
    if not isinstance(botones, list) or not all(isinstance(b, dict) for b in botones):
        raise ValueError("herramientas.json debe ser una lista de botones")
    return botones, {"bom": crudo.startswith(b"\xef\xbb\xbf"), "crlf": b"\r\n" in crudo}


def guardar_botones(ruta: str, botones: list[dict], formato: dict | None = None,
                    copia: str | None = None) -> None:
    """Guarda los botones con el formato que tenía el archivo (BOM y saltos de línea de Windows).

    Comprueba que el resultado sea JSON válido antes de escribir y lo cambia de una sola vez. Con `copia`, deja una
    copia de seguridad del archivo anterior, solo si no existe ya: la que sirve es la de antes del primer cambio.
    """
    formato = formato or {"bom": False, "crlf": True}
    texto = json.dumps(botones, ensure_ascii=False, indent=2)
    json.loads(texto)
    if formato.get("crlf"):
        texto = texto.replace("\n", "\r\n")
    if copia and os.path.isfile(ruta) and not os.path.exists(copia):
        import shutil
        shutil.copy2(ruta, copia)
    temporal = f"{ruta}.tmp"
    with open(temporal, "wb") as f:
        f.write((b"\xef\xbb\xbf" if formato.get("bom") else b"") + texto.encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporal, ruta)


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


def _item(clave: str, titulo: str, grupo: str = "", detalle: str = "", sin_clase: dict | None = None) -> dict:
    """Un ítem con casilla. `sin_clase` ({campo, clave, dia, titulo}) permite marcarlo «no hubo clase» desde la lista."""
    dato = {"clave": clave, "titulo": titulo, "grupo": grupo, "detalle": detalle}
    if sin_clase:
        dato["sin_clase"] = sin_clase
    return dato


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
    if estado.get("sin_clases"):
        return {"titulo": titulo, "puntos": ["Marcaste hoy como día sin clases: no hay nada que registrar."],
                "items": [], "hay_trabajo": False,
                "aviso": "Para deshacerlo: «Días sin clases» (en el grupo Webclass o en ⚙ Ajustes → Profesor)."}
    dia = fecha_de_estado(hoy)
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
        etiqueta = f"{b.get('curso', '?')} {inicio}" + (f" · {asignatura}" if asignatura else "")
        sin_clase = ({"campo": "bloques", "clave": clave_con_fecha(clave_de_bloque(b), dia),
                      "dia": dia.isoformat(), "titulo": f"{dia:%d/%m} {etiqueta}"} if dia else None)
        items.append(_item(clave_de_bloque(b), etiqueta, str(b.get("curso", "")), detalle, sin_clase))
    por_firmar = len(estado.get("sin_firmar", []))
    firma = (f" Quedarán {por_firmar} bloque{'s' if por_firmar != 1 else ''} por firmar: "
             "la firma la haces tú." if por_firmar else "")
    if not puntos:
        return {"titulo": titulo, "puntos": ["Todo lo de hoy ya está registrado."], "items": [],
                "hay_trabajo": False, "aviso": origen + firma}
    return {"titulo": titulo, "puntos": puntos, "items": items, "hay_trabajo": True,
            "aviso": origen + firma}


# Asignaturas con que se puede firmar un recurso al subirlo: (clave, nombre que se muestra).
ASIGNATURAS_SUBIDA = (("ciencias", "Ciencias Naturales"), ("matematica", "Matemática"),
                      ("lenguaje", "Lenguaje y Comunicación"), ("historia", "Historia, Geografía y Cs. Sociales"),
                      ("orientacion", "Orientación"), ("tecnologia", "Tecnología"), ("biologia", "Biología"),
                      ("quimica", "Química"), ("fisica", "Física"), ("filosofia", "Filosofía y Psicología"),
                      ("integracion", "Programa de Integración Escolar"))
# Código de cada asignatura en el formulario de recursos de WebClass («selectSectorLocal»). Es la ÚNICA tabla: de aquí la
# toman el subidor (webclass_recursos.ASIGNATURAS) y el planificador, así no se desfasan.
ID_ASIGNATURA = {"ciencias": 3, "matematica": 2, "lenguaje": 1, "historia": 4, "orientacion": 9, "tecnologia": 7,
                 "biologia": 12, "quimica": 14, "fisica": 13, "filosofia": 16, "integracion": 107}


def _sin_tildes(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn").lower()


def asignaturas_de_la_cuenta(perfil: dict | None) -> list[tuple[str, str, int]]:
    """(clave, nombre, código de WebClass) de las asignaturas con que esta cuenta puede firmar un recurso.

    Si al configurar la cuenta se leyó la lista de WebClass (perfil["asignaturas_webclass"]), se usa esa: así aparecen
    Inglés, Artes, Música, Religión… Si no, la tabla de siempre. Las que están en la tabla conservan su clave
    («ciencias»), para que lo ya elegido siga valiendo; las demás se llaman «wc<código>».
    """
    tabla = [(clave, nombre, ID_ASIGNATURA[clave]) for clave, nombre in ASIGNATURAS_SUBIDA]
    claves = {codigo: clave for clave, _nombre, codigo in tabla}
    leidas, vistas = [], set()
    for item in (perfil or {}).get("asignaturas_webclass") or []:
        try:
            codigo, nombre = int(item["id"]), " ".join(str(item["nombre"]).split())
        except (KeyError, TypeError, ValueError):
            continue
        if codigo > 0 and nombre and codigo not in vistas:
            vistas.add(codigo)
            leidas.append((claves.get(codigo, f"wc{codigo}"), nombre, codigo))
    return leidas or tabla


def asignatura_de_texto(texto: str, asignaturas: list[tuple[str, str, int]]) -> tuple[str, str, int] | None:
    """La asignatura a la que se refiere un texto libre («Orientacion», «musica», «Ed. Física»…). None si ninguna.

    Primero igual al nombre o a la clave (sin tildes); después la de nombre más corto que empiece con el texto (o con
    la que empiece el texto): «educacion fisica» -> «Educación Física y Salud».
    """
    def norma(x: str) -> str:
        return " ".join(_sin_tildes(x).replace(".", " ").split())

    t = norma(texto)
    if not t:
        return None
    for asignatura in asignaturas:
        if t in (norma(asignatura[1]), asignatura[0], norma(asignatura_corta(asignatura[1]))):
            return asignatura
    parecidas = [a for a in asignaturas if _sin_tildes(a[1]).startswith(t) or t.startswith(_sin_tildes(a[1]))
                 or t.startswith(a[0])]
    return min(parecidas, key=lambda a: len(a[1])) if parecidas else None


def carpeta_con_asignatura(nombre: str, asignaturas: list[tuple[str, str, int]]) -> tuple[int, tuple[str, str, int]] | None:
    """Una carpeta del buzón con nivel y asignatura en el nombre («5 basico Orientacion», «7° Básico Música»):
    (código de nivel, asignatura). None si no empieza con un nivel o no se reconoce la asignatura."""
    m = re.fullmatch(r"\s*(\d)\s*°?\s*(basico|medio)\b[\s\-–·:]*(.+)", _sin_tildes(nombre or ""))
    if not m:
        return None
    asignatura = asignatura_de_texto(m.group(3), asignaturas)
    if not asignatura:
        return None
    return (20 if m.group(2) == "basico" else 30) + int(m.group(1)), asignatura


_CORTAS = {"ciencias naturales": "Ciencias", "historia, geografia y ciencias sociales": "Historia",
           "historia, geografia y cs. sociales": "Historia", "lenguaje y comunicacion": "Lenguaje",
           "lengua y literatura": "Lenguaje", "educacion fisica y salud": "Ed. Física", "artes visuales": "Artes",
           "programa de integracion escolar": "PIE", "filosofia y psicologia": "Filosofía"}


def asignatura_corta(nombre: str) -> str:
    """Nombre corto para el horario y la tarjeta «Hoy»: «Ciencias Naturales» -> «Ciencias»."""
    limpio = " ".join(str(nombre or "").split())
    if _sin_tildes(limpio) in _CORTAS:
        return _CORTAS[_sin_tildes(limpio)]
    primera = re.split(r",| y |\(", limpio)[0].strip()
    return primera if len(primera) <= 14 else primera[:13].rstrip() + "…"


def asignatura_sugerida(perfil: dict) -> str:
    """Clave de la asignatura que más dicta el docente (la de su perfil); «ciencias» si no se sabe."""
    cuenta: dict[str, int] = {}
    for nombre in (perfil.get("curso_asignaturas") or {}).values():
        n = _sin_tildes(nombre)
        cuenta[n] = cuenta.get(n, 0) + 1
    principal = max(cuenta, key=cuenta.get) if cuenta else ""
    if perfil.get("asignaturas_webclass") and principal:
        exacta = next((a for a in asignaturas_de_la_cuenta(perfil) if _sin_tildes(a[1]) == principal), None)
        if exacta:
            return exacta[0]
    # La palabra que aparece primero manda: «Historia, Geografía y Ciencias Sociales» es Historia, no Ciencias.
    encontradas = [(principal.index(clave), clave) for clave, _ in ASIGNATURAS_SUBIDA if clave in principal]
    return min(encontradas)[1] if encontradas else "ciencias"


def codigo_de_asignatura(clave: str, perfil: dict | None = None) -> int | None:
    """Código de WebClass de una clave de asignatura, según la lista de la cuenta y, si no está, la tabla."""
    codigo = next((c for k, _n, c in asignaturas_de_la_cuenta(perfil) if k == clave), None)
    return codigo if codigo is not None else ID_ASIGNATURA.get(clave)


def ruta_preferencia_subida(personal: str, perfil: str) -> str:
    """Un archivo por cuenta: así lo que elige un docente no cambia lo de otro."""
    return os.path.join(personal, f"subida_{perfil}.json")


def _claves_validas(validas) -> set:
    return set(validas) if validas is not None else set(dict(ASIGNATURAS_SUBIDA))


def leer_preferencia_subida(ruta: str, validas=None) -> dict:
    """{'asignatura': clave o '', 'preguntar': bool}. Sin archivo o roto: no hay preferencia y se pregunta.

    validas: claves aceptadas (las de la cuenta, ver asignaturas_de_la_cuenta); por omisión, las de la tabla.
    """
    datos = leer_json(ruta)
    clave = datos.get("asignatura") if datos.get("asignatura") in _claves_validas(validas) else ""
    return {"asignatura": clave, "preguntar": not (clave and datos.get("preguntar") is False)}


def guardar_preferencia_subida(ruta: str, asignatura: str, preguntar: bool, validas=None) -> None:
    if asignatura not in _claves_validas(validas):
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
    propuestos = [_item(i["clave"], i["titulo"], i["grupo"], i["detalle"], i.get("sin_clase"))
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


# ------------------------------------------------------- PIN de cada profesor
# En un equipo con varios profesores cada uno tiene un PIN de 4 números. No es por seguridad: es para no usar por
# error la barra (y el libro) de otro. Se guarda solo su huella (PBKDF2 con sal propia), nunca el PIN.
PIN_VALIDO = re.compile(r"\d{4}")
ITERACIONES_PIN = 120_000


def ruta_pin(personal: str, perfil: str) -> str:
    """Un archivo por profesor: personal\\pin_<cuenta>.json."""
    return os.path.join(personal, f"pin_{perfil}.json")


def _huella_pin(pin: str, sal: bytes, iteraciones: int) -> str:
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), sal, iteraciones).hex()


def tiene_pin(ruta: str) -> bool:
    datos = leer_json(ruta)
    return bool(datos.get("sal") and datos.get("huella"))


def guardar_pin(ruta: str, pin: str) -> None:
    """Guarda (o reemplaza) el PIN. ValueError si no son 4 números."""
    if not PIN_VALIDO.fullmatch(pin or ""):
        raise ValueError("El PIN son 4 números.")
    sal = os.urandom(16)
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    escribir_atomico(ruta, json.dumps({"sal": sal.hex(), "huella": _huella_pin(pin, sal, ITERACIONES_PIN),
                                       "iteraciones": ITERACIONES_PIN}, indent=1))


def pin_correcto(ruta: str, pin: str) -> bool:
    import hmac
    datos = leer_json(ruta)
    if not PIN_VALIDO.fullmatch(str(pin or "")):
        return False
    try:
        sal, iteraciones = bytes.fromhex(datos["sal"]), int(datos.get("iteraciones") or ITERACIONES_PIN)
    except (KeyError, TypeError, ValueError):
        return False
    return hmac.compare_digest(_huella_pin(str(pin), sal, iteraciones), str(datos.get("huella", "")))


def marcar_desbloqueo(ruta: str, perfil: str, segundos: int = 120) -> None:
    """La barra se va a reabrir sola (actualización, cambio de color…): la nueva no vuelve a pedir el PIN a quien ya
    lo escribió, si parte con el mismo profesor dentro de `segundos`."""
    import time
    escribir_atomico(ruta, json.dumps({"perfil": perfil, "hasta": time.time() + segundos}))


def desbloqueo_vigente(ruta: str, perfil: str) -> bool:
    """¿La barra anterior dejó a este profesor desbloqueado hace un momento? Sirve una sola vez (se borra al leerlo)."""
    import time
    datos = leer_json(ruta)
    try:
        os.remove(ruta)
    except OSError:
        pass
    try:
        return datos.get("perfil") == perfil and float(datos.get("hasta") or 0) > time.time()
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------- mis registros
# Los tres registros que la barra deja en CSV, para verlos en la ventana «Mis registros» (sin abrir Excel).
# fecha / curso / estado: la columna con que se filtra cada cosa ("" si ese registro no la tiene).
TIPOS_REGISTRO = {
    "Libro": {"fecha": "fecha_clase", "curso": "curso", "estado": "estado",
              "columnas": (("fecha_clase", "Clase del"), ("curso", "Curso"), ("hora", "Hora"), ("asignatura", "Asignatura"),
                           ("clase", "Clase"), ("estado", "Estado"), ("firma", "Firma"))},
    "Subidas": {"fecha": "fecha", "curso": "carpeta", "estado": "estado",
                "columnas": (("fecha", "Fecha"), ("archivo", "Archivo"), ("carpeta", "Nivel"), ("id_recurso", "Id"),
                             ("estado", "Estado"))},
    "Tareas": {"fecha": "fecha_clase", "curso": "curso", "estado": "",
               "columnas": (("fecha_clase", "Clase del"), ("curso", "Curso"), ("clase", "Clase"),
                            ("alumnas_asignadas", "Asignadas"), ("fecha_asignacion", "Asignada el"))},
}


def pestana_de_registro(destino: str) -> str | None:
    """Qué pestaña de «Mis registros» corresponde al destino de un botón (los botones «Registro de…» de siempre)."""
    d = (destino or "").upper().replace("/", "\\")
    if "%REGISTRO_LIBRO%" in d:
        return "Libro"
    if "%REGISTRO_TAREAS%" in d:
        return "Tareas"
    if d.endswith("REGISTRO_SUBIDAS.CSV"):
        return "Subidas"
    return None


def leer_registro(ruta: str) -> list[dict]:
    """Filas de un CSV de registro (separado con ; o con ,), de la más nueva a la más vieja. [] si no existe."""
    import csv
    import io
    try:
        with open(ruta, encoding="utf-8-sig", newline="") as f:
            texto = f.read()
    except OSError:
        return []
    if not texto.strip():
        return []
    primera = texto.splitlines()[0]
    separador = ";" if primera.count(";") > primera.count(",") else ","
    lector = csv.DictReader(io.StringIO(texto), delimiter=separador)
    filas = []
    for fila in lector:
        limpia = {k.strip(): (v or "").strip() for k, v in fila.items() if k is not None and isinstance(v, (str, type(None)))}
        sobrante = fila.get(None)            # una fila con más campos que el encabezado (un «;» dentro de un texto)
        if sobrante and lector.fieldnames:
            ultima = lector.fieldnames[-1].strip()
            limpia[ultima] = separador.join([limpia.get(ultima, ""), *(str(x) for x in sobrante)]).strip(separador)
        filas.append(limpia)
    return filas[::-1]


def fecha_de_registro(texto: str) -> datetime.date | None:
    """«17/10/2026», «17/10/2026 08:30» o «2026-10-17» -> fecha. None si no se entiende."""
    texto = (texto or "").strip()
    for patron, orden in ((r"(\d{1,2})/(\d{1,2})/(\d{4})", (3, 2, 1)), (r"(\d{4})-(\d{2})-(\d{2})", (1, 2, 3))):
        m = re.match(patron, texto)
        if m:
            try:
                return datetime.date(*(int(m.group(i)) for i in orden))
            except ValueError:
                return None
    return None


def estado_corto(texto: str) -> str:
    """«PENDIENTE: no hay clase con esa fecha…» -> «pendiente» (para agrupar en el filtro)."""
    return (texto or "").split(":")[0].strip().lower()


def desde_periodo(periodo: str, hoy: datetime.date) -> datetime.date | None:
    """Primer día de «semana» (desde el lunes) o «mes»; None para «todo»."""
    if periodo == "semana":
        return hoy - datetime.timedelta(days=hoy.weekday())
    if periodo == "mes":
        return hoy.replace(day=1)
    return None


def filtrar_registro(filas: list[dict], tipo: str, desde: datetime.date | None = None, curso: str = "",
                     estado: str = "", docente: str = "") -> list[dict]:
    """Filas de ese registro desde una fecha, de un curso y de un estado. Con `docente`, las subidas de otro docente
    del mismo PC no se muestran (el registro de subidas es uno solo por equipo)."""
    cfg = TIPOS_REGISTRO[tipo]
    salida = []
    for fila in filas:
        if desde is not None:
            fecha = fecha_de_registro(fila.get(cfg["fecha"], ""))
            if fecha is None or fecha < desde:
                continue
        if curso and fila.get(cfg["curso"], "") != curso:
            continue
        if estado and estado_corto(fila.get(cfg["estado"], "")) != estado:
            continue
        autor = fila.get("docente", "")
        if docente and autor and autor.lower() != docente.lower():
            continue
        salida.append(fila)
    return salida


def ordenar_por_fecha(filas: list[dict], tipo: str) -> list[dict]:
    """De la fecha más nueva a la más vieja (la del registro manda; a igual fecha, queda lo último anotado primero)."""
    columna = TIPOS_REGISTRO[tipo]["fecha"]
    return sorted(filas, key=lambda f: fecha_de_registro(f.get(columna, "")) or datetime.date.min, reverse=True)


def opciones_de_registro(filas: list[dict], tipo: str) -> tuple[list[str], list[str]]:
    """(cursos, estados) que aparecen en el registro, para los filtros."""
    cfg = TIPOS_REGISTRO[tipo]
    cursos = sorted({f.get(cfg["curso"], "") for f in filas} - {""})
    estados = sorted({estado_corto(f.get(cfg["estado"], "")) for f in filas} - {""}) if cfg["estado"] else []
    return cursos, estados


# ------------------------------------------------------------------------- tour
TOUR_VERSION = 2          # subir el número hace que el recorrido vuelva a aparecer una vez (2: barra rediseñada)
TOUR_PASOS = (
    {"id": "barra", "titulo": "Tu barra",
     "texto": "Se esconde en el borde de la pantalla: un clic en la lengüeta la abre y Escape la esconde. "
              "Arrastra esta cabecera para moverla; el 📌 la deja fija abierta y la ✕ te pregunta si "
              "esconderla o cerrarla."},
    {"id": "hoy", "titulo": "Tu día",
     "texto": "Qué clase tienes ahora y el estado de tu libro: bloques sin firmar o sin registrar. "
              "Un clic en «HOY» muestra el detalle (qué viene después, quiénes faltaron)."},
    {"id": "lista", "titulo": "Tu lista",
     "texto": "Anota pendientes, márcalos con un clic y bórralos con la ✕. Se guarda sola "
              "en este equipo."},
    {"id": "botones", "titulo": "Los botones",
     "texto": "Arriba quedan tus ★ favoritos; los demás están en grupos que se abren con un clic. "
              "Clic derecho en cualquier botón para sumarlo o quitarlo de favoritos. Al pulsar uno "
              "ves su avance y su estado (◐ en proceso, ✓ listo, ⚠ con avisos, ✕ error), y antes de "
              "escribir en Webclass te muestro una vista previa con casillas."},
    {"id": "pie", "titulo": "Ajustes y ayuda",
     "texto": "En ⚙ están el color, el cambio de profesor, las actualizaciones, el registro "
              "(si algo falla) y este recorrido, para repetirlo cuando quieras."},
)


# ------------------------------------------------------- niveles del buzón
# Carpetas por nivel del buzón «Subir a Webclass» (nombre de la carpeta, código de nivel de WebClass), en orden.
CARPETAS_NIVEL = tuple([(f"{n} basico", 20 + n) for n in range(1, 9)] + [(f"{n} medio", 30 + n) for n in range(1, 5)])
_PALABRAS_CON_TILDE = {"basico": "Básico", "orientacion": "Orientación", "matematica": "Matemática",
                       "tecnologia": "Tecnología", "religion": "Religión", "musica": "Música", "ingles": "Inglés",
                       "educacion": "Educación", "fisica": "Física", "quimica": "Química", "biologia": "Biología",
                       "filosofia": "Filosofía", "psicologia": "Psicología", "geografia": "Geografía",
                       "comunicacion": "Comunicación", "integracion": "Integración"}


def nombre_de_nivel(carpeta: str) -> str:
    """Cómo se muestra una carpeta del buzón: '5 basico' -> '5° Básico', '1 medio' -> '1° Medio',
    '5 basico Orientacion' -> '5° Básico · Orientación'. Las carpetas no se renombran: solo se muestran así."""
    m = re.fullmatch(r"\s*(\d)\s+(basico|medio)\b(.*)", carpeta or "", re.IGNORECASE)
    if not m:
        return carpeta
    base = f"{m.group(1)}° {'Básico' if m.group(2).lower() == 'basico' else 'Medio'}"
    resto = " ".join(_PALABRAS_CON_TILDE.get(p.lower(), p[:1].upper() + p[1:]) for p in m.group(3).split())
    return f"{base} · {resto}" if resto else base


def nivel_de_carpeta(carpeta: str) -> int | None:
    """Código de nivel de WebClass de una carpeta del buzón (25 para «5 basico» y «5 basico Orientacion»)."""
    m = re.match(r"\s*(\d)\s+(basico|medio)\b", carpeta or "", re.IGNORECASE)
    if not m:
        return None
    return (20 if m.group(2).lower() == "basico" else 30) + int(m.group(1))


def niveles_del_docente(perfil: dict) -> set[int]:
    """Códigos de nivel de los cursos del docente: de `curso_niveles` o, si el perfil no lo trae, del nombre del
    curso («5BA» -> 25, «1MA» -> 31)."""
    niveles = {int(v) for v in (perfil.get("curso_niveles") or {}).values() if str(v).isdigit()}
    if niveles:
        return niveles
    cursos = list(perfil.get("curso_ids") or {}) + [u.get("curso", "") for u in perfil.get("unidades") or []]
    for curso in cursos:
        m = re.match(r"\s*(\d)\s*([BM])", str(curso), re.IGNORECASE)
        if m:
            niveles.add((20 if m.group(2).upper() == "B" else 30) + int(m.group(1)))
    return niveles


def ordenar_carpetas(carpetas: list[str], propios: set[int]) -> tuple[list[str], list[str]]:
    """(las del docente, las demás), cada una en orden de nivel (1° a 8° Básico, 1° a 4° Medio) y con las carpetas
    especiales («5 basico Orientacion») justo después de su nivel."""
    def orden(carpeta: str) -> tuple:
        nivel = nivel_de_carpeta(carpeta)
        return (nivel is None, nivel or 0, carpeta.lower())
    ordenadas = sorted(carpetas, key=orden)
    return ([c for c in ordenadas if nivel_de_carpeta(c) in propios],
            [c for c in ordenadas if nivel_de_carpeta(c) not in propios])


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
    salida = {"clave": str(dato["clave"]), "estado": dato["estado"],
              "titulo": str(dato.get("titulo") or dato["clave"]),
              "grupo": str(dato.get("grupo") or ""), "que": str(dato.get("que") or ""),
              "detalle": str(dato.get("detalle") or ""), "motivo": str(dato.get("motivo") or ""),
              "opciones": opciones}
    # Con qué marcar el ítem «no hubo clase»: un bloque del libro (clave con fecha) o una clase (su id), y su día.
    sin_clase = dato.get("sin_clase")
    if (isinstance(sin_clase, dict) and sin_clase.get("campo") in ("bloques", "clases") and sin_clase.get("clave")):
        dia = fecha_iso(sin_clase.get("dia"))
        salida["sin_clase"] = {"campo": sin_clase["campo"], "clave": str(sin_clase["clave"]),
                               "dia": dia.isoformat() if dia else "",
                               "titulo": str(sin_clase.get("titulo") or salida["titulo"])[:80]}
    return salida


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


# ------------------------------------------------------------ días sin clases
# Feriados, salidas, vacaciones: lo que el docente marca como «no hubo clases» deja de aparecer como pendiente
# en la tarjeta «Hoy», en «Registrar libro» (y el pendiente) y en «Asignar clases». Un archivo por cuenta
# (rutas.sin_clases):
#   {"dias": {"2026-10-12": "Feriado"}, "bloques": {"5BA|08:00-09:30|123|2026-10-09": "5BA 08:00"},
#    "clases": {"98765": "5BA · Clase 3"}}
# Un bloque lleva su fecha al final de la clave (la misma de la casilla en la vista previa de varios días).
DIAS_CORTOS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MAX_DIAS_SIN_CLASES = 120       # unas vacaciones caben de sobra; un año entero por error de tipeo, no


def fecha_iso(texto) -> datetime.date | None:
    """'2026-10-12' -> date (None si no es una fecha así)."""
    try:
        return datetime.date.fromisoformat(str(texto or "")[:10])
    except ValueError:
        return None


def fecha_de_estado(texto) -> datetime.date | None:
    """'12/10/2026' (como vienen las fechas del estado del libro) -> date, o None."""
    try:
        return datetime.datetime.strptime(str(texto or "").strip()[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def leer_sin_clases(ruta: str) -> dict:
    """Lo marcado como «no hubo clases»: siempre con las tres listas, aunque falte el archivo o venga roto."""
    datos = leer_json(ruta)
    salida = {}
    for campo in ("dias", "bloques", "clases"):
        valor = datos.get(campo)
        salida[campo] = {str(k): str(v or "") for k, v in valor.items()} if isinstance(valor, dict) else {}
    salida["dias"] = {k: v for k, v in salida["dias"].items() if fecha_iso(k)}
    return salida


def guardar_sin_clases(ruta: str, datos: dict) -> None:
    limpio = {campo: dict(sorted((datos.get(campo) or {}).items())) for campo in ("dias", "bloques", "clases")}
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    escribir_atomico(ruta, json.dumps(limpio, ensure_ascii=False, indent=1))


def marcar_dias_sin_clases(ruta: str, dias: list[datetime.date], motivo: str = "") -> list[str]:
    """Deja esos días como «no hubo clases» (los fines de semana no hace falta). Devuelve los que agregó."""
    datos = leer_sin_clases(ruta)
    agregados = []
    for dia in sorted(set(dias)):
        if dia.weekday() >= 5:
            continue
        clave = dia.isoformat()
        if clave not in datos["dias"]:
            agregados.append(clave)
        datos["dias"][clave] = (motivo or "").strip()[:60]
    guardar_sin_clases(ruta, datos)
    return agregados


def dias_para_marcar(desde_texto: str, hasta_texto: str = "", hoy: datetime.date | None = None) -> list[datetime.date]:
    """Los días hábiles de «desde» a «hasta» (o solo «desde»). ValueError con un mensaje claro si no sirve.

    Se pueden marcar días que vienen (un feriado de la próxima semana, las vacaciones de invierno).
    """
    hoy = hoy or datetime.date.today()
    desde = parsear_fecha(desde_texto, hoy)
    hasta = parsear_fecha(hasta_texto, hoy) if (hasta_texto or "").strip() else desde
    if hasta < desde:
        raise ValueError("El último día no puede ser antes del primero.")
    if (hasta - desde).days > MAX_DIAS_SIN_CLASES:
        raise ValueError(f"Es mucho tiempo: como máximo {MAX_DIAS_SIN_CLASES} días de una vez.")
    dias = dias_habiles(desde, hasta)
    if not dias:
        raise ValueError("Es fin de semana: esos días ya no se revisan.")
    return dias


def quitar_sin_clases(ruta: str, campo: str, claves: list[str]) -> None:
    """Deshace lo marcado: días (ISO), bloques o clases."""
    datos = leer_sin_clases(ruta)
    for clave in claves:
        datos.get(campo, {}).pop(str(clave), None)
    guardar_sin_clases(ruta, datos)


def ignorar_en_sin_clases(ruta: str, campo: str, clave: str, titulo: str = "") -> None:
    """«No hubo esta clase»: un bloque del libro (clave con su fecha) o una clase de la planificación (su id)."""
    datos = leer_sin_clases(ruta)
    datos[campo][str(clave)] = (titulo or "").strip()[:80]
    guardar_sin_clases(ruta, datos)


def clave_con_fecha(clave: str, dia: datetime.date) -> str:
    """La clave de un bloque con su fecha al final (si ya la trae, queda igual)."""
    return clave if fecha_iso(clave.rsplit("|", 1)[-1]) else f"{clave}|{dia.isoformat()}"


def dia_sin_clases(datos: dict, dia: datetime.date | None) -> bool:
    return dia is not None and dia.isoformat() in datos.get("dias", {})


def bloque_sin_clase(datos: dict, clave: str, dia: datetime.date) -> bool:
    """¿Ese bloque (o su día entero) quedó marcado como «no hubo clase»?"""
    return dia_sin_clases(datos, dia) or clave_con_fecha(clave, dia) in datos.get("bloques", {})


def bloque_sin_clase_por_hora(datos: dict, curso: str, inicio: str, dia: datetime.date) -> bool:
    """Lo mismo, cuando solo se sabe el curso y la hora de inicio (las filas del «Informe del mes»)."""
    if dia_sin_clases(datos, dia):
        return True
    for clave in datos.get("bloques", {}):
        partes = clave.split("|")
        if (len(partes) >= 3 and partes[0] == curso and partes[1].startswith(f"{inicio}-")
                and partes[-1] == dia.isoformat()):
            return True
    return False


def clase_sin_tarea(datos: dict, idclase, fechaini: str) -> bool:
    """¿Esa clase de la planificación no se hizo (marcada a mano, o su fecha es un día sin clases)?"""
    return str(idclase) in datos.get("clases", {}) or dia_sin_clases(datos, fecha_de_estado(fechaini))


def aplicar_sin_clases(estado: dict | None, datos: dict) -> dict | None:
    """El estado del libro sin lo marcado como «no hubo clases».

    Se aplica al mostrarlo, así lo que se marca vale al tiro, sin esperar la próxima revisión del libro.
    """
    if not isinstance(estado, dict) or estado.get("error"):
        return estado
    salida = dict(estado)
    dia = fecha_de_estado(estado.get("fecha"))
    if dia_sin_clases(datos, dia):
        salida.update(sin_clases=True, bloques=[], sin_firmar=[], sin_registro=[])
    elif dia is not None:
        for campo in ("bloques", "sin_firmar", "sin_registro"):
            salida[campo] = [b for b in estado.get(campo) or []
                             if clave_con_fecha(clave_de_bloque(b), dia) not in datos.get("bloques", {})]
    atrasados = []
    for a in estado.get("atrasados") or []:
        if dia_sin_clases(datos, fecha_de_estado(a.get("fecha"))):
            continue
        claves = a.get("claves")
        if isinstance(claves, list):
            quedan = [k for k in claves if k not in datos.get("bloques", {})]
            if not quedan:
                continue
            a = {**a, "bloques": len(quedan), "claves": quedan, "cursos": sorted({k.split("|")[0] for k in quedan})}
        atrasados.append(a)
    salida["atrasados"] = atrasados
    return salida


def _dia_habil_siguiente(dia: datetime.date) -> datetime.date:
    dia += datetime.timedelta(days=1)
    while dia.weekday() >= 5:
        dia += datetime.timedelta(days=1)
    return dia


def tramos_sin_clases(dias: dict) -> list[dict]:
    """Los días marcados, juntando los seguidos con el mismo motivo (unas vacaciones son una sola fila).

    [{desde, hasta, motivo, dias: [ISO…], texto}], del más reciente al más antiguo.
    """
    tramos: list[dict] = []
    for dia in sorted(d for d in (fecha_iso(k) for k in dias) if d):
        motivo = dias.get(dia.isoformat(), "")
        ultimo = tramos[-1] if tramos else None
        if ultimo and ultimo["motivo"] == motivo and _dia_habil_siguiente(ultimo["hasta"]) == dia:
            ultimo["hasta"] = dia
            ultimo["dias"].append(dia.isoformat())
        else:
            tramos.append({"desde": dia, "hasta": dia, "motivo": motivo, "dias": [dia.isoformat()]})
    for t in tramos:
        d, h = t["desde"], t["hasta"]
        t["texto"] = (f"{DIAS_CORTOS[d.weekday()]} {d:%d/%m/%Y}" if d == h else
                      f"{DIAS_CORTOS[d.weekday()]} {d:%d/%m} al {DIAS_CORTOS[h.weekday()]} {h:%d/%m/%Y} "
                      f"({len(t['dias'])} días)")
    return list(reversed(tramos))


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


# ------------------------------------------------------------ accesos directos de Windows
def _texto_ps(valor: str) -> str:
    """Texto entre comillas simples para PowerShell (las comillas simples de adentro se duplican)."""
    return "'" + str(valor).replace("'", "''") + "'"


def _powershell(guion: str, timeout: int = 40) -> str:
    import subprocess
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + guion],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise OSError((r.stderr or r.stdout or "PowerShell no respondió").strip()[:300])
    return r.stdout


def _lista_json(salida: str) -> list[dict]:
    salida = (salida or "").strip()
    if not salida:
        return []
    datos = json.loads(salida)
    return datos if isinstance(datos, list) else [datos]


def leer_accesos() -> list[dict]:
    """Los accesos directos (.lnk) del escritorio, del menú Inicio y de la carpeta «Inicio» de Windows:
    [{"ruta", "carpeta" (escritorio/inicio/programas), "destino", "argumentos", "atajo"}]. Solo lee."""
    guion = ("$s=New-Object -ComObject WScript.Shell; $r=@(); "
             "foreach($par in @(@('escritorio',[Environment]::GetFolderPath('Desktop')),"
             "@('inicio',[Environment]::GetFolderPath('Startup')),"
             "@('programas',[Environment]::GetFolderPath('Programs')))){"
             " if($par[1] -and (Test-Path -LiteralPath $par[1])){"
             "  Get-ChildItem -LiteralPath $par[1] -Filter *.lnk | ForEach-Object {"
             "   $a=$s.CreateShortcut($_.FullName);"
             "   $r+=[pscustomobject]@{ruta=$_.FullName;carpeta=$par[0];destino=$a.TargetPath;"
             "argumentos=$a.Arguments;atajo=$a.Hotkey}}}};"
             "ConvertTo-Json -InputObject @($r) -Compress")
    return _lista_json(_powershell(guion))


def leer_acceso(ruta: str) -> dict:
    """Un acceso directo: {"destino", "argumentos", "atajo"} (vacío si no existe)."""
    if not os.path.isfile(ruta):
        return {}
    guion = (f"$a=(New-Object -ComObject WScript.Shell).CreateShortcut({_texto_ps(ruta)});"
             "ConvertTo-Json -InputObject ([pscustomobject]@{destino=$a.TargetPath;argumentos=$a.Arguments;"
             "atajo=$a.Hotkey}) -Compress")
    datos = _lista_json(_powershell(guion))
    return datos[0] if datos else {}


def escribir_acceso(ruta: str, destino: str, argumentos: str, carpeta: str, atajo: str = "") -> None:
    """Crea o rehace un acceso directo de Windows, con su atajo de teclado («CTRL+ALT+A») o sin atajo."""
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    _powershell("$a=(New-Object -ComObject WScript.Shell).CreateShortcut(" + _texto_ps(ruta) + "); "
                f"$a.TargetPath={_texto_ps(destino)}; $a.Arguments={_texto_ps(argumentos)}; "
                f"$a.WorkingDirectory={_texto_ps(carpeta)}; $a.Hotkey={_texto_ps(atajo)}; $a.Save()")


def carpeta_especial(nombre: str) -> str:
    """Desktop, Startup o Programs de este usuario, como las ve Windows (respeta OneDrive)."""
    return _powershell(f"[Environment]::GetFolderPath({_texto_ps(nombre)})").strip()


def script_de_acceso(acceso: dict) -> str:
    """La ruta del barra_profe.pyw que abre un acceso directo ('' si no es de la barra)."""
    m = re.search(r'"?([^"]*barra_profe\.pyw)"?', acceso.get("argumentos") or "", re.IGNORECASE)
    return m.group(1).strip() if m else ""


def accesos_de_la_barra(accesos: list[dict]) -> list[dict]:
    """Los accesos que abren una barra, cada uno con su «script» y «roto» (True si ese archivo ya no existe)."""
    salida = []
    for acceso in accesos:
        script = script_de_acceso(acceso)
        if script:
            salida.append({**acceso, "script": script, "roto": not os.path.isfile(script)})
    return salida


def atajo_de_letra(letra: str) -> str:
    """'A' -> 'CTRL+ALT+A' (como lo pide Windows); '' si no hay letra (sin atajo)."""
    letra = (letra or "").strip().upper()
    return f"CTRL+ALT+{letra}" if re.fullmatch(r"[A-Z0-9]", letra) else ""


def letra_del_atajo(atajo: str) -> str:
    """'Alt+Ctrl+A' (como lo informa Windows) -> 'A'; '' si no es un atajo Ctrl+Alt+letra."""
    partes = [p.strip().upper() for p in (atajo or "").split("+") if p.strip()]
    if len(partes) == 3 and {"CTRL", "ALT"} <= set(partes):
        letra = next(p for p in partes if p not in ("CTRL", "ALT"))
        return letra if re.fullmatch(r"[A-Z0-9]", letra) else ""
    return ""


# ------------------------------------------------------------ respaldo de la configuración
def exportar_configuracion(destino: str, archivos: dict[str, str], info: dict) -> list[str]:
    """Zip con la configuración del docente: de `archivos` ({nombre en el zip: ruta en este PC}) solo los que
    existen, más un info.json. Devuelve los nombres incluidos."""
    import zipfile
    incluidos = []
    temporal = f"{destino}.tmp"
    with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, ruta in archivos.items():
            if ruta and os.path.isfile(ruta):
                z.write(ruta, nombre)
                incluidos.append(nombre)
        z.writestr("info.json", json.dumps({**info, "archivos": incluidos}, ensure_ascii=False, indent=1))
    os.replace(temporal, destino)
    return incluidos


def importar_configuracion(origen: str, archivos: dict[str, str], copia: str) -> list[str]:
    """Restaura un respaldo: solo los nombres que están en `archivos` (lo demás del zip se ignora). Antes guarda lo
    actual en `copia`. Lanza ValueError si el archivo no es un respaldo de Barra Profe."""
    import zipfile
    try:
        zf = zipfile.ZipFile(origen)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("Ese archivo no es un respaldo de Barra Profe.") from exc
    with zf:
        presentes = zf.namelist()
        nombres = [n for n in presentes if n in archivos]
        if "info.json" not in presentes or not nombres:
            raise ValueError("Ese archivo no es un respaldo de Barra Profe.")
        os.makedirs(os.path.dirname(copia) or ".", exist_ok=True)
        exportar_configuracion(copia, archivos, {"tipo": "copia de lo que había antes de importar"})
        for nombre in nombres:
            destino = archivos[nombre]
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            temporal = f"{destino}.tmp"
            with open(temporal, "wb") as f:
                f.write(zf.read(nombre))
            os.replace(temporal, destino)
    return nombres
