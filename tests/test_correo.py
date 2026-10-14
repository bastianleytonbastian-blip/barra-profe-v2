"""Envío de guías al equipo PIE: mensaje, validaciones y corrida con un servidor de juguete."""

import json
import os
import smtplib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import correo_pie as C  # noqa: E402
import webclass_tareas as w  # noqa: E402


def archivo(nombre="guia.pdf", contenido=b"%PDF-1.4 hola"):
    ruta = os.path.join(tempfile.mkdtemp(), nombre)
    with open(ruta, "wb") as f:
        f.write(contenido)
    return ruta


class Servidor:
    """Remplaza a Gmail: anota lo que se le envía."""

    def __init__(self, falla=None):
        self.enviados, self.credenciales, self.falla = [], None, falla

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, usuario, clave):
        self.credenciales = (usuario, clave)

    def send_message(self, msg):
        if self.falla:
            raise self.falla
        self.enviados.append(msg)


class Pura(unittest.TestCase):
    def test_direcciones(self):
        self.assertTrue(C.direccion_valida("impresionespiemtc@gmail.com"))
        for mala in ("", "a@b", "sin arroba", "dos@@x.cl", "@x.cl", "a@x.", "a b@x.cl"):
            self.assertFalse(C.direccion_valida(mala), mala)

    def test_la_clave_de_google_se_limpia(self):
        self.assertEqual(C.limpiar_clave("abcd efgh ijkl mnop"), "abcdefghijklmnop")

    def test_archivos_ausentes_prohibidos_y_pesados(self):
        bueno = archivo()
        peligroso = archivo("virus.exe")
        grande = archivo("grande.pdf", b"x" * 100)
        with mock.patch.object(C, "MAXIMO_BYTES", 50):
            buenos, problemas = C.revisar_archivos([bueno, peligroso, "no_existe.pdf", grande])
        self.assertEqual(buenos, [bueno])
        self.assertEqual(len(problemas), 3)
        self.assertTrue(any("no existe" in p for p in problemas))
        self.assertTrue(any(".exe" in p for p in problemas))
        self.assertTrue(any("pasa de" in p for p in problemas))

    def test_mensaje_con_adjuntos(self):
        ruta = archivo("guía 1.pdf")
        msg = C.construir_mensaje("yo@gmail.com", C.DESTINO_PIE, "Guía", "Hola", [ruta])
        self.assertEqual((msg["To"], msg["From"], msg["Subject"]), (C.DESTINO_PIE, "yo@gmail.com", "Guía"))
        adjuntos = list(msg.iter_attachments())
        self.assertEqual([a.get_filename() for a in adjuntos], ["guía 1.pdf"])
        self.assertEqual(adjuntos[0].get_content_type(), "application/pdf")

    def test_mensaje_de_partida(self):
        asunto, cuerpo = C.mensaje_por_defecto(["Circuitos 5BA.pdf"], "Ana Pérez")
        self.assertEqual(asunto, "Guía NEEP Circuitos 5BA")
        self.assertIn("- Circuitos 5BA.pdf", cuerpo)
        self.assertNotIn("Adjunto", cuerpo)                    # esa frase ya no va
        self.assertNotIn("revisión", cuerpo)
        self.assertTrue(cuerpo.startswith("Estimado equipo PIE:"))
        self.assertTrue(cuerpo.endswith("Ana Pérez"))

    def test_el_destino_por_defecto_es_el_del_pie(self):
        self.assertEqual(C.destinatario_de({}), "impresionespiemtc@gmail.com")
        self.assertEqual(C.destinatario_de({"correo": {"pie": "otro@x.cl"}}), "otro@x.cl")

    def test_enviar_inicia_sesion_y_manda(self):
        servidor = Servidor()
        msg = C.construir_mensaje("yo@gmail.com", C.DESTINO_PIE, "A", "B", [])
        C.enviar(msg, "yo@gmail.com", "clave", conectar=lambda: servidor)
        self.assertEqual(servidor.credenciales, ("yo@gmail.com", "clave"))
        self.assertEqual(len(servidor.enviados), 1)

    def test_errores_comprensibles(self):
        self.assertIn("contraseña de APLICACIÓN", C.explicar_error(smtplib.SMTPAuthenticationError(535, b"x")))
        self.assertIn("sin internet", C.explicar_error(OSError("red")))


