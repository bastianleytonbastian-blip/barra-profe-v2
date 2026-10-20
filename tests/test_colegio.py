"""Buzón del colegio: clave del colegio, cifrado, mensajes y avisos del día, y publicar con GitHub CLI.

Todo simulado: nada toca GitHub ni el llavero de Windows.
"""

import datetime
import io
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace as N
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import colegio as c  # noqa: E402

CODIGO = "ABCDEFGHJKLMNPQRSTUV"
OTRO = "ZZZZZZZZZZZZZZZZZZZZ"
HOY = datetime.date(2026, 10, 20)


class ClaveDelColegio(unittest.TestCase):
    def test_se_genera_en_grupos_y_se_entiende_escrita_de_cualquier_forma(self):
        codigo = c.generar_codigo()
        self.assertRegex(codigo, r"^[A-HJ-NP-Z2-9]{4}(-[A-HJ-NP-Z2-9]{4}){4}$")
        self.assertNotEqual(codigo, c.generar_codigo())
        self.assertTrue(c.es_generada(codigo))
        self.assertEqual(c.normalizar_codigo(codigo.lower().replace("-", " ")), c.normalizar_codigo(codigo))
        self.assertEqual(c.formatear_codigo(CODIGO.lower()), "ABCD-EFGH-JKLM-NPQR-STUV")
        for malo in ("", None, "ABC", "corta-de-15-let"):
            self.assertEqual(c.normalizar_codigo(malo), "", malo)

    def test_una_frase_propia_vale_igual_se_escriba_como_se_escriba(self):
        frase = "Tiza lunes, guitarra VOLCÁN"
        self.assertFalse(c.es_generada(frase))
        self.assertEqual(c.normalizar_codigo(frase), "tizalunesguitarravolcan")
        self.assertEqual(c.normalizar_codigo("tiza-lunes guitarra volcan"), c.normalizar_codigo(frase))
        self.assertEqual(c.formatear_codigo("  Tiza  lunes guitarra   volcán "), "Tiza lunes guitarra volcán")
        paquete = c.cerrar(frase, {"claves": {"GROQ_API_KEY": "g"}})
        self.assertEqual(c.abrir(paquete, "tiza LUNES guitarra volcan")["claves"], {"GROQ_API_KEY": "g"})
        self.assertIsNone(c.abrir(paquete, "tiza lunes guitarra volcanes"))

    def test_una_frase_nueva_debe_ser_dificil_de_adivinar(self):
        self.assertIn("al menos 4 palabras", c.problema_de_frase("tiza lunes"))
        self.assertIn("No repitas", c.problema_de_frase("tiza tiza lunes lunes"))
        self.assertIn("más largas", c.problema_de_frase("sol mar luz paz"))
        self.assertEqual(c.problema_de_frase("tiza lunes guitarra volcán"), "")
        self.assertEqual(c.problema_de_frase(c.generar_codigo()), "", "la generada al azar siempre sirve")

    def test_lo_publicado_con_la_clave_de_la_2_11_0_se_sigue_abriendo(self):
        import base64
        import hashlib
        from cryptography.fernet import Fernet
        sal = b"s" * 16                                 # así cifraba la 2.11.0: la clave en mayúsculas, sin guiones
        llave = base64.urlsafe_b64encode(hashlib.pbkdf2_hmac("sha256", CODIGO.encode(), sal, c.ITERACIONES, 32))
        viejo = {"formato": 1, "sal": base64.b64encode(sal).decode(),
                 "datos": Fernet(llave).encrypt(json.dumps({"claves": {"GEMINI_API_KEY": "k"}}).encode()).decode()}
        self.assertEqual(c.abrir(viejo, "abcd-efgh-jklm-npqr-stuv")["claves"], {"GEMINI_API_KEY": "k"})
        nuevo = c.cerrar("abcd efgh jklm npqr stuv", {"claves": {"GEMINI_API_KEY": "k"}}, sal)
        abierto = json.loads(Fernet(llave).decrypt(nuevo["datos"].encode()))   # una barra 2.11.0 abre lo nuevo
        self.assertEqual(abierto["claves"], {"GEMINI_API_KEY": "k"})

    def test_la_sal_se_puede_mantener(self):
        primero = c.cerrar(CODIGO, {})
        segundo = c.cerrar(CODIGO, {}, c.sal_de(primero))
        self.assertEqual(primero["sal"], segundo["sal"])
        self.assertIsNone(c.sal_de({"formato": 1}))

    def test_queda_en_el_llavero_de_windows_tal_como_se_escribio(self):
        llavero = {}
        with mock.patch("keyring.set_password", lambda s, u, v: llavero.__setitem__((s, u), v)), \
                mock.patch("keyring.get_password", lambda s, u: llavero.get((s, u))):
            with self.assertRaises(ValueError):
                c.guardar_codigo("corta")
            self.assertEqual(llavero, {})
            c.guardar_codigo("abcd-efgh-jklm-npqr-stuv")
            self.assertEqual(llavero, {(c.SERVICIO, c.USUARIO): "ABCD-EFGH-JKLM-NPQR-STUV"})
            self.assertEqual(c.codigo_guardado(vigencia=0), CODIGO.lower())
            c.guardar_codigo("Tiza  lunes guitarra volcán")
            self.assertEqual(c.codigo_escrito(vigencia=0), "Tiza lunes guitarra volcán")
            self.assertEqual(c.codigo_guardado(vigencia=0), "tizalunesguitarravolcan")
            llavero[(c.SERVICIO, c.USUARIO)] = CODIGO                 # como lo dejó guardado la 2.11.0
            self.assertEqual(c.codigo_guardado(vigencia=0), CODIGO.lower())

    def test_sin_llavero_es_como_no_tener_clave(self):
        with mock.patch("keyring.get_password", side_effect=RuntimeError("sin llavero")):
            self.assertEqual(c.codigo_guardado(vigencia=0), "")


