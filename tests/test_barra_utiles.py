"""Pruebas de las funciones de la barra que no necesitan ventana.

Se corren con:   python -m unittest discover -s tests -v
(desde la carpeta que contiene herramienta\\ y tests\\).
"""

import datetime
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import barra_utiles as u  # noqa: E402


def hora(h: int, m: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 10, 5, h, m)      # un lunes


BLOQUES = [
    {"inicio": "08:00", "fin": "08:45", "titulo": "5BA Ciencias"},
    {"inicio": "09:00", "fin": "09:45", "titulo": "6BB Ciencias"},
    {"inicio": "10:00", "fin": "10:45", "titulo": "7BA Ciencias"},
]


class Horario(unittest.TestCase):
    def test_minutos(self):
        self.assertEqual(u.minutos("08:30"), 510)
        self.assertEqual(u.minutos("9"), 540)         # sin minutos

    def test_en_clase_y_siguiente(self):
        ahora, luego = u.ahora_y_luego(BLOQUES, hora(8, 10))
        self.assertEqual(ahora, "5BA Ciencias · hasta 08:45")
        self.assertEqual(luego, "6BB Ciencias 09:00")

    def test_en_recreo(self):
        ahora, luego = u.ahora_y_luego(BLOQUES, hora(8, 50))
        self.assertEqual(ahora, "Libre")
        self.assertEqual(luego, "6BB Ciencias 09:00")

    def test_ultimo_bloque_del_dia(self):
        ahora, luego = u.ahora_y_luego(BLOQUES, hora(10, 30))
        self.assertEqual(ahora, "7BA Ciencias · hasta 10:45")
        self.assertEqual(luego, "Nada más por hoy")

    def test_fin_del_bloque_ya_no_cuenta_como_ahora(self):
        ahora, _ = u.ahora_y_luego(BLOQUES, hora(8, 45))
        self.assertEqual(ahora, "Libre")

    def test_sin_bloques(self):
        self.assertEqual(u.ahora_y_luego([], hora(9)), ("", "Hoy no hay clases"))


class Saludo(unittest.TestCase):
    def test_segun_la_hora(self):
        self.assertEqual(u.saludo_para("Ana", hora(7)), "Buenos días, Ana")
        self.assertEqual(u.saludo_para("Ana", hora(15)), "Buenas tardes, Ana")
        self.assertEqual(u.saludo_para("Ana", hora(22)), "Buenas noches, Ana")
        self.assertEqual(u.saludo_para("Ana", hora(3)), "Buenas noches, Ana")

    def test_sin_nombre(self):
        self.assertEqual(u.saludo_para("", hora(7)), "Buenos días")


class EstadoVencido(unittest.TestCase):
    HOY = "05/10/2026"

    def test_sin_estado(self):
        self.assertTrue(u.estado_vencido(None, 0, self.HOY))

    def test_de_otro_dia(self):
        self.assertTrue(u.estado_vencido({"fecha": "04/10/2026"}, 10, self.HOY))

    def test_reciente(self):
        self.assertFalse(u.estado_vencido({"fecha": self.HOY}, 60, self.HOY))

    def test_pasados_veinte_minutos(self):
        self.assertTrue(u.estado_vencido({"fecha": self.HOY}, 21 * 60, self.HOY))

    def test_con_error_se_reintenta_a_los_tres_minutos(self):
        estado = {"fecha": self.HOY, "error": "conexión cortada"}
        self.assertFalse(u.estado_vencido(estado, 2 * 60, self.HOY))
        self.assertTrue(u.estado_vencido(estado, 4 * 60, self.HOY))


class Botones(unittest.TestCase):
    def test_variables_propias(self):
        destino = u.reemplazar_variables(r"%DATOS%\registro.csv", {"%DATOS%": r"C:\x\datos"})
        self.assertEqual(destino, r"C:\x\datos\registro.csv")

    def test_variables_de_windows(self):
        os.environ["PRUEBA_BARRA"] = "valor"
        self.assertEqual(u.reemplazar_variables("%PRUEBA_BARRA%", {}), "valor")

    def test_comando_simple(self):
        self.assertEqual(u.partes_de_comando("asignar --hoy --dias-atras 7"),
                         ["asignar", "--hoy", "--dias-atras", "7"])

    def test_comando_con_ruta_con_espacios(self):
        self.assertEqual(u.partes_de_comando('subir --carpeta "C:\\Mis Documentos\\Webclass"'),
                         ["subir", "--carpeta", "C:\\Mis Documentos\\Webclass"])

    def test_comando_vacio(self):
        with self.assertRaises(ValueError):
            u.partes_de_comando("   ")


class Consola(unittest.TestCase):
    def test_colores(self):
        casos = {
            "[OK] Clase asignada": "ok",
            "Todo listo": "ok",
            "0 errores": "ok",
            "sin pendientes": "ok",
            "3 pendientes": "aviso",
            "falta el OA": "aviso",
            "error: no se pudo entrar": "error",
            "3 errores": "error",
            "Conectando…": "",
            "listos para empezar": "",          # 'listo' solo cuenta como palabra entera
        }
        for linea, esperado in casos.items():
            with self.subTest(linea=linea):
                self.assertEqual(u.etiqueta_de_linea(linea), esperado)


class Actividades(unittest.TestCase):
    def test_completado(self):
        r = u.resumir_ejecucion(0, ["  [OK] A: asignada", "  [OK] B: asignada", "  [YA] C"])
        self.assertEqual(r["estado"], "completado")
        self.assertEqual(r["resumen"], "2 correctas · 1 ya estaba")

    def test_con_avisos(self):
        r = u.resumir_ejecucion(0, ["[OK] A", "  [SALTADA] B: sin fecha", "[PENDIENTE] C"])
        self.assertEqual(r["estado"], "avisos")
        self.assertEqual(r["resumen"], "1 correcta · 1 saltada · 1 pendiente")

    def test_error_por_codigo_de_salida(self):
        r = u.resumir_ejecucion(1, ["[OK] A"])
        self.assertEqual(r["estado"], "error")

    def test_error_sin_marcas_explica_el_codigo(self):
        r = u.resumir_ejecucion(2, ["Traceback..."])
        self.assertEqual(r["estado"], "error")
        self.assertEqual(r["resumen"], "Terminó con error (código 2)")

    def test_error_por_marca_aunque_el_codigo_sea_cero(self):
        r = u.resumir_ejecucion(0, ["  [ERROR] 05/10: falló"])
        self.assertEqual(r["estado"], "error")
        self.assertEqual(r["resumen"], "1 con error")

    def test_cancelado_manda_sobre_todo(self):
        r = u.resumir_ejecucion(1, ["[ERROR] x"], cancelada=True)
        self.assertEqual(r["estado"], "cancelado")

    def test_sin_novedades(self):
        r = u.resumir_ejecucion(0, ["Conectando…", "Listo"])
        self.assertEqual((r["estado"], r["resumen"]), ("completado", "Terminó sin novedades"))

    def test_las_marcas_deben_estar_al_inicio_de_la_linea(self):
        self.assertEqual(u.resumir_ejecucion(0, ["texto con [ERROR] en medio"])["error"], 0)

    def test_progreso(self):
        self.assertEqual(u.parsear_progreso("##PROGRESO 3/8 6BA"), (3, 8, "6BA"))
        self.assertEqual(u.parsear_progreso("  ##PROGRESO 8/8"), (8, 8, ""))
        self.assertEqual(u.parsear_progreso("##PROGRESO 9/8 x"), (8, 8, "x"))   # no pasa de 100 %
        self.assertIsNone(u.parsear_progreso("##PROGRESO 1/0 x"))
        self.assertIsNone(u.parsear_progreso("[OK] algo"))

    def test_errores_traducidos(self):
        self.assertIn("usuario o contraseña", u.traducir_error(["Usuario incorrecto"]))
        self.assertIn("conexión", u.traducir_error(["requests.exceptions.ConnectionError: x"]))
        self.assertIn("Excel", u.traducir_error(["PermissionError: [Errno 13]"]))
        self.assertIsNone(u.traducir_error(["todo bien"]))

    def test_duracion(self):
        self.assertEqual(u.formatear_duracion(45), "45 s")
        self.assertEqual(u.formatear_duracion(60), "1 min")
        self.assertEqual(u.formatear_duracion(125), "2 min 5 s")
        self.assertEqual(u.formatear_duracion(-3), "0 s")

    def test_hace_cuanto(self):
        ahora = datetime.datetime(2026, 10, 5, 15, 0)
        casos = {
            datetime.datetime(2026, 10, 5, 14, 59, 50): "hace un momento",
            datetime.datetime(2026, 10, 5, 14, 55): "hace 5 min",
            datetime.datetime(2026, 10, 5, 9, 30): "hoy 09:30",
            datetime.datetime(2026, 10, 4, 18, 10): "ayer 18:10",
            datetime.datetime(2026, 10, 1, 8, 5): "01/10 08:05",
        }
        for momento, esperado in casos.items():
            with self.subTest(esperado=esperado):
                self.assertEqual(u.hace_cuanto(momento, ahora), esperado)

    def test_memoria_de_ejecuciones(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "ultimas.json")
            self.assertEqual(u.cargar_ejecuciones(ruta), {})
            u.guardar_ejecucion(ruta, "Asignar clases", "completado", "5 correctas", 41.26,
                                datetime.datetime(2026, 10, 5, 14, 32))
            datos = u.guardar_ejecucion(ruta, "Mi horario", "error", "x", 2)
            self.assertEqual(sorted(datos), ["Asignar clases", "Mi horario"])
            leido = u.cargar_ejecuciones(ruta)["Asignar clases"]
            self.assertEqual((leido["estado"], leido["duracion"], leido["hora"]),
                             ("completado", 41.3, "2026-10-05T14:32:00"))

    def test_memoria_dañada_no_rompe(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "ultimas.json")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write("{roto")
            self.assertEqual(u.cargar_ejecuciones(ruta), {})


