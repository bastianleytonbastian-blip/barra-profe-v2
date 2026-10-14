"""
Envío de guías al equipo PIE por correo (Gmail, contraseña de aplicación).

La contraseña de aplicación NO se guarda en ningún archivo: queda en el Administrador de
credenciales de Windows (keyring), igual que la clave de Webclass. En el perfil del docente
solo se anotan el remitente y el correo del equipo PIE.

  correo --guardar-clave                  pide la contraseña de aplicación y la guarda
  correo --datos correo.json [--simular] [--seleccion s.json]    envía (o muestra) el correo
  correo --probar                         se envía un correo de prueba al propio remitente

correo.json: {"archivos": ["C:\\...\\guia.pdf"], "asunto": "...", "mensaje": "..."}

Cómo obtener la contraseña de aplicación: Cuenta de Google > Seguridad > Verificación en
dos pasos (activada) > Contraseñas de aplicaciones. Es una clave de 16 letras que sirve solo
para este programa y se puede revocar cuando se quiera.
"""

from __future__ import annotations

import argparse
import getpass
import json
import mimetypes
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage

import keyring

import webclass_tareas as w
from barra_utiles import texto_de_correo as mensaje_por_defecto  # noqa: F401  (asunto y cuerpo de partida)

SERVICIO = "barra-correo"
SERVIDOR, PUERTO = "smtp.gmail.com", 465
DESTINO_PIE = "impresionespiemtc@gmail.com"
MAXIMO_BYTES = 18 * 1024 * 1024        # Gmail admite 25 MB en total; el adjunto crece un tercio al codificarse
PROHIBIDAS = {".exe", ".bat", ".cmd", ".com", ".scr", ".js", ".jar", ".msi", ".vbs", ".ps1", ".dll"}


# ---------------------------------------------------------------- lógica pura
def direccion_valida(texto: str) -> bool:
    texto = (texto or "").strip()
    return texto.count("@") == 1 and " " not in texto and "." in texto.split("@")[1] \
        and not texto.startswith("@") and not texto.endswith((".", "@"))


def limpiar_clave(clave: str) -> str:
    """Google muestra la contraseña de aplicación en grupos de 4 con espacios."""
    return "".join((clave or "").split())


def revisar_archivos(rutas: list[str]) -> tuple[list[str], list[str]]:
    """Separa los archivos que sirven de los que no, con la razón de cada descarte."""
    buenos, problemas, total = [], [], 0
    for ruta in rutas:
        nombre = os.path.basename(ruta)
        extension = os.path.splitext(nombre)[1].lower()
        if not os.path.isfile(ruta):
            problemas.append(f"{nombre}: el archivo no existe")
        elif extension in PROHIBIDAS:
            problemas.append(f"{nombre}: Gmail no admite archivos {extension}")
        else:
            tamano = os.path.getsize(ruta)
            if total + tamano > MAXIMO_BYTES:
                problemas.append(f"{nombre}: junto con los otros pasa de {MAXIMO_BYTES // (1024 * 1024)} MB")
            else:
                total += tamano
                buenos.append(ruta)
    return buenos, problemas


def construir_mensaje(remitente: str, destinatario: str, asunto: str, cuerpo: str,
                      archivos: list[str]) -> EmailMessage:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = remitente, destinatario, asunto
    msg.set_content(cuerpo)
    for ruta in archivos:
        tipo, _ = mimetypes.guess_type(ruta)
        principal, _, sub = (tipo or "application/octet-stream").partition("/")
        with open(ruta, "rb") as f:
            msg.add_attachment(f.read(), maintype=principal, subtype=sub or "octet-stream",
                               filename=os.path.basename(ruta))
    return msg


# ------------------------------------------------------------- credenciales y envío
def remitente_de(perfil: dict) -> str:
    return (perfil.get("correo") or {}).get("remitente", "")


def destinatario_de(perfil: dict) -> str:
    return (perfil.get("correo") or {}).get("pie") or DESTINO_PIE


def clave_guardada(remitente: str) -> str:
    try:
        return keyring.get_password(SERVICIO, remitente) or ""
    except Exception:  # noqa: BLE001  (sin llavero disponible)
        return ""


def guardar_clave(remitente: str, clave: str) -> None:
    keyring.set_password(SERVICIO, remitente, limpiar_clave(clave))


def explicar_error(exc: Exception) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return ("Gmail rechazó la contraseña. Hace falta una contraseña de APLICACIÓN (no la normal): "
                "revisa que la verificación en dos pasos esté activada y vuelve a guardarla.")
    if isinstance(exc, (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused)):
        return "Gmail rechazó la dirección del remitente o del destinatario."
    if isinstance(exc, (TimeoutError, OSError)):
        return "No pude conectarme a Gmail (¿sin internet?). El correo no se envió."
    return f"No se pudo enviar: {str(exc)[:120]}"


