"""
Sube al banco de recursos de Webclass todo archivo que se deje en la carpeta
"Subir a Webclass", según la subcarpeta de nivel donde se ponga.

  Documents\\Subir a Webclass\\
     1 basico\\ … 8 basico\\   1 medio\\ … 4 medio\\    (una carpeta por nivel)
     _subidos\\   <- lo ya subido (con la misma subcarpeta de nivel)
     _errores\\   <- lo que no se pudo subir; el motivo queda en _errores\\motivos.txt
     registro_subidas.csv   <- fecha, archivo, nivel e id del recurso en el banco

Solo sube al banco (no adjunta a clases). El nombre del recurso es el del
archivo. Si ya hay un recurso propio con ese nombre, no lo duplica.

Se ejecuta cada 10 minutos por el Programador de tareas y a mano con el acceso
directo "Subir recursos Webclass". Si no hay archivos, termina sin iniciar sesión.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import os
import shutil
import sys
import time

try:
    import msvcrt
except ImportError:  # no-Windows
    msvcrt = None

import rutas
import webclass_tareas as w
from barra_utiles import (asignatura_sugerida, asignaturas_de_la_cuenta, carpeta_con_asignatura, codigo_de_asignatura,
                          leer_preferencia_subida, ruta_preferencia_subida)
import webclass_recursos as r

CARPETA = rutas.BUZON
SUBIDOS = os.path.join(CARPETA, "_subidos")
ERRORES = os.path.join(CARPETA, "_errores")
REGISTRO = os.path.join(CARPETA, "registro_subidas.csv")
LOG = os.path.join(w.carpeta_datos(), "subidas.log")
LOCK = os.path.join(w.carpeta_datos(), "subidas.lock")

# Las carpetas son por NIVEL, de 1° básico a 4° medio, iguales para cualquier
# profesor. El número entre paréntesis es el nivel que espera el banco.
NIVELES_CARPETA = {**{f"{n} basico": r.NIVELES[str(n)] for n in range(1, 9)},
                   **{f"{n} medio": r.NIVELES[f"{n}M"] for n in range(1, 5)}}


def asignatura_principal(perfil: dict, nombre_perfil: str | None = None) -> int:
    """La asignatura con que se firma lo que se sube: la que el docente eligió al subir
    (guardada en personal\\subida_<cuenta>.json) o, si nunca eligió, la que más dicta."""
    clave = ""
    if nombre_perfil:
        validas = [k for k, _nombre, _codigo in asignaturas_de_la_cuenta(perfil)]
        clave = leer_preferencia_subida(ruta_preferencia_subida(rutas.PERSONAL, nombre_perfil), validas)["asignatura"]
    clave = clave or asignatura_sugerida(perfil)
    return codigo_de_asignatura(clave, perfil) or r.ASIGNATURAS["ciencias"]


def destinos_del_perfil(perfil: dict, nombre_perfil: str | None = None) -> dict[str, tuple[list[int], int]]:
    """Carpeta -> (nivel, asignatura). Una por nivel, más las que el docente creó con nivel y asignatura en el nombre."""
    sector = asignatura_principal(perfil, nombre_perfil)
    destinos = {carpeta: ([nivel], sector) for carpeta, nivel in NIVELES_CARPETA.items()}
    # «5 basico Orientacion», «7° Básico Música»…: se suben con ese nivel y esa asignatura. Se reconocen por el nombre,
    # con las asignaturas de la cuenta (las que ofrece su WebClass), sin una lista fija.
    asignaturas = asignaturas_de_la_cuenta(perfil)
    try:
        nombres = os.listdir(CARPETA)
    except OSError:
        nombres = []
    for nombre in nombres:
        if nombre in destinos or nombre.startswith("_") or not os.path.isdir(os.path.join(CARPETA, nombre)):
            continue
        reconocida = carpeta_con_asignatura(nombre, asignaturas)
        if reconocida:
            nivel, (_clave, _nombre, codigo) = reconocida
            destinos[nombre] = ([nivel], codigo)
    return destinos

IGNORAR_EXT = {".tmp", ".crdownload", ".part", ".ini", ".lnk"}

# Cuánto se espera a un archivo que no termina de copiarse antes de darlo por
# perdido y mandarlo a _errores, para que no quede atascado en cada revisión.
ESPERA_MAXIMA = 30          # minutos
SE_RINDE = "RENDIRSE: "     # prefijo interno: marca los que se van a _errores


def minutos_quieto(ruta: str) -> float:
    """Minutos desde la última vez que el archivo cambió."""
    try:
        return (time.time() - os.path.getmtime(ruta)) / 60
    except OSError:
        return 0.0


def log(msg: str) -> None:
    linea = f"{datetime.datetime.now():%d/%m/%Y %H:%M:%S} {msg}"
    if sys.stdout:  # con pythonw no hay consola
        print(linea, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def preparar_carpetas(destinos: dict) -> None:
    """Solo asegura las carpetas de servicio.

    Las de nivel las crea el instalador: si el docente borra las que no usa,
    no tienen por qué volver a aparecer en cada corrida.
    """
    for sub in ("_subidos", "_errores"):
        os.makedirs(os.path.join(CARPETA, sub), exist_ok=True)


def mover(ruta: str, destino_dir: str) -> str:
    """Mueve sin pisar: si el nombre existe, agrega ' (2)', ' (3)'..."""
    os.makedirs(destino_dir, exist_ok=True)
    base, ext = os.path.splitext(os.path.basename(ruta))
    destino, n = os.path.join(destino_dir, base + ext), 2
    while os.path.exists(destino):
        destino, n = os.path.join(destino_dir, f"{base} ({n}){ext}"), n + 1
    shutil.move(ruta, destino)
    return destino


def listo_para_subir(ruta: str) -> tuple[bool, str]:
    """(se puede subir, por qué no).

    Antes devolvía solo sí o no, y cualquier caso salía como «se está
    copiando». El motivo más común no es ese: es tener el archivo abierto en
    Word o en el visor de PDF, y ahí el aviso no ayudaba a destrabarlo porque
    la próxima revisión fallaba igual.
    """
    try:
        tam = os.path.getsize(ruta)
    except OSError as exc:
        return False, f"no se pudo leer ({exc})"
    if tam == 0:
        # Un archivo que lleva horas en cero no se está copiando: quedó así.
        # Sin esto se queda en la carpeta para siempre, y cada revisión pierde
        # dos segundos en él mientras repite el mismo aviso.
        if minutos_quieto(ruta) > ESPERA_MAXIMA:
            return False, SE_RINDE + "quedó vacío (0 bytes): vuelve a copiarlo"
        return False, "está vacío: se espera a que termine de copiarse"
    time.sleep(2)
    try:
        if os.path.getsize(ruta) != tam:
            return False, "se está copiando todavía; se intenta en la próxima revisión"
        os.rename(ruta, ruta)  # falla en Windows si otro proceso lo tiene abierto
    except OSError:
        return False, ("lo tiene abierto otro programa (Word, el visor de PDF…): "
                       "ciérralo y vuelve a apretar «Subir recursos»")
    return True, ""


def esperar_o_rendirse(ruta: str) -> tuple[bool, str, bool]:
    """(se puede subir, motivo, hay que mandarlo a _errores)."""
    puede, motivo = listo_para_subir(ruta)
    if motivo.startswith(SE_RINDE):
        return False, motivo[len(SE_RINDE):], True
    return puede, motivo, False


def pendientes(destinos: dict) -> list[tuple[str, str]]:
    """(ruta, subcarpeta) de cada archivo a procesar. Los sueltos en la raíz van a errores."""
    salida = []
    for nombre in os.listdir(CARPETA):
        ruta = os.path.join(CARPETA, nombre)
        if os.path.isfile(ruta) and nombre != os.path.basename(REGISTRO) \
                and not nombre.startswith(("~$", ".")) \
                and os.path.splitext(nombre)[1].lower() not in IGNORAR_EXT:
            salida.append((ruta, ""))
    for sub in destinos:
        dir_sub = os.path.join(CARPETA, sub)
        if not os.path.isdir(dir_sub):
            continue
        for nombre in sorted(os.listdir(dir_sub)):
            ruta = os.path.join(dir_sub, nombre)
            if os.path.isfile(ruta) and not nombre.startswith(("~$", ".")) \
                    and os.path.splitext(nombre)[1].lower() not in IGNORAR_EXT:
                salida.append((ruta, sub))
    return salida


def a_errores(ruta: str, sub: str, motivo: str) -> None:
    destino = mover(ruta, os.path.join(ERRORES, sub))
    with open(os.path.join(ERRORES, "motivos.txt"), "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%d/%m/%Y %H:%M} | {os.path.basename(destino)} | {motivo}\n")
    log(f"  [ERROR] {os.path.basename(ruta)}: {motivo}")


def registrar(archivo: str, sub: str, id_recurso: str, estado: str, autor: str = "") -> None:
    existe = os.path.exists(REGISTRO)
    with open(REGISTRO, "a", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f, delimiter=";")  # ; para que Excel lo abra en columnas
        if not existe:
            # «docente» importa en los PC compartidos: si no, no hay forma de
            # saber a nombre de quién quedó cada recurso en el banco.
            wr.writerow(["fecha", "archivo", "carpeta", "id_recurso", "estado", "docente"])
        wr.writerow([f"{datetime.datetime.now():%d/%m/%Y %H:%M}", archivo, sub,
                     id_recurso, estado, autor])


def procesar(nombre_perfil: str = w.PERFIL_POR_DEFECTO, seleccion: set | None = None) -> None:
    perfil = w.PERFILES[nombre_perfil]
    # Las carpetas son por nivel (1° básico a 4° medio); la asignatura con que
    # se firma sale del perfil del docente.
    destinos = destinos_del_perfil(perfil, nombre_perfil)
    preparar_carpetas(destinos)
    archivos = pendientes(destinos)
    if not archivos:
        if sys.stdout:
            log("No hay archivos nuevos para subir.")
        return

    log(f"=== {len(archivos)} archivo(s) por revisar "
        f"(docente: {perfil.get('nombre') or nombre_perfil}) ===")
    if seleccion is None:           # con una selección no se toca nada que el docente no eligió
        for ruta, sub in [(a, s) for a, s in archivos if not s]:
            a_errores(ruta, "", "estaba suelto en la carpeta; déjalo dentro de la carpeta de su nivel")
    archivos = [(a, s) for a, s in archivos if s]
    if not archivos:
        return

    session = w.crear_session()
    w.login(session, perfil["rut"], w.obtener_password(perfil["rut"]))
    w.verificar_sesion(session, nombre_perfil, perfil["iduser"])
    autor = perfil.get("nombre") or nombre_perfil.title()

    for n_archivo, (ruta, sub) in enumerate(archivos, 1):
        nombre_archivo = os.path.basename(ruta)
        if sys.stdout:          # la barra lee esto; la tarea programada no tiene consola
            print(f"##PROGRESO {n_archivo - 1}/{len(archivos)} {nombre_archivo}", flush=True)
        base, ext = os.path.splitext(nombre_archivo)
        clave = f"{sub}/{nombre_archivo}"
        if seleccion is not None and clave not in seleccion:
            log(f"  Omitido por ti: {clave}")
            w.item(clave, "omitido", nombre_archivo, sub, "archivo")
            continue
        if ext.lower() not in r.SUBCATEGORIA:
            motivo = f"formato {ext or '(sin extensión)'} no admitido ({', '.join(e[1:] for e in r.SUBCATEGORIA)})"
            a_errores(ruta, sub, motivo)
            w.item(clave, "pendiente", nombre_archivo, sub, "archivo", motivo=motivo)
            continue
        puede, motivo, rendirse = esperar_o_rendirse(ruta)
        if rendirse:
            a_errores(ruta, sub, motivo)
            w.item(clave, "pendiente", nombre_archivo, sub, "archivo", motivo=motivo)
            continue
        if not puede:
            log(f"  [ESPERA] {nombre_archivo}: {motivo}.")
            w.item(clave, "pendiente", nombre_archivo, sub, "archivo", motivo=f"{motivo} (sigue en la carpeta)")
            continue
        niveles, asignatura = destinos[sub]
        try:
            id_rec, nuevo = r.subir_o_reutilizar(
                session, ruta, nombre=base, autor=autor,
                niveles=niveles, asignatura=asignatura, visible=True)
        except Exception as exc:  # noqa: BLE001
            a_errores(ruta, sub, str(exc))
            w.item(clave, "error", nombre_archivo, sub, "archivo", motivo=str(exc)[:200])
            continue
        mover(ruta, os.path.join(SUBIDOS, sub))
        estado = "subido" if nuevo else "ya existía (no se duplicó)"
        registrar(nombre_archivo, sub, id_rec, estado, autor)
        log(f"  [OK] {sub}/{nombre_archivo} -> recurso {id_rec} ({estado})")
        w.item(clave, "ya" if not nuevo else "hecho", nombre_archivo, sub, "archivo",
               f"recurso {id_rec}" if nuevo else "ya existía en el banco: no se duplicó")
    if sys.stdout:
        print(f"##PROGRESO {len(archivos)}/{len(archivos)}", flush=True)
        w.imprimir_resultado(w.ITEMS)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--perfil", choices=sorted(w.PERFILES), default=w.PERFIL_POR_DEFECTO,
                   help="Docente cuyas carpetas y cursos se usan.")
    p.add_argument("--seleccion", metavar="ARCHIVO.json",
                   help="Solo sube los archivos cuya clave («nivel/archivo») esté en "
                        "{\"claves\": [...]} (lo marcado en la vista previa de la barra).")
    args = p.parse_args()

    # Evita que la tarea cada 10 min y el acceso directo suban lo mismo a la vez.
    lock = open(LOCK, "w")
    if msvcrt:
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            log("Ya hay una subida en curso; se omite esta ejecución.")
            return
    try:
        procesar(args.perfil, w.leer_seleccion(args.seleccion))
    except Exception as exc:  # noqa: BLE001
        # Errores de sesión o red: los archivos quedan donde están y se reintenta.
        log(f"FALLÓ la revisión (se reintentará): {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
