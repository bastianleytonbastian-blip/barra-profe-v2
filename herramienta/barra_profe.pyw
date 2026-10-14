"""
Barra flotante de herramientas del profe.

Vive pegada al borde de la pantalla, plegada, como una lengüeta delgada y
siempre encima del resto de las ventanas. Al pasar el mouse por encima se
despliega sola; al salir, vuelve a plegarse. El 📌 la deja fija abierta.

Las herramientas se leen de herramientas.json, que está al lado de este
archivo: para agregar o sacar botones se edita ese archivo, no el código.
La barra vigila ese archivo y se recarga sola cuando lo guardas.

Arriba de los botones muestra qué clase o actividad hay ahora y cuál viene
(lo lee del horario semanal que mantiene el asistente), y tiene un campo
para anotar: lo que escribas ahí se guarda en la bandeja del asistente y él
lo agenda o lo anota como tarea cuando procesa la bandeja.

Solo corre una barra a la vez: si la abres de nuevo, o aprietas el atajo de
teclado, la copia nueva le avisa a la que ya está abierta (por un puerto
local) y se cierra sola. La barra que estaba se despliega con el cursor
puesto en el campo de anotar.

Se ejecuta con pythonw.exe (sin consola): así lo hacen el .bat, el acceso
directo del escritorio y el de inicio de Windows. Como no hay consola, todo
lo que falle queda escrito en barra_profe.log, al lado de este archivo.
"""

from __future__ import annotations

import ctypes
import datetime
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from tkinter import font as tkfont
from tkinter import messagebox
from tkinter import ttk

