"""Ayudas comunes de las pruebas del planificador con IA (no es una prueba: el nombre no empieza con test_)."""

import contextlib
import importlib
import json
import os
import shutil
import sys
import tempfile

RAIZ_BARRA = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HERRAMIENTA = os.path.join(RAIZ_BARRA, "herramienta")
PLANIFICADOR = os.path.join(HERRAMIENTA, "planificador")

for ruta in (PLANIFICADOR, HERRAMIENTA):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

HAY_PLANIFICADOR = os.path.isfile(os.path.join(PLANIFICADOR, "servidor.py"))


def importar(nombre):
    """Importa un módulo del planificador (p. ej. «nucleo.rutas»)."""
    return importlib.import_module(nombre)


class BarraFalsa:
    """Una carpeta de Barra Profe de mentira, con dos cuentas (ana y beto) y la versión indicada.

    Estructura: personal\\perfiles\\<cuenta>.json (solo con «nombre»; nunca RUT reales), datos\\perfil_activo.txt y
    herramienta\\VERSION. Mientras está activa, el planificador cree que vive dentro de ella.
    """

    def __init__(self, activa="beto", version="minima"):
        if version == "minima":                                  # la que pide el planificador: así no envejece al subirla
            version = importar("nucleo.version").BARRA_MINIMA
        self.carpeta = tempfile.mkdtemp(prefix="BarraFalsa_")
        os.makedirs(os.path.join(self.carpeta, "personal", "perfiles"))
        os.makedirs(os.path.join(self.carpeta, "datos"))
        os.makedirs(os.path.join(self.carpeta, "herramienta"))
        for clave, nombre in (("ana", "Ana Pérez"), ("beto", "Beto Soto")):
            with open(os.path.join(self.carpeta, "personal", "perfiles", clave + ".json"), "w", encoding="utf-8") as f:
                json.dump({"nombre": nombre, "rut": "00000000-0", "iduser": "1"}, f)
        self.cambiar_cuenta(activa)
        self.poner_version(version)

    def cambiar_cuenta(self, clave):
        with open(os.path.join(self.carpeta, "datos", "perfil_activo.txt"), "w", encoding="utf-8") as f:
            f.write(clave)

    def poner_version(self, version):
        ruta = os.path.join(self.carpeta, "herramienta", "VERSION")
        if version is None:
            if os.path.exists(ruta):
                os.remove(ruta)
        else:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(version + "\n")

    def __enter__(self):
        os.environ["PLANIFICADOR_BARRA"] = self.carpeta
        importlib.reload(importar("nucleo.rutas"))
        return self

    def __exit__(self, *exc):
        os.environ.pop("PLANIFICADOR_BARRA", None)
        importlib.reload(importar("nucleo.rutas"))
        shutil.rmtree(self.carpeta, ignore_errors=True)


@contextlib.contextmanager
def carpeta_temporal():
    ruta = tempfile.mkdtemp(prefix="planificador_prueba_")
    try:
        yield ruta
    finally:
        shutil.rmtree(ruta, ignore_errors=True)