def enviar(msg: EmailMessage, remitente: str, clave: str, conectar=None) -> None:
    """Envía por Gmail con SSL. `conectar` existe para poder probarlo sin red."""
    conectar = conectar or (lambda: smtplib.SMTP_SSL(SERVIDOR, PUERTO, timeout=60,
                                                     context=ssl.create_default_context()))
    with conectar() as servidor:
        servidor.login(remitente, clave)
        servidor.send_message(msg)


# ------------------------------------------------------------------------ main
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--perfil", choices=sorted(w.PERFILES), default=w.PERFIL_POR_DEFECTO)
    p.add_argument("--guardar-clave", action="store_true", help="Guarda la contraseña de aplicación.")
    p.add_argument("--probar", action="store_true", help="Se envía un correo de prueba al remitente.")
    p.add_argument("--datos", metavar="correo.json")
    p.add_argument("--simular", action="store_true")
    p.add_argument("--seleccion", metavar="ARCHIVO.json")
    a = p.parse_args()
    perfil = w.PERFILES[a.perfil]
    remitente = remitente_de(perfil)

    if a.guardar_clave:
        if not remitente:
            remitente = input("Tu correo de Gmail (desde el que se enviará): ").strip()
            if not direccion_valida(remitente):
                raise ValueError("Ese correo no parece válido.")
            import unidades
            nuevo = json.loads(json.dumps(perfil))
            nuevo.setdefault("correo", {})["remitente"] = remitente
            nuevo["correo"].setdefault("pie", DESTINO_PIE)
            unidades.guardar_perfil(a.perfil, nuevo)
        clave = limpiar_clave(getpass.getpass(f"Contraseña de aplicación de {remitente}: "))
        if len(clave) < 12:
            raise ValueError("Esa clave es muy corta: la de aplicación tiene 16 letras.")
        guardar_clave(remitente, clave)
        print("Contraseña guardada en el Administrador de credenciales de Windows.")
        return

    if not remitente or not clave_guardada(remitente):
        raise ValueError("Falta configurar el correo: guarda tu remitente y la contraseña de aplicación "
                         "(botón «Enviar al equipo PIE», opción Configurar correo).")

    if a.probar:
        msg = construir_mensaje(remitente, remitente, "Prueba de Barra Profe",
                                "Si lees esto, el envío de correos de la barra funciona.", [])
        enviar(msg, remitente, clave_guardada(remitente))
        print(f"Correo de prueba enviado a {remitente}.")
        return

    if not a.datos:
        raise ValueError("Indica --datos correo.json, --guardar-clave o --probar.")
    with open(a.datos, encoding="utf-8") as f:
        datos = json.load(f)
    destinatario = destinatario_de(perfil)
    if not direccion_valida(destinatario):
        raise ValueError(f"El correo de destino «{destinatario}» no es válido.")
    elegidas = w.leer_seleccion(a.seleccion)
    pedidos = [r for r in datos.get("archivos", []) if elegidas is None or r in elegidas]
    for r in datos.get("archivos", []):
        if r not in pedidos:
            w.item(r, "omitido", os.path.basename(r), "ARCHIVOS", "adjunto")
    buenos, problemas = revisar_archivos(pedidos)
    for texto in problemas:
        nombre = texto.split(":")[0]
        ruta = next((r for r in pedidos if os.path.basename(r) == nombre), nombre)
        w.item(ruta, "pendiente", nombre, "ARCHIVOS", "adjunto", motivo=texto.split(":", 1)[1].strip())
    if not buenos:
        print("No hay archivos para enviar.")
        w.imprimir_resultado(w.ITEMS, vacio="No había archivos para enviar.")
        return
    asunto = (datos.get("asunto") or "").strip()
    if not asunto:
        raise ValueError("Falta el asunto del correo.")
    detalle = f"para {destinatario}"
    if a.simular:
        for r in buenos:
            w.item(r, "propuesto", os.path.basename(r), "ARCHIVOS", "adjunto", detalle)
        print(f"[SIMULAR] Se enviaría «{asunto}» a {destinatario} con {len(buenos)} archivo(s).")
        return
    msg = construir_mensaje(remitente, destinatario, asunto, datos.get("mensaje", ""), buenos)
    try:
        enviar(msg, remitente, clave_guardada(remitente))
    except Exception as exc:  # noqa: BLE001
        for r in buenos:
            w.item(r, "error", os.path.basename(r), "ARCHIVOS", "adjunto", motivo=explicar_error(exc))
    else:
        for r in buenos:
            w.item(r, "hecho", os.path.basename(r), "ARCHIVOS", "adjunto", f"enviado a {destinatario}")
    w.imprimir_resultado(w.ITEMS, vacio="No había archivos para enviar.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