class Items(unittest.TestCase):
    @staticmethod
    def item(clave, estado, que="OA y leccionario", **extra):
        return {"clave": clave, "estado": estado, "titulo": clave, "grupo": "",
                "que": que, "detalle": "", "motivo": "", **extra}

    def test_parsear_item(self):
        r = u.parsear_item('  ##ITEM {"clave": "5BA|09:40|Cs", "estado": "hecho", '
                           '"titulo": "5BA 09:40", "grupo": "5BA", "que": "OA"}')
        self.assertEqual((r["clave"], r["estado"], r["grupo"], r["detalle"]),
                         ("5BA|09:40|Cs", "hecho", "5BA", ""))

    def test_parsear_item_invalido(self):
        for linea in ("[OK] algo", "##ITEM {roto", '##ITEM {"clave": "x", "estado": "raro"}',
                      '##ITEM {"estado": "hecho"}', '##ITEM ["x"]'):
            with self.subTest(linea=linea):
                self.assertIsNone(u.parsear_item(linea))

    def test_agrupar_en_bloques(self):
        items = [self.item("a", "hecho"), self.item("b", "ya"), self.item("c", "pendiente"),
                 self.item("d", "error"), self.item("e", "omitido"), self.item("f", "propuesto")]
        bloques = u.agrupar_items(items)
        self.assertEqual([i["clave"] for i in bloques["hecho"]], ["a"])
        self.assertEqual([i["clave"] for i in bloques["ya"]], ["b"])
        self.assertEqual([i["clave"] for i in bloques["no_pude"]], ["c", "d"])
        self.assertEqual([i["clave"] for i in bloques["omitido"]], ["e"])

    def test_el_ultimo_estado_de_la_misma_accion_manda(self):
        items = [self.item("a", "pendiente"), self.item("a", "hecho"),
                 self.item("a", "pendiente", que="asistencia")]
        bloques = u.agrupar_items(items)
        self.assertEqual(len(bloques["hecho"]), 1)
        self.assertEqual(len(bloques["no_pude"]), 1)             # la asistencia sigue pendiente

    def test_resumen_con_items_no_dice_completado_si_algo_quedo_sin_hacer(self):
        items = [self.item("a", "hecho"), self.item("b", "pendiente"), self.item("c", "omitido")]
        r = u.resumir_ejecucion(0, [], items=items)
        self.assertEqual(r["estado"], "avisos")
        self.assertEqual(r["resumen"], "1 correcta · 1 pendiente · 1 omitida por ti")

    def test_resumen_con_items_todo_bien(self):
        r = u.resumir_ejecucion(0, [], items=[self.item("a", "hecho"), self.item("b", "ya")])
        self.assertEqual(r["estado"], "completado")

    def test_asistencia_en_blanco_cuenta_como_pendiente(self):
        r = u.resumir_ejecucion(0, ["  [ASISTENCIA EN BLANCO] 5BA 09:40: sin bloque anterior"])
        self.assertEqual(r["estado"], "avisos")
        self.assertEqual(r["pendiente"], 1)

    def test_motivos_explicados(self):
        r = u.explicar_motivo("no hay clase con esa fecha en la planificación")
        self.assertIn("no tiene una clase con esa fecha", r["que"])
        self.assertIn("Agrega la clase", r["hacer"])
        self.assertIn("a mano", u.explicar_motivo("taller «Química»: la asistencia se toma a mano")["hacer"])
        self.assertIn("varias clases", u.explicar_motivo("3 clases con esa fecha, no sé cuál usar")["que"])
        self.assertEqual(u.explicar_motivo("algo raro")["que"], "algo raro")

    def test_parsear_opciones(self):
        r = u.parsear_opciones('##OPCIONES {"unidad": 7516413, "opciones": [{"id": 5, "nombre": "5BA"}, '
                               '{"id": 6, "nombre": "T.J Ciencias"}, {"sin_id": 1}], "error": ""}')
        self.assertEqual(r["unidad"], "7516413")
        self.assertEqual([o["nombre"] for o in r["opciones"]], ["5BA", "T.J Ciencias"])
        self.assertIsNone(u.parsear_opciones("##OPCIONES {roto"))
        self.assertIsNone(u.parsear_opciones("otra cosa"))
        self.assertEqual(u.parsear_opciones('##OPCIONES {"unidad": "1", "error": "sin clases"}')["error"],
                         "sin clases")

    UNIDADES = [{"curso": "5BA", "id": 1, "nombre": "Energía y circuitos"},
                {"curso": "5BB", "id": 2, "nombre": "Energía y circuitos"},
                {"curso": "7BA", "id": 3, "nombre": "Defensas"}]

    def test_filas_de_destinos(self):
        elegidos = {"2": {"id": 99, "nombre": "T.J Ciencias 1S"}}
        filas = u.filas_de_destinos(self.UNIDADES, elegidos)
        self.assertEqual([f["clave"] for f in filas], ["1", "2", "3"])
        self.assertEqual(filas[0]["detalle"], "Por defecto: el curso 5BA")
        self.assertEqual(filas[1]["detalle"], "Se asigna a: T.J Ciencias 1S")
        self.assertTrue(filas[1]["cambiada"])

    def test_filas_de_destinos_filtradas(self):
        elegidos = {"2": {"id": 99, "nombre": "T.J Ciencias 1S"}}
        self.assertEqual([f["clave"] for f in u.filas_de_destinos(self.UNIDADES, elegidos, filtro="7ba")], ["3"])
        self.assertEqual([f["clave"] for f in u.filas_de_destinos(self.UNIDADES, elegidos, filtro="taller")], [])
        self.assertEqual([f["clave"] for f in u.filas_de_destinos(self.UNIDADES, elegidos, filtro="ciencias 1s")], ["2"])
        self.assertEqual([f["clave"] for f in u.filas_de_destinos(self.UNIDADES, elegidos, solo_cambiadas=True)], ["2"])

    def test_aplicar_destinos_cambia_solo_lo_pedido(self):
        antes = {"1": {"id": 5, "nombre": "5BA"}, "2": {"id": 6, "nombre": "5BB"}}
        despues = u.aplicar_destinos(antes, {"1": None, "3": {"id": 7, "nombre": "7BA", "extra": 1}})
        self.assertEqual(despues, {"2": {"id": 6, "nombre": "5BB"}, "3": {"id": 7, "nombre": "7BA"}})
        self.assertIn("1", antes)                                   # no modifica el original

    def test_vista_previa_con_items_para_marcar(self):
        bloque = {"curso": "5BA", "hora": "09:40-11:10", "asignatura": "Ciencias", "id": 77,
                  "oa": False, "leccionario": True, "asistencia": True}
        sin_id = {"curso": "6BA", "hora": "08:00-09:30", "oa": True, "leccionario": False,
                  "asistencia": True}
        estado = {"fecha": "05/10/2026", "revisado": "05/10/2026 15:52",
                  "sin_firmar": [], "sin_registro": [bloque, sin_id]}
        r = u.vista_previa_libro(estado, "05/10/2026")
        self.assertEqual([i["clave"] for i in r["items"]],
                         ["5BA|09:40-11:10|77", "6BA|08:00-09:30"])
        self.assertEqual(r["items"][0]["titulo"], "5BA 09:40 · Ciencias")
        self.assertEqual(r["items"][0]["grupo"], "5BA")

    def test_vista_previa_subir_items_por_archivo(self):
        with tempfile.TemporaryDirectory() as buzon:
            os.makedirs(os.path.join(buzon, "5 basico"))
            open(os.path.join(buzon, "5 basico", "guia.pdf"), "w").close()
            r = u.vista_previa_subir(buzon)
            self.assertEqual([i["clave"] for i in r["items"]], ["5 basico/guia.pdf"])

    def test_vista_previa_simulacion_con_items(self):
        items = [{"clave": "c1", "estado": "propuesto", "titulo": "5BA · Clase 21", "grupo": "5BA",
                  "que": "asignación", "detalle": "40 alumnas (06/10 - 06/10)", "motivo": ""},
                 {"clave": "c2", "estado": "pendiente", "titulo": "5BA · Clase 22", "grupo": "5BA",
                  "que": "asignación", "detalle": "", "motivo": "sin fechas"}]
        r = u.vista_previa_simulacion("Asignar clases", [], 0, items)
        self.assertEqual([i["clave"] for i in r["items"]], ["c1"])
        self.assertIn("1 clase se saltará", r["aviso"])

    def test_items_con_opciones(self):
        r = u.parsear_item('##ITEM {"clave": "k", "estado": "pendiente", "opciones": '
                           '[{"id": 5, "texto": "Clase 19 · 30/09"}, {"sin_id": 1}, {"id": "7"}]}')
        self.assertEqual(r["opciones"], [{"id": "5", "texto": "Clase 19 · 30/09"},
                                         {"id": "7", "texto": "7"}])
        self.assertEqual(u.parsear_item('##ITEM {"clave": "k", "estado": "hecho"}')["opciones"], [])

    def test_seleccion_con_elecciones_siempre_se_escribe(self):
        with tempfile.TemporaryDirectory() as carpeta:
            todas = ["a", "b"]
            args = u.argumentos_de_seleccion(todas, todas, carpeta, {"a": "c19"})   # aunque marcó todo
            self.assertEqual(args[0], "--seleccion")
            with open(args[1], encoding="utf-8") as f:
                contenido = json.load(f)
            self.assertEqual(contenido, {"claves": ["a", "b"], "elecciones": {"a": "c19"}})

    def test_comando_con_otra_seleccion(self):
        with tempfile.TemporaryDirectory() as carpeta:
            base = ["python", "libro.py", "--desde", "01/10/2026", "--seleccion", "vieja.json",
                    "--perfil", "ana"]
            nuevo = u.comando_con_seleccion(base, ["k1"], carpeta, {"k1": "c9"})
            self.assertEqual(nuevo[:6], ["python", "libro.py", "--desde", "01/10/2026",
                                         "--perfil", "ana"])
            self.assertEqual(nuevo.count("--seleccion"), 1)
            self.assertNotIn("vieja.json", nuevo)
            with open(nuevo[-1], encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"claves": ["k1"], "elecciones": {"k1": "c9"}})

    def test_contar_firmas(self):
        lineas = ["x", "  FALTA TU FIRMA en:", "    07/10 6BB 09:40", "    07/10 7BB 11:20", "", "Registro"]
        self.assertEqual(u.contar_firmas(lineas), 2)
        self.assertEqual(u.contar_firmas(["nada"]), 0)

    def test_la_vista_previa_avisa_cuantas_firmas_quedan(self):
        items = [{"clave": "c1", "estado": "propuesto", "titulo": "t", "grupo": "g", "que": "",
                  "detalle": "d", "motivo": ""}]
        r = u.vista_previa_simulacion("Libro", ["  FALTA TU FIRMA en:", "    a", "    b"], 0, items)
        self.assertIn("Quedarán 2 bloques por firmar", r["aviso"])

    def test_vacio_del_dia(self):
        self.assertEqual(u.vacio_del_dia([], tiene_clases=False), "No tienes clases ese día.")
        self.assertEqual(u.vacio_del_dia([self.item("a", "ya")]), "Todo ya estaba registrado.")
        self.assertIn("no se pudieron", u.vacio_del_dia([self.item("a", "pendiente")]))
        self.assertEqual(u.vacio_del_dia([self.item("a", "hecho")]), "")

    def test_lineas_de_resultado(self):
        items = [self.item("a", "hecho", titulo="5BA 08:00", detalle="clase «21»"),
                 self.item("b", "pendiente", titulo="6BA 09:40",
                           motivo="no hay clase con esa fecha en la planificación"),
                 self.item("c", "ya", titulo="8BA 13:35"),
                 self.item("d", "omitido", titulo="7BA 11:20")]
        lineas = u.lineas_de_resultado(items, ["5BA 08:00-09:30"])
        textos = [t for t, _ in lineas]
        self.assertEqual(lineas[0], ("Intenté 3 · hice 1 · no pude 1 · ya estaban 1 · omitiste 1", "resumen"))
        self.assertIn("✓ Hice (1)", textos)
        self.assertIn("5BA 08:00 — clase «21»", textos)
        self.assertIn("⚠ No pude (1)", textos)
        self.assertIn("Tu planificación no tiene una clase con esa fecha.", textos)
        self.assertTrue(any(t.startswith("→ Agrega la clase") for t in textos))
        self.assertIn("○ Ya estaba hecho (1)", textos)
        self.assertIn("– Omitido por ti (1)", textos)
        self.assertIn("✍ Te falta firmar (1)", textos)

    def test_lineas_de_resultado_vacio(self):
        self.assertEqual(u.lineas_de_resultado([], vacio="No tienes clases ese día."),
                         [("No tienes clases ese día.", "vacio")])

    def test_una_lista_larga_de_ya_hechos_no_tapa_lo_importante(self):
        ya = [self.item(f"k{i}", "ya", titulo=f"bloque {i}") for i in range(10)]
        pendiente = self.item("p", "pendiente", titulo="el que falta", motivo="no hay clase con esa fecha")
        textos = [t for t, _ in u.lineas_de_resultado(ya + [pendiente])]
        self.assertIn("○ Ya estaba hecho (10)", textos)
        self.assertIn("son muchos: no se detallan", textos)
        self.assertNotIn("bloque 3", textos)                       # no se listan uno por uno
        self.assertIn("el que falta", textos)
        pocos = [t for t, _ in u.lineas_de_resultado(ya[:3])]
        self.assertIn("bloque 2", pocos)                           # con pocos, sí se detallan

    def test_seleccion_se_pasa_en_un_archivo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            todas = ["a|1", "b|2", "c;3"]
            self.assertEqual(u.argumentos_de_seleccion(todas, todas, carpeta), [])   # todo: nada
            args = u.argumentos_de_seleccion(["a|1", "c;3"], todas, carpeta)
            self.assertEqual(args[0], "--seleccion")
            with open(args[1], encoding="utf-8") as f:
                self.assertEqual(json.load(f)["claves"], ["a|1", "c;3"])        # sin separadores frágiles

    def test_con_unidad_nueva_la_seleccion_siempre_se_pasa(self):
        with tempfile.TemporaryDirectory() as carpeta:
            todas = ["123", "unidad:9"]
            args = u.argumentos_de_seleccion(todas, todas, carpeta)     # aunque marcó todo
            self.assertEqual(args[0], "--seleccion")
            with open(args[1], encoding="utf-8") as f:
                self.assertIn("unidad:9", json.load(f)["claves"])

    def test_motivos_de_asistencia_y_unidades_se_explican(self):
        for texto in ("unidad nueva sin revisar: usa «Asignar» con vista previa",
                      "la asistencia de 11:20 trae un estado que la barra no conoce (7)",
                      "Webclass guardó distinto en 5 alumnas (ausentes sin marcar: 3)"):
            self.assertTrue(u.explicar_motivo(texto)["hacer"], texto)


