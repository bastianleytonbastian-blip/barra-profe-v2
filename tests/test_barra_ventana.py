"""Prueba de humo de la ventana de la barra: abre la barra de verdad.

Comprueba lo que ya falló una vez: que la ✕ cierre y que la rueda y la barrita
desplacen el contenido cuando no cabe en pantalla. Abre una ventana real unos
instantes (en otro puerto, para no chocar con una barra que esté abierta).
"""

import json
import os
import sys
import tkinter as tk
import unittest
from unittest import mock

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta")
ARCHIVO = os.path.abspath(os.path.join(RAIZ, "barra_profe.pyw"))


def cargar_modulo() -> dict:
    fuente = open(ARCHIVO, encoding="utf-8").read().replace("PUERTO = 50573", "PUERTO = 50998")
    fuente = fuente.replace('if __name__ == "__main__":\n    main()', "")
    espacio = {"__file__": ARCHIVO, "__name__": "barra_prueba"}
    argv, sys.argv = sys.argv, [ARCHIVO]
    try:
        exec(compile(fuente, ARCHIVO, "exec"), espacio)
    finally:
        sys.argv = argv
    return espacio


class VentanaBarra(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.mod = cargar_modulo()
        except Exception as exc:        # noqa: BLE001  (sin pantalla: no se puede probar)
            raise unittest.SkipTest(f"no se pudo abrir una ventana: {exc}")

    def setUp(self):
        import tempfile
        # Nada de estas pruebas debe tocar Webclass: la revisión del libro y las
        # simulaciones corren un script de juguete.
        self.mod["comando_webclass"] = lambda *a, **k: [sys.executable, "-c", "pass"]
        self.mod["clave_de_mensajeria"] = lambda: ""        # la red de mensajes no se abre en las pruebas
        carpeta = tempfile.mkdtemp()
        self.carpeta = carpeta
        self.mod["TOUR"] = os.path.join(carpeta, "tour.json")
        patrulla = mock.patch.object(self.mod["rutas"], "PERSONAL", carpeta)   # lo que se elige al subir no toca tu carpeta real
        patrulla.start()
        self.addCleanup(patrulla.stop)
        self.mod["EJECUCIONES"] = os.path.join(carpeta, "ultimas.json")
        with open(self.mod["CONFIG"], encoding="utf-8") as f:
            herramientas = json.load(f)
        self.barra = self.mod["Barra"](herramientas)
        self.barra.fijada = True        # que no se pliegue sola a mitad de una prueba lenta
        self.barra._desplegar()
        self.barra.update()

    def tearDown(self):
        try:
            self.barra.destroy()
        except Exception:               # noqa: BLE001  (ya estaba cerrada)
            pass
        import gc
        gc.collect()                    # que los objetos de Tk se liberen aquí y no en otro hilo

    def _abrir_subir_con(self, archivos):
        import tempfile
        buzon = tempfile.mkdtemp()
        os.makedirs(os.path.join(buzon, "5 basico"))
        for nombre in archivos:
            open(os.path.join(buzon, "5 basico", nombre), "w").close()
        self.mod["BUZON"] = buzon
        self.mod["comando_webclass"] = lambda *a, **k: [sys.executable, "-c", "pass"]
        self.mod["abrir"]({"nombre": "Subir recursos", "tipo": "webclass", "destino": "subir",
                           "vista_previa": "subir"}, self.barra)
        self.barra.update()
        return [w for w in self.barra.winfo_children() if isinstance(w, self.mod["VistaPrevia"])][0]

    def _cerrar_consolas(self):
        for w in self.barra.winfo_children():
            if isinstance(w, self.mod["Consola"]):
                w.destroy()

    def test_subir_pregunta_la_asignatura_y_recuerda_no_volver_a_preguntar(self):
        import barra_utiles as u
        ruta = u.ruta_preferencia_subida(self.carpeta, self.mod["PERFIL"])
        previa = self._abrir_subir_con(["a.pdf"])
        self.assertIsNotNone(previa.selector_asignatura.combo, "debe ofrecer elegir la asignatura")
        self.assertIn("Historia, Geografía y Cs. Sociales", previa.selector_asignatura.combo.cget("values"))
        previa.selector_asignatura.combo.set("Historia, Geografía y Cs. Sociales")
        previa.selector_asignatura.var_no_preguntar.set(True)
        previa._continuar()
        self.assertEqual(u.leer_preferencia_subida(ruta), {"asignatura": "historia", "preguntar": False})
        self._cerrar_consolas()
        segunda = self._abrir_subir_con(["b.pdf"])                  # ya no pregunta: solo avisa cuál usa
        self.assertIsNone(segunda.selector_asignatura.combo)
        self.assertIn("Se suben como: Historia", self._textos(segunda))
        segunda._continuar()
        self.assertEqual(u.leer_preferencia_subida(ruta)["asignatura"], "historia")
        self._cerrar_consolas()

    def test_subir_sin_marcar_no_volver_a_preguntar_sigue_preguntando(self):
        import barra_utiles as u
        ruta = u.ruta_preferencia_subida(self.carpeta, self.mod["PERFIL"])
        previa = self._abrir_subir_con(["a.pdf"])
        previa.selector_asignatura.combo.set("Matemática")
        previa._continuar()
        self.assertEqual(u.leer_preferencia_subida(ruta), {"asignatura": "matematica", "preguntar": True})
        self._cerrar_consolas()
        otra = self._abrir_subir_con(["b.pdf"])
        self.assertEqual(otra.selector_asignatura.combo.get(), "Matemática", "recuerda la última elegida")
        otra.destroy()

    def test_cambiar_la_asignatura_guardada_vuelve_a_preguntar(self):
        import barra_utiles as u
        ruta = u.ruta_preferencia_subida(self.carpeta, self.mod["PERFIL"])
        u.guardar_preferencia_subida(ruta, "historia", preguntar=False)
        previa = self._abrir_subir_con(["a.pdf"])
        previa.selector_asignatura.mostrar_selector()
        previa.selector_asignatura.combo.set("Orientación")
        previa._continuar()
        self.assertEqual(u.leer_preferencia_subida(ruta), {"asignatura": "orientacion", "preguntar": True})
        self._cerrar_consolas()

    def test_arrastrar_muestra_la_asignatura_y_la_guarda(self):
        import barra_utiles as u
        ruta = u.ruta_preferencia_subida(self.carpeta, self.mod["PERFIL"])
        buzon = os.path.join(self.carpeta, "buzon")
        os.makedirs(os.path.join(buzon, "5 basico"))
        self.mod["BUZON"] = buzon
        origen = os.path.join(self.carpeta, "guia.pdf")
        with open(origen, "wb") as f:
            f.write(b"%PDF contenido")
        soltar = self.mod["VentanaSoltar"](self.barra, [origen])
        self.barra.update()
        sel = soltar.selector_asignatura
        self.assertIsNotNone(sel.combo, "la primera vez muestra dónde se subirá y deja elegir")
        sel.combo.set("Orientación")
        sel.var_no_preguntar.set(True)
        soltar._copiar("5 basico")
        self.assertEqual(u.leer_preferencia_subida(ruta), {"asignatura": "orientacion", "preguntar": False})
        self.assertIn("Orientación", soltar.aviso.cget("text"))
        soltar.destroy()
        otra = self.mod["VentanaSoltar"](self.barra, [origen])
        self.barra.update()
        self.assertIsNone(otra.selector_asignatura.combo, "con «no volver a preguntar» solo informa")
        otra.destroy()

    def test_la_barra_tiene_buscar_actualizaciones_y_avisa_del_resultado(self):
        import actualizador
        from unittest import mock
        textos = self._textos(self.barra)
        self.assertIn("Buscar actualizaciones", textos)
        mensajes = []
        mb = mock.Mock(showinfo=lambda t, m: mensajes.append(m))
        with mock.patch.dict(self.mod, {"messagebox": mb}):
            with mock.patch.object(actualizador, "consultar", lambda v: (None, True)):
                self.barra._buscar_actualizacion("2.4.1", manual=True)
                self.barra.update()
            with mock.patch.object(actualizador, "consultar", lambda v: (None, False)):
                self.barra._buscar_actualizacion("2.4.1", manual=True)
                self.barra.update()
        self.assertIn("Ya tienes la última versión", mensajes[0])
        self.assertIn("No pude consultar", mensajes[1])

    def _nodo_de_prueba(self):
        """Un nodo SIN iniciar (no abre puertos): solo su historial, para probar la interfaz."""
        import mensajeria_red as M
        nodo = M.Nodo("Yo", M.generar_clave(), os.path.join(self.carpeta, "mensajes.json"), difundir=False)
        self.barra.mensajeria = nodo
        return nodo

    def test_mensajes_sin_clave_explica_como_crearla_y_valida(self):
        guardadas = []
        self.mod["guardar_clave_mensajeria"] = guardadas.append
        v = self.mod["VentanaMensajes"](self.barra)
        self.barra.update()
        self.assertIn("clave del grupo", v.estado.cget("text"))
        v.caja_clave.insert(0, "no es una clave")
        v._guardar_clave()
        self.assertIn("no es válida", v.aviso.cget("text"))
        self.assertEqual(guardadas, [])
        v._crear_clave()                                     # quien administra crea una nueva
        clave = v.caja_clave.get()
        import mensajeria_red
        self.assertTrue(mensajeria_red.clave_valida(clave))
        v.destroy()

    def test_el_chat_muestra_lo_recibido_y_lo_pendiente(self):
        nodo = self._nodo_de_prueba()
        nodo.almacen.datos["mensajes"] += [
            {"id": "1", "de": "Ana", "para": "Yo", "texto": "¿Revisaste la guía?", "ts": 1760000000.0, "entrante": True},
            {"id": "2", "de": "Yo", "para": "Luis", "texto": "Sí, ya la envié", "ts": 1760000100.0,
             "entrante": False, "entregado": [], "destinatarios": ["Luis"]},
            {"id": "3", "de": "Yo", "para": "*", "texto": "Aviso a todos", "ts": 1760000200.0,
             "entrante": False, "entregado": ["Ana"], "destinatarios": ["Ana"]}]
        nodo.almacen.datos["conocidos"] = {"Ana": {"ip": "127.0.0.1", "tcp": 1}, "Luis": {"ip": "127.0.0.1", "tcp": 1}}
        nodo.almacen.datos["pendientes"] = {"Luis": ["2"]}
        self.assertEqual(nodo.no_leidos(), 1)
        v = self.mod["VentanaMensajes"](self.barra)
        self.barra.update()
        texto = v.texto.get("1.0", "end")
        self.assertIn("Ana: ¿Revisaste la guía?", texto)
        self.assertIn("pendiente (Luis)", texto)
        self.assertIn("Aviso a todos  ✓", texto)
        self.assertEqual(list(v.destino.cget("values")), ["Todos", "Ana", "Luis"])
        self.assertEqual(nodo.no_leidos(), 0)                 # abrir la ventana los marca como leídos
        v.destroy()

    def test_enviar_sin_conocidos_avisa_en_vez_de_callar(self):
        nodo = self._nodo_de_prueba()
        v = self.mod["VentanaMensajes"](self.barra)
        v.entrada.insert(0, "¿hay alguien?")
        v._enviar()
        self._esperar(lambda: v.aviso.cget("text"))
        self.assertIn("Todavía no conozco a nadie", v.aviso.cget("text"))
        v.destroy()

    def test_el_panel_cuenta_los_mensajes_nuevos_y_avisa_al_llegar(self):
        self.barra.actualizar_mensajes()
        self.assertEqual(self.barra.mensajes_texto.cget("text"), "")           # sin clave: no molesta
        nodo = self._nodo_de_prueba()
        nodo.almacen.datos["mensajes"] += [
            {"id": str(i), "de": "Ana", "para": "*", "texto": "hola", "ts": 1.0 + i, "entrante": True}
            for i in range(2)]
        self.barra.actualizar_mensajes()
        self.assertEqual(self.barra.mensajes_texto.cget("text"), "💬 2 mensajes nuevos")
        nodo.marcar_leidos()
        self.barra.actualizar_mensajes()
        self.assertIn("Mensajes · 0 en línea", self.barra.mensajes_texto.cget("text"))
        self.barra.cola_mensajes.put({"de": "Ana", "texto": "reunión a las 15:00"})
        self.barra._vigilar_mensajes()
        avisos = [w for w in self.barra.winfo_children() if isinstance(w, self.mod["Aviso"])]
        self.assertEqual(len(avisos), 1)
        for a in avisos:
            a.destroy()
        self.barra.mensajeria = None

    def test_la_x_cierra_la_barra(self):
        self.barra.boton_cerrar.event_generate("<ButtonPress-1>", x=3, y=3)
        with self.assertRaises(tk.TclError):        # ventana destruida
            self.barra.winfo_exists()

    def test_la_rueda_desplaza_si_no_cabe(self):
        b = self.barra
        if not b.con_scroll:
            self.skipTest("en esta pantalla la barra cabe entera")
        self.assertEqual(b.desplazamiento, 0)
        b.panel.event_generate("<MouseWheel>", delta=-120)
        b.update()
        self.assertGreater(b.desplazamiento, 0)
        b.panel.event_generate("<MouseWheel>", delta=120)
        b.update()
        self.assertEqual(b.desplazamiento, 0)

    def test_la_barrita_llega_al_final_y_vuelve(self):
        b = self.barra
        if not b.con_scroll:
            self.skipTest("en esta pantalla la barra cabe entera")
        b._arrastrar_indicador(type("Evento", (), {"y": b.alto})())
        self.assertEqual(b.desplazamiento, b.alto_contenido - b.alto)
        b._desplazar(-10 ** 6)
        self.assertEqual(b.desplazamiento, 0)

    def test_nunca_se_sale_de_la_pantalla(self):
        b = self.barra
        izq, arriba, der, abajo = b._area()
        b.update()
        self.assertGreaterEqual(b.winfo_y(), arriba)
        self.assertLessEqual(b.winfo_y() + b.winfo_height(), abajo)

    # ---------------------------------------------------- actividad de los botones
    def _correr(self, codigo_python: str, titulo: str = "Prueba", esperar: float = 15):
        """Lanza un script de juguete en la ventana de actividad y espera que termine."""
        import tempfile
        import time
        carpeta = tempfile.mkdtemp()
        self.mod["EJECUCIONES"] = os.path.join(carpeta, "ultimas.json")
        self.barra.ejecuciones = {}
        consola = self.mod["Consola"](self.barra, titulo, [sys.executable, "-c", codigo_python])
        limite = time.time() + esperar
        while consola.estado_actual == "proceso" and time.time() < limite:
            self.barra.update()
            time.sleep(0.02)
        self.barra.update()
        return consola

    def test_actividad_con_avisos_y_progreso(self):
        c = self._correr("print('##PROGRESO 1/2 uno'); print('[OK] a');"
                         "print('##PROGRESO 2/2 dos'); print('[SALTADA] b')")
        self.assertEqual(c.estado_actual, "avisos")
        self.assertEqual(c.progreso, (2, 2, "dos"))
        self.assertEqual(c.resumen.cget("text"), "1 correcta · 1 saltada")
        self.assertNotIn("##PROGRESO", "\n".join(c.lineas))     # no ensucia el detalle
        c.destroy()

    def test_actividad_fallida_no_dice_listo(self):
        c = self._correr("import sys; print('Usuario incorrecto'); sys.exit(3)")
        self.assertEqual(c.estado_actual, "error")
        self.assertIn("usuario o contraseña", c.pista.cget("text"))
        self.assertTrue(c.detalle_visible)                      # se abre solo para ver qué pasó
        self.assertIn("Reintentar", [b.cget("text").strip() for b in c.botones.values()])
        c.destroy()

    def test_actividad_completada(self):
        c = self._correr("print('[OK] a'); print('[OK] b')")
        self.assertEqual(c.estado_actual, "completado")
        self.assertEqual(c.resumen.cget("text"), "2 correctas")
        c.destroy()

    def test_cancelar_detiene_el_script(self):
        import time
        c = self._correr("import time; time.sleep(60)", esperar=0.5)
        self.assertEqual(c.estado_actual, "proceso")
        c._cancelar()
        limite = time.time() + 10
        while c.estado_actual == "proceso" and time.time() < limite:
            self.barra.update()
            time.sleep(0.02)
        self.assertEqual(c.estado_actual, "cancelado")
        c.destroy()

    def test_el_boton_muestra_el_estado_y_lo_recuerda(self):
        nombre = self.barra.herramientas[0]["nombre"]
        c = self._correr("print('[OK] a')", titulo=nombre)
        icono, _color, texto = self.barra._info_fila(nombre)
        self.assertEqual(icono, "✓")
        self.assertIn("1 correcta", texto)
        self.assertIn("Última vez", self.barra._ayuda_boton(self.barra.herramientas[0]))
        guardado = self.mod["cargar_ejecuciones"](self.mod["EJECUCIONES"])
        self.assertEqual(guardado[nombre]["estado"], "completado")
        c.destroy()

    def test_mientras_corre_el_boton_esta_en_proceso(self):
        nombre = self.barra.herramientas[0]["nombre"]
        c = self._correr("import time; time.sleep(60)", titulo=nombre, esperar=0.3)
        self.assertIn(nombre, self.barra.corriendo)
        self.assertIn(self.barra._info_fila(nombre)[0], "◐◓◑◒")
        c.destroy()                                             # cierra y detiene
        self.assertNotIn(nombre, self.barra.corriendo)

    def test_cartelito_si_la_ventana_esta_oculta(self):
        import tempfile
        import time
        self.mod["EJECUCIONES"] = os.path.join(tempfile.mkdtemp(), "ultimas.json")
        c = self.mod["Consola"](self.barra, "Prueba", [sys.executable, "-c",
                                "import time; time.sleep(0.4); print('[OK] a')"])
        c.withdraw()                       # el usuario la minimizó o la cerró de vista
        limite = time.time() + 15
        while c.estado_actual == "proceso" and time.time() < limite:
            self.barra.update()
            time.sleep(0.02)
        self.barra.update()
        cartelitos = [w for w in self.barra.winfo_children()
                      if isinstance(w, self.mod["Aviso"])]
        self.assertEqual(len(cartelitos), 1)
        c.destroy()

    def test_lengueta_pulsa_y_luego_destella(self):
        import tempfile
        import time
        self.mod["EJECUCIONES"] = os.path.join(tempfile.mkdtemp(), "ultimas.json")
        c = self.mod["Consola"](self.barra, "Prueba", [sys.executable, "-c",
                                "import time; time.sleep(0.4)"])
        self.barra.update()
        self.assertTrue(self.barra.corriendo)
        limite = time.time() + 15
        while c.estado_actual == "proceso" and time.time() < limite:
            self.barra.update()
            time.sleep(0.02)
        self.barra.update()
        self.assertFalse(self.barra.corriendo)
        self.assertEqual(self.barra._color_lengueta(), self.mod["color_de_estado"]("completado"))
        c.destroy()

    # ------------------------------------------------------------ vista previa
    def _esperar(self, condicion, segundos: float = 15) -> None:
        import time
        limite = time.time() + segundos
        while not condicion() and time.time() < limite:
            self.barra.update()
            time.sleep(0.02)
        self.barra.update()

    @staticmethod
    def _textos(ventana) -> str:
        """Todo el texto visible de una ventana."""
        partes = []

        def recorrer(w):
            try:
                partes.append(str(w.cget("text")))
            except Exception:           # noqa: BLE001  (no todos los widgets tienen texto)
                pass
            for hijo in w.winfo_children():
                recorrer(hijo)
        recorrer(ventana)
        return "\n".join(partes)

    def test_vista_previa_del_libro_es_instantanea(self):
        import datetime
        estado = {"fecha": datetime.date.today().strftime("%d/%m/%Y"),
                  "revisado": "05/10/2026 15:52", "bloques": [], "sin_firmar": [],
                  "sin_registro": [{"curso": "5BA", "hora": "09:40-11:10", "oa": False,
                                    "leccionario": True, "asistencia": True}]}
        ruta = os.path.join(self.carpeta, "estado.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(estado, f)
        self.mod["ESTADO_FIRMAS"] = ruta
        lanzado = []
        previa = self.mod["VistaPrevia"](self.barra, {"nombre": "Registrar libro",
                                                       "vista_previa": "libro"},
                                         lambda *a: lanzado.append(a))
        self.barra.update()
        texto = self._textos(previa)
        self.assertIn("5BA 09:40", texto)
        self.assertIn("se completará: OA", texto)
        self.assertIn("1 de 1 marcadas", texto)
        self.assertIn("Continuar (1)", texto)
        self.assertEqual(lanzado, [])                     # todavía no se ejecutó nada
        previa._continuar()
        self.assertEqual(lanzado, [(["5BA|09:40-11:10"], ["5BA|09:40-11:10"])])
        self.assertFalse(previa.winfo_exists())               # la ventana se cerró

    def test_vista_previa_cancelar_no_ejecuta(self):
        lanzado = []
        previa = self.mod["VistaPrevia"](self.barra, {"nombre": "X", "vista_previa": "libro"},
                                         lambda *a: lanzado.append(a))
        self.barra.update()
        previa.destroy()
        self.assertEqual(lanzado, [])

    def test_vista_previa_simulada_muestra_el_avance_y_el_resultado(self):
        self.mod["comando_webclass"] = lambda *a, **k: [
            sys.executable, "-c",
            "print('##PROGRESO 1/2 5BA'); print('  [SIMULAR] Clase 21: se asignaría a 40 alumnas');"
            "print('  [SALTADA] Clase 22: sin fecha'); print('##PROGRESO 2/2')"]
        previa = self.mod["VistaPrevia"](self.barra, {"nombre": "Asignar clases",
                                                       "destino": "asignar --hoy",
                                                       "vista_previa": "simular"},
                                         lambda *a: None)
        self.assertTrue(previa._cargando)
        self._esperar(lambda: not previa._cargando)
        texto = self._textos(previa)
        self.assertIn("Clase 21: se asignaría a 40 alumnas", texto)
        self.assertIn("1 clase se saltará", texto)
        self.assertIn("Continuar", texto)
        previa.destroy()

    def test_abrir_pide_confirmacion_antes_de_ejecutar(self):
        import tempfile
        vacio = tempfile.mkdtemp()
        self.mod["BUZON"] = vacio
        boton = {"nombre": "Subir recursos", "tipo": "webclass", "destino": "subir",
                 "vista_previa": "subir"}
        self.mod["abrir"](boton, self.barra)
        self.barra.update()
        previas = [w for w in self.barra.winfo_children()
                   if isinstance(w, self.mod["VistaPrevia"])]
        self.assertEqual(len(previas), 1)
        self.assertEqual(self.barra.corriendo, {})        # no corrió nada todavía
        self.assertIn("No hay archivos nuevos", self._textos(previas[0]))
        previas[0]._continuar()                           # «Ejecutar igual»
        consolas = [w for w in self.barra.winfo_children()
                    if isinstance(w, self.mod["Consola"])]
        self.assertEqual([c.titulo for c in consolas], ["Subir recursos"])
        consolas[0].destroy()

    def _previa_libro_con_bloques(self, n: int = 3):
        import datetime
        bloques = [{"curso": f"{i}BA", "hora": f"0{i}:00-0{i}:45", "asignatura": "Ciencias",
                    "id": 100 + i, "oa": False, "leccionario": True, "asistencia": True}
                   for i in range(1, n + 1)]
        estado = {"fecha": datetime.date.today().strftime("%d/%m/%Y"),
                  "revisado": "05/10/2026 15:52", "bloques": bloques, "sin_firmar": [],
                  "sin_registro": bloques}
        ruta = os.path.join(self.carpeta, "estado.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(estado, f)
        self.mod["ESTADO_FIRMAS"] = ruta
        self.lanzado = []
        previa = self.mod["VistaPrevia"](self.barra, {"nombre": "Registrar libro",
                                                       "vista_previa": "libro"},
                                         lambda *a: self.lanzado.append(a))
        self.barra.update()
        return previa

    def test_casillas_marcar_y_desmarcar(self):
        previa = self._previa_libro_con_bloques(3)
        lista = previa.lista
        self.assertEqual(len(lista.marcadas()), 3)                  # parte con todo marcado
        primera = lista.orden[0]
        lista._pulsar(primera)
        self.assertEqual(len(lista.marcadas()), 2)
        self.assertIn("2 de 3 marcadas", previa.contador.cget("text"))
        self.assertIn("Continuar (2)", previa.boton_continuar.cget("text"))
        lista._pulsar(primera)
        self.assertEqual(len(lista.marcadas()), 3)
        previa.destroy()

    def test_seleccionar_todo_y_ninguno(self):
        previa = self._previa_libro_con_bloques(3)
        previa.lista.marcar_todo(False)
        self.assertEqual(previa.lista.marcadas(), [])
        self.assertIn("0 de 3 marcadas", previa.contador.cget("text"))
        previa.lista.marcar_todo(True)
        self.assertEqual(len(previa.lista.marcadas()), 3)
        previa.destroy()

    def test_con_nada_marcado_no_se_puede_continuar(self):
        previa = self._previa_libro_con_bloques(2)
        previa.lista.marcar_todo(False)
        previa._continuar()
        self.assertEqual(self.lanzado, [])                          # no ejecutó nada
        self.assertTrue(previa.winfo_exists())
        self.assertIn("marca al menos una casilla", previa.aviso.cget("text"))
        previa.destroy()

    def test_continuar_entrega_solo_lo_marcado(self):
        previa = self._previa_libro_con_bloques(3)
        previa.lista._pulsar(previa.lista.orden[1])                 # desmarca el del medio
        previa._continuar()
        claves, todas = self.lanzado[0]
        self.assertEqual(len(todas), 3)
        self.assertEqual(claves, [todas[0], todas[2]])

    def test_abrir_pasa_la_seleccion_a_la_herramienta(self):
        import tempfile
        buzon = tempfile.mkdtemp()
        os.makedirs(os.path.join(buzon, "5 basico"))
        for nombre in ("a.pdf", "b.docx"):
            open(os.path.join(buzon, "5 basico", nombre), "w").close()
        self.mod["BUZON"] = buzon
        comandos = []
        self.mod["comando_webclass"] = lambda *a, **k: (comandos.append(a),
                                                        [sys.executable, "-c", "pass"])[1]
        self.mod["abrir"]({"nombre": "Subir recursos", "tipo": "webclass", "destino": "subir",
                           "vista_previa": "subir"}, self.barra)
        self.barra.update()
        previa = [w for w in self.barra.winfo_children()
                  if isinstance(w, self.mod["VistaPrevia"])][0]
        previa.lista.fijar("5 basico/b.docx", False)                # solo se sube a.pdf
        previa._continuar()
        self.assertEqual(comandos[-1][0], "subir")
        self.assertEqual(comandos[-1][1], "--seleccion")
        with open(comandos[-1][2], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["claves"], ["5 basico/a.pdf"])
        for w in self.barra.winfo_children():
            if isinstance(w, self.mod["Consola"]):
                w.destroy()

    def test_abrir_con_todo_marcado_no_pasa_seleccion(self):
        import tempfile
        buzon = tempfile.mkdtemp()
        os.makedirs(os.path.join(buzon, "5 basico"))
        open(os.path.join(buzon, "5 basico", "a.pdf"), "w").close()
        self.mod["BUZON"] = buzon
        comandos = []
        self.mod["comando_webclass"] = lambda *a, **k: (comandos.append(a),
                                                        [sys.executable, "-c", "pass"])[1]
        self.mod["abrir"]({"nombre": "Subir recursos", "tipo": "webclass", "destino": "subir",
                           "vista_previa": "subir"}, self.barra)
        self.barra.update()
        previa = [w for w in self.barra.winfo_children()
                  if isinstance(w, self.mod["VistaPrevia"])][0]
        previa._continuar()
        self.assertEqual(comandos[-1], ("subir",))                  # el comportamiento de siempre
        for w in self.barra.winfo_children():
            if isinstance(w, self.mod["Consola"]):
                w.destroy()

    # ----------------------------------------------------- resultado de la actividad
    def test_la_actividad_muestra_intente_hice_y_no_pude(self):
        guion = (
            "import json\n"
            "def it(c, e, t, **x): print('##ITEM ' + json.dumps(dict(clave=c, estado=e, titulo=t, **x)))\n"
            "it('a', 'hecho', '5BA 08:00', que='OA', detalle='clase 21')\n"
            "it('b', 'pendiente', '6BA 09:40', que='OA', motivo='no hay clase con esa fecha en la planificación')\n"
            "it('c', 'ya', '8BA 13:35')\n"
            "it('d', 'omitido', '7BA 11:20')\n"
            "print('=== Resultado ===')\n"
            "print('  FALTA TU FIRMA en:')\n"
            "print('    5BA 08:00-09:30 Ciencias')\n")
        c = self._correr(guion, titulo="Registrar libro")
        self.assertEqual(c.estado_actual, "avisos")                 # no dice Completado
        self.assertIn("1 correcta", c.resumen.cget("text"))
        self.assertIn("omitida por ti", c.resumen.cget("text"))
        texto = c.texto_resultado.get("1.0", "end")
        self.assertIn("Intenté 3 · hice 1 · no pude 1 · ya estaban 1 · omitiste 1", texto)
        self.assertIn("✓ Hice (1)", texto)
        self.assertIn("5BA 08:00 — clase 21", texto)
        self.assertIn("⚠ No pude (1)", texto)
        self.assertIn("Tu planificación no tiene una clase con esa fecha", texto)
        self.assertIn("→ Agrega la clase", texto)
        self.assertIn("– Omitido por ti (1)", texto)
        self.assertIn("✍ Te falta firmar (1)", texto)
        self.assertNotIn("##ITEM", "\n".join(c.lineas))             # el detalle técnico queda limpio
        self.assertTrue(c.marco_resultado.winfo_ismapped())
        c.destroy()

    def test_sin_items_la_actividad_funciona_como_antes(self):
        c = self._correr("print('[OK] a')")
        self.assertEqual(c.estado_actual, "completado")
        self.assertFalse(c.marco_resultado.winfo_ismapped())
        c.destroy()

    # ------------------------------------------------------------- editor de destinos
    def _ventana_destinos(self, opciones_en_cache=None):
        import tempfile
        unidades = [{"curso": "5BA", "id": 1, "nombre": "5A - Energía"},
                    {"curso": "5BB", "id": 2, "nombre": "5B - Energía"},
                    {"curso": "7BA", "id": 3, "nombre": "7A - Defensas"}]
        self.mod["perfil_de_trabajo"] = lambda: {"unidades": unidades,
                                                 "curso_ids": {"5BA": 10, "5BB": 11, "7BA": 12}}
        self.mod["DESTINOS_JSON"] = os.path.join(self.carpeta, "destinos.json")
        self.mod["OPCIONES_DESTINO"] = os.path.join(self.carpeta, "opciones.json")
        with open(self.mod["DESTINOS_JSON"], "w", encoding="utf-8") as f:
            json.dump({"1": {"id": 99, "nombre": "T.J Ciencias 1S"}}, f)
        if opciones_en_cache:
            with open(self.mod["OPCIONES_DESTINO"], "w", encoding="utf-8") as f:
                json.dump(opciones_en_cache, f)
        ventana = self.mod["VentanaDestinos"](self.barra)
        self.barra.update()
        return ventana

    # ------------------------------------------------------ períodos con tickets
    GUION_CLASES = (
        "import json\n"
        "print('##ITEM ' + json.dumps({'clave': '1', 'estado': 'propuesto', 'titulo': '5BA · Clase 22',"
        " 'grupo': '5BA', 'que': 'asignación', 'detalle': '42 alumnas'}))\n"
        "print('##ITEM ' + json.dumps({'clave': '2', 'estado': 'propuesto', 'titulo': '5BB · Clase 23',"
        " 'grupo': '5BB', 'que': 'asignación', 'detalle': '41 alumnas'}))\n")

    def _boton(self, nombre: str) -> dict:
        with open(self.mod["CONFIG"], encoding="utf-8") as f:
            return next(h for h in json.load(f) if h["nombre"] == nombre)

    def test_asignar_lo_pendiente_deja_marcar_los_meses(self):
        comandos = []
        guion = self.GUION_CLASES
        self.mod["comando_webclass"] = lambda *a, **k: (comandos.append(a),
                                                        [sys.executable, "-c", guion])[1]
        boton = self._boton("Asignar lo pendiente")
        self.assertEqual(boton["tipo"], "periodos")
        v = self.mod["VentanaTickets"](self.barra, boton)
        self.barra.update()
        meses = self.mod["meses_escolares"](v.hoy)
        marcadas = v.lista.marcadas()
        self.assertEqual(marcadas, [m["clave"] for m in meses[:2]][:len(marcadas)])   # este mes y el anterior
        self.assertIn("(este mes)", self._textos(v))
        v.lista.marcar_todo(False)
        v._aceptar()                                                  # sin meses no avanza
        self.assertIn("al menos un mes", v.aviso.cget("text"))
        v.lista.fijar(meses[0]["clave"], True)                         # solo el mes actual
        v._aceptar()
        previa = [w for w in self.barra.winfo_children()
                  if isinstance(w, self.mod["VistaPrevia"])][0]
        self._esperar(lambda: not previa._cargando)
        comandos[:] = [c for c in comandos if c[0] == "asignar"]       # sin la revisión del libro de fondo
        self.assertEqual(comandos[0], ("asignar", "--meses", meses[0]["clave"], "--simular"))
        self.assertEqual(len(previa.lista.marcadas()), 2)             # además, las clases con casillas
        previa.lista.fijar("2", False)
        previa._continuar()
        corrida = comandos[1]
        self.assertEqual(corrida[:3], ("asignar", "--meses", meses[0]["clave"]))
        with open(corrida[corrida.index("--seleccion") + 1], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["claves"], ["1"])
        for w in self.barra.winfo_children():
            if isinstance(w, self.mod["Consola"]):
                w.destroy()

    def test_varios_meses_van_en_orden_cronologico(self):
        comandos = []
        self.mod["comando_webclass"] = lambda *a, **k: (comandos.append(a),
                                                        [sys.executable, "-c", "pass"])[1]
        v = self.mod["VentanaTickets"](self.barra, self._boton("Asignar lo pendiente"))
        meses = self.mod["meses_escolares"](v.hoy)
        if len(meses) < 3:
            self.skipTest("hace falta más de dos meses del año escolar")
        v.lista.marcar_todo(False)
        for m in (meses[0], meses[2]):                                 # octubre y agosto, por ejemplo
            v.lista.fijar(m["clave"], True)
        v._aceptar()
        previa = [w for w in self.barra.winfo_children()
                  if isinstance(w, self.mod["VistaPrevia"])][0]
        self._esperar(lambda: not previa._cargando)
        self.assertEqual(comandos[0][2], f"{meses[2]['clave']},{meses[0]['clave']}")
        previa.destroy()

    def test_diagnostico_con_tickets_de_periodos(self):
        comandos = []
        self.mod["comando_webclass"] = lambda *a, **k: (comandos.append(a),
                                                        [sys.executable, "-c", "pass"])[1]
        boton = self._boton("Diagnóstico del libro")
        v = self.mod["VentanaTickets"](self.barra, boton)
        self.barra.update()
        textos = self._textos(v)
        for esperado in ("Hoy", "Ayer", "Esta semana", "Semana anterior", "Este mes", "Mes anterior",
                         "Todo el año"):
            self.assertIn(esperado, textos)
        self.assertEqual(v.lista.marcadas(), ["ayer"])                  # parte con «Ayer»
        v.lista.fijar("semana_anterior", True)
        dias = self.mod["dias_de_periodos"](["ayer", "semana_anterior"], v.hoy)
        self.assertIn("Revisaré", v.resumen.cget("text"))
        v._aceptar()
        consolas = [w for w in self.barra.winfo_children() if isinstance(w, self.mod["Consola"])]
        self.assertEqual(len(consolas), 1)
        self.assertEqual(comandos[-1], ("libro", "--diagnostico", "--fechas",
                                        self.mod["formatear_fechas"](dias)))
        consolas[0].destroy()

    def test_diagnostico_con_fecha_escrita_y_errores(self):
        v = self.mod["VentanaTickets"](self.barra, self._boton("Diagnóstico del libro"))
        v.lista.marcar_todo(False)
        v.texto_fecha.set("01/01/2099")
        v._actualizar()
        self.assertIn("todavía no llega", v.aviso.cget("text"))
        v._aceptar()
        self.assertTrue(v.winfo_exists())                              # no avanza con una fecha futura
        v.lista.marcar_todo(False)
        v.texto_fecha.set("")
        v._actualizar()
        self.assertEqual(v.aviso.cget("text"), "")                     # sin nada marcado no regaña de entrada
        v.destroy()

    def test_un_boton_que_la_barra_no_conoce_no_abre_la_carpeta(self):
        import tkinter.messagebox as caja
        avisos, abiertos = [], []
        original_info, original_inicio = caja.showinfo, self.mod["os"].startfile
        caja.showinfo = lambda *a, **k: avisos.append(a)
        self.mod["os"].startfile = lambda ruta: abiertos.append(ruta)
        try:
            self.mod["abrir"]({"nombre": "Botón del futuro", "tipo": "tipo-nuevo", "destino": ""},
                              self.barra)
        finally:
            caja.showinfo = original_info
            self.mod["os"].startfile = original_inicio
        self.assertEqual(abiertos, [])                                 # ya no abre la carpeta de la barra
        self.assertIn("Ciérrala con la ✕", avisos[0][1])

    def test_una_barra_con_programa_mas_nuevo_reinicia_a_la_abierta(self):
        import time
        reabiertas = []
        self.mod["reabrir_barra"] = lambda: reabiertas.append(1)
        self.assertTrue(self.mod["avisar_a_la_barra_abierta"](self.mod["VERSION_CODIGO"] + 10))
        limite = time.time() + 5
        while self.barra.senales.qsize() < 2 and time.time() < limite:
            time.sleep(0.02)
        self.assertEqual(sorted(self.barra.senales.queue), ["anotar", "reabrir"])
        self.barra._atender_senal()
        self.assertEqual(reabiertas, [1])

    def test_con_el_mismo_programa_solo_se_despliega(self):
        import time
        reabiertas = []
        self.mod["reabrir_barra"] = lambda: reabiertas.append(1)
        self.assertTrue(self.mod["avisar_a_la_barra_abierta"]())
        limite = time.time() + 5
        while self.barra.senales.empty() and time.time() < limite:
            time.sleep(0.02)
        time.sleep(0.1)
        self.assertEqual(list(self.barra.senales.queue), ["anotar"])
        self.barra._atender_senal()
        self.assertEqual(reabiertas, [])

    OPCIONES = {"opciones": [{"id": 10, "nombre": "5BA"}, {"id": 11, "nombre": "5BB"},
                             {"id": 99, "nombre": "T.J Ciencias 1S"}], "hora": "2026-10-05T10:00:00"}

    def test_destinos_muestra_todas_las_unidades_sin_consultar(self):
        v = self._ventana_destinos()
        texto = self._textos(v)
        for esperado in ("5A - Energía", "5B - Energía", "7A - Defensas",
                         "Se asigna a: T.J Ciencias 1S", "Por defecto: el curso 5BB"):
            self.assertIn(esperado, texto)
        self.assertEqual(v.lista.marcadas(), [])                     # nada marcado de entrada
        self.assertIsNone(v.proceso)                                 # no consultó a Webclass
        v.destroy()

    def test_destinos_cambia_solo_la_unidad_marcada(self):
        v = self._ventana_destinos({"2": self.OPCIONES})
        v.lista.fijar("2", True)
        v._elegir_destino()                                          # opciones ya guardadas: sin red
        self.assertIsNone(v.proceso)
        self.assertEqual(list(v.combos), ["2"])
        combo = v.combos["2"]
        valores = list(combo["values"])
        self.assertIn("5BB (curso de la unidad)", valores)
        combo.current(valores.index("T.J Ciencias 1S"))
        v._guardar()
        with open(self.mod["DESTINOS_JSON"], encoding="utf-8") as f:
            guardado = json.load(f)
        self.assertEqual(guardado, {"1": {"id": 99, "nombre": "T.J Ciencias 1S"},
                                    "2": {"id": 99, "nombre": "T.J Ciencias 1S"}})
        self.assertIn("Guardado: 1 unidad actualizada", v.aviso.cget("text"))
        v.destroy()

    # ------------------------------------------------- registrar libro hacia atrás
    def _guion_pendientes(self) -> str:
        items = [
            {"clave": "4BA|08:00-00:00|801|2026-10-05", "estado": "propuesto",
             "titulo": "05/10 4BA 08:00-00:00 Ciencias Naturales", "grupo": "lun 05/10",
             "que": "bloque", "detalle": "se completará: OA, leccionario"},
            {"clave": "4BA|12:50-00:00|802|2026-10-06", "estado": "propuesto",
             "titulo": "06/10 4BA 12:50-00:00 Ciencias Naturales", "grupo": "mar 06/10",
             "que": "bloque", "detalle": "se completará: OA, leccionario, asistencia"}]
        lineas = ["print('##PROGRESO 1/3 Leyendo 4BA (10/2026)')"]
        lineas += [f"print('##ITEM ' + {json.dumps(i, ensure_ascii=False)!r})" for i in items]
        lineas += ["print('  FALTA TU FIRMA en:')", "print('    06/10 4BA 12:50-00:00')"]
        return "; ".join(lineas)

    def test_cada_comando_que_usa_la_barra_tiene_su_script(self):
        original = cargar_modulo()["comando_webclass"]          # el de verdad, no el de juguete
        for orden in ("firmas", "horario", "asignar", "subir", "libro", "observar", "planificar", "correo"):
            self.assertTrue(original(orden, "--x"), orden)

    def _abrir_planificar(self, comandos):
        self.mod["comando_webclass"] = lambda *a, **k: (comandos.append(a),
                                                        [sys.executable, "-c", "pass"])[1]
        v = self.mod["VentanaPlanificar"](self.barra, {"nombre": "Planificar", "icono": "🗓️",
                                                       "tipo": "planificar"})
        self.barra.update()
        v.unidades = {"5BA · Unidad": "50"}
        v.unidad.configure(values=list(v.unidades))
        return v

    def _vista_previa(self):
        previa = [w for w in self.barra.winfo_children() if isinstance(w, self.mod["VistaPrevia"])][0]
        self._esperar(lambda: not previa._cargando)
        return previa

    def test_planificar_esqueleto_arma_el_comando_y_valida_fechas(self):
        comandos = []
        v = self._abrir_planificar(comandos)
        v._continuar()
        self.assertIn("Elige la unidad", v.aviso.cget("text"))
        v.unidad.set("5BA · Unidad")
        v.desde.delete(0, "end")
        v.desde.insert(0, "12/10/2026")
        v.hasta.delete(0, "end")
        v.hasta.insert(0, "01/10/2026")
        v._continuar()
        self.assertIn("anterior", v.aviso.cget("text"))
        v.hasta.delete(0, "end")
        v.hasta.insert(0, "23/10/2026")
        v._continuar()
        self._vista_previa().destroy()
        self.assertEqual(comandos[0], ("planificar", "--unidad", "50", "--esqueleto", "--desde",
                                       "12/10/2026", "--hasta", "23/10/2026", "--simular"))

    def test_planificar_marcar_pide_clases_y_envia_las_etiquetas(self):
        comandos = []
        v = self._abrir_planificar(comandos)
        v.unidad.set("5BA · Unidad")
        v.accion.set("marcar")
        v._mostrar_accion()
        v._continuar()
        self.assertIn("marca al menos una clase", v.aviso.cget("text"))
        v.lista = self.mod["ListaMarcable"](v.cuerpo)
        v.tipos = {"1": "oa", "2": "habilidad", "3": "clase", "4": "clase"}
        v.etiquetas = {"1": "OA8", "2": "Hab_d", "3": "", "4": ""}
        for clave in v.tipos:
            v.lista.agregar(clave, clave, marcado=clave != "4")
        v._continuar()
        self._vista_previa().destroy()
        self.assertEqual(comandos[0][:6], ("planificar", "--unidad", "50", "--marcar", "--clases", "3"))
        self.assertIn("OA8", comandos[0])
        self.assertIn("Hab_d", comandos[0])

    def _soltar(self, nombre="guia.pdf"):
        """Una VentanaSoltar con un buzón de juguete (nunca el real) y un archivo de verdad."""
        buzon = os.path.join(self.carpeta, "buzon")
        os.makedirs(os.path.join(buzon, "5 basico"))
        self.mod["BUZON"] = buzon
        guia = os.path.join(self.carpeta, nombre)
        with open(guia, "wb") as f:
            f.write(b"%PDF-1.4 prueba")
        return buzon, guia, self.mod["VentanaSoltar"](self.barra, [guia])

    def _correo_configurado(self):
        """Como si el docente ya hubiera guardado su Gmail y la contraseña (sin tocar el llavero)."""
        clase = self.mod["VentanaCorreo"]
        self.enterContext(mock.patch.object(clase, "_remitente", lambda s: "ana@gmail.com"))
        self.enterContext(mock.patch.object(clase, "_clave", lambda s: "clave"))

    def _ventanas_de_correo(self):
        self.barra.update()
        return [w for w in self.barra.winfo_children() if isinstance(w, self.mod["VentanaCorreo"])]

    def test_soltar_sin_marcar_pie_solo_sube_a_webclass(self):
        buzon, _guia, v = self._soltar()
        v._copiar("5 basico")
        self.assertEqual(os.listdir(os.path.join(buzon, "5 basico")), ["guia.pdf"])
        self.assertEqual(self._ventanas_de_correo(), [])               # no se ofrece correo
        self.assertFalse(v.pie.get())                                  # y por defecto viene sin marcar

    def test_soltar_con_pie_sube_y_abre_el_correo_con_el_archivo(self):
        buzon, guia, v = self._soltar()
        v.pie.set(True)
        v._copiar("5 basico")
        self.assertEqual(os.listdir(os.path.join(buzon, "5 basico")), ["guia.pdf"])
        correos = self._ventanas_de_correo()
        self.assertEqual(len(correos), 1)
        self.assertEqual(correos[0].archivos, [guia])
        correos[0].destroy()

    def test_soltar_solo_pie_no_copia_nada_al_buzon(self):
        buzon, guia, v = self._soltar()
        v._solo_pie()
        self.assertEqual(os.listdir(os.path.join(buzon, "5 basico")), [])
        correos = self._ventanas_de_correo()
        self.assertEqual([c.archivos for c in correos], [[guia]])
        correos[0].destroy()

    def test_un_segundo_archivo_soltado_se_suma_al_mismo_correo(self):
        self._correo_configurado()
        _buzon, guia, v = self._soltar("Energía 5BA.pdf")
        otra = os.path.join(self.carpeta, "Circuitos 5BB.pdf")
        with open(otra, "wb") as f:
            f.write(b"%PDF-1.4 dos")
        evento = mock.Mock(data="{%s}" % otra)
        # 1) con la ventana de arrastre abierta, el archivo se suma a ella (no abre otra)
        self.barra._al_soltar(evento)
        self.assertEqual(len([w for w in self.barra.winfo_children()
                              if isinstance(w, self.mod["VentanaSoltar"])]), 1)
        self.assertEqual(v.archivos, [guia, otra])
        # 2) con el correo abierto, se suma al correo y el asunto/curso se rearman
        v.pie.set(True)
        v._abrir_correo()
        correo = self._ventanas_de_correo()[0]
        self.assertEqual(correo.caja_curso.get(), "5BA, 5BB")
        self.assertEqual(correo.caja_asunto.get(), "Guías NEEP Energía, Circuitos 5BA, 5BB")
        tercera = os.path.join(self.carpeta, "Agua 5BA.pdf")
        with open(tercera, "wb") as f:
            f.write(b"%PDF-1.4 tres")
        self.barra._al_soltar(mock.Mock(data="{%s}" % tercera))
        self.assertEqual(len(self._ventanas_de_correo()), 1)
        self.assertEqual(correo.archivos, [guia, otra, tercera])
        correo.destroy()

    def test_el_asunto_escrito_a_mano_no_se_pisa(self):
        self._correo_configurado()
        _buzon, guia, v = self._soltar("Energía 5BA.pdf")
        v.pie.set(True)
        v._abrir_correo()
        correo = self._ventanas_de_correo()[0]
        self.assertEqual(correo.caja_asunto.get(), "Guía NEEP Energía 5BA")
        correo.caja_asunto.delete(0, "end")
        correo.caja_asunto.insert(0, "Mi asunto")
        correo._asunto_escrito()                      # lo que hace la tecla al soltarse
        correo.agregar_archivos([os.path.join(self.carpeta, "otra 5BB.pdf")])
        self.assertEqual(correo.caja_asunto.get(), "Mi asunto")
        correo.destroy()

    def test_la_ventana_de_correo_valida_y_arma_el_envio(self):
        comandos = []
        self.mod["comando_webclass"] = lambda *a, **k: (comandos.append(a),
                                                        [sys.executable, "-c", "pass"])[1]
        v = self.mod["VentanaCorreo"](self.barra, {"nombre": "Enviar al equipo PIE", "icono": "✉️",
                                                   "tipo": "correo"})
        self.barra.update()
        v.config_correo = {}
        v._remitente = lambda: ""
        v._ver_configuracion()                                    # sin cuenta: pide configurarla
        v.caja_correo.insert(0, "no es un correo")
        v._guardar_config()                                       # no toca el llavero con datos malos
        self.assertIn("no parece válido", v.aviso.cget("text"))
        v.caja_correo.delete(0, "end")
        v.caja_correo.insert(0, "ana@gmail.com")
        v.caja_clave.insert(0, "corta")
        v._guardar_config()
        self.assertIn("16 letras", v.aviso.cget("text"))
        # con la cuenta ya configurada: pide archivo y asunto, y arma «correo --datos»
        v._remitente = lambda: "ana@gmail.com"
        v._ver_envio()
        v._continuar()
        self.assertIn("al menos un archivo", v.aviso.cget("text"))
        guia = os.path.join(self.carpeta, "guia.pdf")
        with open(guia, "wb") as f:
            f.write(b"%PDF")
        v.archivos = [guia]
        v._continuar()
        self.assertIn("asunto", v.aviso.cget("text"))
        v.caja_asunto.insert(0, "Guía 1")
        v.mensaje.insert("1.0", "Hola")
        v._continuar()
        previa = [w for w in self.barra.winfo_children() if isinstance(w, self.mod["VistaPrevia"])][0]
        self._esperar(lambda: not previa._cargando)
        previa.destroy()
        self.assertEqual(comandos[0][:2], ("correo", "--datos"))
        self.assertEqual(comandos[0][-1], "--simular")
        with open(comandos[0][2], encoding="utf-8") as f:
            datos = json.load(f)
        self.assertEqual((datos["archivos"], datos["asunto"], datos["mensaje"]), ([guia], "Guía 1", "Hola"))

    def test_la_ventana_de_observacion_pide_lo_que_falta_y_arma_la_vista_previa(self):
        comandos = []
        self.mod["comando_webclass"] = lambda *a, **k: (comandos.append(a),
                                                        [sys.executable, "-c", "pass"])[1]
        v = self.mod["VentanaObservacion"](self.barra, {"nombre": "Registrar observación",
                                                        "icono": "📝", "tipo": "observacion"})
        self.barra.update()
        v._continuar()                                  # vacía: no avanza y dice qué falta
        self.assertIn("marca al menos una alumna", v.aviso.cget("text"))
        self.assertTrue(v.winfo_exists())
        # con todo lleno, arma el archivo y abre la vista previa de «observar --datos»
        v.curso.set("5BA")
        v.asignaturas = {"Ciencias": "55"}
        v.asignatura.set("Ciencias")
        v.lista = self.mod["ListaMarcable"](v.cuerpo)
        v.lista.agregar("101", "Ana", marcado=True)
        v.lista.agregar("102", "Luz", marcado=False)
        v.tipo.set(2)
        v.texto.insert("1.0", "Llegó tarde")
        v._continuar()
        previa = [w for w in self.barra.winfo_children()
                  if isinstance(w, self.mod["VistaPrevia"])][0]
        self._esperar(lambda: not previa._cargando)
        self.assertEqual(comandos[0][:2], ("observar", "--datos"))
        self.assertEqual(comandos[0][-1], "--simular")
        with open(comandos[0][2], encoding="utf-8") as f:
            datos = json.load(f)
        self.assertEqual((datos["alumnas"], datos["tipo"], datos["visible"]), (["101"], 2, "equipo"))
        previa.destroy()

    def test_la_ventana_de_periodo_muestra_el_rango(self):
        v = self.mod["VentanaPeriodo"](self.barra, {"nombre": "Registrar libro pendiente",
                                                    "icono": "⏪"})
        self.barra.update()
        self.assertIn("días hábil", v.rango.cget("text"))             # por defecto: últimos 7 días
        v.atajo.set("ayer")
        v._actualizar()
        self.assertRegex(v.rango.cget("text"), r"el \d\d/\d\d/\d{4} \(1 día hábil\)")
        v.atajo.set("fecha")
        v.texto_fecha.set("31/02/2026")
        v._actualizar()
        self.assertIn("no existe", v.aviso.cget("text"))
        v._continuar()                                                # no avanza con una fecha mala
        self.assertTrue(v.winfo_exists())
        v.destroy()

    def test_registrar_hacia_atras_de_punta_a_punta(self):
        comandos = []
        guion = self._guion_pendientes()
        self.mod["comando_webclass"] = lambda *a, **k: (comandos.append(a),
                                                        [sys.executable, "-c", guion])[1]
        v = self.mod["VentanaPeriodo"](self.barra, {"nombre": "Registrar libro pendiente",
                                                    "icono": "⏪", "tipo": "libro-atras"})
        v.atajo.set("7")
        v._continuar()                                                # abre la vista previa
        previa = [w for w in self.barra.winfo_children()
                  if isinstance(w, self.mod["VistaPrevia"])][0]
        self._esperar(lambda: not previa._cargando)
        self.assertEqual(comandos[0][0], "libro")
        self.assertEqual(comandos[0][1], "--desde")
        self.assertEqual(comandos[0][3], "--hasta")
        self.assertEqual(comandos[0][-1], "--solo-listar")             # la vista previa solo lee
        texto = self._textos(previa)
        self.assertIn("LUN 05/10", texto)                             # agrupado por día
        self.assertIn("MAR 06/10", texto)
        self.assertIn("Quedarán 1 bloque por firmar", texto)
        self.assertEqual(len(previa.lista.marcadas()), 2)
        previa.lista.fijar("4BA|08:00-00:00|801|2026-10-05", False)   # desmarca el del lunes
        previa._continuar()
        corrida = comandos[1]
        self.assertEqual(corrida[:2], ("libro", "--desde"))
        self.assertNotIn("--solo-listar", corrida)
        self.assertEqual(corrida[corrida.index("--seleccion") - 0], "--seleccion")
        with open(corrida[corrida.index("--seleccion") + 1], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["claves"], ["4BA|12:50-00:00|802|2026-10-06"])
        for w in self.barra.winfo_children():
            if isinstance(w, self.mod["Consola"]):
                w.destroy()

    # ------------------------------------------------------- elegir la clase a mano
    GUION_SIN_CLASE = (
        "import json\n"
        "print('##ITEM ' + json.dumps({'clave': '4BA|12:50-00:00|802|2026-10-06', 'estado': 'pendiente',"
        " 'titulo': '06/10 4BA 12:50 Ciencias Naturales', 'grupo': 'mar 06/10', 'que': 'OA y leccionario',"
        " 'motivo': 'no hay clase con esa fecha en la planificación',"
        " 'opciones': [{'id': 'c19', 'texto': '19. Fuerzas · 30/09'}, {'id': 'cx', 'texto': 'Para después · sin fecha'}]}))\n")

    def test_si_falta_la_clase_se_puede_elegir(self):
        c = self._correr(self.GUION_SIN_CLASE, titulo="Registrar libro")
        self.assertEqual(c.estado_actual, "avisos")
        self.assertIn("Elegir clase…", [b.cget("text").strip() for b in c.botones.values()])
        c.destroy()

    def test_sin_opciones_no_aparece_elegir_clase(self):
        c = self._correr("print('[OK] a')", titulo="Registrar libro")
        self.assertNotIn("Elegir clase…", [b.cget("text").strip() for b in c.botones.values()])
        c.destroy()

    def test_elegir_la_clase_vuelve_a_correr_solo_ese_bloque(self):
        c = self._correr(self.GUION_SIN_CLASE, titulo="Registrar libro")
        elegir = self.mod["VentanaElegirClase"](c)
        self.barra.update()
        self.assertEqual(list(elegir.combos), ["4BA|12:50-00:00|802|2026-10-06"])
        valores = list(elegir.combos["4BA|12:50-00:00|802|2026-10-06"]["values"])
        self.assertEqual(valores[0], "— no declarar este bloque —")     # por defecto no se adivina
        self.assertIn("Tu planificación no tiene una clase con esa fecha", self._textos(elegir))
        elegir._declarar()                                              # sin elegir nada: no hace nada
        self.assertIn("No elegiste ninguna clase", elegir.aviso.cget("text"))
        elegir.combos["4BA|12:50-00:00|802|2026-10-06"].current(1)      # 19. Fuerzas
        antes = [w for w in self.barra.winfo_children() if isinstance(w, self.mod["Consola"])]
        elegir._declarar()
        nuevas = [w for w in self.barra.winfo_children()
                  if isinstance(w, self.mod["Consola"]) and w not in antes]
        self.assertEqual(len(nuevas), 1)
        self.assertIn("clase elegida", nuevas[0].titulo)
        comando = nuevas[0].comando
        with open(comando[comando.index("--seleccion") + 1], encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"claves": ["4BA|12:50-00:00|802|2026-10-06"],
                                            "elecciones": {"4BA|12:50-00:00|802|2026-10-06": "c19"}})
        nuevas[0].destroy()
        c.destroy()

    def test_destinos_volver_al_por_defecto(self):
        v = self._ventana_destinos({"1": {"opciones": self.OPCIONES["opciones"], "hora": "x"}})
        v.lista.fijar("1", True)
        v._elegir_destino()
        v.combos["1"].current(0)                                     # «Volver al curso de la unidad»
        v._guardar()
        with open(self.mod["DESTINOS_JSON"], encoding="utf-8") as f:
            self.assertEqual(json.load(f), {})
        v.destroy()

    def test_destinos_sin_cambios_no_escribe(self):
        v = self._ventana_destinos({"2": self.OPCIONES})
        antes = os.path.getmtime(self.mod["DESTINOS_JSON"])
        v.lista.fijar("2", True)
        v._elegir_destino()
        v._guardar()                                                 # no tocó el desplegable
        self.assertEqual(os.path.getmtime(self.mod["DESTINOS_JSON"]), antes)
        self.assertIn("No cambiaste nada", v.aviso.cget("text"))
        v.destroy()

    def test_destinos_pide_opciones_solo_de_las_marcadas(self):
        pedidas = []
        opciones = json.dumps({"unidad": "3", "opciones": self.OPCIONES["opciones"], "error": ""})
        self.mod["comando_webclass"] = lambda *a, **k: (
            pedidas.append(a),
            [sys.executable, "-c", f"print('##PROGRESO 0/1 unidad 3'); print('##OPCIONES ' + {opciones!r}); "
                                   "print('##PROGRESO 1/1')"])[1]
        v = self._ventana_destinos()
        v.lista.fijar("3", True)
        v._elegir_destino()
        self.assertTrue(v._cargando)
        self._esperar(lambda: not v._cargando)
        self.assertEqual(pedidas[-1], ("asignar", "--opciones-destino", "3"))   # solo la marcada
        self.assertEqual(list(v.combos), ["3"])
        with open(self.mod["OPCIONES_DESTINO"], encoding="utf-8") as f:
            self.assertIn("3", json.load(f))                         # quedan guardadas
        v.destroy()

    def test_destinos_sin_marcar_no_hace_nada(self):
        v = self._ventana_destinos()
        v._elegir_destino()
        self.assertIsNone(v.proceso)
        self.assertIn("Marca al menos una unidad", v.aviso.cget("text"))
        v.destroy()

    def test_destinos_filtra_por_texto(self):
        v = self._ventana_destinos()
        v.filtro.set("7ba")
        v._refrescar_lista()
        self.assertEqual(v.lista.todas(), ["3"])
        v.destroy()

    # --------------------------------------------------------------------- tour
    def test_el_tour_recorre_todos_los_pasos_y_se_marca_visto(self):
        pasos = self.mod["TOUR_PASOS"]
        self.assertTrue(self.mod["tour_pendiente"](self.mod["TOUR"]))
        self.barra.iniciar_tour()
        tour = self.barra._tour
        self.assertIsNotNone(tour)
        self.assertFalse(self.mod["tour_pendiente"](self.mod["TOUR"]))   # no vuelve a salir solo
        for numero in range(len(pasos)):
            self.barra.update()
            self.assertEqual(len(self.barra._marcos_resalte), 4, f"paso {numero + 1}")
            self.assertIn(f"Paso {numero + 1} de {len(pasos)}", tour.etiqueta_paso.cget("text"))
            tour._siguiente()
        self.assertIsNone(self.barra._tour)
        self.assertEqual(self.barra._marcos_resalte, [])
        self.assertFalse(tour.winfo_exists())

    def test_el_tour_se_puede_saltar_y_la_barra_no_se_pliega_durante_el_tour(self):
        self.barra.iniciar_tour()
        self.barra.update()
        self.barra._plegar(forzar=True)
        self.assertTrue(self.barra.desplegada)            # el tour la mantiene abierta
        self.barra._tour._terminar()
        self.assertIsNone(self.barra._tour)
        self.barra._plegar(forzar=True)
        self.assertFalse(self.barra.desplegada)

    def test_tour_inicial_solo_si_no_se_vio(self):
        self.barra._tour_inicial()
        self.assertIsNotNone(self.barra._tour)
        self.barra._tour._terminar()
        self.barra._tour_inicial()                        # ya visto: no sale otra vez
        self.assertIsNone(self.barra._tour)

    def test_escape_pliega_sin_cerrar(self):
        b = self.barra
        b.focus_force()             # las teclas llegan a la ventana con el foco
        b.update()
        b.event_generate("<Escape>")
        b.update()
        self.assertFalse(b.desplegada)
        self.assertTrue(b.winfo_exists())


if __name__ == "__main__":
    unittest.main()
