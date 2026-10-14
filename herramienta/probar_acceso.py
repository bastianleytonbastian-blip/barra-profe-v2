"""
Prueba paso a paso si una cuenta puede usar estas herramientas.

No escribe nada, ni en Webclass ni en el PC: solo mira hasta dónde llega y
dice qué falló. Sirve cuando configurar.py se corta y no se entiende por qué.

    python probar_acceso.py

Pide el RUT y la contraseña (o usa la guardada, con --usar-clave-guardada) y
revisa cuatro cosas, en orden:

    1. entrar a Webclass
    2. la página de planificaciones (de ahí salen "asignar clases" y "recursos")
    3. el libro de clases, que es un sistema aparte (webicp2)
    4. la lista de cursos del libro

Los pasos 1 y 2 son los que necesitan subir recursos y asignar clases. Los
pasos 3 y 4 solo hacen falta para el libro (OA, leccionario, asistencia,
horario y el aviso de firmas).
"""

from __future__ import annotations

import argparse
import datetime
import getpass
import html
import re
import sys

import keyring

import webclass_tareas as w

WEBICP = "https://webicp2.webescuela.cl"


def paso(n: int, texto: str) -> None:
    print(f"\n{n}. {texto}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rut", help="RUT con guion; si no, se pregunta.")
    p.add_argument("--usar-clave-guardada", action="store_true",
                   help="No pide la contraseña: usa la del llavero de Windows.")
    args = p.parse_args()

    print("=== Prueba de acceso a Webclass ===")
    rut = args.rut or input("RUT con guion y dígito verificador: ").strip()
    if not re.fullmatch(r"\d{7,8}-[\dkK]", rut):
        raise SystemExit("Ese RUT no tiene el formato esperado (ej. 12345678-9).")
    if args.usar_clave_guardada:
        password = keyring.get_password(w.KEYRING_SERVICE, rut)
        if not password:
            raise SystemExit(f"No hay clave guardada para {rut}.")
    else:
        password = getpass.getpass(f"Contraseña Webclass de {rut}: ")

    s = w.crear_session()

    paso(1, "Entrando a Webclass…")
    try:
        w.login(s, rut, password)
        print("   OK: usuario y contraseña aceptados.")
    except Exception as exc:  # noqa: BLE001
        print(f"   FALLÓ: {exc}")
        print("\n   Revisa el RUT y la contraseña. Si entras bien desde el navegador")
        print("   pero acá no, avísame.")
        sys.exit(1)

    paso(2, "Abriendo tus planificaciones…")
    pagina = s.get(f"{w.BASE}/home/planificacion/index.php", params={"wc": 1},
                   headers=w.HEADERS, timeout=90).text
    iduser = re.search(r'id="iduser"[^>]*value="([^"]*)"', pagina)
    if not iduser:
        print("   FALLÓ: no aparece tu id de usuario. ¿Es una cuenta de profesor?")
        sys.exit(1)
    print(f"   OK: id de usuario {iduser.group(1)}.")
    print("   -> Subir recursos y asignar clases pueden funcionar.")

    paso(3, "Entrando al libro de clases (es otro sistema)…")
    usuario = w.usuario_del_libro(s, rut)
    print(f"   Usuario con que Webclass entra al libro: {usuario}")
    if usuario != rut.split("-")[0]:
        print("   (ojo: no es tu RUT. Pasa cuando la persona tiene más de una cuenta.)")
    entrada = s.post(f"{WEBICP}/loginFromWebclass",
                     data={"username": usuario, "module": "/classbook"},
                     headers=w.HEADERS, timeout=120)
    print(f"   loginFromWebclass respondió HTTP {entrada.status_code}.")
    resp = s.get(f"{WEBICP}/portada-profesor", headers=w.HEADERS, timeout=120)
    token = re.search(r'name="csrf-token" content="([^"]+)"', resp.text)
    if not token:
        print("   FALLÓ:")
        for linea in w.por_que_no_entro(resp, resp.text, entrada).splitlines():
            print(f"     {linea}")
        print("\n   El libro de clases no va a funcionar para esta cuenta, pero lo")
        print("   demás (recursos y asignación) sí, si el paso 2 salió bien.")
        sys.exit(1)
    print("   OK: entré al libro.")

    paso(4, "Pidiendo tus cursos…")
    libro = html.unescape(s.get(f"{WEBICP}/classbook", headers=w.HEADERS, timeout=120).text)
    colegio = re.search(r'"colegio":(\d+)', libro)
    if not colegio:
        print("   FALLÓ: no pude leer el id del colegio desde el libro.")
        sys.exit(1)
    r = s.get(f"{WEBICP}/api/portadaProfesor/getCourses",
              params={"idColegio": colegio.group(1), "anio": datetime.date.today().year,
                      "idUsuario": iduser.group(1)},
              headers={**w.HEADERS, "X-CSRF-TOKEN": token.group(1),
                       "X-Requested-With": "XMLHttpRequest"}, timeout=120)
    if r.status_code != 200:
        print(f"   FALLÓ: el libro respondió HTTP {r.status_code}.")
        sys.exit(1)
    cursos = r.json().get("data", {}).get("courses", [])
    print(f"   OK: colegio {colegio.group(1)}, {len(cursos)} curso(s).")
    for c in cursos[:12]:
        print(f"     · {c.get('cur_nom') or c}")

    print("\n=== Todo en orden: esta cuenta puede usar las herramientas completas. ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
