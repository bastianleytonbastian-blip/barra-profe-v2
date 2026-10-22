"""Mini app «Administrador del colegio»: solo en el PC del administrador, publica avisos, mensajes y claves de IA.

Todo simulado: nada toca GitHub, el llavero de Windows ni el portapapeles.
"""

import datetime
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HERRAMIENTA = os.path.join(RAIZ, "herramienta")
APP = os.path.join(RAIZ, "administrador", "administrador_colegio.pyw")
sys.path.insert(0, HERRAMIENTA)

import colegio  # noqa: E402

CODIGO = "ABCDEFGHJKLMNPQRSTUV"


def cargar() -> dict:
    espacio = {"__file__": APP, "__name__": "administrador_prueba"}
    with open(APP, encoding="utf-8") as f:
        exec(compile(f.read(), APP, "exec"), espacio)
    return espacio


def setUpModule():
    if not os.path.isfile(APP):          # la mini app vive solo en el PC del administrador (no está en el repositorio)
        raise unittest.SkipTest("la mini app del administrador no está en este PC")


class NoViajaConLaBarra(unittest.TestCase):
    def test_vive_fuera_de_herramienta_y_no_entra_en_el_paquete(self):
        self.assertNotEqual(os.path.commonpath([APP, HERRAMIENTA]), HERRAMIENTA)
        import publicar
        with tempfile.TemporaryDirectory() as tmp:
            ruta, _ = publicar.armar_zip("0.0.0", salida=tmp)
            import zipfile
            with zipfile.ZipFile(ruta) as z:
                self.assertFalse([n for n in z.namelist() if "administrador" in n.lower()])


class MiniApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.mod = cargar()
        except Exception as exc:        # noqa: BLE001  (sin pantalla: no se puede probar)
            raise unittest.SkipTest(f"no se pudo cargar la mini app: {exc}")

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.mod["BUZON"] = os.path.join(self.tmp, "colegio.json")
        self.codigo, self.escrito, self.publicados, self.puede = "", "", [], True

        def sin_red(*_a, **_k):
            raise OSError("sin red en las pruebas")

        def guardar_codigo(texto):
            self.codigo, self.escrito = colegio.normalizar_codigo(texto), colegio.formatear_codigo(texto)
            return self.codigo

        def sin_ventanas(*_a, **_k):
            raise AssertionError("una prueba abrió una ventana de confirmación de verdad")
        # Nada toca el llavero de Windows (ni para leer), GitHub ni ventanas de confirmación de verdad.
        for nombre, falso in (("descargar", sin_red), ("es_administrador", lambda *a, **k: self.puede),
                              ("codigo_guardado", lambda vigencia=30: self.codigo),
                              ("codigo_escrito", lambda vigencia=30: self.escrito),
                              ("_leer_llavero", lambda vigencia=30: self.escrito),
                              ("guardar_codigo", guardar_codigo),
                              ("publicar", lambda paquete, carpeta, **k: self.publicados.append(paquete))):
            parche = mock.patch.object(colegio, nombre, falso)
            parche.start()
            self.addCleanup(parche.stop)
        # Las claves de IA del planificador de quien corre las pruebas jamás se leen: se simulan.
        self.mias = {}
        parche = mock.patch.dict(self.mod, {"messagebox": mock.Mock(askyesno=sin_ventanas),
                                            "mis_claves": lambda: dict(self.mias)})
        parche.start()
        self.addCleanup(parche.stop)

    def responder(self, si: bool):
        """Lo que se contesta en las ventanas de confirmación durante el bloque."""
        return mock.patch.dict(self.mod, {"messagebox": mock.Mock(askyesno=lambda *a, **k: si)})

    def abrir(self):
        app = self.mod["Administrador"]()
        self.copiado = []
        app.clipboard_clear = lambda: None                      # el portapapeles de verdad no se toca
        app.clipboard_append = self.copiado.append

        def cerrar():
            try:
                app.destroy()
            except Exception:  # noqa: BLE001  (ya estaba cerrada)
                pass
            import gc
            gc.collect()        # las variables de Tk se liberan aquí y no en un hilo de fondo (eso bota Tk)
        self.addCleanup(cerrar)
        self.esperar(app, lambda: "Revisando" not in app.estado_gh.cget("text"))
        return app

    def esperar(self, app, condicion, segundos: float = 10) -> None:
        fin = time.time() + segundos
        while time.time() < fin:
            app.update()
            if condicion():
                return
            time.sleep(0.02)
        self.fail("no pasó a tiempo")

    @staticmethod
    def textos(ventana) -> str:
        partes = []

        def recorrer(w):
            try:
                partes.append(str(w.cget("text")))
            except Exception:  # noqa: BLE001
                pass
            for hijo in w.winfo_children():
                recorrer(hijo)
        recorrer(ventana)
        return "\n".join(partes)

    def _buzon(self, mensajes=()):
        colegio.guardar_paquete(self.mod["BUZON"], colegio.cerrar(CODIGO, {"mensajes": list(mensajes)}))

    def test_sin_clave_parte_por_crearla_y_la_copia(self):
        app = self.abrir()
        self.assertEqual(app.actual, "Clave del colegio")
        app.elegir("Mensajes")
        self.assertIn("Primero crea (o pega) la clave del colegio", self.textos(app))
        app.elegir("Clave del colegio")
        app._crear()
        self.assertTrue(colegio.es_generada(self.codigo))
        self.assertEqual(self.copiado, [self.escrito])
        self.assertIn(self.escrito, self.textos(app))

    def test_crear_otra_con_algo_publicado_pregunta_antes(self):
        self.codigo = colegio.normalizar_codigo(CODIGO)
        self._buzon()
        app = self.abrir()
        with self.responder(False):
            app._crear()
        self.assertEqual(self.codigo, colegio.normalizar_codigo(CODIGO), "sin confirmar no se cambia")

    def test_una_clave_que_ya_abre_lo_publicado_se_usa_sin_preguntar(self):
        self._buzon()
        app = self.abrir()
        app.nueva_clave.set("abcd efgh jklm npqr stuv")            # la misma, escrita de otra forma
        app._usar_otra()
        self.assertEqual(self.codigo, colegio.normalizar_codigo(CODIGO))
        self.assertEqual(self.publicados, [], "no hace falta publicar de nuevo")

    def test_frase_propia_debil_no_sirve(self):
        app = self.abrir()
        for debil, motivo in (("tiza lunes", "al menos 4 palabras"), ("sol mar luz paz", "más largas"),
                              ("tiza tiza lunes lunes", "No repitas")):
            app.nueva_clave.set(debil)
            app._usar_otra()
            self.assertIn(motivo, app.aviso.cget("text"), debil)
        self.assertEqual(self.codigo, "")

    def test_frase_propia_nueva_publica_todo_de_nuevo_con_ella(self):
        self.codigo = colegio.normalizar_codigo(CODIGO)
        self._buzon([colegio.nuevo_mensaje("mensaje", "Para Ana", "Ana Pérez")])
        app = self.abrir()
        app.nueva_clave.set("Tiza lunes guitarra volcán")
        with self.responder(False):
            app._usar_otra()
        self.assertEqual(self.codigo, colegio.normalizar_codigo(CODIGO), "sin confirmar queda la de antes")
        with self.responder(True):
            app._usar_otra()
        self.esperar(app, lambda: self.publicados)
        self.esperar(app, lambda: "publicado de nuevo" in app.aviso.cget("text"))
        self.assertEqual(self.escrito, "Tiza lunes guitarra volcán", "se muestra tal como se escribió")
        self.assertIn("Tiza lunes guitarra volcán", self.textos(app))
        self.assertIsNone(colegio.abrir(self.publicados[-1], CODIGO), "la clave de antes ya no abre")
        abierto = colegio.abrir(self.publicados[-1], "tiza LUNES guitarra volcan")
        self.assertEqual([m["texto"] for m in abierto["mensajes"]], ["Para Ana"], "lo que había no se pierde")

    def test_si_este_pc_no_puede_publicar_lo_dice(self):
        self.puede = False
        app = self.abrir()
        self.assertIn("no puede publicar", app.estado_gh.cget("text"))

    def test_publica_mensajes_avisos_y_claves(self):
        self.codigo = colegio.normalizar_codigo(CODIGO)
        app = self.abrir()
        app.campo_texto.insert("1.0", "Consejo de profesores a las 15:00")
        app._publicar_mensaje()
        self.esperar(app, lambda: "publicado para todos" in app.aviso.cget("text"))
        self.assertIn("Consejo de profesores a las 15:00", json.dumps(self.publicados[-1], ensure_ascii=False),
                      "lo general va a la vista")
        self.assertEqual(colegio.leer_paquete(self.mod["BUZON"]), self.publicados[-1], "la barra de este PC lo ve al tiro")

        app.para.set("Ana Pérez")
        app.campo_texto.insert("1.0", "Tus guías PIE están en el casillero")
        app._publicar_mensaje()
        self.esperar(app, lambda: "publicado para Ana Pérez" in app.aviso.cget("text"))
        self.assertNotIn("Tus guías PIE", json.dumps(self.publicados[-1], ensure_ascii=False), "lo dirigido va cifrado")
        self.assertEqual(self.publicados[-1]["sal"], self.publicados[0]["sal"],
                         "con la misma clave se mantiene la sal: cada barra calcula la llave una sola vez")
        contenido = colegio.abrir(self.publicados[-1], CODIGO)
        self.assertEqual([(m["para"], m["texto"]) for m in contenido["mensajes"]],
                         [("*", "Consejo de profesores a las 15:00"), ("Ana Pérez", "Tus guías PIE están en el casillero")])
        self.assertIn("PUBLICADOS · 2", self.textos(app))

        app._elegir_tipo("aviso")
        app.fecha.set((datetime.date.today() - datetime.timedelta(days=1)).strftime("%d/%m/%Y"))
        app.campo_texto.insert("1.0", "Atrasado")
        app._publicar_mensaje()
        self.assertIn("ya pasó", app.aviso.cget("text"))

        with self.responder(True):
            app._quitar_mensaje(contenido["mensajes"][0]["id"])
        self.esperar(app, lambda: "se quitó" in app.aviso.cget("text"))
        self.assertEqual([m["texto"] for m in colegio.abrir(self.publicados[-1], CODIGO)["mensajes"]],
                         ["Tus guías PIE están en el casillero"])

        app.elegir("Claves de IA")
        app.campos_claves["GROQ_API_KEY"].insert(0, "gsk-clave-del-colegio-4321")
        app._publicar_claves()
        self.esperar(app, lambda: "claves de IA del colegio quedaron publicadas" in app.aviso.cget("text"))
        self.assertEqual(colegio.abrir(self.publicados[-1], CODIGO)["claves"], {"GROQ_API_KEY": "gsk-clave-del-colegio-4321"})
        self.assertNotIn("gsk-clave-del-colegio", json.dumps(self.publicados[-1]))
        self.assertIn("publicada …4321", self.textos(app))

    def test_sin_claves_publicadas_lo_dice_y_ofrece_las_de_mi_planificador(self):
        self.codigo = colegio.normalizar_codigo(CODIGO)
        app = self.abrir()
        app.elegir("Claves de IA")
        self.assertIn("Todavía no hay claves de IA publicadas", self.textos(app))
        self.assertNotIn("Usar las claves de mi planificador", self.textos(app), "sin claves propias no se ofrece")
        self.mias = {"GEMINI_API_KEY": "AIza-mia-1111", "OTRA_COSA": "no se copia"}
        app.elegir("Claves de IA")
        self.assertIn("Usar las claves de mi planificador", self.textos(app))
        app._usar_mis_claves()
        self.assertEqual(app.campos_claves["GEMINI_API_KEY"].get(), "AIza-mia-1111")
        self.assertEqual(app.campos_claves["GROQ_API_KEY"].get(), "")
        self.assertIn("Se copiaron 1 clave", app.aviso.cget("text"))
        self.assertEqual(self.publicados, [], "copiar no publica: falta «Guardar y publicar»")
        app._publicar_claves()
        self.esperar(app, lambda: "quedaron publicadas" in app.aviso.cget("text"))
        self.assertEqual(colegio.abrir(self.publicados[-1], CODIGO)["claves"], {"GEMINI_API_KEY": "AIza-mia-1111"})
        self.assertNotIn("Todavía no hay claves de IA publicadas", self.textos(app))

    def test_mis_claves_lee_solo_las_de_la_cuenta_activa(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "perfiles"))
            for cuenta in ("ana", "beto"):
                open(os.path.join(tmp, "perfiles", f"{cuenta}.json"), "w").close()
            carpeta = os.path.join(tmp, "planificador", "ana")
            os.makedirs(carpeta)
            with open(os.path.join(carpeta, "claves.json"), "w", encoding="utf-8") as f:
                json.dump({"GEMINI_API_KEY": " k1 ", "GROQ_API_KEY": "", "OTRA": "x"}, f)
            leer = cargar()["mis_claves"]                         # la de verdad, con rutas simuladas
            rutas = self.mod["rutas"]
            for activa, esperado in (("ana", {"GEMINI_API_KEY": "k1"}), ("beto", {}),
                                     ("", {"GEMINI_API_KEY": "k1"})):  # sin perfil_activo.txt: la primera, como la barra
                with self.subTest(activa=activa), mock.patch.object(rutas, "PERSONAL", tmp), \
                        mock.patch.object(rutas, "PERFILES", os.path.join(tmp, "perfiles")), \
                        mock.patch.object(rutas, "perfil_activo", lambda *a, c=activa: c):
                    self.assertEqual(leer(), esperado)

    def test_si_github_falla_lo_dice_y_no_cambia_lo_guardado(self):
        self.codigo = colegio.normalizar_codigo(CODIGO)

        def falla(*_a, **_k):
            raise RuntimeError("No pude subir el buzón a GitHub: HTTP 403")
        app = self.abrir()
        with mock.patch.object(colegio, "publicar", falla):
            app.campo_texto.insert("1.0", "Hola")
            app._publicar_mensaje()
            self.esperar(app, lambda: "403" in app.aviso.cget("text"))
        self.assertIsNone(colegio.leer_paquete(self.mod["BUZON"]))


if __name__ == "__main__":
    unittest.main()
