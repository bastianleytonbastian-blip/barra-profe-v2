"""Prueba de red: lógica pura y una conexión real por loopback (sin salir del computador)."""

import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import probar_red as R  # noqa: E402


class Pura(unittest.TestCase):
    def test_difusion_y_subred(self):
        self.assertEqual(R.broadcast_de("192.168.1.40"), "192.168.1.255")
        self.assertEqual(R.broadcast_de("raro"), "255.255.255.255")
        self.assertTrue(R.misma_subred("192.168.1.4", "192.168.1.200"))
        self.assertFalse(R.misma_subred("192.168.1.4", "192.168.2.4"))

    def test_el_anuncio_de_otro_se_lee_y_el_propio_se_ignora(self):
        msg = R.armar_hola("PC-SALA", 50575, "abc12345")
        self.assertEqual(R.leer_hola(msg, propio="otro"), {"id": "abc12345", "nombre": "PC-SALA", "tcp": 50575})
        self.assertIsNone(R.leer_hola(msg, propio="abc12345"))
        for basura in (b"", b"no es json", b'{"t": "otra cosa"}', b"[1, 2]"):
            self.assertIsNone(R.leer_hola(basura))

    def test_diagnostico_sin_nadie(self):
        texto = " ".join(R.diagnostico("192.168.1.4", {}, {}, set()))
        self.assertIn("No vi ningún otro computador", texto)
        self.assertIn("aísla", texto)

    def test_diagnostico_ok_en_los_dos_sentidos(self):
        pares = {"192.168.1.9": {"nombre": "PC-B"}}
        texto = " ".join(R.diagnostico("192.168.1.4", pares, {"192.168.1.9": True}, {"192.168.1.9"}))
        self.assertIn("viable", texto)
        self.assertNotIn("✗", texto)

    def test_diagnostico_se_ven_pero_no_se_conectan(self):
        pares = {"192.168.1.9": {"nombre": "PC-B"}}
        texto = " ".join(R.diagnostico("192.168.1.4", pares, {"192.168.1.9": False}, set()))
        self.assertIn("firewall", texto.lower())
        self.assertNotIn("viable", texto)

    def test_otra_subred_se_advierte(self):
        pares = {"10.0.0.9": {"nombre": "PC-B"}}
        self.assertIn("otra subred", " ".join(R.diagnostico("192.168.1.4", pares, {}, set())))


class ConexionReal(unittest.TestCase):
    def test_ping_pong_por_loopback(self):
        puerto = 50999
        entrantes, parar, listo = set(), threading.Event(), threading.Event()
        hilo = threading.Thread(target=R.servidor_tcp, args=(puerto, entrantes, parar, listo), daemon=True)
        hilo.start()
        self.assertTrue(listo.wait(3))
        self.assertTrue(R.ping_tcp("127.0.0.1", puerto))
        self.assertEqual(entrantes, {"127.0.0.1"})
        parar.set()
        hilo.join(3)
        self.assertFalse(R.ping_tcp("127.0.0.1", puerto, espera=0.5))       # ya no responde


if __name__ == "__main__":
    unittest.main()
