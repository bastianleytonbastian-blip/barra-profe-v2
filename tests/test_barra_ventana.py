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
        # Botones, preferencias y posición: copias en la carpeta temporal (las pruebas nunca tocan los tuyos).
        if not hasattr(type(self), "_config_real"):
            type(self)._config_real = self.mod["CONFIG"]
        copia = os.path.join(carpeta, "herramientas.json")
        import shutil
        shutil.copy2(type(self)._config_real, copia)
        self.mod["CONFIG"] = copia
        self.mod["PREFERENCIAS"] = os.path.join(carpeta, "preferencias.json")
        self.mod["ESTADO"] = os.path.join(carpeta, "posicion.json")
        self.mod["SIN_CLASES"] = os.path.join(carpeta, "sin_clases.json")
        # Buzón del colegio: archivos en la carpeta temporal, sin GitHub y sin tocar el llavero de Windows.
        self.mod["BUZON_COLEGIO"] = os.path.join(carpeta, "colegio.json")
        self.mod["AVISOS_LEIDOS"] = os.path.join(carpeta, "avisos_leidos.json")
        self.codigo_colegio = ""
        self.publicados = []

        def sin_red(*_a, **_k):
            raise OSError("sin red en las pruebas")

        def guardar_codigo(codigo):
            self.codigo_colegio = self.mod["colegio"].normalizar_codigo(codigo)
            return self.codigo_colegio
        for nombre, falso in (("descargar", sin_red), ("es_administrador", lambda *a, **k: False),
                              ("codigo_guardado", lambda vigencia=30: self.codigo_colegio),
                              ("_leer_llavero", lambda vigencia=30: self.codigo_colegio),     # ni leer el de verdad
                              ("guardar_codigo", guardar_codigo),
                              ("publicar", lambda paquete, carpeta, **k: self.publicados.append(paquete))):
            parche = mock.patch.object(self.mod["colegio"], nombre, falso)
            parche.start()
            self.addCleanup(parche.stop)
        # Por defecto, un equipo de un solo profesor (sin PIN); las pruebas del PIN lo cambian.
        self.mod["equipo_compartido"] = lambda: False
        self.mod["RUTA_DESBLOQUEO"] = os.path.join(carpeta, "desbloqueo.json")
        if not hasattr(type(self), "_buscar_periodica_real"):
            type(self)._buscar_periodica_real = self.mod["Barra"]._buscar_periodica
        busqueda = mock.patch.object(self.mod["Barra"], "_buscar_periodica", lambda s: None)   # sin GitHub
        busqueda.start()
        self.addCleanup(busqueda.stop)
        with open(copia, encoding="utf-8-sig") as f:
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

    def _ventanas_auxiliares(self):
        """Las ventanas que antes se ubicaban suponiendo la barra a la derecha (y la de arrastrar, que se salía)."""
        buzon = os.path.join(self.carpeta, "buzon_ubicacion")
        for nivel in ("1 basico", "5 basico", "1 medio"):
            os.makedirs(os.path.join(buzon, nivel), exist_ok=True)
        self.mod["BUZON"] = buzon
        self.mod["HORARIO_SEMANA"] = os.path.join(self.carpeta, "horario.json")
        origen = os.path.join(self.carpeta, "guia.pdf")
        with open(origen, "wb") as f:
            f.write(b"%PDF")
        mes = {"nombre": "Completar mes atrasado", "pregunta": "¿Qué mes?", "opciones": "meses",
               "destino": "libro --completar-mes --mes {valor}"}
        return {"Colores": lambda: self.mod["VentanaColores"](self.barra),
                "Profesores": lambda: self.mod["VentanaDocentes"](self.barra),
                "Horario": lambda: self.mod["VentanaHorario"](self.barra),
                "Preguntar": lambda: self.mod["VentanaPreguntar"](self.barra, "Completar mes atrasado", mes),
                "Arrastrar": lambda: self.mod["VentanaSoltar"](self.barra, [origen])}

    def test_las_ventanas_quedan_dentro_del_monitor_y_al_lado_de_la_barra(self):
        for lado in ("derecha", "izquierda"):
            self.barra.lado = lado
            self.barra._colocar()
            self.barra.update()
            izq, arriba, der, abajo = self.barra._area()
            for nombre, crear in self._ventanas_auxiliares().items():
                with self.subTest(lado=lado, ventana=nombre):
                    v = crear()
                    try:
                        v.update_idletasks()
                        self.barra.update()
                        x, y = v.winfo_x(), v.winfo_y()
                        ancho, alto = v.winfo_reqwidth(), v.winfo_reqheight()
                        self.assertGreaterEqual(x, izq)
                        self.assertLessEqual(x + ancho, der, "se sale por la derecha del monitor")
                        self.assertGreaterEqual(y, arriba)
                        if alto <= abajo - arriba:
                            self.assertLessEqual(y + alto, abajo, "se sale por abajo")
                        if lado == "derecha":
                            self.assertLessEqual(x + ancho, self.barra.winfo_x(), "queda encima de la barra")
                        else:
                            self.assertGreaterEqual(x, self.barra.winfo_x() + self.barra.winfo_width(),
                                                    "queda encima de la barra")
                    finally:
                        v.destroy()

    def test_completar_mes_ofrece_los_meses_de_este_anio(self):
        import barra_utiles as u
        v = self._ventanas_auxiliares()["Preguntar"]()
        try:
            esperados = u.meses_escolares()
            self.assertEqual([o["valor"] for o in v.opciones], [m["clave"] for m in esperados])
            self.assertTrue(v.opciones[0]["texto"].endswith("(este mes)"))
            self.assertEqual(v.elegida.get(), esperados[0]["clave"], "parte marcado el mes actual")
        finally:
            v.destroy()

    def _ajustes(self, pestana=None):
        self.barra.abrir_ajustes(pestana)
        self.barra.update()
        return [w for w in self.barra.winfo_children() if isinstance(w, self.mod["VentanaAjustes"])][0]

    def test_buscar_actualizaciones_esta_en_ajustes_y_avisa_del_resultado(self):
        import actualizador
        from unittest import mock
        ajustes = self._ajustes("Actualizaciones")
        self.assertIn("Buscar actualizaciones ahora", self._textos(ajustes))
        ajustes.destroy()
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

    def test_la_cabecera_cabe_y_ningun_boton_queda_oculto(self):
        b = self.barra
        b.update()
        for boton in (b.boton_ajustes, b.boton_fijar, b.boton_cerrar):
            derecha = boton.winfo_rootx() + boton.winfo_width() - b.winfo_rootx()
            self.assertLessEqual(derecha, b.winfo_width(), f"«{boton.cget('text')}» se sale de la barra")
            self.assertGreaterEqual(boton.winfo_width(), boton.winfo_reqwidth(), f"«{boton.cget('text')}» recortado")
        # La cabecera no se desplaza: queda arriba aunque el resto se mueva.
        b._desplazar(10 ** 6)
        b.update()
        self.assertEqual(b.cabecera.winfo_rooty(), b.winfo_rooty())
        b._desplazar(-10 ** 6)

    def test_ajustes_reune_lo_que_antes_estaba_en_el_pie(self):
        ajustes = self._ajustes()
        self.assertEqual(list(ajustes.pestanas.pestanas),
                         ["Apariencia", "Botones", "Comportamiento", "Windows y sonido", "Profesor", "Respaldo",
                          "Actualizaciones", "Ayuda"])
        ajustes.pestanas.elegir("Ayuda")
        textos = self._textos(ajustes)
        for esperado in ("Ver el recorrido", "Ver el registro", "Abrir la carpeta"):
            self.assertIn(esperado, textos)
        self.barra.abrir_ajustes("Apariencia")              # una sola ventana de ajustes
        self.assertEqual(len([w for w in self.barra.winfo_children()
                              if isinstance(w, self.mod["VentanaAjustes"])]), 1)
        self.assertEqual(ajustes.pestanas.actual, "Apariencia")
        ajustes.destroy()

    def test_los_grupos_se_pliegan_y_solo_favoritos_parte_abierto(self):
        b = self.barra
        grupos = b.grupos_ui
        self.assertEqual(next(iter(grupos)), self.mod["GRUPO_FAVORITOS"])
        abiertos = [g for g, i in grupos.items() if i["abierto"]]
        self.assertEqual(abiertos, [self.mod["GRUPO_FAVORITOS"]], "solo los favoritos parten abiertos")
        cerrado = next(g for g, i in grupos.items() if not i["abierto"])
        self.assertFalse(grupos[cerrado]["armado"], "un grupo cerrado no arma sus botones (abre más rápido)")
        b.alternar_grupo(cerrado)
        self.assertTrue(grupos[cerrado]["armado"])
        self.assertIn(cerrado, self.mod["leer_preferencias"]()["grupos_abiertos"], "se recuerda abierto")
        b.alternar_grupo(cerrado)
        self.assertNotIn(cerrado, self.mod["leer_preferencias"]()["grupos_abiertos"])

    def test_favoritos_se_agregan_y_quitan_con_clic_derecho(self):
        b = self.barra
        favoritos = [h["nombre"] for h in b.grupos_ui[self.mod["GRUPO_FAVORITOS"]]["botones"]]
        otro = next(h for h in b.herramientas if h.get("nombre") not in favoritos and not h.get("oculto"))
        b.alternar_favorito(otro)
        nuevos = [h["nombre"] for h in b.grupos_ui[self.mod["GRUPO_FAVORITOS"]]["botones"]]
        self.assertIn(otro["nombre"], nuevos)
        self.assertEqual(set(nuevos) - {otro["nombre"]}, set(favoritos), "los demás favoritos siguen")
        with open(self.mod["CONFIG"], encoding="utf-8-sig") as f:
            guardados = {x["nombre"] for x in json.load(f) if x.get("favorito")}
        self.assertEqual(guardados, set(nuevos), "queda escrito en los botones del docente")
        b.alternar_favorito(otro)
        self.assertNotIn(otro["nombre"], [h["nombre"] for h in b.grupos_ui[self.mod["GRUPO_FAVORITOS"]]["botones"]])

    def test_la_tarjeta_hoy_plegada_muestra_lo_justo(self):
        import datetime
        b = self.barra
        estado = {"fecha": datetime.date.today().strftime("%d/%m/%Y"), "bloques": [{}],
                  "sin_firmar": [{"curso": "6BB", "hora": "09:40-11:10"}],
                  "atrasados": [{"fecha": "13/10/2026"}],
                  "jefatura": {"curso": "5BA", "ausentes": ["Diaz", "Espinoza"], "atrasadas": []}}
        ruta = os.path.join(self.carpeta, "estado_firmas.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(estado, f)
        self.mod["ESTADO_FIRMAS"] = ruta
        b._refrescar_firmas()
        self.assertFalse(b.hoy_abierta)
        self.assertEqual(b.jefatura_texto.cget("text"), "5BA · 2 ausentes", "plegada: cuántos, sin nombres")
        self.assertNotIn("\n", b.libro_texto.cget("text"), "plegada: una línea del libro")
        b.alternar_hoy()
        self.assertIn("Diaz, Espinoza", b.jefatura_texto.cget("text"))
        self.assertTrue(self.mod["leer_preferencias"]()["hoy_abierta"])
        b.alternar_hoy()

    def test_ya_no_hay_notas_para_el_asistente_y_el_atajo_solo_abre_la_barra(self):
        b = self.barra
        self.assertNotIn("NOTAS PARA EL ASISTENTE", self._textos(b))
        self.assertFalse(hasattr(b, "alternar_notas"))
        self.assertNotIn("notas", [p["id"] for p in self.mod["TOUR_PASOS"]])
        b._plegar(forzar=True)
        b.senales.put("anotar")
        b._atender_senal()
        self.assertTrue(b.desplegada)

    def test_un_clic_en_el_libro_o_en_los_ausentes_despliega_el_detalle(self):
        import datetime
        b = self.barra
        estado = {"fecha": datetime.date.today().strftime("%d/%m/%Y"), "bloques": [{}],
                  "sin_firmar": [{"curso": "6BB", "hora": "09:40-11:10"}],
                  "jefatura": {"curso": "5BA", "ausentes": ["Diaz", "Espinoza"], "atrasadas": []}}
        ruta = os.path.join(self.carpeta, "estado_firmas.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(estado, f)
        self.mod["ESTADO_FIRMAS"] = ruta
        b._refrescar_firmas()
        if b.hoy_abierta:
            b.alternar_hoy()
        for etiqueta in (b.libro_texto, b.jefatura_texto):
            etiqueta.event_generate("<Button-1>")
            b.update()
            self.assertTrue(b.hoy_abierta, "un clic despliega")
            self.assertIn("Diaz, Espinoza", b.jefatura_texto.cget("text"))
            self.assertTrue(b.libro_enlace.winfo_manager(), "abierta, el libro en Webclass queda a un clic")
            etiqueta.event_generate("<Button-1>")
            b.update()
            self.assertFalse(b.hoy_abierta, "otro clic lo pliega")
            self.assertFalse(b.libro_enlace.winfo_manager())

    def test_los_favoritos_de_fabrica_traen_escala_de_notas_y_no_abrir_y_firmar(self):
        botones = [{"nombre": n} for n in ("Abrir y firmar", "Escala de notas", "Registrar libro", "Asignar clases",
                                          "Planificar", "Subir recursos", "Mi horario")]
        nombres = [b["nombre"] for b in self.mod["Barra"]._favoritos(botones)]
        self.assertEqual(nombres, ["Registrar libro", "Asignar clases", "Planificar", "Subir recursos", "Escala de notas"])
        elegidos = [{"nombre": "Abrir y firmar", "favorito": True}, {"nombre": "Escala de notas", "favorito": False}]
        self.assertEqual([b["nombre"] for b in self.mod["Barra"]._favoritos(elegidos)], ["Abrir y firmar"],
                         "lo que el profesor eligió se respeta")

    def test_el_aviso_de_version_nueva_aparece_bajo_la_cabecera(self):
        b = self.barra
        self.assertFalse(b.aviso_actualizacion.winfo_manager())
        b._mostrar_actualizacion({"version": "9.9.9", "notas": ""})
        b.update()
        self.assertTrue(b.aviso_actualizacion.winfo_manager())
        self.assertIn("9.9.9", b.aviso_actualizacion.cget("text"))
        self.assertGreater(b.aviso_actualizacion.winfo_rooty(), b.cabecera.winfo_rooty())
        b._pintar_aviso_actualizacion("")
        self.assertFalse(b.aviso_actualizacion.winfo_manager())

    def test_busca_actualizaciones_al_abrir_y_cada_6_horas(self):
        from unittest import mock
        programado, hilos = [], []

        class HiloFalso:                       # no sale a GitHub: solo se anota qué se iba a buscar
            def __init__(self, target=None, args=(), daemon=None):
                hilos.append(args)

            def start(self):
                pass
        with mock.patch.object(self.mod["threading"], "Thread", HiloFalso), \
                mock.patch.object(self.barra, "after", lambda ms, f: programado.append(ms)):
            type(self)._buscar_periodica_real(self.barra)
        self.assertEqual(len(hilos), 1, "busca al tiro")
        self.assertEqual(programado, [6 * 3600 * 1000], "y vuelve a mirar en 6 horas")

    def test_soltar_ordena_los_niveles_y_sube_ahora_solo_lo_soltado(self):
        buzon = os.path.join(self.carpeta, "buzon_niveles")
        for nivel in ("1 medio", "2 basico", "5 basico", "5 basico Orientacion", "8 basico", "1 basico"):
            os.makedirs(os.path.join(buzon, nivel))
        open(os.path.join(buzon, "8 basico", "otro.pdf"), "w").close()     # algo que ya esperaba en el buzón
        self.mod["BUZON"] = buzon
        self.mod["perfil_de_trabajo"] = lambda: {"curso_niveles": {"5BA": 25, "8BA": 28}}
        origen = os.path.join(self.carpeta, "guia.pdf")
        with open(origen, "wb") as f:
            f.write(b"%PDF")
        v = self.mod["VentanaSoltar"](self.barra, [origen])
        self.assertEqual(v.propias, ["5 basico", "5 basico Orientacion", "8 basico"])
        self.assertEqual(v.otras, ["1 basico", "2 basico", "1 medio"])
        self.assertIn("5° Básico · Orientación", self._textos(v))
        self.assertNotIn("1° Medio", self._textos(v), "los otros niveles parten plegados")
        abiertos = []
        self.mod["abrir"], original = (lambda h, m: abiertos.append(h)), self.mod["abrir"]
        try:
            v._copiar("5 basico")
            self.assertIn("Subir ahora", self._textos(v))
            v._subir_ahora()
        finally:
            self.mod["abrir"] = original
        claves, todas = abiertos[0]["_seleccion"]
        self.assertTrue(abiertos[0]["_confirmado"])
        self.assertEqual(claves, ["5 basico/guia.pdf"])
        self.assertEqual(sorted(todas), ["5 basico/guia.pdf", "8 basico/otro.pdf"], "lo demás del buzón no se sube")

    # ------------------------------------------------------- fase 2: ajustes sin tocar archivos
    GLOBALES_DOCENTE = ("DOCENTES", "PERFIL", "NOMBRE_COMPLETO", "NOMBRE", "_sufijo", "RUTA_MENSAJES",
                        "ESTADO_FIRMAS", "TEMA", "HORARIO_SEMANA", "TAREAS", "EJECUCIONES", "TOUR", "PREFERENCIAS",
                        "PALETA", "ESCALA_LETRA", "ANCHO")

    def _guardar_globales(self):
        """Cambiar de docente o de apariencia toca variables del programa: se dejan como estaban al terminar."""
        antes = {k: self.mod[k] for k in self.GLOBALES_DOCENTE}
        antes.update({k: v for k, v in self.mod.items() if k.startswith("COLOR_")})
        self.addCleanup(lambda: self.mod.update(antes))

    def _esperar_ventana(self, clase):
        self._esperar(lambda: any(isinstance(w, self.mod[clase]) for w in self.barra.winfo_children()), 3)
        return [w for w in self.barra.winfo_children() if isinstance(w, self.mod[clase])]

    def test_cambiar_la_letra_se_aplica_sin_reabrir_la_barra(self):
        self._guardar_globales()
        self.mod["TEMA"] = os.path.join(self.carpeta, "tema.json")
        reabiertas = []
        self.enterContext(mock.patch.dict(self.mod, {"reabrir_barra": lambda: reabiertas.append(1)}))
        b = self.barra
        antes = abs(int(b.fuente.cget("size")))
        ajustes = self._ajustes("Apariencia")
        self.mod["guardar_apariencia"](b, "Apariencia", letra="grande")
        self.assertEqual(reabiertas, [], "ya no se cierra y se vuelve a abrir")
        self.assertTrue(b.winfo_exists())
        self.assertGreater(abs(int(b.fuente.cget("size"))), antes)
        self.assertFalse(ajustes.winfo_exists(), "la ventana con la letra de antes se cierra…")
        nuevas = self._esperar_ventana("VentanaAjustes")
        self.assertEqual([v.pestanas.actual for v in nuevas], ["Apariencia"], "…y vuelve abierta en la misma pestaña")
        with open(self.mod["TEMA"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["letra"], "grande")

    def test_cambiar_el_color_no_reabre_la_barra(self):
        self._guardar_globales()
        self.mod["TEMA"] = os.path.join(self.carpeta, "tema.json")
        reabiertas = []
        self.enterContext(mock.patch.dict(self.mod, {"reabrir_barra": lambda: reabiertas.append(1)}))
        self.mod["guardar_color"]("claro", self.barra)
        self.assertEqual(reabiertas, [])
        self.assertEqual(self.barra.cget("bg"), self.mod["PALETAS"]["claro"]["fondo"])
        self.assertEqual(self.barra.cabecera.cget("bg"), self.mod["PALETAS"]["claro"]["fondo"])

    def test_cambiar_de_profesor_no_reabre_la_barra(self):
        self._guardar_globales()
        datos = os.path.join(self.carpeta, "datos")
        perfiles = os.path.join(self.carpeta, "perfiles")
        os.makedirs(datos)
        os.makedirs(perfiles)
        for clave, nombre in (("ana", "Ana Pérez"), ("beto", "Beto Soto")):
            with open(os.path.join(perfiles, clave + ".json"), "w", encoding="utf-8") as f:
                json.dump({"nombre": nombre}, f)
        self.enterContext(mock.patch.object(self.mod["rutas"], "dato", lambda nombre: os.path.join(datos, nombre)))
        self.enterContext(mock.patch.object(self.mod["rutas"], "PERFILES", perfiles))
        self.barra.cambiar_docente("beto")
        self.assertTrue(self.barra.winfo_exists())
        self.assertEqual(self.mod["PERFIL"], "beto")
        self.assertEqual(self.barra.saludo.cget("text"), "Beto")
        self.assertEqual(self.mod["EJECUCIONES"], os.path.join(datos, "ultimas_ejecuciones_beto.json"))

    def test_no_cambia_de_profesor_mientras_algo_corre(self):
        avisos = []
        self.enterContext(mock.patch.object(self.mod["messagebox"], "showinfo", lambda *a, **k: avisos.append(a)))
        self.enterContext(mock.patch.object(self.mod["rutas"], "fijar_perfil_activo", lambda c: avisos.append(c)))
        self.barra.corriendo["Asignar clases"] = mock.Mock()
        try:
            self.mod["elegir_docente"]("otro", self.barra)
        finally:
            self.barra.corriendo.clear()
        self.assertEqual(len(avisos), 1)
        self.assertIn("Espera a que termine", avisos[0][1])

    def _editor(self):
        ajustes = self._ajustes("Botones")
        editor = [w for w in ajustes.pestanas.panel.winfo_children() if isinstance(w, self.mod["EditorBotones"])][0]
        return ajustes, editor

    def _visibles_en_la_barra(self):
        return [h["nombre"] for g in self.barra.grupos_ui.values() for h in g["botones"]]

    def test_editor_oculta_ordena_y_marca_favoritos(self):
        ajustes, editor = self._editor()
        grupo = [h["nombre"] for h in editor.botones if h.get("grupo") == "Correo y nube"]
        if len(grupo) < 2:
            self.skipTest("estos botones no traen el grupo «Correo y nube»")
        editor._alternar_visible(grupo[0])
        with open(self.mod["CONFIG"], encoding="utf-8-sig") as f:
            self.assertTrue(next(x for x in json.load(f) if x["nombre"] == grupo[0])["oculto"])
        self.assertNotIn(grupo[0], self._visibles_en_la_barra(), "oculto: ya no está en la barra")
        editor._alternar_visible(grupo[0])
        self.assertIn(grupo[0], self._visibles_en_la_barra())
        editor._mover(grupo[1], -1)
        self.assertEqual([h["nombre"] for h in editor.botones if h.get("grupo") == "Correo y nube"][:2],
                         [grupo[1], grupo[0]])
        editor._alternar_favorito(grupo[0])
        self.assertIn(grupo[0], [h["nombre"] for h in self.barra.grupos_ui[self.mod["GRUPO_FAVORITOS"]]["botones"]])
        ajustes.destroy()

    def test_editor_agrega_edita_y_borra_un_boton_propio(self):
        ajustes, editor = self._editor()
        nuevo = {"nombre": "Mi sitio", "icono": "🌐", "grupo": "Mis enlaces", "tipo": "url",
                 "destino": "https://ejemplo.cl", "ayuda": ""}
        self.assertEqual(editor.guardar_boton(None, dict(nuevo)), "")
        self.assertIn("Mi sitio", self._visibles_en_la_barra() + [h["nombre"] for h in self.barra.herramientas])
        self.assertIn("ya hay", editor.guardar_boton(None, dict(nuevo)).lower())
        self.assertEqual(editor.guardar_boton("Mi sitio", {**nuevo, "nombre": "Mi sitio 2"}), "")
        self.assertIn("Mi sitio 2", [h["nombre"] for h in self.barra.herramientas])
        with mock.patch.object(self.mod["messagebox"], "askyesno", lambda *a, **k: True):
            editor._borrar("Mi sitio 2")
        self.assertNotIn("Mi sitio 2", [h["nombre"] for h in self.barra.herramientas])
        ajustes.destroy()

    def test_la_ventana_de_boton_valida_la_direccion(self):
        ajustes, editor = self._editor()
        v = self.mod["VentanaBoton"](editor, None)
        v.nombre.set("Sitio de prueba")
        v.destino.set("ejemplo.cl")
        v._guardar()
        self.assertIn("https://", v.aviso.cget("text"))
        v.destino.set("https://ejemplo.cl")
        v._guardar()
        self.assertFalse(v.winfo_exists())
        self.assertIn("Sitio de prueba", [h["nombre"] for h in self.barra.herramientas])
        ajustes.destroy()

    def test_configurar_una_cuenta_sin_consola(self):
        import types
        self._guardar_globales()
        llamadas = {}
        falso = types.ModuleType("configurar")

        def preparar(rut, clave):
            llamadas["preparar"] = (rut, clave)
            return {"rut": rut, "curso_ids": {"5BA": 1, "5BB": 2}, "unidades": [1, 2, 3]}

        def guardar(preparada, clave, nombre, jefatura):
            llamadas["guardar"] = (clave, nombre, jefatura)
            return "ana"
        falso.preparar_cuenta, falso.guardar_cuenta = preparar, guardar
        elegidos = []
        self.enterContext(mock.patch.dict(sys.modules, {"configurar": falso}))
        self.enterContext(mock.patch.dict(self.mod, {"elegir_docente": lambda c, b=None: elegidos.append(c),
                                                     "docentes_registrados": lambda: [("ana", "Ana")]}))
        v = self.mod["VentanaCuenta"](self.barra)
        v.rut.set("12.345.678-9")
        v.clave.set("x")
        v.nombre.set("Ana Pérez")
        v._conectar()
        self.assertIn("RUT", v.aviso.cget("text"), "con puntos no se conecta")
        self.assertNotIn("preparar", llamadas)
        v.rut.set("12345678-9")
        v._conectar()
        self._esperar(lambda: v.preparada is not None, 5)
        self.assertEqual(llamadas["preparar"], ("12345678-9", "x"))
        self.assertIn("2 cursos", self._textos(v))
        v.jefatura.set("5BB")
        with mock.patch.object(self.mod["messagebox"], "askyesno", lambda *a, **k: True):
            v._guardar()
        self.assertEqual(llamadas["guardar"], ("x", "Ana Pérez", "5BB"))
        self.assertEqual(elegidos, ["ana"])

    def test_el_respaldo_no_lleva_secretos(self):
        mapa = self.mod["archivos_de_respaldo"]()
        for nombre, ruta in mapa.items():
            self.assertNotIn("claves", nombre + ruta, "las claves de IA no van al respaldo")
            self.assertNotIn("perfiles", ruta.replace("\\", "/"), "el perfil de Webclass (con el RUT) tampoco")
        for esperado in ("personal/herramientas.json", "datos/apariencia.json", "datos/lista.json"):
            self.assertIn(esperado, mapa)

    def test_windows_y_sonido_ofrece_reparar_los_accesos_rotos(self):
        import barra_utiles as u
        actual = os.path.join(self.mod["CARPETA"], "barra_profe.pyw")
        falsos = [{"ruta": os.path.join(self.carpeta, "Anotar - Barra Profe.lnk"), "carpeta": "escritorio",
                   "destino": "pythonw.exe", "argumentos": '"C:\\\\viejo\\\\barra_profe.pyw"', "atajo": "Alt+Ctrl+A"}]
        escritos = []
        self.enterContext(mock.patch.object(u, "leer_accesos", lambda: falsos))
        self.enterContext(mock.patch.object(u, "escribir_acceso", lambda ruta, destino, argumentos, carpeta, atajo="":
                                            escritos.append((ruta, argumentos, atajo))))
        ajustes = self._ajustes("Windows y sonido")
        self._esperar(lambda: "Repararlos" in self._textos(ajustes), 5)
        self.assertIn("Hay 1 acceso", self._textos(ajustes))
        ajustes._reparar(u.accesos_de_la_barra(falsos))
        self._esperar(lambda: escritos, 5)
        self.assertEqual(escritos[0][0], falsos[0]["ruta"])
        self.assertIn(actual, escritos[0][1], "ahora abre esta barra")
        self.assertEqual(escritos[0][2], "CTRL+ALT+A", "y conserva el atajo que tenía")
        ajustes.destroy()

    def test_la_demora_para_esconderse_se_puede_elegir(self):
        b = self.barra
        self.assertEqual(b._ciclos_para_plegar(), self.mod["CICLOS_FUERA_PARA_PLEGAR"])
        b.preferencias = {"demora_plegado": 2.0}
        self.assertEqual(b._ciclos_para_plegar(), 10)
        b.preferencias = {"demora_plegado": "basura"}
        self.assertEqual(b._ciclos_para_plegar(), self.mod["CICLOS_FUERA_PARA_PLEGAR"])

    def test_el_planificador_puede_quedar_listo_al_abrir_la_barra(self):
        lanzados = []
        with mock.patch.object(self.mod["subprocess"], "Popen", lambda args, **_k: lanzados.append(list(args))):
            ajustes = self._ajustes("Comportamiento")
            self.assertIn("Dejarlo listo al abrir la barra", self._textos(ajustes))
            ajustes.var_plan_listo.set(True)
            ajustes._alternar_planificador_listo()
            self.assertTrue(self.mod["leer_preferencias"]()["planificador_listo"])
            ajustes.var_plan_listo.set(False)
            ajustes._alternar_planificador_listo()
            self.assertFalse(self.mod["leer_preferencias"]()["planificador_listo"])
            ajustes.destroy()
        preparados = [a for a in lanzados if "--solo-servidor" in a]
        self.assertEqual(len(preparados), 1, "al marcarlo se deja listo al tiro; al quitarlo no se lanza nada")
        self.assertEqual(preparados[0][1:], [self.mod["LANZADOR_PLANIFICADOR"], "--solo-servidor"])

    # ── Fase 5: para cualquier docente (sin asistente personal) ──
    def _horario_semana(self, bloques, generado=None):
        import datetime
        ruta = os.path.join(self.carpeta, "horario_semana.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"generado": generado or datetime.date.today().strftime("%d/%m/%Y 08:00"), "bloques": bloques}, f)
        return ruta

    def test_sin_asistente_ahora_y_luego_salen_de_mi_horario_de_webclass(self):
        import datetime
        dia = datetime.date.today().weekday()
        ruta = self._horario_semana([{"dia": dia, "inicio": "00:00", "fin": "23:59", "curso": "5BA",
                                      "asignatura": "Ciencias Naturales"}])
        with mock.patch.dict(self.mod, {"HORARIO": os.path.join(self.carpeta, "sin_asistente.json"), "HORARIO_SEMANA": ruta}):
            self.barra._refrescar_agenda()
            self.assertEqual(self.barra.ahora_texto.cget("text"), "Ahora · 5BA · Ciencias · hasta 23:59")
            os.remove(ruta)
            self.barra._refrescar_agenda()
            self.assertEqual((self.barra.ahora_texto.cget("text"), self.barra.luego_texto.cget("text")), ("", ""),
                             "sin ningún horario no se inventa «Hoy no hay clases»")

    def test_sin_asistente_lee_mi_horario_solo_si_falta_y_una_vez(self):
        lanzados = []
        falta = os.path.join(self.carpeta, "nunca_leido.json")

        def comando(*partes, **_k):
            lanzados.append(partes)
            return [sys.executable, "-c", "pass"]
        with mock.patch.dict(self.mod, {"HORARIO": os.path.join(self.carpeta, "sin_asistente.json"), "HORARIO_SEMANA": falta,
                                        "PERFIL": "ana", "comando_webclass": comando}):
            self.barra._horario_pedido = False
            self.barra._vigilar_horario()
            self.barra._vigilar_horario()
            self.assertEqual(lanzados, [("horario", "--salida", falta)], "una sola vez por sesión")
            lanzados.clear()
            self.barra._horario_pedido = False
            self.mod["HORARIO_SEMANA"] = self._horario_semana([{"dia": 0, "inicio": "08:00", "fin": "09:00", "curso": "5BA"}])
            self.barra._vigilar_horario()
            self.assertEqual(lanzados, [], "uno de esta semana no se vuelve a leer")

    # ── PIN de cada profesor (equipos compartidos) ──
    def _compartido(self):
        """Equipo con varios profesores mientras dure la prueba."""
        parche = mock.patch.dict(self.mod, {"equipo_compartido": lambda: True})
        parche.start()
        self.addCleanup(parche.stop)

    def _ventana_pin(self):
        self.barra.update()
        abiertas = [w for w in self.barra.winfo_children() if isinstance(w, self.mod["VentanaPin"])]
        return abiertas[-1] if abiertas else None

    def _esperar_que(self, condicion, segundos=5):
        import time
        fin = time.time() + segundos
        while time.time() < fin and not condicion():
            self.barra.update()
            time.sleep(0.05)
        self.assertTrue(condicion())

    def test_parte_bloqueada_solo_en_un_equipo_compartido(self):
        self.assertFalse(self.mod["debe_partir_bloqueada"](), "un solo profesor: sin PIN")
        self._compartido()
        self.assertTrue(self.mod["debe_partir_bloqueada"]())
        self.mod["marcar_desbloqueo"](self.mod["RUTA_DESBLOQUEO"], self.mod["PERFIL"])
        self.assertFalse(self.mod["debe_partir_bloqueada"](), "se reabrió sola recién desbloqueada")
        self.assertTrue(self.mod["debe_partir_bloqueada"](), "eso sirve una sola vez")

    def test_bloqueada_no_deja_usar_nada_hasta_escribir_el_pin(self):
        self._compartido()
        b, perfil = self.barra, self.mod["PERFIL"]
        self.mod["guardar_pin"](self.mod["ruta_pin"](self.carpeta, perfil), "2468")
        b.bloquear()
        b.update()
        self.assertTrue(b.bloqueada)
        self.assertEqual(b.velo.winfo_manager(), "place", "un velo tapa los botones")
        self.assertIn("escribe tu PIN", self._textos(b))
        with mock.patch.object(self.mod["webbrowser"], "open") as navegador:
            self.mod["abrir"]({"nombre": "Una página", "tipo": "url", "destino": "https://example.com"}, b)
        navegador.assert_not_called()
        b.abrir_ajustes()
        self.assertFalse([w for w in b.winfo_children() if isinstance(w, self.mod["VentanaAjustes"])])
        ventana = self._ventana_pin()
        self.assertIsNotNone(ventana, "en vez de abrir el botón, pide el PIN")
        ventana.campo.insert(0, "1111")
        ventana._revisar_pin()
        self.assertTrue(b.bloqueada)
        self.assertIn("incorrecto", ventana.aviso.cget("text"))
        self.assertEqual(ventana.campo.get(), "", "el PIN equivocado se borra")
        ventana.campo.insert(0, "2468")
        ventana._revisar_pin()
        b.update()
        self.assertFalse(b.bloqueada)
        self.assertIsNone(b.velo)
        self.assertIsNone(self._ventana_pin())
        self.assertTrue(self.mod["DESBLOQUEO"]["activo"])

    def test_el_campo_del_pin_solo_acepta_4_numeros(self):
        self._compartido()
        self.mod["guardar_pin"](self.mod["ruta_pin"](self.carpeta, self.mod["PERFIL"]), "2468")
        self.barra.bloquear()
        self.barra.pedir_pin()
        ventana = self._ventana_pin()
        for tecla in "12a456":
            ventana.campo.insert("end", tecla)
        self.assertEqual(ventana.campo.get(), "1245", "las letras y el quinto número no entran")
        ventana.destroy()

    def test_sin_pin_entra_con_su_contrasena_de_webclass_y_crea_uno(self):
        import configurar
        self._compartido()
        b, perfil = self.barra, self.mod["PERFIL"]
        if not self.mod["leer_json"](os.path.join(self.mod["rutas"].PERFILES, f"{perfil}.json")).get("rut"):
            self.skipTest("el perfil activo de este equipo no tiene RUT")
        b.bloquear()
        b.pedir_pin()
        ventana = self._ventana_pin()
        self.assertIn("contraseña de Webclass", ventana.subtitulo.cget("text"))
        with mock.patch.object(configurar, "verificar_contrasena") as verificar:
            ventana.contrasena.set("secreta")
            ventana._revisar_webclass()
            self._esperar_que(lambda: hasattr(ventana, "nuevo"))
        self.assertEqual(verificar.call_args.args[1], "secreta")
        self.assertEqual(ventana.contrasena.get(), "", "la contraseña no queda en la ventana")
        ventana.nuevo.insert(0, "1357")
        ventana.repetido.insert(0, "1350")
        ventana._guardar()
        self.assertIn("no son iguales", ventana.aviso.cget("text"))
        ventana.repetido.insert(0, "1357")
        ventana._guardar()
        b.update()
        self.assertFalse(b.bloqueada)
        self.assertTrue(self.mod["pin_correcto"](self.mod["ruta_pin"](self.carpeta, perfil), "1357"))

    def test_si_olvida_el_pin_lo_reemplaza_entrando_con_webclass(self):
        import configurar
        self._compartido()
        b, perfil = self.barra, self.mod["PERFIL"]
        ruta = self.mod["ruta_pin"](self.carpeta, perfil)
        self.mod["guardar_pin"](ruta, "2468")
        if not self.mod["leer_json"](os.path.join(self.mod["rutas"].PERFILES, f"{perfil}.json")).get("rut"):
            self.skipTest("el perfil activo de este equipo no tiene RUT")
        b.bloquear()
        b.pedir_pin()
        ventana = self._ventana_pin()
        ventana._paso_webclass("Entra con tu contraseña de Webclass y crea un PIN nuevo.")
        with mock.patch.object(configurar, "verificar_contrasena", side_effect=ValueError("Esa no es tu contraseña de Webclass.")):
            ventana.contrasena.set("mala")
            ventana._revisar_webclass()
            self._esperar_que(lambda: "no es tu contraseña" in ventana.aviso.cget("text"))
        self.assertFalse(hasattr(ventana, "nuevo"), "con la contraseña equivocada no se crea otro PIN")
        with mock.patch.object(configurar, "verificar_contrasena"):
            ventana.contrasena.set("buena")
            ventana._revisar_webclass()
            self._esperar_que(lambda: hasattr(ventana, "nuevo"))
        ventana.nuevo.insert(0, "9753")
        ventana.repetido.insert(0, "9753")
        ventana._guardar()
        self.assertFalse(self.mod["pin_correcto"](ruta, "2468"), "el PIN olvidado deja de servir")
        self.assertTrue(self.mod["pin_correcto"](ruta, "9753"))
        self.assertFalse(b.bloqueada)

    def test_cambiar_de_profesor_pide_el_pin_del_otro(self):
        import tempfile
        self._compartido()
        perfiles = tempfile.mkdtemp()
        with open(os.path.join(perfiles, "otra.json"), "w", encoding="utf-8") as f:
            json.dump({"nombre": "Otra Profesora", "rut": "11111111-1"}, f)
        self.mod["guardar_pin"](self.mod["ruta_pin"](self.carpeta, "otra"), "8642")
        cambios = []
        with mock.patch.object(self.mod["rutas"], "PERFILES", perfiles), \
                mock.patch.dict(self.mod, {"elegir_docente": lambda clave, barra=None: cambios.append(clave)}):
            self.mod["entrar_como_docente"]("otra", self.barra)
            ventana = self._ventana_pin()
            self.assertEqual(ventana.etiqueta_titulo.cget("text"), "Otra Profesora")
            self.assertEqual(cambios, [], "sin el PIN no se cambia")
            ventana.campo.insert(0, "8642")
            ventana._revisar_pin()
        self.assertEqual(cambios, ["otra"])

    def test_la_x_ofrece_bloquear_al_irse(self):
        self._compartido()
        ventana = self.mod["VentanaCerrar"](self.barra)
        self.barra.update()
        self.assertIn("Bloquear y esconder", self._textos(ventana))
        ventana._bloquear()
        self.assertTrue(self.barra.bloqueada)
        self.assertFalse(self.barra.desplegada)
        self.barra.fijada = True
        self.barra._desplegar(tomar_foco=False)

    def test_el_horario_muestra_la_asignatura_de_cada_bloque(self):
        ruta = self._horario_semana([
            {"dia": 0, "inicio": "08:00", "fin": "09:30", "curso": "5BA", "asignatura": "Ciencias Naturales"},
            {"dia": 1, "inicio": "08:00", "fin": "09:30", "curso": "5BA", "asignatura": "Orientación"},
            {"dia": 2, "inicio": "10:00", "fin": "11:30", "curso": "6BB", "asignatura": "Música"}])
        with mock.patch.dict(self.mod, {"HORARIO_SEMANA": ruta}):
            ventana = self.mod["VentanaHorario"](self.barra)
            self.barra.update()
            textos = self._textos(ventana)
            ventana.destroy()
        for esperado in ("5BA\nCiencias", "5BA\nOrientación", "6BB\nMúsica"):
            self.assertIn(esperado, textos)

    def test_mis_registros_abre_en_la_pestana_del_boton_y_filtra(self):
        archivos = {
            "Libro": "fecha_clase;curso;hora;asignatura;clase;estado;firma\n01/10/2026;5BA;08:00;Ciencias;Clase 1;declarado;firmado\n"
                     "02/10/2026;5BB;08:00;Ciencias;;PENDIENTE: sin clase;sin firmar\n03/10/2026;5BA;08:00;Ciencias;Clase 3;declarado;\n",
            "Subidas": "fecha;archivo;carpeta;id_recurso;estado;docente\n01/10/2026 10:00;a.pdf;5 basico;1;subido;Ana Pérez\n"
                       "02/10/2026 10:00;b.pdf;5 basico;2;subido;Otra Persona\n03/10/2026 10:00;c.pdf;6 basico;3;subido;\n",
            "Tareas": "fecha_asignacion,unidad,idunidad,curso,idclase,clase,fecha_clase,alumnas_asignadas\n",
        }
        rutas_csv = {}
        for tipo, texto in archivos.items():
            rutas_csv[tipo] = os.path.join(self.carpeta, f"{tipo}.csv")
            with open(rutas_csv[tipo], "w", encoding="utf-8-sig", newline="") as f:
                f.write(texto)
        with mock.patch.dict(self.mod, {"ruta_de_registro": rutas_csv.__getitem__, "NOMBRE_COMPLETO": "Ana Pérez"}), \
                mock.patch.object(self.mod["os"], "startfile", create=True) as abrir_archivo:
            self.mod["abrir"]({"nombre": "Registro de subidas", "tipo": "programa",
                               "destino": "%BUZON%\\registro_subidas.csv"}, self.barra)
            self.barra.update()
            ventana = [w for w in self.barra.winfo_children() if isinstance(w, self.mod["VentanaRegistros"])][0]
            self.assertEqual(ventana.pestanas.actual, "Subidas", "el botón de siempre abre su pestaña")
            ventana._elegir_periodo("todo")
            self.assertEqual(len(ventana.tabla.get_children()), 2, "la subida de otro docente del PC no se ve")
            ventana.pestanas.elegir("Libro")
            self.assertEqual(len(ventana.tabla.get_children()), 3)
            ventana._filtrar("curso", "5BA")
            self.assertEqual(len(ventana.tabla.get_children()), 2)
            ventana._filtrar("estado", "pendiente")
            self.assertEqual(len(ventana.tabla.get_children()), 0)
            ventana.pestanas.elegir("Tareas")
            self.assertIn("Todavía no hay nada anotado", ventana.resumen.cget("text"))
            abrir_archivo.assert_not_called()
            ventana.pestanas.elegir("Libro")
            ventana._abrir_excel()
            abrir_archivo.assert_called_once_with(rutas_csv["Libro"])
            ventana.destroy()

    def test_el_aviso_dura_lo_elegido(self):
        capturado = {}
        self.barra.preferencias = {"aviso_segundos": 10}
        with mock.patch.dict(self.mod, {"Aviso": lambda *a, **k: capturado.update(k)}):
            self.barra._avisar(mock.Mock(titulo="Asignar clases"), "completado", {"resumen": "listo"})
        self.assertEqual(capturado["segundos"], 10)

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

    def _pedir_cierre(self):
        self.barra.boton_cerrar.event_generate("<ButtonPress-1>", x=3, y=3)
        self.barra.update()
        dialogos = [w for w in self.barra.winfo_children() if isinstance(w, self.mod["VentanaCerrar"])]
        self.assertEqual(len(dialogos), 1, "la ✕ pregunta antes")
        return dialogos[0]

    def test_la_x_pregunta_y_cerrar_cierra_la_barra(self):
        self._pedir_cierre()._cerrar()
        with self.assertRaises(tk.TclError):        # ventana destruida
            self.barra.winfo_exists()

    def test_la_x_puede_solo_esconderla(self):
        self._pedir_cierre()._esconder()
        self.assertTrue(self.barra.winfo_exists())
        self.assertFalse(self.barra.desplegada)

    def _abrir_todos_los_grupos(self):
        """Con todo abierto la barra pasa del alto de la pantalla: sirve para probar el desplazamiento."""
        b = self.barra
        for grupo, info in list(b.grupos_ui.items()):
            if not info["abierto"]:
                b.alternar_grupo(grupo)
        b.update()
        if not b.con_scroll:
            self.skipTest("en esta pantalla la barra cabe entera")

    def test_la_rueda_desplaza_si_no_cabe(self):
        b = self.barra
        self._abrir_todos_los_grupos()
        self.assertEqual(b.desplazamiento, 0)
        b.panel.event_generate("<MouseWheel>", delta=-120)
        b.update()
        self.assertGreater(b.desplazamiento, 0)
        b.panel.event_generate("<MouseWheel>", delta=120)
        b.update()
        self.assertEqual(b.desplazamiento, 0)

    def test_la_barrita_llega_al_final_y_vuelve(self):
        b = self.barra
        self._abrir_todos_los_grupos()
        b._arrastrar_indicador(type("Evento", (), {"y": b.alto_area})())
        self.assertEqual(b.desplazamiento, b.alto_contenido - b.alto_area)
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
        import datetime
        v.atajo.set("ayer")
        v._actualizar()
        ayer_habil = (datetime.date.today() - datetime.timedelta(days=1)).weekday() < 5   # un lunes, ayer fue domingo
        self.assertRegex(v.rango.cget("text"),
                         r"el \d\d/\d\d/\d{4} \(1 día hábil\)" if ayer_habil else r"el \d\d/\d\d/\d{4} \(0 días hábiles\)")
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

    def test_elegir_la_clase_ofrece_no_hubo_clase_y_no_vuelve_a_correr(self):
        guion = self.GUION_SIN_CLASE.replace(
            "'opciones':", "'sin_clase': {'campo': 'bloques', 'clave': '4BA|12:50-00:00|802|2026-10-06',"
                           " 'dia': '2026-10-06', 'titulo': '06/10 4BA 12:50'}, 'opciones':")
        c = self._correr(guion, titulo="Registrar libro")
        elegir = self.mod["VentanaElegirClase"](c)
        self.barra.update()
        combo = elegir.combos["4BA|12:50-00:00|802|2026-10-06"]
        self.assertEqual(list(combo["values"])[-1], elegir.NO_HUBO)
        combo.current(len(combo["values"]) - 1)
        antes = [w for w in self.barra.winfo_children() if isinstance(w, self.mod["Consola"])]
        elegir._declarar()
        self.assertFalse(elegir.winfo_exists())
        self.assertEqual(antes, [w for w in self.barra.winfo_children() if isinstance(w, self.mod["Consola"])],
                         "no hay nada que declarar: no vuelve a correr")
        self.assertEqual(self.mod["leer_sin_clases"](self.mod["SIN_CLASES"])["bloques"],
                         {"4BA|12:50-00:00|802|2026-10-06": "06/10 4BA 12:50"})
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

    # ------------------------------------------------------------ buzón del colegio
    CODIGO = "ABCDEFGHJKLMNPQRSTUV"

    def _buzon(self, mensajes=(), claves=None):
        col = self.mod["colegio"]
        col.guardar_paquete(self.mod["BUZON_COLEGIO"],
                            col.cerrar(self.CODIGO, {"claves": claves or {}, "mensajes": list(mensajes)}))

    def test_los_avisos_del_colegio_se_ven_arriba_avisan_una_vez_y_se_marcan_listos(self):
        import datetime
        col, b = self.mod["colegio"], self.barra
        hoy = datetime.date.today()
        mensajes = [col.nuevo_mensaje("mensaje", "Reunión de ciclo a las 16:00", de="Bastián"),
                    col.nuevo_mensaje("aviso", "Hoy hay consejo de profesores", fecha=hoy),
                    col.nuevo_mensaje("aviso", "Mañana no", fecha=hoy + datetime.timedelta(days=1)),
                    col.nuevo_mensaje("mensaje", "Para otra persona", "Nadie Inexistente Xyz")]
        self._buzon(mensajes)
        self.codigo_colegio = self.CODIGO
        avisos = []
        with mock.patch.dict(self.mod, {"Aviso": lambda barra, estado, titulo, detalle, **k: avisos.append(titulo)}):
            b.refrescar_avisos()
            b.refrescar_avisos()                              # lo ya avisado no vuelve a saltar
        texto = self._textos(b.tarjeta_avisos)
        self.assertIn("📣 AVISOS · 2", texto)
        self.assertIn("Reunión de ciclo a las 16:00", texto)
        self.assertIn("Mensaje de Bastián", texto)
        self.assertIn("Hoy hay consejo de profesores", texto)
        self.assertNotIn("Mañana no", texto)
        self.assertNotIn("Para otra persona", texto)
        self.assertEqual(avisos, ["2 avisos nuevos del colegio"])
        ordenados = b.panel.pack_slaves()
        self.assertLess(ordenados.index(b.tarjeta_avisos), ordenados.index(b.tarjeta_hoy), "van arriba de «Hoy»")
        b.marcar_aviso_leido(mensajes[0]["id"])
        self.assertIn("📣 AVISOS · 1", self._textos(b.tarjeta_avisos))
        b.marcar_aviso_leido(mensajes[1]["id"])
        self.assertFalse(b.tarjeta_avisos.winfo_manager(), "sin avisos no ocupa lugar")

    def test_sin_la_clave_del_colegio_se_ve_lo_general_y_no_lo_dirigido(self):
        import datetime
        col, b = self.mod["colegio"], self.barra
        nombre = self.mod["NOMBRE_COMPLETO"]
        if not nombre:
            self.skipTest("este PC no tiene un profesor configurado")
        self._buzon([col.nuevo_mensaje("aviso", "Consejo para todos", fecha=datetime.date.today()),
                     col.nuevo_mensaje("mensaje", "Solo para ti", nombre)])
        with mock.patch.dict(self.mod, {"Aviso": lambda *a, **k: None}):
            b.refrescar_avisos()
            texto = self._textos(b.tarjeta_avisos)
            self.assertIn("Consejo para todos", texto)
            self.assertNotIn("Solo para ti", texto, "lo dirigido necesita la clave del colegio")
            self.codigo_colegio = self.CODIGO
            b.refrescar_avisos()
        self.assertIn("Solo para ti", self._textos(b.tarjeta_avisos))

    def test_la_clave_del_colegio_se_revisa_antes_de_guardarla(self):
        self._buzon()
        ajustes = self._ajustes("Profesor")
        self.assertIn("Clave del colegio", self._textos(ajustes))
        ajustes.destroy()
        v = self.mod["VentanaClaveColegio"](self.barra)
        self.barra.update()
        self.assertIn("todavía no tiene la clave del colegio", v.aviso.cget("text"))
        v.texto.set("abc")
        v._guardar()
        self.assertIn("Escribe la clave completa", v.aviso.cget("text"))
        v.texto.set("ZZZZ-ZZZZ-ZZZZ-ZZZZ-ZZZZ")
        v._guardar()
        self._esperar(lambda: "no abre" in v.aviso.cget("text"))
        self.assertEqual(self.codigo_colegio, "", "una clave que no abre no se guarda")
        v.texto.set("abcd efgh jklm npqr stuv")
        v._guardar()
        self._esperar(lambda: "Guardada" in v.aviso.cget("text"))
        self.assertEqual(self.codigo_colegio, self.mod["colegio"].normalizar_codigo(self.CODIGO))
        v.destroy()

    def test_la_clave_del_colegio_puede_ser_una_frase(self):
        col = self.mod["colegio"]
        col.guardar_paquete(self.mod["BUZON_COLEGIO"], col.cerrar("Tiza lunes guitarra volcán", {"mensajes": []}))
        v = self.mod["VentanaClaveColegio"](self.barra)
        v.texto.set("tiza LUNES guitarra volcan")              # sin tildes ni mayúsculas: vale igual
        v._guardar()
        self._esperar(lambda: "Guardada" in v.aviso.cget("text"))
        self.assertEqual(self.codigo_colegio, "tizalunesguitarravolcan")
        v.destroy()

    def test_la_barra_no_trae_nada_de_administrador(self):
        """Publicar es de la mini app «Administrador del colegio», que no viaja con la barra: ni aunque este PC pueda."""
        with mock.patch.object(self.mod["colegio"], "es_administrador", lambda *a, **k: True):
            ajustes = self._ajustes()
            self.assertNotIn("Administrador", ajustes.pestanas.pestanas)
            ajustes.destroy()
        for nombre in ("VentanaAdministrador", "_revisar_admin"):
            self.assertNotIn(nombre, self.mod)
            self.assertFalse(hasattr(self.barra, nombre))
        self.assertEqual(self.mod["MS_VIGILAR_COLEGIO"], 3 * 60 * 1000, "el buzón se revisa cada 3 minutos")

    # ------------------------------------------------------------ días sin clases
    def _estado_con_pendientes(self):
        """Hoy, dos bloques sin completar (5BA y 6BB); el lunes 12/10, dos bloques atrasados."""
        import datetime
        hoy = datetime.date.today()
        bloques = [{"curso": "5BA", "id": 701, "hora": "08:00-09:30", "asignatura": "Ciencias", "oa": False,
                    "leccionario": False, "asistencia": True, "firma": False},
                   {"curso": "6BB", "id": 702, "hora": "10:00-11:30", "asignatura": "Ciencias", "oa": False,
                    "leccionario": True, "asistencia": True, "firma": False}]
        estado = {"fecha": hoy.strftime("%d/%m/%Y"), "revisado": f"{hoy:%d/%m/%Y} 10:00", "bloques": bloques,
                  "sin_firmar": bloques, "sin_registro": bloques,
                  "atrasados": [{"fecha": "12/10/2026", "bloques": 2, "cursos": ["5BA", "6BB"],
                                 "claves": ["5BA|08:00-09:30|1|2026-10-12", "6BB|10:00-11:30|2|2026-10-12"]}]}
        ruta = os.path.join(self.carpeta, "estado_firmas.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(estado, f)
        self.mod["ESTADO_FIRMAS"] = ruta
        return hoy

    def _sin_clases(self):
        return self.mod["leer_sin_clases"](self.mod["SIN_CLASES"])

    def test_la_lista_saca_una_fila_y_el_titulo_de_su_grupo_si_queda_vacio(self):
        lista = self.mod["ListaMarcable"](self.barra)
        avisos = []
        lista.al_cambiar = lambda marcadas, total: avisos.append((marcadas, total))
        for clave, grupo in (("a", "lun 12/10"), ("b", "lun 12/10"), ("c", "mar 13/10")):
            lista.agregar(clave, clave.upper(), grupo=grupo, accion=("No hubo clase ▾", lambda _e: None))
        self.assertIn("No hubo clase ▾", self._textos(lista))
        lista.quitar("c")
        self.assertEqual(lista.todas(), ["a", "b"])
        self.assertEqual(avisos[-1], (["a", "b"], 2))
        self.assertNotIn("MAR 13/10", self._textos(lista))
        lista.quitar("a")
        self.assertIn("LUN 12/10", self._textos(lista), "el grupo sigue mientras le quede una fila")
        lista.quitar("no existe")
        self.assertEqual(lista.todas(), ["b"])
        lista.destroy()

    def test_vista_previa_del_libro_deja_marcar_un_bloque_sin_clase(self):
        hoy = self._estado_con_pendientes()
        lanzado = []
        previa = self.mod["VistaPrevia"](self.barra, {"nombre": "Registrar libro", "vista_previa": "libro"},
                                         lambda *a: lanzado.append(a))
        self.barra.update()
        self.assertEqual(self._textos(previa).count("No hubo clase ▾"), 2)
        previa._marcar_sin_clase(previa._items_lista[0], todo_el_dia=False)
        self.barra.update()
        self.assertEqual(list(self._sin_clases()["bloques"]), [f"5BA|08:00-09:30|701|{hoy.isoformat()}"])
        self.assertEqual(previa.lista.todas(), ["6BB|10:00-11:30|702"])
        self.assertIn("queda como clase que no se hizo", previa.aviso.cget("text"))
        self.assertIn("1 de 1 marcadas", self._textos(previa))
        self.assertNotIn("5BA", self.barra.libro_texto.cget("text"), "la tarjeta «Hoy» deja de contarlo al tiro")
        previa._continuar()
        self.assertEqual(lanzado, [(["6BB|10:00-11:30|702"], ["6BB|10:00-11:30|702"])])

    def test_vista_previa_marca_el_dia_entero_y_si_no_queda_nada_lo_dice(self):
        previa = self.mod["VistaPrevia"](self.barra, {"nombre": "Registrar libro pendiente"}, lambda *a: None)

        def item(clave, dia):
            return {"clave": clave, "titulo": clave, "grupo": dia, "detalle": "",
                    "sin_clase": {"campo": "bloques", "clave": clave, "dia": dia, "titulo": clave}}
        items = [item("a|2026-10-12", "2026-10-12"), item("b|2026-10-12", "2026-10-12"),
                 item("c|2026-10-13", "2026-10-13")]
        previa._mostrar({"titulo": "x", "puntos": [], "items": items, "hay_trabajo": True, "aviso": ""})
        previa._marcar_sin_clase(items[0], todo_el_dia=True)
        self.assertEqual(previa.lista.todas(), ["c|2026-10-13"], "se van todos los bloques de ese día")
        self.assertEqual(self._sin_clases()["dias"], {"2026-10-12": ""})
        self.assertIn("lunes 12/10 queda como día sin clases", previa.aviso.cget("text"))
        previa._marcar_sin_clase(items[2], todo_el_dia=False)
        self.assertIsNone(previa.lista)
        self.assertIn("Ya no queda nada por hacer", self._textos(previa))
        previa.destroy()

    def test_la_tarjeta_hoy_no_cuenta_lo_marcado_sin_clases(self):
        hoy = self._estado_con_pendientes()
        b = self.barra
        b._refrescar_firmas()
        if not b.hoy_abierta:
            b.alternar_hoy()
        self.assertIn("2 sin firmar", b.libro_texto.cget("text"))
        self.assertIn("2 bloques de días anteriores", b.libro_texto.cget("text"))
        self.assertTrue(b.sin_clases_enlace.winfo_manager(), "abierta, ofrece marcar feriados")
        with open(self.mod["SIN_CLASES"], "w", encoding="utf-8") as f:
            json.dump({"dias": {"2026-10-12": "Feriado", hoy.isoformat(): "Salida"}}, f)
        b._refrescar_firmas()
        self.assertEqual(b.libro_texto.cget("text"), "Hoy: sin clases (lo marcaste)")
        self.assertFalse(b.sin_clases_enlace.winfo_manager(), "sin pendientes no hace falta")
        b.alternar_hoy()

    def test_dias_sin_clases_marca_un_dia_pendiente_y_un_rango_y_se_deshace(self):
        self._estado_con_pendientes()
        self.mod["abrir"]({"nombre": "Días sin clases", "tipo": "sin-clases", "destino": ""}, self.barra)
        self.barra.update()
        v = [w for w in self.barra.winfo_children() if isinstance(w, self.mod["VentanaSinClases"])][0]
        texto = self._textos(v)
        self.assertIn("lun 12/10 · 2 bloques sin registrar (5BA, 6BB)", texto)
        self.assertIn("Todavía no marcas ningún día.", texto)
        v._marcar()
        self.assertIn("Marca un día de la lista", v.aviso.cget("text"))
        v.elegidos["2026-10-12"].set(True)
        v.desde.set("20/07/2026")
        v.hasta.set("24/07/2026")
        v.motivo.set("Vacaciones")
        v._marcar()
        self.barra.update()
        self.assertEqual(len(self._sin_clases()["dias"]), 6)
        texto = self._textos(v)
        self.assertIn("lun 20/07 al vie 24/07/2026 (5 días) · Vacaciones", texto)
        self.assertNotIn("bloques sin registrar", texto, "lo marcado ya no se ofrece")
        self.assertNotIn("días anteriores", self.barra.libro_texto.cget("text"))
        quitar = [w for w in v.marcados.interior.winfo_children()[1].winfo_children() if w.cget("text") == "Quitar"]
        quitar[0].event_generate("<Button-1>")             # la segunda fila: las vacaciones de julio
        self.barra.update()
        self.assertEqual(list(self._sin_clases()["dias"]), ["2026-10-12"])
        self.assertIn("Quitado", v.aviso.cget("text"))
        v.desde.set("31/02")
        v._marcar()
        self.assertIn("no existe", v.aviso.cget("text"))
        self.barra.abrir_sin_clases()                       # una sola ventana
        self.assertEqual(len([w for w in self.barra.winfo_children() if isinstance(w, self.mod["VentanaSinClases"])]), 1)
        v.destroy()

    def test_dias_sin_clases_esta_en_ajustes_y_con_la_barra_bloqueada_pide_el_pin(self):
        ajustes = self._ajustes("Profesor")
        self.assertIn("Días sin clases", self._textos(ajustes))
        ajustes._sin_clases()
        self.barra.update()
        abiertas = [w for w in self.barra.winfo_children() if isinstance(w, self.mod["VentanaSinClases"])]
        self.assertEqual(len(abiertas), 1)
        abiertas[0].destroy()
        self._compartido()
        self.mod["guardar_pin"](self.mod["ruta_pin"](self.carpeta, self.mod["PERFIL"]), "2468")
        self.barra.bloquear()
        self.barra.abrir_sin_clases()
        self.barra.update()
        self.assertFalse([w for w in self.barra.winfo_children() if isinstance(w, self.mod["VentanaSinClases"])])
        self.assertIsNotNone(self._ventana_pin())


if __name__ == "__main__":
    unittest.main()
