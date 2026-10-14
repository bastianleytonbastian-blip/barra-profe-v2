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


if __name__ == "__main__":
    unittest.main()
