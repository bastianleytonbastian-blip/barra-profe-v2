"""Mensajería interna por red: cifrado, encuentro, entrega, pendientes y rechazo de intrusos.

Los nodos se hablan por loopback (127.0.0.1) con puertos propios de cada prueba.
"""

import itertools
import os
import socket
import struct
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import mensajeria_red as M  # noqa: E402

_PUERTOS = itertools.count(50700, 10)
CLAVE = M.generar_clave()


def esperar(condicion, tiempo=6.0):
    fin = time.time() + tiempo
    while time.time() < fin:
        if condicion():
            return True
        time.sleep(0.05)
    return False


class Cifrado(unittest.TestCase):
    def test_ida_y_vuelta(self):
        token = M.sellar(CLAVE, {"t": "msg", "texto": "Reunión PIE a las 15:00 ñandú"})
        self.assertEqual(M.abrir(CLAVE, token)["texto"], "Reunión PIE a las 15:00 ñandú")

    def test_otra_clave_o_un_token_alterado_no_abren(self):
        token = M.sellar(CLAVE, {"t": "msg"})
        self.assertIsNone(M.abrir(M.generar_clave(), token))
        self.assertIsNone(M.abrir(CLAVE, token[:-3] + b"AAA"))
        self.assertIsNone(M.abrir(CLAVE, b"basura"))

    def test_un_token_viejo_se_rechaza_si_se_pide_vigencia(self):
        token = M.sellar(CLAVE, {"t": "hola"})
        time.sleep(1.1)
        self.assertIsNone(M.abrir(CLAVE, token, ttl=0))
        self.assertIsNotNone(M.abrir(CLAVE, token, ttl=60))

    def test_validacion_de_clave(self):
        self.assertTrue(M.clave_valida(CLAVE))
        for mala in ("", "corta", "x" * 44, None):
            self.assertFalse(M.clave_valida(mala))
        with self.assertRaises(ValueError):
            M.Nodo("Ana", "no es una clave", os.path.join(tempfile.mkdtemp(), "a.json"))


