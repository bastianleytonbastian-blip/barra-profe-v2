"""Perfil del docente y del colegio: reemplaza todo lo que antes estaba fijo en el código.

Hay un perfil por cuenta de Barra Profe (el de la cuenta activa); ver nucleo/rutas.py.
"""
import json
import os
from dataclasses import asdict, dataclass, field, fields

from nucleo import rutas

VOCES = {
    "neutra": "Redacta con lenguaje inclusivo y neutro ('el curso', 'las y los estudiantes' solo si es necesario; "
              "prefiere formas como 'estudiantes' sin artículo de género).",
    "femenina": "Redacta estrictamente en tercera persona plural femenina ('las estudiantes observan', 'las estudiantes "
                "leen en pareja'). Los roles y adjetivos referidos al curso van siempre en femenino.",
    "masculina": "Redacta en tercera persona plural masculina genérica ('los estudiantes observan', 'los estudiantes "
                 "leen en pareja').",
}


@dataclass
class Perfil:
    nombre_docente: str = ""
    colegio: str = ""
    departamento: str = ""
    asignaturas: list = field(default_factory=list)   # asignaturas que enseña (vacío = todas)
    contexto_colegio: str = ""                         # ej. "colegio católico de Recoleta, comuna con memoria obrera"
    voz: str = "neutra"                                # neutra | femenina | masculina
    tratamiento_docente: str = "el profesor"           # cómo se nombra al docente en el texto
    apertura_fija: str = ""                            # primera línea del Inicio (ej. un lema institucional); vacío = ninguna
    enfoque_pedagogico: str = ""                       # marco teórico o enfoque que la IA debe seguir (texto libre)
    actividades_extra: list = field(default_factory=list)  # [{"nombre", "curso", "minutos", "descripcion"}]
    duracion_defecto: int = 90                         # minutos de un bloque de clase
    ruta_logo: str = ""                                # nombre del archivo del logo, dentro de la carpeta personal (opcional)
    asignaturas_webclass: dict = field(default_factory=dict)  # {nombre: id} extra del select de asignatura de WebClass
    ruta_barra: str = ""                               # carpeta de «Barra Profe v2» (solo si el planificador está suelto)
    # Preferencias de la pantalla (Mi perfil → Preferencias)
    tema: str = "sistema"                              # sistema | claro | oscuro
    color_barra: bool = True                           # usar el color que el docente eligió en la barra
    asignatura_defecto: str = ""                       # con qué asignatura parte «Planificar una clase»
    curso_defecto: str = ""
    hora_defecto: str = "08:00"                        # hora de inicio con que se crean las clases en WebClass
    plantillas: list = field(default_factory=list)     # indicaciones reutilizables: [{"nombre", "texto"}]

    @property
    def completo(self):
        return bool(self.nombre_docente.strip() and self.colegio.strip())

    def encabezado(self, asignatura):
        """Datos del encabezado de las guías PIE (HTML y Word)."""
        return {"logo": ruta_logo_completa(self), "colegio": self.colegio.strip(), "departamento": self.departamento.strip(),
                "asignatura": (asignatura or "").strip(),
                "docente": f"Prof. {self.nombre_docente.strip()}" if self.nombre_docente.strip() else ""}


def _sanear(datos):
    validos = {f.name for f in fields(Perfil)}
    return {k: v for k, v in (datos or {}).items() if k in validos}


def _ruta_perfil():
    return os.path.join(rutas.personal_usuario(), "perfil.json")


TEMAS = ("sistema", "claro", "oscuro")


def cargar():
    """Perfil de la cuenta activa.

    Dentro de Barra, el nombre del docente es siempre el de su cuenta de Barra (un solo nombre para las dos apps);
    suelto, el que se escribió en «Mi perfil».
    """
    try:
        with open(_ruta_perfil(), encoding="utf-8") as f:
            perfil = Perfil(**_sanear(json.load(f)))
    except Exception:
        perfil = Perfil()
    nombre_barra = rutas.nombre_de_cuenta()
    if nombre_barra:
        perfil.nombre_docente = nombre_barra
    if perfil.tema not in TEMAS:
        perfil.tema = "sistema"
    return perfil


def guardar(perfil):
    ruta = _ruta_perfil()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(asdict(perfil), f, ensure_ascii=False, indent=2)


def ruta_logo_completa(perfil):
    """Ruta del logo en disco ('' si no hay). Acepta el nombre de archivo o una ruta completa de versiones anteriores."""
    if not perfil.ruta_logo:
        return ""
    ruta = perfil.ruta_logo if os.path.isabs(perfil.ruta_logo) else os.path.join(rutas.personal_usuario(), perfil.ruta_logo)
    return ruta if os.path.isfile(ruta) else ""


def guardar_logo(nombre_archivo, contenido):
    """Guarda el logo subido en la carpeta personal de la cuenta y devuelve su nombre de archivo."""
    ext = os.path.splitext(nombre_archivo)[1].lower() or ".png"
    carpeta = rutas.personal_usuario()
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, "logo" + ext), "wb") as f:
        f.write(contenido)
    return "logo" + ext
