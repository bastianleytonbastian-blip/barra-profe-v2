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


def buscar_puerto():
    """(puerto, ya_corriendo). Primero el servidor propio que ya esté abierto; si no, el primer puerto libre."""
    for p in PUERTOS:
        if es_mio(p):
            return p, True
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
    if "--solo-servidor" in sys.argv[1:]:
        preparar()
        return
    ruta = sys.argv[1].lstrip("#/") if len(sys.argv) > 1 else "planificar"
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