class Red(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.mkdtemp()
        self.nodos = []
        self.recibidos = {"A": [], "B": []}

    def tearDown(self):
        for n in self.nodos:
            n.detener()

    def nodo(self, nombre, base, otro_base, clave=CLAVE, archivo=None):
        n = M.Nodo(nombre, clave, os.path.join(self.carpeta, archivo or f"{nombre}.json"),
                   puerto_udp=base, puerto_tcp=base + 1, destinos_udp=[("127.0.0.1", otro_base)],
                   intervalo=0.2, vigencia=1.5, difundir=False,
                   al_recibir=lambda m, k=nombre: self.recibidos.setdefault(k, []).append(m))
        n.iniciar()
        self.nodos.append(n)
        return n

    def par(self):
        base = next(_PUERTOS)
        a = self.nodo("A", base, base + 4)
        b = self.nodo("B", base + 4, base)
        self.assertTrue(esperar(lambda: a.en_linea() == ["B"] and b.en_linea() == ["A"]))
        return a, b, base

    def test_se_encuentran_y_el_mensaje_llega_con_confirmacion(self):
        a, b, _ = self.par()
        registro = a.enviar("Hola equipo", "B")
        self.assertTrue(esperar(lambda: self.recibidos["B"]))
        self.assertEqual((self.recibidos["B"][0]["de"], self.recibidos["B"][0]["texto"]), ("A", "Hola equipo"))
        self.assertTrue(esperar(lambda: a.pendientes() == 0))
        self.assertEqual([m for m in a.mensajes() if m["id"] == registro["id"]][0]["entregado"], ["B"])

    def test_no_leidos_y_marcar_leidos(self):
        a, b, _ = self.par()
        a.enviar("uno", "B")
        a.enviar("dos", "B")
        self.assertTrue(esperar(lambda: b.no_leidos() == 2))
        self.assertEqual(a.no_leidos(), 0)                      # lo que uno envía no cuenta como pendiente de leer
        b.marcar_leidos()
        self.assertEqual(b.no_leidos(), 0)

    def test_un_mensaje_repetido_no_se_guarda_dos_veces(self):
        a, b, _ = self.par()
        registro = a.enviar("una sola vez", "B")
        self.assertTrue(esperar(lambda: self.recibidos["B"]))
        self.assertTrue(a._entregar("B", registro))               # llega otra vez el mismo id
        self.assertEqual(len([m for m in b.mensajes() if m["id"] == registro["id"]]), 1)
        self.assertEqual(len(self.recibidos["B"]), 1)

    def test_si_el_otro_no_esta_el_mensaje_espera_y_llega_cuando_vuelve(self):
        a, b, base = self.par()
        b.detener()
        self.assertTrue(esperar(lambda: a.en_linea() == []))
        registro = a.enviar("para cuando vuelvas", "B")
        self.assertEqual(a.pendientes("B"), 1)
        self.assertEqual([m for m in a.mensajes() if m["id"] == registro["id"]][0]["entregado"], [])
        b2 = self.nodo("B", base + 4, base, archivo="B.json")      # B vuelve (con su mismo historial)
        self.assertTrue(esperar(lambda: self.recibidos["B"]))
        self.assertEqual(self.recibidos["B"][0]["texto"], "para cuando vuelvas")
        self.assertTrue(esperar(lambda: a.pendientes() == 0))

    def test_a_todos_va_a_cada_conocido(self):
        a, b, _ = self.par()
        a.enviar("aviso general")                                  # para="*"
        self.assertTrue(esperar(lambda: self.recibidos["B"]))
        self.assertEqual(self.recibidos["B"][0]["para"], M.TODOS)

    def test_sin_conocidos_no_se_puede_enviar_a_todos(self):
        solo = self.nodo("A", next(_PUERTOS), 1)
        with self.assertRaises(ValueError):
            solo.enviar("¿alguien?")

    def test_mensaje_vacio_o_muy_largo(self):
        a, b, _ = self.par()
        for malo in ("   ", "x" * (M.MAX_MENSAJE + 1)):
            with self.assertRaises(ValueError):
                a.enviar(malo, "B")

    def test_quien_no_tiene_la_clave_no_puede_escribir_ni_aparecer(self):
        a, b, base = self.par()
        intruso = M.Nodo("Intruso", M.generar_clave(), os.path.join(self.carpeta, "i.json"),
                         puerto_udp=base + 8, puerto_tcp=base + 9, destinos_udp=[("127.0.0.1", base)],
                         intervalo=0.2, vigencia=1.5, difundir=False)
        intruso.iniciar()
        self.nodos.append(intruso)
        time.sleep(1.0)
        self.assertNotIn("Intruso", a.en_linea())                 # sus anuncios no se descifran
        with socket.create_connection(("127.0.0.1", base + 1), timeout=3) as s:   # y su mensaje directo tampoco
            M.enviar_trama(s, M.sellar(intruso.clave, {"t": "msg", "id": "x1", "de": "Intruso", "texto": "hola"}))
            s.settimeout(2)
            self.assertIsNone(M.leer_trama(s))                    # sin confirmación: se descarta
        self.assertEqual(a.mensajes(), [])

    def test_una_trama_gigante_se_corta_y_el_nodo_sigue_vivo(self):
        a, b, base = self.par()
        with socket.create_connection(("127.0.0.1", base + 1), timeout=3) as s:
            s.sendall(struct.pack(">I", M.MAX_MARCO + 1) + b"x")
            s.settimeout(2)
            self.assertIsNone(M.leer_trama(s))
        b.enviar("sigo aquí", "A")
        self.assertTrue(esperar(lambda: self.recibidos["A"]))

    def test_el_historial_sobrevive_a_reiniciar(self):
        a, b, base = self.par()
        a.enviar("guardado", "B")
        self.assertTrue(esperar(lambda: b.mensajes()))
        b.detener()
        otra_vez = M.Nodo("B", CLAVE, os.path.join(self.carpeta, "B.json"), puerto_udp=base + 4,
                          puerto_tcp=base + 5, difundir=False)
        self.assertEqual([m["texto"] for m in otra_vez.mensajes()], ["guardado"])
        self.assertEqual(otra_vez.no_leidos(), 1)


if __name__ == "__main__":
    unittest.main()
