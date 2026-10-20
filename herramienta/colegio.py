"""
Lo que el administrador reparte a todos los profes: claves de IA del colegio y mensajes o avisos del día.

Viaja por GitHub, adjunto a un release fijo («buzon») del mismo repositorio de las actualizaciones. Ese repositorio es
público, así que el archivo tiene dos partes:
  - lo que va para TODOS los profes viaja sin cifrar, para que lo vean sin configurar nada (y lo puede leer cualquiera
    en internet: es como un aviso en la entrada del colegio);
  - los mensajes a profes en particular (llevan su nombre o RUT) y las claves de IA van CIFRADOS (Fernet: AES + HMAC)
    con la «clave del colegio». La crea el administrador una sola vez y se pega en cada PC; queda en el Administrador de
    credenciales de Windows, nunca en un archivo.

    lo que se publica (y se guarda en datos\\colegio.json):
        {"formato": 1, "sal": "<base64>", "datos": "<Fernet>", "publico": {"mensajes": [...], "publicado": "…"}}
    lo que va cifrado en «datos»:
        {"claves": {"GEMINI_API_KEY": "…"}, "mensajes": [los dirigidos], "publicado": "2026-10-20 08:00"}
    cada mensaje: {id, tipo, para, texto, fecha, de, creado}

Un mensaje («mensaje») se ve hasta que el profe lo marca leído; un aviso del día («aviso») se ve solo en su fecha.
`para` es «*» (todos) o RUT / nombre de uno o varios profes, separados por coma.

Límite honesto: cualquiera que tenga la clave del colegio puede abrir la parte cifrada entera, también los mensajes que
van a otro profe. Para algo confidencial, mejor el correo.

Este módulo es LIVIANO a propósito (nada de red ni de llavero al importarlo): el planificador lo carga para leer las
claves de IA del colegio.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import re
import secrets
import subprocess
import time
import unicodedata
import uuid

REPO = "bastianleytonbastian-blip/barra-profe-v2"      # el mismo de actualizador.REPO (aquí no se importa: va liviano)
ETIQUETA = "buzon"           # release preliminar: nunca es la «última versión» que buscan las actualizaciones
ARCHIVO = "colegio.json"
URL = "https://github.com/{repo}/releases/download/" + ETIQUETA + "/" + ARCHIVO
SERVICIO, USUARIO = "barra-colegio", "colegio"          # dónde queda la clave del colegio en el llavero de Windows
FORMATO = 1
ITERACIONES = 200_000
LETRAS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"            # sin O/0 ni I/1: se dicta y se copia sin confundirse
LARGO = 20                                              # 20 letras de 32 posibles: 100 bits
MAX_ARCHIVO = 512 * 1024
MAX_TEXTO = 1000
TIPOS = ("mensaje", "aviso")
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# Proveedores de IA del planificador (nombre, nombre de la clave, dónde se saca gratis): los mismos de su ia.PROVEEDORES.
PROVEEDORES_IA = (("Gemini (Google)", "GEMINI_API_KEY", "aistudio.google.com/apikey"),
                  ("Groq", "GROQ_API_KEY", "console.groq.com/keys"),
                  ("Cerebras", "CEREBRAS_API_KEY", "cloud.cerebras.ai"),
                  ("OpenRouter", "OPENROUTER_API_KEY", "openrouter.ai/settings/keys"))


# ------------------------------------------------------------ clave del colegio
def generar_codigo() -> str:
    """Una clave del colegio nueva, en grupos de 4 («K7M2-9QXP-…») para dictarla o copiarla."""
    return formatear_codigo("".join(secrets.choice(LETRAS) for _ in range(LARGO)))


def normalizar_codigo(texto) -> str:
    """'k7m2-9qxp …' -> 'K7M29QXP…'; '' si no es una clave del colegio válida."""
    limpio = re.sub(r"[^A-Za-z0-9]", "", str(texto or "")).upper()
    return limpio if len(limpio) == LARGO and all(c in LETRAS for c in limpio) else ""


def formatear_codigo(codigo) -> str:
    c = normalizar_codigo(codigo)
    return "-".join(c[i:i + 4] for i in range(0, len(c), 4))


_derivadas: dict = {}


def _clave_fernet(codigo: str, sal: bytes) -> bytes:
    """De la clave del colegio a la llave de cifrado (PBKDF2: probar claves al azar cuesta caro)."""
    if (codigo, sal) not in _derivadas:
        _derivadas[(codigo, sal)] = base64.urlsafe_b64encode(
            hashlib.pbkdf2_hmac("sha256", codigo.encode(), sal, ITERACIONES, 32))
    return _derivadas[(codigo, sal)]


_codigo_leido = {"instante": 0.0, "codigo": ""}


def codigo_guardado(vigencia: float = 30) -> str:
    """La clave del colegio de este PC ('' si no hay). Se relee cada 30 s: si se pega una nueva, vale al tiro."""
    if vigencia <= 0 or time.time() - _codigo_leido["instante"] > vigencia:
        try:
            import keyring
            _codigo_leido["codigo"] = normalizar_codigo(keyring.get_password(SERVICIO, USUARIO) or "")
        except Exception:  # noqa: BLE001  (sin llavero: como si no hubiera clave)
            _codigo_leido["codigo"] = ""
        _codigo_leido["instante"] = time.time()
    return _codigo_leido["codigo"]


def guardar_codigo(codigo) -> str:
    """Guarda la clave del colegio en el llavero de Windows. ValueError si no es válida."""
    limpio = normalizar_codigo(codigo)
    if not limpio:
        raise ValueError(f"La clave del colegio son {LARGO} letras y números (por ejemplo K7M2-9QXP-…). Revísala.")
    import keyring
    keyring.set_password(SERVICIO, USUARIO, limpio)
    _codigo_leido.update(instante=time.time(), codigo=limpio)
    return limpio


# ------------------------------------------------------------------ el paquete
def paquete_valido(paquete) -> bool:
    return (isinstance(paquete, dict) and paquete.get("formato") == FORMATO and isinstance(paquete.get("sal"), str)
            and isinstance(paquete.get("datos"), str))


def contenido_vacio() -> dict:
    return {"claves": {}, "mensajes": [], "publicado": ""}


def _fecha(texto) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(texto or "")[:10])
    except ValueError:
        return None


def mensaje_valido(m) -> bool:
    return (isinstance(m, dict) and m.get("tipo") in TIPOS and isinstance(m.get("id"), str)
            and isinstance(m.get("texto"), str) and bool(m["texto"].strip())
            and (m["tipo"] != "aviso" or _fecha(m.get("fecha")) is not None))


def limpiar(contenido) -> dict:
    """El contenido con la forma esperada, sin nada raro (lo que no calza se descarta)."""
    if not isinstance(contenido, dict):
        return contenido_vacio()
    claves = contenido.get("claves") if isinstance(contenido.get("claves"), dict) else {}
    return {"claves": {str(k): v.strip() for k, v in claves.items() if isinstance(v, str) and v.strip()},
            "mensajes": [m for m in contenido.get("mensajes") or [] if mensaje_valido(m)],
            "publicado": str(contenido.get("publicado") or "")}


def es_general(mensaje: dict) -> bool:
    """¿Va para todos? Entonces viaja sin cifrar."""
    destinos = destinatarios(str(mensaje.get("para") or "*"))
    return not destinos or "*" in destinos


def cerrar(codigo, contenido: dict, sal: bytes | None = None) -> dict:
    """El paquete que se publica: lo general a la vista y lo dirigido y las claves, cifrado. ValueError si la clave del
    colegio no sirve."""
    from cryptography.fernet import Fernet
    limpio = normalizar_codigo(codigo)
    if not limpio:
        raise ValueError("La clave del colegio no es válida.")
    contenido = limpiar(contenido)
    generales = [m for m in contenido["mensajes"] if es_general(m)]
    privado = {**contenido, "mensajes": [m for m in contenido["mensajes"] if not es_general(m)]}
    sal = sal or os.urandom(16)
    datos = Fernet(_clave_fernet(limpio, sal)).encrypt(json.dumps(privado, ensure_ascii=False).encode())
    return {"formato": FORMATO, "sal": base64.b64encode(sal).decode(), "datos": datos.decode(),
            "publico": {"mensajes": generales, "publicado": contenido["publicado"]}}


def parte_publica(paquete) -> dict:
    """Lo que va para todos, sin cifrar: se lee sin la clave del colegio. Algo dirigido que apareciera aquí se ignora."""
    publico = paquete.get("publico") if isinstance(paquete, dict) and isinstance(paquete.get("publico"), dict) else {}
    contenido = limpiar({"mensajes": publico.get("mensajes"), "publicado": publico.get("publicado")})
    contenido["mensajes"] = [m for m in contenido["mensajes"] if es_general(m)]
    return contenido


def abrir(paquete, codigo) -> dict | None:
    """Todo el contenido (lo general y lo cifrado) si la clave es la del colegio; None si no lo es (o si el paquete no
    sirve o la parte cifrada fue alterada)."""
    limpio = normalizar_codigo(codigo)
    if not (paquete_valido(paquete) and limpio):
        return None
    from cryptography.fernet import Fernet, InvalidToken
    try:
        sal = base64.b64decode(paquete["sal"])
        privado = json.loads(Fernet(_clave_fernet(limpio, sal)).decrypt(paquete["datos"].encode()).decode())
    except (InvalidToken, ValueError, TypeError):
        return None
    if not isinstance(privado, dict):
        return None
    privado = limpiar(privado)
    return {**privado, "mensajes": parte_publica(paquete)["mensajes"] + privado["mensajes"]}


# ------------------------------------------------------- lo guardado en este PC
def leer_paquete(ruta: str) -> dict | None:
    try:
        with open(ruta, encoding="utf-8") as f:
            paquete = json.load(f)
    except (OSError, ValueError):
        return None
    return paquete if paquete_valido(paquete) else None


def guardar_paquete(ruta: str, paquete: dict) -> None:
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    temporal = f"{ruta}.tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(paquete, f)
    os.replace(temporal, ruta)


_abiertos: dict = {}


def contenido_guardado(ruta: str, codigo: str | None = None) -> dict | None:
    """Lo que este PC puede leer del buzón: con la clave del colegio, todo; sin ella (o si no abre), solo lo que va para
    todos. None si todavía no llega nada."""
    try:
        fecha = os.path.getmtime(ruta)
    except OSError:
        return None
    codigo = codigo_guardado() if codigo is None else codigo
    llave = (ruta, fecha, codigo)
    if llave not in _abiertos:
        _abiertos.clear()                   # basta el último: el archivo cambia pocas veces al día
        paquete = leer_paquete(ruta)
        _abiertos[llave] = None if paquete is None else (abrir(paquete, codigo) or parte_publica(paquete))
    return _abiertos[llave]


def estado(ruta: str, codigo: str | None = None) -> str:
    """'sin_buzon' (aún no llega nada), 'sin_codigo', 'codigo_incorrecto' u 'ok' (la parte cifrada se abre)."""
    paquete = leer_paquete(ruta)
    if paquete is None:
        return "sin_buzon"
    codigo = codigo_guardado() if codigo is None else codigo
    if not codigo:
        return "sin_codigo"
    return "ok" if abrir(paquete, codigo) is not None else "codigo_incorrecto"


def claves_ia(ruta: str) -> dict:
    """{GEMINI_API_KEY: …} del colegio, para el planificador ({} si no hay o falta la clave del colegio)."""
    return dict((contenido_guardado(ruta) or {}).get("claves") or {})


def descargar(ruta: str, repo: str = REPO, abrir_url=None) -> bool:
    """Trae el buzón de GitHub y lo guarda si cambió (True si cambió). OSError / ValueError si no se pudo.

    Sin release «buzon» todavía, GitHub responde 404 (un OSError): quien llama lo toma como «no hay nada».
    """
    import actualizador                     # solo en la barra: el planificador nunca descarga
    with actualizador._abrir(URL.format(repo=repo), abrir_url, timeout=10) as r:
        crudo = r.read(MAX_ARCHIVO + 1)
    if len(crudo) > MAX_ARCHIVO:
        raise ValueError("El buzón del colegio es demasiado grande.")
    paquete = json.loads(crudo.decode("utf-8-sig"))
    if not paquete_valido(paquete):
        raise ValueError("El buzón del colegio no tiene el formato esperado.")
    if leer_paquete(ruta) == paquete:
        return False
    guardar_paquete(ruta, paquete)
    return True


# --------------------------------------------------------------------- mensajes
def nuevo_mensaje(tipo: str, texto: str, para: str = "*", fecha: datetime.date | None = None, de: str = "",
                  ahora: datetime.datetime | None = None) -> dict:
    """Un mensaje (se ve hasta que lo marcan leído) o un aviso del día (se ve solo en su fecha). ValueError si falta algo."""
    texto = (texto or "").strip()
    if tipo not in TIPOS:
        raise ValueError("Elige si es un mensaje o un aviso del día.")
    if not texto:
        raise ValueError("Escribe el texto.")
    if len(texto) > MAX_TEXTO:
        raise ValueError(f"Es muy largo: como máximo {MAX_TEXTO} letras.")
    if tipo == "aviso" and fecha is None:
        raise ValueError("Un aviso del día necesita su fecha.")
    ahora = ahora or datetime.datetime.now()
    return {"id": uuid.uuid4().hex[:12], "tipo": tipo, "para": (para or "").strip() or "*", "texto": texto,
            "fecha": fecha.isoformat() if fecha else "", "de": (de or "").strip(), "creado": f"{ahora:%Y-%m-%d %H:%M}"}


def _sin_tildes(texto: str) -> str:
    sin = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in sin if unicodedata.category(c) != "Mn").lower()


def _rut(texto: str) -> str:
    return re.sub(r"[^0-9K]", "", (texto or "").upper())


def destinatarios(para: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,;\n]", para or "") if p.strip()]


def es_para(mensaje: dict, rut: str, nombre: str) -> bool:
    """¿Va para este profe? «*» es todos; si no, su RUT (con o sin puntos) o su nombre (todas las palabras)."""
    destinos = destinatarios(str(mensaje.get("para") or "*"))
    if not destinos or "*" in destinos:
        return True
    palabras_nombre = _sin_tildes(nombre).split()
    for destino in destinos:
        if any(c.isdigit() for c in destino):
            if rut and len(_rut(destino)) >= 7 and _rut(destino) == _rut(rut):
                return True
            continue
        palabras = _sin_tildes(destino).split()
        if palabras and all(p in palabras_nombre for p in palabras):
            return True
    return False


def para_mostrar(contenido: dict | None, rut: str, nombre: str, hoy: datetime.date, leidos: set) -> list[dict]:
    """Lo que este profe ve hoy: sus mensajes sin leer y los avisos de hoy, del más nuevo al más antiguo."""
    salida = []
    for m in (contenido or {}).get("mensajes") or []:
        if m["id"] in leidos or not es_para(m, rut, nombre):
            continue
        if m["tipo"] == "aviso" and m.get("fecha") != hoy.isoformat():
            continue
        salida.append(m)
    return sorted(salida, key=lambda m: m.get("creado", ""), reverse=True)


def vigentes(mensajes: list[dict], hoy: datetime.date) -> list[dict]:
    """Sin los avisos de días que ya pasaron (al publicar se limpian solos)."""
    return [m for m in mensajes if m["tipo"] != "aviso" or (_fecha(m.get("fecha")) or hoy) >= hoy]


def _lista_de_leidos(ruta: str) -> list[str]:
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return []
    return [str(x) for x in datos] if isinstance(datos, list) else []


def leer_leidos(ruta: str) -> set:
    return set(_lista_de_leidos(ruta))


def marcar_leido(ruta: str, ident: str) -> None:
    """Lo deja leído (se guardan los últimos 300, en orden: los más viejos se olvidan primero)."""
    leidos = [x for x in _lista_de_leidos(ruta) if x != str(ident)][-299:] + [str(ident)]
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(leidos, f)


# ---------------------------------------------------------------- administrador
def _correr(orden: list[str], correr=None, timeout: int = 60):
    return (correr or subprocess.run)(orden, capture_output=True, text=True, timeout=timeout,
                                      creationflags=SIN_VENTANA)


def es_administrador(repo: str = REPO, correr=None) -> bool:
    """¿Este PC puede publicar en el buzón? GitHub CLI («gh») con sesión iniciada y permiso de escritura en el repo."""
    try:
        r = _correr(["gh", "api", f"repos/{repo}", "--jq", ".permissions.push"], correr, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def publicar(paquete: dict, carpeta: str, repo: str = REPO, correr=None) -> None:
    """Sube el buzón cifrado al release «buzon» (la primera vez lo crea, como versión preliminar). RuntimeError si falla."""
    ruta = os.path.join(carpeta, ARCHIVO)
    guardar_paquete(ruta, paquete)
    try:
        if _correr(["gh", "release", "view", ETIQUETA, "-R", repo], correr).returncode != 0:
            creado = _correr(["gh", "release", "create", ETIQUETA, "-R", repo, "--prerelease", "--title",
                              "Buzón del colegio", "--notes", "Avisos y claves del colegio para Barra Profe, cifrados. "
                              "No es una versión del programa: no lo borres."], correr)
            if creado.returncode != 0:
                raise RuntimeError(f"No pude crear el buzón en GitHub: {(creado.stderr or creado.stdout).strip()[-300:]}")
        subido = _correr(["gh", "release", "upload", ETIQUETA, ruta, "-R", repo, "--clobber"], correr, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"No pude usar GitHub CLI («gh»): {exc}") from exc
    if subido.returncode != 0:
        raise RuntimeError(f"No pude subir el buzón a GitHub: {(subido.stderr or subido.stdout).strip()[-300:]}")