def carpeta_datos() -> str:
    """Dónde viven la configuración y el registro.

    Empaquetada como .exe, __file__ apunta a una carpeta temporal que Windows
    borra: los archivos van junto al ejecutable.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rutas                              # noqa: E402
import re                                 # noqa: E402
from barra_utiles import (                # noqa: E402
    ATAJOS_ATRAS, ESTADOS, TOUR_PASOS, agrupar_items, ahora_y_luego, aplicar_destinos,
    argumentos_de_seleccion, cargar_ejecuciones, comando_con_seleccion, dias_de_periodos,
    escribir_atomico, escribir_seleccion, estado_vencido, etiqueta_de_linea, explicar_motivo, filas_de_destinos,
    formatear_fechas, meses_escolares, periodos_de_revision, version_del_codigo,
    formatear_duracion, guardar_ejecucion, hace_cuanto, lineas_de_resultado, marcar_tour_visto,
    minutos, monitores, parsear_item, parsear_opciones, parsear_progreso, partes_de_comando,
    rango_de_atajo, reemplazar_variables, resumir_ejecucion, saludo_para, tour_pendiente,
    asunto_de_correo, cursos_en_nombres, problemas_de_observacion, texto_atrasados, texto_de_correo, traducir_error,
    vista_previa_libro, vista_previa_simulacion, vista_previa_subir)

CARPETA = rutas.CODIGO
# Los botones: primero los de este docente (personal\), si no la plantilla.
CONFIG = (os.path.join(rutas.PERSONAL, "herramientas.json")
          if os.path.isfile(os.path.join(rutas.PERSONAL, "herramientas.json"))
          else os.path.join(CARPETA, "herramientas.json"))
ESTADO = rutas.dato("posicion.json")
LOG = rutas.dato("barra_profe.log")
# TEMA se define más abajo: el color es de cada docente, no del equipo.

CASA = os.path.expanduser("~")

# Carpeta del asistente (Claude). De ahí salen el horario y ahí va la bandeja.
ASISTENTE = os.path.join(CASA, "Asistente personal beta")
BANDEJA = os.path.join(ASISTENTE, "entrada", "bandeja.jsonl")
HORARIO = os.path.join(ASISTENTE, "perfil", "horario_semanal.json")
AGENDA_HOY = os.path.join(ASISTENTE, "registro", "agenda_hoy.json")

# Estado del libro de clases del día (lo escribe estado_firmas.py).
# Las herramientas de Webclass pueden venir junto a la barra (empaquetadas o
# como scripts, según cómo se haya repartido) o estar en su carpeta de siempre.
def docentes_registrados() -> list[tuple[str, str]]:
    """(clave, nombre) de cada docente configurado en este PC.

    En la sala de profesores hay varios en el mismo equipo: la barra muestra
    el que está activo y deja cambiar entre ellos.
    """
    salida = []
    if os.path.isdir(rutas.PERFILES):
        for archivo in sorted(os.listdir(rutas.PERFILES)):
            if not archivo.endswith(".json"):
                continue
            clave = archivo[:-5]
            try:
                with open(os.path.join(rutas.PERFILES, archivo), encoding="utf-8-sig") as f:
                    nombre = (json.load(f).get("nombre") or "").strip()
            except (OSError, ValueError):
                nombre = ""
            salida.append((clave, nombre or clave.title()))
    return salida


DOCENTES = docentes_registrados()
PERFIL = rutas.perfil_activo(DOCENTES[0][0] if DOCENTES else "")
if PERFIL not in [c for c, _ in DOCENTES]:        # se borró el perfil activo
    PERFIL = DOCENTES[0][0] if DOCENTES else ""
NOMBRE_COMPLETO = next((n for c, n in DOCENTES if c == PERFIL), "")

WEBCLASS = CARPETA          # la barra vive junto a las herramientas
# Cada docente tiene lo suyo: si no, al cambiar de profe se vería el libro ajeno.
_sufijo = f"_{PERFIL}" if PERFIL else ""

# Mensajería interna entre barras: la clave del grupo vive en el llavero de Windows, no en un archivo.
SERVICIO_MENSAJERIA = "barra-mensajeria"
RUTA_MENSAJES = rutas.dato(f"mensajes{_sufijo}.json")


def clave_de_mensajeria() -> str:
    try:
        import keyring
        return keyring.get_password(SERVICIO_MENSAJERIA, "grupo") or ""
    except Exception:  # noqa: BLE001  (sin llavero: la mensajería queda apagada)
        return ""


def guardar_clave_mensajeria(clave: str) -> None:
    import keyring
    keyring.set_password(SERVICIO_MENSAJERIA, "grupo", clave.strip())


def nombre_en_mensajeria() -> str:
    """Cómo aparece este docente ante los demás: su nombre de perfil (o la clave del perfil)."""
    try:
        with open(os.path.join(rutas.PERFILES, f"{PERFIL}.json"), encoding="utf-8-sig") as f:
            return (json.load(f).get("nombre") or "").strip() or PERFIL.title() or "Docente"
    except (OSError, ValueError):
        return PERFIL.title() or "Docente"
ESTADO_FIRMAS = rutas.dato(f"estado_firmas{_sufijo}.json")
# El color también es de cada docente: así además se ve de un vistazo quién
# está activo en los equipos que comparten varios.
TEMA = rutas.dato(f"tema{_sufijo}.json")
# Sonido al abrir la barra, si el docente deja un archivo con ese nombre.
SONIDO = [os.path.join(rutas.PERSONAL, f"inicio{ext}") for ext in (".mp3", ".wav")]
TOPE_SONIDO = 600        # segundos: tope de seguridad, por si el archivo miente
REVISOR_FIRMAS = os.path.join(WEBCLASS, "estado_firmas.py")
CALENDARIO = "https://proyecto.webescuela.cl/sistema/webclass/home/portada_profesor.php"
HORARIO_SEMANA = rutas.dato(f"horario_semana{_sufijo}.json")
GENERADOR_HORARIO = os.path.join(WEBCLASS, "horario_semana.py")


def comando_webclass(subcomando: str, *opciones: str) -> list[str]:
    """Cómo lanzar una herramienta de Webclass desde la barra.

    Si está webclass.exe (la versión empaquetada, que no necesita Python), se
    usa ese; si no, python con el script suelto de siempre.
    """
    scripts = {"firmas": REVISOR_FIRMAS, "horario": GENERADOR_HORARIO,
               "asignar": os.path.join(WEBCLASS, "webclass_tareas.py"),
               "subir": os.path.join(WEBCLASS, "subir_carpeta.py"),
               "libro": os.path.join(WEBCLASS, "webclass_libro.py"),
               "observar": os.path.join(WEBCLASS, "webclass_observaciones.py"),
               "planificar": os.path.join(WEBCLASS, "webclass_planificacion.py"),
               "correo": os.path.join(WEBCLASS, "correo_pie.py")}
    # Siempre con el docente activo: en la sala de profesores hay varios.
    perfil = ["--perfil", PERFIL] if PERFIL else []
    for base in (CARPETA, WEBCLASS):
        exe = os.path.join(base, "webclass.exe")
        if os.path.isfile(exe):
            return [exe, subcomando, *opciones, *perfil]
    piton = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if getattr(sys, "frozen", False) or not os.path.isfile(piton):
        piton = "pythonw.exe"       # último recurso: que lo resuelva el PATH
    return [piton, scripts[subcomando], *opciones, *perfil]


BUZON = os.path.join(CASA, "Documents", "Subir a Webclass")

MARCA_AGUA = "Anotar… (Enter)"
# Lista de verificación: vive solo en este archivo, sin internet ni asistente.
TAREAS = rutas.dato(f"lista_tareas{_sufijo}.json")
# Último resultado de cada botón (para mostrar "hoy 14:32 · completado").
EJECUCIONES = rutas.dato(f"ultimas_ejecuciones{_sufijo}.json")
# Si este docente ya vio el recorrido de bienvenida.
TOUR = rutas.dato(f"tour{_sufijo}.json")
MARCA_TAREA = "Agregar a la lista… (Enter)"
PUERTO = 50573        # puerto local: instancia única y atajo de teclado
VERSION_CODIGO = version_del_codigo(CARPETA)      # qué tan nuevo es el programa que corre
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# Paletas. La primera es la de siempre (morados oscuros y blancos); el botón
# «Cambiar color» de la barra rota entre estas y recuerda la elegida.
PALETAS = {
    "morado": {"nombre": "Morado", "fondo": "#17122a", "boton": "#241c3d",
               "hover": "#3b2d66", "pulsado": "#513c8c", "acento": "#a78bfa",
               "texto": "#ffffff", "tenue": "#b3a8d6", "lengueta": "#7c5cff"},
    "azul": {"nombre": "Azul noche", "fondo": "#0f1829", "boton": "#1b2740",
             "hover": "#2a3c63", "pulsado": "#3a5288", "acento": "#7cb3ff",
             "texto": "#ffffff", "tenue": "#a3b8d9", "lengueta": "#4a8cff"},
    "verde": {"nombre": "Verde pizarra", "fondo": "#10211c", "boton": "#1a3129",
              "hover": "#27493d", "pulsado": "#336152", "acento": "#6ee7b7",
              "texto": "#ffffff", "tenue": "#a4cdbd", "lengueta": "#34d399"},
    "vino": {"nombre": "Vino", "fondo": "#231016", "boton": "#391a23",
             "hover": "#5a2936", "pulsado": "#7a3646", "acento": "#fb9eb5",
             "texto": "#ffffff", "tenue": "#d9aeb8", "lengueta": "#e35d7d"},
    "grafito": {"nombre": "Grafito", "fondo": "#16181d", "boton": "#23262e",
                "hover": "#343843", "pulsado": "#464b59", "acento": "#cbd5e1",
                "texto": "#ffffff", "tenue": "#a7aebb", "lengueta": "#94a3b8"},
}


def paleta_guardada() -> str:
    try:
        with open(TEMA, encoding="utf-8-sig") as f:
            clave = json.load(f).get("paleta", "")
        if clave in PALETAS:
            return clave
    except (OSError, ValueError):
        pass
    return "morado"


def aplicar_paleta(clave: str) -> None:
    """Deja los COLOR_* en los de esa paleta. Se usa al abrir y al cambiarla."""
    p = PALETAS.get(clave, PALETAS["morado"])
    g = globals()
    g["PALETA"] = clave
    g["COLOR_FONDO"] = p["fondo"]
    g["COLOR_BOTON"] = p["boton"]
    g["COLOR_HOVER"] = p["hover"]
    g["COLOR_PULSADO"] = p["pulsado"]
    g["COLOR_ACENTO"] = p["acento"]
    g["COLOR_TEXTO"] = p["texto"]
    g["COLOR_TENUE"] = p["tenue"]
    g["COLOR_LENGUETA"] = p["lengueta"]


PALETA = "morado"
COLOR_SUAVE = "#7f74a8"      # detalles discretos pero visibles (la ✕ de la lista)
COLOR_ALERTA_SUAVE = "#f0c775"   # advertencias que no son error
COLOR_ERROR = "#ff8b9a"
COLOR_ALERTA = "#e0455f"     # lengüeta cuando quedan bloques sin firmar
aplicar_paleta(paleta_guardada())

def ajustar_escalado() -> None:
    """Le dice a Windows que la ventana maneja su propio escalado.

    Sin esto, con la pantalla al 125% o 150% Windows estira la imagen y el
    texto se ve borroso.

    Va ANTES de abrir cualquier ventana, incluida la de prueba con la que se
    comprueba tkdnd: Windows fija el escalado del proceso con la primera
    ventana y después ya no acepta cambiarlo. Cuando pasó eso, la barra se
    calculaba en coordenadas lógicas y terminaba a media pantalla en vez de
    pegada al borde.
    """
    for intento in (lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),
                    lambda: ctypes.windll.user32.SetProcessDPIAware()):
        try:
            intento()
            return
        except (AttributeError, OSError):
            continue


ajustar_escalado()


def _soltar_disponible():
    """(DND_FILES, clase de ventana) si se puede arrastrar archivos a la barra.

    No basta con que tkinterdnd2 se importe: el paquete de Python puede estar
    y faltarle igual su biblioteca tkdnd, y entonces revienta recién al abrir
    la ventana ("unable to load tkdnd library"). Se abre una de prueba, oculta,
    para enterarse acá y no quedarse sin barra.
    """
    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
    except Exception:        # noqa: BLE001
        return None, None
    # Al encender el PC la barra parte antes de que Windows termine de
    # acomodarse y la biblioteca a veces no alcanza a cargar: se reintenta.
    ultimo: Exception | None = None
    for espera in (0, 1, 2):
        if espera:
            time.sleep(espera)
        try:
            prueba = TkinterDnD.Tk()
            prueba.withdraw()
            prueba.destroy()
            return DND_FILES, TkinterDnD.Tk
        except Exception as exc:  # noqa: BLE001
            ultimo = exc
    # registrar() todavía no existe acá: el motivo se anota al abrir la barra.
    globals()["MOTIVO_SIN_SOLTAR"] = str(ultimo)
    return None, None


# Arrastrar y soltar archivos sobre la barra. Si no se puede, la barra
# funciona igual: lo único que se pierde es soltarle archivos encima.
MOTIVO_SIN_SOLTAR = ""
DND_FILES, _RAIZ_CON_SOLTAR = _soltar_disponible()
RAIZ_TK = _RAIZ_CON_SOLTAR or tk.Tk

ANCHO = 210          # ancho de la barra desplegada (a escala 100%)
LENGUETA = 10        # ancho de la lengüeta cuando está plegada
ALTO_LENGUETA = 150
MARGEN = 60          # cuánto más allá del borde se considera "el mouse encima"

# Cada cuánto vigila la barra cada cosa (milisegundos) y otros tiempos.
MS_VIGILAR_MOUSE = 200            # ¿sigue el mouse encima?
CICLOS_FUERA_PARA_PLEGAR = 4      # ~0,8 s fuera antes de plegarse
MS_AL_FRENTE = 4_000              # reafirmar «siempre encima»
MS_VIGILAR_CONFIG = 2_000         # ¿cambió herramientas.json?
MS_VIGILAR_AGENDA = 60_000        # refrescar «Ahora / Luego»
MS_VIGILAR_LIBRO = 120_000        # ¿hay que revisar el libro de clases?
MINUTOS_VALIDEZ_LIBRO = 20        # cuánto vale una revisión del libro
SEGUNDOS_TOPE_REVISION = 300      # una revisión que pasa de esto se cancela


# --------------------------------------------------------------------- registro
def registrar(mensaje: str, detalle: str = "") -> None:
    """Deja una línea en barra_profe.log.

    Sin consola, un error se pierde sin dejar rastro; aquí queda. El archivo
    se recorta solo cuando pasa de ~200 KB.
    """
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 200_000:
            with open(LOG, encoding="utf-8", errors="replace") as f:
                cola = f.readlines()[-400:]
            with open(LOG, "w", encoding="utf-8") as f:
                f.writelines(cola)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {mensaje}\n")
            for linea in detalle.strip().splitlines():
                f.write(f"    {linea}\n")
    except OSError:
        pass      # si ni siquiera se puede registrar, no vale la pena insistir


# ---------------------------------------------------------------------- bandeja
def anotar(texto: str) -> None:
    """Agrega una nota a la bandeja del asistente."""
    nota = {"id": datetime.datetime.now().isoformat(timespec="seconds"),
            "texto": texto, "estado": "pendiente", "origen": "barra"}
    os.makedirs(os.path.dirname(BANDEJA), exist_ok=True)
    linea = json.dumps(nota, ensure_ascii=False) + "\n"
    # Si la última línea quedó sin salto (corte a medias), la nota nueva no
    # debe pegarse a ella. Todo va en un solo write para que sea indivisible.
    try:
        with open(BANDEJA, "rb") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() and (f.seek(-1, os.SEEK_END), f.read(1))[1] != b"\n":
                linea = "\n" + linea
    except OSError:
        pass
    with open(BANDEJA, "a", encoding="utf-8", newline="") as f:
        f.write(linea)
        f.flush()
        os.fsync(f.fileno())


def pendientes() -> int:
    """Cuántas notas siguen esperando a que el asistente las procese."""
    total = 0
    try:
        with open(BANDEJA, encoding="utf-8") as f:
            for linea in f:
                try:
                    if json.loads(linea).get("estado") == "pendiente":
                        total += 1
                except ValueError:      # línea a medio escribir: se ignora
                    continue
    except OSError:
        return 0
    return total


# ---------------------------------------------------------------------- agenda
def agenda_de_hoy(ahora: datetime.datetime | None = None) -> list[dict]:
    """Bloques de hoy: el horario semanal más lo que agregue el asistente.

    Devuelve lista vacía si hoy no hay clases (fin de semana, feriado o fuera
    del año escolar).
    """
    ahora = ahora or datetime.datetime.now()
    hoy = ahora.date().isoformat()
    bloques: list[dict] = []
    try:
        with open(HORARIO, encoding="utf-8") as f:
            horario = json.load(f)
    except (OSError, ValueError):
        horario = {}
    vigencia = horario.get("vigencia", {})
    en_el_ano = vigencia.get("desde", "0000-00-00") <= hoy <= vigencia.get("hasta", "9999-99-99")
    if en_el_ano and hoy not in horario.get("excepciones", []):
        bloques += horario.get("dias", {}).get(DIAS[ahora.weekday()], [])
    try:
        with open(AGENDA_HOY, encoding="utf-8") as f:
            extra = json.load(f)
        if extra.get("fecha") == hoy:
            bloques += extra.get("bloques", [])
    except (OSError, ValueError):
        pass
    try:
        return sorted(bloques, key=lambda b: minutos(b.get("inicio", "23:59")))
    except (AttributeError, ValueError):
        registrar("horario_semanal.json tiene horas mal escritas")
        return []


# ------------------------------------------------------- instancia única / DPI
def avisar_a_la_barra_abierta(version: int | None = None) -> bool:
    """Si ya hay una barra corriendo, le pide desplegarse y devuelve True.

    Le cuenta qué tan nuevo es el programa de quien llama: si es más nuevo que el
    de la barra abierta, esa se reinicia sola (si no, quedaba corriendo el programa
    viejo y los botones nuevos no funcionaban hasta cerrarla a mano).
    """
    version = VERSION_CODIGO if version is None else version
    try:
        with socket.create_connection(("127.0.0.1", PUERTO), timeout=0.5) as enlace:
            enlace.sendall(f"anotar {version}".encode())
        return True
    except OSError:
        return False



# Nombre de pila del docente activo, para saludarlo.
NOMBRE = NOMBRE_COMPLETO.split(" ")[0] if NOMBRE_COMPLETO else ""


def saludo(ahora: datetime.datetime | None = None) -> str:
    """Buenos días / tardes / noches, según la hora, con el nombre del docente."""
    return saludo_para(NOMBRE, ahora)


def sonar_al_abrir() -> None:
    """Suena el archivo «inicio» de personal\\, si el docente dejó uno.

    Admite .mp3 y .wav. Se usa MCI, que viene en Windows, para no obligar a
    instalar nada. Suena aparte para no demorar la apertura de la barra, y si
    algo falla la barra abre igual: es un adorno, no una función.
    """
    archivo = next((a for a in SONIDO if os.path.isfile(a)), None)
    if not archivo:
        return

    def reproducir() -> None:
        try:
            mci = ctypes.windll.winmm.mciSendStringW
            # El alias evita problemas con las rutas largas o con espacios.
            if mci(f'open "{archivo}" type mpegvideo alias barraprofe', None, 0, None):
                registrar(f"no se pudo abrir el sonido de inicio: {archivo}")
                return
            # Se espera lo que dure el archivo: con un tiempo fijo, una canción
            # larga se cortaba de golpe a la mitad.
            respuesta = ctypes.create_unicode_buffer(256)
            mci("status barraprofe length", respuesta, 256, None)
            try:
                segundos = int(respuesta.value) / 1000
            except (TypeError, ValueError):
                segundos = 60
            mci("play barraprofe", None, 0, None)
            time.sleep(min(segundos + 1, TOPE_SONIDO))
            mci("close barraprofe", None, 0, None)
        except Exception as exc:                # noqa: BLE001
            registrar("no se pudo reproducir el sonido de inicio", str(exc))

    threading.Thread(target=reproducir, daemon=True).start()


def abrir_en_consola(titulo: str, orden: list[str]) -> None:
    """Abre la herramienta en una consola donde el docente pueda responder.

    Se escribe un .bat y se abre ese, en vez de armar una línea para
    «cmd /k»: las carpetas llevan espacios («Webclass para docentes») y ahí
    las comillas se enredan y cmd parte la ruta en pedazos.

    Y va con python.exe, no con pythonw.exe: pythonw no tiene consola, así que
    la ventana aparecía vacía y no se podía escribir nada.
    """
    con_consola = list(orden)
    if con_consola and con_consola[0].lower().endswith("pythonw.exe"):
        normal = con_consola[0][:-len("pythonw.exe")] + "python.exe"
        if os.path.isfile(normal):
            con_consola[0] = normal

    lanzador = rutas.dato("abrir_consola.bat")
    with open(lanzador, "w", encoding="ascii", errors="replace", newline="\r\n") as f:
        f.write("@echo off\r\n"
                f"title {''.join(c for c in titulo if c.isalnum() or c == ' ')}\r\n"
                "chcp 65001 >nul\r\n"
                "set PYTHONIOENCODING=utf-8\r\n"
                f'cd /d "{WEBCLASS}"\r\n'
                + " ".join(f'"{a}"' if " " in a else a for a in con_consola) + "\r\n"
                "echo.\r\n"
                "pause\r\n")
    os.startfile(lanzador)


def reabrir_barra() -> None:
    """Cierra esta barra y abre una nueva.

    Cambiar de docente o de color toca cosas que ya están dibujadas (los
    colores de cada widget, el saludo, los archivos de cada profe): rehacer la
    ventana entera es más simple y más seguro que ir repintando a mano.
    """
    if getattr(sys, "frozen", False):
        orden = [sys.executable]
    else:
        piton = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        orden = [piton if os.path.isfile(piton) else sys.executable,
                 os.path.abspath(__file__)]
    # Cambiar de color o de profesor reabre la barra: la musiquita es para
    # cuando parte el PC, no para cada vez que se toca un botón.
    orden.append("--sin-sonido")
    try:
        subprocess.Popen(orden, cwd=CARPETA,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    except Exception as exc:  # noqa: BLE001
        registrar("no se pudo reabrir la barra", str(exc))
        messagebox.showerror("Barra Profe",
                             f"No pude reabrir la barra sola.\nÁbrela a mano.\n\n{exc}")
        return
    os._exit(0)          # sin esperar al mainloop: el puerto queda libre al tiro


def guardar_color(clave: str) -> None:
    """Deja elegida esa paleta y reabre la barra con ella."""
    if clave == PALETA:
        return
    try:
        escribir_atomico(TEMA, json.dumps({"paleta": clave}))
    except OSError as exc:
        registrar("no se pudo guardar el color", str(exc))
        return
    registrar(f"color cambiado a {PALETAS[clave]['nombre']}")
    reabrir_barra()


def cambiar_color(maestra: tk.Misc | None = None) -> None:
    """Abre la paleta para elegir el color, en vez de ir rotando a ciegas."""
    VentanaColores(maestra)


def cambiar_docente(maestra: tk.Misc | None = None) -> None:
    """Elige entre los docentes registrados en este PC y reabre la barra."""
    if len(DOCENTES) < 2:
        messagebox.showinfo(
            "Barra Profe",
            "En este equipo hay un solo docente registrado.\n\n"
            "Para agregar otro, abre una ventana de comandos en la carpeta "
            "de la herramienta y escribe:\n\n    python configurar.py")
        return
    VentanaDocentes(maestra)


def ruta_util(destino: str) -> str:
    """Resuelve el destino de un botón.

    Además de las variables de Windows (%USERPROFILE%), entiende atajos
    propios para que el mismo herramientas.json sirva en cualquier PC:
    %BARRA%, %WEBCLASS%, %BUZON%, %DATOS%, %PERSONAL% y %RAIZ%, más
    %REGISTRO_LIBRO% y %REGISTRO_TAREAS%: los CSV del docente activo (cada
    docente tiene los suyos, así no se ven las filas de otro en un PC compartido).
    """
    return reemplazar_variables(destino, {
        "%BARRA%": CARPETA, "%WEBCLASS%": WEBCLASS, "%BUZON%": BUZON,
        "%DATOS%": rutas.DATOS, "%PERSONAL%": rutas.PERSONAL, "%RAIZ%": rutas.RAIZ,
        "%REGISTRO_LIBRO%": rutas.registro("registro_libro", PERFIL),
        "%REGISTRO_TAREAS%": rutas.registro("registro_asignaciones", PERFIL)})


def abrir_asistente_ia(lanzador: str) -> None:
    """Abre el asistente de IA para planificar (el lanzador inicia su servidor si hace falta y abre el navegador)."""
    # El mismo Python con que corre la barra (ahí se instalaron los complementos); empaquetada, el que haya en el PATH.
    python = (shutil.which("pythonw") or shutil.which("python") or sys.executable) if getattr(sys, "frozen", False) \
        else sys.executable
    try:
        subprocess.Popen([python, lanzador, "planificar"], cwd=os.path.dirname(lanzador),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        messagebox.showerror("Barra Profe", f"No se pudo abrir el asistente.\n\n{lanzador}\n\n{exc}")


def abrir(herramienta: dict, maestra: tk.Misc | None = None) -> None:
    """Ejecuta un .bat, abre una carpeta, un archivo o una URL."""
    tipo = herramienta.get("tipo", "programa")
    destino = ruta_util(herramienta.get("destino", ""))
    nombre = herramienta.get("nombre", "(sin nombre)")
    icono = herramienta.get("icono", "")
    # Si ese botón ya está corriendo, se trae su ventana al frente en vez de
    # lanzar la misma tarea dos veces.
    en_curso = getattr(maestra, "corriendo", {}).get(nombre)
    if en_curso is not None and tipo in ("consola", "webclass", "webclass-confirmar"):
        try:
            en_curso.deiconify()
            en_curso.lift()
            return
        except tk.TclError:
            pass
    # Antes de escribir en Webclass se muestra qué se va a hacer (vista previa).
    if (herramienta.get("vista_previa") and not herramienta.get("_confirmado")
            and tipo in ("consola", "webclass", "webclass-confirmar")):
        VistaPrevia(maestra, herramienta,
                    lambda claves, todas: abrir({**herramienta, "_confirmado": True,
                                                 "_seleccion": (claves, todas)}, maestra))
        return
    # Lo que el docente dejó marcado en la vista previa (nada si marcó todo).
    claves, todas = herramienta.get("_seleccion") or (None, [])
    extra = argumentos_de_seleccion(claves, todas, rutas.dato("selecciones")) if claves else []
    try:
        if tipo == "url":
            webbrowser.open(destino)
        elif tipo == "consola":
            # En vez de la ventana negra de cmd, una ventanita propia que va
            # mostrando lo que el script escribe.
            if not os.path.isfile(destino):
                raise FileNotFoundError(f"No existe el archivo: {destino}")
            Consola(maestra, nombre, ["cmd", "/c", destino],
                    os.path.dirname(os.path.abspath(destino)), icono)
        elif tipo == "webclass":
            # Una herramienta de Webclass por su subcomando: sirve igual con el
            # .exe empaquetado o con los scripts sueltos.
            Consola(maestra, nombre, comando_webclass(*partes_de_comando(destino), *extra),
                    WEBCLASS, icono)
        elif tipo == "webclass-confirmar":
            # Igual que el anterior, pero preguntando antes. Solo para lo que
            # escribe mucho de una vez, como asignar dos meses de clases.
            aviso = herramienta.get("confirmar") or (
                f"¿Ejecutar «{nombre}»?\n\nVa a escribir en Webclass.")
            if not herramienta.get("_confirmado") and not messagebox.askyesno(
                    "Barra Profe", aviso, icon="question", default="no", parent=maestra):
                registrar(f"«{nombre}»: cancelado por el usuario")
                return
            Consola(maestra, nombre, comando_webclass(*partes_de_comando(destino), *extra),
                    WEBCLASS, icono)
        elif tipo == "preguntar":
            # Para lo que pide elegir algo escribiendo: la ventanita de la
            # barra solo muestra texto, así que esto va en una consola de
            # verdad, donde se puede responder.
            VentanaPreguntar(maestra, nombre, herramienta)
        elif tipo == "destinos":
            VentanaDestinos(maestra)
        elif tipo == "libro-atras":
            VentanaPeriodo(maestra, herramienta)
        elif tipo == "observacion":
            VentanaObservacion(maestra, herramienta)
        elif tipo == "planificar":
            # Si el botón trae en «destino» el lanzador del asistente de IA, se abre directo; si no, la ventana de siempre.
            if destino.strip() and os.path.isfile(destino):
                abrir_asistente_ia(destino)
            else:
                VentanaPlanificar(maestra, herramienta)
        elif tipo == "correo":
            VentanaCorreo(maestra, herramienta)
        elif tipo == "mensajes":
            maestra.abrir_mensajes()
        elif tipo == "periodos":
            VentanaTickets(maestra, herramienta)
        elif tipo == "horario":
            VentanaHorario(maestra)
        elif tipo == "color":
            cambiar_color(maestra)
        elif tipo == "perfil":
            cambiar_docente(maestra)
        elif not destino.strip():
            # Un botón sin destino casi siempre es uno NUEVO que esta barra (abierta
            # antes de actualizar el programa) todavía no sabe usar: antes abría la
            # carpeta de la barra, que no es lo que se quería.
            messagebox.showinfo(
                "Barra Profe",
                f"«{nombre}» es un botón que esta barra todavía no conoce.\n\n"
                "Ciérrala con la ✕ y ábrela de nuevo para que tome la versión nueva.",
                parent=maestra)
            registrar(f"«{nombre}»: tipo «{tipo}» sin destino; hay que reabrir la barra")
            return
        else:
            os.startfile(destino)
        registrar(f"abrir «{nombre}» ({tipo})")
    except Exception as exc:  # noqa: BLE001
        registrar(f"no se pudo abrir «{nombre}»: {destino}", traceback.format_exc())
        messagebox.showerror("Barra Profe",
                             f"No se pudo abrir «{nombre}».\n\n"
                             f"{destino}\n\n{exc}")


def color_de_estado(estado: str) -> str:
    """Color de cada estado de una actividad, según la paleta activa."""
    return {"proceso": COLOR_ACENTO, "completado": "#6fd18c", "avisos": "#f0c775",
            "error": COLOR_ERROR, "cancelado": COLOR_TENUE}.get(estado, COLOR_TENUE)


GIRO = "◐◓◑◒"       # cuadros del indicador "en proceso"


def cuadro_de_giro() -> str:
    return GIRO[int(time.time() * 6) % len(GIRO)]


class Consola(tk.Toplevel):
    """Ventana de actividad: corre una herramienta y cuenta cómo va.

    Muestra el estado (en proceso, completado, con avisos, con error), una barra
    de carga, un resumen en lenguaje simple y, plegado, el detalle técnico.
    Le avisa a la barra (`maestra`) cuando empieza, avanza y termina, para que
    el botón y la lengüeta reflejen el estado aunque esta ventana se cierre.
    """

    ANCHO_VENTANA = 560
    ALTO_COMPACTO = 290
    ALTO_RESULTADO = 600
    ALTO_DETALLE = 500

    def __init__(self, maestra, titulo: str, comando: list[str],
                 carpeta: str | None = None, icono: str = ""):
        super().__init__(maestra)
        self.title(titulo)
        self.configure(bg=COLOR_FONDO)
        self.geometry(f"{self.ANCHO_VENTANA}x{self.ALTO_COMPACTO}")
        self.minsize(440, 230)
        self.attributes("-topmost", True)
        self.maestra = maestra
        self.comando = comando
        self.carpeta = carpeta or None
        self.titulo = titulo
        self.icono = icono
        self.ultimas: list[str] = []      # para el registro, si termina mal
        self.lineas: list[str] = []       # todo lo que escribió (sin las de progreso)
        self.cola: queue.Queue = queue.Queue()
        self.proceso: subprocess.Popen | None = None
        self._cerrada = False
        self._cancelada = False
        self._notificada = False
        self.estado_actual = "proceso"
        self.progreso: tuple[int, int, str] | None = None
        self.resultado: dict | None = None
        self.items: list[dict] = []        # lo que la herramienta informó (##ITEM)
        self.firmas: list[str] = []        # bloques que esperan la firma del docente
        self._leyendo_firmas = False
        self.inicio = time.time()
        self.duracion = 0.0
        self.detalle_visible = False

        fuente = tkfont.Font(family="Segoe UI", size=10)
        familia = fuente.cget("family")

        # El pie se empaqueta primero: así los botones siempre tienen su lugar,
        # por poco alto que tenga la ventana.
        self.pie = tk.Frame(self, bg=COLOR_FONDO)
        self.pie.pack(side="bottom", fill="x", padx=16, pady=(4, 14))

        cabecera = tk.Frame(self, bg=COLOR_FONDO)
        cabecera.pack(fill="x", padx=16, pady=(14, 6))
        if icono:
            tk.Label(cabecera, text=icono, bg=COLOR_FONDO, fg=COLOR_TEXTO,
                     font=("Segoe UI Emoji", 16)).pack(side="left", padx=(0, 8))
        tk.Label(cabecera, text=titulo, bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=(familia, 13, "bold")).pack(side="left")
        self.chip = tk.Label(cabecera, text="", bg=COLOR_BOTON, fg=COLOR_ACENTO,
                             font=(familia, 9, "bold"), padx=10, pady=3)
        self.chip.pack(side="right")

        self.barra_carga = tk.Canvas(self, height=10, bg=COLOR_BOTON, bd=0,
                                     highlightthickness=0)
        self.barra_carga.pack(fill="x", padx=16, pady=(2, 6))

        self.linea_estado = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_TENUE,
                                     font=(familia, 9), anchor="w", justify="left")
        self.linea_estado.pack(fill="x", padx=16)
        self.resumen = tk.Label(self, text="Empezando…", bg=COLOR_FONDO, fg=COLOR_TEXTO,
                                font=(familia, 11, "bold"), anchor="w", justify="left",
                                wraplength=self.ANCHO_VENTANA - 40)
        self.resumen.pack(fill="x", padx=16, pady=(4, 0))
        self.pista = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_TENUE,
                              font=(familia, 9), anchor="w", justify="left",
                              wraplength=self.ANCHO_VENTANA - 40)
        self.pista.pack(fill="x", padx=16, pady=(2, 0))

        # Resultado en bloques (intenté / hice / no pude / omitido / firmar): solo
        # aparece si la herramienta informó ítems.
        self.marco_resultado = tk.Frame(self, bg=COLOR_BOTON)
        self.texto_resultado = tk.Text(self.marco_resultado, bg=COLOR_BOTON, fg=COLOR_TEXTO, bd=0,
                                       font=(familia, 10), wrap="word", padx=12, pady=8,
                                       height=11, cursor="arrow", state="disabled",
                                       highlightthickness=0)
        scroll_res = tk.Scrollbar(self.marco_resultado, command=self.texto_resultado.yview)
        self.texto_resultado.configure(yscrollcommand=scroll_res.set)
        scroll_res.pack(side="right", fill="y")
        self.texto_resultado.pack(side="left", fill="both", expand=True)
        for etiqueta, opciones in {
                "resumen": {"foreground": COLOR_TEXTO, "font": (familia, 11, "bold"),
                            "spacing3": 6},
                "titulo_ok": {"foreground": "#6fd18c", "font": (familia, 10, "bold"),
                              "spacing1": 8},
                "titulo_aviso": {"foreground": "#f0c775", "font": (familia, 10, "bold"),
                                 "spacing1": 8},
                "titulo_gris": {"foreground": COLOR_TENUE, "font": (familia, 10, "bold"),
                                "spacing1": 8},
                "item": {"foreground": COLOR_TEXTO, "lmargin1": 14, "lmargin2": 14},
                "detalle": {"foreground": COLOR_TENUE, "lmargin1": 28, "lmargin2": 28},
                "hacer": {"foreground": "#f0c775", "lmargin1": 28, "lmargin2": 28},
                "vacio": {"foreground": COLOR_TENUE}}.items():
            self.texto_resultado.tag_configure(etiqueta, **opciones)

        self.alternador = tk.Label(self, text="▸ Ver detalles", bg=COLOR_FONDO,
                                   fg=COLOR_ACENTO, font=(familia, 9), cursor="hand2",
                                   anchor="w", takefocus=True)
        self.alternador.pack(fill="x", padx=16, pady=(8, 2))
        self.alternador.bind("<Button-1>", lambda _e: self._alternar_detalle())
        for tecla in ("<Return>", "<space>"):
            self.alternador.bind(tecla, lambda _e: self._alternar_detalle())

        self.marco_detalle = tk.Frame(self, bg=COLOR_BOTON)
        self.texto = tk.Text(self.marco_detalle, bg="#120e1f", fg="#e9e4ff", bd=0,
                             font=("Consolas", 9), wrap="word", padx=10, pady=8,
                             insertbackground="#e9e4ff")
        scroll = tk.Scrollbar(self.marco_detalle, command=self.texto.yview)
        self.texto.configure(yscrollcommand=scroll.set, state="disabled")
        scroll.pack(side="right", fill="y")
        self.texto.pack(side="left", fill="both", expand=True)
        self.texto.tag_configure("ok", foreground="#86e6a8")
        self.texto.tag_configure("aviso", foreground="#f0c775")
        self.texto.tag_configure("error", foreground=COLOR_ERROR)

        self.botones: dict[str, tk.Label] = {}
        self._fuente_boton = fuente
        self._armar_pie()

        self.bind("<Escape>", lambda _e: self.destroy())
        aviso = getattr(maestra, "actividad_inicio", None)
        if aviso:
            aviso(self)
        threading.Thread(target=self._correr, daemon=True).start()
        self.after(60, self._tick)

    # --------------------------------------------------------------- interfaz
    def _boton(self, clave: str, texto: str, accion, principal: bool = False) -> tk.Label:
        b = tk.Label(self.pie, text=f"  {texto}  ", font=self._fuente_boton, cursor="hand2",
                     bg=COLOR_ACENTO if principal else COLOR_BOTON,
                     fg=COLOR_FONDO if principal else COLOR_TEXTO, pady=5, takefocus=True,
                     highlightthickness=1, highlightbackground=COLOR_BOTON,
                     highlightcolor=COLOR_ACENTO)
        normal = COLOR_ACENTO if principal else COLOR_BOTON
        b.bind("<Button-1>", lambda _e: accion())
        for tecla in ("<Return>", "<space>"):
            b.bind(tecla, lambda _e: accion())
        b.bind("<Enter>", lambda _e: b.configure(bg=COLOR_HOVER if not principal else COLOR_TEXTO))
        b.bind("<Leave>", lambda _e: b.configure(bg=normal))
        self.botones[clave] = b
        return b

    def _armar_pie(self) -> None:
        """Los botones cambian según el estado: Cancelar mientras corre, etc."""
        for b in self.botones.values():
            b.destroy()
        self.botones.clear()
        corriendo = self.estado_actual == "proceso"
        orden: list[tuple[str, str, object, bool]] = []
        if corriendo:
            orden.append(("cancelar", "Cancelar", self._cancelar, False))
        else:
            if self._hay_clases_por_elegir():
                orden.append(("elegir", "Elegir clase…", self._elegir_clase, True))
            if self.estado_actual in ("error", "cancelado"):
                orden.append(("reintentar", "Reintentar", self._reintentar, True))
            resaltar_cerrar = (self.estado_actual != "error" and not self._hay_clases_por_elegir())
            orden.append(("cerrar", "Cerrar", self.destroy, resaltar_cerrar))
        orden.append(("registro", "Abrir registro", self._abrir_registro, False))
        orden.append(("copiar", "Copiar detalle", self._copiar_detalle, False))
        for clave, texto, accion, principal in reversed(orden):
            self._boton(clave, texto, accion, principal).pack(side="right", padx=(6, 0))

    def _alternar_detalle(self, mostrar: bool | None = None) -> None:
        self.detalle_visible = (not self.detalle_visible) if mostrar is None else mostrar
        if self.detalle_visible:
            self.marco_detalle.pack(fill="both", expand=True, padx=16, pady=(0, 4),
                                    after=self.alternador)
            self.alternador.configure(text="▾ Ocultar detalles")
            con_resultado = self.marco_resultado.winfo_ismapped()
            alto = self.ALTO_DETALLE + (240 if con_resultado else 0)
            self.geometry(f"{self.winfo_width()}x{max(self.winfo_height(), self._acotar(alto))}")
        else:
            self.marco_detalle.pack_forget()
            self.alternador.configure(text="▸ Ver detalles")
            alto = (self.ALTO_RESULTADO if self.marco_resultado.winfo_ismapped()
                    else self.ALTO_COMPACTO)
            self.geometry(f"{self.winfo_width()}x{self._acotar(alto)}")

    def _acotar(self, alto: int) -> int:
        """Que la ventana no sea más alta que la pantalla (en notebooks de 720 px sobra poco)."""
        return max(300, min(alto, self.winfo_screenheight() - 90))

    def _dibujar_barra(self) -> None:
        c = self.barra_carga
        c.delete("all")
        ancho, alto = max(c.winfo_width(), 2), int(c.cget("height"))
        color = color_de_estado(self.estado_actual)
        if self.estado_actual != "proceso":
            c.create_rectangle(0, 0, ancho, alto, fill=color, outline="")
        elif self.progreso:
            hecho, total, _ = self.progreso
            c.create_rectangle(0, 0, int(ancho * hecho / total), alto, fill=color, outline="")
        else:
            largo = max(ancho // 4, 20)
            x = int(((time.time() * 0.8) % 1) * (ancho + largo)) - largo
            c.create_rectangle(max(x, 0), 0, min(x + largo, ancho), alto, fill=color, outline="")

    def _pintar_estado(self) -> None:
        datos = ESTADOS[self.estado_actual]
        icono = cuadro_de_giro() if self.estado_actual == "proceso" else datos["icono"]
        self.chip.configure(text=f"{icono}  {datos['texto']}",
                            fg=color_de_estado(self.estado_actual))

    # ---------------------------------------------------------------- proceso
    def destroy(self) -> None:
        """Al cerrar la ventana se detiene también el script que corría."""
        self._cerrada = True
        if self.estado_actual == "proceso":
            self._cancelada = True
        self._matar()
        if self.estado_actual == "proceso":
            self._terminar(None)
        super().destroy()

    def _matar(self) -> None:
        if self.proceso is not None and self.proceso.poll() is None:
            registrar(f"«{self.titulo}» detenido")
        matar_proceso(self.proceso)

    def _cancelar(self) -> None:
        self._cancelada = True
        self.resumen.configure(text="Deteniendo…")
        threading.Thread(target=self._matar, daemon=True).start()

    def _hay_clases_por_elegir(self) -> bool:
        return any(it.get("opciones") for it in agrupar_items(self.items)["no_pude"])

    def _elegir_clase(self) -> None:
        VentanaElegirClase(self)

    def _reintentar(self) -> None:
        maestra, titulo, comando = self.maestra, self.titulo, self.comando
        carpeta, icono = self.carpeta, self.icono
        self.destroy()
        Consola(maestra, titulo, comando, carpeta, icono)

    def _abrir_registro(self) -> None:
        try:
            os.startfile(LOG)
        except OSError as exc:
            self.pista.configure(text=f"No se pudo abrir el registro: {exc}")

    def _copiar_detalle(self) -> None:
        texto = (f"{self.titulo} · {ESTADOS[self.estado_actual]['texto']}\n"
                 f"{self.resumen.cget('text')}\n\n" + "\n".join(self.lineas))
        try:
            self.clipboard_clear()
            self.clipboard_append(texto)
            self.pista.configure(text="Detalle copiado: puedes pegarlo en un mensaje.")
        except tk.TclError:
            pass

    def _correr(self) -> None:
        codigo: int | None = None
        try:
            proceso = subprocess.Popen(
                self.comando, cwd=self.carpeta,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace",
                # Sin esto Python guarda lo que imprime en un búfer y el avance
                # llegaría a pedazos grandes, no línea a línea.
                env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.proceso = proceso
            if self._cerrada:       # se cerró la ventana mientras arrancaba
                proceso.kill()
                return
            for linea in proceso.stdout:
                # El .bat termina con "pause": aquí no hace falta, se ignora.
                if "Presione una tecla" in linea or "Press any key" in linea:
                    continue
                linea = linea.rstrip("\n")
                self.ultimas = (self.ultimas + [linea])[-20:]
                self.cola.put(linea)
            proceso.wait()
            codigo = proceso.returncode
            if codigo and not self._cerrada and not self._cancelada:
                registrar(f"«{self.titulo}» terminó con error (código {codigo})",
                          "\n".join(self.ultimas))
        except Exception as exc:  # noqa: BLE001
            registrar(f"no se pudo ejecutar «{self.titulo}»: {' '.join(self.comando)}",
                      traceback.format_exc())
            self.cola.put(f"[ERROR] No se pudo ejecutar: {exc}")
            codigo = -1
        self.cola.put(("fin", codigo))

    def _tick(self) -> None:
        """Cada instante: pasa lo nuevo a la pantalla y anima la barra."""
        try:
            while True:
                elemento = self.cola.get_nowait()
                if isinstance(elemento, tuple):
                    self._terminar(elemento[1])
                    break
                self._recibir(elemento)
        except queue.Empty:
            pass
        except tk.TclError:
            return
        try:
            if self.estado_actual == "proceso":
                transcurrido = formatear_duracion(time.time() - self.inicio)
                texto = f"En proceso · {transcurrido}"
                if self.progreso:
                    hecho, total, que = self.progreso
                    texto = f"Paso {hecho} de {total}" + (f" · {que}" if que else "") \
                            + f" · {transcurrido}"
                self.linea_estado.configure(text=texto)
            self._pintar_estado()
            self._dibujar_barra()
        except tk.TclError:
            return
        self.after(80, self._tick)

    def _recibir(self, linea: str) -> None:
        avance = parsear_progreso(linea)
        if avance:
            self.progreso = avance
            aviso = getattr(self.maestra, "actividad_progreso", None)
            if aviso:
                aviso(self)
            return
        nuevo = parsear_item(linea)
        if nuevo:
            self.items.append(nuevo)        # no ensucia el detalle: se muestra en el resultado
            return
        # El cierre de las herramientas lista los bloques que esperan la firma.
        if linea.strip() == "FALTA TU FIRMA en:":
            self._leyendo_firmas = True
        elif self._leyendo_firmas:
            if linea.startswith("    ") and linea.strip():
                self.firmas.append(linea.strip())
            elif linea.strip():
                self._leyendo_firmas = False
        self.lineas = (self.lineas + [linea])[-5000:]
        self._escribir(linea)
        if linea.strip():
            limpia = re.sub(r"^\s*\[[A-ZÁ-Ú]+\]\s*", "", linea.strip())
            self.resumen.configure(text=limpia[:90] or "Trabajando…")

    def _mostrar_resultado(self) -> None:
        """Pinta qué intenté, qué hice y qué no (solo si la herramienta informó ítems)."""
        if not self.items and not self.firmas:
            return
        lineas = lineas_de_resultado(self.items, self.firmas)
        self.texto_resultado.configure(state="normal")
        self.texto_resultado.delete("1.0", "end")
        for texto, estilo in lineas:
            self.texto_resultado.insert("end", texto + "\n", estilo)
        self.texto_resultado.configure(state="disabled")
        self.marco_resultado.pack(fill="both", expand=True, padx=16, pady=(6, 0),
                                  before=self.alternador)
        self.geometry(f"{self.winfo_width()}x"
                      f"{max(self.winfo_height(), self._acotar(self.ALTO_RESULTADO))}")

    def _escribir(self, linea: str) -> None:
        etiqueta = etiqueta_de_linea(linea)
        self.texto.configure(state="normal")
        self.texto.insert("end", linea + "\n", etiqueta)
        self.texto.see("end")
        self.texto.configure(state="disabled")

    def _terminar(self, codigo: int | None) -> None:
        """El script terminó (o se cerró la ventana): se fija el resultado final."""
        if self._notificada:
            return
        self._notificada = True
        self.duracion = time.time() - self.inicio
        self.resultado = resumir_ejecucion(codigo, self.lineas, cancelada=self._cancelada,
                                           items=self.items)
        self.estado_actual = self.resultado["estado"]
        registrar(f"«{self.titulo}»: {ESTADOS[self.estado_actual]['texto'].lower()} "
                  f"({formatear_duracion(self.duracion)}) · {self.resultado['resumen']}")
        aviso = getattr(self.maestra, "actividad_fin", None)
        if aviso:
            try:
                aviso(self, {**self.resultado, "duracion": self.duracion})
            except tk.TclError:
                pass
        if self._cerrada:
            return
        self.resumen.configure(text=self.resultado["resumen"])
        self.linea_estado.configure(
            text=f"{ESTADOS[self.estado_actual]['texto']} · tardó "
                 f"{formatear_duracion(self.duracion)}")
        pista = ""
        if self.estado_actual == "error":
            pista = traducir_error(self.lineas) or \
                "Algo salió mal. Abre «Ver detalles» para ver qué pasó."
            self._alternar_detalle(True)
        elif self.estado_actual == "avisos":
            pista = ("Terminó, pero algunas cosas no se pudieron completar: abajo dice cuáles "
                     "y qué hacer." if self.items else
                     "Terminó, pero quedaron cosas por revisar. Mira «Ver detalles».")
        self._mostrar_resultado()
        self.pista.configure(text=pista, fg=color_de_estado(self.estado_actual)
                             if self.estado_actual in ("error", "avisos") else COLOR_TENUE)
        self._armar_pie()
        self._pintar_estado()
        self._dibujar_barra()


class VentanaPreguntar(tk.Toplevel):
    """Pide un dato y después abre la herramienta en una consola de verdad.

    La ventanita de la barra solo muestra lo que el script escribe; no deja
    responder. Lo que necesita que el docente elija algo (qué mes completar, a
    qué curso asignar cada unidad) se lanza en una consola donde sí se puede.
    """

    def __init__(self, maestra, titulo: str, herramienta: dict):
        super().__init__(maestra)
        self.herramienta = herramienta
        self.title(titulo)
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        fuente = tkfont.Font(family="Segoe UI", size=10)

        tk.Label(self, text=titulo, bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=(fuente.cget("family"), 12, "bold"), anchor="w"
                 ).pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(self, text=herramienta.get("pregunta", ""), bg=COLOR_FONDO,
                 fg=COLOR_TENUE, font=(fuente.cget("family"), 8), anchor="w",
                 justify="left", wraplength=300).pack(fill="x", padx=16, pady=(0, 8))

        self.opciones = herramienta.get("opciones") or []
        self.elegida = tk.StringVar(value=(self.opciones[0]["valor"]
                                           if self.opciones else ""))
        for o in self.opciones:
            tk.Radiobutton(self, text=o["texto"], value=o["valor"], variable=self.elegida,
                           bg=COLOR_FONDO, fg=COLOR_TEXTO, selectcolor=COLOR_BOTON,
                           activebackground=COLOR_FONDO, activeforeground=COLOR_ACENTO,
                           font=fuente, anchor="w", bd=0, highlightthickness=0
                           ).pack(fill="x", padx=22)

        self.libre = None
        if herramienta.get("escribir"):
            marco = tk.Frame(self, bg=COLOR_BOTON)
            marco.pack(fill="x", padx=16, pady=(8, 2))
            self.libre = tk.Entry(marco, bg=COLOR_BOTON, fg=COLOR_TEXTO, bd=0,
                                  font=fuente, insertbackground=COLOR_TEXTO,
                                  highlightthickness=0)
            self.libre.pack(fill="x", padx=8, pady=7)
            self.libre.bind("<Return>", lambda _e: self._lanzar())

        pie = tk.Frame(self, bg=COLOR_FONDO)
        pie.pack(fill="x", padx=16, pady=(10, 14))
        for texto, accion, lado in (("Continuar", self._lanzar, "left"),
                                    ("Cancelar", self.destroy, "right")):
            b = tk.Label(pie, text=f"   {texto}   ", bg=COLOR_BOTON, fg=COLOR_TEXTO,
                         font=fuente, cursor="hand2", pady=5)
            b.pack(side=lado)
            b.bind("<Button-1>", lambda _e, a=accion: a())
            b.bind("<Enter>", lambda _e, w=b: w.configure(bg=COLOR_HOVER))
            b.bind("<Leave>", lambda _e, w=b: w.configure(bg=COLOR_BOTON))

        self.update_idletasks()
        x = maestra.winfo_x() - self.winfo_reqwidth() - 12
        self.geometry(f"+{max(20, x)}+{max(20, maestra.winfo_y() + 40)}")

    def _lanzar(self) -> None:
        valor = (self.libre.get().strip() if self.libre and self.libre.get().strip()
                 else self.elegida.get())
        orden = comando_webclass(*partes_de_comando(
            self.herramienta.get("destino", "").replace("{valor}", valor)))
        if self.herramienta.get("interactivo"):
            try:
                abrir_en_consola(self.title(), orden)
            except Exception as exc:  # noqa: BLE001
                registrar("no se pudo abrir la consola", traceback.format_exc())
                messagebox.showerror("Barra Profe", f"No se pudo abrir.\n\n{exc}")
                return
        else:
            Consola(self.master, self.title(), orden, WEBCLASS,
                    self.herramienta.get("icono", ""))
        registrar(f"«{self.title()}» con «{valor}»")
        self.destroy()


class VentanaColores(tk.Toplevel):
    """Muestra las paletas para elegir, con una muestra de cada una."""

    def __init__(self, maestra):
        super().__init__(maestra)
        self.title("Color de la barra")
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        fuente = tkfont.Font(family="Segoe UI", size=10)

        tk.Label(self, text="Elige el color", bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=(fuente.cget("family"), 12, "bold"), anchor="w"
                 ).pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(self, text=f"Queda guardado para {NOMBRE or 'este perfil'}.",
                 bg=COLOR_FONDO, fg=COLOR_TENUE, font=(fuente.cget("family"), 8),
                 anchor="w").pack(fill="x", padx=16, pady=(0, 10))

        for clave, p in PALETAS.items():
            activa = clave == PALETA
            fila = tk.Frame(self, bg=p["boton"], cursor="hand2",
                            highlightthickness=2,
                            highlightbackground=p["acento"] if activa else p["boton"],
                            highlightcolor=p["acento"] if activa else p["boton"])
            fila.pack(fill="x", padx=16, pady=3)
            # Una muestra de los colores de esa paleta, para verla antes de elegir.
            muestra = tk.Frame(fila, bg=p["boton"])
            muestra.pack(side="left", padx=(8, 10), pady=8)
            for color in (p["fondo"], p["acento"], p["lengueta"], p["hover"]):
                tk.Frame(muestra, bg=color, width=14, height=14).pack(side="left", padx=1)
            tk.Label(fila, text=("● " if activa else "") + p["nombre"], bg=p["boton"],
                     fg=p["texto"], font=fuente, anchor="w").pack(side="left", pady=8)
            for widget in (fila, *fila.winfo_children()):
                widget.bind("<Button-1>", lambda _e, c=clave: self._elegir(c))
                for hijo in widget.winfo_children():
                    hijo.bind("<Button-1>", lambda _e, c=clave: self._elegir(c))

        cerrar = tk.Label(self, text="   Cerrar   ", bg=COLOR_BOTON, fg=COLOR_TEXTO,
                          font=fuente, cursor="hand2", pady=5)
        cerrar.pack(pady=(10, 14))
        cerrar.bind("<Button-1>", lambda _e: self.destroy())

        self.update_idletasks()
        x = maestra.winfo_x() - self.winfo_reqwidth() - 12
        self.geometry(f"+{max(20, x)}+{max(20, maestra.winfo_y() + 40)}")

    def _elegir(self, clave: str) -> None:
        if clave == PALETA:
            self.destroy()
            return
        guardar_color(clave)


class VentanaDocentes(tk.Toplevel):
    """Cambia entre los docentes registrados en este equipo."""

    def __init__(self, maestra):
        super().__init__(maestra)
        self.title("Cambiar de profesor")
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        fuente = tkfont.Font(family="Segoe UI", size=10)

        tk.Label(self, text="¿Quién va a usar la barra?", bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=(fuente.cget("family"), 12, "bold"), anchor="w"
                 ).pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(self, text="Se cambian los cursos, el libro y la lista de pendientes.",
                 bg=COLOR_FONDO, fg=COLOR_TENUE, font=(fuente.cget("family"), 8),
                 anchor="w", justify="left").pack(fill="x", padx=16, pady=(0, 10))

        for clave, nombre in DOCENTES:
            activo = clave == PERFIL
            fila = tk.Label(self, text=f"   {'●' if activo else '○'}  {nombre}   ",
                            bg=COLOR_ACENTO if activo else COLOR_BOTON,
                            fg=COLOR_FONDO if activo else COLOR_TEXTO,
                            font=fuente, anchor="w", cursor="hand2", pady=7)
            fila.pack(fill="x", padx=16, pady=2)
            if not activo:
                fila.bind("<Button-1>", lambda _e, c=clave: self._elegir(c))
                fila.bind("<Enter>", lambda _e, f=fila: f.configure(bg=COLOR_HOVER))
                fila.bind("<Leave>", lambda _e, f=fila: f.configure(bg=COLOR_BOTON))

        cerrar = tk.Label(self, text="   Cerrar   ", bg=COLOR_BOTON, fg=COLOR_TEXTO,
                          font=fuente, cursor="hand2", pady=5)
        cerrar.pack(pady=(10, 14))
        cerrar.bind("<Button-1>", lambda _e: self.destroy())

        self.update_idletasks()
        x = maestra.winfo_x() - self.winfo_reqwidth() - 12
        self.geometry(f"+{max(20, x)}+{max(20, maestra.winfo_y() + 40)}")

    def _elegir(self, clave: str) -> None:
        try:
            rutas.fijar_perfil_activo(clave)
        except OSError as exc:
            messagebox.showerror("Barra Profe", f"No pude cambiar de profesor.\n\n{exc}")
            return
        registrar(f"docente activo: {clave}")
        reabrir_barra()


class VentanaHorario(tk.Toplevel):
    """Muestra el horario de la semana como tabla: días en columnas, horas en filas."""

    def __init__(self, maestra):
        super().__init__(maestra)
        self.title("Mi horario de la semana")
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.fuente = tkfont.Font(family="Segoe UI", size=9)
        self._generando = False

        self.titulo = tk.Label(self, text="Mi horario de la semana", bg=COLOR_FONDO,
                               fg=COLOR_TEXTO, font=(self.fuente.cget("family"), 12, "bold"),
                               anchor="w")
        self.titulo.pack(fill="x", padx=16, pady=(14, 0))
        self.subtitulo = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_TENUE,
                                  font=(self.fuente.cget("family"), 8), anchor="w")
        self.subtitulo.pack(fill="x", padx=16, pady=(0, 8))

        self.tabla = tk.Frame(self, bg=COLOR_FONDO)
        self.tabla.pack(padx=16, pady=(0, 6))

        pie = tk.Frame(self, bg=COLOR_FONDO)
        pie.pack(fill="x", padx=16, pady=(0, 12))
        self.boton_actualizar = self._boton(pie, "Actualizar", self._generar, "left")
        self._boton(pie, "Cerrar", self.destroy, "right")

        self._dibujar()
        self.update_idletasks()
        x = maestra.winfo_x() - self.winfo_reqwidth() - 12
        self.geometry(f"+{max(20, x)}+{max(20, maestra.winfo_y() + 40)}")
        if not self._hay_datos():
            self._generar()

    def _boton(self, padre, texto: str, accion, lado: str) -> tk.Label:
        b = tk.Label(padre, text=f"   {texto}   ", bg=COLOR_BOTON, fg=COLOR_TEXTO,
                     font=self.fuente, cursor="hand2", pady=5)
        b.pack(side=lado)
        b.bind("<Button-1>", lambda _e: accion())
        b.bind("<Enter>", lambda _e: b.configure(bg=COLOR_HOVER))
        b.bind("<Leave>", lambda _e: b.configure(bg=COLOR_BOTON))
        return b

    def _leer(self) -> dict:
        try:
            with open(HORARIO_SEMANA, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _hay_datos(self) -> bool:
        return bool(self._leer().get("bloques"))

    def _generar(self) -> None:
        """Vuelve a armar el horario consultando Webclass (demora unos segundos)."""
        if self._generando:
            return
        self._generando = True
        self.subtitulo.configure(text="Consultando Webclass…")
        self.boton_actualizar.configure(text="   Espera…   ")
        try:
            proceso = subprocess.Popen(comando_webclass("horario", "--salida", HORARIO_SEMANA),
                                       cwd=WEBCLASS,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as exc:  # noqa: BLE001
            registrar("no se pudo generar el horario", str(exc))
            self._generando = False
            self.subtitulo.configure(text="No se pudo consultar Webclass")
            return

        def esperar() -> None:
            proceso.wait()
            try:
                self.after(0, self._termina_generar)
            except tk.TclError:
                pass
        threading.Thread(target=esperar, daemon=True).start()

    def _termina_generar(self) -> None:
        self._generando = False
        self.boton_actualizar.configure(text="   Actualizar   ")
        self._dibujar()

    def _dibujar(self) -> None:
        for hijo in self.tabla.winfo_children():
            hijo.destroy()
        datos = self._leer()
        bloques = datos.get("bloques", [])
        if datos.get("error"):
            self.subtitulo.configure(text="No se pudo leer el horario desde Webclass")
        elif datos.get("semana"):
            self.subtitulo.configure(text=f"Semana del {datos['semana']} · "
                                          f"actualizado {datos.get('generado', '')}")
        if not bloques:
            tk.Label(self.tabla, text="Sin datos todavía.", bg=COLOR_FONDO,
                     fg=COLOR_TENUE, font=self.fuente).pack(pady=10)
            return

        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
        horas = sorted({(b["inicio"], b["fin"]) for b in bloques})
        celdas = {(b["dia"], b["inicio"]): b for b in bloques}

        tk.Label(self.tabla, text="", bg=COLOR_FONDO).grid(row=0, column=0, padx=1, pady=1)
        for c, dia in enumerate(dias, start=1):
            tk.Label(self.tabla, text=dia, bg=COLOR_FONDO, fg=COLOR_ACENTO,
                     font=(self.fuente.cget("family"), 9, "bold"), width=11,
                     pady=4).grid(row=0, column=c, padx=1, pady=1)

        for f, (inicio, fin) in enumerate(horas, start=1):
            tk.Label(self.tabla, text=f"{inicio}\n{fin}", bg=COLOR_FONDO, fg=COLOR_TENUE,
                     font=(self.fuente.cget("family"), 8), justify="right",
                     padx=6).grid(row=f, column=0, sticky="e")
            for c, _dia in enumerate(dias):
                b = celdas.get((c, inicio))
                if b:
                    texto = b["curso"]
                    if "rientaci" in (b.get("asignatura") or ""):
                        texto += "\nOrientación"
                    celda = tk.Label(self.tabla, text=texto, bg=COLOR_BOTON, fg=COLOR_TEXTO,
                                     font=(self.fuente.cget("family"), 10, "bold"),
                                     width=11, height=2)
                else:
                    celda = tk.Label(self.tabla, text="", bg=COLOR_FONDO, width=11, height=2)
                celda.grid(row=f, column=c + 1, padx=1, pady=1, sticky="nsew")


class SelectorAsignatura(tk.Frame):
    """«Asignatura de estos recursos: [ … ]  ☐ No volver a preguntar», para «Subir recursos» y para arrastrar.

    Lo elegido se guarda por cuenta (personal\\subida_<cuenta>.json): lo lee la subida automática de cada
    10 minutos, así que vale para todo lo que haya en el buzón. Si el docente marcó «No volver a preguntar»,
    solo avisa con cuál se sube y deja «Cambiar».
    """

    def __init__(self, padre):
        super().__init__(padre, bg=COLOR_FONDO)
        from barra_utiles import (ASIGNATURAS_SUBIDA, asignatura_sugerida, leer_preferencia_subida,
                                  ruta_preferencia_subida)
        self.ruta = ruta_preferencia_subida(rutas.PERSONAL, PERFIL)
        pref = leer_preferencia_subida(self.ruta)
        self.nombres = dict(ASIGNATURAS_SUBIDA)
        self.clave = pref["asignatura"] or asignatura_sugerida(perfil_de_trabajo())
        self.combo = None
        self.var_no_preguntar = tk.BooleanVar(value=not pref["preguntar"])
        if pref["preguntar"]:
            self.mostrar_selector()
        else:
            self._mostrar_fija()

    def _mostrar_fija(self) -> None:
        familia = "Segoe UI"
        tk.Label(self, text=f"Se suben como: {self.nombres[self.clave]}", bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=(familia, 10)).pack(side="left")
        cambiar = tk.Label(self, text="Cambiar", bg=COLOR_FONDO, fg=COLOR_ACENTO, font=(familia, 9, "underline"),
                           cursor="hand2", takefocus=True)
        cambiar.pack(side="left", padx=(10, 0))
        cambiar.bind("<Button-1>", lambda _e: self.mostrar_selector())
        cambiar.bind("<Return>", lambda _e: self.mostrar_selector())

    def mostrar_selector(self) -> None:
        for hijo in self.winfo_children():
            hijo.destroy()
        familia = "Segoe UI"
        estilo = ttk.Style(self)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        estilo.configure("Barra.TCombobox", fieldbackground=COLOR_FONDO, background=COLOR_BOTON,
                         foreground=COLOR_TEXTO, arrowcolor=COLOR_ACENTO, bordercolor=COLOR_ACENTO,
                         lightcolor=COLOR_BOTON, darkcolor=COLOR_BOTON, padding=4)
        estilo.map("Barra.TCombobox", fieldbackground=[("readonly", COLOR_FONDO)],
                   foreground=[("readonly", COLOR_TEXTO)])
        self.option_add("*TCombobox*Listbox.background", COLOR_FONDO)
        self.option_add("*TCombobox*Listbox.foreground", COLOR_TEXTO)
        self.option_add("*TCombobox*Listbox.selectBackground", COLOR_ACENTO)
        self.option_add("*TCombobox*Listbox.selectForeground", COLOR_FONDO)
        tk.Label(self, text="Asignatura de estos recursos:", bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=(familia, 10)).pack(side="left")
        self.combo = ttk.Combobox(self, values=list(self.nombres.values()), state="readonly", width=30,
                                  style="Barra.TCombobox", font=(familia, 10))
        self.combo.set(self.nombres[self.clave])
        self.combo.pack(side="left", padx=(8, 0))
        tk.Checkbutton(self, text="No volver a preguntar", variable=self.var_no_preguntar, bg=COLOR_FONDO,
                       fg=COLOR_TENUE, selectcolor=COLOR_BOTON, activebackground=COLOR_FONDO,
                       activeforeground=COLOR_TEXTO, font=(familia, 9)).pack(side="left", padx=(12, 0))
        self.var_no_preguntar.set(False)

    def elegida(self) -> str:
        if self.combo is not None:
            return next((k for k, n in self.nombres.items() if n == self.combo.get()), self.clave)
        return self.clave

    def guardar(self) -> None:
        from barra_utiles import guardar_preferencia_subida
        try:
            guardar_preferencia_subida(self.ruta, self.elegida(), preguntar=not self.var_no_preguntar.get())
        except (OSError, ValueError):
            pass                                          # sin guardar: se sube con la que ya había


class VentanaSoltar(tk.Toplevel):
    """Pregunta a qué nivel van los archivos soltados y los copia al buzón."""

    def __init__(self, maestra, archivos: list[str]):
        super().__init__(maestra)
        self.maestra = maestra
        self.archivos = archivos
        self.title("Enviar a Webclass")
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        fuente = tkfont.Font(family="Segoe UI", size=10)

        resumen = (os.path.basename(archivos[0]) if len(archivos) == 1
                   else f"{len(archivos)} archivos")
        self.titulo_resumen = tk.Label(self, text=resumen, bg=COLOR_FONDO, fg=COLOR_TEXTO, anchor="w",
                                       font=(fuente.cget("family"), 11, "bold"), wraplength=320,
                                       justify="left")
        self.titulo_resumen.pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(self, text="¿A qué nivel lo dejo?", bg=COLOR_FONDO, fg=COLOR_TENUE,
                 font=fuente, anchor="w").pack(fill="x", padx=16, pady=(0, 8))

        try:
            niveles = sorted(d for d in os.listdir(BUZON)
                             if os.path.isdir(os.path.join(BUZON, d))
                             and not d.startswith("_"))
        except OSError:
            niveles = []
        for nivel in niveles:
            fila = tk.Label(self, text=f"  {nivel}", bg=COLOR_BOTON, fg=COLOR_TEXTO,
                            font=fuente, anchor="w", cursor="hand2", pady=7)
            fila.pack(fill="x", padx=16, pady=2)
            fila.bind("<Button-1>", lambda _e, n=nivel: self._copiar(n))
            fila.bind("<Enter>", lambda _e, f=fila: f.configure(bg=COLOR_HOVER))
            fila.bind("<Leave>", lambda _e, f=fila: f.configure(bg=COLOR_BOTON))

        # Con qué asignatura se firman al subirse (se ve y se elige aquí, la primera vez y cuando se quiera).
        self.selector_asignatura = SelectorAsignatura(self)
        self.selector_asignatura.pack(fill="x", padx=16, pady=(10, 0))
        # No todo es para el equipo PIE: se decide aquí, archivo por archivo, y siempre pasa por
        # la vista previa del correo antes de enviar. Por defecto no se envía nada.
        self.pie = tk.BooleanVar(value=False)
        tk.Checkbutton(self, text="Además, enviarlo al equipo PIE por correo", variable=self.pie,
                       bg=COLOR_FONDO, fg=COLOR_TEXTO, selectcolor=COLOR_BOTON,
                       activebackground=COLOR_FONDO, activeforeground=COLOR_TEXTO, font=fuente,
                       anchor="w").pack(fill="x", padx=16, pady=(10, 0))
        solo = tk.Label(self, text="  ✉ Solo enviarlo al equipo PIE (no subir a Webclass)",
                        bg=COLOR_BOTON, fg=COLOR_TEXTO, font=fuente, anchor="w", cursor="hand2", pady=7)
        solo.pack(fill="x", padx=16, pady=(6, 2))
        solo.bind("<Button-1>", lambda _e: self._solo_pie())
        solo.bind("<Enter>", lambda _e: solo.configure(bg=COLOR_HOVER))
        solo.bind("<Leave>", lambda _e: solo.configure(bg=COLOR_BOTON))
        self.aviso = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_ACENTO,
                              font=(fuente.cget("family"), 8), anchor="w",
                              wraplength=320, justify="left")
        self.aviso.pack(fill="x", padx=16, pady=(6, 0))
        cerrar = tk.Label(self, text="   Cancelar   ", bg=COLOR_BOTON, fg=COLOR_TENUE,
                          font=fuente, cursor="hand2", pady=5)
        cerrar.pack(padx=16, pady=(8, 14))
        cerrar.bind("<Button-1>", lambda _e: self.destroy())
        self.update_idletasks()
        x = maestra.winfo_x() - 360 if maestra.lado == "derecha" else maestra.winfo_x() + 60
        self.geometry(f"+{max(20, x)}+{maestra.winfo_y() + 60}")

    def _copiar(self, nivel: str) -> None:
        destino = os.path.join(BUZON, nivel)
        os.makedirs(destino, exist_ok=True)   # puede que esa carpeta aún no exista
        copiados, fallidos = 0, []
        for origen in self.archivos:
            nombre = os.path.basename(origen)
            try:
                tam = os.path.getsize(origen)
                if tam == 0:
                    # Pasa al arrastrar algo que todavía se está descargando o
                    # que está en la nube sin bajar. Copiarlo deja un archivo
                    # vacío que después se queda atascado esperando para siempre.
                    fallidos.append(f"{nombre}: está vacío (0 bytes)")
                    continue
                final = os.path.join(destino, nombre)
                base, ext = os.path.splitext(final)
                n = 2
                while os.path.exists(final):      # no pisar lo que ya esté ahí
                    final, n = f"{base} ({n}){ext}", n + 1
                shutil.copy2(origen, final)
                if os.path.getsize(final) != tam:
                    os.remove(final)              # copia a medias: no se deja
                    fallidos.append(f"{nombre}: la copia quedó incompleta")
                    continue
                copiados += 1
            except OSError as exc:
                fallidos.append(f"{nombre}: {exc}")
        registrar(f"soltados {copiados} archivo(s) en {nivel}",
                  "\n".join(fallidos))
        if copiados:
            self.selector_asignatura.guardar()
        if fallidos:
            self.aviso.configure(text="No se pudieron copiar: " + "; ".join(fallidos),
                                 fg=COLOR_ERROR)
            return
        if self.pie.get():
            self._abrir_correo()
            return
        self.aviso.configure(text=f"{copiados} copiado(s) en «{nivel}». Se suben solos dentro de 10 minutos, "
                                  f"como {self.selector_asignatura.nombres[self.selector_asignatura.elegida()]}.",
                             fg=COLOR_ACENTO)
        self.after(1800, self.destroy)

    def agregar_archivos(self, nuevos: list[str]) -> None:
        """Otro archivo soltado mientras esta ventana está abierta: van todos juntos."""
        self.archivos += [n for n in nuevos if n not in self.archivos]
        self.titulo_resumen.configure(text=f"{len(self.archivos)} archivos")

    def _abrir_correo(self) -> None:
        """Abre el correo al equipo PIE con estos archivos ya elegidos (se confirma allí)."""
        maestra, archivos = self.maestra, list(self.archivos)
        self.destroy()
        VentanaCorreo(maestra, {"nombre": "Enviar al equipo PIE", "icono": "✉️", "tipo": "correo"},
                      archivos=archivos)

    def _solo_pie(self) -> None:
        self._abrir_correo()


def boton_texto(padre, texto: str, accion, principal: bool = False) -> tk.Label:
    """Botón de texto de las ventanas auxiliares (hover, teclado, color de énfasis)."""
    normal = COLOR_ACENTO if principal else COLOR_BOTON
    b = tk.Label(padre, text=f"  {texto}  ", font=("Segoe UI", 10), cursor="hand2",
                 bg=normal, fg=COLOR_FONDO if principal else COLOR_TEXTO, pady=5,
                 takefocus=True, highlightthickness=1, highlightbackground=normal,
                 highlightcolor=COLOR_TEXTO)
    b.bind("<Button-1>", lambda _e: accion())
    for tecla in ("<Return>", "<space>"):
        b.bind(tecla, lambda _e: accion())
    b.bind("<Enter>", lambda _e: b.configure(bg=COLOR_TEXTO if principal else COLOR_HOVER))
    b.bind("<Leave>", lambda _e: b.configure(bg=normal))
    return b


def matar_proceso(proceso: subprocess.Popen | None) -> None:
    """Detiene un proceso y los que lanzó (un .bat lanza python)."""
    if proceso is None or proceso.poll() is not None:
        return
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proceso.pid)],
                       capture_output=True, timeout=5,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        try:
            proceso.kill()
        except OSError:
            pass


def colocar_junto_a_la_barra(ventana: tk.Toplevel, barra, y_preferida: int | None = None) -> None:
    """Pone una ventana al costado de la barra, sin salirse del monitor."""
    ventana.update_idletasks()
    ancho, alto = ventana.winfo_reqwidth(), ventana.winfo_reqheight()
    izq, arriba, der, abajo = barra._area()
    if barra.lado == "derecha":
        x = barra.winfo_x() - ancho - 12
    else:
        x = barra.winfo_x() + barra.winfo_width() + 12
    y = barra.winfo_y() + 40 if y_preferida is None else y_preferida
    x = max(izq + 8, min(x, der - ancho - 8))
    y = max(arriba + 8, min(y, abajo - alto - 8))
    ventana.geometry(f"+{x}+{y}")


class ListaMarcable(tk.Frame):
    """Lista con casillas (☑ / ☐), agrupada, con scroll y manejo por teclado.

    Sirve para elegir qué se aplica (vista previa) y qué se cambia (destinos).
    Clic o espacio marcan y desmarcan; Arriba y Abajo recorren; la rueda
    desplaza. `al_cambiar(marcadas, total)` avisa cada vez que cambia algo.
    """

    def __init__(self, padre, al_cambiar=None, alto_max: int = 300):
        super().__init__(padre, bg=COLOR_BOTON)
        self.al_cambiar = al_cambiar
        self.alto_max = alto_max
        self.estado: dict[str, bool] = {}
        self.orden: list[str] = []
        self.cajas: dict[str, tk.Label] = {}
        self.filas: dict[str, tk.Frame] = {}
        self._grupo_actual: str | None = None
        self.canvas = tk.Canvas(self, bg=COLOR_BOTON, highlightthickness=0, bd=0, height=10)
        self.barra = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.barra.set)
        self.interior = tk.Frame(self.canvas, bg=COLOR_BOTON)
        self._ventana = self.canvas.create_window((0, 0), window=self.interior, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.interior.bind("<Configure>", lambda _e: self._ajustar())
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._ventana, width=e.width))
        self._rueda_en(self.canvas)
        self._rueda_en(self.interior)

    # ------------------------------------------------------------- armado
    def _rueda_en(self, widget) -> None:
        widget.bind("<MouseWheel>", self._rueda, add="+")

    def _rueda(self, evento) -> None:
        if self.barra.winfo_ismapped():
            self.canvas.yview_scroll(int(-evento.delta / 120), "units")

    def _ajustar(self) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        alto = self.interior.winfo_reqheight()
        self.canvas.configure(height=min(alto, self.alto_max))
        if alto > self.alto_max:
            if not self.barra.winfo_ismapped():
                self.barra.pack(side="right", fill="y")
        elif self.barra.winfo_ismapped():
            self.barra.pack_forget()

    def agregar(self, clave: str, titulo: str, detalle: str = "", grupo: str = "",
                marcado: bool = True, ancho_texto: int = 380) -> None:
        familia = "Segoe UI"
        if grupo and grupo != self._grupo_actual:
            self._grupo_actual = grupo
            cab = tk.Label(self.interior, text=grupo.upper(), bg=COLOR_BOTON, fg=COLOR_ACENTO,
                           font=(familia, 8, "bold"), anchor="w")
            cab.pack(fill="x", padx=12, pady=(8, 0))
            self._rueda_en(cab)
        fila = tk.Frame(self.interior, bg=COLOR_BOTON, cursor="hand2", takefocus=True,
                        highlightthickness=1, highlightbackground=COLOR_BOTON,
                        highlightcolor=COLOR_ACENTO)
        fila.pack(fill="x", padx=6, pady=1)
        caja = tk.Label(fila, text="", bg=COLOR_BOTON, fg=COLOR_ACENTO,
                        font=("Segoe UI Symbol", 13), width=2)
        caja.pack(side="left", padx=(6, 2), anchor="n", pady=2)
        columna = tk.Frame(fila, bg=COLOR_BOTON)
        columna.pack(side="left", fill="x", expand=True, pady=4)
        tk.Label(columna, text=titulo, bg=COLOR_BOTON, fg=COLOR_TEXTO, font=(familia, 10),
                 anchor="w", justify="left", wraplength=ancho_texto).pack(fill="x")
        if detalle:
            tk.Label(columna, text=detalle, bg=COLOR_BOTON, fg=COLOR_TENUE, font=(familia, 9),
                     anchor="w", justify="left", wraplength=ancho_texto).pack(fill="x")
        self.estado[clave] = marcado
        self.orden.append(clave)
        self.cajas[clave] = caja
        self.filas[clave] = fila
        for widget in (fila, caja, columna, *columna.winfo_children()):
            widget.bind("<Button-1>", lambda _e, k=clave: self._pulsar(k))
            self._rueda_en(widget)
        fila.bind("<space>", lambda _e, k=clave: (self._pulsar(k), "break")[1])
        fila.bind("<Return>", lambda _e, k=clave: (self._pulsar(k), "break")[1])
        fila.bind("<Down>", lambda e: (e.widget.tk_focusNext().focus_set(), "break")[1])
        fila.bind("<Up>", lambda e: (e.widget.tk_focusPrev().focus_set(), "break")[1])
        self._pintar(clave)

    # ------------------------------------------------------------ estado
    def _pintar(self, clave: str) -> None:
        marcada = self.estado[clave]
        self.cajas[clave].configure(text="☑" if marcada else "☐",
                                    fg=COLOR_ACENTO if marcada else COLOR_SUAVE)

    def _pulsar(self, clave: str) -> None:
        self.fijar(clave, not self.estado[clave])
        self.filas[clave].focus_set()

    def fijar(self, clave: str, valor: bool) -> None:
        if self.estado.get(clave) == valor:
            return
        self.estado[clave] = valor
        self._pintar(clave)
        self._avisar()

    def marcar_todo(self, valor: bool = True) -> None:
        for clave in self.orden:
            self.estado[clave] = valor
            self._pintar(clave)
        self._avisar()

    def marcadas(self) -> list[str]:
        return [c for c in self.orden if self.estado[c]]

    def todas(self) -> list[str]:
        return list(self.orden)

    def _avisar(self) -> None:
        if self.al_cambiar:
            self.al_cambiar(self.marcadas(), len(self.orden))


class VistaPrevia(tk.Toplevel):
    """«Esto es lo que voy a hacer»: confirmación con vista previa y casillas.

    Se abre antes de ejecutar un botón que escribe en Webclass. Según el campo
    `vista_previa` del botón, arma el resumen al instante ("libro", "subir") o
    simulando la herramienta con `--simular` ("simular": consulta Webclass,
    pero no escribe nada). Cada cosa que se haría tiene una casilla: el docente
    deja marcado lo que quiere que se aplique y desmarca lo demás.

    Al continuar se llama a `continuar(claves, todas)`: las claves marcadas y
    todas las posibles (o None y [] si el resumen no tenía casillas).
    """

    ANCHO = 520

    def __init__(self, maestra, herramienta: dict, continuar):
        super().__init__(maestra)
        self.maestra = maestra
        self.herramienta = herramienta
        self.continuar = continuar
        self.nombre = herramienta.get("nombre", "(sin nombre)")
        self.proceso: subprocess.Popen | None = None
        self.cola: queue.Queue = queue.Queue()
        self.lineas: list[str] = []
        self.items: list[dict] = []
        self.progreso: tuple[int, int, str] | None = None
        self.lista: ListaMarcable | None = None
        self.boton_continuar: tk.Label | None = None
        self.inicio = time.time()
        self._cerrada = False
        self._cargando = False
        self._hay_marcadas = True
        self.title("Antes de empezar")
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        familia = "Segoe UI"

        cabecera = tk.Frame(self, bg=COLOR_FONDO)
        cabecera.pack(fill="x", padx=18, pady=(16, 2))
        if herramienta.get("icono"):
            tk.Label(cabecera, text=herramienta["icono"], bg=COLOR_FONDO, fg=COLOR_TEXTO,
                     font=("Segoe UI Emoji", 16)).pack(side="left", padx=(0, 8))
        tk.Label(cabecera, text=self.nombre, bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=(familia, 13, "bold")).pack(side="left")
        self.subtitulo = tk.Label(self, text="Antes de empezar, esto es lo que voy a hacer:",
                                  bg=COLOR_FONDO, fg=COLOR_TENUE, font=(familia, 9),
                                  anchor="w")
        self.subtitulo.pack(fill="x", padx=18, pady=(0, 8))
        # Si el botón traía una advertencia propia ("puede tardar varios minutos…"),
        # se muestra su primer párrafo bajo el título.
        advertencia = (herramienta.get("confirmar") or "").split("\n\n")[0].strip()
        if advertencia:
            tk.Label(self, text=advertencia, bg=COLOR_FONDO, fg=COLOR_ALERTA_SUAVE,
                     font=(familia, 9), anchor="w", justify="left",
                     wraplength=self.ANCHO - 40).pack(fill="x", padx=18, pady=(0, 8))

        self.barra_carga = tk.Canvas(self, height=8, bg=COLOR_BOTON, bd=0, highlightthickness=0)
        self.controles = tk.Frame(self, bg=COLOR_FONDO)
        self.cuerpo = tk.Frame(self, bg=COLOR_BOTON)
        self.cuerpo.pack(fill="x", padx=18)
        self.aviso = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_TENUE, font=(familia, 9),
                              anchor="w", justify="left", wraplength=self.ANCHO - 40)
        self.aviso.pack(fill="x", padx=18, pady=(8, 0))
        self.pie = tk.Frame(self, bg=COLOR_FONDO)
        self.pie.pack(fill="x", padx=18, pady=(12, 16))

        self.bind("<Escape>", lambda _e: self.destroy())
        tipo = herramienta.get("vista_previa")
        self.tipo = tipo
        if tipo == "libro":
            self._mostrar(vista_previa_libro(self._leer_estado_libro(),
                                             datetime.date.today().strftime("%d/%m/%Y")))
        elif tipo == "subir":
            datos_subida = vista_previa_subir(BUZON)
            self._mostrar(datos_subida)
            if datos_subida.get("hay_trabajo"):
                self.selector_asignatura = SelectorAsignatura(self)
                self.selector_asignatura.pack(fill="x", padx=18, pady=(8, 0), before=self.aviso)
        elif tipo in ("simular", "listar", "unidades"):
            self._calcular()
        else:
            self._mostrar({"titulo": self.nombre, "puntos": [], "items": [], "aviso": "",
                           "hay_trabajo": None})
        colocar_junto_a_la_barra(self, maestra)

    # ------------------------------------------------------------- contenido
    @staticmethod
    def _leer_estado_libro() -> dict | None:
        try:
            with open(ESTADO_FIRMAS, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _poner_botones(self, botones: list[tuple[str, object, bool]]) -> None:
        for hijo in self.pie.winfo_children():
            hijo.destroy()
        self.boton_continuar = None
        for texto, accion, principal in reversed(botones):
            b = boton_texto(self.pie, texto, accion, principal)
            b.pack(side="right", padx=(8, 0))
            if accion == self._continuar:
                self.boton_continuar = b

    def _mostrar(self, datos: dict) -> None:
        """Pinta el resumen (con casillas si hay ítems) y los botones que corresponden."""
        self._cargando = False
        self.barra_carga.pack_forget()
        for hijo in self.cuerpo.winfo_children():
            hijo.destroy()
        self.controles.pack_forget()
        self.lista = None
        familia = "Segoe UI"
        items = datos.get("items") or []
        if items:
            self._armar_lista(items)
        else:
            puntos = datos["puntos"] or ["Se ejecutará la herramienta y verás cómo va."]
            for punto in puntos[:12]:
                fila = tk.Frame(self.cuerpo, bg=COLOR_BOTON)
                fila.pack(fill="x", padx=12, pady=(6, 0))
                tk.Label(fila, text="•", bg=COLOR_BOTON, fg=COLOR_ACENTO,
                         font=(familia, 11, "bold")).pack(side="left", anchor="n")
                tk.Label(fila, text=punto, bg=COLOR_BOTON, fg=COLOR_TEXTO, font=(familia, 10),
                         anchor="w", justify="left",
                         wraplength=self.ANCHO - 90).pack(side="left", fill="x", expand=True,
                                                          padx=(6, 0))
            tk.Frame(self.cuerpo, bg=COLOR_BOTON, height=8).pack()
        self.aviso.configure(text=datos["aviso"])
        if datos["hay_trabajo"] is False:
            self.subtitulo.configure(text="Por ahora no hay nada que hacer.")
            self._poner_botones([("Cerrar", self.destroy, True),
                                 ("Ejecutar igual", self._continuar, False)])
        else:
            if datos["hay_trabajo"] is None and datos["aviso"]:
                self.subtitulo.configure(text="No pude calcular la vista previa.")
            elif items:
                self.subtitulo.configure(
                    text="Marca lo que quieres que haga; lo que dejes sin marcar no se toca:")
            self._poner_botones([("Continuar", self._continuar, True),
                                 ("Cancelar", self.destroy, False)])
            self._actualizar_continuar()
        colocar_junto_a_la_barra(self, self.maestra)

    def _armar_lista(self, items: list[dict]) -> None:
        """Casillas para cada ítem, con «Seleccionar todo» y «Ninguno»."""
        self.controles.pack(fill="x", padx=18, pady=(0, 6), before=self.cuerpo)
        for hijo in self.controles.winfo_children():
            hijo.destroy()
        familia = "Segoe UI"
        self.contador = tk.Label(self.controles, text="", bg=COLOR_FONDO, fg=COLOR_TENUE,
                                 font=(familia, 9))
        self.contador.pack(side="right")
        for texto, valor in (("Seleccionar todo", True), ("Ninguno", False)):
            enlace = tk.Label(self.controles, text=texto, bg=COLOR_FONDO, fg=COLOR_ACENTO,
                              font=(familia, 9, "underline"), cursor="hand2", takefocus=True,
                              highlightthickness=1, highlightbackground=COLOR_FONDO,
                              highlightcolor=COLOR_TEXTO)
            enlace.pack(side="left", padx=(0, 14))
            enlace.bind("<Button-1>", lambda _e, v=valor: self.lista.marcar_todo(v))
            for tecla in ("<Return>", "<space>"):
                enlace.bind(tecla, lambda _e, v=valor: (self.lista.marcar_todo(v), "break")[1])
        self.lista = ListaMarcable(self.cuerpo, al_cambiar=self._al_cambiar_seleccion,
                                   alto_max=int(300))
        self.lista.pack(fill="x", padx=2, pady=2)
        for it in items:
            self.lista.agregar(it["clave"], it["titulo"], it["detalle"], it["grupo"],
                               ancho_texto=self.ANCHO - 100)
        self._al_cambiar_seleccion(self.lista.marcadas(), len(items))

    def _al_cambiar_seleccion(self, marcadas: list[str], total: int) -> None:
        self.contador.configure(text=f"{len(marcadas)} de {total} marcadas")
        self._hay_marcadas = bool(marcadas)
        self._actualizar_continuar()

    def _actualizar_continuar(self) -> None:
        b = self.boton_continuar
        if b is None or self.lista is None:
            return
        n = len(self.lista.marcadas())
        b.configure(text=f"  Continuar ({n})  " if n else "  Continuar  ",
                    bg=COLOR_ACENTO if n else COLOR_BOTON,
                    fg=COLOR_FONDO if n else COLOR_SUAVE,
                    cursor="hand2" if n else "arrow")
        # El color de pasar el mouse también depende de si se puede continuar.
        if n:
            b.bind("<Enter>", lambda _e: b.configure(bg=COLOR_TEXTO))
            b.bind("<Leave>", lambda _e: b.configure(bg=COLOR_ACENTO))
        else:
            b.bind("<Enter>", lambda _e: None)
            b.bind("<Leave>", lambda _e: b.configure(bg=COLOR_BOTON))

    def _continuar(self) -> None:
        if self.lista is not None and not self.lista.marcadas():
            self.aviso.configure(text="No hay nada marcado: marca al menos una casilla "
                                      "o cancela.", fg=COLOR_ERROR)
            return
        if getattr(self, "selector_asignatura", None) is not None:
            self.selector_asignatura.guardar()
        claves = self.lista.marcadas() if self.lista else None
        todas = self.lista.todas() if self.lista else []
        accion = self.continuar
        self.destroy()
        accion(claves, todas)

    # ------------------------------------------------ simulación (consulta Webclass)
    def _calcular(self) -> None:
        self._cargando = True
        self.subtitulo.configure(
            text="Buscando lo que está pendiente, sin escribir nada en Webclass…"
            if self.tipo == "listar" else
            "Buscando unidades nuevas en Webclass, sin escribir nada…"
            if self.tipo == "unidades" else
            "Revisando qué haría, sin escribir nada en Webclass…")
        self.barra_carga.pack(fill="x", padx=18, pady=(0, 8), before=self.cuerpo)
        self.estado_carga = tk.Label(self.cuerpo, text="", bg=COLOR_BOTON, fg=COLOR_TENUE,
                                     font=("Segoe UI", 10), anchor="w")
        self.estado_carga.pack(fill="x", padx=12, pady=12)
        self._poner_botones([("Continuar sin vista previa", self._continuar, False),
                             ("Cancelar", self.destroy, False)])
        destino = ruta_util(self.herramienta.get("destino", ""))
        orden = comando_webclass(*partes_de_comando(destino),
                                 {"listar": "--solo-listar",
                                  "unidades": "--buscar-unidades"}.get(self.tipo, "--simular"))
        threading.Thread(target=self._correr, args=(orden,), daemon=True).start()
        self.after(80, self._tick)

    def _correr(self, orden: list[str]) -> None:
        codigo: int | None = None
        try:
            proceso = subprocess.Popen(
                orden, cwd=WEBCLASS, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.proceso = proceso
            if self._cerrada:
                proceso.kill()
                return
            for linea in proceso.stdout:
                self.cola.put(linea.rstrip("\n"))
            proceso.wait()
            codigo = proceso.returncode
        except Exception as exc:  # noqa: BLE001
            registrar(f"no se pudo calcular la vista previa de «{self.nombre}»",
                      traceback.format_exc())
            self.cola.put(f"Error: {exc}")
            codigo = -1
        self.cola.put(("fin", codigo))

    def _tick(self) -> None:
        if self._cerrada or not self._cargando:
            return
        try:
            while True:
                elemento = self.cola.get_nowait()
                if isinstance(elemento, tuple):
                    self._mostrar(vista_previa_simulacion(self.nombre, self.lineas, elemento[1],
                                                          self.items))
                    return
                avance = parsear_progreso(elemento)
                nuevo = parsear_item(elemento)
                if avance:
                    self.progreso = avance
                elif nuevo:
                    self.items.append(nuevo)
                else:
                    self.lineas.append(elemento)
        except queue.Empty:
            pass
        except tk.TclError:
            return
        try:
            texto = f"Revisando… {formatear_duracion(time.time() - self.inicio)}"
            if self.progreso:
                hecho, total, que = self.progreso
                texto = f"Paso {hecho} de {total}" + (f" · {que}" if que else "") + \
                        f" · {formatear_duracion(time.time() - self.inicio)}"
            self.estado_carga.configure(text=texto)
            c = self.barra_carga
            c.delete("all")
            ancho, alto = max(c.winfo_width(), 2), int(c.cget("height"))
            if self.progreso:
                c.create_rectangle(0, 0, int(ancho * self.progreso[0] / self.progreso[1]), alto,
                                   fill=COLOR_ACENTO, outline="")
            else:
                largo = max(ancho // 4, 20)
                x = int(((time.time() * 0.8) % 1) * (ancho + largo)) - largo
                c.create_rectangle(max(x, 0), 0, min(x + largo, ancho), alto,
                                   fill=COLOR_ACENTO, outline="")
        except tk.TclError:
            return
        self.after(80, self._tick)

    def destroy(self) -> None:
        self._cerrada = True
        matar_proceso(self.proceso)
        super().destroy()


DESTINOS_JSON = os.path.join(rutas.PERSONAL, "destinos.json")
OPCIONES_DESTINO = rutas.dato("destinos_opciones.json")      # opciones ya consultadas a Webclass


def _leer_json(ruta: str, por_defecto):
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            dato = json.load(f)
        return dato if isinstance(dato, type(por_defecto)) else por_defecto
    except (OSError, ValueError):
        return por_defecto


def perfil_de_trabajo() -> dict:
    """El perfil del docente activo (cursos y unidades), como lo arma configurar.py."""
    return _leer_json(os.path.join(rutas.PERFILES, f"{PERFIL}.json"), {})


class VentanaDestinos(tk.Toplevel):
    """Editor de «a dónde se asigna cada unidad»: cambia solo las que se necesitan.

    Muestra todas las unidades de una vez (sin consultar a Webclass) con su
    destino actual. El docente marca únicamente las que quiere cambiar; solo
    para esas se piden a Webclass las opciones (una sola consulta, y quedan
    guardadas para la próxima). Guardar escribe lo cambiado en destinos.json;
    no se manda nada a Webclass.
    """

    ANCHO = 560

    def __init__(self, maestra):
        super().__init__(maestra)
        self.maestra = maestra
        self.title("A dónde asigno cada unidad")
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.perfil = perfil_de_trabajo()
        self.unidades = list(self.perfil.get("unidades", []))
        self.elegidos = _leer_json(DESTINOS_JSON, {})
        self.opciones = _leer_json(OPCIONES_DESTINO, {})        # {id_unidad: {opciones, hora}}
        self.proceso: subprocess.Popen | None = None
        self.cola: queue.Queue = queue.Queue()
        self.combos: dict[str, ttk.Combobox] = {}
        self.lista: ListaMarcable | None = None
        self.filtro = tk.StringVar()
        self.solo_cambiadas = False
        self._cerrada = False
        self._cargando = False
        self.progreso: tuple[int, int, str] | None = None
        self.inicio = time.time()
        familia = "Segoe UI"

        tk.Label(self, text="A dónde asigno cada unidad", bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=(familia, 13, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 2))
        self.subtitulo = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_TENUE,
                                  font=(familia, 9), anchor="w", justify="left",
                                  wraplength=self.ANCHO - 40)
        self.subtitulo.pack(fill="x", padx=18, pady=(0, 8))
        # Los controles se crean una sola vez (si no, escribir en el filtro perdería el foco).
        self.controles = tk.Frame(self, bg=COLOR_FONDO)
        tk.Label(self.controles, text="Filtrar:", bg=COLOR_FONDO, fg=COLOR_TENUE,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        self.entrada = tk.Entry(self.controles, textvariable=self.filtro, bg=COLOR_BOTON,
                                fg=COLOR_TEXTO, bd=0, font=("Segoe UI", 10),
                                insertbackground=COLOR_TEXTO, highlightthickness=1,
                                highlightbackground=COLOR_BOTON, highlightcolor=COLOR_ACENTO,
                                width=22)
        self.entrada.pack(side="left", ipady=4, padx=(0, 10))
        self.entrada.bind("<KeyRelease>", lambda _e: self._refrescar_lista())
        self.enlace_cambiadas = self._enlace(self.controles, "Solo las que cambié",
                                             self._alternar_cambiadas)
        self.enlace_cambiadas.pack(side="left", padx=(0, 10))
        self.contador = tk.Label(self.controles, text="", bg=COLOR_FONDO, fg=COLOR_TENUE,
                                 font=("Segoe UI", 9))
        self.contador.pack(side="right")
        self.cuerpo = tk.Frame(self, bg=COLOR_BOTON)
        self.cuerpo.pack(fill="x", padx=18)
        self.barra_carga = tk.Canvas(self, height=8, bg=COLOR_BOTON, bd=0, highlightthickness=0)
        self.aviso = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_TENUE, font=(familia, 9),
                              anchor="w", justify="left", wraplength=self.ANCHO - 40)
        self.aviso.pack(fill="x", padx=18, pady=(8, 0))
        self.pie = tk.Frame(self, bg=COLOR_FONDO)
        self.pie.pack(fill="x", padx=18, pady=(12, 16))
        self.bind("<Escape>", lambda _e: self.destroy())

        estilo = ttk.Style(self)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        estilo.configure("Barra.TCombobox", fieldbackground=COLOR_FONDO, background=COLOR_BOTON,
                         foreground=COLOR_TEXTO, arrowcolor=COLOR_ACENTO, bordercolor=COLOR_ACENTO,
                         lightcolor=COLOR_BOTON, darkcolor=COLOR_BOTON, padding=4)
        estilo.map("Barra.TCombobox", fieldbackground=[("readonly", COLOR_FONDO)],
                   foreground=[("readonly", COLOR_TEXTO)])
        self.option_add("*TCombobox*Listbox.background", COLOR_FONDO)
        self.option_add("*TCombobox*Listbox.foreground", COLOR_TEXTO)
        self.option_add("*TCombobox*Listbox.selectBackground", COLOR_ACENTO)
        self.option_add("*TCombobox*Listbox.selectForeground", COLOR_FONDO)

        if not self.unidades:
            self.subtitulo.configure(text="No encuentro unidades en tu perfil. Vuelve a correr "
                                          "configurar.py.")
            self._poner_botones([("Cerrar", self.destroy, True)])
        else:
            self._ver_lista()
        colocar_junto_a_la_barra(self, maestra)

    # ---------------------------------------------------------------- utilidades
    def _limpiar(self) -> None:
        for hijo in self.cuerpo.winfo_children():
            hijo.destroy()
        self.controles.pack_forget()
        self.barra_carga.pack_forget()
        self.lista = None
        self.combos = {}

    def _buscar_unidades(self) -> None:
        """Busca en Webclass unidades que el perfil no conoce y deja elegir cuáles incluir."""
        maestra = self.maestra
        previa = {"nombre": "Unidades nuevas", "icono": "🔎", "vista_previa": "unidades",
                  "destino": "asignar"}
        self.destroy()

        def guardar(claves, todas):
            archivo = escribir_seleccion(rutas.dato("selecciones"), claves or [])
            orden = comando_webclass("asignar", "--guardar-unidades", "--seleccion", archivo)
            threading.Thread(target=lambda: subprocess.run(
                orden, cwd=WEBCLASS, stdin=subprocess.DEVNULL, capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)), daemon=True).start()
        VistaPrevia(maestra, previa, guardar)

    def _poner_botones(self, botones: list[tuple[str, object, bool]]) -> None:
        for hijo in self.pie.winfo_children():
            hijo.destroy()
        self.boton_elegir = None
        for texto, accion, principal in reversed(botones):
            b = boton_texto(self.pie, texto, accion, principal)
            b.pack(side="right", padx=(8, 0))
            if accion == self._elegir_destino:
                self.boton_elegir = b

    def _enlace(self, padre, texto: str, accion) -> tk.Label:
        e = tk.Label(padre, text=texto, bg=COLOR_FONDO, fg=COLOR_ACENTO,
                     font=("Segoe UI", 9, "underline"), cursor="hand2", takefocus=True,
                     highlightthickness=1, highlightbackground=COLOR_FONDO,
                     highlightcolor=COLOR_TEXTO)
        e.bind("<Button-1>", lambda _e: accion())
        for tecla in ("<Return>", "<space>"):
            e.bind(tecla, lambda _e: (accion(), "break")[1])
        return e

    # ------------------------------------------------------------ vista 1: lista
    def _ver_lista(self, mantener: set[str] | None = None) -> None:
        self._limpiar()
        self.aviso.configure(text="")
        self.subtitulo.configure(
            text="Marca solo las unidades que quieres cambiar y pulsa «Elegir destino». "
                 "Las que no marques quedan como están.")
        self.controles.pack(fill="x", padx=18, pady=(0, 6), before=self.cuerpo)
        self.enlace_cambiadas.configure(
            text="Ver todas" if self.solo_cambiadas else "Solo las que cambié")
        filas = filas_de_destinos(self.unidades, self.elegidos, self.perfil.get("curso_ids"),
                                  self.filtro.get(), self.solo_cambiadas)
        self.lista = ListaMarcable(self.cuerpo, al_cambiar=self._al_cambiar, alto_max=330)
        self.lista.pack(fill="x", padx=2, pady=2)
        for f in filas:
            self.lista.agregar(f["clave"], f["titulo"], f["detalle"], f["grupo"],
                               marcado=bool(mantener and f["clave"] in mantener),
                               ancho_texto=self.ANCHO - 110)
        if not filas:
            tk.Label(self.cuerpo, text="Ninguna unidad coincide con el filtro.", bg=COLOR_BOTON,
                     fg=COLOR_TENUE, font=("Segoe UI", 10)).pack(padx=12, pady=14)
        self._poner_botones([("Elegir destino", self._elegir_destino, True),
                             ("Buscar unidades nuevas", self._buscar_unidades, False),
                             ("Cerrar", self.destroy, False)])
        self._al_cambiar(self.lista.marcadas(), len(filas))
        colocar_junto_a_la_barra(self, self.maestra)

    def _refrescar_lista(self) -> None:
        """Vuelve a armar la lista (por el filtro), sin perder lo ya marcado."""
        self._ver_lista(set(self.lista.marcadas()) if self.lista else None)

    def _alternar_cambiadas(self) -> None:
        self.solo_cambiadas = not self.solo_cambiadas
        self._refrescar_lista()

    def _al_cambiar(self, marcadas: list[str], total: int) -> None:
        self.contador.configure(text=f"{len(marcadas)} marcadas de {total}")
        b = self.boton_elegir
        if b is None:
            return
        n = len(marcadas)
        b.configure(text=f"  Elegir destino ({n})  " if n else "  Elegir destino  ",
                    bg=COLOR_ACENTO if n else COLOR_BOTON, fg=COLOR_FONDO if n else COLOR_SUAVE)

    # ------------------------------------------------- vista 2: opciones de cada una
    def _elegir_destino(self) -> None:
        if self.lista is None:
            return
        marcadas = self.lista.marcadas()
        if not marcadas:
            self.aviso.configure(text="Marca al menos una unidad para cambiarle el destino.",
                                 fg=COLOR_ERROR)
            return
        self.marcadas = marcadas
        faltan = [m for m in marcadas if not (self.opciones.get(m) or {}).get("opciones")]
        if faltan:
            self._consultar(faltan)
        else:
            self._ver_editor()

    def _consultar(self, ids: list[str]) -> None:
        """Pide a Webclass las opciones SOLO de las unidades que faltan (un inicio de sesión)."""
        self._limpiar()
        self._cargando = True
        self.progreso = None
        self.inicio = time.time()
        self.recibidas: list[dict] = []
        self.subtitulo.configure(
            text="Consultando a Webclass los destinos posibles (solo para las unidades que "
                 "marcaste). Si el servidor está lento puede tardar un par de minutos; "
                 "después quedan guardados.")
        self.barra_carga.pack(fill="x", padx=18, pady=(0, 8), before=self.cuerpo)
        self.estado_carga = tk.Label(self.cuerpo, text="", bg=COLOR_BOTON, fg=COLOR_TENUE,
                                     font=("Segoe UI", 10), anchor="w")
        self.estado_carga.pack(fill="x", padx=12, pady=12)
        self._poner_botones([("Volver", self._cancelar_consulta, False)])
        orden = comando_webclass("asignar", "--opciones-destino", ",".join(ids))
        threading.Thread(target=self._correr, args=(orden,), daemon=True).start()
        self.after(80, self._tick)

    def _correr(self, orden: list[str]) -> None:
        codigo: int | None = None
        try:
            proceso = subprocess.Popen(
                orden, cwd=WEBCLASS, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.proceso = proceso
            if self._cerrada:
                proceso.kill()
                return
            for linea in proceso.stdout:
                self.cola.put(linea.rstrip("\n"))
            proceso.wait()
            codigo = proceso.returncode
        except Exception as exc:  # noqa: BLE001
            registrar("no se pudieron consultar los destinos", traceback.format_exc())
            self.cola.put(f"Error: {exc}")
            codigo = -1
        self.cola.put(("fin", codigo))

    def _tick(self) -> None:
        if self._cerrada or not self._cargando:
            return
        lineas: list[str] = []
        try:
            while True:
                elemento = self.cola.get_nowait()
                if isinstance(elemento, tuple):
                    self._termino_consulta(elemento[1], lineas)
                    return
                avance = parsear_progreso(elemento)
                opcion = parsear_opciones(elemento)
                if avance:
                    self.progreso = avance
                elif opcion:
                    self.recibidas.append(opcion)
                else:
                    lineas.append(elemento)
        except queue.Empty:
            pass
        except tk.TclError:
            return
        try:
            texto = f"Consultando… {formatear_duracion(time.time() - self.inicio)}"
            if self.progreso:
                hecho, total, que = self.progreso
                texto = f"Unidad {min(hecho + 1, total)} de {total}" + \
                        f" · {formatear_duracion(time.time() - self.inicio)}"
            self.estado_carga.configure(text=texto)
            c = self.barra_carga
            c.delete("all")
            ancho, alto = max(c.winfo_width(), 2), int(c.cget("height"))
            if self.progreso:
                c.create_rectangle(0, 0, int(ancho * self.progreso[0] / self.progreso[1]), alto,
                                   fill=COLOR_ACENTO, outline="")
            else:
                largo = max(ancho // 4, 20)
                x = int(((time.time() * 0.8) % 1) * (ancho + largo)) - largo
                c.create_rectangle(max(x, 0), 0, min(x + largo, ancho), alto,
                                   fill=COLOR_ACENTO, outline="")
        except tk.TclError:
            return
        self.after(80, self._tick)

    def _termino_consulta(self, codigo: int | None, lineas: list[str]) -> None:
        self._cargando = False
        ahora = datetime.datetime.now().isoformat(timespec="seconds")
        errores = []
        for o in self.recibidas:
            if o["opciones"]:
                self.opciones[o["unidad"]] = {"opciones": o["opciones"], "hora": ahora}
            elif o["error"]:
                errores.append(f"{o['unidad']}: {o['error']}")
        try:
            escribir_atomico(OPCIONES_DESTINO, json.dumps(self.opciones, ensure_ascii=False))
        except OSError as exc:
            registrar("no se pudieron guardar las opciones de destino", str(exc))
        sin_opciones = [m for m in self.marcadas
                        if not (self.opciones.get(m) or {}).get("opciones")]
        if codigo not in (0, None) and not self.recibidas:
            self._ver_lista(set(self.marcadas))
            self.aviso.configure(
                text=(traducir_error(lineas) or "No pude consultar a Webclass.") +
                     " Puedes volver a intentarlo.", fg=COLOR_ERROR)
        elif sin_opciones and len(sin_opciones) == len(self.marcadas):
            self._ver_lista(set(self.marcadas))
            self.aviso.configure(text="Webclass no devolvió destinos para esas unidades"
                                      + (f" ({'; '.join(errores)})" if errores else "") + ".",
                                 fg=COLOR_ERROR)
        else:
            self._ver_editor(avisos=errores)

    def _cancelar_consulta(self) -> None:
        self._cargando = False
        matar_proceso(self.proceso)
        self._ver_lista(set(self.marcadas))

    def _ver_editor(self, avisos: list[str] | None = None) -> None:
        """Un desplegable por cada unidad marcada, con las opciones reales de Webclass."""
        self._limpiar()
        self.subtitulo.configure(text="Elige el nuevo destino de cada unidad marcada. "
                                      "Solo se guarda lo que cambies.")
        por_id = {str(u["id"]): u for u in self.unidades}
        curso_ids = self.perfil.get("curso_ids", {})
        DEFECTO = "↺  Volver al curso de la unidad (por defecto)"
        self.actuales: dict[str, tuple[str, list[dict], int]] = {}
        for unidad in self.marcadas:
            info = por_id.get(unidad)
            opciones = (self.opciones.get(unidad) or {}).get("opciones", [])
            if not info or not opciones:
                continue
            id_defecto = curso_ids.get(info.get("curso"))
            valores = [DEFECTO] + [o["nombre"] + (" (curso de la unidad)" if o["id"] == id_defecto
                                                  else "") for o in opciones]
            elegido = self.elegidos.get(unidad)
            if elegido:
                indice = next((i + 1 for i, o in enumerate(opciones) if o["id"] == elegido["id"]), 0)
            else:
                indice = next((i + 1 for i, o in enumerate(opciones) if o["id"] == id_defecto), 0)
            fila = tk.Frame(self.cuerpo, bg=COLOR_BOTON)
            fila.pack(fill="x", padx=12, pady=(8, 0))
            tk.Label(fila, text=f"{info.get('curso', '')} · {info.get('nombre', unidad)}",
                     bg=COLOR_BOTON, fg=COLOR_TEXTO, font=("Segoe UI", 10, "bold"), anchor="w",
                     justify="left", wraplength=self.ANCHO - 70).pack(fill="x")
            combo = ttk.Combobox(fila, values=valores, state="readonly",
                                 style="Barra.TCombobox", font=("Segoe UI", 10),
                                 width=max(len(v) for v in valores) + 2)
            combo.current(indice)
            combo.pack(fill="x", pady=(4, 0))
            self.combos[unidad] = combo
            self.actuales[unidad] = (DEFECTO, opciones, indice)
        tk.Frame(self.cuerpo, bg=COLOR_BOTON, height=10).pack()
        self.aviso.configure(text=("Sin opciones: " + "; ".join(avisos)) if avisos else "",
                             fg=COLOR_ALERTA_SUAVE)
        self._poner_botones([("Guardar", self._guardar, True),
                             ("Atrás", lambda: self._ver_lista(set(self.marcadas)), False),
                             ("Actualizar opciones", self._actualizar_opciones, False)])
        colocar_junto_a_la_barra(self, self.maestra)

    def _actualizar_opciones(self) -> None:
        for m in self.marcadas:
            self.opciones.pop(m, None)
        self._consultar(list(self.marcadas))

    def _guardar(self) -> None:
        """Escribe en destinos.json solo lo que cambió."""
        cambios: dict[str, dict | None] = {}
        id_defecto = {str(u["id"]): self.perfil.get("curso_ids", {}).get(u.get("curso"))
                      for u in self.unidades}
        for unidad, combo in self.combos.items():
            _defecto, opciones, indice_inicial = self.actuales[unidad]
            indice = combo.current()
            if indice == indice_inicial:
                continue                                         # no la tocó
            if indice == 0 or opciones[indice - 1]["id"] == id_defecto.get(unidad):
                if unidad in self.elegidos:
                    cambios[unidad] = None                       # vuelve al curso de la unidad
            else:
                cambios[unidad] = opciones[indice - 1]
        if not cambios:
            self._ver_lista()
            self.aviso.configure(text="No cambiaste nada: todo queda como estaba.",
                                 fg=COLOR_TENUE)
            return
        nuevos = aplicar_destinos(self.elegidos, cambios)
        try:
            escribir_atomico(DESTINOS_JSON, json.dumps(nuevos, ensure_ascii=False, indent=1))
        except OSError as exc:
            self.aviso.configure(text=f"No se pudo guardar: {exc}", fg=COLOR_ERROR)
            return
        self.elegidos = nuevos
        registrar(f"destinos guardados: {len(cambios)} unidad(es)")
        self._ver_lista()
        self.aviso.configure(
            text=f"✓ Guardado: {_plural_es(len(cambios), 'unidad', 'unidades')} actualizada"
                 f"{'s' if len(cambios) != 1 else ''}. Las demás quedaron igual.",
            fg=color_de_estado("completado"))

    def destroy(self) -> None:
        self._cerrada = True
        matar_proceso(self.proceso)
        super().destroy()


def _plural_es(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


class VentanaPeriodo(tk.Toplevel):
    """«¿Hasta cuándo miro hacia atrás?»: elige el período del libro pendiente.

    Con atajos (ayer, últimos 7 o 15 días, este mes) o desde una fecha. Al
    aceptar se abre la vista previa con lo pendiente de ese rango, agrupado por
    día y con casillas; recién al continuar se registra.
    """

    ANCHO = 440

    def __init__(self, maestra, herramienta: dict):
        super().__init__(maestra)
        self.maestra = maestra
        self.herramienta = herramienta
        self.title("Registrar libro pendiente")
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        familia = "Segoe UI"
        self.atajo = tk.StringVar(value="7")
        self.texto_fecha = tk.StringVar()

        cabecera = tk.Frame(self, bg=COLOR_FONDO)
        cabecera.pack(fill="x", padx=18, pady=(16, 2))
        tk.Label(cabecera, text=herramienta.get("icono", "⏪"), bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=("Segoe UI Emoji", 16)).pack(side="left", padx=(0, 8))
        tk.Label(cabecera, text="¿Hasta cuándo miro hacia atrás?", bg=COLOR_FONDO,
                 fg=COLOR_TEXTO, font=(familia, 13, "bold")).pack(side="left")
        tk.Label(self, text="Busco los bloques de esos días que tienen algo sin registrar. "
                            "Después eliges cuáles completar.",
                 bg=COLOR_FONDO, fg=COLOR_TENUE, font=(familia, 9), anchor="w", justify="left",
                 wraplength=self.ANCHO - 40).pack(fill="x", padx=18, pady=(0, 8))

        marco = tk.Frame(self, bg=COLOR_BOTON)
        marco.pack(fill="x", padx=18)
        for valor, texto in ATAJOS_ATRAS:
            tk.Radiobutton(marco, text=texto, value=valor, variable=self.atajo,
                           command=self._actualizar, bg=COLOR_BOTON, fg=COLOR_TEXTO,
                           selectcolor=COLOR_FONDO, activebackground=COLOR_BOTON,
                           activeforeground=COLOR_ACENTO, font=(familia, 10), anchor="w",
                           bd=0, highlightthickness=0).pack(fill="x", padx=14, pady=(6, 0))
        fila_fecha = tk.Frame(marco, bg=COLOR_BOTON)
        fila_fecha.pack(fill="x", padx=14, pady=(2, 10))
        tk.Label(fila_fecha, text="Fecha (día/mes/año):", bg=COLOR_BOTON, fg=COLOR_TENUE,
                 font=(familia, 9)).pack(side="left", padx=(24, 6))
        self.campo_fecha = tk.Entry(fila_fecha, textvariable=self.texto_fecha, bg=COLOR_FONDO,
                                    fg=COLOR_TEXTO, bd=0, font=(familia, 10), width=12,
                                    insertbackground=COLOR_TEXTO, highlightthickness=1,
                                    highlightbackground=COLOR_FONDO, highlightcolor=COLOR_ACENTO)
        self.campo_fecha.pack(side="left", ipady=3)
        self.campo_fecha.bind("<KeyRelease>", lambda _e: self._actualizar())
        self.campo_fecha.bind("<FocusIn>", lambda _e: (self.atajo.set("fecha"), self._actualizar()))
        self.campo_fecha.bind("<Return>", lambda _e: self._continuar())

        self.rango = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_TEXTO, font=(familia, 10, "bold"),
                              anchor="w", justify="left", wraplength=self.ANCHO - 40)
        self.rango.pack(fill="x", padx=18, pady=(10, 0))
        self.aviso = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_ERROR, font=(familia, 9),
                              anchor="w", justify="left", wraplength=self.ANCHO - 40)
        self.aviso.pack(fill="x", padx=18)
        pie = tk.Frame(self, bg=COLOR_FONDO)
        pie.pack(fill="x", padx=18, pady=(10, 16))
        self.boton = boton_texto(pie, "Ver lo pendiente", self._continuar, principal=True)
        self.boton.pack(side="right")
        boton_texto(pie, "Cancelar", self.destroy).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _e: self.destroy())
        self._actualizar()
        colocar_junto_a_la_barra(self, maestra)

    def _rango(self) -> tuple[datetime.date, datetime.date]:
        return rango_de_atajo(self.atajo.get(), datetime.date.today(), self.texto_fecha.get())

    def _actualizar(self) -> None:
        """Muestra el rango resultante (o por qué no sirve) mientras se elige."""
        try:
            desde, hasta = self._rango()
        except ValueError as exc:
            self.rango.configure(text="")
            self.aviso.configure(text=str(exc) if self.atajo.get() != "fecha" or self.texto_fecha.get()
                                 else "")
            return
        dias = len([d for d in (desde + datetime.timedelta(days=i)
                                for i in range((hasta - desde).days + 1)) if d.weekday() < 5])
        cuando = f"el {desde:%d/%m/%Y}" if desde == hasta else f"del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}"
        self.rango.configure(text=f"Miraré {cuando} ({dias} día{'s' if dias != 1 else ''} hábil"
                                  f"{'es' if dias != 1 else ''}).")
        self.aviso.configure(text="")

    def _continuar(self) -> None:
        try:
            desde, hasta = self._rango()
        except ValueError as exc:
            self.aviso.configure(text=str(exc))
            return
        maestra, base = self.maestra, self.herramienta
        previa = {**base, "tipo": "webclass", "vista_previa": "listar",
                  "destino": f"libro --desde {desde:%d/%m/%Y} --hasta {hasta:%d/%m/%Y}"}
        self.destroy()
        VistaPrevia(maestra, previa,
                    lambda claves, todas: abrir({**previa, "_confirmado": True,
                                                 "_seleccion": (claves, todas)}, maestra))


class VentanaObservacion(tk.Toplevel):
    """Registrar una observación a una o varias alumnas, con vista previa antes de guardar.

    Se elige el curso (se leen sus alumnas y asignaturas de Webclass, sin escribir
    nada), se marcan las alumnas (ninguna viene marcada), el tipo, la fecha y la
    descripción. «Ver vista previa» muestra una línea por alumna con casilla; solo al
    continuar se guarda, una observación por alumna.
    """

    ANCHO = 560
    TIPOS = (("Positiva", 1), ("Negativa", 2), ("Neutra", 3))

    def __init__(self, maestra, herramienta: dict):
        super().__init__(maestra)
        self.maestra, self.herramienta = maestra, herramienta
        self.title("Registrar observación")
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.cola: queue.Queue = queue.Queue()
        self.asignaturas: dict[str, str] = {}
        self.lista: ListaMarcable | None = None
        self._cerrada = False
        perfil = perfil_de_trabajo()
        familia = "Segoe UI"
        estilo = ttk.Style(self)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        estilo.configure("Barra.TCombobox", fieldbackground=COLOR_FONDO, background=COLOR_BOTON,
                         foreground=COLOR_TEXTO, arrowcolor=COLOR_ACENTO, bordercolor=COLOR_ACENTO,
                         lightcolor=COLOR_BOTON, darkcolor=COLOR_BOTON, padding=4)
        estilo.map("Barra.TCombobox", fieldbackground=[("readonly", COLOR_FONDO)],
                   foreground=[("readonly", COLOR_TEXTO)])
        self.option_add("*TCombobox*Listbox.background", COLOR_FONDO)
        self.option_add("*TCombobox*Listbox.foreground", COLOR_TEXTO)
        self.option_add("*TCombobox*Listbox.selectBackground", COLOR_ACENTO)
        self.option_add("*TCombobox*Listbox.selectForeground", COLOR_FONDO)
        tk.Label(self, text="Registrar observación", bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=(familia, 13, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 2))
        self.estado = tk.Label(self, text="Elige el curso para ver sus alumnas.", bg=COLOR_FONDO,
                               fg=COLOR_TENUE, font=(familia, 9), anchor="w", justify="left",
                               wraplength=self.ANCHO - 40)
        self.estado.pack(fill="x", padx=18, pady=(0, 6))
        fila = tk.Frame(self, bg=COLOR_FONDO)
        fila.pack(fill="x", padx=18)
        self.curso = ttk.Combobox(fila, values=list(perfil.get("curso_ids", {})), state="readonly",
                                  width=8, style="Barra.TCombobox", font=(familia, 10))
        self.curso.pack(side="left")
        self.curso.bind("<<ComboboxSelected>>", lambda _e: self._cargar())
        self.asignatura = ttk.Combobox(fila, values=[], state="readonly", width=34,
                                       style="Barra.TCombobox", font=(familia, 10))
        self.asignatura.pack(side="left", padx=(8, 0))
        self.cuerpo = tk.Frame(self, bg=COLOR_BOTON)
        self.cuerpo.pack(fill="x", padx=18, pady=(8, 0))
        fila2 = tk.Frame(self, bg=COLOR_FONDO)
        fila2.pack(fill="x", padx=18, pady=(8, 0))
        self.tipo = tk.IntVar(value=0)
        for texto, valor in self.TIPOS:
            tk.Radiobutton(fila2, text=texto, variable=self.tipo, value=valor, bg=COLOR_FONDO,
                           fg=COLOR_TEXTO, selectcolor=COLOR_BOTON, activebackground=COLOR_FONDO,
                           activeforeground=COLOR_TEXTO, font=(familia, 10)).pack(side="left")
        tk.Label(fila2, text="Fecha:", bg=COLOR_FONDO, fg=COLOR_TENUE,
                 font=(familia, 9)).pack(side="left", padx=(14, 4))
        self.fecha = tk.Entry(fila2, width=11, bg=COLOR_BOTON, fg=COLOR_TEXTO, bd=0,
                              insertbackground=COLOR_TEXTO, font=(familia, 10))
        self.fecha.insert(0, datetime.date.today().strftime("%d/%m/%Y"))
        self.fecha.pack(side="left", ipady=3)
        self.texto = tk.Text(self, height=4, wrap="word", bg=COLOR_BOTON, fg=COLOR_TEXTO, bd=0,
                             insertbackground=COLOR_TEXTO, font=(familia, 10), padx=8, pady=6)
        self.texto.pack(fill="x", padx=18, pady=(8, 0))
        self.familia = tk.BooleanVar(value=False)
        tk.Checkbutton(self, text="Que también la vean el alumno y el apoderado",
                       variable=self.familia, bg=COLOR_FONDO, fg=COLOR_TENUE, selectcolor=COLOR_BOTON,
                       activebackground=COLOR_FONDO, activeforeground=COLOR_TEXTO,
                       font=(familia, 9)).pack(anchor="w", padx=18, pady=(6, 0))
        self.aviso = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_ERROR, font=(familia, 9),
                              anchor="w", justify="left", wraplength=self.ANCHO - 40)
        self.aviso.pack(fill="x", padx=18, pady=(6, 0))
        pie = tk.Frame(self, bg=COLOR_FONDO)
        pie.pack(fill="x", padx=18, pady=(8, 16))
        boton_texto(pie, "Ver vista previa", self._continuar, principal=True).pack(side="right")
        boton_texto(pie, "Cancelar", self.destroy).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _e: self.destroy())
        colocar_junto_a_la_barra(self, maestra)

    def _cargar(self) -> None:
        """Lee las alumnas y asignaturas del curso (solo lectura)."""
        curso = self.curso.get()
        for hijo in self.cuerpo.winfo_children():
            hijo.destroy()
        self.lista = None
        self.estado.configure(text=f"Leyendo {curso} en Webclass…", fg=COLOR_TENUE)
        threading.Thread(target=self._leer, args=(curso,), daemon=True).start()
        self.after(150, self._esperar)

    def _leer(self, curso: str) -> None:
        items, error = [], ""
        try:
            proceso = subprocess.run(
                comando_webclass("observar", "--curso", curso, "--formulario"), cwd=WEBCLASS,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240,
                stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            items = [i for i in map(parsear_item, proceso.stdout.splitlines()) if i]
            if proceso.returncode and not items:
                ultima = (proceso.stderr or proceso.stdout).strip().splitlines()[-1:]
                error = (ultima[0] if ultima else "error")[:120]
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:120]
        self.cola.put((curso, items, error))

    def _esperar(self) -> None:
        if self._cerrada:
            return
        try:
            curso, items, error = self.cola.get_nowait()
        except queue.Empty:
            self.after(150, self._esperar)
            return
        if curso != self.curso.get():
            return
        if error or not items:
            self.estado.configure(text=f"No pude leer {curso}: {error or 'sin datos'}", fg=COLOR_ERROR)
            return
        asignaturas = [i for i in items if i["que"] == "asignatura"]
        self.asignaturas = {i["titulo"]: i["clave"] for i in asignaturas}
        self.asignatura.configure(values=list(self.asignaturas))
        self.asignatura.set(next((i["titulo"] for i in asignaturas if i["detalle"] == "sugerida"), ""))
        alumnas = [i for i in items if i["que"] == "alumna"]
        self.lista = ListaMarcable(self.cuerpo, alto_max=170)
        self.lista.pack(fill="x", padx=2, pady=2)
        for a in alumnas:
            self.lista.agregar(a["clave"], a["titulo"].split(" · ", 1)[-1], grupo=curso,
                               marcado=False, ancho_texto=self.ANCHO - 100)
        self.estado.configure(text=f"{len(alumnas)} alumnas en {curso}. Marca a quienes corresponde:",
                              fg=COLOR_TENUE)
        colocar_junto_a_la_barra(self, self.maestra)

    def _continuar(self) -> None:
        curso = self.curso.get()
        alumnas = self.lista.marcadas() if self.lista else []
        texto = self.texto.get("1.0", "end").strip()
        asignatura = self.asignaturas.get(self.asignatura.get(), "")
        problemas = problemas_de_observacion(curso, alumnas, self.tipo.get(), self.fecha.get(),
                                             texto, asignatura)
        if problemas:
            self.aviso.configure(text="Falta: " + "; ".join(problemas) + ".")
            return
        datos = {"curso": curso, "alumnas": alumnas, "tipo": self.tipo.get(),
                 "fecha": self.fecha.get().strip(), "texto": texto, "asignatura": asignatura,
                 "visible": "todos" if self.familia.get() else "equipo"}
        carpeta = rutas.dato("observaciones")
        os.makedirs(carpeta, exist_ok=True)
        archivo = os.path.join(carpeta, "observacion_pendiente.json")
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)
        previa = {**self.herramienta, "tipo": "webclass", "vista_previa": "simular",
                  "destino": f'observar --datos "{archivo}"', "confirmar": ""}
        maestra = self.maestra
        self.destroy()
        VistaPrevia(maestra, previa,
                    lambda claves, todas: abrir({**previa, "_confirmado": True,
                                                 "_seleccion": (claves, todas)}, maestra))

    def destroy(self) -> None:
        self._cerrada = True
        super().destroy()


class VentanaPlanificar(tk.Toplevel):
    """Planificaciones en bloque: clases vacías según el horario, importar una planilla o marcar OA/DUA.

    Cada opción termina en una vista previa con casillas (nada se escribe antes de continuar).
    """

    ANCHO = 580
    ACCIONES = (("esqueleto", "Crear clases vacías en los días que tengo clase"),
                ("importar", "Importar clases desde una planilla (Excel o CSV)"),
                ("marcar", "Marcar OA, habilidades y DUA en varias clases"))

    def __init__(self, maestra, herramienta: dict):
        super().__init__(maestra)
        self.maestra, self.herramienta = maestra, herramienta
        self.title("Planificar")
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.cola: queue.Queue = queue.Queue()
        self.lista: ListaMarcable | None = None
        self.planilla = ""
        self._cerrada = False
        perfil = perfil_de_trabajo()
        self.unidades = {f"{u['curso']} · {u['nombre'][:50]}": str(u["id"])
                         for u in perfil.get("unidades", [])}
        familia = "Segoe UI"
        estilo = ttk.Style(self)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        estilo.configure("Barra.TCombobox", fieldbackground=COLOR_FONDO, background=COLOR_BOTON,
                         foreground=COLOR_TEXTO, arrowcolor=COLOR_ACENTO, bordercolor=COLOR_ACENTO,
                         lightcolor=COLOR_BOTON, darkcolor=COLOR_BOTON, padding=4)
        estilo.map("Barra.TCombobox", fieldbackground=[("readonly", COLOR_FONDO)],
                   foreground=[("readonly", COLOR_TEXTO)])
        self.option_add("*TCombobox*Listbox.background", COLOR_FONDO)
        self.option_add("*TCombobox*Listbox.foreground", COLOR_TEXTO)
        self.option_add("*TCombobox*Listbox.selectBackground", COLOR_ACENTO)
        self.option_add("*TCombobox*Listbox.selectForeground", COLOR_FONDO)
        tk.Label(self, text="Planificar", bg=COLOR_FONDO, fg=COLOR_TEXTO, font=(familia, 13, "bold"),
                 anchor="w").pack(fill="x", padx=18, pady=(16, 2))
        tk.Label(self, text="La barra ordena y completa; el contenido de las clases lo escribes tú.",
                 bg=COLOR_FONDO, fg=COLOR_TENUE, font=(familia, 9), anchor="w").pack(fill="x", padx=18)
        self.unidad = ttk.Combobox(self, values=list(self.unidades), state="readonly", width=60,
                                   style="Barra.TCombobox", font=(familia, 10))
        self.unidad.pack(padx=18, pady=(10, 6), anchor="w")
        self.unidad.bind("<<ComboboxSelected>>", lambda _e: self._mostrar_accion())
        self.accion = tk.StringVar(value="esqueleto")
        for valor, texto in self.ACCIONES:
            tk.Radiobutton(self, text=texto, variable=self.accion, value=valor, bg=COLOR_FONDO,
                           fg=COLOR_TEXTO, selectcolor=COLOR_BOTON, activebackground=COLOR_FONDO,
                           activeforeground=COLOR_TEXTO, font=(familia, 10), anchor="w",
                           command=self._mostrar_accion).pack(fill="x", padx=18)
        self.panel = tk.Frame(self, bg=COLOR_FONDO)
        self.panel.pack(fill="x", padx=18, pady=(8, 0))
        self.aviso = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_ERROR, font=(familia, 9),
                              anchor="w", justify="left", wraplength=self.ANCHO - 40)
        self.aviso.pack(fill="x", padx=18, pady=(6, 0))
        pie = tk.Frame(self, bg=COLOR_FONDO)
        pie.pack(fill="x", padx=18, pady=(8, 16))
        boton_texto(pie, "Ver vista previa", self._continuar, principal=True).pack(side="right")
        boton_texto(pie, "Cancelar", self.destroy).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _e: self.destroy())
        self._mostrar_accion()
        colocar_junto_a_la_barra(self, maestra)

    # ------------------------------------------------------------- paneles
    def _campo(self, padre, etiqueta: str, valor: str = "", ancho: int = 12) -> tk.Entry:
        fila = tk.Frame(padre, bg=COLOR_FONDO)
        fila.pack(fill="x", pady=2)
        tk.Label(fila, text=etiqueta, bg=COLOR_FONDO, fg=COLOR_TENUE, font=("Segoe UI", 9),
                 width=10, anchor="w").pack(side="left")
        entrada = tk.Entry(fila, width=ancho, bg=COLOR_BOTON, fg=COLOR_TEXTO, bd=0,
                           insertbackground=COLOR_TEXTO, font=("Segoe UI", 10))
        entrada.insert(0, valor)
        entrada.pack(side="left", ipady=3)
        return entrada

    def _mostrar_accion(self) -> None:
        for hijo in self.panel.winfo_children():
            hijo.destroy()
        self.lista = None
        self.aviso.configure(text="")
        accion = self.accion.get()
        hoy = datetime.date.today()
        if accion == "esqueleto":
            self.desde = self._campo(self.panel, "Desde:", hoy.strftime("%d/%m/%Y"))
            self.hasta = self._campo(self.panel, "Hasta:",
                                     (hoy + datetime.timedelta(days=14)).strftime("%d/%m/%Y"))
        elif accion == "importar":
            fila = tk.Frame(self.panel, bg=COLOR_FONDO)
            fila.pack(fill="x")
            self.texto_planilla = tk.Label(fila, text="Ninguna planilla elegida", bg=COLOR_FONDO,
                                           fg=COLOR_TENUE, font=("Segoe UI", 9), anchor="w")
            self.texto_planilla.pack(side="left", fill="x", expand=True)
            boton_texto(fila, "Elegir…", self._elegir_planilla).pack(side="right")
            boton_texto(fila, "Plantilla", self._plantilla).pack(side="right", padx=(0, 6))
        else:
            tk.Label(self.panel, text="Marca los OA, habilidades y clases que quieres completar.",
                     bg=COLOR_FONDO, fg=COLOR_TENUE, font=("Segoe UI", 9), anchor="w").pack(fill="x")
            boton_texto(self.panel, "Cargar OA y clases de la unidad", self._cargar).pack(anchor="w", pady=4)
            self.cuerpo = tk.Frame(self.panel, bg=COLOR_BOTON)
            self.cuerpo.pack(fill="x")
            self.dua = tk.StringVar(value="habitual")
            fila = tk.Frame(self.panel, bg=COLOR_FONDO)
            fila.pack(fill="x", pady=(6, 0))
            tk.Label(fila, text="DUA:", bg=COLOR_FONDO, fg=COLOR_TENUE,
                     font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
            for texto, valor in (("Habitual", "habitual"), ("Con TIC", "tic"), ("No tocar", "ninguno")):
                tk.Radiobutton(fila, text=texto, variable=self.dua, value=valor, bg=COLOR_FONDO,
                               fg=COLOR_TEXTO, selectcolor=COLOR_BOTON, activebackground=COLOR_FONDO,
                               activeforeground=COLOR_TEXTO, font=("Segoe UI", 10)).pack(side="left")
        colocar_junto_a_la_barra(self, self.maestra)

    def _elegir_planilla(self) -> None:
        from tkinter import filedialog
        ruta = filedialog.askopenfilename(parent=self, title="Planilla de clases",
                                          filetypes=[("Planillas", "*.csv *.xlsx"), ("Todos", "*.*")])
        if ruta:
            self.planilla = ruta
            self.texto_planilla.configure(text=os.path.basename(ruta), fg=COLOR_TEXTO)

    def _plantilla(self) -> None:
        """Deja una planilla de ejemplo para rellenar y la muestra en su carpeta."""
        try:
            proceso = subprocess.run(
                comando_webclass("planificar", "--plantilla"), cwd=WEBCLASS, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=60, stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            ruta = next((l[7:].strip() for l in proceso.stdout.splitlines() if l.startswith("##RUTA ")), "")
            if ruta:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(ruta)])
                self.aviso.configure(text="Rellena la planilla, guárdala y elígela aquí.", fg=COLOR_TENUE)
            else:
                self.aviso.configure(text="No pude crear la plantilla.", fg=COLOR_ERROR)
        except Exception as exc:  # noqa: BLE001
            self.aviso.configure(text=f"No pude crear la plantilla: {exc}", fg=COLOR_ERROR)

    # ----------------------------------------------------- catálogo (marcar)
    def _id_unidad(self) -> str:
        return self.unidades.get(self.unidad.get(), "")

    def _cargar(self) -> None:
        if not self._id_unidad():
            self.aviso.configure(text="Elige primero la unidad.", fg=COLOR_ERROR)
            return
        self.aviso.configure(text="Leyendo la unidad en Webclass…", fg=COLOR_TENUE)
        unidad = self._id_unidad()
        threading.Thread(target=self._leer_catalogo, args=(unidad,), daemon=True).start()
        self.after(200, self._esperar)

    def _leer_catalogo(self, unidad: str) -> None:
        items, error = [], ""
        try:
            proceso = subprocess.run(
                comando_webclass("planificar", "--catalogo", "--unidad", unidad), cwd=WEBCLASS,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240,
                stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            items = [i for i in map(parsear_item, proceso.stdout.splitlines()) if i]
            if proceso.returncode and not items:
                ultima = (proceso.stderr or proceso.stdout).strip().splitlines()[-1:]
                error = (ultima[0] if ultima else "error")[:120]
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:120]
        self.cola.put((unidad, items, error))

    def _esperar(self) -> None:
        if self._cerrada:
            return
        try:
            unidad, items, error = self.cola.get_nowait()
        except queue.Empty:
            self.after(200, self._esperar)
            return
        if unidad != self._id_unidad() or self.accion.get() != "marcar":
            return
        if error or not items:
            self.aviso.configure(text=f"No pude leer la unidad: {error or 'sin datos'}", fg=COLOR_ERROR)
            return
        for hijo in self.cuerpo.winfo_children():
            hijo.destroy()
        self.lista = ListaMarcable(self.cuerpo, alto_max=190)
        self.lista.pack(fill="x", padx=2, pady=2)
        self.etiquetas = {}
        for i in items:
            self.etiquetas[i["clave"]] = i["detalle"] if i["que"] in ("oa", "habilidad") else ""
            self.lista.agregar(i["clave"], i["titulo"], i["detalle"] if i["que"] == "clase" else "",
                               grupo=i["grupo"], marcado=False, ancho_texto=self.ANCHO - 100)
        self.tipos = {i["clave"]: i["que"] for i in items}
        self.aviso.configure(text="", fg=COLOR_TENUE)
        colocar_junto_a_la_barra(self, self.maestra)

    # --------------------------------------------------------- continuar
    def _continuar(self) -> None:
        unidad, accion = self._id_unidad(), self.accion.get()
        if not unidad:
            self.aviso.configure(text="Elige la unidad.", fg=COLOR_ERROR)
            return
        base = f"planificar --unidad {unidad}"
        if accion == "esqueleto":
            desde, hasta = self.desde.get().strip(), self.hasta.get().strip()
            try:
                d1 = datetime.datetime.strptime(desde, "%d/%m/%Y")
                d2 = datetime.datetime.strptime(hasta, "%d/%m/%Y")
            except ValueError:
                self.aviso.configure(text="Las fechas deben ser DD/MM/AAAA.", fg=COLOR_ERROR)
                return
            if d2 < d1:
                self.aviso.configure(text="«Hasta» es anterior a «Desde».", fg=COLOR_ERROR)
                return
            destino = f"{base} --esqueleto --desde {desde} --hasta {hasta}"
        elif accion == "importar":
            if not self.planilla:
                self.aviso.configure(text="Elige la planilla.", fg=COLOR_ERROR)
                return
            destino = f'{base} --importar "{self.planilla}"'
        else:
            marcadas = self.lista.marcadas() if self.lista else []
            clases = [c for c in marcadas if self.tipos.get(c) == "clase"]
            oa = [self.etiquetas[c] for c in marcadas if self.tipos.get(c) == "oa"]
            hab = [self.etiquetas[c] for c in marcadas if self.tipos.get(c) == "habilidad"]
            if not clases:
                self.aviso.configure(text="Carga la unidad y marca al menos una clase.", fg=COLOR_ERROR)
                return
            if not (oa or hab) and self.dua.get() == "ninguno":
                self.aviso.configure(text="No hay nada que marcar: elige OA, habilidades o DUA.",
                                     fg=COLOR_ERROR)
                return
            destino = (f'{base} --marcar --clases {",".join(clases)} --oa "{";".join(oa)}" '
                       f'--hab "{";".join(hab)}" --dua {self.dua.get()}')
        previa = {**self.herramienta, "tipo": "webclass", "vista_previa": "simular",
                  "destino": destino, "confirmar": ""}
        maestra = self.maestra
        self.destroy()
        VistaPrevia(maestra, previa,
                    lambda claves, todas: abrir({**previa, "_confirmado": True,
                                                 "_seleccion": (claves, todas)}, maestra))

    def destroy(self) -> None:
        self._cerrada = True
        super().destroy()


class VentanaCorreo(tk.Toplevel):
    """Enviar guías al equipo PIE por correo (Gmail con contraseña de aplicación).

    La contraseña se guarda en el Administrador de credenciales de Windows, nunca en un
    archivo. Antes de enviar hay una vista previa con el destinatario y los archivos.
    """

    ANCHO = 560
    DESTINO_PIE = "impresionespiemtc@gmail.com"
    SERVICIO = "barra-correo"

    def __init__(self, maestra, herramienta: dict, archivos: list[str] | None = None):
        super().__init__(maestra)
        self.maestra, self.herramienta = maestra, herramienta
        self.title("Enviar al equipo PIE")
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.archivos: list[str] = list(archivos or [])
        self.asunto_manual = self.mensaje_manual = self.curso_manual = False
        self.perfil = perfil_de_trabajo()
        self.config_correo = self.perfil.get("correo") or {}
        familia = "Segoe UI"
        tk.Label(self, text="Enviar al equipo PIE", bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=(familia, 13, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 2))
        self.destino = self.config_correo.get("pie") or self.DESTINO_PIE
        self.estado = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_TENUE, font=(familia, 9),
                               anchor="w", justify="left", wraplength=self.ANCHO - 40)
        self.estado.pack(fill="x", padx=18)
        self.cuerpo = tk.Frame(self, bg=COLOR_FONDO)
        self.cuerpo.pack(fill="x", padx=18, pady=(8, 0))
        self.aviso = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_ERROR, font=(familia, 9),
                              anchor="w", justify="left", wraplength=self.ANCHO - 40)
        self.aviso.pack(fill="x", padx=18, pady=(6, 0))
        self.pie = tk.Frame(self, bg=COLOR_FONDO)
        self.pie.pack(fill="x", padx=18, pady=(8, 16))
        self.bind("<Escape>", lambda _e: self.destroy())
        if self._remitente() and self._clave():
            self._ver_envio()
        else:
            self._ver_configuracion()
        colocar_junto_a_la_barra(self, maestra)

    # ------------------------------------------------------------ credenciales
    def _remitente(self) -> str:
        return (self.config_correo.get("remitente") or "").strip()

    def _clave(self) -> str:
        try:
            import keyring
            return keyring.get_password(self.SERVICIO, self._remitente()) or ""
        except Exception:  # noqa: BLE001
            return ""

    def _limpiar(self) -> None:
        for marco in (self.cuerpo, self.pie):
            for hijo in marco.winfo_children():
                hijo.destroy()
        self.aviso.configure(text="")

    def _caja(self, etiqueta: str, valor: str = "", secreto: bool = False) -> tk.Entry:
        fila = tk.Frame(self.cuerpo, bg=COLOR_FONDO)
        fila.pack(fill="x", pady=2)
        tk.Label(fila, text=etiqueta, bg=COLOR_FONDO, fg=COLOR_TENUE, font=("Segoe UI", 9),
                 width=14, anchor="w").pack(side="left")
        entrada = tk.Entry(fila, bg=COLOR_BOTON, fg=COLOR_TEXTO, bd=0, insertbackground=COLOR_TEXTO,
                           font=("Segoe UI", 10), show="•" if secreto else "")
        entrada.insert(0, valor)
        entrada.pack(side="left", fill="x", expand=True, ipady=3)
        return entrada

    def _ver_configuracion(self) -> None:
        self._limpiar()
        self.estado.configure(
            text="Primero hay que configurar el correo desde el que se envía (Gmail). Necesitas una "
                 "contraseña de aplicación: en tu cuenta de Google, Seguridad > Verificación en dos "
                 "pasos > Contraseñas de aplicaciones. Es una clave de 16 letras, distinta de la "
                 "normal; se guarda solo en este computador y se puede revocar cuando quieras.")
        self.caja_correo = self._caja("Tu Gmail:", self._remitente())
        self.caja_clave = self._caja("Contraseña de app:", secreto=True)
        boton_texto(self.pie, "Guardar", self._guardar_config, principal=True).pack(side="right")
        boton_texto(self.pie, "Cancelar", self.destroy).pack(side="right", padx=(0, 8))

    def _guardar_config(self) -> None:
        correo = self.caja_correo.get().strip()
        clave = "".join(self.caja_clave.get().split())
        if correo.count("@") != 1 or " " in correo or "." not in correo.split("@")[-1]:
            self.aviso.configure(text="Ese correo no parece válido.")
            return
        if len(clave) < 12:
            self.aviso.configure(text="La contraseña de aplicación tiene 16 letras (sin espacios).")
            return
        try:
            import keyring
            keyring.set_password(self.SERVICIO, correo, clave)
            ruta = os.path.join(rutas.PERFILES, f"{PERFIL}.json")
            perfil = perfil_de_trabajo()
            perfil.setdefault("correo", {})["remitente"] = correo
            perfil["correo"].setdefault("pie", self.DESTINO_PIE)
            escribir_atomico(ruta, json.dumps(perfil, ensure_ascii=False, indent=1))
        except Exception as exc:  # noqa: BLE001
            registrar("no se pudo guardar el correo", traceback.format_exc())
            self.aviso.configure(text=f"No pude guardarlo: {exc}")
            return
        self.config_correo = {"remitente": correo, "pie": self.DESTINO_PIE}
        self.destino = self.DESTINO_PIE
        self._ver_envio()

    # -------------------------------------------------------------- envío
    def _ver_envio(self) -> None:
        self._limpiar()
        self.estado.configure(text=f"Se envía desde {self._remitente()} a {self.destino}.")
        fila = tk.Frame(self.cuerpo, bg=COLOR_FONDO)
        fila.pack(fill="x")
        self.texto_archivos = tk.Label(fila, text="Ningún archivo elegido", bg=COLOR_FONDO,
                                       fg=COLOR_TENUE, font=("Segoe UI", 9), anchor="w",
                                       justify="left", wraplength=self.ANCHO - 160)
        self.texto_archivos.pack(side="left", fill="x", expand=True)
        boton_texto(fila, "Elegir archivos…", self._elegir).pack(side="right")
        self.asunto_manual = self.mensaje_manual = self.curso_manual = False
        self.caja_curso = self._caja("Curso:")
        self.caja_curso.bind("<KeyRelease>", self._curso_escrito)
        self.caja_asunto = self._caja("Asunto:")
        self.caja_asunto.bind("<KeyRelease>", self._asunto_escrito)
        self.mensaje = tk.Text(self.cuerpo, height=6, wrap="word", bg=COLOR_BOTON, fg=COLOR_TEXTO,
                               bd=0, insertbackground=COLOR_TEXTO, font=("Segoe UI", 10), padx=8, pady=6)
        self.mensaje.pack(fill="x", pady=(6, 0))
        self.mensaje.bind("<KeyRelease>", self._mensaje_escrito)
        boton_texto(self.pie, "Ver vista previa", self._continuar, principal=True).pack(side="right")
        boton_texto(self.pie, "Cancelar", self.destroy).pack(side="right", padx=(0, 8))
        boton_texto(self.pie, "Cambiar cuenta", self._ver_configuracion).pack(side="left")
        boton_texto(self.pie, "Prueba", self._probar).pack(side="left", padx=(8, 0))
        if self.archivos:
            self._poner_archivos(self.archivos)
        colocar_junto_a_la_barra(self, self.maestra)

    def _elegir(self) -> None:
        from tkinter import filedialog
        rutas_elegidas = filedialog.askopenfilenames(parent=self, title="Guías a enviar")
        if rutas_elegidas:
            self._poner_archivos(list(rutas_elegidas))

    def _poner_archivos(self, archivos: list[str]) -> None:
        self.archivos = archivos
        nombres = [os.path.basename(r) for r in self.archivos]
        self.texto_archivos.configure(text="; ".join(nombres), fg=COLOR_TEXTO)
        if not self.curso_manual:                     # el curso se deduce de los nombres
            self.caja_curso.delete(0, "end")
            self.caja_curso.insert(0, cursos_en_nombres(nombres))
        self._rearmar()

    def agregar_archivos(self, nuevos: list[str]) -> None:
        """Suma archivos al mismo correo (por ejemplo, al arrastrar otro sobre la barra)."""
        self._poner_archivos(self.archivos + [n for n in nuevos if n not in self.archivos])

    def _asunto_escrito(self, _evento=None) -> None:
        self.asunto_manual = True            # lo que el docente escribe no se vuelve a pisar

    def _mensaje_escrito(self, _evento=None) -> None:
        self.mensaje_manual = True

    def _curso_escrito(self, _evento=None) -> None:
        self.curso_manual = True
        self._rearmar(solo_asunto=True)

    def _rearmar(self, solo_asunto: bool = False) -> None:
        """Rehace asunto y mensaje, salvo lo que el docente ya escribió a mano."""
        nombres = [os.path.basename(r) for r in self.archivos]
        if not self.asunto_manual:
            self.caja_asunto.delete(0, "end")
            self.caja_asunto.insert(0, asunto_de_correo(nombres, self.caja_curso.get()))
        if not solo_asunto and not self.mensaje_manual:
            docente = (self.perfil.get("nombre") or "").strip()
            self.mensaje.delete("1.0", "end")
            self.mensaje.insert("1.0", texto_de_correo(nombres, docente)[1])

    def _probar(self) -> None:
        """Envía un correo de prueba a tu propia dirección (no al equipo PIE)."""
        if not messagebox.askyesno("Barra Profe", f"Se enviará un correo de prueba a {self._remitente()}.\n\n¿Continuar?",
                                   parent=self):
            return
        orden = comando_webclass("correo", "--probar")

        def correr() -> None:
            try:
                p = subprocess.run(orden, cwd=WEBCLASS, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=120, stdin=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                salida = (p.stdout or p.stderr).strip().splitlines()
                texto = salida[-1] if salida else "sin respuesta"
                color = COLOR_TENUE if p.returncode == 0 else COLOR_ERROR
            except Exception as exc:  # noqa: BLE001
                texto, color = str(exc)[:120], COLOR_ERROR
            try:
                self.after(0, lambda: self.aviso.configure(text=texto, fg=color))
            except tk.TclError:
                pass
        threading.Thread(target=correr, daemon=True).start()
        self.aviso.configure(text="Enviando la prueba…", fg=COLOR_TENUE)

    def _continuar(self) -> None:
        asunto = self.caja_asunto.get().strip()
        mensaje = self.mensaje.get("1.0", "end").strip()
        if not self.archivos:
            self.aviso.configure(text="Elige al menos un archivo.", fg=COLOR_ERROR)
            return
        if not asunto:
            self.aviso.configure(text="Escribe el asunto.", fg=COLOR_ERROR)
            return
        carpeta = rutas.dato("correo")
        os.makedirs(carpeta, exist_ok=True)
        archivo = os.path.join(carpeta, "correo_pendiente.json")
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump({"archivos": self.archivos, "asunto": asunto, "mensaje": mensaje}, f,
                      ensure_ascii=False)
        previa = {**self.herramienta, "tipo": "webclass", "vista_previa": "simular",
                  "destino": f'correo --datos "{archivo}"', "confirmar": ""}
        maestra = self.maestra
        self.destroy()
        VistaPrevia(maestra, previa,
                    lambda claves, todas: abrir({**previa, "_confirmado": True,
                                                 "_seleccion": (claves, todas)}, maestra))


class VentanaMensajes(tk.Toplevel):
    """Mensajes internos entre las barras del equipo (por la red del colegio, sin internet).

    Sin clave de grupo muestra cómo configurarla; con clave, el historial y un cuadro para
    escribir. Lo que no se pudo entregar queda «pendiente» y sale apenas el otro se conecte.
    """

    ANCHO = 540

    def __init__(self, maestra, herramienta: dict | None = None):
        super().__init__(maestra)
        self.maestra = maestra
        self.title("Mensajes del equipo")
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self._cerrada = False
        self.errores: queue.Queue = queue.Queue()
        familia = "Segoe UI"
        estilo = ttk.Style(self)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        estilo.configure("Barra.TCombobox", fieldbackground=COLOR_FONDO, background=COLOR_BOTON,
                         foreground=COLOR_TEXTO, arrowcolor=COLOR_ACENTO, bordercolor=COLOR_ACENTO,
                         lightcolor=COLOR_BOTON, darkcolor=COLOR_BOTON, padding=4)
        estilo.map("Barra.TCombobox", fieldbackground=[("readonly", COLOR_FONDO)],
                   foreground=[("readonly", COLOR_TEXTO)])
        self.after(300, self._sondear)
        tk.Label(self, text="Mensajes del equipo", bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=(familia, 13, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 2))
        self.estado = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_TENUE, font=(familia, 9),
                               anchor="w", justify="left", wraplength=self.ANCHO - 40)
        self.estado.pack(fill="x", padx=18)
        self.cuerpo = tk.Frame(self, bg=COLOR_FONDO)
        self.cuerpo.pack(fill="x", padx=18, pady=(8, 0))
        self.aviso = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_ERROR, font=(familia, 9),
                              anchor="w", justify="left", wraplength=self.ANCHO - 40)
        self.aviso.pack(fill="x", padx=18, pady=(6, 0))
        self.pie = tk.Frame(self, bg=COLOR_FONDO)
        self.pie.pack(fill="x", padx=18, pady=(8, 16))
        self.bind("<Escape>", lambda _e: self.destroy())
        self._elegir_vista()
        colocar_junto_a_la_barra(self, maestra)

    def _elegir_vista(self) -> None:
        for marco in (self.cuerpo, self.pie):
            for hijo in marco.winfo_children():
                hijo.destroy()
        self.aviso.configure(text="")
        if getattr(self.maestra, "mensajeria", None) is None:
            self._ver_clave()
        else:
            self._ver_chat()

    # ---------------------------------------------------------- clave del grupo
    def _ver_clave(self) -> None:
        self.estado.configure(
            text="Para hablar entre barras hace falta la clave del grupo: una sola para todo el "
                 "equipo. Quien administra la crea (botón «Crear nueva»), la copia y se la entrega a "
                 "cada persona por un canal privado; los demás solo la pegan aquí. Sin la clave nadie "
                 "puede leer ni escribir mensajes.")
        fila = tk.Frame(self.cuerpo, bg=COLOR_FONDO)
        fila.pack(fill="x")
        self.caja_clave = tk.Entry(fila, bg=COLOR_BOTON, fg=COLOR_TEXTO, bd=0, insertbackground=COLOR_TEXTO,
                                   font=("Consolas", 9))
        self.caja_clave.pack(side="left", fill="x", expand=True, ipady=4)
        boton_texto(fila, "Crear nueva", self._crear_clave).pack(side="right", padx=(6, 0))
        boton_texto(self.pie, "Guardar clave", self._guardar_clave, principal=True).pack(side="right")
        boton_texto(self.pie, "Cerrar", self.destroy).pack(side="right", padx=(0, 8))
        if not self.maestra.mensajeria_disponible:
            self.aviso.configure(text="Falta instalar la librería de cifrado: pip install cryptography")

    def _crear_clave(self) -> None:
        import mensajeria_red
        self.caja_clave.delete(0, "end")
        self.caja_clave.insert(0, mensajeria_red.generar_clave())
        self.caja_clave.select_range(0, "end")
        self.clipboard_clear()
        self.clipboard_append(self.caja_clave.get())
        self.aviso.configure(text="Clave nueva creada y copiada. Guárdala y entrégala al equipo.",
                             fg=COLOR_TENUE)

    def _guardar_clave(self) -> None:
        clave = self.caja_clave.get().strip()
        try:
            import mensajeria_red
            valida = mensajeria_red.clave_valida(clave)
        except ImportError:
            valida = False
        if not valida:
            self.aviso.configure(text="Esa clave no es válida: debe ser la que creó quien administra.",
                                 fg=COLOR_ERROR)
            return
        try:
            guardar_clave_mensajeria(clave)
        except Exception as exc:  # noqa: BLE001
            registrar("no se pudo guardar la clave de mensajería", traceback.format_exc())
            self.aviso.configure(text=f"No pude guardarla: {exc}", fg=COLOR_ERROR)
            return
        self.maestra.reiniciar_mensajeria()
        self._elegir_vista()

    # ------------------------------------------------------------------ chat
    def _ver_chat(self) -> None:
        nodo = self.maestra.mensajeria
        familia = "Segoe UI"
        marco = tk.Frame(self.cuerpo, bg=COLOR_BOTON)
        marco.pack(fill="x")
        self.texto = tk.Text(marco, height=12, wrap="word", bg=COLOR_BOTON, fg=COLOR_TEXTO, bd=0,
                             font=(familia, 10), padx=8, pady=6, state="disabled", cursor="arrow")
        barra = tk.Scrollbar(marco, command=self.texto.yview)
        self.texto.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.texto.pack(side="left", fill="x", expand=True)
        self.texto.tag_configure("yo", foreground=COLOR_ACENTO)
        self.texto.tag_configure("hora", foreground=COLOR_TENUE)
        self.texto.tag_configure("pendiente", foreground=COLOR_ALERTA)
        fila = tk.Frame(self.cuerpo, bg=COLOR_FONDO)
        fila.pack(fill="x", pady=(8, 0))
        tk.Label(fila, text="Para:", bg=COLOR_FONDO, fg=COLOR_TENUE, font=(familia, 9)).pack(side="left")
        self.destino = ttk.Combobox(fila, state="readonly", width=24, style="Barra.TCombobox",
                                    font=(familia, 10))
        self.destino.pack(side="left", padx=(6, 0))
        self.entrada = tk.Entry(self.cuerpo, bg=COLOR_BOTON, fg=COLOR_TEXTO, bd=0,
                                insertbackground=COLOR_TEXTO, font=(familia, 10))
        self.entrada.pack(fill="x", pady=(6, 0), ipady=5)
        self.entrada.bind("<Return>", lambda _e: self._enviar())
        boton_texto(self.pie, "Enviar", self._enviar, principal=True).pack(side="right")
        boton_texto(self.pie, "Cerrar", self.destroy).pack(side="right", padx=(0, 8))
        boton_texto(self.pie, "Cambiar clave", lambda: (self.maestra.detener_mensajeria(),
                                                       self._elegir_vista())).pack(side="left")
        self._refrescar()
        nodo.marcar_leidos()
        self.maestra.actualizar_mensajes()
        self.entrada.focus_set()

    def _refrescar(self) -> None:
        if self._cerrada:
            return
        nodo = getattr(self.maestra, "mensajeria", None)
        if nodo is None or not hasattr(self, "texto"):
            return
        try:
            en_linea = nodo.en_linea()
            otros = [n for n in nodo.conocidos() if n != nodo.nombre]
            opciones = ["Todos"] + [f"{n}{' ●' if n in en_linea else ''}" for n in otros]
            if tuple(opciones) != tuple(self.destino.cget("values")):
                actual = self.destino.get() or "Todos"
                self.destino.configure(values=opciones)
                self.destino.set(actual if actual in opciones else "Todos")
            self.estado.configure(
                text=(f"Conectada como {nodo.nombre}. En línea: {', '.join(en_linea) or 'nadie por ahora'}."
                      + (f" Pendientes de entregar: {nodo.pendientes()}." if nodo.pendientes() else "")))
            self.texto.configure(state="normal")
            self.texto.delete("1.0", "end")
            for m in sorted(nodo.mensajes(), key=lambda x: x["ts"])[-80:]:
                hora = datetime.datetime.fromtimestamp(m["ts"]).strftime("%d/%m %H:%M")
                if m.get("entrante"):
                    self.texto.insert("end", f"{hora}  ", "hora")
                    self.texto.insert("end", f"{m['de']}" + (" (a todos)" if m["para"] == "*" else "") + ": ")
                    self.texto.insert("end", m["texto"] + "\n")
                else:
                    faltan = [d for d in m.get("destinatarios", []) if d not in m.get("entregado", [])]
                    self.texto.insert("end", f"{hora}  ", "hora")
                    self.texto.insert("end", "Tú → " + ("todos" if m["para"] == "*" else m["para"]) + ": ", "yo")
                    self.texto.insert("end", m["texto"])
                    if faltan:
                        self.texto.insert("end", f"  ⏳ pendiente ({', '.join(faltan)})", "pendiente")
                    else:
                        self.texto.insert("end", "  ✓")
                    self.texto.insert("end", "\n")
            self.texto.configure(state="disabled")
            self.texto.see("end")
            nodo.marcar_leidos()
            self.maestra.actualizar_mensajes()
        except tk.TclError:
            return
        self.after(2000, self._refrescar)

    def _enviar(self) -> None:
        nodo = self.maestra.mensajeria
        texto = self.entrada.get().strip()
        if not texto:
            return
        elegido = (self.destino.get() or "Todos").replace(" ●", "")
        para = "*" if elegido == "Todos" else elegido
        self.entrada.delete(0, "end")

        def trabajo() -> None:
            try:
                nodo.enviar(texto, para)
                error = ""
            except ValueError as exc:
                error = str(exc)
            except Exception as exc:  # noqa: BLE001
                registrar("no se pudo enviar el mensaje", traceback.format_exc())
                error = f"No se pudo enviar: {exc}"
            self.errores.put(error)          # el hilo no toca Tk: lo recoge _sondear
        threading.Thread(target=trabajo, daemon=True).start()

    def _sondear(self) -> None:
        """Pasa a pantalla lo que dejó el hilo de envío (en el hilo principal)."""
        if self._cerrada:
            return
        try:
            while True:
                self.aviso.configure(text=self.errores.get_nowait(), fg=COLOR_ERROR)
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self.after(300, self._sondear)

    def destroy(self) -> None:
        self._cerrada = True
        super().destroy()


class VentanaElegirClase(tk.Toplevel):
    """Elegir a mano la clase de la planificación para los bloques que quedaron pendientes.

    Aparece después de una corrida en la que a algún bloque no se le encontró la
    clase de ese día (o había varias). Muestra, para cada uno, las clases más
    cercanas por fecha; lo que se deje sin elegir no se toca. Al aceptar se
    vuelve a correr la herramienta solo para esos bloques, con la clase elegida.
    """

    ANCHO = 600

    def __init__(self, consola):
        super().__init__(consola.maestra)
        self.consola = consola
        self.title("Elegir la clase")
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        familia = "Segoe UI"
        estilo = ttk.Style(self)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        estilo.configure("Barra.TCombobox", fieldbackground=COLOR_FONDO, background=COLOR_BOTON,
                         foreground=COLOR_TEXTO, arrowcolor=COLOR_ACENTO, bordercolor=COLOR_ACENTO,
                         lightcolor=COLOR_BOTON, darkcolor=COLOR_BOTON, padding=4)
        estilo.map("Barra.TCombobox", fieldbackground=[("readonly", COLOR_FONDO)],
                   foreground=[("readonly", COLOR_TEXTO)])
        self.option_add("*TCombobox*Listbox.background", COLOR_FONDO)
        self.option_add("*TCombobox*Listbox.foreground", COLOR_TEXTO)
        self.option_add("*TCombobox*Listbox.selectBackground", COLOR_ACENTO)
        self.option_add("*TCombobox*Listbox.selectForeground", COLOR_FONDO)
        self.pendientes = [it for it in agrupar_items(consola.items)["no_pude"] if it.get("opciones")]
        tk.Label(self, text="Elige la clase de cada bloque", bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=(familia, 13, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 2))
        tk.Label(self, text="Estas son las clases de tu planificación más cercanas a esa fecha. "
                            "Lo que dejes en «no declarar» no se toca.",
                 bg=COLOR_FONDO, fg=COLOR_TENUE, font=(familia, 9), anchor="w", justify="left",
                 wraplength=self.ANCHO - 40).pack(fill="x", padx=18, pady=(0, 8))
        self.combos: dict[str, ttk.Combobox] = {}
        cuerpo = tk.Frame(self, bg=COLOR_BOTON)
        cuerpo.pack(fill="x", padx=18)
        for it in self.pendientes:
            fila = tk.Frame(cuerpo, bg=COLOR_BOTON)
            fila.pack(fill="x", padx=12, pady=(8, 0))
            tk.Label(fila, text=it["titulo"], bg=COLOR_BOTON, fg=COLOR_TEXTO,
                     font=(familia, 10, "bold"), anchor="w", justify="left",
                     wraplength=self.ANCHO - 70).pack(fill="x")
            que = explicar_motivo(it["motivo"] or it["detalle"])["que"]
            tk.Label(fila, text=que, bg=COLOR_BOTON, fg=COLOR_TENUE, font=(familia, 9),
                     anchor="w", justify="left", wraplength=self.ANCHO - 70).pack(fill="x")
            valores = ["— no declarar este bloque —"] + [o["texto"] for o in it["opciones"]]
            combo = ttk.Combobox(fila, values=valores, state="readonly", style="Barra.TCombobox",
                                 font=(familia, 10), width=max(len(v) for v in valores) + 2)
            combo.current(0)
            combo.pack(fill="x", pady=(4, 0))
            self.combos[it["clave"]] = combo
        tk.Frame(cuerpo, bg=COLOR_BOTON, height=10).pack()
        self.aviso = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_ERROR, font=(familia, 9),
                              anchor="w")
        self.aviso.pack(fill="x", padx=18, pady=(6, 0))
        pie = tk.Frame(self, bg=COLOR_FONDO)
        pie.pack(fill="x", padx=18, pady=(10, 16))
        boton_texto(pie, "Declarar con la clase elegida", self._declarar, principal=True).pack(side="right")
        boton_texto(pie, "Cancelar", self.destroy).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _e: self.destroy())
        colocar_junto_a_la_barra(self, consola.maestra)

    def _declarar(self) -> None:
        elecciones: dict[str, str] = {}
        for it in self.pendientes:
            indice = self.combos[it["clave"]].current()
            if indice > 0:
                elecciones[it["clave"]] = it["opciones"][indice - 1]["id"]
        if not elecciones:
            self.aviso.configure(text="No elegiste ninguna clase: elige al menos una o cancela.")
            return
        consola = self.consola
        comando = comando_con_seleccion(consola.comando, list(elecciones), rutas.dato("selecciones"),
                                        elecciones)
        maestra, titulo, carpeta, icono = consola.maestra, consola.titulo, consola.carpeta, consola.icono
        self.destroy()
        Consola(maestra, f"{titulo} · clase elegida", comando, carpeta, icono)


class VentanaTickets(tk.Toplevel):
    """Elegir con tickets (casillas) uno o varios períodos antes de ejecutar un botón.

    `selector: "meses"` (Asignar lo pendiente): los meses del año escolar, para
    asignar las clases pendientes solo de los que se marquen. `selector:
    "periodos"` (Diagnóstico del libro): Hoy, Ayer, Esta semana, Semana anterior,
    Este mes, Mes anterior, Todo el año o una fecha escrita. Se pueden marcar
    varios a la vez. El texto que resulta reemplaza a `{valor}` en el destino.
    """

    ANCHO = 470

    def __init__(self, maestra, herramienta: dict):
        super().__init__(maestra)
        self.maestra = maestra
        self.herramienta = herramienta
        self.selector = herramienta.get("selector", "periodos")
        self.hoy = datetime.date.today()
        self.title(herramienta.get("nombre", "Elegir período"))
        self.configure(bg=COLOR_FONDO)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        familia = "Segoe UI"

        if self.selector == "meses":
            titulo = "¿Qué meses reviso?"
            ayuda = ("Marca los meses de los que quieres asignar las clases pendientes. "
                     "Después verás las clases para elegir cuáles.")
            meses = meses_escolares(self.hoy)
            opciones = [(m["clave"], m["texto"], "") for m in meses]
            marcadas = {m["clave"] for m in meses[:2]}          # este mes y el anterior, como antes
            boton = "Ver lo pendiente"
        else:
            titulo = "¿Qué días reviso?"
            ayuda = ("Marca uno o varios períodos. Es de solo lectura: explica por qué cada "
                     "bloque se podría o no registrar, sin escribir nada.")
            opciones = [(p["clave"], p["texto"], p["detalle"]) for p in periodos_de_revision(self.hoy)]
            marcadas = {"ayer"}
            boton = "Diagnosticar"

        cabecera = tk.Frame(self, bg=COLOR_FONDO)
        cabecera.pack(fill="x", padx=18, pady=(16, 2))
        if herramienta.get("icono"):
            tk.Label(cabecera, text=herramienta["icono"], bg=COLOR_FONDO, fg=COLOR_TEXTO,
                     font=("Segoe UI Emoji", 16)).pack(side="left", padx=(0, 8))
        tk.Label(cabecera, text=titulo, bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=(familia, 13, "bold")).pack(side="left")
        tk.Label(self, text=ayuda, bg=COLOR_FONDO, fg=COLOR_TENUE, font=(familia, 9),
                 anchor="w", justify="left", wraplength=self.ANCHO - 40).pack(fill="x", padx=18,
                                                                              pady=(0, 8))
        controles = tk.Frame(self, bg=COLOR_FONDO)
        controles.pack(fill="x", padx=18, pady=(0, 6))
        self.contador = tk.Label(controles, text="", bg=COLOR_FONDO, fg=COLOR_TENUE,
                                 font=(familia, 9))
        self.contador.pack(side="right")
        for texto, valor in (("Seleccionar todo", True), ("Ninguno", False)):
            enlace = tk.Label(controles, text=texto, bg=COLOR_FONDO, fg=COLOR_ACENTO,
                              font=(familia, 9, "underline"), cursor="hand2", takefocus=True,
                              highlightthickness=1, highlightbackground=COLOR_FONDO,
                              highlightcolor=COLOR_TEXTO)
            enlace.pack(side="left", padx=(0, 14))
            enlace.bind("<Button-1>", lambda _e, v=valor: self.lista.marcar_todo(v))
            for tecla in ("<Return>", "<space>"):
                enlace.bind(tecla, lambda _e, v=valor: (self.lista.marcar_todo(v), "break")[1])

        marco = tk.Frame(self, bg=COLOR_BOTON)
        marco.pack(fill="x", padx=18)
        self.lista = ListaMarcable(marco, al_cambiar=lambda *_a: self._actualizar(), alto_max=300)
        self.lista.pack(fill="x", padx=2, pady=2)
        for clave, texto, detalle in opciones:
            self.lista.agregar(clave, texto, detalle, marcado=clave in marcadas,
                               ancho_texto=self.ANCHO - 100)

        self.texto_fecha = tk.StringVar()
        self.campo_fecha = None
        if self.selector != "meses":
            fila = tk.Frame(self, bg=COLOR_FONDO)
            fila.pack(fill="x", padx=18, pady=(8, 0))
            tk.Label(fila, text="Además, este día (día/mes/año):", bg=COLOR_FONDO, fg=COLOR_TENUE,
                     font=(familia, 9)).pack(side="left", padx=(0, 6))
            self.campo_fecha = tk.Entry(fila, textvariable=self.texto_fecha, bg=COLOR_BOTON,
                                        fg=COLOR_TEXTO, bd=0, font=(familia, 10), width=12,
                                        insertbackground=COLOR_TEXTO, highlightthickness=1,
                                        highlightbackground=COLOR_BOTON,
                                        highlightcolor=COLOR_ACENTO)
            self.campo_fecha.pack(side="left", ipady=3)
            self.campo_fecha.bind("<KeyRelease>", lambda _e: self._actualizar())
            self.campo_fecha.bind("<Return>", lambda _e: self._aceptar())

        self.resumen = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_TEXTO,
                                font=(familia, 10, "bold"), anchor="w", justify="left",
                                wraplength=self.ANCHO - 40)
        self.resumen.pack(fill="x", padx=18, pady=(10, 0))
        self.aviso = tk.Label(self, text="", bg=COLOR_FONDO, fg=COLOR_ERROR, font=(familia, 9),
                              anchor="w", justify="left", wraplength=self.ANCHO - 40)
        self.aviso.pack(fill="x", padx=18)
        pie = tk.Frame(self, bg=COLOR_FONDO)
        pie.pack(fill="x", padx=18, pady=(10, 16))
        boton_texto(pie, boton, self._aceptar, principal=True).pack(side="right")
        boton_texto(pie, "Cancelar", self.destroy).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _e: self.destroy())
        self._actualizar()
        colocar_junto_a_la_barra(self, maestra)

    # ------------------------------------------------------------------ cálculo
    def _valor(self) -> tuple[str, str]:
        """(valor para el destino, frase que lo resume). ValueError si no sirve."""
        marcadas = self.lista.marcadas()
        if self.selector == "meses":
            if not marcadas:
                raise ValueError("Marca al menos un mes.")
            ordenadas = sorted(marcadas, key=lambda c: (c[3:], c[:2]))          # cronológico
            textos = {m["clave"]: m["texto"].split(" (")[0] for m in meses_escolares(self.hoy)}
            return ",".join(ordenadas), "Buscaré clases pendientes de: " + ", ".join(
                textos[c] for c in ordenadas) + "."
        dias = dias_de_periodos(marcadas, self.hoy, self.texto_fecha.get())
        return formatear_fechas(dias), (
            f"Revisaré {len(dias)} día{'s' if len(dias) != 1 else ''} hábil"
            f"{'es' if len(dias) != 1 else ''} ({dias[0]:%d/%m/%Y}"
            + (f" al {dias[-1]:%d/%m/%Y})." if dias[0] != dias[-1] else ")."))

    def _actualizar(self) -> None:
        marcadas = self.lista.marcadas()
        self.contador.configure(text=f"{len(marcadas)} de {len(self.lista.todas())} marcados")
        try:
            _valor, frase = self._valor()
        except ValueError as exc:
            self.resumen.configure(text="")
            sin_nada = not marcadas and not (self.campo_fecha and self.texto_fecha.get().strip())
            self.aviso.configure(text="" if sin_nada else str(exc))
            return
        self.resumen.configure(text=frase)
        self.aviso.configure(text="")

    def _aceptar(self) -> None:
        try:
            valor, _frase = self._valor()
        except ValueError as exc:
            self.aviso.configure(text=str(exc))
            return
        base = self.herramienta
        nuevo = {**base, "tipo": "webclass",
                 "destino": base.get("destino", "").replace("{valor}", valor)}
        maestra = self.maestra
        self.destroy()
        if base.get("vista_previa"):
            VistaPrevia(maestra, nuevo,
                        lambda claves, todas: abrir({**nuevo, "_confirmado": True,
                                                     "_seleccion": (claves, todas)}, maestra))
        else:
            abrir({**nuevo, "_confirmado": True}, maestra)


class Tour(tk.Toplevel):
    """Recorrido de bienvenida: resalta cada parte de la barra y la explica."""

    def __init__(self, barra):
        super().__init__(barra)
        self.barra = barra
        self.paso = 0
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=COLOR_ACENTO)               # el borde de color
        familia = barra.fuente.cget("family")
        ancho = int(310 * barra.escala)
        interior = tk.Frame(self, bg=COLOR_BOTON)
        interior.pack(padx=2, pady=2, fill="both", expand=True)
        self.etiqueta_paso = tk.Label(interior, text="", bg=COLOR_BOTON, fg=COLOR_ACENTO,
                                      font=(familia, 9, "bold"), anchor="w")
        self.etiqueta_paso.pack(fill="x", padx=14, pady=(12, 0))
        self.titulo = tk.Label(interior, text="", bg=COLOR_BOTON, fg=COLOR_TEXTO,
                               font=(familia, 13, "bold"), anchor="w")
        self.titulo.pack(fill="x", padx=14)
        self.texto = tk.Label(interior, text="", bg=COLOR_BOTON, fg=COLOR_TEXTO,
                              font=(familia, 10), anchor="w", justify="left",
                              wraplength=ancho - 30)
        self.texto.pack(fill="x", padx=14, pady=(4, 8))
        self.puntos = tk.Label(interior, text="", bg=COLOR_BOTON, fg=COLOR_ACENTO,
                               font=(familia, 10), anchor="w")
        self.puntos.pack(fill="x", padx=14)
        pie = tk.Frame(interior, bg=COLOR_BOTON)
        pie.pack(fill="x", padx=14, pady=(8, 12))
        self.saltar = boton_texto(pie, "Saltar", self._terminar)
        self.saltar.pack(side="left")
        self.siguiente = boton_texto(pie, "Siguiente", self._siguiente, principal=True)
        self.siguiente.pack(side="right")
        self.anterior = boton_texto(pie, "Atrás", self._anterior)
        self.anterior.pack(side="right", padx=(0, 6))
        for tecla, accion in (("<Right>", self._siguiente), ("<Return>", self._siguiente),
                              ("<Left>", self._anterior), ("<Escape>", self._terminar)):
            self.bind(tecla, lambda _e, a=accion: a())

        barra._tour = self
        barra._desplegar()
        self._mostrar()
        self.focus_force()

    def _mostrar(self) -> None:
        pasos = TOUR_PASOS
        paso = pasos[self.paso]
        self.etiqueta_paso.configure(text=f"Paso {self.paso + 1} de {len(pasos)}")
        self.titulo.configure(text=paso["titulo"])
        self.texto.configure(text=paso["texto"])
        self.puntos.configure(text=" ".join("●" if i == self.paso else "○"
                                            for i in range(len(pasos))))
        ultimo = self.paso == len(pasos) - 1
        self.siguiente.configure(text="  Listo  " if ultimo else "  Siguiente  ")
        if self.paso == 0:
            self.anterior.pack_forget()
        elif not self.anterior.winfo_ismapped():
            self.anterior.pack(side="right", padx=(0, 6))
        objetivo = self.barra._objetivo_tour(paso["id"])
        self.barra._resaltar_region(objetivo)
        self.update_idletasks()
        y = objetivo.winfo_rooty() - 10 if objetivo is not None else None
        colocar_junto_a_la_barra(self, self.barra, y)

    def _siguiente(self) -> None:
        if self.paso >= len(TOUR_PASOS) - 1:
            self._terminar()
        else:
            self.paso += 1
            self._mostrar()

    def _anterior(self) -> None:
        if self.paso > 0:
            self.paso -= 1
            self._mostrar()

    def _terminar(self) -> None:
        self.barra._tour = None
        try:
            self.barra._quitar_resalte()
        except tk.TclError:
            pass
        self.destroy()


class Aviso(tk.Toplevel):
    """Cartelito que aparece junto a la barra al terminar algo y se va solo.

    No toma el foco: puedes seguir escribiendo en lo que estabas. Un clic lo
    cierra y, si se indicó, muestra el detalle de la actividad.
    """

    def __init__(self, barra, estado: str, titulo: str, detalle: str,
                 al_pulsar=None, segundos: int = 6):
        super().__init__(barra)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        color = color_de_estado(estado)
        self.configure(bg=color)
        familia = barra.fuente.cget("family")
        cuerpo = tk.Frame(self, bg=COLOR_BOTON, cursor="hand2")
        cuerpo.pack(padx=(4, 0), fill="both", expand=True)       # franja de color a la izquierda
        tk.Label(cuerpo, text=titulo, bg=COLOR_BOTON, fg=COLOR_TEXTO, anchor="w",
                 font=(familia, 10, "bold"), wraplength=int(260 * barra.escala),
                 justify="left").pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(cuerpo, text=detalle, bg=COLOR_BOTON, fg=COLOR_TENUE, anchor="w",
                 font=(familia, 9), wraplength=int(260 * barra.escala),
                 justify="left").pack(fill="x", padx=12, pady=(2, 10))
        for widget in (self, cuerpo, *cuerpo.winfo_children()):
            widget.bind("<Button-1>", lambda _e: self._pulsado(al_pulsar))
        self.update_idletasks()
        ancho, alto = self.winfo_reqwidth(), self.winfo_reqheight()
        izq, arriba, der, abajo = barra._area()
        if barra.lado == "derecha":
            x = barra.winfo_x() - ancho - 12
        else:
            x = barra.winfo_x() + barra.winfo_width() + 12
        y = min(max(barra.winfo_y() + 40, arriba), abajo - alto - 8)
        self.geometry(f"{ancho}x{alto}+{max(izq + 8, min(x, der - ancho - 8))}+{y}")
        self.after(segundos * 1000, self._cerrar)

    def _pulsado(self, accion) -> None:
        self._cerrar()
        if accion:
            accion()

    def _cerrar(self) -> None:
        try:
            self.destroy()
        except tk.TclError:
            pass


class Barra(RAIZ_TK):
    def __init__(self, herramientas: list[dict]):
        super().__init__()
        self.title("Barra Profe")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=COLOR_FONDO)
        self.herramientas = herramientas

        # Escalado de la pantalla: 1.0 al 100%, 1.25 al 125%, etc. Todo lo que
        # se mide en píxeles se multiplica por esto; las fuentes las escala Tk.
        puntos = self.winfo_fpixels("1i")
        self.escala = puntos / 96.0
        self.tk.call("tk", "scaling", puntos / 72.0)
        self.ancho = int(ANCHO * self.escala)
        self.ancho_lengueta = max(4, int(LENGUETA * self.escala))
        self.alto_lengueta = int(ALTO_LENGUETA * self.escala)
        self.margen = int(MARGEN * self.escala)

        self.fuente = tkfont.Font(family="Segoe UI", size=9)
        self.fuente_icono = tkfont.Font(family="Segoe UI Emoji", size=13)

        estado = self._leer_estado()
        self.lado = estado.get("lado", "derecha")
        self.y = estado.get("y", 80)
        self.monitor = (estado.get("monitor_x"), estado.get("monitor_y"))
        self.fijada = estado.get("fijada", False)
        self.desplegada = True
        self._dx = self._dy = 0
        self._fuera = 0
        self._marca_config = self._marca(CONFIG)
        self.estado_texto: tk.Label | None = None
        self.senales: queue.Queue[str] = queue.Queue()
        self._puerta: socket.socket | None = None
        self._candado_revision = threading.Lock()
        self.corriendo: dict[str, Consola] = {}       # actividades en marcha, por botón
        self.ejecuciones = cargar_ejecuciones(EJECUCIONES)
        self.filas_boton: dict[str, dict] = {}
        self._fin_barra: dict[str, tuple[str, float]] = {}   # barrita que se apaga sola
        self._alerta_libro = False
        self._destello: str | None = None             # color breve de la lengüeta
        self._animando = False
        self._tour: Tour | None = None
        self.primer_boton: tk.Misc | None = None
        self.pie_botones: tk.Misc | None = None
        self._marcos_resalte: list[tk.Frame] = []
        self._revisando = False      # antes de construir: _actualizar_saludo lo consulta

        self._construir_lengueta()
        self._construir_panel()
        self._actualizar_saludo()
        self.update_idletasks()
        self.desplegada = True
        self.desplazamiento = 0
        self.con_scroll = False
        self._recalcular_alto()
        # Tk en Windows manda la rueda solo a la ventana que tiene el foco, y
        # esta barra casi nunca lo tiene: hay que tomarlo al hacer clic y al
        # pasar el mouse mientras esté desplegada, o la rueda no llega.
        self.bind_all("<MouseWheel>", self._rodar)
        self.bind_all("<ButtonPress-1>", self._tomar_foco, add="+")
        self.bind_all("<Prior>", lambda _e: self._desplazar(-self.alto * 0.8), add="+")
        self.bind_all("<Next>", lambda _e: self._desplazar(self.alto * 0.8), add="+")
        self._construir_indicador()
        self._colocar()
        self._abrir_puerta()
        self.after(1200, self._plegar)      # parte plegada, tras mostrarse una vez
        self.after(MS_VIGILAR_MOUSE, self._vigilar)
        self.after(600, self._al_frente)
        self.after(MS_VIGILAR_CONFIG, self._vigilar_config)
        self.after(30000, self._vigilar_agenda)
        self.after(3000, self._vigilar_firmas)
        import importlib.util
        self.mensajeria_disponible = importlib.util.find_spec("cryptography") is not None
        self._iniciar_mensajeria()
        self.after(2500, self._vigilar_mensajes)
        self.after(2500, self._tour_inicial)
        self._activar_soltar()
        # Escape solo esconde la barra; para cerrarla de verdad está la ✕.
        self.bind("<Escape>", lambda _e: self._plegar(forzar=True))
        registrar(f"barra abierta ({len(herramientas)} botones, escala {self.escala:.2f})")

    # ---------------------------------------------------------------- interfaz
    def _construir_lengueta(self) -> None:
        """La lengüeta se abre con un clic: pasar el mouse no la despliega."""
        self.lengueta = tk.Frame(self, bg=COLOR_LENGUETA, width=self.ancho_lengueta,
                                 cursor="hand2")
        marca = tk.Label(self.lengueta, text="⋮", bg=COLOR_LENGUETA, fg="white",
                         font=(self.fuente.cget("family"), 9), cursor="hand2")
        marca.pack(expand=True)
        for widget in (self.lengueta, marca):
            widget.bind("<Button-1>", lambda _e: self._desplegar())
            widget.bind("<Enter>", lambda _e: self._pintar(self.lengueta, marca, COLOR_ACENTO))
            widget.bind("<Leave>", lambda _e: self._pintar(self.lengueta, marca,
                                                           self._color_lengueta()))

    def _construir_panel(self) -> None:
        self.panel = tk.Frame(self, bg=COLOR_FONDO)
        self.panel.pack(fill="both", expand=True)

        self.cabecera = tk.Frame(self.panel, bg=COLOR_FONDO, cursor="fleur")
        self.cabecera.pack(fill="x")
        tk.Label(self.cabecera, text="≡", bg=COLOR_FONDO, fg=COLOR_TENUE,
                 font=self.fuente, cursor="fleur").pack(side="left", padx=(8, 4), pady=2)
        self.boton_cerrar = self._boton_cabecera("✕", self.destroy)
        self.boton_fijar = self._boton_cabecera("📌", self.alternar_fijada)
        self._pintar_fijada()
        # Los botones de la cabecera no arrastran: si se les asignara el
        # arrastre, se pisaría su propio clic (así la ✕ dejó de cerrar).
        botones = (self.boton_cerrar, self.boton_fijar)
        for evento, accion in (("<Button-1>", self._tomar), ("<B1-Motion>", self._mover),
                               ("<ButtonRelease-1>", self._soltar)):
            self.cabecera.bind(evento, accion)
            for hijo in self.cabecera.winfo_children():
                if hijo not in botones:
                    hijo.bind(evento, accion)

        envoltura = self.ancho - int(20 * self.escala)
        self.saludo = tk.Label(self.panel, text=saludo(), bg=COLOR_FONDO, fg=COLOR_TEXTO,
                               font=(self.fuente.cget("family"), 11, "bold"),
                               anchor="w", wraplength=envoltura, justify="left")
        self.saludo.pack(fill="x", padx=10, pady=(6, 0))
        self.fecha = tk.Label(self.panel, text="", bg=COLOR_FONDO, fg=COLOR_TENUE,
                              font=(self.fuente.cget("family"), 9), anchor="w")
        self.fecha.pack(fill="x", padx=10, pady=(0, 4))

        self._construir_agenda(envoltura)
        self.libro_texto = tk.Label(self.panel, text="", bg=COLOR_FONDO, fg=COLOR_TENUE,
                                    font=(self.fuente.cget("family"), 9), anchor="w",
                                    wraplength=envoltura, justify="left", cursor="hand2")
        self.libro_texto.pack(fill="x", padx=10, pady=(0, 4))
        self.libro_texto.bind("<Button-1>", lambda _e: webbrowser.open(CALENDARIO))
        self.jefatura_texto = tk.Label(self.panel, text="", bg=COLOR_FONDO, fg=COLOR_TENUE,
                                       font=(self.fuente.cget("family"), 9), anchor="w",
                                       wraplength=envoltura, justify="left")
        self.jefatura_texto.pack(fill="x", padx=10, pady=(0, 4))
        self.mensajes_texto = tk.Label(self.panel, text="", bg=COLOR_FONDO, fg=COLOR_TENUE,
                                       font=(self.fuente.cget("family"), 9), anchor="w",
                                       cursor="hand2")
        self.mensajes_texto.pack(fill="x", padx=10, pady=(0, 4))
        self.mensajes_texto.bind("<Button-1>", lambda _e: self.abrir_mensajes())
        self._construir_lista(envoltura)
        self._construir_bandeja(envoltura)

        self.cuerpo = tk.Frame(self.panel, bg=COLOR_FONDO)
        self.cuerpo.pack(fill="both", expand=True)
        self._construir_botones()

    def _boton_cabecera(self, texto: str, accion) -> tk.Label:
        b = tk.Label(self.cabecera, text=texto, bg=COLOR_FONDO, fg=COLOR_TENUE,
                     font=self.fuente, cursor="hand2", padx=6)
        b.pack(side="right")
        b.bind("<Button-1>", lambda _e: accion())
        return b

    # ----------------------------------------------------------------- agenda
    def _construir_agenda(self, envoltura: int) -> None:
        """Dos líneas: qué hay ahora y qué viene después."""
        marco = tk.Frame(self.panel, bg=COLOR_FONDO)
        marco.pack(fill="x", padx=10, pady=(0, 4))
        self.ahora_texto = tk.Label(marco, text="", bg=COLOR_FONDO, fg=COLOR_TEXTO,
                                    font=(self.fuente.cget("family"), 9, "bold"),
                                    anchor="w", wraplength=envoltura, justify="left")
        self.ahora_texto.pack(fill="x")
        self.luego_texto = tk.Label(marco, text="", bg=COLOR_FONDO, fg=COLOR_ACENTO,
                                    font=(self.fuente.cget("family"), 9),
                                    anchor="w", wraplength=envoltura, justify="left")
        self.luego_texto.pack(fill="x")

    def _refrescar_agenda(self) -> None:
        if getattr(self, "ahora_texto", None) is None:
            return
        ahora, luego = ahora_y_luego(agenda_de_hoy())
        self.ahora_texto.configure(text=f"Ahora · {ahora}" if ahora else "")
        self.luego_texto.configure(text=f"Luego · {luego}" if luego else "")

    def _vigilar_agenda(self) -> None:
        """La agenda se refresca sola aunque la barra quede fija y abierta."""
        self._refrescar_agenda()
        self.after(MS_VIGILAR_AGENDA, self._vigilar_agenda)

    # ------------------------------------------------------- firmas pendientes
    def _vigilar_firmas(self) -> None:
        """Mantiene al día el estado del libro, mire cuando mire.

        Cada dos minutos compara el reloj con el archivo: si es de otro día o
        tiene más de veinte minutos, manda a revisar de nuevo. Así se recupera
        sola cuando el PC durmió toda la noche, en vez de depender de un
        temporizador que quedó corriendo desde ayer.
        """
        try:
            if self._estado_vencido():
                self._revisar_libro()
            self._refrescar_firmas()
        except Exception as exc:  # noqa: BLE001
            registrar("fallo al vigilar el libro", traceback.format_exc())
        self.after(MS_VIGILAR_LIBRO, self._vigilar_firmas)

    def _estado_vencido(self, minutos_validez: int = MINUTOS_VALIDEZ_LIBRO) -> bool:
        """True si hay que volver a revisar el libro."""
        if self._revisando:
            return False
        try:
            with open(ESTADO_FIRMAS, encoding="utf-8") as f:
                estado = json.load(f)
            edad = datetime.datetime.now().timestamp() - os.path.getmtime(ESTADO_FIRMAS)
        except (OSError, ValueError):
            return True
        return estado_vencido(estado, edad, datetime.date.today().strftime("%d/%m/%Y"),
                              minutos_validez)

    def _revisar_libro(self) -> None:
        """Lanza la revisión aparte (entra a Webclass, demora unos segundos)."""
        # El candado hace que la comprobación y la marca sean una sola
        # operación: dos llamadas seguidas no lanzan dos revisiones.
        with self._candado_revision:
            if self._revisando:
                return
            self._revisando = True
        try:
            proceso = subprocess.Popen(comando_webclass("firmas", "--salida", ESTADO_FIRMAS),
                                       cwd=WEBCLASS,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as exc:  # noqa: BLE001
            with self._candado_revision:
                self._revisando = False
            registrar("no se pudo revisar el libro", str(exc))
            return
        registrar("revisando el libro de clases…")

        def esperar() -> None:
            try:
                proceso.wait(timeout=SEGUNDOS_TOPE_REVISION)
            except subprocess.TimeoutExpired:
                proceso.kill()
                registrar(f"la revisión del libro pasó de {SEGUNDOS_TOPE_REVISION} s y se canceló")
            finally:
                with self._candado_revision:
                    self._revisando = False
        threading.Thread(target=esperar, daemon=True).start()

    def _refrescar_firmas(self) -> None:
        """Lee estado_firmas.json y actualiza la lengüeta y la línea del panel."""
        hoy = datetime.date.today().strftime("%d/%m/%Y")
        texto, color, alerta = "", COLOR_TENUE, False
        estado: dict = {}
        try:
            with open(ESTADO_FIRMAS, encoding="utf-8") as f:
                estado = json.load(f)
            if estado.get("fecha") != hoy:
                texto = "Libro: sin revisar hoy"
            elif estado.get("error"):
                texto = "Libro: no se pudo revisar (se reintenta solo)"
            else:
                faltan = estado.get("sin_firmar", [])
                sin_reg = estado.get("sin_registro", [])
                if faltan:
                    cuales = ", ".join(f"{b['curso']} {b['hora'].split('-')[0]}" for b in faltan[:3])
                    texto = f"⚠ {len(faltan)} sin firmar · {cuales}"
                    color, alerta = COLOR_ALERTA, True
                elif sin_reg:
                    texto = f"⚠ {len(sin_reg)} sin registrar (OA o asistencia)"
                    color = COLOR_ACENTO
                elif estado.get("bloques"):
                    texto = f"✓ Libro al día ({len(estado['bloques'])} bloques)"
                else:
                    texto = "Hoy no tienes bloques"
                antiguos = texto_atrasados(estado.get("atrasados", []))
                if antiguos:
                    texto += f"\n↩ {antiguos}: usa «Registrar libro pendiente»"
                    if not alerta:
                        color = COLOR_ACENTO
        except (OSError, ValueError):
            texto = "Libro: aún sin datos (se revisa solo)"
        if getattr(self, "libro_texto", None):
            self.libro_texto.configure(text=texto, fg=color)
        self._pintar_lengueta(alerta)
        self._refrescar_jefatura(estado)

    def _refrescar_jefatura(self, completo: dict) -> None:
        """Quiénes faltaron hoy en el curso del que eres profesor jefe.

        Recibe el estado ya leído por _refrescar_firmas, para no abrir el
        mismo archivo dos veces.
        """
        if getattr(self, "jefatura_texto", None) is None:
            return
        texto, color = "", COLOR_TENUE
        try:
            # Si el archivo es de otro día, no se muestra: valen los de hoy.
            if completo.get("fecha") != datetime.date.today().strftime("%d/%m/%Y"):
                self.jefatura_texto.configure(text="")
                return
            datos = completo.get("jefatura", {})
            curso = datos.get("curso", "")
            if datos.get("estado"):
                texto = f"{curso} · {datos['estado']}"
            elif datos:
                ausentes, atrasadas = datos.get("ausentes", []), datos.get("atrasadas", [])
                if ausentes:
                    nombres = ", ".join(ausentes[:4])
                    if len(ausentes) > 4:
                        nombres += f" y {len(ausentes) - 4} más"
                    texto = f"{curso} · {len(ausentes)} ausentes: {nombres}"
                    color = COLOR_TEXTO
                else:
                    texto = f"{curso} · sin ausentes hoy"
                if atrasadas:
                    texto += f" · {len(atrasadas)} atrasadas: " + ", ".join(atrasadas[:3])
        except (OSError, ValueError):
            texto = ""
        self.jefatura_texto.configure(text=texto, fg=color)

    def _color_lengueta(self) -> str:
        """Pulsa mientras algo corre; si no, destello de resultado; si no, alerta del libro."""
        if self.corriendo:
            return COLOR_ACENTO if int(time.time() * 2) % 2 else COLOR_LENGUETA
        if self._destello:
            return self._destello
        return COLOR_ALERTA if self._alerta_libro else COLOR_LENGUETA

    def _pintar_lengueta(self, alerta: bool | None = None) -> None:
        if alerta is not None:
            self._alerta_libro = alerta
        color = self._color_lengueta()
        self.color_lengueta = color
        try:
            self.lengueta.configure(bg=color)
            for hijo in self.lengueta.winfo_children():
                hijo.configure(bg=color)
        except tk.TclError:
            pass

    # ------------------------------------------------------- soltar archivos
    def _activar_soltar(self) -> None:
        """Permite arrastrar archivos sobre la barra para dejarlos en el buzón."""
        if DND_FILES is None:
            registrar("sin tkinterdnd2: no se pueden soltar archivos en la barra")
            self._sin_soltar()
            return
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._al_soltar)
        except Exception as exc:  # noqa: BLE001
            registrar("no se pudo activar soltar archivos", str(exc))
            self._sin_soltar()

    def _sin_soltar(self) -> None:
        """Avisa en la barra que arrastrar no va a funcionar en este equipo.

        Sin esto, arrastrar un archivo simplemente no hacía nada y no había
        forma de saber por qué: parecía que la barra se había colgado.
        """
        self.soltar_roto = True
        try:
            if getattr(self, "estado_texto", None):
                self.estado_texto.configure(
                    text="Aquí no se pueden soltar archivos: usa «Subir a Webclass»",
                    fg=COLOR_ERROR)
        except tk.TclError:
            pass

    def _al_soltar(self, evento) -> None:
        archivos = [a for a in self.tk.splitlist(evento.data) if os.path.isfile(a)]
        if not archivos:
            return
        self._desplegar()
        # Si ya hay un correo o una ventana de arrastre abiertos, el archivo se suma a ellos:
        # así dos guías soltadas una tras otra salen juntas, en el mismo correo.
        for clase in (VentanaCorreo, VentanaSoltar):
            abiertas = [v for v in self.winfo_children() if isinstance(v, clase)]
            if abiertas:
                abiertas[-1].agregar_archivos(archivos)
                abiertas[-1].lift()
                return
        VentanaSoltar(self, archivos)

    # ---------------------------------------------------------------- bandeja
    # ------------------------------------------------- lista de verificación
    def _construir_lista(self, envoltura: int) -> None:
        """Checklist propia, guardada en este PC. No sale a internet."""
        self.lista_abierta = self._leer_estado().get("lista_abierta", False)
        self.titulo_lista = tk.Label(self.panel, text="", bg=COLOR_FONDO, fg=COLOR_ACENTO,
                                     font=(self.fuente.cget("family"), 9, "bold"),
                                     anchor="w", cursor="hand2")
        self.titulo_lista.pack(fill="x", padx=10, pady=(6, 1))
        self.titulo_lista.bind("<Button-1>", lambda _e: self.alternar_lista())

        self.caja_lista = tk.Frame(self.panel, bg=COLOR_FONDO)
        self.items_lista = tk.Frame(self.caja_lista, bg=COLOR_FONDO)
        self.items_lista.pack(fill="x")

        marco = tk.Frame(self.caja_lista, bg=COLOR_BOTON)
        marco.pack(fill="x", padx=6, pady=(3, 2))
        tk.Frame(marco, bg=COLOR_ACENTO, width=3).pack(side="left", fill="y")
        self.entrada_tarea = tk.Entry(marco, bg=COLOR_BOTON, fg=COLOR_TENUE, bd=0,
                                      font=self.fuente, insertbackground=COLOR_TEXTO,
                                      highlightthickness=0)
        self.entrada_tarea.pack(side="left", fill="x", expand=True, padx=(6, 8), pady=6)
        self.entrada_tarea.insert(0, MARCA_TAREA)
        self.entrada_tarea.bind("<Button-1>", lambda _e: (self.focus_force(),
                                                          self.entrada_tarea.focus_set()))
        self.entrada_tarea.bind("<FocusIn>", lambda _e: self._limpiar_marca(
            self.entrada_tarea, MARCA_TAREA))
        self.entrada_tarea.bind("<FocusOut>", lambda _e: self._poner_marca(
            self.entrada_tarea, MARCA_TAREA))
        self.entrada_tarea.bind("<Return>", self._agregar_tarea)
        self.entrada_tarea.bind("<Escape>", lambda _e: (self.entrada_tarea.delete(0, "end"),
                                                        self.focus_force()))
        self._refrescar_lista()

    def _limpiar_marca(self, campo: tk.Entry, marca: str) -> None:
        if campo.get() == marca:
            campo.delete(0, "end")
        campo.configure(fg=COLOR_TEXTO)

    def _poner_marca(self, campo: tk.Entry, marca: str) -> None:
        if not campo.get().strip():
            campo.delete(0, "end")
            campo.insert(0, marca)
            campo.configure(fg=COLOR_TENUE)

    def _leer_tareas(self) -> list[dict]:
        try:
            with open(TAREAS, encoding="utf-8") as f:
                datos = json.load(f)
            return datos if isinstance(datos, list) else []
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as exc:
            # Archivo ilegible: se aparta una copia para no pisarlo con una
            # lista vacía en el próximo guardado.
            registrar("la lista de tareas está ilegible, se guarda copia", str(exc))
            try:
                shutil.copy2(TAREAS, TAREAS + ".corrupto")
            except OSError:
                pass
            return []

    def _guardar_tareas(self, tareas: list[dict]) -> None:
        try:
            escribir_atomico(TAREAS, json.dumps(tareas, ensure_ascii=False, indent=1))
        except OSError as exc:
            registrar("no se pudo guardar la lista", str(exc))
            messagebox.showwarning("Barra Profe", f"No se pudo guardar la lista.\n\n{exc}")

    def _agregar_tarea(self, _evento=None) -> None:
        texto = self.entrada_tarea.get().strip()
        if not texto or texto == MARCA_TAREA:
            return
        tareas = self._leer_tareas()
        tareas.append({"texto": texto, "hecha": False,
                       "creada": datetime.datetime.now().isoformat(timespec="minutes")})
        self._guardar_tareas(tareas)
        self.entrada_tarea.delete(0, "end")
        self.lista_abierta = True
        self._refrescar_lista()
        self._recolocar()

    def _marcar_tarea(self, indice: int) -> None:
        tareas = self._leer_tareas()
        if 0 <= indice < len(tareas):
            tareas[indice]["hecha"] = not tareas[indice].get("hecha")
            self._guardar_tareas(tareas)
            self._refrescar_lista()

    def _borrar_tarea(self, indice: int) -> None:
        tareas = self._leer_tareas()
        if 0 <= indice < len(tareas):
            tareas.pop(indice)
            self._guardar_tareas(tareas)
            self._refrescar_lista()
            self._recolocar()

    def _limpiar_hechas(self) -> None:
        self._guardar_tareas([t for t in self._leer_tareas() if not t.get("hecha")])
        self._refrescar_lista()
        self._recolocar()

    def _refrescar_lista(self) -> None:
        if getattr(self, "items_lista", None) is None:
            return
        tareas = self._leer_tareas()
        pendientes_lista = sum(1 for t in tareas if not t.get("hecha"))
        flecha = "▾" if self.lista_abierta else "▸"
        self.titulo_lista.configure(
            text=f"{flecha} MI LISTA · {pendientes_lista} pendiente"
                 f"{'s' if pendientes_lista != 1 else ''}")
        for hijo in self.items_lista.winfo_children():
            hijo.destroy()
        if not self.lista_abierta:
            self.caja_lista.pack_forget()
            return
        self.caja_lista.pack(fill="x", after=self.titulo_lista)

        for i, tarea in enumerate(tareas):
            hecha = tarea.get("hecha")
            fila = tk.Frame(self.items_lista, bg=COLOR_FONDO)
            fila.pack(fill="x", padx=10, pady=1)
            marca = tk.Label(fila, text="☑" if hecha else "☐", bg=COLOR_FONDO,
                             fg=COLOR_ACENTO if hecha else COLOR_TENUE,
                             font=self.fuente, cursor="hand2")
            marca.pack(side="left")
            texto = tk.Label(fila, text=tarea.get("texto", ""), bg=COLOR_FONDO,
                             fg=COLOR_TENUE if hecha else COLOR_TEXTO,
                             font=(self.fuente.cget("family"), 9,
                                   "overstrike" if hecha else "normal"),
                             anchor="w", justify="left", cursor="hand2",
                             wraplength=self.ancho - int(50 * self.escala))
            texto.pack(side="left", fill="x", expand=True, padx=(4, 2))
            quitar = tk.Label(fila, text="✕", bg=COLOR_FONDO, fg=COLOR_SUAVE,
                              font=(self.fuente.cget("family"), 8), cursor="hand2")
            quitar.pack(side="right")
            for w_ in (marca, texto):
                w_.bind("<Button-1>", lambda _e, k=i: self._marcar_tarea(k))
            quitar.bind("<Button-1>", lambda _e, k=i: self._borrar_tarea(k))
            # La ✕ aparece solo al pasar el mouse por la fila.
            for w_ in (fila, marca, texto, quitar):
                w_.bind("<Enter>", lambda _e, q=quitar: q.configure(fg=COLOR_ERROR), add="+")
                w_.bind("<Leave>", lambda _e, q=quitar: q.configure(fg=COLOR_SUAVE), add="+")

        if any(t.get("hecha") for t in tareas):
            limpiar = tk.Label(self.items_lista, text="borrar las hechas", bg=COLOR_FONDO,
                               fg=COLOR_TENUE, font=(self.fuente.cget("family"), 8),
                               anchor="w", cursor="hand2")
            limpiar.pack(fill="x", padx=10, pady=(2, 0))
            limpiar.bind("<Button-1>", lambda _e: self._limpiar_hechas())

    def alternar_lista(self) -> None:
        self.lista_abierta = not self.lista_abierta
        self._refrescar_lista()
        self._recolocar()
        self._guardar_estado()

    def _recolocar(self) -> None:
        """Recalcula el alto tras abrir o cerrar la lista."""
        self.update_idletasks()
        self._recalcular_alto()
        if self.desplegada:
            self._colocar()

    def _construir_bandeja(self, envoltura: int) -> None:
        """Campo para anotar: Enter guarda la nota para el asistente."""
        marco = tk.Frame(self.panel, bg=COLOR_BOTON)
        marco.pack(fill="x", padx=6, pady=(2, 2))
        tk.Frame(marco, bg=COLOR_ACENTO, width=3).pack(side="left", fill="y")
        self.entrada = tk.Entry(marco, bg=COLOR_BOTON, fg=COLOR_TENUE, bd=0,
                                font=self.fuente, insertbackground=COLOR_TEXTO,
                                highlightthickness=0)
        self.entrada.pack(side="left", fill="x", expand=True, padx=(6, 8), pady=6)
        self.entrada.insert(0, MARCA_AGUA)
        # Con overrideredirect Windows no le da el foco sola: hay que forzarlo.
        self.entrada.bind("<Button-1>", lambda _e: (self.focus_force(),
                                                    self.entrada.focus_set()))
        self.entrada.bind("<FocusIn>", self._entrar_bandeja)
        self.entrada.bind("<FocusOut>", self._salir_bandeja)
        self.entrada.bind("<Return>", self._guardar_nota)
        self.entrada.bind("<Escape>", self._cancelar_nota)

        self.bandeja_estado = tk.Label(self.panel, text="", bg=COLOR_FONDO, fg=COLOR_TENUE,
                                       font=(self.fuente.cget("family"), 8), anchor="w",
                                       wraplength=envoltura, justify="left")
        self.bandeja_estado.pack(fill="x", padx=12, pady=(0, 2))

    def _entrar_bandeja(self, _evento=None) -> None:
        if self.entrada.get() == MARCA_AGUA:
            self.entrada.delete(0, "end")
        self.entrada.configure(fg=COLOR_TEXTO)

    def _salir_bandeja(self, _evento=None) -> None:
        if not self.entrada.get().strip():
            self.entrada.delete(0, "end")
            self.entrada.insert(0, MARCA_AGUA)
            self.entrada.configure(fg=COLOR_TENUE)

    def _guardar_nota(self, _evento=None) -> str:
        texto = self.entrada.get().strip()
        if not texto or texto == MARCA_AGUA:
            return "break"
        try:
            anotar(texto)
        except OSError as exc:  # noqa: BLE001
            registrar("no se pudo guardar la nota", traceback.format_exc())
            self._pintar_bandeja(f"No se pudo guardar: {exc}", error=True)
            return "break"
        self.entrada.delete(0, "end")
        self._pintar_bandeja(f"✓ Guardado · {self._texto_pendientes()}")
        return "break"

    def _cancelar_nota(self, _evento=None) -> str:
        """Escape limpia la nota; sin el 'break' cerraría la barra entera."""
        self.entrada.delete(0, "end")
        self._salir_bandeja()
        self.cuerpo.focus_set()
        return "break"

    def _refrescar_bandeja(self) -> None:
        if getattr(self, "bandeja_estado", None):
            self._pintar_bandeja(self._texto_pendientes())

    @staticmethod
    def _texto_pendientes() -> str:
        cuantas = pendientes()
        if cuantas == 0:
            return "Sin notas pendientes"
        if cuantas == 1:
            return "1 nota esperando al asistente"
        return f"{cuantas} notas esperando al asistente"

    def _pintar_bandeja(self, texto: str, error: bool = False) -> None:
        self.bandeja_estado.configure(text=texto, fg=COLOR_ERROR if error else COLOR_TENUE)

    def _anotando(self) -> bool:
        """Mientras escribes una nota, la barra no se pliega."""
        entrada = getattr(self, "entrada", None)
        if entrada is None:
            return False
        try:
            if entrada.get().strip() not in ("", MARCA_AGUA):
                return True
            return self.focus_get() is entrada
        except (tk.TclError, KeyError):
            return False

    # --------------------------------------------------------------- botones
    def _construir_botones(self) -> None:
        """(Re)arma los botones. Se llama de nuevo al recargar el .json."""
        for hijo in self.cuerpo.winfo_children():
            hijo.destroy()
        self.filas_boton = {}
        self.primer_boton = None
        grupo_actual = None
        for h in self.herramientas:
            if h.get("grupo") and h["grupo"] != grupo_actual:
                grupo_actual = h["grupo"]
                tk.Label(self.cuerpo, text=grupo_actual.upper(), bg=COLOR_FONDO,
                         fg=COLOR_ACENTO, font=(self.fuente.cget("family"), 8, "bold"),
                         anchor="w").pack(fill="x", padx=10, pady=(8, 2))
            nombre = h.get("nombre", "(sin nombre)")
            contenedor = tk.Frame(self.cuerpo, bg=COLOR_FONDO)
            contenedor.pack(fill="x", padx=6, pady=1)
            if self.primer_boton is None:
                self.primer_boton = contenedor
            # takefocus: se llega con Tab y se acciona con Enter o espacio.
            fila = tk.Frame(contenedor, bg=COLOR_BOTON, cursor="hand2", takefocus=True,
                            highlightthickness=1, highlightbackground=COLOR_BOTON,
                            highlightcolor=COLOR_ACENTO)
            fila.pack(fill="x")
            # Franja lateral: se enciende en morado claro al pasar el mouse.
            franja = tk.Frame(fila, bg=COLOR_BOTON, width=3)
            franja.pack(side="left", fill="y")
            icono = tk.Label(fila, text=h.get("icono", "•"), bg=COLOR_BOTON,
                             fg=COLOR_TEXTO, font=self.fuente_icono, width=2)
            icono.pack(side="left", padx=(5, 2))
            # Estado de la actividad (◐ en proceso, ✓ listo, ⚠ avisos, ✕ error).
            estado = tk.Label(fila, text="", bg=COLOR_BOTON, fg=COLOR_TENUE,
                              font=("Segoe UI Symbol", 11), width=2)
            estado.pack(side="right", padx=(0, 6))
            columna = tk.Frame(fila, bg=COLOR_BOTON)
            columna.pack(side="left", fill="x", expand=True, padx=(0, 4), pady=4)
            texto = tk.Label(columna, text=nombre, bg=COLOR_BOTON,
                             fg=COLOR_TENUE, font=self.fuente, anchor="w")
            texto.pack(fill="x")
            sub = tk.Label(columna, text="", bg=COLOR_BOTON, fg=COLOR_SUAVE,
                           font=(self.fuente.cget("family"), 8), anchor="w")
            barra = tk.Canvas(contenedor, height=3, bg=COLOR_BOTON, bd=0,
                              highlightthickness=0)

            partes = (fila, icono, texto, columna, sub, estado)
            self.filas_boton[nombre] = {"estado": estado, "sub": sub, "barra": barra,
                                        "texto": texto}
            for widget in partes:
                widget.bind("<Enter>", lambda _e, p=partes, fr=franja, x=h:
                            (self._resaltar(p, fr, True), self._tip(self._ayuda_boton(x))))
                widget.bind("<Leave>", lambda _e, p=partes, fr=franja:
                            (self._resaltar(p, fr, False), self._tip("")))
                widget.bind("<ButtonPress-1>", lambda _e, p=partes:
                            self._pintar(*p, COLOR_PULSADO))
                widget.bind("<ButtonRelease-1>", lambda _e, x=h, p=partes, fr=franja:
                            (self._pintar(*p, COLOR_HOVER), abrir(x, self)))
            # Teclado: el foco se ve igual que pasar el mouse; flechas y Tab navegan.
            fila.bind("<FocusIn>", lambda _e, p=partes, fr=franja, x=h:
                      (self._resaltar(p, fr, True), self._tip(self._ayuda_boton(x)),
                       self._mostrar_fila(_e.widget)))
            fila.bind("<FocusOut>", lambda _e, p=partes, fr=franja:
                      (self._resaltar(p, fr, False), self._tip("")))
            for tecla in ("<Return>", "<space>"):
                fila.bind(tecla, lambda _e, x=h: (abrir(x, self), "break")[1])
            fila.bind("<Down>", lambda e: (e.widget.tk_focusNext().focus_set(), "break")[1])
            fila.bind("<Up>", lambda e: (e.widget.tk_focusPrev().focus_set(), "break")[1])

        self.estado_texto = tk.Label(self.cuerpo, text="", bg=COLOR_FONDO, fg=COLOR_TENUE,
                                     font=(self.fuente.cget("family"), 9),
                                     wraplength=self.ancho - int(20 * self.escala),
                                     justify="left", anchor="w")
        self.estado_texto.pack(fill="x", padx=10, pady=(4, 2))

        pie = tk.Frame(self.cuerpo, bg=COLOR_FONDO)
        pie.pack(fill="x", padx=10, pady=(0, 6))
        self.pie_botones = pie
        # La barra mide ~210 px: los enlaces van en filas para que ninguno quede oculto a la derecha.
        fila_pie1 = tk.Frame(pie, bg=COLOR_FONDO)
        fila_pie1.pack(fill="x")
        fila_pie2 = tk.Frame(pie, bg=COLOR_FONDO)
        fila_pie2.pack(fill="x")
        fila_pie3 = tk.Frame(pie, bg=COLOR_FONDO)
        fila_pie3.pack(fill="x")
        for texto_enlace, ruta in (("Ver registro", LOG), ("Editar botones", CONFIG)):
            enlace = tk.Label(fila_pie1, text=texto_enlace, bg=COLOR_FONDO, fg=COLOR_SUAVE,
                              font=(self.fuente.cget("family"), 9, "underline"),
                              cursor="hand2", takefocus=True, highlightthickness=1,
                              highlightbackground=COLOR_FONDO, highlightcolor=COLOR_ACENTO)
            enlace.pack(side="left", padx=(0, 10))
            enlace.bind("<Button-1>", lambda _e, r=ruta: self._abrir_archivo(r))
            for tecla in ("<Return>", "<space>"):
                enlace.bind(tecla, lambda _e, r=ruta: (self._abrir_archivo(r), "break")[1])
            enlace.bind("<Enter>", lambda _e, w=enlace: w.configure(fg=COLOR_TEXTO))
            enlace.bind("<Leave>", lambda _e, w=enlace: w.configure(fg=COLOR_SUAVE))
        tour = tk.Label(fila_pie2, text="Ver tour", bg=COLOR_FONDO, fg=COLOR_SUAVE,
                        font=(self.fuente.cget("family"), 9, "underline"), cursor="hand2",
                        takefocus=True, highlightthickness=1,
                        highlightbackground=COLOR_FONDO, highlightcolor=COLOR_ACENTO)
        tour.pack(side="left", padx=(0, 10))
        tour.bind("<Button-1>", lambda _e: self.iniciar_tour())
        for tecla in ("<Return>", "<space>"):
            tour.bind(tecla, lambda _e: (self.iniciar_tour(), "break")[1])
        tour.bind("<Enter>", lambda _e: tour.configure(fg=COLOR_TEXTO))
        tour.bind("<Leave>", lambda _e: tour.configure(fg=COLOR_SUAVE))
        buscar = tk.Label(fila_pie2, text="Buscar actualizaciones", bg=COLOR_FONDO, fg=COLOR_SUAVE,
                          font=(self.fuente.cget("family"), 9, "underline"), cursor="hand2",
                          takefocus=True, highlightthickness=1,
                          highlightbackground=COLOR_FONDO, highlightcolor=COLOR_ACENTO)
        buscar.pack(side="left", padx=(0, 10))
        buscar.bind("<Button-1>", lambda _e: self._buscar_actualizacion_manual())
        for tecla in ("<Return>", "<space>"):
            buscar.bind(tecla, lambda _e: (self._buscar_actualizacion_manual(), "break")[1])
        buscar.bind("<Enter>", lambda _e: buscar.configure(fg=COLOR_TEXTO))
        buscar.bind("<Leave>", lambda _e: buscar.configure(fg=COLOR_SUAVE))
        from barra_utiles import leer_version
        version = leer_version(CARPETA)
        if version:                                  # versión de Barra, discreta, al final de la fila
            tk.Label(fila_pie3, text=f"v{version}", bg=COLOR_FONDO, fg=COLOR_SUAVE,
                     font=(self.fuente.cget("family"), 9)).pack(side="left")
        self.aviso_actualizacion = tk.Label(fila_pie3, text="", bg=COLOR_FONDO, fg=COLOR_ACENTO, cursor="hand2",
                                            font=(self.fuente.cget("family"), 9, "underline"), justify="left",
                                            wraplength=self.ancho - int(70 * self.escala))
        self.aviso_actualizacion.pack(side="left", padx=(8, 0))
        if version and not getattr(self, "_busqueda_actualizacion", False):
            self._busqueda_actualizacion = True          # una sola consulta por sesión, sin bloquear la ventana
            threading.Thread(target=self._buscar_actualizacion, args=(version,), daemon=True).start()
        self._refrescar_filas()

    def _buscar_actualizacion(self, version: str, manual: bool = False) -> None:
        """Consulta GitHub en segundo plano. Solo la búsqueda manual avisa cuando no hay nada o no hay red."""
        try:
            import actualizador
            info, hubo_red = actualizador.consultar(version)
        except Exception:                                # respuesta rara: la barra sigue como siempre
            info, hubo_red = None, False
        def mostrar():
            if not info:
                self.aviso_actualizacion.configure(text="")
            if info:
                self._mostrar_actualizacion(info)
                if manual:
                    self._preguntar_actualizar(info)
            elif manual:
                if hubo_red:
                    texto = f"Ya tienes la última versión (v{version})."
                else:
                    texto = ("No pude consultar si hay una versión nueva. Revisa tu conexión a internet "
                             "e inténtalo de nuevo.")
                    detalle = getattr(sys.modules.get("actualizador"), "ULTIMO_ERROR", "")
                    if detalle:
                        texto += f"\n\nDetalle técnico: {detalle}"
                messagebox.showinfo("Barra Profe", texto)
        try:
            self.after(0, mostrar)
        except (tk.TclError, RuntimeError):
            pass

    def _buscar_actualizacion_manual(self) -> None:
        from barra_utiles import leer_version
        version = leer_version(CARPETA)
        if not version:
            messagebox.showinfo("Barra Profe", "No encuentro el número de versión de esta barra (archivo VERSION).")
            return
        self.aviso_actualizacion.configure(text="Buscando actualizaciones…")
        threading.Thread(target=self._buscar_actualizacion, args=(version, True), daemon=True).start()

    def _mostrar_actualizacion(self, info: dict) -> None:
        self.aviso_actualizacion.configure(text=f"Hay una versión nueva: {info['version']}")
        self.aviso_actualizacion.bind("<Button-1>", lambda _e: self._preguntar_actualizar(info))

    def _preguntar_actualizar(self, info: dict) -> None:
        notas = info.get("notas") or "(sin notas)"
        if not messagebox.askyesno(
                "Barra Profe",
                f"Versión {info['version']} disponible.\n\nQué cambió:\n{notas[:900]}\n\n"
                f"Tu perfil, tus datos y tus botones no se tocan; se guarda una copia del código actual.\n\n¿Actualizar ahora?"):
            return
        self.aviso_actualizacion.configure(text="Actualizando… no cierres la barra")
        threading.Thread(target=self._actualizar, args=(info,), daemon=True).start()

    def _actualizar(self, info: dict) -> None:
        import actualizador
        try:
            r = actualizador.actualizar(info, CARPETA, os.path.join(os.path.dirname(CARPETA), "respaldo_actualizacion"))
            texto, color = "Actualizada. Cierra la barra y ábrela de nuevo.", "info"
            if r["avisos"]:
                texto += "\n\n" + "\n".join(r["avisos"])
        except actualizador.ErrorActualizacion as exc:
            texto, color = str(exc), "error"
        except Exception as exc:                         # nunca dejar la ventana colgada
            texto, color = f"No se pudo actualizar: {exc}", "error"
        def fin():
            self.aviso_actualizacion.configure(text="" if color == "info" else "No se pudo actualizar")
            (messagebox.showinfo if color == "info" else messagebox.showerror)("Barra Profe", texto)
        self.after(0, fin)

    def _mostrar_fila(self, fila: tk.Misc) -> None:
        """Si el foco de teclado cae fuera de la vista, desplaza hasta mostrarlo."""
        if not getattr(self, "con_scroll", False):
            return
        try:
            arriba = fila.winfo_rooty() - self.panel.winfo_rooty()
            abajo = arriba + fila.winfo_height()
            if arriba < self.desplazamiento:
                self._desplazar(arriba - self.desplazamiento - 8)
            elif abajo > self.desplazamiento + self.alto:
                self._desplazar(abajo - self.desplazamiento - self.alto + 8)
        except tk.TclError:
            pass

    def _abrir_archivo(self, ruta: str) -> None:
        """Abre el registro o la configuración con el programa predeterminado."""
        nombre = os.path.basename(ruta)
        if not os.path.exists(ruta):
            self._tip(f"Todavía no existe {nombre}")
            return
        try:
            os.startfile(ruta)
        except OSError as exc:
            registrar(f"no se pudo abrir {nombre}", str(exc))
            self._tip(f"No se pudo abrir {nombre}")

    # ------------------------------------------------------------------- tour
    def _tour_inicial(self) -> None:
        """La primera vez que se abre la barra, se ofrece el recorrido de bienvenida."""
        if tour_pendiente(TOUR):
            self.iniciar_tour()

    def iniciar_tour(self) -> None:
        if self._tour is not None:
            return
        try:
            marcar_tour_visto(TOUR)          # una vez iniciado no vuelve a salir solo
        except OSError as exc:
            registrar("no se pudo guardar que el tour ya se vio", str(exc))
        self._tour = Tour(self)

    def _objetivo_tour(self, paso: str) -> tk.Misc | None:
        return {"barra": getattr(self, "cabecera", None),
                "hoy": getattr(getattr(self, "ahora_texto", None), "master", None),
                "lista": getattr(self, "titulo_lista", None),
                "notas": getattr(getattr(self, "entrada", None), "master", None),
                "botones": self.primer_boton,
                "pie": self.pie_botones}.get(paso)

    def _quitar_resalte(self) -> None:
        for marco in self._marcos_resalte:
            marco.destroy()
        self._marcos_resalte = []

    def _resaltar_region(self, widget: tk.Misc | None) -> None:
        """Dibuja un marco de color alrededor de `widget` y lo trae a la vista."""
        self._quitar_resalte()
        if widget is None:
            return
        try:
            self.update_idletasks()
            self._mostrar_fila(widget)
            x = widget.winfo_rootx() - self.panel.winfo_rootx() - 3
            y = widget.winfo_rooty() - self.panel.winfo_rooty() - 3
            ancho, alto = widget.winfo_width() + 6, widget.winfo_height() + 6
            grosor = 3
            for (px, py, pa, pl) in ((x, y, ancho, grosor), (x, y + alto - grosor, ancho, grosor),
                                     (x, y, grosor, alto), (x + ancho - grosor, y, grosor, alto)):
                marco = tk.Frame(self.panel, bg=COLOR_ACENTO)
                marco.place(x=px, y=py, width=pa, height=pl)
                marco.lift()
                self._marcos_resalte.append(marco)
        except tk.TclError:
            pass

    # -------------------------------------------------- actividad de los botones
    def actividad_inicio(self, consola: "Consola") -> None:
        """Una herramienta empezó a correr: el botón y la lengüeta lo muestran."""
        nombre = consola.titulo
        self.corriendo[nombre] = consola
        self._fin_barra.pop(nombre, None)
        self._destello = None
        self._refrescar_fila(nombre)
        self._arrancar_animacion()

    def actividad_progreso(self, consola: "Consola") -> None:
        self._refrescar_fila(consola.titulo)

    def actividad_fin(self, consola: "Consola", resultado: dict) -> None:
        """Terminó (bien, con avisos, con error o cancelada): se anota y se avisa."""
        try:
            nombre = consola.titulo
            if self.corriendo.get(nombre) is consola:
                del self.corriendo[nombre]
            estado = resultado["estado"]
            try:
                self.ejecuciones = guardar_ejecucion(
                    EJECUCIONES, nombre, estado, resultado["resumen"], resultado["duracion"])
            except OSError as exc:
                registrar("no se pudo guardar el resultado de la actividad", str(exc))
            color = color_de_estado(estado)
            self._fin_barra[nombre] = (color, time.time() + 5)
            if not self.corriendo:
                self._destello = color
                self.after(6000, self._apagar_destello)
            self._refrescar_fila(nombre)
            self._arrancar_animacion()
            # Si la ventana de la actividad ya no se ve, se avisa con un cartelito.
            oculta = consola._cerrada or consola.state() in ("iconic", "withdrawn")
            if oculta and not (consola._cerrada and estado == "cancelado"):
                self._avisar(consola, estado, resultado)
        except tk.TclError:
            pass          # la barra se está cerrando
        except Exception:  # noqa: BLE001
            registrar("fallo al registrar el fin de una actividad", traceback.format_exc())

    def _apagar_destello(self) -> None:
        self._destello = None
        try:
            self._pintar_lengueta()
        except tk.TclError:
            pass

    def _avisar(self, consola: "Consola", estado: str, resultado: dict) -> None:
        titulo = f"{ESTADOS[estado]['icono']}  {consola.titulo}: {ESTADOS[estado]['texto'].lower()}"
        Aviso(self, estado, titulo, resultado["resumen"],
              lambda: self._mostrar_actividad(consola))

    def _mostrar_actividad(self, consola: "Consola") -> None:
        try:
            consola.deiconify()
            consola.lift()
        except tk.TclError:
            pass        # la ventana ya no existe

    def _arrancar_animacion(self) -> None:
        if not self._animando:
            self._animando = True
            self.after(90, self._animar)

    def _animar(self) -> None:
        """Mueve el giro, las barritas y el pulso de la lengüeta mientras haya algo vivo."""
        try:
            ahora = time.time()
            for nombre, (_color, hasta) in list(self._fin_barra.items()):
                if ahora > hasta:
                    del self._fin_barra[nombre]
                    self._refrescar_fila(nombre)
            for nombre in set(self.corriendo) | set(self._fin_barra):
                self._refrescar_fila(nombre)
            self._pintar_lengueta()
            if not self.corriendo and not self._fin_barra:
                self._animando = False
                return
        except tk.TclError:
            self._animando = False
            return
        self.after(90, self._animar)

    def _info_fila(self, nombre: str) -> tuple[str, str, str]:
        """(icono de estado, color, texto pequeño) del botón."""
        consola = self.corriendo.get(nombre)
        if consola is not None:
            if consola.progreso:
                hecho, total, que = consola.progreso
                texto = f"Paso {hecho} de {total}" + (f" · {que}" if que else "")
            else:
                texto = "En proceso…"
            return cuadro_de_giro(), color_de_estado("proceso"), texto
        ultima = self.ejecuciones.get(nombre)
        if not ultima or ultima.get("estado") not in ESTADOS:
            return "", COLOR_TENUE, ""
        try:
            cuando = hace_cuanto(datetime.datetime.fromisoformat(ultima["hora"]))
        except (KeyError, ValueError, TypeError):
            cuando = ""
        texto = " · ".join(p for p in (cuando, ultima.get("resumen", "")) if p)
        if len(texto) > 31:         # el ancho de la barra da para ~31 letras
            texto = texto[:30] + "…"
        estado = ultima["estado"]
        return ESTADOS[estado]["icono"], color_de_estado(estado), texto

    def _refrescar_fila(self, nombre: str) -> None:
        fila = self.filas_boton.get(nombre)
        if not fila:
            return
        try:
            icono, color, texto = self._info_fila(nombre)
            fila["estado"].configure(text=icono, fg=color)
            if texto:
                fila["sub"].configure(text=texto)
                if not fila["sub"].winfo_ismapped():
                    fila["sub"].pack(fill="x")
            else:
                fila["sub"].pack_forget()
            self._dibujar_barrita(nombre, fila["barra"])
        except tk.TclError:
            pass

    def _refrescar_filas(self) -> None:
        for nombre in list(self.filas_boton):
            self._refrescar_fila(nombre)

    def _dibujar_barrita(self, nombre: str, barra: tk.Canvas) -> None:
        """La barrita fina bajo el botón: vaivén mientras corre, color al terminar."""
        consola = self.corriendo.get(nombre)
        final = self._fin_barra.get(nombre)
        if consola is None and final is None:
            barra.pack_forget()
            return
        if not barra.winfo_ismapped():
            barra.pack(fill="x", pady=(1, 0))
        barra.delete("all")
        ancho = max(barra.winfo_width(), 2)
        alto = int(barra.cget("height"))
        barra.create_rectangle(0, 0, ancho, alto, fill=COLOR_BOTON, outline="")
        if consola is None:
            barra.create_rectangle(0, 0, ancho, alto, fill=final[0], outline="")
        elif consola.progreso:
            hecho, total, _ = consola.progreso
            barra.create_rectangle(0, 0, int(ancho * hecho / total), alto,
                                   fill=COLOR_ACENTO, outline="")
        else:
            largo = max(ancho // 4, 12)
            x = int(((time.time() * 0.8) % 1) * (ancho + largo)) - largo
            barra.create_rectangle(max(x, 0), 0, min(x + largo, ancho), alto,
                                   fill=COLOR_ACENTO, outline="")

    def _ayuda_boton(self, herramienta: dict) -> str:
        """Ayuda del botón más cuándo corrió por última vez."""
        ayuda = herramienta.get("ayuda", "")
        ultima = self.ejecuciones.get(herramienta.get("nombre", ""))
        if not ultima or ultima.get("estado") not in ESTADOS:
            return ayuda
        try:
            cuando = hace_cuanto(datetime.datetime.fromisoformat(ultima["hora"]))
        except (KeyError, ValueError, TypeError):
            return ayuda
        linea = (f"Última vez: {cuando} · {ESTADOS[ultima['estado']]['texto'].lower()}"
                 f" ({formatear_duracion(ultima.get('duracion', 0))})")
        return f"{ayuda}\n{linea}" if ayuda else linea

    @staticmethod
    def _pintar(*widgets_y_color) -> None:
        *widgets, color = widgets_y_color
        for w in widgets:
            w.configure(bg=color)

    def _resaltar(self, partes, franja, encendido: bool) -> None:
        """Fila bajo el mouse: fondo más claro, texto blanco y franja morada."""
        fila, icono, texto = partes[:3]
        self._pintar(*partes, COLOR_HOVER if encendido else COLOR_BOTON)
        texto.configure(fg=COLOR_TEXTO if encendido else COLOR_TENUE)
        franja.configure(bg=COLOR_ACENTO if encendido else COLOR_BOTON)

    def _tip(self, mensaje: str) -> None:
        if getattr(self, "estado_texto", None):
            self.estado_texto.configure(text=mensaje)

    # ------------------------------------------------- herramientas.json vivo
    @staticmethod
    def _marca(ruta: str) -> float | None:
        try:
            return os.path.getmtime(ruta)
        except OSError:
            return None

    def _vigilar_config(self) -> None:
        """Si guardaste herramientas.json, los botones se rehacen solos."""
        marca = self._marca(CONFIG)
        if marca and marca != self._marca_config:
            self._marca_config = marca
            self._recargar_config()
        self.after(MS_VIGILAR_CONFIG, self._vigilar_config)

    def _recargar_config(self) -> None:
        try:
            with open(CONFIG, encoding="utf-8") as f:
                nuevas = json.load(f)
            if not isinstance(nuevas, list):
                raise ValueError("herramientas.json debe ser una lista de botones")
        except (OSError, ValueError) as exc:
            registrar("herramientas.json con error: se mantienen los botones", str(exc))
            self._tip("Los botones tienen un error de escritura (comas o comillas). "
                      "Usa «Editar botones» para corregirlo.")
            return
        self.herramientas = nuevas
        self._construir_botones()
        self.update_idletasks()
        self._recalcular_alto()
        self._colocar()
        self._tip(f"Herramientas actualizadas ({len(nuevas)})")
        registrar(f"herramientas.json recargado ({len(nuevas)} botones)")

    # ------------------------------------------------- atajo / instancia única
    def _abrir_puerta(self) -> None:
        """Escucha en 127.0.0.1 para que otra copia le avise en vez de abrirse."""
        try:
            puerta = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            puerta.bind(("127.0.0.1", PUERTO))
            puerta.listen(4)
        except OSError as exc:
            registrar("no se pudo escuchar el atajo de teclado", str(exc))
            return
        self._puerta = puerta
        threading.Thread(target=self._atender, daemon=True).start()

    def _atender(self) -> None:
        """Hilo aparte: deja el aviso en la cola y el hilo de la interfaz lo ve."""
        while self._puerta is not None:
            try:
                cliente, _ = self._puerta.accept()
                with cliente:
                    # Sin tope de espera, un programa que se conectara y no
                    # dijera nada dejaría la puerta tomada para siempre.
                    cliente.settimeout(2)
                    try:
                        mensaje = cliente.recv(64)
                    except OSError:
                        continue
                if mensaje.startswith(b"anotar"):
                    self.senales.put("anotar")
                    partes = mensaje.split()
                    if len(partes) > 1 and partes[1].isdigit() and int(partes[1]) > VERSION_CODIGO:
                        self.senales.put("reabrir")     # quien llama trae un programa más nuevo
            except OSError:
                return

    def _atender_senal(self) -> None:
        reabrir = False
        while not self.senales.empty():
            reabrir = self.senales.get_nowait() == "reabrir" or reabrir
        if reabrir:
            registrar("hay un programa más nuevo: la barra se reinicia sola")
            reabrir_barra()
            return
        self._desplegar()
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        self.entrada.focus_set()
        self._entrar_bandeja()

    # ------------------------------------------------------------- mensajería interna
    def _iniciar_mensajeria(self) -> None:
        """Pone en marcha la red de mensajes si ya hay clave de grupo; si no, queda inactiva."""
        self.mensajeria = None
        self.cola_mensajes: queue.Queue = queue.Queue()
        try:
            clave = clave_de_mensajeria()
            if not clave:
                return
            import mensajeria_red
            self.mensajeria_disponible = True
            nodo = mensajeria_red.Nodo(nombre_en_mensajeria(), clave, RUTA_MENSAJES,
                                       al_recibir=self.cola_mensajes.put)
            nodo.iniciar()
            self.mensajeria = nodo
            registrar(f"mensajería iniciada como «{nodo.nombre}»")
        except Exception as exc:  # noqa: BLE001
            self.mensajeria = None
            registrar("no se pudo iniciar la mensajería", f"{exc}\n{traceback.format_exc()}")

    def detener_mensajeria(self) -> None:
        nodo, self.mensajeria = getattr(self, "mensajeria", None), None
        if nodo is not None:
            try:
                nodo.detener()
            except Exception:  # noqa: BLE001
                pass
        self.actualizar_mensajes()

    def reiniciar_mensajeria(self) -> None:
        self.detener_mensajeria()
        self._iniciar_mensajeria()
        self.actualizar_mensajes()

    def abrir_mensajes(self) -> None:
        self._desplegar()
        VentanaMensajes(self)

    def actualizar_mensajes(self) -> None:
        """Pinta en el panel cuántos mensajes hay sin leer (o no pinta nada si está inactiva)."""
        etiqueta = getattr(self, "mensajes_texto", None)
        if etiqueta is None:
            return
        nodo = getattr(self, "mensajeria", None)
        try:
            if nodo is None:
                etiqueta.configure(text="")
                return
            sin_leer = nodo.no_leidos()
            if sin_leer:
                etiqueta.configure(text=f"💬 {sin_leer} mensaje{'s' if sin_leer != 1 else ''} nuevo"
                                        f"{'s' if sin_leer != 1 else ''}", fg=COLOR_ACENTO)
            else:
                etiqueta.configure(text=f"💬 Mensajes · {len(nodo.en_linea())} en línea", fg=COLOR_TENUE)
        except tk.TclError:
            pass

    def _vigilar_mensajes(self) -> None:
        """Cada par de segundos: avisa de lo que llegó y deja al día el contador."""
        try:
            while True:
                try:
                    nuevo = self.cola_mensajes.get_nowait()
                except queue.Empty:
                    break
                Aviso(self, "proceso", f"Mensaje de {nuevo['de']}", nuevo["texto"][:140],
                      al_pulsar=self.abrir_mensajes)
            self.actualizar_mensajes()
        except Exception:  # noqa: BLE001
            registrar("fallo al vigilar los mensajes", traceback.format_exc())
        self.after(2000, self._vigilar_mensajes)

    def destroy(self) -> None:
        try:
            self.detener_mensajeria()
        except Exception:  # noqa: BLE001
            pass
        puerta, self._puerta = self._puerta, None
        if puerta is not None:
            try:
                puerta.close()
            except OSError:
                pass
        super().destroy()

    def report_callback_exception(self, tipo, valor, rastro) -> None:  # noqa: N802
        """Cualquier error de la interfaz queda en el log en vez de perderse."""
        registrar("error dentro de la barra",
                  "".join(traceback.format_exception(tipo, valor, rastro)))

    # --------------------------------------------------------- plegar/desplegar
    def _colocar(self) -> None:
        """Ubica la ventana según el lado y si está desplegada o no."""
        izq, arriba, der, abajo = self._area()
        if self.desplegada:
            ancho, alto = self.ancho, self.alto
        else:
            ancho, alto = self.ancho_lengueta, self.alto_lengueta
        # Nunca más alta que la pantalla ni con el borde inferior fuera de ella.
        alto = min(alto, abajo - arriba)
        y = max(arriba, min(self.y, abajo - alto))
        x = der - ancho if self.lado == "derecha" else izq
        self.geometry(f"{ancho}x{alto}+{x}+{y}")
        self._pintar_indicador()

    def _area(self) -> tuple[int, int, int, int]:
        """Área útil del monitor donde vive la barra (el principal por defecto)."""
        todos = monitores()
        for m in todos:
            if (m[0], m[1]) == self.monitor:
                return m
        if todos:
            return todos[0]
        return (0, 0, self.winfo_screenwidth(), self.winfo_screenheight())

    def _recalcular_alto(self) -> None:
        """El alto de la barra, sin pasarse de la pantalla.

        En los notebook del colegio la pantalla mide 720 px y la barra con
        todos los botones pasa de 1100: lo que sobraba quedaba fuera y no se
        podía pulsar. Cuando no cabe, el panel se desplaza con la rueda (tras
        hacer clic en la barra), con RePág/AvPág o arrastrando la barrita.
        """
        self.alto_contenido = max(self.panel.winfo_reqheight(), int(120 * self.escala))
        _izq, arriba, _der, abajo = self._area()
        disponible = abajo - arriba
        self.alto = max(min(self.alto_contenido, disponible), int(120 * self.escala))
        antes = getattr(self, "con_scroll", False)
        self.con_scroll = self.alto_contenido > self.alto
        tope = max(0, self.alto_contenido - self.alto)
        self.desplazamiento = min(getattr(self, "desplazamiento", 0), tope)
        if self.desplegada and (self.con_scroll != antes or self.con_scroll):
            self._ocultar_panel(antes)
            self._mostrar_panel()

    def _mostrar_panel(self) -> None:
        if self.con_scroll:
            self.panel.place(x=0, y=-self.desplazamiento, relwidth=1,
                             height=self.alto_contenido)
        else:
            self.panel.pack(fill="both", expand=True)

    def _ocultar_panel(self, con_scroll: bool | None = None) -> None:
        if self.con_scroll if con_scroll is None else con_scroll:
            self.panel.place_forget()
        else:
            self.panel.pack_forget()

    def _tomar_foco(self, evento) -> None:
        """Con un clic dentro de la barra, la rueda del mouse empieza a llegarle."""
        try:
            if evento.widget.winfo_toplevel() is self and not isinstance(evento.widget, tk.Entry):
                self.focus_force()
        except (tk.TclError, KeyError, AttributeError):
            pass

    def _desplazar(self, delta: float) -> None:
        """Mueve el contenido `delta` píxeles (positivo = hacia abajo)."""
        if not self.desplegada or not self.con_scroll:
            return
        tope = self.alto_contenido - self.alto
        nuevo = int(min(max(self.desplazamiento + delta, 0), tope))
        if nuevo != self.desplazamiento:
            self.desplazamiento = nuevo
            self.panel.place_configure(y=-self.desplazamiento)
            self._pintar_indicador()

    def _rodar(self, evento) -> None:
        """Desplaza el panel con la rueda, cuando no cabe entero."""
        try:
            if evento.widget.winfo_toplevel() is not self:
                return
        except (tk.TclError, KeyError, AttributeError):
            return
        pasos = evento.delta // 120 if evento.delta else 0
        self._desplazar(-pasos * int(70 * self.escala))

    def _construir_indicador(self) -> None:
        """Barrita fina a la derecha que muestra y permite arrastrar el desplazamiento."""
        self.indicador = tk.Canvas(self, width=max(6, int(8 * self.escala)), bd=0,
                                   highlightthickness=0, bg=COLOR_FONDO, cursor="hand2")
        self.indicador.bind("<Button-1>", self._arrastrar_indicador)
        self.indicador.bind("<B1-Motion>", self._arrastrar_indicador)

    def _pintar_indicador(self) -> None:
        indicador = getattr(self, "indicador", None)
        if indicador is None:
            return
        if not (self.desplegada and getattr(self, "con_scroll", False)):
            indicador.place_forget()
            return
        indicador.place(relx=1.0, x=0, y=0, anchor="ne", relheight=1.0)
        indicador.delete("all")
        alto = max(self.alto, 1)
        largo = max(int(alto * alto / self.alto_contenido), 24)
        tope = max(self.alto_contenido - self.alto, 1)
        arriba = int((alto - largo) * self.desplazamiento / tope)
        ancho = int(indicador.cget("width"))
        indicador.create_rectangle(1, arriba, ancho - 1, arriba + largo,
                                   fill=COLOR_ACENTO, outline="")
        tk.Misc.lift(indicador)      # Canvas.lift es otra cosa (tag_raise)

    def _arrastrar_indicador(self, evento) -> None:
        alto = max(self.alto, 1)
        largo = max(int(alto * alto / self.alto_contenido), 24)
        fraccion = min(max((evento.y - largo / 2) / max(alto - largo, 1), 0), 1)
        self._desplazar(fraccion * (self.alto_contenido - self.alto) - self.desplazamiento)

    def _desplegar(self) -> None:
        if self.desplegada:
            return
        self.lengueta.pack_forget()
        self.desplegada = True
        self._mostrar_panel()
        self._actualizar_saludo()
        self._colocar()
        try:
            self.focus_force()      # con el foco, la rueda del mouse funciona
        except tk.TclError:
            pass

    def _actualizar_saludo(self) -> None:
        """Se refresca al desplegarse: así todo calza con la hora real."""
        ahora = datetime.datetime.now()
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                 "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        self.saludo.configure(text=saludo(ahora))
        self.fecha.configure(text=f"{DIAS[ahora.weekday()]} {ahora.day} de "
                                  f"{meses[ahora.month - 1]} · {ahora:%H:%M}")
        self._refrescar_agenda()
        self._refrescar_bandeja()
        # Relee la lista por si la editaste con la barra cerrada.
        if getattr(self, "items_lista", None) is not None:
            self._refrescar_lista()
        # Al abrirla siempre se muestra lo último, y si está vencido se revisa.
        if getattr(self, "libro_texto", None) is not None:
            if self._estado_vencido():
                self._revisar_libro()
            self._refrescar_firmas()

    def _plegar(self, forzar: bool = False) -> None:
        if self._tour is not None:          # durante el recorrido la barra se queda abierta
            return
        if not self.desplegada or (not forzar and (self.fijada or self._anotando())):
            return
        self._ocultar_panel()
        self.lengueta.pack(fill="both", expand=True)
        self.desplegada = False
        self._colocar()

    def _vigilar(self) -> None:
        """Pliega la barra cuando el mouse se va (abrir es solo con clic)."""
        try:
            if not self.senales.empty():
                self._atender_senal()
            if self.desplegada and not self.fijada:
                px, py = self.winfo_pointerxy()
                x, y = self.winfo_x(), self.winfo_y()
                ancho, alto = self.winfo_width(), self.winfo_height()
                dentro = (x - 8 <= px <= x + ancho + 8) and (y - 8 <= py <= y + alto + 8)
                if dentro:
                    self._fuera = 0
                else:
                    self._fuera += 1
                    if self._fuera >= CICLOS_FUERA_PARA_PLEGAR:
                        self._plegar()
        except tk.TclError:
            return
        self.after(MS_VIGILAR_MOUSE, self._vigilar)

    def _al_frente(self) -> None:
        """Windows baja el 'siempre encima' cuando otra app se abre completa."""
        try:
            self.attributes("-topmost", True)
            self.lift()
        except tk.TclError:
            return
        self.after(MS_AL_FRENTE, self._al_frente)

    def alternar_fijada(self) -> None:
        self.fijada = not self.fijada
        self._pintar_fijada()
        self._guardar_estado()

    def _pintar_fijada(self) -> None:
        self.boton_fijar.configure(fg=COLOR_TEXTO if self.fijada else COLOR_TENUE)

    # ------------------------------------------------------------------ mover
    def _tomar(self, evento) -> None:
        self._dx, self._dy = evento.x_root - self.winfo_x(), evento.y_root - self.winfo_y()

    def _mover(self, evento) -> None:
        # Se pega al monitor donde esté el cursor y, dentro de él, al borde más cercano.
        izq, arriba, der, abajo = self._area()
        for m in monitores():
            if m[0] <= evento.x_root < m[2] and m[1] <= evento.y_root < m[3]:
                izq, arriba, der, abajo = m
                self.monitor = (m[0], m[1])
                break
        self.y = max(arriba, min(evento.y_root - self._dy, abajo - self.alto_lengueta))
        self.lado = "derecha" if evento.x_root > (izq + der) / 2 else "izquierda"
        self._recalcular_alto()
        self._colocar()

    def _soltar(self, _evento=None) -> None:
        self._guardar_estado()

    # ----------------------------------------------------------------- estado
    def _leer_estado(self) -> dict:
        try:
            with open(ESTADO, encoding="utf-8") as f:
                datos = json.load(f)
            return datos if isinstance(datos, dict) else {}
        except (OSError, ValueError):
            return {}

    def _guardar_estado(self) -> None:
        try:
            escribir_atomico(ESTADO, json.dumps(
                {"lado": self.lado, "y": self.y, "fijada": self.fijada,
                 "monitor_x": self.monitor[0], "monitor_y": self.monitor[1],
                 "lista_abierta": getattr(self, "lista_abierta", False)}))
        except OSError:
            pass


def main() -> None:
    # Si ya hay una barra abierta, esta copia solo le avisa y se va. Así el
    # atajo de teclado (Ctrl+Alt+A) usa siempre la misma barra.
    if avisar_a_la_barra_abierta():
        return
    ajustar_escalado()
    if "--sin-sonido" not in sys.argv:
        sonar_al_abrir()
    if MOTIVO_SIN_SOLTAR:
        registrar("la barra abre sin soltar archivos (tkdnd no cargó)", MOTIVO_SIN_SOLTAR)
    # Con pythonw no hay consola: si herramientas.json quedó mal escrito hay que
    # avisarlo con una ventana, o la barra simplemente no aparecería.
    try:
        with open(CONFIG, encoding="utf-8") as f:
            herramientas = json.load(f)
        Barra(herramientas).mainloop()
    except Exception as exc:  # noqa: BLE001
        registrar("la barra no pudo abrirse", traceback.format_exc())
        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror("Barra Profe",
                             "No se pudo abrir la barra.\n\n"
                             f"Revisa {os.path.basename(CONFIG)} (comas de más, "
                             f"comillas sin cerrar o un botón sin «nombre»).\n\n{exc}")
        raiz.destroy()


if __name__ == "__main__":
    main()