ENVIAR_DE_VERDAD = C.enviar


class Corrida(unittest.TestCase):
    def setUp(self):
        w.ITEMS.clear()
        self.perfil = {"rut": "1", "iduser": "7", "nombre": "Ana", "curso_ids": {},
                       "correo": {"remitente": "ana@gmail.com"}}
        self.servidor = Servidor()

    def correr(self, datos, *extra, clave="clave-app-1234"):
        ruta = os.path.join(tempfile.mkdtemp(), "c.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f)
        patches = [mock.patch.dict(w.PERFILES, {"ana": self.perfil}),
                   mock.patch.object(C, "clave_guardada", return_value=clave),
                   mock.patch.object(C, "enviar", side_effect=lambda m, r, c, conectar=None:
                                     ENVIAR_DE_VERDAD(m, r, c, conectar=lambda: self.servidor)),
                   mock.patch.object(sys, "argv", ["correo", "--perfil", "ana", "--datos", ruta, *extra])]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        w.PERFIL_POR_DEFECTO = "ana"
        C.main()
        return {os.path.basename(i["clave"]): i["estado"] for i in w.ITEMS}

    def test_simular_no_envia(self):
        g = archivo()
        estados = self.correr({"archivos": [g], "asunto": "Guía", "mensaje": "x"}, "--simular")
        self.assertEqual(estados, {"guia.pdf": "propuesto"})
        self.assertEqual(self.servidor.enviados, [])

    def test_envia_un_correo_con_los_archivos_marcados(self):
        a, b = archivo("a.pdf"), archivo("b.pdf")
        sel = os.path.join(tempfile.mkdtemp(), "s.json")
        with open(sel, "w") as f:
            json.dump({"claves": [a]}, f)
        estados = self.correr({"archivos": [a, b], "asunto": "Guía", "mensaje": "x"}, "--seleccion", sel)
        self.assertEqual(estados, {"a.pdf": "hecho", "b.pdf": "omitido"})
        msg = self.servidor.enviados[0]
        self.assertEqual(msg["To"], C.DESTINO_PIE)
        self.assertEqual([x.get_filename() for x in msg.iter_attachments()], ["a.pdf"])

    def test_si_gmail_falla_queda_en_error_con_motivo(self):
        self.servidor = Servidor(falla=smtplib.SMTPAuthenticationError(535, b"mal"))
        estados = self.correr({"archivos": [archivo()], "asunto": "Guía", "mensaje": "x"})
        self.assertEqual(estados, {"guia.pdf": "error"})
        self.assertIn("APLICACIÓN", w.ITEMS[0]["motivo"])

    def test_sin_clave_guardada_explica_que_falta_configurar(self):
        with self.assertRaises(ValueError) as e:
            self.correr({"archivos": [archivo()], "asunto": "Guía"}, clave="")
        self.assertIn("Falta configurar el correo", str(e.exception))

    def test_sin_asunto_no_envia(self):
        with self.assertRaises(ValueError):
            self.correr({"archivos": [archivo()], "asunto": "  "})
        self.assertEqual(self.servidor.enviados, [])

    def test_archivo_prohibido_no_se_envia_pero_el_resto_si(self):
        estados = self.correr({"archivos": [archivo("a.pdf"), archivo("x.exe")], "asunto": "Guía"})
        self.assertEqual(sorted(estados.values()), ["hecho", "pendiente"])
        self.assertEqual(len(list(self.servidor.enviados[0].iter_attachments())), 1)


if __name__ == "__main__":
    unittest.main()