class Cifrado(unittest.TestCase):
    CONTENIDO = {"claves": {"GEMINI_API_KEY": "clave-secreta"}, "publicado": "2026-10-20 08:00",
                 "mensajes": [{"id": "a1", "tipo": "mensaje", "para": "Ana Pérez", "texto": "Reunión a las 16:00",
                               "fecha": "", "de": "Bastián", "creado": "2026-10-20 08:00"}]}

    def test_ida_y_vuelta_sin_dejar_legible_lo_dirigido_ni_las_claves(self):
        paquete = c.cerrar(CODIGO, self.CONTENIDO)
        crudo = json.dumps(paquete, ensure_ascii=False)
        for secreto in ("clave-secreta", "Reunión", "Ana Pérez"):
            self.assertNotIn(secreto, crudo)
        self.assertEqual(c.abrir(paquete, CODIGO), self.CONTENIDO)
        self.assertEqual(c.abrir(paquete, c.formatear_codigo(CODIGO).lower()), self.CONTENIDO)

    def test_lo_general_va_a_la_vista_y_lo_dirigido_cifrado(self):
        general = c.nuevo_mensaje("aviso", "Consejo de profesores", fecha=HOY, de="Bastián")
        dirigido = c.nuevo_mensaje("mensaje", "Tus guías PIE", "Ana Pérez, 12.345.678-9")
        paquete = c.cerrar(CODIGO, {"claves": {"GEMINI_API_KEY": "clave-secreta"}, "mensajes": [general, dirigido]})
        crudo = json.dumps(paquete, ensure_ascii=False)
        self.assertIn("Consejo de profesores", crudo, "lo que va para todos se lee sin la clave")
        for secreto in ("Tus guías PIE", "Ana Pérez", "12.345.678-9", "clave-secreta"):
            self.assertNotIn(secreto, crudo)
        self.assertEqual(c.parte_publica(paquete)["mensajes"], [general])
        self.assertEqual(c.abrir(paquete, CODIGO)["mensajes"], [general, dirigido])

    def test_sin_la_clave_se_ve_solo_lo_general(self):
        general = c.nuevo_mensaje("aviso", "Consejo", fecha=HOY)
        dirigido = c.nuevo_mensaje("mensaje", "Para Ana", "Ana Pérez")
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "colegio.json")
            c.guardar_paquete(ruta, c.cerrar(CODIGO, {"claves": {"GROQ_API_KEY": "g"}, "mensajes": [general, dirigido]}))
            for codigo, textos, claves in (("", ["Consejo"], {}), (OTRO, ["Consejo"], {}),
                                           (CODIGO, ["Consejo", "Para Ana"], {"GROQ_API_KEY": "g"})):
                with self.subTest(codigo=codigo):
                    contenido = c.contenido_guardado(ruta, codigo)
                    self.assertEqual([m["texto"] for m in contenido["mensajes"]], textos)
                    self.assertEqual(contenido["claves"], claves)
            vistos = c.para_mostrar(c.contenido_guardado(ruta, ""), "", "Ana Pérez", HOY, set())
            self.assertEqual([m["texto"] for m in vistos], ["Consejo"], "Ana ve lo suyo recién con la clave")

    def test_algo_dirigido_puesto_en_la_parte_publica_se_ignora(self):
        paquete = c.cerrar(CODIGO, {})
        paquete["publico"]["mensajes"].append(c.nuevo_mensaje("mensaje", "Colado", "Ana Pérez"))
        self.assertEqual(c.parte_publica(paquete)["mensajes"], [])
        self.assertEqual(c.abrir(paquete, CODIGO)["mensajes"], [])
        self.assertEqual(c.parte_publica({"formato": 1})["mensajes"], [], "un buzón sin parte pública no falla")

    def test_otra_clave_un_paquete_alterado_o_raro_no_abren(self):
        paquete = c.cerrar(CODIGO, self.CONTENIDO)
        self.assertIsNone(c.abrir(paquete, OTRO))
        self.assertIsNone(c.abrir(paquete, ""))
        alterado = dict(paquete, datos=paquete["datos"][:-6] + "AAAAAA")
        self.assertIsNone(c.abrir(alterado, CODIGO))
        for raro in (None, [], {"formato": 2, "sal": paquete["sal"], "datos": paquete["datos"]}, {"formato": 1}):
            self.assertIsNone(c.abrir(raro, CODIGO))
        with self.assertRaises(ValueError):
            c.cerrar("mala", self.CONTENIDO)

    def test_lo_que_no_calza_se_descarta(self):
        limpio = c.limpiar({"claves": {"A": " x ", "B": 3, "C": ""},
                            "mensajes": [{"tipo": "otro", "id": "1", "texto": "x"},
                                         {"id": "2", "tipo": "aviso", "texto": "sin fecha"},
                                         {"id": "3", "tipo": "mensaje", "texto": "  "},
                                         {"id": "4", "tipo": "aviso", "texto": "ok", "fecha": "2026-10-21"}],
                            "publicado": None})
        self.assertEqual(limpio["claves"], {"A": "x"})
        self.assertEqual([m["id"] for m in limpio["mensajes"]], ["4"])
        self.assertEqual(c.limpiar("roto"), c.contenido_vacio())

    def test_lo_guardado_en_el_pc_y_su_estado(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "colegio.json")
            self.assertEqual(c.estado(ruta, CODIGO), "sin_buzon")
            c.guardar_paquete(ruta, c.cerrar(CODIGO, {"claves": {"GROQ_API_KEY": "g"}}))
            self.assertEqual(c.estado(ruta, ""), "sin_codigo")
            self.assertEqual(c.estado(ruta, OTRO), "codigo_incorrecto")
            self.assertEqual(c.estado(ruta, CODIGO), "ok")
            with mock.patch.object(c, "codigo_guardado", return_value=CODIGO):
                self.assertEqual(c.claves_ia(ruta), {"GROQ_API_KEY": "g"})
            with mock.patch.object(c, "codigo_guardado", return_value=""):
                self.assertEqual(c.claves_ia(ruta), {})


