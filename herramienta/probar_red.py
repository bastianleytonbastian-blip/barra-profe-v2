"""
Prueba de red para mensajería entre barras: ¿se ven dos computadores en la wifi del colegio?

Se ejecuta en DOS computadores, conectados a la misma red, al mismo tiempo:

    python probar_red.py                 (dura 90 segundos; Ctrl+C para terminar antes)
    python probar_red.py --ip 192.168.1.40     (si el otro computador no aparece solo)

No envía nada a internet, no lee archivos y no guarda nada: solo anuncia «estoy aquí» a la red
local y comprueba si el otro computador responde. La primera vez Windows preguntará si permites
a Python recibir conexiones en la red: para esta prueba hay que PERMITIR (red privada/pública).

Al final dice qué funcionó y, si algo falló, la causa más probable.
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time
import uuid

PUERTO_UDP = 50574
PUERTO_TCP = 50575
ID = uuid.uuid4().hex[:8]


# ---------------------------------------------------------------- lógica pura
def broadcast_de(ip: str) -> str:
    """Dirección de difusión suponiendo una red /24 (la habitual en colegios y casas)."""
    partes = ip.split(".")
    return ".".join(partes[:3] + ["255"]) if len(partes) == 4 else "255.255.255.255"


def misma_subred(a: str, b: str) -> bool:
    return a.split(".")[:3] == b.split(".")[:3]


def armar_hola(nombre: str, puerto_tcp: int, id_: str = ID) -> bytes:
    return json.dumps({"t": "hola", "id": id_, "nombre": nombre, "tcp": puerto_tcp}).encode()


def leer_hola(datos: bytes, propio: str = ID) -> dict | None:
    """El anuncio de otro computador, o None si no es uno (o es el propio)."""
    try:
        msg = json.loads(datos.decode("utf-8", "replace"))
    except ValueError:
        return None
    if not isinstance(msg, dict) or msg.get("t") != "hola" or msg.get("id") == propio:
        return None
    return {"id": str(msg.get("id")), "nombre": str(msg.get("nombre", ""))[:40],
            "tcp": int(msg.get("tcp") or PUERTO_TCP)}


def diagnostico(mi_ip: str, pares: dict, tcp_saliente: dict, tcp_entrante: set, probe_ip: str = "") -> list[str]:
    """Qué se concluye de lo observado, en frases para el usuario."""
    lineas = []
    if not pares and not probe_ip:
        lineas.append("✗ No vi ningún otro computador por difusión (UDP).")
        lineas.append("   Causas posibles: el otro no tiene la prueba corriendo, la wifi aísla a los "
                      "dispositivos entre sí, o el Firewall de Windows bloqueó a Python (acepta el aviso "
                      "o permite «python.exe» en redes privadas y públicas).")
        lineas.append("   Prueba con --ip <dirección del otro> para ver si al menos la conexión directa funciona.")
        return lineas
    for ip, info in pares.items():
        misma = misma_subred(mi_ip, ip)
        lineas.append(f"✓ Vi a «{info['nombre']}» ({ip}) por difusión."
                      + ("" if misma else "  ⚠ Está en otra subred: puede que cable y wifi estén separados."))
    for ip, ok in tcp_saliente.items():
        lineas.append(f"{'✓' if ok else '✗'} Conexión directa hacia {ip}: {'funciona' if ok else 'no respondió'}.")
        if not ok:
            lineas.append("   El firewall del otro computador probablemente bloquea conexiones entrantes.")
    for ip in sorted(tcp_entrante):
        lineas.append(f"✓ {ip} se pudo conectar a este computador.")
    if (pares or probe_ip) and not any(tcp_saliente.values()) and not tcp_entrante:
        lineas.append("✗ Se ven por difusión pero no se conectan: es el síntoma típico de firewall o de "
                      "aislamiento de clientes.")
    if any(tcp_saliente.values()) or tcp_entrante:
        lineas.append("→ La mensajería directa por la red del colegio es viable entre estos dos equipos.")
    return lineas


# ------------------------------------------------------------------ red real
def mi_ip() -> str:
    """La dirección con la que este equipo sale a la red local (no envía nada)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def servidor_tcp(puerto: int, entrantes: set, parar: threading.Event, listo: threading.Event | None = None) -> None:
    """Responde «pong» a quien se conecta y anota quién fue."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("", puerto))
    srv.listen(5)
    srv.settimeout(1)
    if listo:
        listo.set()
    while not parar.is_set():
        try:
            conexion, (ip, _p) = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        with conexion:
            try:
                conexion.settimeout(3)
                if conexion.recv(16).startswith(b"ping"):
                    conexion.sendall(b"pong")
                    entrantes.add(ip)
            except OSError:
                pass
    srv.close()


def ping_tcp(ip: str, puerto: int, espera: float = 3.0) -> bool:
    try:
        with socket.create_connection((ip, puerto), timeout=espera) as s:
            s.sendall(b"ping")
            s.settimeout(espera)
            return s.recv(16).startswith(b"pong")
    except OSError:
        return False


def escuchar_udp(pares: dict, parar: threading.Event, mi: str) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", PUERTO_UDP))
    except OSError as exc:
        print(f"✗ No pude abrir el puerto UDP {PUERTO_UDP}: {exc}")
        return
    sock.settimeout(1)
    while not parar.is_set():
        try:
            datos, (ip, _p) = sock.recvfrom(1024)
        except socket.timeout:
            continue
        except OSError:
            break
        hola = leer_hola(datos)
        if hola and ip != mi and ip not in pares:
            pares[ip] = hola
            print(f"  → apareció «{hola['nombre']}» en {ip}")
    sock.close()


def anunciar(mi: str, nombre: str, parar: threading.Event) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    destinos = {"255.255.255.255", broadcast_de(mi)}
    while not parar.is_set():
        for d in destinos:
            try:
                sock.sendto(armar_hola(nombre, PUERTO_TCP), (d, PUERTO_UDP))
            except OSError:
                pass
        parar.wait(2)
    sock.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ip", default="", help="Dirección del otro computador, si no aparece solo.")
    p.add_argument("--segundos", type=int, default=90)
    a = p.parse_args()
    nombre, mi = socket.gethostname(), mi_ip()
    print(f"Este computador: {nombre} · {mi} · id {ID}")
    print("Ejecuta lo mismo en el otro computador, con la misma red, ahora.")
    if mi.startswith("127."):
        print("✗ No parece haber conexión de red.")
        return
    pares: dict[str, dict] = {}
    entrantes: set[str] = set()
    saliente: dict[str, bool] = {}
    parar = threading.Event()
    for objetivo, args in ((servidor_tcp, (PUERTO_TCP, entrantes, parar)), (escuchar_udp, (pares, parar, mi)),
                           (anunciar, (mi, nombre, parar))):
        threading.Thread(target=objetivo, args=args, daemon=True).start()
    fin = time.time() + a.segundos
    try:
        while time.time() < fin:
            objetivos = list(pares) + ([a.ip] if a.ip and a.ip not in pares else [])
            for ip in objetivos:
                if not saliente.get(ip):
                    saliente[ip] = ping_tcp(ip, pares.get(ip, {}).get("tcp", PUERTO_TCP))
                    if saliente[ip]:
                        print(f"  → conexión directa con {ip}: ¡funciona!")
            if any(saliente.values()) and entrantes:
                break                      # ya se comprobó en los dos sentidos
            time.sleep(3)
    except KeyboardInterrupt:
        pass
    parar.set()
    print("\n=== Resultado ===")
    for linea in diagnostico(mi, pares, saliente, entrantes, a.ip):
        print(linea)


if __name__ == "__main__":
    main()
