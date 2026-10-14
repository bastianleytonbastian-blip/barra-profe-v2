"""Para quien mantiene Barra Profe: arma el paquete de actualización y lo publica como release de GitHub.

    python publicar.py            # arma el zip en la carpeta «publicaciones» y muestra qué haría
    python publicar.py --subir    # además crea el release en GitHub (necesita `gh` con sesión iniciada)

La versión sale de `herramienta\\VERSION` y las notas, de su sección en `CAMBIOS.md`.
No se incluye nada de `personal\\` ni `datos\\` (no están dentro de `herramienta\\`).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import zipfile

import actualizador

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SALIDA = os.path.join(RAIZ, "publicaciones")


def notas_de(version: str, ruta_cambios: str | None = None) -> str:
    """Texto de la sección «## <version>» de CAMBIOS.md."""
    with open(ruta_cambios or os.path.join(AQUI, "CAMBIOS.md"), encoding="utf-8-sig") as f:
        texto = f.read()
    m = re.search(rf"^## {re.escape(version)}\s*\n(.*?)(?=^## |\Z)", texto, re.S | re.M)
    return m.group(1).strip() if m else ""


def armar_zip(version: str, carpeta: str = AQUI, salida: str = SALIDA) -> tuple[str, str]:
    """Crea barra-profe-<version>.zip (+ .sha256). Excluye cachés y archivos del docente."""
    os.makedirs(salida, exist_ok=True)
    ruta = os.path.join(salida, f"barra-profe-{version}.zip")
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, archivos in os.walk(carpeta):
            dirs[:] = sorted(d for d in dirs if d not in actualizador.IGNORAR)
            for a in sorted(archivos):
                if a in actualizador.PROTEGIDOS or a.endswith((".pyc", ".nuevo", ".corrupto", ".log")):
                    continue
                completo = os.path.join(base, a)
                z.write(completo, os.path.join("herramienta", os.path.relpath(completo, carpeta)).replace("\\", "/"))
    sha = actualizador.suma_sha256(ruta)
    ruta_sha = ruta + ".sha256"
    with open(ruta_sha, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{sha}  {os.path.basename(ruta)}\n")
    return ruta, ruta_sha


def armar_manifiesto(version: str, notas: str, salida: str = SALIDA, repo: str = actualizador.REPO) -> str:
    """version.json: lo que consulta la barra de cada docente para saber si hay algo nuevo."""
    base = f"https://github.com/{repo}/releases/download/v{version}/barra-profe-{version}.zip"
    ruta = os.path.join(salida, "version.json")
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"version": version, "zip": base, "sha256": base + ".sha256", "notas": notas}, f, ensure_ascii=False, indent=2)
    return ruta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subir", action="store_true", help="crear el release en GitHub")
    args = ap.parse_args()
    from barra_utiles import leer_version
    version = leer_version(AQUI)
    if not version:
        raise SystemExit("Falta herramienta\\VERSION (formato MAYOR.MENOR.PARCHE).")
    notas = notas_de(version)
    if not notas:
        raise SystemExit(f"CAMBIOS.md no tiene una sección «## {version}». Anota qué cambió antes de publicar.")
    ruta, ruta_sha = armar_zip(version)
    ruta_json = armar_manifiesto(version, notas)
    print(f"Paquete: {ruta}\nSuma:    {ruta_sha}\nNotas:\n{notas}\n")
    if not args.subir:
        print("(Solo se armó el paquete. Usa --subir para publicarlo en GitHub.)")
        return
    orden = ["gh", "release", "create", f"v{version}", ruta, ruta_sha, ruta_json, "--repo", actualizador.REPO,
             "--title", f"Barra Profe {version}", "--notes", notas]
    sys.exit(subprocess.run(orden).returncode)


if __name__ == "__main__":
    main()
