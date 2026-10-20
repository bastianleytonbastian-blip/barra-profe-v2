"""
Sube un archivo al banco de recursos de Webclass y lo adjunta a una o más clases.

El recurso se sube UNA sola vez al banco y después se vincula a cada clase, igual
que en la página "Agregar recursos". Si en el banco ya existe un recurso tuyo con
el mismo nombre, se reutiliza en vez de subirlo de nuevo.

Ejemplos:
  python webclass_recursos.py "C:\\...\\guia.pdf" --clases 6BA=64534152,6BB=64534153 ^
      --nombre "Clase 21: Fuentes de energía" --nivel 6
  python webclass_recursos.py --recurso 5071459 --clases 6BA=64534152    (solo vincular)
  python webclass_recursos.py "guia.pdf" --clases 6BA=64534152 --simular (no escribe nada)

Usa las mismas sesiones y perfiles que webclass_tareas.py.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys

import webclass_tareas as w
from barra_utiles import ID_ASIGNATURA

PLANIF = f"{w.BASE}/home/planificacion"
MULTIFILE = f"{w.BASE}/home/recursos/multifile"

# Subcategoría "Ofimática" del formulario de subida, según la extensión.
SUBCATEGORIA = {".doc": 41, ".docx": 41, ".xls": 42, ".xlsx": 42,
                ".ppt": 43, ".pptx": 43, ".pdf": 44,
                # Otras categorías del formulario de WebClass (el código es el de su campo «TipoFile»):
                ".jpg": 33, ".jpeg": 33, ".png": 33,      # Imágenes → Fotos
                ".mp3": 55, ".wav": 55,                   # Audio → Audiolibro
                ".mp4": 21}                               # Documentos → Video

# Nivel de aplicación: 1°..8° básico = 21..28, 1°..4° medio = 31..34.
NIVELES = {**{str(n): 20 + n for n in range(1, 9)},
           **{f"{n}M": 30 + n for n in range(1, 5)}}

# Grupo de asignatura (selectSectorLocal): sale de la tabla única de barra_utiles, que también usa el planificador.
ASIGNATURAS = dict(ID_ASIGNATURA)

MOMENTOS = {"inicio": 1, "desarrollo": 2, "cierre": 3}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("archivo", nargs="?", help="Archivo a subir (pdf, Word, Excel, PowerPoint, jpg, png, mp3, wav o mp4).")
    p.add_argument("--recurso", help="Id de un recurso que ya está en el banco (no sube nada).")
    p.add_argument("--clases", default="", metavar="CURSO=IDCLASE,...",
                   help="Clases donde adjuntarlo, ej. 6BA=64534152,6BB=64534153. "
                        "El curso también puede ser el id numérico de la unidad. "
                        "Si se omite, solo se sube al banco (requiere --nivel).")
    p.add_argument("--nombre", help="Nombre del recurso en el banco (por defecto, el del archivo).")
    p.add_argument("--autor", help="Por defecto, el nombre del perfil.")
    p.add_argument("--nivel", help="Nivel(es) separados por coma: 1..8 básico o 1M..4M medio. "
                                   "Por defecto se deduce del curso (6BA -> 6).")
    p.add_argument("--asignatura", default="ciencias", choices=sorted(ASIGNATURAS))
    p.add_argument("--momento", default="desarrollo", choices=sorted(MOMENTOS),
                   help="Momento de la clase en que se muestra el recurso.")
    p.add_argument("--oculto", action="store_true", help="No visible para las alumnas.")
    p.add_argument("--perfil", choices=sorted(w.PERFILES), default=w.PERFIL_POR_DEFECTO)
    p.add_argument("--simular", action="store_true",
                   help="Muestra lo que haría sin subir ni vincular nada.")
    args = p.parse_args()
    if bool(args.archivo) == bool(args.recurso):
        p.error("indica un archivo para subir o --recurso ID, no ambos.")
    if not args.clases and (args.recurso or not args.nivel):
        p.error("sin --clases solo se puede subir un archivo al banco, indicando --nivel.")
    return args


def resolver_clases(texto: str, perfil: dict) -> list[tuple[str, int, str]]:
    """'6BA=64534152' -> (curso, id_unidad, idclase). Usa las unidades del perfil."""
    salida = []
    for par in filter(str.strip, texto.split(",")):
        curso, _, idclase = par.strip().partition("=")
        curso = curso.strip().upper()
        if not idclase.strip().isdigit():
            raise ValueError(f"Clase mal escrita: {par!r} (formato CURSO=IDCLASE).")
        if curso.isdigit():
            salida.append((curso, int(curso), idclase.strip()))
            continue
        unidades = [u["id"] for u in perfil["unidades"] if u["curso"] == curso]
        if not unidades:
            raise ValueError(f"El curso {curso} no está en las unidades del perfil.")
        salida.append((curso, unidades, idclase.strip()))
    return salida


def unidad_de_clase(session, unidades: list[int], idclase: str) -> int:
    """Si un curso tiene varias unidades (ej. 5BA + Orientación), busca la correcta."""
    if len(unidades) == 1:
        return unidades[0]
    for uid in unidades:
        if any(c["idclase"] == idclase for c in w.listar_clases(session, uid)):
            return uid
    raise ValueError(f"La clase {idclase} no aparece en ninguna unidad del curso.")


def buscar_banco(session, texto: str) -> list[dict]:
    """Busca en el banco por palabra clave (el buscador de "Agregar recursos")."""
    r = session.get(f"{PLANIF}/agregar_recursos.php",
                    params={"p": 0, "page": 1, "nom": texto, "load": 1},
                    headers=w.HEADERS, timeout=120)
    r.raise_for_status()
    recursos = []
    for fila in r.text.split("<tr class='fila_comun'")[1:]:
        celdas = re.findall(r"<div class='columna'>(.*?)</div>", fila, re.S)
        if len(celdas) >= 4:
            recursos.append({"id": celdas[0].strip(), "nombre": html.unescape(celdas[1]).strip(),
                             "autor": html.unescape(celdas[2]).strip()})
    return recursos


def normalizar(nombre: str) -> str:
    return " ".join(nombre.split())


def buscar_propio(session, nombre: str, autor: str) -> str | None:
    """Id del recurso más reciente con ese nombre y autor, o None.

    Webclass recorta los espacios extremos pero conserva los dobles, así que el
    buscador no calza si se le pasa el nombre con otros espacios: se busca por
    el tramo más largo sin espacios dobles y se compara normalizado.
    """
    clave = normalizar(nombre)
    tramo = max(nombre.strip().split("  "), key=len).strip()
    iguales = [r for r in buscar_banco(session, tramo)
               if normalizar(r["nombre"]) == clave and r["autor"] == autor]
    return max(iguales, key=lambda r: int(r["id"]))["id"] if iguales else None


def asignaturas_del_formulario(pagina: str) -> list[dict]:
    """[{'id': 3, 'nombre': 'Ciencias Naturales'}, …] del selector «Asignatura» (selectSectorLocal) del formulario
    de subida de WebClass. [] si la página no lo trae."""
    m = re.search(r"<select\b[^>]*\b(?:id|name)\s*=\s*[\"']?selectSectorLocal\b[^>]*>(.*?)</select>", pagina or "", re.S | re.I)
    if not m:
        return []
    salida, vistos = [], set()
    for valor, texto in re.findall(r"<option\b[^>]*?\bvalue\s*=\s*[\"']?([^\"'\s>]*)[\"']?[^>]*>(.*?)</option>",
                                   m.group(1), re.S | re.I):
        nombre = " ".join(html.unescape(re.sub(r"<[^>]+>", "", texto)).split())
        if valor.isdigit() and int(valor) > 0 and nombre and int(valor) not in vistos:
            vistos.add(int(valor))
            salida.append({"id": int(valor), "nombre": nombre})
    return salida


def leer_asignaturas(session) -> list[dict]:
    """Asignaturas que ofrece WebClass al subir un recurso. Solo lectura: abre el formulario y no envía nada."""
    r = session.get(f"{MULTIFILE}/subidaArchivo.php", params={"cl": 1}, headers=w.HEADERS, timeout=120)
    r.raise_for_status()
    return asignaturas_del_formulario(r.text)


def subir_o_reutilizar(session, ruta: str, *, nombre: str, autor: str, niveles: list[int],
                       asignatura: int, visible: bool, tipo_file: int | None = None) -> tuple[str, bool]:
    """Sube al banco salvo que ya exista uno propio con el mismo nombre.

    Devuelve (id_recurso, subido_ahora).
    """
    previo = buscar_propio(session, nombre, autor)
    if previo:
        return previo, False
    subir_al_banco(session, ruta, nombre=nombre, autor=autor, niveles=niveles,
                   asignatura=asignatura, visible=visible, tipo_file=tipo_file)
    nuevo = buscar_propio(session, nombre, autor)
    if not nuevo:
        raise RuntimeError("Se subió, pero no aparece en el banco para obtener su id.")
    return nuevo, True


def subir_al_banco(session, ruta: str, *, nombre: str, autor: str, niveles: list[int],
                   asignatura: int, visible: bool, tipo_file: int | None = None) -> None:
    """tipo_file: el tipo del formulario de WebClass (p. ej. 70 = Guía PIE); sin él, se deduce de la extensión."""
    ext = os.path.splitext(ruta)[1].lower()
    if ext not in SUBCATEGORIA:
        raise ValueError(f"Extensión {ext} no soportada (usa: {', '.join(e[1:] for e in SUBCATEGORIA)}).")
    # Abrir el formulario primero deja en la sesión el contexto que usa el servidor.
    session.get(f"{MULTIFILE}/subidaArchivo.php", params={"cl": 1},
                headers=w.HEADERS, timeout=120)
    datos = [("TipoFile", tipo_file or SUBCATEGORIA[ext]), ("nombreLocal", nombre.strip()),
             ("autorLocal", autor), ("selectSectorLocal", asignatura),
             ("CategoryDecoration", -1), ("boton", "")]
    datos += [("optionLocal[]", n) for n in niveles]
    if visible:
        datos.append(("visibleFormStudent", "on"))
    with open(ruta, "rb") as f:
        r = session.post(f"{MULTIFILE}/server/php/upload_local.php", data=datos,
                         files={"archivo": (os.path.basename(ruta), f)},
                         headers=w.HEADERS, timeout=300)
    r.raise_for_status()
    if "subido con exito" not in r.text:
        texto = re.sub(r"<[^>]+>", " ", r.text)
        raise RuntimeError("Webclass no confirmó la subida: " + " ".join(texto.split())[:200])


def vincular(session, id_recurso: str, id_unidad: int, idclase: str, momento: int) -> int:
    session.get(f"{PLANIF}/agregar_recursos.php",
                params={"p": idclase, "page": 1, "u": id_unidad}, headers=w.HEADERS, timeout=120)
    r = session.post(f"{PLANIF}/add_recurso_clase.php",
                     params={"id": id_recurso, "idclase": idclase, "page": 1},
                     headers=w.HEADERS, timeout=120)
    r.raise_for_status()
    id_cr = r.text.strip().strip('"')
    if not id_cr.isdigit():
        raise RuntimeError(f"Respuesta inesperada al vincular a {idclase}: {r.text[:80]!r}")
    session.post(f"{PLANIF}/clase_recurso_momento.php",
                 params={"id": id_cr, "momento": momento}, headers=w.HEADERS, timeout=120)
    c = session.post(f"{PLANIF}/controladores/controladorArchivo.php",
                     data={"caso": 7, "accion": 5, "idClase": idclase},
                     headers=w.HEADERS, timeout=120)
    m = re.search(r"\d+", re.sub(r"<[^>]+>", "", c.text))
    return int(m.group()) if m else -1


def main() -> None:
    args = parse_args()
    perfil = w.PERFILES[args.perfil]
    # El autor con que se firma el recurso sale del perfil del docente; así el
    # script sirve igual a cualquier profesor sin editar el código.
    autor = args.autor or perfil.get("nombre") or args.perfil.title()
    clases = resolver_clases(args.clases, perfil)

    if args.archivo and not os.path.isfile(args.archivo):
        raise FileNotFoundError(args.archivo)
    nombre = args.nombre or (os.path.splitext(os.path.basename(args.archivo))[0]
                             if args.archivo else "")
    if args.nivel:
        claves = [n.strip().upper() for n in args.nivel.split(",")]
    else:
        claves = sorted({re.match(r"\d+", c).group() for c, _, _ in clases
                         if re.match(r"\d+[BM]", c)})
    niveles = [NIVELES[k] for k in claves if k in NIVELES]
    if args.archivo and not niveles:
        raise ValueError("No se pudo deducir el nivel; indícalo con --nivel (ej. 6).")

    session = w.crear_session()
    w.login(session, perfil["rut"], w.obtener_password(perfil["rut"]))
    w.verificar_sesion(session, args.perfil, perfil["iduser"])
    clases = [(c, u if isinstance(u, int) else unidad_de_clase(session, u, idc), idc)
              for c, u, idc in clases]

    id_recurso = args.recurso
    if args.archivo:
        previo = buscar_propio(session, nombre, autor)
        if previo:
            id_recurso = previo
            print(f"Ya existe en el banco '{nombre}' (id {id_recurso}); se reutiliza.")
        elif args.simular:
            print(f"[SIMULAR] Subiría {args.archivo} como '{nombre}' | autor {autor} | "
                  f"niveles {niveles} | asignatura {args.asignatura} | "
                  f"visible {not args.oculto}")
        else:
            id_recurso, _ = subir_o_reutilizar(
                session, args.archivo, nombre=nombre, autor=autor, niveles=niveles,
                asignatura=ASIGNATURAS[args.asignatura], visible=not args.oculto)
            print(f"Subido al banco: '{nombre}' (id {id_recurso}).")

    for curso, uid, idc in clases:
        if args.simular:
            print(f"[SIMULAR] Vincularía recurso {id_recurso or '(nuevo)'} a {curso} "
                  f"clase {idc} (unidad {uid}), momento {args.momento}.")
            continue
        total = vincular(session, id_recurso, uid, idc, MOMENTOS[args.momento])
        print(f"  {curso} clase {idc}: vinculado ({args.momento}); recursos en la clase: {total}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
