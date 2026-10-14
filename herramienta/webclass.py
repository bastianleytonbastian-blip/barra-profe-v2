"""
Punto de entrada único de las herramientas de Webclass.

Existe para poder empaquetar todo en un solo ejecutable: el profesor que reciba
webclass.exe no necesita tener Python instalado.

    webclass.exe instalar              deja el PC listo (carpetas, accesos, tareas)
    webclass.exe configurar            crea o actualiza el perfil del profesor
    webclass.exe probar                revisa si una cuenta puede entrar, paso a paso
    webclass.exe asignar --hoy         asigna las clases del día a las alumnas
    webclass.exe subir                 sube al banco lo que haya en la carpeta
    webclass.exe recursos guia.pdf …   sube un archivo y lo adjunta a clases
    webclass.exe libro                 declara OA y leccionario del día
    webclass.exe libro --informe       estado del mes, sin escribir nada
    webclass.exe horario --ver         horario semanal de clases
    webclass.exe observar --datos obs.json   registra una observación a varias alumnas
    webclass.exe firmas                revisa qué quedó sin firmar hoy

Cada subcomando acepta sus propias opciones: `webclass.exe asignar --ayuda`.
"""

from __future__ import annotations

import sys

# Se importan explícitamente (y no por nombre) para que el empaquetador los
# incluya en el .exe: PyInstaller no ve los import armados en tiempo de ejecución.
import configurar
import correo_pie
import estado_firmas
import horario_semana
import instalar
import probar_acceso
import subir_carpeta
import webclass_libro
import webclass_observaciones
import webclass_planificacion
import webclass_recursos
import webclass_tareas

ORDENES = {
    "instalar": (instalar, "Deja el PC listo: carpetas, accesos directos y tareas"),
    "configurar": (configurar, "Crea o actualiza el perfil del profesor"),
    "probar": (probar_acceso, "Revisa paso a paso si una cuenta puede entrar"),
    "asignar": (webclass_tareas, "Asigna las clases pendientes a las alumnas"),
    "subir": (subir_carpeta, "Sube al banco lo que haya en la carpeta"),
    "recursos": (webclass_recursos, "Sube un archivo y lo adjunta a clases"),
    "libro": (webclass_libro, "Libro de clases: OA, leccionario y asistencia"),
    "horario": (horario_semana, "Arma el horario semanal"),
    "observar": (webclass_observaciones, "Registra observaciones de estudiantes"),
    "planificar": (webclass_planificacion, "Crea clases en bloque, importa planillas y marca OA/DUA"),
    "correo": (correo_pie, "Envía guías al equipo PIE por correo"),
    "firmas": (estado_firmas, "Revisa qué quedó sin firmar hoy"),
}


def ayuda() -> None:
    print(__doc__.strip())
    print("\nSubcomandos:")
    for nombre, (_modulo, que_hace) in ORDENES.items():
        print(f"  {nombre:<12} {que_hace}")


def main() -> None:
    # En una consola antigua (cp850) un acento haría reventar el print; mejor
    # que se vea un carácter raro y no que se caiga la herramienta.
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "ayuda", "/?"):
        ayuda()
        return
    orden = sys.argv[1].lower()
    if orden not in ORDENES:
        print(f"No conozco la orden «{orden}».\n", file=sys.stderr)
        ayuda()
        sys.exit(2)
    # Se saca el subcomando para que el módulo lea sus propias opciones.
    del sys.argv[1]
    ORDENES[orden][0].main()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
