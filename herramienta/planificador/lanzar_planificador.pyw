"""Abre el Planificador de Clases sin ventana de consola: si el servidor no está corriendo lo inicia en segundo plano,
y luego abre el navegador. Lo llama el botón «Planificar» de Barra Profe (o se puede abrir con doble clic).

Uso:  lanzar_planificador.pyw [ruta]      (ruta por defecto: planificar, o guia-pie, perfil, webclass)
      lanzar_planificador.pyw --solo-servidor   deja el servidor listo en segundo plano, sin ventanas ni navegador
                                                (lo pide la barra al abrirse si el docente eligió «Tener el planificador listo»)

Cada computador (y cada usuario de Windows) levanta su propio servidor local, solo accesible desde ese equipo:
  · si el puerto habitual está ocupado por otro programa, usa el siguiente libre;
  · nunca abre el servidor de OTRO usuario de Windows (en un PC compartido se vería la cuenta de otra persona).
"""
import getpass
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

RAIZ = os.path.dirname(os.path.abspath(__file__))
PUERTO_BASE = int(os.environ.get("PLANIFICADOR_PUERTO", "8501"))
PUERTOS = range(PUERTO_BASE, PUERTO_BASE + 10)
# Complementos de Python que necesita el servidor (módulo, paquete de requirements.txt). Si la actualización no pudo
# instalarlos (pip sin internet en la red del colegio), el servidor no arranca: mejor decirlo que esperar un minuto.
COMPLEMENTOS = (("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("multipart", "python-multipart"),
                ("openai", "openai"), ("openpyxl", "openpyxl"), ("pypdf", "pypdf"), ("docx", "python-docx"),
                ("pptx", "python-pptx"), ("PIL", "Pillow"), ("youtube_transcript_api", "youtube-transcript-api"))


def complementos_faltantes():
    """Los paquetes que faltan en este Python (vacío si está todo)."""
    import importlib.util
    faltan = []
    for modulo, paquete in COMPLEMENTOS:
        try:
            if importlib.util.find_spec(modulo) is None:
                faltan.append(paquete)
        except (ImportError, ValueError):
            faltan.append(paquete)
    return faltan


def ofrecer_instalar(faltan):
    """Explica qué falta y, si el docente acepta, instala los complementos en una ventana de consola visible."""
    try:
        import tkinter
        from tkinter import messagebox
        raiz = tkinter.Tk()
        raiz.withdraw()
    except Exception:
        return False
    try:
        if not messagebox.askyesno(
                "Planificador", "Al planificador le faltan complementos de Python en este PC:\n"
                f"{', '.join(faltan)}.\n\n¿Instalarlos ahora? Se abre una ventana negra que tarda unos minutos y "
                "necesita internet. Cuando se cierre, vuelve a tocar «Planificar».", parent=raiz):
            return False
        python = sys.executable
        if python.lower().endswith("pythonw.exe"):           # pip necesita consola para mostrar cómo va
            python = python[:-len("pythonw.exe")] + "python.exe"
        subprocess.Popen([python, "-m", "pip", "install", "-r", os.path.join(RAIZ, "requirements.txt")], cwd=RAIZ,
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        return True
    finally:
        raiz.destroy()


def es_mio(puerto):
    """¿Hay en ese puerto un planificador iniciado por ESTE usuario de Windows?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/identidad", timeout=1.5) as r:
            datos = json.load(r)
        return datos.get("app") == "planificador" and datos.get("usuario_windows") == getpass.getuser()
    except Exception:
        return False


def esta_libre(puerto):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", puerto)) != 0


def version_local():
    """La versión del planificador de esta carpeta ('' si no se sabe)."""
    try:
        with open(os.path.join(RAIZ, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def version_corriendo(puerto):
    """La versión del planificador que atiende en ese puerto ('' si no la informa: uno muy antiguo)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/version", timeout=2) as r:
            return str(json.load(r).get("planificador") or "")
    except Exception:
        return ""


def apagar(puerto):
    """Cierra el planificador de ese puerto con «Cerrar el planificador». Como el navegador, primero pide la página para
    tener el token de la sesión. True si se cerró."""
    import http.cookiejar
    import re
    base = f"http://127.0.0.1:{puerto}"
    try:
        abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with abridor.open(base + "/", timeout=3) as r:
            pagina = r.read().decode("utf-8", "replace")
        m = re.search(r'name="planificador-token" content="([^"]+)"', pagina)
        if not m:
            return False
        pedido = urllib.request.Request(base + "/api/apagar", data=b"{}", method="POST",
                                        headers={"x-planificador-token": m.group(1), "Content-Type": "application/json"})
        abridor.open(pedido, timeout=3).close()
    except Exception:
        return False
    for _ in range(40):                  # hasta ~10 s para soltar el puerto
        if not es_mio(puerto):
            return True
        time.sleep(0.25)
    return False


def buscar_puerto():
    """(puerto, ya_corriendo). Primero el servidor propio que ya esté abierto; si no, el primer puerto libre.

    Un servidor propio de OTRA versión quedó corriendo de antes de una actualización (sigue en segundo plano aunque la
    barra se reinicie) y atiende con el código viejo: se cierra y se abre el nuevo en su lugar.
    """
    for p in PUERTOS:
        if es_mio(p):
            local = version_local()
            if not local or version_corriendo(p) == local:
                return p, True
            if apagar(p):
                return p, False
            return p, True               # no se pudo cerrar: mejor el que hay que ninguno
    for p in PUERTOS:
        if esta_libre(p):
            return p, False
    return None, False


class Aviso:
    """Cartelito «Abriendo…» mientras arranca el servidor (la primera vez en un equipo puede tardar casi un minuto)."""

    def __init__(self):
        self.ventana = None
        try:
            import tkinter
            self.ventana = tkinter.Tk()
            self.ventana.overrideredirect(True)
            self.ventana.attributes("-topmost", True)
            tkinter.Label(self.ventana, text="Abriendo el planificador…\nLa primera vez puede tardar un poco.",
                          font=("Segoe UI", 11), padx=24, pady=16, bg="#1F3B57", fg="white").pack()
            self.ventana.update_idletasks()
            ancho, alto = self.ventana.winfo_reqwidth(), self.ventana.winfo_reqheight()
            self.ventana.geometry(f"+{(self.ventana.winfo_screenwidth() - ancho) // 2}+{(self.ventana.winfo_screenheight() - alto) // 3}")
            self.ventana.update()
        except Exception:
            self.ventana = None

    def latir(self):
        if self.ventana:
            try:
                self.ventana.update()
            except Exception:
                self.ventana = None

    def cerrar(self):
        if self.ventana:
            try:
                self.ventana.destroy()
            except Exception:
                pass


def iniciar_servidor(puerto):
    sys.path.insert(0, RAIZ)
    from nucleo import rutas
    os.makedirs(rutas.DATOS_COMUN, exist_ok=True)
    registro = open(os.path.join(rutas.DATOS_COMUN, "servidor.log"), "ab")   # con pythonw no hay consola: la salida va a un archivo
    entorno = {**os.environ, "PLANIFICADOR_SIN_NAVEGADOR": "1", "PLANIFICADOR_PUERTO": str(puerto), "PYTHONIOENCODING": "utf-8"}
    subprocess.Popen([sys.executable, os.path.join(RAIZ, "servidor.py")], cwd=RAIZ, env=entorno, stdin=subprocess.DEVNULL,
                     stdout=registro, stderr=registro,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0))


def asegurar_servidor():
    """Devuelve el puerto del servidor propio, iniciándolo si hace falta (None si no se pudo)."""
    puerto, corriendo = buscar_puerto()
    if puerto is None or corriendo:
        return puerto
    aviso = Aviso()
    try:
        iniciar_servidor(puerto)
        for _ in range(240):         # hasta ~60 s (la primera vez en una carpeta nueva tarda más)
            if es_mio(puerto):
                return puerto
            aviso.latir()
            time.sleep(0.25)
        return None
    finally:
        aviso.cerrar()


def preparar():
    """--solo-servidor: si este usuario no tiene ya un planificador abierto, lo inicia y termina (sin esperar ni avisar)."""
    puerto, corriendo = buscar_puerto()
    if puerto is not None and not corriendo:
        iniciar_servidor(puerto)


def main():
    faltan = complementos_faltantes()
    if "--solo-servidor" in sys.argv[1:]:
        if not faltan:                   # sin complementos no hay servidor que dejar listo (ni ventanas que mostrar)
            preparar()
        return
    ruta = sys.argv[1].lstrip("#/") if len(sys.argv) > 1 else "planificar"
    if faltan and not buscar_puerto()[1]:
        ofrecer_instalar(faltan)
        return
    puerto = asegurar_servidor()
    if puerto is None:
        try:
            import tkinter
            from tkinter import messagebox
            raiz = tkinter.Tk(); raiz.withdraw()
            messagebox.showerror("Planificador", "No se pudo iniciar el planificador.\n"
                                 "Revisa el archivo servidor.log en la carpeta de datos del planificador.")
        except Exception:
            pass
        return
    webbrowser.open(f"http://127.0.0.1:{puerto}/#/{ruta}")


if __name__ == "__main__":
    main()
