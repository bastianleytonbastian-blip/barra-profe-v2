"""
Mensajería interna entre barras por la red del colegio (sin servidor, sin internet, sin IA).

Cada barra es un «nodo»:
  - se anuncia por difusión UDP («estoy aquí») y escucha a las demás;
  - envía y recibe mensajes por TCP, directo de computador a computador;
  - todo (anuncios y mensajes) va CIFRADO y firmado con una clave de grupo que solo conocen
    quienes la tienen (Fernet: AES-128 + HMAC). Sin la clave no se puede leer ni escribir;
  - si el destinatario no está conectado, el mensaje queda en una cola local y se entrega
    apenas aparezca (el emisor ve «pendiente» hasta que llegue la confirmación);
  - el historial queda solo en cada computador (un archivo JSON).

Límite honesto: dos equipos solo pueden hablarse si están en la misma red a la vez; no hay
buzón central. Un mensaje para alguien que nunca se ha visto no tiene dirección a dónde ir.
"""

from __future__ import annotations

import json
import os
import socket
import struct
import threading
import time
import uuid
from typing import Callable

from cryptography.fernet import Fernet, InvalidToken

PUERTO_UDP = 50576
PUERTO_TCP = 50577
TODOS = "*"
MAX_MENSAJE = 4000            # letras por aviso: esto es mensajería corta, no correo
MAX_MARCO = 64 * 1024         # bytes por trama: nadie puede pedirnos memoria sin límite
MAX_HISTORIAL = 500
SERVICIO_CLAVE = "barra-mensajeria"


# ------------------------------------------------------------------ cifrado
def generar_clave() -> str:
    """Una clave de grupo nueva (texto, para copiar y pegar)."""
    return Fernet.generate_key().decode()


def clave_valida(clave: str) -> bool:
    try:
        Fernet((clave or "").strip().encode())
        return True
    except (ValueError, TypeError):
        return False


def sellar(clave: str, datos: dict) -> bytes:
    return Fernet(clave.encode()).encrypt(json.dumps(datos, ensure_ascii=False).encode())


def abrir(clave: str, token: bytes, ttl: int | None = None) -> dict | None:
    """El contenido si el token es auténtico (y no demasiado viejo, si se pide ttl); si no, None."""
    try:
        dato = json.loads(Fernet(clave.encode()).decrypt(token, ttl=ttl).decode())
    except (InvalidToken, ValueError, TypeError):
        return None
    return dato if isinstance(dato, dict) else None


# ------------------------------------------------------------------ tramas TCP
def enviar_trama(sock: socket.socket, token: bytes) -> None:
    sock.sendall(struct.pack(">I", len(token)) + token)


def leer_trama(sock: socket.socket) -> bytes | None:
    cabecera = _leer_exacto(sock, 4)
    if not cabecera:
        return None
    largo = struct.unpack(">I", cabecera)[0]
    if largo == 0 or largo > MAX_MARCO:
        return None
    return _leer_exacto(sock, largo)


def _leer_exacto(sock: socket.socket, n: int) -> bytes | None:
    datos = b""
    while len(datos) < n:
        try:
            trozo = sock.recv(n - len(datos))
        except OSError:                  # la otra punta cortó o no contestó a tiempo
            return None
        if not trozo:
            return None
        datos += trozo
    return datos


# ------------------------------------------------------------------ almacén
class Almacen:
    """Historial, pendientes y equipos conocidos en un archivo JSON (escritura atómica)."""

    def __init__(self, ruta: str):
        self.ruta = ruta
        self.candado = threading.RLock()
        self.datos = {"mensajes": [], "pendientes": {}, "conocidos": {}, "leidos": []}
        try:
            with open(ruta, encoding="utf-8") as f:
                leido = json.load(f)
            if isinstance(leido, dict):
                self.datos.update({k: leido[k] for k in self.datos if k in leido})
        except (OSError, ValueError):
            pass

    def guardar(self) -> None:
        with self.candado:
            os.makedirs(os.path.dirname(os.path.abspath(self.ruta)), exist_ok=True)
            temporal = self.ruta + ".tmp"
            with open(temporal, "w", encoding="utf-8") as f:
                json.dump(self.datos, f, ensure_ascii=False)
            os.replace(temporal, self.ruta)


