"""
Deja estas herramientas listas en el PC de un profesor.

Hace, en orden:
  1. comprueba que estén los complementos de Python que se necesitan,
  2. llama a configurar.py si todavía no hay perfil,
  3. crea la carpeta "Subir a Webclass" con una subcarpeta por curso,
  4. deja los accesos directos en el escritorio,
  5. crea las dos tareas programadas (asignar clases y subir recursos).

Se ejecuta una vez, desde la carpeta de los scripts:

    python instalar.py

Todo lo que hace es reversible: los accesos directos se borran a mano y las
tareas con  schtasks /delete /tn <nombre>  (o desde el Programador de tareas).
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import subprocess
import sys

import rutas
from barra_utiles import guardar_botones, leer_botones

CARPETA = rutas.CODIGO        # donde están los scripts o el .exe
PERFILES = rutas.PERFILES     # personal\perfiles\
GENERADOS = rutas.DATOS       # datos\: lanzadores, registros y logs
BUZON = rutas.BUZON
EMPAQUETADO = getattr(sys, "frozen", False)   # ¿se está corriendo desde webclass.exe?
PY = sys.executable                       # python.exe (o el propio .exe si va empaquetado)
PYW = PY.replace("python.exe", "pythonw.exe")


def orden(subcomando: str, *opciones: str) -> tuple[str, list[str]]:
    """(programa, argumentos) para lanzar una herramienta.

    Empaquetado se llama al propio .exe con su subcomando; sin empaquetar, a
    python.exe con el script correspondiente.

    Los argumentos van en una lista, nunca en una cadena: las carpetas de esto
    llevan espacios ("Barra Profe", "Webclass Asignar") y partir el texto por
    espacios dejaba la ruta hecha pedazos.
    """
    scripts = {"asignar": "webclass_tareas.py", "subir": "subir_carpeta.py",
               "libro": "webclass_libro.py", "configurar": "configurar.py"}
    if EMPAQUETADO:
        return PY, [subcomando, *opciones]
    return PY, [os.path.join(CARPETA, scripts[subcomando]), *opciones]


def como_texto(programa: str, argumentos: list[str]) -> str:
    """La misma orden escrita para un .bat, con comillas donde hacen falta."""
    partes = [f'"{a}"' if " " in a else a for a in argumentos]
    return " ".join([f'"{programa}"', *partes])

TAREA_ASIGNAR = "WebclassAsignacionDiaria"
TAREA_SUBIR = "WebclassSubirRecursos"


def paso(texto: str) -> None:
    print(f"\n== {texto}")


def revisar_complementos() -> None:
    if EMPAQUETADO:
        paso("Complementos")
        print("   Van dentro del ejecutable: no hay que instalar nada.")
        return
    paso("Revisando complementos de Python")
    necesarios = [("requests", "requests"), ("keyring", "keyring"), ("cryptography", "cryptography")]
    if os.path.isfile(os.path.join(CARPETA, "barra_profe.pyw")):
        # Solo la barra lo usa, para arrastrarle archivos encima.
        necesarios.append(("tkinterdnd2", "tkinterdnd2"))
    if os.path.isfile(os.path.join(CARPETA, "planificador", "servidor.py")):
        # El planificador con IA viaja dentro de herramienta\planificador y necesita estos complementos.
        necesarios += [("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("multipart", "python-multipart"),
                       ("openai", "openai"), ("openpyxl", "openpyxl"), ("pypdf", "pypdf"), ("docx", "python-docx"),
                       ("pptx", "python-pptx"), ("PIL", "Pillow"), ("youtube_transcript_api", "youtube-transcript-api")]
    faltan = []
    for modulo, paquete in necesarios:
        try:
            __import__(modulo)
            print(f"   {paquete}: ok")
        except ImportError:
            faltan.append(paquete)
    if faltan:
        print(f"   Faltan: {', '.join(faltan)}. Instalando…")
        try:
            subprocess.run([PY, "-m", "pip", "install", *faltan], check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            # Sin internet o con la red del colegio bloqueando pip: se sigue igual. Los botones y el resto se arreglan
            # igual; el planificador avisa qué falta cuando se abre.
            print(f"   No se pudieron instalar ({exc}). Se sigue con lo demás: vuelve a correr ACTUALIZAR.bat con "
                  "internet para completarlos.")


def limpiar_versiones_viejas() -> None:
    """Borra los scripts que sobraron de una versión anterior.

    Al copiar una versión nueva encima de otra (por pendrive, por ejemplo) los
    archivos que ya no existen se quedan ahí: conviven dos versiones y no se
    sabe cuál manda. ARCHIVOS.txt viene en el paquete y dice qué trae esta.
    """
    lista = os.path.join(CARPETA, "ARCHIVOS.txt")
    if not os.path.isfile(lista):
        return
    try:
        with open(lista, encoding="utf-8-sig") as f:
            deben_estar = {l.strip().lower() for l in f if l.strip()}
    except OSError:
        return
    if len(deben_estar) < 5:        # lista sospechosamente corta: no se borra nada
        return
    paso("Restos de versiones anteriores")
    sobran = [a for a in sorted(os.listdir(CARPETA))
              if a.lower().endswith((".py", ".pyw", ".ps1"))
              and a.lower() not in deben_estar]
    for archivo in sobran:
        try:
            os.remove(os.path.join(CARPETA, archivo))
            print(f"   se quita: {archivo}")
        except OSError as exc:
            print(f"   no se pudo quitar {archivo}: {exc}")
    cache = os.path.join(CARPETA, "__pycache__")
    if os.path.isdir(cache):
        import shutil
        shutil.rmtree(cache, ignore_errors=True)
    if not sobran:
        print("   no hay: la carpeta está limpia.")


def botones_propios() -> None:
    """Le da a este docente su propia copia de los botones.

    La barra usa personal\\herramientas.json si existe, y si no la plantilla
    de herramienta\\. Como las actualizaciones reemplazan herramienta\\, quien
    editara la plantilla perdía sus cambios: con la copia en personal\\ eso no
    vuelve a pasar.
    """
    propio = os.path.join(rutas.PERSONAL, "herramientas.json")
    plantilla = os.path.join(CARPETA, "herramientas.json")
    if os.path.isfile(propio) or not os.path.isfile(plantilla):
        return
    paso("Botones de la barra")
    os.makedirs(rutas.PERSONAL, exist_ok=True)
    import shutil
    shutil.copy2(plantilla, propio)
    print(f"   Tu copia: {propio}")
    print("   Edítala a gusto: las actualizaciones ya no la tocan.")


def planificador_en_botones(personal: str | None = None) -> bool:
    """Deja el botón «Planificar» de este docente apuntando al planificador con IA (si viaja en esta carpeta).

    Cada docente tiene su copia de herramientas.json en personal\\, y las actualizaciones no la reemplazan: sin esto,
    quien ya tenía la barra seguiría con el botón de antes. Es idempotente: si ya está, no hace nada.
    Devuelve True si cambió algo.
    """
    if not os.path.isfile(os.path.join(CARPETA, "planificador", "lanzar_planificador.pyw")):
        return False
    propio = os.path.join(personal or rutas.PERSONAL, "herramientas.json")
    if not os.path.isfile(propio):
        return False                       # sin copia propia se usa la plantilla, que ya trae el botón nuevo
    try:
        botones, formato = leer_botones(propio)
    except (OSError, ValueError):
        return False
    destino = "%BARRA%\\planificador\\lanzar_planificador.pyw"
    cambio = False
    for i, b in enumerate(botones):
        if b.get("tipo") == "planificar" and not b.get("destino") and b.get("nombre") != "Planificar en bloque":
            b["destino"] = destino
            b["ayuda"] = "Abre el asistente de IA: redacta la clase y la envía a Webclass con su recurso, OA y DUA"
            if not any(x.get("nombre") == "Planificar en bloque" for x in botones):
                botones.insert(i + 1, {"grupo": b.get("grupo", "Webclass"), "nombre": "Planificar en bloque", "icono": "📋",
                                       "tipo": "planificar", "destino": "",
                                       "ayuda": "Crea clases vacías según tu horario, importa una planilla o marca OA y DUA en lote"})
            cambio = True
            break
    if not cambio:
        return False
    guardar_botones(propio, botones, formato, copia=propio + ".antes-del-planificador")   # por si prefiere volver atrás
    paso("Botón «Planificar»")
    print("   Ahora abre el asistente de IA. La ventana de antes quedó en «Planificar en bloque».")
    return True


# Botones de la plantilla que se suman a la copia personal si faltan. «Planificar» y «Planificar en bloque» también:
# quien instaló antes de que existieran (o los perdió) nunca los recibía, porque solo se convertía uno que ya estuviera.
BOTONES_NUEVOS = ("Planificar", "Planificar en bloque", "Escala de notas", "Días sin clases")


def botones_nuevos_en_propios(personal: str | None = None) -> list[str]:
    """Suma a la copia personal de herramientas.json los botones nuevos de la plantilla (por nombre), sin tocar los demás.

    Las actualizaciones no reemplazan personal\\herramientas.json (ahí van los cambios de cada docente), así que un botón
    nuevo de la plantilla no le llegaría a quien ya tenía la barra. Entra justo después del botón que lo antecede en la
    plantilla y solo si el docente no lo tiene ya (si lo borró a propósito, vuelve a aparecer: se quita de nuevo a mano).
    Devuelve los nombres agregados.
    """
    propio = os.path.join(personal or rutas.PERSONAL, "herramientas.json")
    plantilla = os.path.join(CARPETA, "herramientas.json")
    if not (os.path.isfile(propio) and os.path.isfile(plantilla)):
        return []
    try:
        botones, formato = leer_botones(propio)
        modelo, _ = leer_botones(plantilla)
    except (OSError, ValueError):
        return []
    tienen = {b.get("nombre") for b in botones}
    agregados = []
    for nombre in BOTONES_NUEVOS:
        boton = next((b for b in modelo if b.get("nombre") == nombre), None)
        if boton is None or nombre in tienen:
            continue
        anterior = modelo[modelo.index(boton) - 1].get("nombre") if modelo.index(boton) else None
        lugar = next((i + 1 for i, b in enumerate(botones) if b.get("nombre") == anterior), len(botones))
        botones.insert(lugar, boton)
        agregados.append(nombre)
    if not agregados:
        return []
    guardar_botones(propio, botones, formato, copia=propio + ".antes-de-actualizar")   # una sola copia, la del primer cambio
    paso("Botones nuevos")
    for nombre in agregados:
        print(f"   Se agregó «{nombre}» a tu barra.")
    return agregados


BOTONES_RETIRADOS = ("Mensajes del equipo",)   # botones que ya no van en la barra (el código sigue en barra_profe.pyw)


def botones_retirados_de_propios(personal: str | None = None) -> list[str]:
    """Quita de la copia personal de herramientas.json los botones que se retiraron de la plantilla.

    Solo el botón: la herramienta sigue en el programa (por ejemplo, la mensajería interna) por si se retoma. Hace una copia de
    seguridad antes de cambiar nada y devuelve los nombres quitados.
    """
    propio = os.path.join(personal or rutas.PERSONAL, "herramientas.json")
    if not os.path.isfile(propio):
        return []
    try:
        botones, formato = leer_botones(propio)
    except (OSError, ValueError):
        return []
    quitados = [b["nombre"] for b in botones if b.get("nombre") in BOTONES_RETIRADOS]
    if not quitados:
        return []
    botones = [b for b in botones if b.get("nombre") not in BOTONES_RETIRADOS]
    guardar_botones(propio, botones, formato, copia=propio + ".antes-de-actualizar")
    paso("Botones retirados")
    for nombre in quitados:
        print(f"   Se quitó «{nombre}» de tu barra (la herramienta sigue en el programa).")
    return quitados


# Arreglos de la plantilla que también llegan a la copia de cada docente: (campo, texto de antes, texto nuevo).
# Solo se cambia lo que sigue exactamente como venía; si el docente lo editó, se respeta.
TEXTOS_CORREGIDOS = (
    ("nombre", "A donde asigno cada unidad", "A dónde asigno cada unidad"),
    ("ayuda", "Pone al dia el libro de un mes completo", "Pone al día el libro de un mes completo"),
    ("pregunta", "Recorre los dias habiles de ese mes que ya pasaron y declara OA, leccionario y asistencia donde "
                 "falte. Tarda varios minutos y escribe en Webclass.",
     "Recorre los días hábiles de ese mes que ya pasaron y declara OA, leccionario y asistencia donde falte. "
     "Tarda varios minutos y escribe en Webclass."),
    ("ayuda", "Pasa a la siguiente paleta de colores", "Elige el color de la barra (queda guardado para tu perfil)"),
    ("ayuda", "Deja aqui un archivo llamado inicio.mp3 (o inicio.wav); borralo para silenciarla",
     "Deja aquí un archivo llamado inicio.mp3 (o inicio.wav); bórralo para silenciarla"),
)


def meses_fijos(opciones) -> bool:
    """¿Es la lista de meses escrita a mano que traía «Completar mes atrasado» (valores tipo 10/2026)?"""
    return (isinstance(opciones, list) and bool(opciones)
            and all(isinstance(o, dict) and re.fullmatch(r"\d{2}/\d{4}", str(o.get("valor", ""))) for o in opciones))


def botones_corregidos_en_propios(personal: str | None = None) -> list[str]:
    """Lleva a la copia personal de herramientas.json los arreglos de la plantilla, sin pisar lo que el docente cambió:
    los meses de «Completar mes atrasado» pasan a calcularse solos (antes eran fijos de 2026) y los textos sin tildes o
    desactualizados se corrigen. Devuelve los nombres de los botones que cambiaron."""
    propio = os.path.join(personal or rutas.PERSONAL, "herramientas.json")
    if not os.path.isfile(propio):
        return []
    try:
        botones, formato = leer_botones(propio)
    except (OSError, ValueError):
        return []
    cambiados = []
    for b in botones:
        antes = dict(b)
        if b.get("tipo") == "preguntar" and "--mes {valor}" in str(b.get("destino", "")) and meses_fijos(b.get("opciones")):
            b["opciones"] = "meses"
        for campo, viejo, nuevo in TEXTOS_CORREGIDOS:
            if b.get(campo) == viejo:
                b[campo] = nuevo
        if b != antes:
            cambiados.append(b.get("nombre", "(sin nombre)"))
    if not cambiados:
        return []
    guardar_botones(propio, botones, formato, copia=propio + ".antes-de-actualizar")
    paso("Botones corregidos")
    for nombre in cambiados:
        print(f"   «{nombre}» quedó al día.")
    return cambiados


def mostrar_versiones() -> None:
    """Imprime la versión de Barra y la del planificador (si viaja en esta carpeta)."""
    from barra_utiles import leer_version
    barra = leer_version(CARPETA) or "sin número"
    plan = os.path.join(CARPETA, "planificador")
    print(f"Barra Profe: versión {barra}")
    if os.path.isdir(plan):
        print(f"Planificador con IA: versión {leer_version(plan) or 'sin número'}")


def perfil_disponible() -> str | None:
    if not os.path.isdir(PERFILES):
        return None
    archivos = [a for a in sorted(os.listdir(PERFILES)) if a.endswith(".json")]
    return archivos[0][:-5] if archivos else None


def configurar_perfil() -> str:
    paso("Perfil del profesor")
    clave = perfil_disponible()
    if clave:
        print(f"   Ya existe el perfil «{clave}».")
        if input("   ¿Usar ese perfil? [S/n]: ").strip().lower() in ("", "s", "si", "sí"):
            return clave
    print("   Se abrirá la configuración: pedirá tu RUT y tu contraseña de Webclass.")
    print("   La contraseña queda en el Administrador de credenciales de Windows,")
    print("   no se escribe en ningún archivo.\n")
    programa, argumentos = orden("configurar")
    subprocess.run([programa, *argumentos], check=True)
    clave = perfil_disponible()
    if not clave:
        raise SystemExit("No quedó ningún perfil configurado.")
    return clave


def crear_carpetas(clave: str) -> None:
    """Una carpeta por nivel, de 1° básico a 4° medio, más _subidos y _errores."""
    paso("Carpeta para subir recursos")
    sys.path.insert(0, CARPETA)
    import subir_carpeta as sc          # usa la misma lista de niveles que el subidor

    os.makedirs(BUZON, exist_ok=True)
    for sub in [*sc.NIVELES_CARPETA, "_subidos", "_errores"]:
        os.makedirs(os.path.join(BUZON, sub), exist_ok=True)
    print(f"   {BUZON}")
    print(f"   Subcarpetas: {', '.join(sc.NIVELES_CARPETA)}")


LANZADORES = {
    "ejecutar_asignacion.bat": ("Asignando clases de HOY (y pendientes de 7 dias)",
                                "webclass_tareas.py", "--hoy --dias-atras 7"),
    "registrar_libro.bat": ("Registrando el libro de clases de HOY",
                            "webclass_libro.py", ""),
    "informe_libro.bat": ("Informe del libro de clases (mes actual)",
                          "webclass_libro.py", "--informe"),
    "subir_recursos.bat": ("Subiendo recursos al banco de Webclass",
                           "subir_carpeta.py", ""),
}


def lanzadores(clave: str) -> None:
    """Escribe los .bat de los accesos directos con el Python de ESTE equipo.

    Antes venían con la ruta de Python escrita a mano, así que se rompían en
    cuanto el otro docente tenía otra versión instalada.
    """
    if EMPAQUETADO:
        return
    paso("Lanzadores")
    os.makedirs(GENERADOS, exist_ok=True)   # en un PC nuevo todavía no existe
    for archivo, (titulo, script, opciones) in LANZADORES.items():
        # Los .bat se generan y se regeneran: van a datos\, no entre el código.
        # Corren desde la carpeta del código para que los imports se encuentren.
        with open(os.path.join(GENERADOS, archivo), "w",
                  encoding="ascii", errors="replace", newline="\r\n") as f:
            f.write("@echo off\r\n"
                    "REM Lo genera instalar.py con el Python de este equipo.\r\n"
                    "chcp 65001 >nul\r\n"
                    "set PYTHONIOENCODING=utf-8\r\n"
                    f'cd /d "{CARPETA}"\r\n'
                    "echo.\r\n"
                    "echo ==========================================\r\n"
                    f"echo   {titulo}\r\n"
                    "echo ==========================================\r\n"
                    "echo.\r\n"
                    f'"{PY}" {script} {opciones} --perfil {clave}\r\n'
                    "echo.\r\n"
                    "pause\r\n")
        print(f"   {archivo}")


def carpeta_escritorio(clave: str) -> str:
    """Escritorio\\Webclass - <Nombre>: todo junto en vez de accesos sueltos.

    Lleva el nombre del docente porque en los PC de sala de profesores hay
    varios instalados y, si no, no se sabe de quién es cada acceso.
    """
    nombre = clave.title()
    try:
        with open(os.path.join(PERFILES, f"{clave}.json"), encoding="utf-8-sig") as f:
            nombre = (json.load(f).get("nombre") or nombre).strip()
    except (OSError, ValueError):
        pass
    destino = os.path.join(os.path.expanduser("~"), "Desktop", f"Webclass - {nombre}")
    os.makedirs(destino, exist_ok=True)
    return destino


def accesos_directos(clave: str) -> None:
    paso("Accesos directos en el escritorio")
    escritorio = carpeta_escritorio(clave)
    print(f"   {escritorio}")
    if EMPAQUETADO:
        atajos = {
            "Asignar clases": (PY, f"asignar --hoy --dias-atras 7 --perfil {clave}"),
            "Registrar libro de hoy": (PY, f"libro --perfil {clave}"),
            "Informe del libro": (PY, f"libro --informe --perfil {clave}"),
            "Subir recursos": (PY, f"subir --perfil {clave}"),
            "Carpeta Subir a Webclass": (BUZON, ""),
        }
    else:
        atajos = {
            "Asignar clases": (os.path.join(GENERADOS, "ejecutar_asignacion.bat"), ""),
            "Registrar libro de hoy": (os.path.join(GENERADOS, "registrar_libro.bat"), ""),
            "Informe del libro": (os.path.join(GENERADOS, "informe_libro.bat"), ""),
            "Subir recursos": (os.path.join(GENERADOS, "subir_recursos.bat"), ""),
            "Carpeta Subir a Webclass": (BUZON, ""),
        }
    lineas = []
    for nombre, (destino, argumentos) in atajos.items():
        if not os.path.exists(destino):
            print(f"   (se omite «{nombre}»: no existe {os.path.basename(destino)})")
            continue
        enlace = os.path.join(escritorio, f"{nombre}.lnk")
        extra = f'$a.Arguments="{argumentos}"; ' if argumentos else ""
        lineas.append(
            f'$a=$s.CreateShortcut("{enlace}"); $a.TargetPath="{destino}"; {extra}'
            f'$a.WorkingDirectory="{CARPETA}"; $a.Save();')
        print(f"   {nombre}")
    if lineas:
        # Un salto de línea entre órdenes: PowerShell no acepta dos asignaciones
        # seguidas en la misma línea sin separador.
        guion = "$s=New-Object -ComObject WScript.Shell;\n" + "\n".join(lineas)
        subprocess.run(["powershell", "-NoProfile", "-Command", guion], check=True)


def barra_al_inicio() -> None:
    """Si la barra flotante viene en la misma carpeta, la deja al iniciar Windows."""
    exe = os.path.join(CARPETA, "Barra Profe.exe")
    script = os.path.join(CARPETA, "barra_profe.pyw")
    if os.path.isfile(exe):
        destino, argumentos = exe, ""
    elif os.path.isfile(script):
        destino, argumentos = PYW, f'"{script}"'   # pythonw: sin ventana negra
    else:
        return
    paso("Barra flotante")
    inicio = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                          "Start Menu", "Programs", "Startup")
    enlace = os.path.join(inicio, "Barra Profe.lnk")
    extra = f'$a.Arguments={chr(39)}{argumentos}{chr(39)};\n' if argumentos else ""
    guion = ('$s=New-Object -ComObject WScript.Shell;\n'
             f'$a=$s.CreateShortcut("{enlace}");\n'
             f'$a.TargetPath="{destino}";\n'
             f'{extra}'
             f'$a.WorkingDirectory="{CARPETA}";\n'
             '$a.Save();')
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", guion], check=True)
        print("   Se abrirá sola al encender el PC.")
    except subprocess.CalledProcessError as exc:
        print(f"   No se pudo dejar al inicio ({exc}). Ábrela a mano cuando quieras.")


def retirar_tarea_asignar() -> bool:
    """Quita la tarea de las 16:00 («asignar las clases del día»), que ya no se usa: la asignación se hace con el
    botón de la barra. Es seguro repetirlo. Devuelve True si había una tarea y se eliminó."""
    try:
        r = subprocess.run(["schtasks", "/delete", "/f", "/tn", TAREA_ASIGNAR], capture_output=True, text=True)
    except OSError:
        return False
    for resto in ("tarea_asignacion.bat",):                  # el lanzador que generaba el instalador
        try:
            os.remove(os.path.join(GENERADOS, resto))
        except OSError:
            pass
    if r.returncode == 0:
        print(f"   {TAREA_ASIGNAR}: eliminada (las clases se asignan con el botón de la barra)")
    return r.returncode == 0


def tareas_programadas(clave: str) -> None:
    paso("Tareas programadas")
    retirar_tarea_asignar()
    if EMPAQUETADO:
        # El .exe no tiene versión "sin consola": la tarea corre oculta igual,
        # porque el Programador la lanza sin sesión interactiva.
        subir = como_texto(PY, ["subir", "--perfil", clave])
    else:
        subir = como_texto(PYW, [os.path.join(CARPETA, "subir_carpeta.py"),
                                 "--perfil", clave])
    ordenes = [
        ["schtasks", "/create", "/f", "/tn", TAREA_SUBIR, "/sc", "minute", "/mo", "10",
         "/tr", subir],
    ]
    for tarea in ordenes:
        try:
            subprocess.run(tarea, check=True, capture_output=True, text=True)
            print(f"   {tarea[4]}: creada")
        except subprocess.CalledProcessError as exc:
            print(f"   {tarea[4]}: no se pudo crear ({(exc.stderr or '').strip()[:80]})")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sin-tareas", action="store_true",
                   help="No crea las tareas programadas (solo carpetas y accesos).")
    p.add_argument("--sin-accesos", action="store_true",
                   help="No toca los accesos directos del escritorio.")
    p.add_argument("--buzon", metavar="RUTA",
                   help="Otra carpeta para dejar los archivos a subir (para pruebas).")
    p.add_argument("--actualizar", action="store_true",
                   help="Solo pone el código al día: limpia restos de versiones "
                        "anteriores y revisa complementos. No pregunta nada ni toca "
                        "el perfil, los botones, los accesos ni las tareas.")
    args = p.parse_args()

    print("=== Instalación de las herramientas de Webclass ===")
    print(f"Usuario de Windows: {getpass.getuser()}")
    mostrar_versiones()
    print(f"Python: {PY}")
    if args.buzon:
        global BUZON
        BUZON = os.path.abspath(args.buzon)
    limpiar_versiones_viejas()
    revisar_complementos()
    botones_propios()
    planificador_en_botones()
    botones_nuevos_en_propios()
    botones_retirados_de_propios()
    botones_corregidos_en_propios()
    retirar_tarea_asignar()

    if args.actualizar:
        clave = perfil_disponible()
        print("\n=== Actualizado ===")
        print("  El código quedó al día.")
        print(f"  Perfil: {clave or '(ninguno: corre INSTALAR.bat)'}")
        print("  Tus botones, registros y accesos quedaron como estaban (la tarea de las 16:00 ya no existe).")
        print("\n  Cierra la barra y vuelve a abrirla para que tome los cambios.")
        return

    clave = configurar_perfil()
    crear_carpetas(clave)
    if not args.sin_accesos:
        lanzadores(clave)
        accesos_directos(clave)
        barra_al_inicio()
    if not args.sin_tareas:
        tareas_programadas(clave)

    print("\n=== Listo ===")
    print("Desde ahora:")
    print("  · Deja archivos en «Subir a Webclass\\<curso>» y se suben solos cada 10 min.")
    print("  · Las clases se asignan con el botón de la barra (ya no hay tarea automática a las 16:00).")
    print("  · Los accesos del escritorio hacen lo mismo cuando tú quieras.")
    print(f"\nSi cambian tus cursos o unidades:  python configurar.py --perfil {clave} --solo-actualizar")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
