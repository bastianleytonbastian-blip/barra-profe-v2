"""
Configura estas herramientas para un profesor nuevo.

Pregunta el RUT, guarda la contraseña en el llavero de Windows (no queda
escrita en ningún archivo) y luego le pregunta a Webclass todo lo demás:
id de usuario, colegio, cursos y unidades vigentes. Con eso deja un perfil
en perfiles\\<nombre>.json que usan el resto de los scripts.

Cada profesor corre esto UNA vez, en su propio PC y con su propia cuenta:

    python configurar.py

Para rehacer el perfil después (por ejemplo si le cambian los cursos):

    python configurar.py --perfil bastian --solo-actualizar
"""

from __future__ import annotations

import argparse
import datetime
import getpass
import html
import json
import os
import re
import sys
import unicodedata

import keyring

import rutas
import webclass_tareas as w

CARPETA_PERFILES = rutas.PERFILES
WEBICP = "https://webicp2.webescuela.cl"
API = f"{WEBICP}/api/portadaProfesor"


def clave_archivo(nombre: str) -> str:
    """'Bastián Leyton' -> 'bastian' (nombre de archivo simple y sin tildes)."""
    limpio = unicodedata.normalize("NFD", nombre.strip().lower())
    limpio = "".join(c for c in limpio if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", limpio).strip("-").split("-")[0] or "profesor"


def entrar(rut: str, password: str):
    """Sesión en Webclass y en el módulo del libro; devuelve (sesión, token, datos)."""
    s = w.crear_session()
    w.login(s, rut, password)
    pagina = s.get(f"{w.BASE}/home/planificacion/index.php", params={"wc": 1},
                   headers=w.HEADERS, timeout=90).text
    iduser = re.search(r'id="iduser"[^>]*value="([^"]*)"', pagina)
    if not iduser:
        raise RuntimeError("Entré, pero no pude leer tu id de usuario. ¿Es un perfil de profesor?")
    entrada = s.post(f"{WEBICP}/loginFromWebclass",
                     data={"username": w.usuario_del_libro(s, rut), "module": "/classbook"},
                     headers=w.HEADERS, timeout=120)
    resp = s.get(f"{WEBICP}/portada-profesor", headers=w.HEADERS, timeout=120)
    portada = resp.text
    token = re.search(r'name="csrf-token" content="([^"]+)"', portada)
    if not token:
        raise RuntimeError(w.por_que_no_entro(resp, portada, entrada))
    # El id del colegio viene en los datos de los cursos del libro, escapados.
    libro = html.unescape(s.get(f"{WEBICP}/classbook", headers=w.HEADERS, timeout=120).text)
    colegio = re.search(r'"colegio":(\d+)', libro)
    if not colegio:
        raise RuntimeError("No pude leer el id del colegio desde el libro de clases.")
    rol = re.search(r'"rol":(\d+)', libro)
    return s, token.group(1), {"iduser": iduser.group(1), "colegio": colegio.group(1),
                               "rol": int(rol.group(1)) if rol else 13}


def pedir(s, token: str, ruta: str, params: dict) -> dict:
    r = s.get(f"{API}/{ruta}", params=params,
              headers={**w.HEADERS, "X-CSRF-TOKEN": token,
                       "X-Requested-With": "XMLHttpRequest"}, timeout=120)
    r.raise_for_status()
    return r.json().get("data", {})


def descubrir(s, token: str, datos: dict) -> dict:
    """Cursos del profesor y, dentro de cada uno, sus unidades de planificación."""
    anio = datetime.date.today().year
    cursos_api = pedir(s, token, "getCourses",
                       {"idColegio": datos["colegio"], "anio": anio,
                        "idUsuario": datos["iduser"]}).get("courses", [])
    cursos, unidades, niveles, asignaturas = {}, [], {}, {}
    hoy = datetime.date.today().strftime("%Y-%m-%d")
    for c in cursos_api:
        nombre, curso_id, nivel = c["cur_nom"], c["id"], c["niv_id"]
        subs = pedir(s, token, "get-plan-subjects",
                     {"schoolID": datos["colegio"], "gradeID": curso_id, "levelID": nivel})
        encontradas = []
        for sub in subs.get("subjects", []):
            u = pedir(s, token, "get-plan-units",
                      {"subjectID": sub["id"], "schoolID": datos["colegio"],
                       "profesorID": datos["iduser"], "rolID": datos["rol"],
                       "cursoID": curso_id, "levelID": nivel, "date": hoy})
            for unidad in u.get("units", []):
                encontradas.append({"curso": nombre, "id": unidad["id"],
                                    "nombre": unidad.get("nombre", ""),
                                    "asignatura": sub.get("sectornombre", "")})
        if encontradas:
            # Solo se guardan los cursos donde el profesor tiene planificación.
            cursos[nombre] = curso_id
            unidades += encontradas
            niveles[nombre] = nivel
            # La asignatura que más se repite es la que dicta en ese curso; es
            # la que se usará al subir recursos desde su carpeta.
            cuenta: dict[str, int] = {}
            for u in encontradas:
                cuenta[u["asignatura"]] = cuenta.get(u["asignatura"], 0) + 1
            asignaturas[nombre] = max(cuenta, key=cuenta.get)
        print(f"   {nombre}: {len(encontradas)} unidades")
    return {"curso_ids": cursos, "unidades": unidades,
            "curso_niveles": niveles, "curso_asignaturas": asignaturas}


def guardar(perfil: dict, clave: str) -> str:
    os.makedirs(CARPETA_PERFILES, exist_ok=True)
    ruta = os.path.join(CARPETA_PERFILES, f"{clave}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(perfil, f, ensure_ascii=False, indent=1)
    return ruta


def jefatura(cursos: dict, args) -> str:
    """Curso del que el docente es profesor jefe, o "" si no tiene.

    Solo lo usa la barra flotante, para avisar quién faltó hoy en ese curso.
    """
    if args.solo_actualizar and args.perfil:
        ruta = os.path.join(CARPETA_PERFILES, f"{args.perfil}.json")
        with open(ruta, encoding="utf-8") as f:
            return json.load(f).get("jefatura", "")
    nombres = sorted(cursos)
    print("\nTus cursos: " + ", ".join(nombres))
    respuesta = input("¿De cuál eres profesor jefe? (Enter si de ninguno): ").strip().upper()
    if respuesta and respuesta not in cursos:
        print(f"   «{respuesta}» no está en la lista: se deja sin jefatura.")
        return ""
    return respuesta


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--perfil", help="Nombre del perfil a rehacer (sin .json).")
    p.add_argument("--solo-actualizar", action="store_true",
                   help="Usa la clave ya guardada y solo vuelve a leer cursos y unidades.")
    p.add_argument("--usar-clave-guardada", action="store_true",
                   help="No pide la contraseña: usa la que ya está en el llavero.")
    p.add_argument("--nombre", help="Tu nombre como aparece en Webclass (si el perfil no lo trae).")
    args = p.parse_args()

    print("=== Configuración de las herramientas de Webclass ===\n")
    if args.perfil and args.solo_actualizar:
        ruta = os.path.join(CARPETA_PERFILES, f"{args.perfil}.json")
        with open(ruta, encoding="utf-8") as f:
            previo = json.load(f)
        rut, clave = previo["rut"], args.perfil
        password = keyring.get_password(w.KEYRING_SERVICE, rut)
        if not password:
            raise SystemExit(f"No hay clave guardada para {rut}. Corre configurar.py sin --solo-actualizar.")
    else:
        rut = input("RUT con guion y dígito verificador (ej. 12345678-9): ").strip()
        if not re.fullmatch(r"\d{7,8}-[\dkK]", rut):
            raise SystemExit("Ese RUT no tiene el formato esperado.")
        if args.usar_clave_guardada:
            password = keyring.get_password(w.KEYRING_SERVICE, rut)
            if not password:
                raise SystemExit(f"No hay clave guardada para {rut}.")
        else:
            print("\nLa contraseña se guarda en el Administrador de credenciales de Windows.")
            print("No queda escrita en ningún archivo ni se le muestra a nadie.")
            password = getpass.getpass(f"Contraseña Webclass de {rut}: ")
        clave = ""

    print("\nEntrando a Webclass…")
    s, token, datos = entrar(rut, password)
    keyring.set_password(w.KEYRING_SERVICE, rut, password)

    if args.solo_actualizar:
        # Un perfil armado a mano puede no traer el nombre: se pide (o se pasa con --nombre).
        with open(os.path.join(CARPETA_PERFILES, f"{args.perfil}.json"), encoding="utf-8") as f:
            nombre = (args.nombre or json.load(f).get("nombre") or "").strip()
        if not nombre:
            nombre = input("\\nTu nombre como aparece en Webclass (para firmar recursos): ").strip()
    else:
        nombre = (args.nombre or input(
            "\\nTu nombre como aparece en Webclass (para firmar recursos): ")).strip()
    clave = clave or clave_archivo(nombre)

    print("\nBuscando tus cursos y unidades…")
    descubierto = descubrir(s, token, datos)
    if not descubierto["curso_ids"]:
        raise SystemExit("No encontré cursos con planificación para este usuario.")

    perfil = {"nombre": nombre, "rut": rut, "iduser": datos["iduser"],
              "colegio": datos["colegio"], "rol": datos["rol"],
              "jefatura": jefatura(descubierto["curso_ids"], args),
              "actualizado": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
              **descubierto}
    ruta = guardar(perfil, clave)

    print(f"\nListo. Perfil «{clave}» guardado en:\n  {ruta}")
    print(f"  {len(perfil['curso_ids'])} cursos · {len(perfil['unidades'])} unidades")
    print("\nAhora puedes usar, por ejemplo:")
    print(f"  python webclass_tareas.py --hoy --perfil {clave}")
    print(f"  python webclass_recursos.py archivo.pdf --nivel 6 --perfil {clave}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