# --------------------------------------------------------------------- nodo
class Nodo:
    def __init__(self, nombre: str, clave: str, ruta_almacen: str, *, puerto_udp: int = PUERTO_UDP,
                 puerto_tcp: int = PUERTO_TCP, al_recibir: Callable[[dict], None] | None = None,
                 destinos_udp: list[tuple[str, int]] | None = None, intervalo: float = 3.0,
                 vigencia: float = 12.0, difundir: bool = True):
        if not clave_valida(clave):
            raise ValueError("La clave del grupo no es válida.")
        self.nombre, self.clave = nombre.strip(), clave.strip()
        self.puerto_udp, self.puerto_tcp = puerto_udp, puerto_tcp
        self.al_recibir = al_recibir
        self.destinos_udp = list(destinos_udp or [])
        self.intervalo, self.vigencia, self.difundir = intervalo, vigencia, difundir
        self.almacen = Almacen(ruta_almacen)
        self.parar = threading.Event()
        self.hilos: list[threading.Thread] = []
        self.visto: dict[str, float] = {}          # nombre -> última vez que se anunció
        self.direccion: dict[str, tuple[str, int]] = {}   # nombre -> (ip, puerto tcp)
        self.candado = threading.RLock()
        self._servidor: socket.socket | None = None

    # ------------------------------------------------------------- ciclo de vida
    def iniciar(self) -> None:
        self._servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._servidor.bind(("", self.puerto_tcp))
        self._servidor.listen(8)
        self._servidor.settimeout(0.5)
        for destino in (self._servir, self._escuchar_udp, self._anunciar):
            hilo = threading.Thread(target=destino, daemon=True)
            hilo.start()
            self.hilos.append(hilo)

    def detener(self) -> None:
        self.parar.set()
        if self._servidor:
            try:
                self._servidor.close()
            except OSError:
                pass
        for hilo in self.hilos:
            hilo.join(2)

    # --------------------------------------------------------------- descubrimiento
    def _anunciar(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not self.parar.is_set():
            token = sellar(self.clave, {"t": "hola", "nombre": self.nombre, "tcp": self.puerto_tcp})
            destinos = list(self.destinos_udp)
            if self.difundir:
                destinos += [("255.255.255.255", self.puerto_udp)]
            for destino in destinos:
                try:
                    sock.sendto(token, destino)
                except OSError:
                    pass
            self.parar.wait(self.intervalo)
        sock.close()

    def _escuchar_udp(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", self.puerto_udp))
        except OSError:
            return
        sock.settimeout(0.5)
        while not self.parar.is_set():
            try:
                datos, (ip, _p) = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            hola = abrir(self.clave, datos, ttl=300)         # un anuncio viejo no vale (repetición)
            if not hola or hola.get("t") != "hola" or not hola.get("nombre") or hola["nombre"] == self.nombre:
                continue
            self._ver(str(hola["nombre"])[:40], ip, int(hola.get("tcp") or self.puerto_tcp))
        sock.close()

    def _ver(self, nombre: str, ip: str, puerto: int) -> None:
        nuevo = False
        with self.candado:
            nuevo = nombre not in self.visto or time.time() - self.visto[nombre] > self.vigencia
            self.visto[nombre] = time.time()
            self.direccion[nombre] = (ip, puerto)
        with self.almacen.candado:
            conocido = self.almacen.datos["conocidos"].get(nombre)
            if conocido != {"ip": ip, "tcp": puerto}:
                self.almacen.datos["conocidos"][nombre] = {"ip": ip, "tcp": puerto}
                self.almacen.guardar()
        if nuevo:
            threading.Thread(target=self.entregar_pendientes, args=(nombre,), daemon=True).start()

    def en_linea(self) -> list[str]:
        ahora = time.time()
        with self.candado:
            return sorted(n for n, t in self.visto.items() if ahora - t <= self.vigencia)

    def conocidos(self) -> list[str]:
        with self.almacen.candado:
            return sorted(self.almacen.datos["conocidos"])

    # ------------------------------------------------------------------ recepción
    def _servir(self) -> None:
        while not self.parar.is_set():
            try:
                conexion, _dir = self._servidor.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._atender, args=(conexion,), daemon=True).start()

    def _atender(self, conexion: socket.socket) -> None:
        with conexion:
            try:
                conexion.settimeout(5)
                token = leer_trama(conexion)
                msg = abrir(self.clave, token) if token else None
                if not msg or msg.get("t") != "msg" or not msg.get("id"):
                    return                                    # clave ajena o basura: se ignora
                texto = str(msg.get("texto", ""))[:MAX_MENSAJE]
                nuevo = self._guardar_recibido({"id": str(msg["id"]), "de": str(msg.get("de", ""))[:40],
                                                "para": str(msg.get("para", TODOS))[:40], "texto": texto,
                                                "ts": float(msg.get("ts") or time.time())})
                enviar_trama(conexion, sellar(self.clave, {"t": "ack", "id": str(msg["id"])}))
                if nuevo and self.al_recibir:
                    try:
                        self.al_recibir(nuevo)
                    except Exception:  # noqa: BLE001  (un fallo de la interfaz no tumba la red)
                        pass
            except (OSError, ValueError):
                pass

    def _guardar_recibido(self, msg: dict) -> dict | None:
        """Guarda el mensaje si no lo teníamos; devuelve None si era repetido."""
        with self.almacen.candado:
            if any(m["id"] == msg["id"] for m in self.almacen.datos["mensajes"]):
                return None
            msg = {**msg, "entrante": True}
            self.almacen.datos["mensajes"].append(msg)
            del self.almacen.datos["mensajes"][:-MAX_HISTORIAL]
            self.almacen.guardar()
            return msg

    # ---------------------------------------------------------------------- envío
    def enviar(self, texto: str, para: str = TODOS) -> dict:
        """Envía un aviso a una persona (o a todos los conocidos). Devuelve el mensaje registrado."""
        texto = (texto or "").strip()
        if not texto:
            raise ValueError("El mensaje está vacío.")
        if len(texto) > MAX_MENSAJE:
            raise ValueError(f"El mensaje pasa de {MAX_MENSAJE} letras.")
        destinatarios = ([n for n in self.conocidos() if n != self.nombre] if para == TODOS else [para])
        if not destinatarios:
            raise ValueError("Todavía no conozco a nadie: espera a que otra barra se conecte.")
        msg = {"id": uuid.uuid4().hex, "de": self.nombre, "para": para, "texto": texto, "ts": time.time()}
        with self.almacen.candado:
            registro = {**msg, "entrante": False, "entregado": [], "destinatarios": destinatarios}
            self.almacen.datos["mensajes"].append(registro)
            del self.almacen.datos["mensajes"][:-MAX_HISTORIAL]
            for d in destinatarios:
                self.almacen.datos["pendientes"].setdefault(d, []).append(msg["id"])
            self.almacen.guardar()
        for d in destinatarios:
            if d in self.en_linea():
                self.entregar_pendientes(d)
        return registro

    def entregar_pendientes(self, nombre: str) -> int:
        """Intenta entregar a `nombre` lo que le quedó pendiente. Devuelve cuántos llegaron."""
        with self.almacen.candado:
            ids = list(self.almacen.datos["pendientes"].get(nombre, []))
            por_id = {m["id"]: m for m in self.almacen.datos["mensajes"]}
        llegaron = 0
        for id_ in ids:
            msg = por_id.get(id_)
            if msg is None:                                  # ya salió del historial
                self._quitar_pendiente(nombre, id_)
                continue
            if self._entregar(nombre, msg):
                llegaron += 1
                self._quitar_pendiente(nombre, id_, entregado=True)
            else:
                break                                        # si falla uno, el resto también
        return llegaron

    def _quitar_pendiente(self, nombre: str, id_: str, entregado: bool = False) -> None:
        with self.almacen.candado:
            lista = self.almacen.datos["pendientes"].get(nombre, [])
            if id_ in lista:
                lista.remove(id_)
            if not lista:
                self.almacen.datos["pendientes"].pop(nombre, None)
            if entregado:
                for m in self.almacen.datos["mensajes"]:
                    if m["id"] == id_ and nombre not in m.get("entregado", []):
                        m.setdefault("entregado", []).append(nombre)
            self.almacen.guardar()

    def _entregar(self, nombre: str, msg: dict) -> bool:
        with self.candado:
            ip, puerto = self.direccion.get(nombre) or (None, None)
        if not ip:
            conocido = self.almacen.datos["conocidos"].get(nombre)
            if not conocido:
                return False
            ip, puerto = conocido["ip"], conocido["tcp"]
        paquete = {"t": "msg", "id": msg["id"], "de": msg["de"], "para": msg["para"],
                   "texto": msg["texto"], "ts": msg["ts"]}
        try:
            with socket.create_connection((ip, puerto), timeout=4) as s:
                s.settimeout(5)
                enviar_trama(s, sellar(self.clave, paquete))
                token = leer_trama(s)
            respuesta = abrir(self.clave, token) if token else None
            return bool(respuesta and respuesta.get("t") == "ack" and respuesta.get("id") == msg["id"])
        except OSError:
            return False

    # --------------------------------------------------------------- lectura
    def mensajes(self) -> list[dict]:
        with self.almacen.candado:
            return list(self.almacen.datos["mensajes"])

    def no_leidos(self) -> int:
        with self.almacen.candado:
            leidos = set(self.almacen.datos["leidos"])
            return sum(1 for m in self.almacen.datos["mensajes"] if m.get("entrante") and m["id"] not in leidos)

    def marcar_leidos(self) -> None:
        with self.almacen.candado:
            self.almacen.datos["leidos"] = [m["id"] for m in self.almacen.datos["mensajes"] if m.get("entrante")]
            self.almacen.guardar()

    def pendientes(self, nombre: str | None = None) -> int:
        with self.almacen.candado:
            p = self.almacen.datos["pendientes"]
            return len(p.get(nombre, [])) if nombre else sum(len(v) for v in p.values())