class AvisoDeAtrasados(unittest.TestCase):
    def test_sin_pendientes_no_dice_nada(self):
        self.assertEqual(u.texto_atrasados([]), "")
        self.assertEqual(u.texto_atrasados([{"fecha": "06/10/2026", "bloques": 0}]), "")

    def test_cuenta_y_nombra_los_dias(self):
        texto = u.texto_atrasados([{"fecha": "06/10/2026", "bloques": 1},
                                   {"fecha": "05/10/2026", "bloques": 2}])
        self.assertEqual(texto, "3 bloques de días anteriores sin registrar (06/10, 05/10)")

    def test_singular_y_muchos_dias(self):
        self.assertIn("1 bloque de", u.texto_atrasados([{"fecha": "06/10/2026", "bloques": 1}]))
        dias = [{"fecha": f"0{i}/10/2026", "bloques": 1} for i in range(1, 6)]
        self.assertIn("y 2 días más", u.texto_atrasados(dias))


class AsuntoDelCorreo(unittest.TestCase):
    def test_curso_escrito_en_el_nombre(self):
        self.assertEqual(u.cursos_en_nombres(["Guía energía 5BA.pdf"]), "5BA")
        self.assertEqual(u.cursos_en_nombres(["a_5ba.pdf", "b 5BB.docx", "c 5BA.pdf"]), "5BA, 5BB")
        self.assertEqual(u.cursos_en_nombres(["1MA guía.pdf", "PKA juego.pdf"]), "1MA, PKA")
        self.assertEqual(u.cursos_en_nombres(["guía 25BAR.pdf", "sin curso.pdf"]), "")   # no confunde

    def test_titulo_sin_extension_ni_curso(self):
        self.assertEqual(u.titulo_de_guia("Circuitos eléctricos 5BA.pdf"), "Circuitos eléctricos")
        self.assertEqual(u.titulo_de_guia("5BB_el_agua_-_guia.docx"), "el agua - guia")
        self.assertEqual(u.titulo_de_guia("5BA.pdf"), "5BA")                              # nada más que el curso

    def test_asunto(self):
        self.assertEqual(u.asunto_de_correo(["Circuitos 5BA.pdf"], "5BA"), "Guía NEEP Circuitos 5BA")
        self.assertEqual(u.asunto_de_correo(["Circuitos.pdf"], ""), "Guía NEEP Circuitos")
        self.assertEqual(u.asunto_de_correo(["A.pdf", "B.pdf"], "5BA, 5BB"),
                         "Guías NEEP A, B 5BA, 5BB")

    def test_el_cuerpo_ya_no_trae_la_frase_de_adjunto(self):
        asunto, cuerpo = u.texto_de_correo(["Guía 6BA.pdf"], "Ana")
        self.assertEqual(asunto, "Guía NEEP Guía 6BA")
        self.assertNotIn("Adjunto", cuerpo)
        self.assertEqual(cuerpo, "Estimado equipo PIE:\n\n- Guía 6BA.pdf\n\nSaludos cordiales,\nAna")


class ObservacionLista(unittest.TestCase):
    def test_completa(self):
        self.assertEqual(u.problemas_de_observacion("5BA", ["1"], 2, "07/10/2026", "texto", "55"), [])

    def test_dice_todo_lo_que_falta(self):
        malos = u.problemas_de_observacion("", [], 0, "ayer", " ", "")
        self.assertEqual(len(malos), 6)

    def test_descripcion_larga(self):
        malos = u.problemas_de_observacion("5BA", ["1"], 1, "07/10/2026", "x" * 1600, "55")
        self.assertEqual(len(malos), 1)


class HaciaAtras(unittest.TestCase):
    HOY = datetime.date(2026, 10, 7)                # miércoles

    def test_atajos(self):
        d = datetime.date
        self.assertEqual(u.rango_de_atajo("ayer", self.HOY), (d(2026, 10, 6), d(2026, 10, 6)))
        self.assertEqual(u.rango_de_atajo("7", self.HOY), (d(2026, 9, 30), self.HOY))
        self.assertEqual(u.rango_de_atajo("15", self.HOY), (d(2026, 9, 22), self.HOY))
        self.assertEqual(u.rango_de_atajo("mes", self.HOY), (d(2026, 10, 1), self.HOY))

    def test_desde_una_fecha(self):
        d = datetime.date
        self.assertEqual(u.rango_de_atajo("fecha", self.HOY, "29/09/2026"), (d(2026, 9, 29), self.HOY))
        self.assertEqual(u.rango_de_atajo("fecha", self.HOY, "1-10"), (d(2026, 10, 1), self.HOY))

    def test_fechas_que_no_sirven(self):
        for texto, esperado in (("", "Escribe la fecha"), ("31/02/2026", "no existe"),
                                ("hola", "Escribe la fecha"), ("08/10/2026", "todavía no llega"),
                                ("01/01/2026", "Es mucho tiempo")):
            with self.subTest(texto=texto):
                with self.assertRaises(ValueError) as caso:
                    u.rango_de_atajo("fecha", self.HOY, texto)
                self.assertIn(esperado, str(caso.exception))

    def test_atajo_desconocido(self):
        with self.assertRaises(ValueError):
            u.rango_de_atajo("siempre", self.HOY)

    def test_parsear_fecha_con_anio_corto(self):
        self.assertEqual(u.parsear_fecha("6/10/26"), datetime.date(2026, 10, 6))

    def test_dias_habiles_sin_fines_de_semana(self):
        dias = u.dias_habiles(datetime.date(2026, 10, 2), datetime.date(2026, 10, 7))
        self.assertEqual([d.day for d in dias], [2, 5, 6, 7])           # sin sábado 3 ni domingo 4