class Descargar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)
        self.ruta = os.path.join(self.tmp, "datos", "colegio.json")
        self.pedidos = []

    def abrir_con(self, cuerpo: bytes):
        def abrir(pedido, timeout):
            self.pedidos.append(pedido.full_url)
            return io.BytesIO(cuerpo)
        return abrir

    def test_trae_el_buzon_y_avisa_solo_si_cambio(self):
        paquete = c.cerrar(CODIGO, {"claves": {}})
        abrir = self.abrir_con(json.dumps(paquete).encode())
        self.assertTrue(c.descargar(self.ruta, abrir_url=abrir))
        self.assertFalse(c.descargar(self.ruta, abrir_url=abrir))
        self.assertEqual(c.leer_paquete(self.ruta), paquete)
        self.assertEqual(self.pedidos[0], f"https://github.com/{c.REPO}/releases/download/buzon/colegio.json")

    def test_algo_que_no_es_el_buzon_no_se_guarda(self):
        for cuerpo in (b'{"hola": 1}', b"no es json", b"x" * (c.MAX_ARCHIVO + 10)):
            with self.subTest(cuerpo=cuerpo[:12]), self.assertRaises(ValueError):
                c.descargar(self.ruta, abrir_url=self.abrir_con(cuerpo))
        self.assertFalse(os.path.exists(self.ruta))


