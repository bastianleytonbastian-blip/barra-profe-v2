"""
Dónde vive cada cosa. Un solo lugar para no tener rutas escritas a mano.

La instalación tiene tres carpetas, y la gracia es que no se pisen:

    herramienta\\   el código. Es lo que se actualiza y lo que se reparte.
    personal\\      la configuración de este docente (botones de la barra, perfil).
    datos\\         lo que se va generando: registros, logs, estado de la barra.

Actualizar la herramienta nunca toca personal\\ ni datos\\, y repartirla no se
lleva nada de nadie.

Si el .exe o los scripts están sueltos (sin esas carpetas al lado), todo cae en
la misma carpeta, como antes: así una instalación vieja sigue funcionando.
"""

from __future__ import annotations

import os
import sys


def carpeta_codigo() -> str:
    """Donde están los scripts o el ejecutable."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def raiz() -> str:
    """La carpeta de la instalación: la que contiene herramienta\\, personal\\ y datos\\."""
    codigo = carpeta_codigo()
    if os.path.basename(codigo).lower() == "herramienta":
        return os.path.dirname(codigo)
    return codigo


def _carpeta(nombre: str) -> str:
    """raiz\\<nombre>. Si la instalación es plana, la raíz misma.

    No la crea: importar un módulo no debería dejar carpetas por ahí. Se crean
    recién cuando hay algo que escribir.
    """
    base = raiz()
    if base == carpeta_codigo() and not os.path.isdir(os.path.join(base, nombre)):
        return base          # instalación antigua, todo junto
    return os.path.join(base, nombre)


CODIGO = carpeta_codigo()
RAIZ = raiz()
PERSONAL = _carpeta("personal")
DATOS = _carpeta("datos")
PERFILES = os.path.join(PERSONAL, "perfiles")

# El buzón de recursos vive en Documentos, a la vista, no dentro de la instalación.
BUZON = os.path.join(os.path.expanduser("~"), "Documents", "Subir a Webclass")

# Qué docente está activo en este PC (los PC de sala de profesores tienen varios).
PERFIL_ACTIVO = os.path.join(DATOS, "perfil_activo.txt")


def dato(nombre: str) -> str:
    """Ruta de un archivo generado (registro, log, estado de la barra).

    Asegura la carpeta, porque casi siempre se pide para escribir dentro.
    """
    os.makedirs(DATOS, exist_ok=True)
    return os.path.join(DATOS, nombre)


HISTORICO = os.path.join(DATOS, "registro_historico.txt")


def dueno_del_registro_historico() -> str:
    """Docente a quien pertenece el CSV «de siempre» (sin nombre de perfil).

    Antes todos los registros eran un solo archivo. En un PC compartido eso
    mezclaba a los docentes: cada uno veía las filas de los demás. El archivo
    histórico se le deja al primer perfil que había (y queda anotado para que
    no cambie si después se agregan otros); los demás escriben el suyo.
    """
    try:
        with open(HISTORICO, encoding="utf-8") as f:
            dueno = f.read().strip()
        if dueno:
            return dueno
    except OSError:
        pass
    try:
        claves = sorted(a[:-5] for a in os.listdir(PERFILES) if a.endswith(".json"))
    except OSError:
        claves = []
    if claves:
        try:
            os.makedirs(DATOS, exist_ok=True)
            with open(HISTORICO, "w", encoding="utf-8") as f:
                f.write(claves[0])
        except OSError:
            pass
        return claves[0]
    return ""


def registro(base: str, perfil: str) -> str:
    """Ruta del CSV de registro de ese docente: `<base>.csv` o `<base>_<perfil>.csv`."""
    if not perfil or perfil == dueno_del_registro_historico():
        return os.path.join(DATOS, f"{base}.csv")
    return os.path.join(DATOS, f"{base}_{perfil}.csv")


def sin_clases(perfil: str) -> str:
    """Días (y bloques o clases) que ese docente marcó como «no hubo clases»: datos\\sin_clases_<perfil>.json.

    Lo escribe la barra y lo leen el libro, las tareas y la revisión del libro para no darlos por pendientes.
    """
    return os.path.join(DATOS, f"sin_clases_{perfil}.json" if perfil else "sin_clases.json")


def perfil_activo(por_defecto: str = "") -> str:
    """El perfil elegido en este PC, o el que se pase por defecto."""
    try:
        with open(PERFIL_ACTIVO, encoding="utf-8") as f:
            elegido = f.read().strip()
        if elegido:
            return elegido
    except OSError:
        pass
    return por_defecto


def fijar_perfil_activo(clave: str) -> None:
    os.makedirs(DATOS, exist_ok=True)
    with open(PERFIL_ACTIVO, "w", encoding="utf-8") as f:
        f.write(clave.strip())