class Periodos(unittest.TestCase):
    HOY = datetime.date(2026, 10, 7)                # miércoles

    def dias(self, clave, hoy=None):
        return {p["clave"]: p["dias"] for p in u.periodos_de_revision(hoy or self.HOY)}[clave]

    def test_meses_escolares(self):
        meses = u.meses_escolares(self.HOY)
        self.assertEqual(len(meses), 8)                               # marzo … octubre
        self.assertEqual(meses[0]["texto"], "Octubre 2026 (este mes)")
        self.assertEqual(meses[0]["clave"], "10/2026")
        self.assertEqual(meses[1]["texto"], "Septiembre 2026 (mes anterior)")
        self.assertEqual(meses[-1]["texto"], "Marzo 2026")

    def test_meses_escolares_en_verano_son_los_del_ano_pasado(self):
        meses = u.meses_escolares(datetime.date(2027, 1, 15))
        self.assertEqual(meses[0]["clave"], "01/2027")
        self.assertEqual(meses[-1]["clave"], "03/2026")
        self.assertEqual(len(meses), 11)

    def test_meses_escolares_en_marzo(self):
        meses = u.meses_escolares(datetime.date(2026, 3, 10))
        self.assertEqual([m["clave"] for m in meses], ["03/2026"])
        self.assertEqual(meses[0]["texto"], "Marzo 2026 (este mes)")

    def test_periodos(self):
        d = datetime.date
        self.assertEqual(self.dias("hoy"), [d(2026, 10, 7)])
        self.assertEqual(self.dias("ayer"), [d(2026, 10, 6)])
        self.assertEqual(self.dias("esta_semana"), [d(2026, 10, 5), d(2026, 10, 6), d(2026, 10, 7)])
        self.assertEqual(self.dias("semana_anterior"),
                         [d(2026, 9, 28), d(2026, 9, 29), d(2026, 9, 30), d(2026, 10, 1), d(2026, 10, 2)])
        self.assertEqual(self.dias("este_mes"), [d(2026, 10, 1), d(2026, 10, 2), d(2026, 10, 5),
                                                 d(2026, 10, 6), d(2026, 10, 7)])
        septiembre = self.dias("mes_anterior")
        self.assertEqual((septiembre[0], septiembre[-1], len(septiembre)),
                         (d(2026, 9, 1), d(2026, 9, 30), 22))
        todo = self.dias("todo")
        self.assertEqual((todo[0], todo[-1]), (d(2026, 3, 2), d(2026, 10, 7)))   # sin el domingo 1/3
        self.assertTrue(all(x.weekday() < 5 for x in todo))

    def test_en_fin_de_semana_hoy_no_tiene_dias(self):
        sabado = datetime.date(2026, 10, 3)
        self.assertEqual(self.dias("hoy", sabado), [])
        detalle = {p["clave"]: p["detalle"] for p in u.periodos_de_revision(sabado)}
        self.assertEqual(detalle["hoy"], "sin días hábiles")

    def test_nunca_hay_dias_futuros(self):
        for p in u.periodos_de_revision(self.HOY):
            self.assertTrue(all(x <= self.HOY for x in p["dias"]), p["clave"])

    def test_union_sin_repetir_y_en_orden(self):
        dias = u.dias_de_periodos(["hoy", "esta_semana", "ayer"], self.HOY)
        self.assertEqual([x.day for x in dias], [5, 6, 7])

    def test_con_una_fecha_escrita(self):
        dias = u.dias_de_periodos(["hoy"], self.HOY, "01/10/2026")
        self.assertEqual([x.day for x in dias], [1, 7])
        self.assertEqual(len(u.dias_de_periodos([], self.HOY, "01/10/2026")), 1)

    def test_fechas_que_no_sirven(self):
        for claves, texto, esperado in (([], "", "al menos un período"), (["hoy"], "04/10/2026", "fin de semana"),
                                        (["hoy"], "08/10/2026", "todavía no llega"),
                                        (["hoy"], "32/10", "no existe"), (["hoy"], "hola", "Escribe la fecha")):
            with self.subTest(texto=texto, claves=claves):
                with self.assertRaises(ValueError) as caso:
                    u.dias_de_periodos(claves, self.HOY, texto)
                self.assertIn(esperado, str(caso.exception))

    def test_un_periodo_sin_dias_no_sirve_solo(self):
        with self.assertRaises(ValueError):
            u.dias_de_periodos(["hoy"], datetime.date(2026, 10, 3))   # sábado

    def test_formatear_fechas(self):
        self.assertEqual(u.formatear_fechas([datetime.date(2026, 10, 5), datetime.date(2026, 10, 6)]),
                         "05/10/2026,06/10/2026")

    def test_version_del_codigo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            self.assertEqual(u.version_del_codigo(carpeta), 0)
            ruta = os.path.join(carpeta, "a.py")
            open(ruta, "w").close()
            os.utime(ruta, (1_700_000_000, 1_700_000_000))
            open(os.path.join(carpeta, "notas.txt"), "w").close()      # no cuenta
            self.assertEqual(u.version_del_codigo(carpeta), 1_700_000_000)
        self.assertEqual(u.version_del_codigo(os.path.join(tempfile.gettempdir(), "no_existe_xyz")), 0)


class VistaPrevia(unittest.TestCase):
    HOY = "05/10/2026"

    def estado(self, **extra):
        base = {"fecha": self.HOY, "revisado": "05/10/2026 15:52", "bloques": [],
                "sin_firmar": [], "sin_registro": []}
        base.update(extra)
        return base

    def test_libro_lista_lo_que_falta(self):
        bloque = {"curso": "5BB", "hora": "07:50-09:20", "oa": False,
                  "leccionario": True, "asistencia": False, "firma": False}
        r = u.vista_previa_libro(self.estado(sin_registro=[bloque], sin_firmar=[bloque]), self.HOY)
        self.assertTrue(r["hay_trabajo"])
        self.assertEqual(r["puntos"], ["5BB 07:50 · se completará: OA, "
                                       "asistencia (se copia del bloque anterior)"])
        self.assertIn("revisión de las 15:52", r["aviso"])
        self.assertIn("1 bloque por firmar", r["aviso"])
        self.assertIn("la haces tú", r["aviso"])

    def test_libro_al_dia(self):
        r = u.vista_previa_libro(self.estado(), self.HOY)
        self.assertFalse(r["hay_trabajo"])
        self.assertEqual(r["puntos"], ["Todo lo de hoy ya está registrado."])

    def test_libro_sin_revision_de_hoy(self):
        for estado in (None, {"fecha": "04/10/2026"}, self.estado(error="se cortó")):
            with self.subTest(estado=estado):
                r = u.vista_previa_libro(estado, self.HOY)
                self.assertIsNone(r["hay_trabajo"])
                self.assertIn("Todavía no tengo una revisión", r["aviso"])

    def test_subir_cuenta_por_nivel(self):
        with tempfile.TemporaryDirectory() as buzon:
            for nivel, nombres in {"5 basico": ["a.pdf", "b.docx", "c.pptx"],
                                   "6 basico": ["d.xlsx", "~$temp.docx", "e.exe"],
                                   "_errores": ["x.pdf"], "7 basico": []}.items():
                os.makedirs(os.path.join(buzon, nivel))
                for n in nombres:
                    open(os.path.join(buzon, nivel, n), "w").close()
            r = u.vista_previa_subir(buzon)
            self.assertTrue(r["hay_trabajo"])
            self.assertEqual(r["puntos"], ["5 basico: 3 archivos (a.pdf, b.docx y 1 más)",
                                           "6 basico: 1 archivo (d.xlsx)"])
            self.assertIn("1 archivo tiene un formato que no se sube", r["aviso"])

    def test_subir_sin_archivos(self):
        with tempfile.TemporaryDirectory() as buzon:
            os.makedirs(os.path.join(buzon, "5 basico"))
            r = u.vista_previa_subir(buzon)
            self.assertFalse(r["hay_trabajo"])

    def test_subir_sin_carpeta(self):
        r = u.vista_previa_subir(os.path.join(tempfile.gettempdir(), "no_existe_barra_xyz"))
        self.assertIsNone(r["hay_trabajo"])

    def test_simulacion(self):
        lineas = ["=== 5BA ===", "  [SIMULAR] Clase 21: se asignaría a 40 alumnas (06/10 - 06/10).",
                  "  [SALTADA] Clase 22: sin fecha", "  [SIMULAR] Clase 23: se asignaría a 38 alumnas"]
        r = u.vista_previa_simulacion("Asignar clases", lineas)
        self.assertTrue(r["hay_trabajo"])
        self.assertEqual(len(r["puntos"]), 2)
        self.assertIn("1 clase se saltará", r["aviso"])

    def test_simulacion_sin_nada(self):
        r = u.vista_previa_simulacion("Asignar clases", ["=== 5BA ===", "0 pendientes"])
        self.assertFalse(r["hay_trabajo"])

    def test_simulacion_fallida(self):
        r = u.vista_previa_simulacion("Asignar clases", ["Usuario incorrecto"], codigo=1)
        self.assertIsNone(r["hay_trabajo"])
        self.assertIn("usuario o contraseña", r["aviso"])


class Tour(unittest.TestCase):
    def test_pasos_bien_formados(self):
        ids = [p["id"] for p in u.TOUR_PASOS]
        self.assertEqual(len(ids), len(set(ids)))
        for paso in u.TOUR_PASOS:
            self.assertTrue(paso["titulo"].strip() and paso["texto"].strip())

    def test_se_muestra_una_sola_vez(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "tour.json")
            self.assertTrue(u.tour_pendiente(ruta))
            u.marcar_tour_visto(ruta)
            self.assertFalse(u.tour_pendiente(ruta))
            self.assertTrue(u.tour_pendiente(ruta, version=u.TOUR_VERSION + 1))

    def test_archivo_roto_vuelve_a_mostrarlo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "tour.json")
            with open(ruta, "w") as f:
                f.write("{roto")
            self.assertTrue(u.tour_pendiente(ruta))


class Archivos(unittest.TestCase):
    def test_escritura_atomica(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "lista.json")
            u.escribir_atomico(ruta, "uno")
            u.escribir_atomico(ruta, "dos")
            with open(ruta, encoding="utf-8") as f:
                self.assertEqual(f.read(), "dos")
            self.assertEqual(os.listdir(carpeta), ["lista.json"])   # sin temporales


class Monitores(unittest.TestCase):
    def test_formato(self):
        for izq, arriba, der, abajo in u.monitores():
            self.assertLess(izq, der)
            self.assertLess(arriba, abajo)