class Mensajes(unittest.TestCase):
    def test_nuevo_mensaje_pide_lo_necesario(self):
        m = c.nuevo_mensaje("mensaje", "  Hola  ", "", de="Bastián", ahora=datetime.datetime(2026, 10, 20, 8, 5))
        self.assertEqual((m["texto"], m["para"], m["de"], m["creado"], m["fecha"]),
                         ("Hola", "*", "Bastián", "2026-10-20 08:05", ""))
        self.assertEqual(c.nuevo_mensaje("aviso", "Consejo", fecha=HOY)["fecha"], "2026-10-20")
        for tipo, texto, fecha in (("otro", "x", None), ("mensaje", " ", None), ("aviso", "x", None),
                                   ("mensaje", "x" * (c.MAX_TEXTO + 1), None)):
            with self.subTest(tipo=tipo, texto=texto[:5]), self.assertRaises(ValueError):
                c.nuevo_mensaje(tipo, texto, fecha=fecha)

    def test_para_quien_va(self):
        def para(destino):
            return c.es_para({"para": destino}, "12345678-9", "Ana María Pérez Soto")
        self.assertTrue(para("*"))
        self.assertTrue(para("12.345.678-9"))
        self.assertTrue(para("ana perez"))                       # sin tildes ni mayúsculas, todas sus palabras
        self.assertTrue(para("Beto Soto, 12345678-9"))           # varios destinatarios
        self.assertFalse(para("Beto Soto"))
        self.assertFalse(para("11.111.111-1"))
        self.assertFalse(c.es_para({"para": "12345678-9"}, "", "Ana"), "sin RUT en el perfil no calza por RUT")

    def test_lo_que_ve_cada_profe_hoy(self):
        mensajes = [c.nuevo_mensaje("mensaje", "Para todos", ahora=datetime.datetime(2026, 10, 19, 9)),
                    c.nuevo_mensaje("aviso", "Consejo hoy", fecha=HOY, ahora=datetime.datetime(2026, 10, 19, 10)),
                    c.nuevo_mensaje("aviso", "Mañana", fecha=HOY + datetime.timedelta(days=1)),
                    c.nuevo_mensaje("mensaje", "Solo para Beto", "Beto Soto"),
                    c.nuevo_mensaje("mensaje", "Ya leído")]
        contenido = {"mensajes": mensajes}
        vistos = c.para_mostrar(contenido, "12345678-9", "Ana Pérez", HOY, {mensajes[4]["id"]})
        self.assertEqual([m["texto"] for m in vistos], ["Consejo hoy", "Para todos"])     # el más nuevo arriba
        self.assertEqual(c.para_mostrar(None, "", "", HOY, set()), [])

    def test_al_publicar_se_van_los_avisos_viejos(self):
        mensajes = [c.nuevo_mensaje("aviso", "Ayer", fecha=HOY - datetime.timedelta(days=1)),
                    c.nuevo_mensaje("aviso", "Hoy", fecha=HOY), c.nuevo_mensaje("mensaje", "Sigue")]
        self.assertEqual([m["texto"] for m in c.vigentes(mensajes, HOY)], ["Hoy", "Sigue"])

    def test_leidos_por_profe(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "avisos_leidos_ana.json")
            self.assertEqual(c.leer_leidos(ruta), set())
            c.marcar_leido(ruta, "a")
            c.marcar_leido(ruta, "b")
            c.marcar_leido(ruta, "a")
            self.assertEqual(c.leer_leidos(ruta), {"a", "b"})
            for n in range(400):
                c.marcar_leido(ruta, f"x{n}")
            leidos = c.leer_leidos(ruta)
            self.assertEqual(len(leidos), 300)
            self.assertIn("x399", leidos)
            self.assertNotIn("a", leidos, "los más viejos se olvidan primero")


