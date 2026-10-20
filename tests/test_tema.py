"""Colores y letra (tema.py): cada paleta debe leerse bien y tener todos sus colores con nombre."""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import tema  # noqa: E402

CAMPOS = {"nombre", "fondo", "boton", "hover", "pulsado", "acento", "texto", "tenue", "suave", "lengueta", "alerta",
          "ok", "aviso", "error", "consola", "consola_texto", "sobre_acento", "sobre_lengueta", "web"}
# (texto, fondo): texto chico de la barra, que debe tener contraste de al menos 4,5 : 1.
TEXTO_CHICO = [("texto", "fondo"), ("texto", "boton"), ("texto", "hover"), ("tenue", "fondo"), ("tenue", "boton"),
               ("suave", "fondo"), ("suave", "boton"), ("acento", "fondo"), ("acento", "boton"), ("ok", "fondo"),
               ("ok", "boton"), ("aviso", "fondo"), ("aviso", "boton"), ("error", "fondo"), ("error", "boton"),
               ("sobre_acento", "acento"), ("consola_texto", "consola")]


class Paletas(unittest.TestCase):
    def test_cada_paleta_tiene_todos_sus_colores(self):
        for clave, p in tema.PALETAS.items():
            with self.subTest(paleta=clave):
                self.assertEqual(set(p), CAMPOS)
                for campo, valor in p.items():
                    if campo not in ("nombre", "web"):
                        self.assertRegex(valor, r"^#[0-9a-f]{6}$", campo)
                self.assertEqual(set(p["web"]), {"claro", "oscuro"})

    def test_el_texto_chico_se_lee_en_todas_las_paletas(self):
        for clave, p in tema.PALETAS.items():
            for texto, fondo in TEXTO_CHICO:
                with self.subTest(paleta=clave, texto=texto, fondo=fondo):
                    self.assertGreaterEqual(tema.contraste(p[texto], p[fondo]), 4.5)

    def test_la_marca_de_la_lengueta_se_distingue(self):
        for clave, p in tema.PALETAS.items():
            with self.subTest(paleta=clave):
                self.assertGreaterEqual(tema.contraste(p["sobre_lengueta"], p["lengueta"]), 3.0)

    def test_hay_paleta_clara_y_de_alto_contraste(self):
        self.assertIn("claro", tema.PALETAS)
        self.assertGreaterEqual(tema.contraste(tema.PALETAS["contraste"]["texto"],
                                               tema.PALETAS["contraste"]["fondo"]), 15)
        self.assertEqual(tema.paleta("no-existe"), tema.PALETAS[tema.PALETA_INICIAL])

    def test_contraste(self):
        self.assertAlmostEqual(tema.contraste("#000000", "#ffffff"), 21.0, places=1)
        self.assertAlmostEqual(tema.contraste("#777777", "#777777"), 1.0)

    def test_el_color_de_la_barra_se_lee_en_el_planificador(self):
        # web.claro y web.oscuro son el color principal del planificador (enlaces, pestañas, códigos de OA) sobre sus
        # tarjetas: blanca en modo claro (#ffffff) y #1a2129 en modo oscuro (las de estilos.css).
        for clave, p in tema.PALETAS.items():
            with self.subTest(paleta=clave):
                self.assertRegex(p["web"]["claro"], r"^#[0-9a-f]{6}$")
                self.assertRegex(p["web"]["oscuro"], r"^#[0-9a-f]{6}$")
                self.assertGreaterEqual(tema.contraste(p["web"]["claro"], "#ffffff"), 4.5)
                self.assertGreaterEqual(tema.contraste(p["web"]["oscuro"], "#1a2129"), 4.5)


class Letra(unittest.TestCase):
    def test_nada_bajo_9_puntos(self):
        self.assertEqual(tema.tamano_letra(8), 9)
        self.assertEqual(tema.tamano_letra(8, 0.9), 9)
        self.assertEqual(tema.tamano_letra(13, 1.15), 15)
        self.assertEqual(tema.tamano_letra(10), 10)

    def test_la_barra_no_usa_colores_ni_letras_escritos_a_mano(self):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta", "barra_profe.pyw")
        with open(ruta, encoding="utf-8") as f:
            codigo = f.read()
        self.assertEqual(re.findall(r'"#[0-9a-fA-F]{6}"', codigo), [], "los colores salen de tema.py")
        self.assertEqual(re.findall(r'font=\(', codigo), [], "las letras pasan por letra()")


if __name__ == "__main__":
    unittest.main()