class AsignaturaAlSubir(unittest.TestCase):
    def test_sugerida_por_el_perfil_sin_importar_tildes_ni_mayusculas(self):
        casos = [({"curso_asignaturas": {"5BA": "Matemática", "5BB": "Matemática", "6BA": "Orientación"}}, "matematica"),
                 ({"curso_asignaturas": {"1MA": "Historia, Geografía y Ciencias Sociales"}}, "historia"),
                 ({"curso_asignaturas": {"5BA": "Lenguaje y Comunicación"}}, "lenguaje"),
                 ({"curso_asignaturas": {"5BA": "Ciencias Naturales"}}, "ciencias"),
                 ({}, "ciencias"), ({"curso_asignaturas": {"5BA": "Asignatura rara"}}, "ciencias")]
        for perfil, esperado in casos:
            self.assertEqual(u.asignatura_sugerida(perfil), esperado, perfil)

    def test_las_asignaturas_ofrecidas_existen_en_webclass(self):
        import webclass_recursos as rec
        for clave, nombre in u.ASIGNATURAS_SUBIDA:
            self.assertIn(clave, rec.ASIGNATURAS, clave)
            self.assertTrue(nombre)

    def test_una_sola_tabla_de_asignaturas(self):
        import webclass_recursos as rec
        self.assertEqual(set(dict(u.ASIGNATURAS_SUBIDA)), set(u.ID_ASIGNATURA), "cada asignatura ofrecida tiene su código")
        self.assertEqual(rec.ASIGNATURAS, u.ID_ASIGNATURA, "el subidor usa la misma tabla")
        self.assertEqual(len(set(u.ID_ASIGNATURA.values())), len(u.ID_ASIGNATURA), "sin códigos repetidos")
        for clave in ("filosofia", "integracion"):            # las que antes solo conocía el planificador
            self.assertIn(clave, u.ID_ASIGNATURA)

    def test_preferencia_guardar_leer_y_casos_raros(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = u.ruta_preferencia_subida(tmp, "ana")
            self.assertEqual(u.leer_preferencia_subida(ruta), {"asignatura": "", "preguntar": True})
            u.guardar_preferencia_subida(ruta, "fisica", preguntar=False)
            self.assertEqual(u.leer_preferencia_subida(ruta), {"asignatura": "fisica", "preguntar": False})
            self.assertNotEqual(ruta, u.ruta_preferencia_subida(tmp, "beto"), "una cuenta no pisa a la otra")
            with self.assertRaises(ValueError):
                u.guardar_preferencia_subida(ruta, "inventada", preguntar=True)
            for basura in ("{roto", "[]", json.dumps({"asignatura": "inventada", "preguntar": False})):
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(basura)
                self.assertEqual(u.leer_preferencia_subida(ruta), {"asignatura": "", "preguntar": True}, basura)

    def test_el_subidor_firma_con_lo_elegido_y_si_no_con_el_perfil(self):
        import subir_carpeta as sc
        import webclass_recursos as rec
        perfil = {"curso_asignaturas": {"5BA": "Matemática"}}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(sc.rutas, "PERSONAL", tmp):
            self.assertEqual(sc.asignatura_principal(perfil, "ana"), rec.ASIGNATURAS["matematica"])
            u.guardar_preferencia_subida(u.ruta_preferencia_subida(tmp, "ana"), "historia", preguntar=False)
            self.assertEqual(sc.asignatura_principal(perfil, "ana"), rec.ASIGNATURAS["historia"])
            self.assertEqual(sc.asignatura_principal(perfil, "beto"), rec.ASIGNATURAS["matematica"], "otra cuenta no se afecta")
            self.assertEqual(sc.destinos_del_perfil(perfil, "ana")["5 basico"], ([rec.NIVELES["5"]], rec.ASIGNATURAS["historia"]))


class OpcionesDePregunta(unittest.TestCase):
    def test_meses_se_calculan_y_calzan_con_el_comando(self):
        opciones = u.opciones_de_pregunta("meses", datetime.date(2026, 11, 3))
        self.assertEqual(opciones[0], {"texto": "Noviembre 2026 (este mes)", "valor": "11/2026"})
        self.assertEqual(opciones[1]["texto"], "Octubre 2026 (mes anterior)")
        self.assertEqual(opciones[-1]["valor"], "03/2026", "desde marzo, el inicio del año escolar")
        self.assertEqual(u.opciones_de_pregunta("meses", datetime.date(2027, 3, 10))[0]["valor"], "03/2027",
                         "al año siguiente no quedan meses viejos")

    def test_lista_escrita_a_mano_se_respeta_y_se_filtra(self):
        lista = [{"texto": "Uno", "valor": "1"}, {"texto": "sin valor"}, "basura"]
        self.assertEqual(u.opciones_de_pregunta(lista), [{"texto": "Uno", "valor": "1"}])
        self.assertEqual(u.opciones_de_pregunta(None), [])


class NivelesDelBuzon(unittest.TestCase):
    def test_nombre_con_tilde_sin_renombrar_la_carpeta(self):
        self.assertEqual(u.nombre_de_nivel("5 basico"), "5° Básico")
        self.assertEqual(u.nombre_de_nivel("1 medio"), "1° Medio")
        self.assertEqual(u.nombre_de_nivel("5 basico Orientacion"), "5° Básico · Orientación")
        self.assertEqual(u.nombre_de_nivel("7 basico educacion fisica"), "7° Básico · Educación Física")
        self.assertEqual(u.nombre_de_nivel("carpeta rara"), "carpeta rara")

    def test_nivel_de_cada_carpeta(self):
        self.assertEqual(u.nivel_de_carpeta("5 basico"), 25)
        self.assertEqual(u.nivel_de_carpeta("5 basico Orientacion"), 25)
        self.assertEqual(u.nivel_de_carpeta("4 medio"), 34)
        self.assertIsNone(u.nivel_de_carpeta("_subidos"))
        self.assertEqual([n for _c, n in u.CARPETAS_NIVEL], list(range(21, 29)) + list(range(31, 35)))

    def test_niveles_del_docente_desde_el_perfil_o_el_nombre_del_curso(self):
        self.assertEqual(u.niveles_del_docente({"curso_niveles": {"5BA": 25, "8BB": 28}}), {25, 28})
        self.assertEqual(u.niveles_del_docente({"curso_ids": {"6BA": 1, "1MB": 2}}), {26, 31})
        self.assertEqual(u.niveles_del_docente({"unidades": [{"curso": "7BA"}]}), {27})
        self.assertEqual(u.niveles_del_docente({}), set())

    def test_ordenar_carpetas_en_orden_de_nivel_y_las_del_docente_primero(self):
        carpetas = ["1 medio", "2 basico", "5 basico Orientacion", "8 basico", "5 basico", "1 basico", "extra"]
        propias, otras = u.ordenar_carpetas(carpetas, {25, 28})
        self.assertEqual(propias, ["5 basico", "5 basico Orientacion", "8 basico"])
        self.assertEqual(otras, ["1 basico", "2 basico", "1 medio", "extra"], "nunca «1 medio» antes de «2 basico»")


class AccesosDirectos(unittest.TestCase):
    def test_atajos(self):
        self.assertEqual(u.atajo_de_letra("a"), "CTRL+ALT+A")
        self.assertEqual(u.atajo_de_letra(""), "")
        self.assertEqual(u.atajo_de_letra("(sin atajo)"), "")
        self.assertEqual(u.letra_del_atajo("Alt+Ctrl+A"), "A")
        self.assertEqual(u.letra_del_atajo("CTRL+ALT+B"), "B")
        self.assertEqual(u.letra_del_atajo("Ctrl+Shift+A"), "")
        self.assertEqual(u.letra_del_atajo(""), "")

    def test_reconoce_los_accesos_de_la_barra_y_los_rotos(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "barra_profe.pyw")
            open(script, "w").close()
            accesos = [{"ruta": "a.lnk", "argumentos": f'"{script}"', "atajo": ""},
                       {"ruta": "b.lnk", "argumentos": '"C:\\\\no\\\\existe\\\\barra_profe.pyw"', "atajo": "Alt+Ctrl+A"},
                       {"ruta": "c.lnk", "argumentos": "", "destino": "notepad.exe"}]
            barra = u.accesos_de_la_barra(accesos)
        self.assertEqual([a["ruta"] for a in barra], ["a.lnk", "b.lnk"], "el del bloc de notas no es de la barra")
        self.assertEqual([a["roto"] for a in barra], [False, True])

    @unittest.skipUnless(sys.platform == "win32", "los accesos directos son de Windows")
    def test_escribir_y_leer_un_acceso_directo(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "Prueba barra.lnk")
            script = os.path.join(tmp, "barra_profe.pyw")
            u.escribir_acceso(ruta, sys.executable, f'"{script}"', tmp, atajo="CTRL+ALT+Q")
            leido = u.leer_acceso(ruta)
        self.assertEqual(os.path.normcase(leido["destino"]), os.path.normcase(sys.executable))
        self.assertEqual(u.script_de_acceso(leido), script)
        self.assertEqual(u.letra_del_atajo(leido["atajo"]), "Q")


class RespaldoDeConfiguracion(unittest.TestCase):
    def test_exportar_e_importar_solo_lo_conocido(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            uno, dos = os.path.join(tmp, "uno.json"), os.path.join(tmp, "sub", "dos.json")
            with open(uno, "w", encoding="utf-8") as f:
                f.write('{"a": 1}')
            mapa = {"datos/uno.json": uno, "datos/dos.json": dos}           # dos.json no existe: no entra
            zip_ = os.path.join(tmp, "respaldo.zip")
            self.assertEqual(u.exportar_configuracion(zip_, mapa, {"perfil": "ana"}), ["datos/uno.json"])
            with zipfile.ZipFile(zip_) as z:
                self.assertEqual(sorted(z.namelist()), ["datos/uno.json", "info.json"])
            # Un respaldo con algo de más (o un nombre raro) solo restaura lo conocido.
            with zipfile.ZipFile(zip_, "a") as z:
                z.writestr("../fuera.json", "malo")
                z.writestr("datos/dos.json", '{"b": 2}')
            with open(uno, "w", encoding="utf-8") as f:
                f.write('{"a": "cambiado"}')
            copia = os.path.join(tmp, "copia.zip")
            importados = u.importar_configuracion(zip_, mapa, copia)
            self.assertEqual(sorted(importados), ["datos/dos.json", "datos/uno.json"])
            with open(uno, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"a": 1})
            self.assertTrue(os.path.isfile(dos))
            self.assertFalse(os.path.exists(os.path.join(tmp, "..", "fuera.json")))
            with zipfile.ZipFile(copia) as z:
                self.assertEqual(json.loads(z.read("datos/uno.json")), {"a": "cambiado"}, "lo de antes queda a salvo")

    def test_un_zip_cualquiera_no_se_importa(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            otro = os.path.join(tmp, "otro.zip")
            with zipfile.ZipFile(otro, "w") as z:
                z.writestr("foto.jpg", "x")
            with self.assertRaises(ValueError):
                u.importar_configuracion(otro, {"datos/uno.json": os.path.join(tmp, "uno.json")},
                                         os.path.join(tmp, "copia.zip"))
            with open(os.path.join(tmp, "texto.zip"), "w") as f:
                f.write("no es zip")
            with self.assertRaises(ValueError):
                u.importar_configuracion(os.path.join(tmp, "texto.zip"), {}, os.path.join(tmp, "copia.zip"))


class CuentaSinConsola(unittest.TestCase):
    def setUp(self):
        import configurar
        self.c = configurar
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.enterContext(mock.patch.object(configurar, "CARPETA_PERFILES", self.tmp))

    def test_rut_y_contrasena_se_validan_antes_de_conectar(self):
        with mock.patch.object(self.c, "entrar") as entrar:
            for rut, clave in (("12.345.678-9", "x"), ("12345678", "x"), ("12345678-9", "")):
                with self.assertRaises(ValueError, msg=rut):
                    self.c.preparar_cuenta(rut, clave)
            entrar.assert_not_called()

    def test_guardar_cuenta_deja_el_perfil_y_la_clave_en_el_llavero(self):
        preparada = {"rut": "12345678-9", "iduser": "7", "colegio": "3", "rol": 13,
                     "curso_ids": {"5BA": 1, "5BB": 2}, "unidades": [{"id": 1}], "curso_niveles": {"5BA": 25},
                     "curso_asignaturas": {"5BA": "Ciencias Naturales"}}
        with mock.patch.object(self.c.keyring, "set_password") as llavero:
            clave = self.c.guardar_cuenta(preparada, "secreta", "Ana Pérez", "5BB")
        llavero.assert_called_once_with(self.c.w.KEYRING_SERVICE, "12345678-9", "secreta")
        self.assertEqual(clave, "ana")
        with open(os.path.join(self.tmp, "ana.json"), encoding="utf-8") as f:
            perfil = json.load(f)
        self.assertEqual((perfil["nombre"], perfil["jefatura"], perfil["curso_niveles"]), ("Ana Pérez", "5BB", {"5BA": 25}))
        self.assertNotIn("secreta", json.dumps(perfil), "la contraseña nunca va al archivo")

    def test_clave_libre_no_pisa_a_otro_docente(self):
        for clave, rut in (("ana", "1-9"), ("ana2", "2-7")):
            with open(os.path.join(self.tmp, f"{clave}.json"), "w", encoding="utf-8") as f:
                json.dump({"rut": rut}, f)
        self.assertEqual(self.c.clave_libre("ana", "1-9"), "ana", "el mismo RUT reusa su perfil")
        self.assertEqual(self.c.clave_libre("ana", "3-5"), "ana3")
        self.assertEqual(self.c.clave_libre("beto", "3-5"), "beto")


class ArchivoDeBotones(unittest.TestCase):
    def test_ida_y_vuelta_conserva_el_formato(self):
        botones = [{"nombre": "Á", "tipo": "url", "destino": "https://x"}]
        for bom in (True, False):
            for crlf in (True, False):
                with self.subTest(bom=bom, crlf=crlf), tempfile.TemporaryDirectory() as tmp:
                    ruta = os.path.join(tmp, "herramientas.json")
                    texto = json.dumps(botones, ensure_ascii=False, indent=2)
                    texto = texto.replace("\n", "\r\n") if crlf else texto
                    with open(ruta, "wb") as f:
                        f.write((b"\xef\xbb\xbf" if bom else b"") + texto.encode("utf-8"))
                    leidos, formato = u.leer_botones(ruta)
                    self.assertEqual((leidos, formato), (botones, {"bom": bom, "crlf": crlf}))
                    u.guardar_botones(ruta, leidos + [{"nombre": "B"}], formato, copia=ruta + ".antes")
                    with open(ruta, "rb") as f:
                        crudo = f.read()
                    self.assertEqual(crudo.startswith(b"\xef\xbb\xbf"), bom)
                    self.assertEqual(b"\r\n" in crudo, crlf)
                    self.assertEqual(len(u.leer_botones(ruta)[0]), 2)
                    self.assertTrue(os.path.isfile(ruta + ".antes"), "copia de seguridad del archivo anterior")

    def test_rechaza_lo_que_no_es_una_lista_de_botones(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "herramientas.json")
            for contenido in ("{roto", "{}", "[1, 2]"):
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(contenido)
                with self.assertRaises(ValueError, msg=contenido):
                    u.leer_botones(ruta)


class AgendaDesdeWebclass(unittest.TestCase):
    """Fase 5: sin asistente, «Ahora / Luego» sale de «Mi horario» de WebClass (la semana tipo)."""

    HORARIO = {"semana": "12/10 al 16/10/2026", "generado": "14/10/2026 23:44", "bloques": [
        {"dia": 0, "inicio": "09:40", "fin": "11:10", "curso": "5BA", "asignatura": "Ciencias Naturales"},
        {"dia": 0, "inicio": "07:50", "fin": "09:20", "curso": "5BB", "asignatura": "Historia, Geografía y Ciencias Sociales"},
        {"dia": 1, "inicio": "07:50", "fin": "09:20", "curso": "6BB", "asignatura": "Ciencias Naturales"},
        {"dia": 0, "inicio": "a las 3", "fin": "", "curso": "8BA", "asignatura": "Ciencias Naturales"},
        "basura"]}

    def test_los_bloques_del_dia_van_en_orden_con_curso_y_asignatura_corta(self):
        lunes = datetime.date(2026, 10, 19)
        bloques = u.bloques_de_horario_webclass(self.HORARIO, lunes)
        self.assertEqual([(b["titulo"], b["inicio"], b["fin"]) for b in bloques],
                         [("5BB · Historia", "07:50", "09:20"), ("5BA · Ciencias", "09:40", "11:10")])
        self.assertEqual(u.bloques_de_horario_webclass(self.HORARIO, datetime.date(2026, 10, 24)), [], "sábado")
        ahora, luego = u.ahora_y_luego(bloques, datetime.datetime(2026, 10, 19, 8, 0))
        self.assertEqual((ahora, luego), ("5BB · Historia · hasta 09:20", "5BA · Ciencias 09:40"))

    def test_se_vuelve_a_leer_si_no_hay_o_tiene_mas_de_una_semana(self):
        hoy = datetime.date(2026, 10, 17)
        self.assertFalse(u.horario_vencido(self.HORARIO, hoy))
        self.assertTrue(u.horario_vencido(self.HORARIO, datetime.date(2026, 10, 22)))
        for malo in ({}, {"bloques": []}, {**self.HORARIO, "error": "sin conexión"}, {**self.HORARIO, "generado": "ayer"}):
            self.assertTrue(u.horario_vencido(malo, hoy), malo)

    def test_nombres_cortos_de_asignatura(self):
        casos = {"Ciencias Naturales": "Ciencias", "Historia, Geografía y Ciencias Sociales": "Historia",
                 "Lenguaje y Comunicación": "Lenguaje", "Educación Física y Salud": "Ed. Física", "Orientación": "Orientación",
                 "Taller Jec Ciencias Avanzadas": "Taller Jec Ci…", "": ""}
        for nombre, corto in casos.items():
            self.assertEqual(u.asignatura_corta(nombre), corto, nombre)


class AsignaturasDeLaCuenta(unittest.TestCase):
    """Fase 5: las asignaturas que ofrece el WebClass de cada cuenta (leídas al configurarla) y la tabla de respaldo."""

    LEIDAS = {"asignaturas_webclass": [{"id": 3, "nombre": "Ciencias Naturales"}, {"id": 50, "nombre": "Música"},
                                       {"id": 51, "nombre": "Educación Física y Salud"}, {"id": 50, "nombre": "Repetida"},
                                       {"id": "x", "nombre": "Mala"}, {"nombre": "Sin id"}, "basura"]}

    def test_sin_lista_de_webclass_queda_la_tabla_de_siempre(self):
        self.assertEqual([(k, n) for k, n, _c in u.asignaturas_de_la_cuenta({})], list(u.ASIGNATURAS_SUBIDA))
        self.assertEqual(u.asignaturas_de_la_cuenta(None)[0][2], u.ID_ASIGNATURA["ciencias"])

    def test_con_la_lista_de_webclass_las_conocidas_conservan_su_clave(self):
        cuenta = u.asignaturas_de_la_cuenta(self.LEIDAS)
        self.assertEqual(cuenta, [("ciencias", "Ciencias Naturales", 3), ("wc50", "Música", 50),
                                  ("wc51", "Educación Física y Salud", 51)])
        self.assertEqual(u.codigo_de_asignatura("wc50", self.LEIDAS), 50)
        self.assertEqual(u.codigo_de_asignatura("ciencias", self.LEIDAS), 3)
        self.assertEqual(u.codigo_de_asignatura("historia", {}), u.ID_ASIGNATURA["historia"], "la tabla de respaldo")

    def test_reconoce_asignaturas_escritas_a_mano(self):
        cuenta = u.asignaturas_de_la_cuenta(self.LEIDAS)
        self.assertEqual(u.asignatura_de_texto("musica", cuenta)[2], 50)
        self.assertEqual(u.asignatura_de_texto("Ed. Física", cuenta)[2], 51)
        self.assertEqual(u.asignatura_de_texto("educacion fisica", cuenta)[2], 51)
        self.assertEqual(u.asignatura_de_texto("Ciencias", cuenta)[2], 3)
        self.assertIsNone(u.asignatura_de_texto("Astrología", cuenta))
        self.assertEqual(u.asignatura_de_texto("Orientacion", u.asignaturas_de_la_cuenta({}))[0], "orientacion")

    def test_carpetas_con_nivel_y_asignatura(self):
        cuenta = u.asignaturas_de_la_cuenta(self.LEIDAS)
        tabla = u.asignaturas_de_la_cuenta({})
        self.assertEqual(u.carpeta_con_asignatura("5 basico Orientacion", tabla), (25, ("orientacion", "Orientación", 9)))
        self.assertEqual(u.carpeta_con_asignatura("7° Básico Música", cuenta), (27, ("wc50", "Música", 50)))
        self.assertEqual(u.carpeta_con_asignatura("1 medio - Historia", tabla)[0], 31)
        for sin_asignatura in ("5 basico", "Música", "5 basico Astrología", "", "carpeta rara"):
            self.assertIsNone(u.carpeta_con_asignatura(sin_asignatura, cuenta), sin_asignatura)

    def test_la_preferencia_acepta_las_claves_de_la_cuenta(self):
        validas = [k for k, _n, _c in u.asignaturas_de_la_cuenta(self.LEIDAS)]
        with tempfile.TemporaryDirectory() as tmp:
            ruta = u.ruta_preferencia_subida(tmp, "ana")
            u.guardar_preferencia_subida(ruta, "wc50", preguntar=False, validas=validas)
            self.assertEqual(u.leer_preferencia_subida(ruta, validas), {"asignatura": "wc50", "preguntar": False})
            self.assertEqual(u.leer_preferencia_subida(ruta)["asignatura"], "", "sin la lista, «wc50» no se conoce")

    def test_el_subidor_reconoce_carpetas_por_su_nombre(self):
        import subir_carpeta as sc
        perfil = {**self.LEIDAS, "curso_asignaturas": {"5BA": "Ciencias Naturales"}}
        with tempfile.TemporaryDirectory() as buzon, tempfile.TemporaryDirectory() as personal, \
                mock.patch.object(sc, "CARPETA", buzon), mock.patch.object(sc.rutas, "PERSONAL", personal):
            for carpeta in ("5 basico", "5 basico Orientacion", "7 basico Musica", "8 basico Astrologia", "_subidos", "otra"):
                os.makedirs(os.path.join(buzon, carpeta))
            destinos = sc.destinos_del_perfil(perfil, "ana")
        self.assertEqual(destinos["5 basico"], ([25], 3))
        self.assertEqual(destinos["7 basico Musica"], ([27], 50))
        self.assertNotIn("5 basico Orientacion", destinos, "Orientación no está entre las asignaturas de esta cuenta")
        for fuera in ("8 basico Astrologia", "_subidos", "otra"):
            self.assertNotIn(fuera, destinos)
        self.assertFalse(hasattr(sc, "ESPECIALES"), "ya no hay lista fija")

    def test_lee_las_asignaturas_del_formulario_de_webclass(self):
        import webclass_recursos as rec
        pagina = """<form><select class="form-control" id="selectSectorLocal" name="selectSectorLocal">
            <option value="0">Seleccione</option><option value="3" selected>Ciencias Naturales</option>
            <option value='50'>M&uacute;sica</option><option data-x="1" value="51"> Educación  Física y Salud </option>
            <option value="3">Repetida</option><option>Sin valor</option></select>
            <select id="otro"><option value="9">No es este</option></select></form>"""
        self.assertEqual(rec.asignaturas_del_formulario(pagina), [
            {"id": 3, "nombre": "Ciencias Naturales"}, {"id": 50, "nombre": "Música"}, {"id": 51, "nombre": "Educación Física y Salud"}])
        self.assertEqual(rec.asignaturas_del_formulario("<html>sin selector</html>"), [])

    def test_lee_las_asignaturas_como_las_entrega_webclass(self):
        """El selector viene vacío y su JavaScript lo llena con class/data.php (case=3): así lo entregó WebClass real."""
        import webclass_recursos as rec
        from types import SimpleNamespace as N
        pagina = ("<script type='text/javascript'> var idcolegio=1795; var idcurr=881</script>"
                  '<select name="selectSectorLocal" id="selectSectorLocal" class="form-control"></select>')
        opciones = ('<option value="-1">- Seleccione asignatura -</option><option value="3">Ciencias Naturales</option>'
                    '<option value="100">ninguno</option><option value="15">Religion</option>')
        pedidos = []

        class Sesion:
            def get(self, url, params=None, **_k):
                pedidos.append((url.rsplit("/", 1)[-1], params))
                return N(text=opciones if url.endswith("data.php") else pagina, raise_for_status=lambda: None)
        self.assertEqual(rec.leer_asignaturas(Sesion()), [{"id": 3, "nombre": "Ciencias Naturales"},
                                                          {"id": 15, "nombre": "Religion"}])
        self.assertEqual(pedidos[-1], ("data.php", {"idcolegio": "1795", "idcurr": "881", "case": 3}))

    def test_la_tabla_de_respaldo_trae_religion_y_las_demas_de_webclass(self):
        """Códigos leídos de WebClass real: aunque la cuenta no haya leído su lista, aparecen para subir."""
        nombres = {n: u.ID_ASIGNATURA[c] for c, n in u.ASIGNATURAS_SUBIDA}
        self.assertEqual((nombres["Religión"], nombres["Inglés"], nombres["Educación Física y Salud"],
                          nombres["Música"], nombres["Artes Visuales"]), (15, 10, 5, 8, 6))
        self.assertIn("Religión", [n for _c, n, _i in u.asignaturas_de_la_cuenta({})])


class MisRegistros(unittest.TestCase):
    """Fase 5: la ventana «Mis registros» lee los CSV del libro, de las subidas y de las tareas."""

    LIBRO = ("﻿corrida;fecha_clase;curso;hora;asignatura;clase;estado;firma\n"
             "01/10/2026 20:00;01/10/2026;5BA;08:00-09:30;Ciencias Naturales;Clase 1;declarado;sin firmar\n"
             "16/10/2026 20:00;15/10/2026;5BB;08:00-09:30;Ciencias Naturales;;PENDIENTE: no hay clase;sin firmar\n"
             "17/10/2026 20:00;16/10/2026;5BA;10:00-11:30;Ciencias Naturales;Clase 3;declarado;firmado\n")
    TAREAS = ("fecha_asignacion,unidad,idunidad,curso,idclase,clase,fecha_clase,alumnas_asignadas\n"
              "2026-10-01,U1,1,5BA,11,Clase 1,2026-10-01,42\n2026-10-16,U1,1,5BB,12,Clase 2,2026-10-15,40\n")
    SUBIDAS = ("﻿fecha;archivo;carpeta;id_recurso;estado;docente\n"
               "15/10/2026 10:00;guia.pdf;5 basico;900;subido;Ana Pérez\n"
               "16/10/2026 10:00;ppt.pptx;6 basico;901;subido;Beto Soto\n"
               "16/10/2026 11:00;antiguo.pdf;6 basico;902;subido;\n")

    def _escribir(self, carpeta, nombre, texto):
        ruta = os.path.join(carpeta, nombre)
        with open(ruta, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
        return ruta

    def test_que_pestana_abre_cada_boton_de_siempre(self):
        self.assertEqual(u.pestana_de_registro("%REGISTRO_LIBRO%"), "Libro")
        self.assertEqual(u.pestana_de_registro("%REGISTRO_TAREAS%"), "Tareas")
        self.assertEqual(u.pestana_de_registro("%BUZON%\\registro_subidas.csv"), "Subidas")
        self.assertIsNone(u.pestana_de_registro("%BARRA%\\otro.csv"))

    def test_lee_con_punto_y_coma_o_coma_lo_mas_nuevo_primero(self):
        with tempfile.TemporaryDirectory() as tmp:
            libro = u.leer_registro(self._escribir(tmp, "libro.csv", self.LIBRO))
            tareas = u.leer_registro(self._escribir(tmp, "tareas.csv", self.TAREAS))
            self.assertEqual(u.leer_registro(os.path.join(tmp, "no_existe.csv")), [])
            self.assertEqual(u.leer_registro(self._escribir(tmp, "vacio.csv", "")), [])
        self.assertEqual([f["clase"] for f in libro], ["Clase 3", "", "Clase 1"])
        self.assertEqual(libro[0]["corrida"], "17/10/2026 20:00", "sin la marca BOM en el nombre de la columna")
        self.assertEqual(tareas[0]["alumnas_asignadas"], "40")

    def test_se_ordena_por_la_fecha_del_registro(self):
        filas = [{"fecha_clase": "14/10/2026", "clase": "b"}, {"fecha_clase": "13/10/2026", "clase": "a"},
                 {"fecha_clase": "", "clase": "sin fecha"}, {"fecha_clase": "14/10/2026", "clase": "c"}]
        self.assertEqual([f["clase"] for f in u.ordenar_por_fecha(filas, "Libro")], ["b", "c", "a", "sin fecha"],
                         "a igual fecha se mantiene el orden (lo último anotado primero)")

    def test_una_fila_con_campos_de_mas_o_de_menos_no_rompe_la_lectura(self):
        texto = "fecha;archivo;estado\n01/10/2026;a.pdf;subido;con un ; de más\n02/10/2026;b.pdf\n"
        with tempfile.TemporaryDirectory() as tmp:
            filas = u.leer_registro(self._escribir(tmp, "raro.csv", texto))
        self.assertEqual(filas[0], {"fecha": "02/10/2026", "archivo": "b.pdf", "estado": ""})
        self.assertEqual(filas[1]["estado"], "subido;con un ; de más")

    def test_filtra_por_fecha_curso_estado_y_docente(self):
        with tempfile.TemporaryDirectory() as tmp:
            libro = u.leer_registro(self._escribir(tmp, "libro.csv", self.LIBRO))
            subidas = u.leer_registro(self._escribir(tmp, "subidas.csv", self.SUBIDAS))
        semana = u.desde_periodo("semana", datetime.date(2026, 10, 17))
        self.assertEqual(semana, datetime.date(2026, 10, 12))
        self.assertEqual(u.desde_periodo("mes", datetime.date(2026, 10, 17)), datetime.date(2026, 10, 1))
        self.assertIsNone(u.desde_periodo("todo", datetime.date(2026, 10, 17)))
        self.assertEqual(len(u.filtrar_registro(libro, "Libro", desde=semana)), 2)
        self.assertEqual([f["clase"] for f in u.filtrar_registro(libro, "Libro", curso="5BA")], ["Clase 3", "Clase 1"])
        self.assertEqual(len(u.filtrar_registro(libro, "Libro", estado="pendiente")), 1)
        self.assertEqual(u.opciones_de_registro(libro, "Libro"), (["5BA", "5BB"], ["declarado", "pendiente"]))
        propias = u.filtrar_registro(subidas, "Subidas", docente="ana pérez")
        self.assertEqual([f["archivo"] for f in propias], ["antiguo.pdf", "guia.pdf"], "las de otro docente del PC no se ven")
        self.assertEqual(u.fecha_de_registro("2026-10-15"), datetime.date(2026, 10, 15))
        self.assertIsNone(u.fecha_de_registro("31/02/2026"))


class PinDeProfesor(unittest.TestCase):
    """El PIN de 4 números de cada profesor en un equipo compartido."""

    def test_guardar_y_comprobar_sin_dejar_el_pin_escrito(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = u.ruta_pin(tmp, "ana")
            self.assertFalse(u.tiene_pin(ruta))
            self.assertFalse(u.pin_correcto(ruta, "1234"), "sin PIN guardado nada es correcto")
            u.guardar_pin(ruta, "4821")
            self.assertTrue(u.tiene_pin(ruta))
            self.assertTrue(u.pin_correcto(ruta, "4821"))
            for malo in ("4822", "482", "48210", "48a1", "", None):
                self.assertFalse(u.pin_correcto(ruta, malo), malo)
            def leer():
                with open(ruta, encoding="utf-8") as f:
                    return f.read()
            contenido = leer()
            self.assertNotIn("4821", contenido, "solo la huella, nunca el PIN")
            u.guardar_pin(ruta, "4821")
            self.assertNotEqual(contenido, leer(), "cada vez con sal nueva")
            self.assertNotEqual(ruta, u.ruta_pin(tmp, "beto"), "un archivo por profesor")

    def test_rechaza_lo_que_no_son_4_numeros_y_los_archivos_rotos(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = u.ruta_pin(tmp, "ana")
            for malo in ("123", "12345", "abcd", " 123", ""):
                with self.assertRaises(ValueError, msg=malo):
                    u.guardar_pin(ruta, malo)
            for roto in ("{roto", "[]", json.dumps({"sal": "zz", "huella": "x"}), json.dumps({"huella": "x"})):
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(roto)
                self.assertFalse(u.pin_correcto(ruta, "1234"), roto)

    def test_la_barra_reabierta_no_vuelve_a_pedir_el_pin_una_sola_vez(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "desbloqueo.json")
            self.assertFalse(u.desbloqueo_vigente(ruta, "ana"))
            u.marcar_desbloqueo(ruta, "ana")
            self.assertFalse(u.desbloqueo_vigente(ruta, "beto"), "solo para el mismo profesor")
            u.marcar_desbloqueo(ruta, "ana")
            self.assertTrue(u.desbloqueo_vigente(ruta, "ana"))
            self.assertFalse(u.desbloqueo_vigente(ruta, "ana"), "sirve una sola vez")
            u.marcar_desbloqueo(ruta, "ana", segundos=-1)
            self.assertFalse(u.desbloqueo_vigente(ruta, "ana"), "vencido")


class ContrasenaDeWebclass(unittest.TestCase):
    """configurar.verificar_contrasena: la que se pide para crear el PIN o si se olvidó."""

    def setUp(self):
        import configurar
        self.c = configurar
        self.llavero = {}
        for nombre, funcion in (("get_password", lambda _s, rut: self.llavero.get(rut)),
                                ("set_password", lambda _s, rut, clave: self.llavero.__setitem__(rut, clave))):
            parche = mock.patch.object(configurar.keyring, nombre, funcion)
            parche.start()
            self.addCleanup(parche.stop)

    def test_si_coincide_con_la_guardada_no_entra_a_webclass(self):
        self.llavero["12345678-9"] = "secreta"
        with mock.patch.object(self.c.w, "login") as login:
            self.c.verificar_contrasena("12345678-9", "secreta")
        login.assert_not_called()

    def test_si_no_coincide_entra_a_webclass_y_guarda_la_nueva(self):
        self.llavero["12345678-9"] = "vieja"
        with mock.patch.object(self.c.w, "login") as login, mock.patch.object(self.c.w, "crear_session"):
            self.c.verificar_contrasena("12345678-9", "nueva")
        login.assert_called_once()
        self.assertEqual(self.llavero["12345678-9"], "nueva")

    def test_una_contrasena_equivocada_se_explica(self):
        self.llavero["12345678-9"] = "vieja"
        error = RuntimeError("Login fallido: Usuario o contraseña incorrecta (accion=0)")
        with mock.patch.object(self.c.w, "login", side_effect=error), mock.patch.object(self.c.w, "crear_session"):
            with self.assertRaises(ValueError) as caso:
                self.c.verificar_contrasena("12345678-9", "otra")
        self.assertIn("no es tu contraseña", str(caso.exception))
        self.assertEqual(self.llavero["12345678-9"], "vieja", "no se toca la guardada")
        with self.assertRaises(ValueError):
            self.c.verificar_contrasena("12345678-9", "")

    def test_sin_internet_el_error_llega_tal_cual(self):
        with mock.patch.object(self.c.w, "login", side_effect=OSError("sin red")), mock.patch.object(self.c.w, "crear_session"):
            with self.assertRaises(OSError):
                self.c.verificar_contrasena("12345678-9", "otra")


class DiasSinClases(unittest.TestCase):
    """Feriados y vacaciones: lo marcado deja de contar como pendiente."""

    LUNES = datetime.date(2026, 10, 5)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)
        self.ruta = os.path.join(self.tmp, "sin_clases_ana.json")

    def test_sin_archivo_o_roto_queda_vacio(self):
        self.assertEqual(u.leer_sin_clases(self.ruta), {"dias": {}, "bloques": {}, "clases": {}})
        with open(self.ruta, "w", encoding="utf-8") as f:
            f.write('{"dias": {"2026-10-12": "Feriado", "no es fecha": "x"}, "bloques": [1, 2]}')
        self.assertEqual(u.leer_sin_clases(self.ruta), {"dias": {"2026-10-12": "Feriado"}, "bloques": {}, "clases": {}})
        with open(self.ruta, "w", encoding="utf-8") as f:
            f.write("{roto")
        self.assertEqual(u.leer_sin_clases(self.ruta)["dias"], {})

    def test_marcar_dias_salta_los_fines_de_semana_y_no_repite(self):
        viernes, sabado = datetime.date(2026, 10, 9), datetime.date(2026, 10, 10)
        self.assertEqual(u.marcar_dias_sin_clases(self.ruta, [viernes, sabado], " Feriado "), ["2026-10-09"])
        self.assertEqual(u.marcar_dias_sin_clases(self.ruta, [viernes], "Salida"), [])
        self.assertEqual(u.leer_sin_clases(self.ruta)["dias"], {"2026-10-09": "Salida"})   # el motivo se actualiza

    def test_dias_para_marcar(self):
        hoy = datetime.date(2026, 10, 18)
        self.assertEqual(u.dias_para_marcar("12/10", hoy=hoy), [datetime.date(2026, 10, 12)])
        rango = u.dias_para_marcar("08/10/2026", "13/10/2026", hoy)          # cruza un fin de semana
        self.assertEqual([d.day for d in rango], [8, 9, 12, 13])
        self.assertEqual(len(u.dias_para_marcar("20/07", "31/07", hoy)), 10)   # vacaciones que ya pasaron
        self.assertEqual(len(u.dias_para_marcar("21/12", "", hoy)), 1)        # o que vienen
        for desde, hasta, error in (("13/10", "08/10", "antes del primero"), ("10/10", "11/10", "fin de semana"),
                                    ("01/03", "31/10", "como máximo"), ("31/02", "", "no existe"),
                                    ("mañana", "", "día/mes/año")):
            with self.subTest(desde=desde), self.assertRaises(ValueError) as caso:
                u.dias_para_marcar(desde, hasta, hoy)
            self.assertIn(error, str(caso.exception))

    def test_bloques_y_clases_sueltos_y_quitar(self):
        clave = "5BA|08:00-09:30|123|2026-10-05"
        u.ignorar_en_sin_clases(self.ruta, "bloques", clave, "05/10 5BA 08:00")
        u.ignorar_en_sin_clases(self.ruta, "clases", 98765, "5BA · Clase 3")
        datos = u.leer_sin_clases(self.ruta)
        self.assertTrue(u.bloque_sin_clase(datos, "5BA|08:00-09:30|123", self.LUNES))      # sin fecha en la clave
        self.assertTrue(u.bloque_sin_clase(datos, clave, self.LUNES))
        self.assertFalse(u.bloque_sin_clase(datos, "5BA|08:00-09:30|124", self.LUNES))
        self.assertFalse(u.bloque_sin_clase(datos, "5BA|08:00-09:30|123", datetime.date(2026, 10, 6)))
        self.assertTrue(u.bloque_sin_clase_por_hora(datos, "5BA", "08:00", self.LUNES))     # el informe del mes
        self.assertFalse(u.bloque_sin_clase_por_hora(datos, "5BA", "08:0", self.LUNES))
        self.assertTrue(u.clase_sin_tarea(datos, "98765", "06/10/2026"))
        self.assertFalse(u.clase_sin_tarea(datos, "11111", "06/10/2026"))
        u.quitar_sin_clases(self.ruta, "bloques", [clave])
        u.quitar_sin_clases(self.ruta, "clases", ["98765"])
        self.assertEqual(u.leer_sin_clases(self.ruta), {"dias": {}, "bloques": {}, "clases": {}})

    def test_un_dia_marcado_cubre_sus_bloques_y_sus_tareas(self):
        u.marcar_dias_sin_clases(self.ruta, [self.LUNES])
        datos = u.leer_sin_clases(self.ruta)
        self.assertTrue(u.bloque_sin_clase(datos, "5BA|08:00-09:30|123", self.LUNES))
        self.assertTrue(u.bloque_sin_clase_por_hora(datos, "6BB", "11:20", self.LUNES))
        self.assertTrue(u.clase_sin_tarea(datos, "1", "05/10/2026"))
        self.assertFalse(u.clase_sin_tarea(datos, "1", ""))                    # una clase sin fecha, no

    def estado(self, **cambios):
        b1 = {"curso": "5BA", "id": 123, "hora": "08:00-09:30", "oa": False, "leccionario": False,
              "asistencia": True, "firma": False}
        b2 = {"curso": "6BB", "id": 124, "hora": "11:20-12:50", "oa": True, "leccionario": True,
              "asistencia": True, "firma": False}
        base = {"fecha": "05/10/2026", "bloques": [b1, b2], "sin_firmar": [b1, b2], "sin_registro": [b1],
                "atrasados": [{"fecha": "02/10/2026", "bloques": 2, "cursos": ["5BA", "6BB"],
                               "claves": ["5BA|08:00-09:30|1|2026-10-02", "6BB|10:00-11:30|2|2026-10-02"]},
                              {"fecha": "01/10/2026", "bloques": 1, "cursos": ["7BA"]}]}
        base.update(cambios)
        return base

    def test_aplicar_a_la_tarjeta_hoy(self):
        sin_nada = u.aplicar_sin_clases(self.estado(), u.leer_sin_clases(self.ruta))
        self.assertEqual(sin_nada, self.estado())
        u.ignorar_en_sin_clases(self.ruta, "bloques", "5BA|08:00-09:30|123|2026-10-05")
        u.ignorar_en_sin_clases(self.ruta, "bloques", "6BB|10:00-11:30|2|2026-10-02")
        u.marcar_dias_sin_clases(self.ruta, [datetime.date(2026, 10, 1)])
        r = u.aplicar_sin_clases(self.estado(), u.leer_sin_clases(self.ruta))
        self.assertEqual([b["curso"] for b in r["sin_firmar"]], ["6BB"])
        self.assertEqual(r["sin_registro"], [])
        self.assertEqual(r["atrasados"], [{"fecha": "02/10/2026", "bloques": 1, "cursos": ["5BA"],
                                           "claves": ["5BA|08:00-09:30|1|2026-10-02"]}])
        self.assertEqual(len(self.estado()["sin_firmar"]), 2, "no cambia el estado original")

    def test_hoy_marcado_sin_clases(self):
        u.marcar_dias_sin_clases(self.ruta, [self.LUNES], "Feriado")
        r = u.aplicar_sin_clases(self.estado(), u.leer_sin_clases(self.ruta))
        self.assertTrue(r["sin_clases"])
        self.assertEqual((r["bloques"], r["sin_firmar"], r["sin_registro"]), ([], [], []))
        self.assertEqual(len(r["atrasados"]), 2)                            # los días anteriores siguen
        previa = u.vista_previa_libro(r, "05/10/2026")
        self.assertIs(previa["hay_trabajo"], False)
        self.assertIn("sin clases", previa["puntos"][0])

    def test_estado_con_error_o_vacio_no_se_toca(self):
        datos = {"dias": {"2026-10-05": ""}, "bloques": {}, "clases": {}}
        self.assertEqual(u.aplicar_sin_clases({"fecha": "05/10/2026", "error": "x"}, datos),
                         {"fecha": "05/10/2026", "error": "x"})
        self.assertIsNone(u.aplicar_sin_clases(None, datos))

    def test_la_vista_previa_del_libro_ofrece_marcar_cada_bloque(self):
        previa = u.vista_previa_libro(dict(self.estado(), revisado="05/10/2026 10:00"), "05/10/2026")
        marca = previa["items"][0]["sin_clase"]
        self.assertEqual(marca, {"campo": "bloques", "clave": "5BA|08:00-09:30|123|2026-10-05", "dia": "2026-10-05",
                                 "titulo": "05/10 5BA 08:00"})

    def test_los_items_traen_como_marcarlos(self):
        linea = ('##ITEM {"clave": "98765", "estado": "propuesto", "titulo": "5BA · Clase 3", '
                 '"sin_clase": {"campo": "clases", "clave": 98765, "dia": "2026-10-05", "titulo": "5BA · Clase 3"}}')
        it = u.parsear_item(linea)
        self.assertEqual(it["sin_clase"], {"campo": "clases", "clave": "98765", "dia": "2026-10-05",
                                           "titulo": "5BA · Clase 3"})
        previa = u.vista_previa_simulacion("Asignar", [], 0, [it])
        self.assertEqual(previa["items"][0]["sin_clase"]["clave"], "98765")
        for malo in ('"sin_clase": {"campo": "otra", "clave": "1"}', '"sin_clase": {"campo": "clases"}',
                     '"sin_clase": "1"'):
            with self.subTest(malo=malo):
                self.assertNotIn("sin_clase", u.parsear_item('##ITEM {"clave": "1", "estado": "propuesto", ' + malo + "}"))

    def test_tramos_juntan_los_dias_seguidos_con_el_mismo_motivo(self):
        dias = {"2026-07-20": "Vacaciones", "2026-07-21": "Vacaciones", "2026-07-22": "Vacaciones",
                "2026-07-23": "Vacaciones", "2026-07-24": "Vacaciones", "2026-07-27": "Vacaciones",
                "2026-07-28": "Salida", "2026-10-12": "Feriado"}
        tramos = u.tramos_sin_clases(dias)
        self.assertEqual([t["motivo"] for t in tramos], ["Feriado", "Salida", "Vacaciones"])   # lo más reciente arriba
        self.assertEqual(tramos[0]["texto"], "lun 12/10/2026")
        self.assertEqual(tramos[2]["texto"], "lun 20/07 al lun 27/07/2026 (6 días)")   # cruza el fin de semana
        self.assertEqual(len(tramos[2]["dias"]), 6)

    def test_ruta_por_docente(self):
        import rutas
        self.assertTrue(rutas.sin_clases("ana").endswith("sin_clases_ana.json"))
        self.assertNotEqual(rutas.sin_clases("ana"), rutas.sin_clases("beto"))


if __name__ == "__main__":
    unittest.main()