class Administrador(unittest.TestCase):
    def test_es_administrador_si_gh_tiene_permiso_de_escritura(self):
        def correr_con(salida, codigo=0):
            return lambda orden, **k: N(returncode=codigo, stdout=salida, stderr="")
        self.assertTrue(c.es_administrador(correr=correr_con("true\n")))
        self.assertFalse(c.es_administrador(correr=correr_con("false\n")))
        self.assertFalse(c.es_administrador(correr=correr_con("", 1)))

        def sin_gh(orden, **k):
            raise FileNotFoundError("gh")
        self.assertFalse(c.es_administrador(correr=sin_gh))

    def _publicar(self, existe: bool, sube: bool = True):
        ordenes = []

        def correr(orden, **k):
            ordenes.append(orden)
            if orden[:3] == ["gh", "release", "view"]:
                return N(returncode=0 if existe else 1, stdout="", stderr="release not found")
            if orden[:3] == ["gh", "release", "upload"]:
                with open(orden[4], encoding="utf-8") as f:
                    self.subido = json.load(f)
                return N(returncode=0 if sube else 1, stdout="", stderr="HTTP 403: sin permiso")
            return N(returncode=0, stdout="", stderr="")
        paquete = c.cerrar(CODIGO, {"claves": {}})
        with tempfile.TemporaryDirectory() as tmp:
            c.publicar(paquete, tmp, correr=correr)
        self.assertEqual(self.subido, paquete)
        return ordenes

    def test_la_primera_vez_crea_el_buzon_como_version_preliminar(self):
        ordenes = self._publicar(existe=False)
        self.assertEqual([o[2] for o in ordenes], ["view", "create", "upload"])
        self.assertIn("--prerelease", ordenes[1])           # nunca pasa a ser la «última versión» de la barra
        self.assertIn("--clobber", ordenes[2])

    def test_si_ya_existe_solo_sube(self):
        self.assertEqual([o[2] for o in self._publicar(existe=True)], ["view", "upload"])

    def test_si_github_no_deja_subir_lo_dice(self):
        with self.assertRaises(RuntimeError) as caso:
            self._publicar(existe=True, sube=False)
        self.assertIn("403", str(caso.exception))


if __name__ == "__main__":
    unittest.main()
