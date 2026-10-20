"""Dónde vive cada cosa del planificador y de quién es.

Dos modos:
  · Dentro de Barra Profe  (…\\Barra Profe v2\\herramienta\\planificador): el planificador viaja con la barra y usa SU cuenta.
        código     herramienta\\planificador\\
        personal   personal\\planificador\\<cuenta>\\   perfil, logo, claves de IA   (no se reparte)
        datos      datos\\planificador\\<cuenta>\\       planificaciones, materiales, guías PIE
        común      datos\\planificador\\                 currículo oficial, registro del servidor
  · Suelto (desarrollo): todo en la carpeta data\\ junto al código, cuenta «local».

La cuenta es la que está ACTIVA en Barra (datos\\perfil_activo.txt, igual que Barra) y se lee en cada llamada: si en la barra
se cambia de profesor, el planificador cambia con ella. Nunca se guarda ni se pide una contraseña aquí: las de WebClass
están en el Administrador de credenciales de Windows y solo las usa Barra.
"""
import json
import os

CODIGO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # carpeta del planificador (donde está servidor.py)


def _detectar_barra():
    """Carpeta raíz de Barra Profe si el planificador está instalado dentro de ella (o la que se fuerce con la variable)."""
    forzada = os.environ.get("PLANIFICADOR_BARRA", "").strip().strip('"')
    if forzada:
        return forzada
    herramienta = os.path.dirname(CODIGO)
    if os.path.basename(herramienta).lower() == "herramienta" and \
            os.path.isfile(os.path.join(herramienta, "webclass_clases.py")):
        return os.path.dirname(herramienta)
    return None


BARRA = _detectar_barra()
EN_BARRA = BARRA is not None
_PERFILES_BARRA = os.path.join(BARRA, "personal", "perfiles") if EN_BARRA else ""
_ACTIVO_BARRA = os.path.join(BARRA, "datos", "perfil_activo.txt") if EN_BARRA else ""

DATOS_COMUN = os.path.join(BARRA, "datos", "planificador") if EN_BARRA else os.path.join(CODIGO, "data")
PERSONAL_COMUN = os.path.join(BARRA, "personal", "planificador") if EN_BARRA else os.path.join(CODIGO, "data")


def perfiles_barra():
    """Claves de las cuentas que tiene Barra en este equipo (solo los nombres de archivo)."""
    if not EN_BARRA or not os.path.isdir(_PERFILES_BARRA):
        return []
    return sorted(a[:-5] for a in os.listdir(_PERFILES_BARRA) if a.endswith(".json"))


def clave_activa():
    """La cuenta que Barra tiene activa, con la misma regla de Barra: la de perfil_activo.txt si existe; si no, la primera.
    Fuera de Barra, «local»."""
    if not EN_BARRA:
        return "local"
    perfiles = perfiles_barra()
    try:
        with open(_ACTIVO_BARRA, encoding="utf-8") as f:
            elegida = f.read().strip()
    except OSError:
        elegida = ""
    if elegida in perfiles:
        return elegida
    return perfiles[0] if perfiles else "local"


def nombre_de_cuenta(clave=None):
    """Nombre del docente según el perfil de Barra (solo se lee la clave «nombre»; nunca el RUT ni otros datos)."""
    clave = clave or clave_activa()
    if not EN_BARRA or clave == "local":
        return ""
    try:
        with open(os.path.join(_PERFILES_BARRA, f"{clave}.json"), encoding="utf-8-sig") as f:
            return str(json.load(f).get("nombre") or "").strip()
    except (OSError, ValueError):
        return ""


def asignaturas_webclass_de_cuenta(clave=None):
    """Asignaturas de WebClass que Barra leyó para esa cuenta ([{id, nombre}]; solo esa clave del perfil, nunca el RUT
    ni otros datos). [] si no hay Barra o todavía no se leyeron."""
    clave = clave or clave_activa()
    if not EN_BARRA or clave == "local":
        return []
    try:
        with open(os.path.join(_PERFILES_BARRA, f"{clave}.json"), encoding="utf-8-sig") as f:
            lista = json.load(f).get("asignaturas_webclass") or []
    except (OSError, ValueError, AttributeError):
        return []
    return lista if isinstance(lista, list) else []


def _por_usuario(base, clave):
    return os.path.join(base, clave) if EN_BARRA else base


def personal_usuario(clave=None):
    """Carpeta de lo personal de la cuenta activa (perfil, logo, claves de IA)."""
    return _por_usuario(PERSONAL_COMUN, clave or clave_activa())


def datos_usuario(clave=None):
    """Carpeta de lo generado por la cuenta activa (planificaciones, materiales, guías PIE)."""
    return _por_usuario(DATOS_COMUN, clave or clave_activa())


def registro_planificaciones(clave=None):
    """Archivo CSV con lo que el planificador creó en WebClass para esa cuenta (misma regla que `rutas.registro` de Barra:
    la cuenta «dueña del registro histórico» usa el nombre sin sufijo; las demás, `_<cuenta>`). '' si no hay Barra."""
    if not EN_BARRA:
        return ""
    clave = clave or clave_activa()
    try:
        with open(os.path.join(BARRA, "datos", "registro_historico.txt"), encoding="utf-8") as f:
            dueno = f.read().strip()
    except OSError:
        dueno = ""
    dueno = dueno or (perfiles_barra() or [""])[0]
    nombre = "registro_planificaciones.csv" if clave == dueno else f"registro_planificaciones_{clave}.csv"
    return os.path.join(BARRA, "datos", nombre)


def ruta_barra(respaldo=""):
    """Carpeta de Barra Profe: la de la instalación o, si el planificador está suelto, la que el docente indicó."""
    return BARRA or respaldo


def tema_de_barra(clave=None):
    """Archivo donde Barra guarda la apariencia (color, letra, ancho) de esa cuenta. '' si no hay Barra."""
    if not EN_BARRA:
        return ""
    clave = clave or clave_activa()
    nombre = "tema.json" if clave == "local" else f"tema_{clave}.json"   # misma regla que `_sufijo` en la barra
    return os.path.join(BARRA, "datos", nombre)
