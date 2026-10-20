"""Pruebas de «Registrar libro» con una sesión falsa (nunca toca Webclass).

Comprueba lo que el docente necesita ver: qué se intentó, qué se hizo, qué no
y por qué, y que lo desmarcado en la vista previa se respete.
"""

import contextlib
import datetime
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import webclass_libro as L  # noqa: E402
import webclass_tareas as w  # noqa: E402

FECHA = datetime.date(2026, 10, 5)
PERFIL = {"iduser": "7", "curso_ids": {"5BA": 1, "6BA": 2, "7BA": 3, "8BA": 4}}


def bloque(inicio, termino, id_detalle, asignatura="Ciencias", oa=False, lecc=False,
           asist=True, firma=False, profesor="7"):
    return {"id": 1, "id_bloque_detalle": id_detalle, "inicio": inicio, "termino": termino,
            "nombreAsignatura": asignatura, "profesor_id": profesor, "nivel": 5,
            "val_oa": oa, "val_leccionario": lecc, "val_asistencia": asist, "val_firma": firma}


class RegistrarDia(unittest.TestCase):
    def setUp(self):
        w.ITEMS.clear()
        self.escrituras = []
        self.listar_original = w.listar_clases
        w.listar_clases = lambda session, id_unidad: []     # nada toca Webclass
        self.guardados = {}
        for nombre in ("bloques_de_cursos", "unidades_vigentes", "clase_del_dia", "api_post",
                       "asignatura_del_bloque", "registrar", "replicar_asistencia"):
            self.guardados[nombre] = getattr(L, nombre)
        L.registrar = lambda fila: None
        L.api_post = lambda s, ruta, params, token: self.escrituras.append(ruta)
        L.asignatura_del_bloque = lambda *a, **k: 99
        L.unidades_vigentes = lambda *a, **k: [{"id": 1}]
        self.clases = {"5BA": [({"id": 1}, {"idclase": "c1", "nombre": "Clase 21"})],
                       "6BA": [], "7BA": [({"id": 1}, {"idclase": "c2", "nombre": "A"}),
                                          ({"id": 1}, {"idclase": "c3", "nombre": "B"})],
                       "8BA": [({"id": 1}, {"idclase": "c4", "nombre": "Clase 9"})]}
        self.curso_actual = {}

        def clase_del_dia(session_plan, unidades, fecha, cache):
            return self.clases[self.curso_actual["curso"]]
        L.clase_del_dia = clase_del_dia
        original_unidades = L.unidades_vigentes

        def unidades(s, token, curso_id, nivel, asig, fecha, cache, perfil):
            self.curso_actual["curso"] = {v: k for k, v in PERFIL["curso_ids"].items()}[curso_id]
            return original_unidades()
        L.unidades_vigentes = unidades
        L.replicar_asistencia = lambda *a, **k: (None, "sin bloque anterior con el curso completo (40 alumnas)")
        self.dia = {
            "5BA": [bloque("08:00", "09:30", 11)],                          # se puede declarar
            "6BA": [bloque("09:40", "11:10", 12)],                          # no hay clase con esa fecha
            "7BA": [bloque("11:20", "12:50", 13, asist=False)],             # dos clases + asistencia en blanco
            "8BA": [bloque("13:35", "15:05", 14, oa=True, lecc=True)],      # ya estaba
        }
        L.bloques_de_cursos = lambda *a, **k: self.dia

    def tearDown(self):
        for nombre, valor in self.guardados.items():
            setattr(L, nombre, valor)
        w.listar_clases = self.listar_original
        w.ITEMS.clear()

    def correr(self, seleccion=None, simular=False):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            resumen, sin_firma = L.registrar_dia(None, PERFIL, FECHA, "t", datetime.datetime.now(),
                                                 None, simular, seleccion=seleccion)
        return salida.getvalue(), sin_firma

    def estados(self):
        return {(i["grupo"], i["que"]): i["estado"] for i in w.ITEMS}

    def test_informa_lo_que_hizo_y_lo_que_no(self):
        _salida, sin_firma = self.correr()
        self.assertEqual(self.estados(), {
            ("5BA", "OA y leccionario"): "hecho",
            ("6BA", "OA y leccionario"): "pendiente",
            ("7BA", "asistencia"): "pendiente",
            ("7BA", "OA y leccionario"): "pendiente",
            ("8BA", "OA y leccionario"): "ya",
        })
        self.assertEqual(self.escrituras, ["plan-add-class", "declare-oas"])   # solo escribió 5BA
        self.assertEqual(len(sin_firma), 4)

    def test_lo_desmarcado_no_se_toca(self):
        seleccion = {L.clave_bloque("6BA", "09:40-11:10", 12)}
        _salida, _firmas = self.correr(seleccion=seleccion)
        estados = self.estados()
        self.assertEqual(estados[("6BA", "OA y leccionario")], "pendiente")   # lo único marcado
        self.assertEqual(estados[("5BA", "bloque")], "omitido")
        self.assertEqual(estados[("7BA", "bloque")], "omitido")
        self.assertEqual(estados[("8BA", "bloque")], "omitido")
        self.assertEqual(self.escrituras, [])                                  # no se escribió nada

    def test_seleccion_tolera_claves_sin_id(self):
        _s, _f = self.correr(seleccion={"5BA|08:00-09:30"})
        self.assertEqual(self.estados()[("5BA", "OA y leccionario")], "hecho")
        self.assertEqual(self.estados()[("6BA", "bloque")], "omitido")

    def test_simular_no_escribe_y_propone(self):
        self.correr(simular=True)
        self.assertEqual(self.estados()[("5BA", "OA y leccionario")], "propuesto")
        self.assertEqual(self.escrituras, [])

    def test_un_bloque_que_falla_no_impide_informar_los_demas(self):
        original = L.asignatura_del_bloque

        def roto(*a, **k):
            raise RuntimeError("Webclass respondió 419 (sesión expirada)")
        L.asignatura_del_bloque = roto
        try:
            self.correr()
        finally:
            L.asignatura_del_bloque = original
        estados = self.estados()
        self.assertEqual(estados[("5BA", "bloque")], "error")
        self.assertEqual(estados[("8BA", "OA y leccionario")], "ya")           # siguió con el resto

    def test_el_resultado_se_entiende(self):
        self.correr()
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            w.imprimir_resultado(w.ITEMS, ["5BA 08:00-09:30 Ciencias"])
        texto = salida.getvalue()
        self.assertIn("Intenté: 5", texto)                    # 5BA, 6BA, 7BA (OA y asistencia), 8BA
        self.assertIn("Hice (1):", texto)
        self.assertIn("No pude (3):", texto)
        self.assertIn("Tu planificación no tiene una clase con esa fecha", texto)
        self.assertIn("Hay varias clases con esa fecha", texto)
        self.assertIn("Qué hacer:", texto)
        self.assertIn("Ya estaba hecho (1):", texto)
        self.assertIn("FALTA TU FIRMA", texto)

    def test_resultado_vacio_explica_por_que(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            w.imprimir_resultado([], vacio="No tienes clases ese día.")
        self.assertIn("No tienes clases ese día.", salida.getvalue())


class Seleccion(unittest.TestCase):
    def test_leer_seleccion(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "s.json")
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump({"claves": ["a", "b"]}, f)
            self.assertEqual(w.leer_seleccion(ruta), {"a", "b"})
        self.assertIsNone(w.leer_seleccion(None))

    def test_dias_de_meses(self):
        hoy = datetime.date(2026, 10, 7)
        dias = w.dias_de_meses("09/2026,10/2026", hoy)
        self.assertEqual(len(dias), 30 + 7)                        # septiembre entero + 1..7 de octubre
        self.assertIn("30/09/2026", dias)
        self.assertIn("07/10/2026", dias)
        self.assertNotIn("08/10/2026", dias)                       # lo que no ha llegado no cuenta
        self.assertEqual(w.dias_de_meses("10/2026", hoy), {f"{d:02d}/10/2026" for d in range(1, 8)})

    def test_dias_de_meses_mal_escritos(self):
        hoy = datetime.date(2026, 10, 7)
        for texto in ("septiembre", "13/2026", "11/2026"):
            with self.subTest(texto=texto):
                with self.assertRaises(ValueError):
                    w.dias_de_meses(texto, hoy)

    def test_registro_por_docente(self):
        import rutas
        propio = rutas.registro("registro_libro", rutas.dueno_del_registro_historico())
        otro = rutas.registro("registro_libro", "otra_docente_xyz")
        self.assertTrue(propio.endswith("registro_libro.csv"))
        self.assertTrue(otro.endswith("registro_libro_otra_docente_xyz.csv"))
        self.assertNotEqual(propio, otro)                 # las filas de un docente no son del otro

    def test_el_registro_de_asignaciones_tambien_es_por_docente(self):
        import rutas
        dueno = rutas.dueno_del_registro_historico()
        self.assertTrue(w.archivo_registro(dueno).endswith("registro_asignaciones.csv"))
        self.assertTrue(w.archivo_registro("otra_docente_xyz")
                        .endswith("registro_asignaciones_otra_docente_xyz.csv"))
        self.assertTrue(os.path.isabs(w.archivo_registro("otra_docente_xyz")))   # siempre en datos\\


class AsignarConDiasSinClases(unittest.TestCase):
    """«Asignar clases» no ofrece ni asigna una clase de un día sin clases ni una marcada «no hubo esta clase»."""

    def test_simular_salta_lo_marcado_y_ofrece_marcar_lo_demas(self):
        import argparse
        import shutil
        import tempfile
        from unittest import mock

        import barra_utiles as bu
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        ruta = os.path.join(tmp, "sin_clases_ana.json")
        bu.marcar_dias_sin_clases(ruta, [datetime.date(2026, 10, 12)], "Feriado")
        bu.ignorar_en_sin_clases(ruta, "clases", "c3", "5BA · Clase 3")
        perfil = {"rut": "1-9", "iduser": "7", "unidades": [{"curso": "5BA", "id": 5, "nombre": "U1"}],
                  "curso_ids": {"5BA": 1}}
        args = argparse.Namespace(perfil="ana", guardar_clave=False, ver_destinos=False, destinos=False,
                                  rehacer_destinos=False, opciones_destino=None, seleccion=None,
                                  guardar_unidades=False, buscar_unidades=False, unidades=None, meses=None,
                                  fecha=None, hoy=False, dias_atras=0, simular=True)
        clases = [{"idclase": f"c{n}", "nombre": f"Clase {n}", "fechaini": f"1{n + 1}/10/2026",
                   "fechafin": f"1{n + 1}/10/2026", "asignados": 0} for n in (1, 2, 3)]
        w.ITEMS.clear()
        self.addCleanup(w.ITEMS.clear)
        salida = io.StringIO()
        with mock.patch.multiple(w, parse_args=lambda: args, PERFILES={"ana": perfil}, obtener_password=lambda r: "x",
                                 crear_session=lambda: None, login=lambda *a: None, verificar_sesion=lambda *a: None,
                                 archivo_registro=lambda p: os.path.join(tmp, "registro.csv"),
                                 destinos_elegidos=lambda: {}, unidades_nuevas=lambda *a, **k: ([], False),
                                 listar_clases=lambda s, u: clases,
                                 datos_clase=lambda *a: {"idcolegio": 1, "idprofesor": 2, "iduser": 7},
                                 listar_alumnas=lambda *a: ["a", "b"]), \
                mock.patch.object(w.rutas, "sin_clases", lambda p: ruta), contextlib.redirect_stdout(salida):
            w.main()
        self.assertEqual([i["clave"] for i in w.ITEMS if i["estado"] == "propuesto"], ["c2"])
        self.assertIn("[SIN CLASES] Clase 1: marcaste que no hubo esa clase (12/10/2026)", salida.getvalue())
        self.assertIn("[SIN CLASES] Clase 3", salida.getvalue())
        self.assertEqual(w.ITEMS[0]["sin_clase"], {"campo": "clases", "clave": "c2", "dia": "2026-10-13",
                                                   "titulo": "5BA · Clase 2 (13/10/2026)"})


class OpcionesDeDestino(unittest.TestCase):
    """`asignar --opciones-destino`: solo consulta las unidades pedidas."""

    def setUp(self):
        self.guardados = {n: getattr(w, n) for n in ("listar_clases", "datos_clase",
                                                      "destinos_de_clase")}
        self.consultadas = []

        def listar(session, id_unidad):
            self.consultadas.append(str(id_unidad))
            return [] if str(id_unidad) == "2" else [{"idclase": f"c{id_unidad}"}]
        w.listar_clases = listar
        w.datos_clase = lambda *a, **k: {}
        w.destinos_de_clase = lambda *a, **k: [{"id": 10, "nombre": "5BA"},
                                               {"id": 99, "nombre": "T.J Ciencias"}]

    def tearDown(self):
        for nombre, valor in self.guardados.items():
            setattr(w, nombre, valor)

    def test_solo_consulta_las_pedidas_y_informa_cada_una(self):
        import json
        perfil = {"unidades": [{"id": 1, "curso": "5BA"}, {"id": 2, "curso": "5BB"},
                               {"id": 3, "curso": "7BA"}]}
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            w.opciones_de_unidades(None, perfil, ["1", "2", "9"])
        self.assertEqual(self.consultadas, ["1", "2"])                # la 3 no se tocó; la 9 no existe
        lineas = [json.loads(l[len("##OPCIONES "):]) for l in salida.getvalue().splitlines()
                  if l.startswith("##OPCIONES ")]
        self.assertEqual([l["unidad"] for l in lineas], ["1", "2", "9"])
        self.assertEqual([o["nombre"] for o in lineas[0]["opciones"]], ["5BA", "T.J Ciencias"])
        self.assertEqual(lineas[1]["error"], "la unidad no tiene clases")
        self.assertEqual(lineas[2]["error"], "esa unidad no está en tu perfil")
        self.assertIn("##PROGRESO 3/3", salida.getvalue())

    def test_un_error_de_red_no_corta_las_demas(self):
        import json

        def listar(session, id_unidad):
            if str(id_unidad) == "1":
                raise RuntimeError("Webclass no respondió")
            return [{"idclase": "c"}]
        w.listar_clases = listar
        perfil = {"unidades": [{"id": 1, "curso": "5BA"}, {"id": 3, "curso": "7BA"}]}
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            w.opciones_de_unidades(None, perfil, ["1", "3"])
        lineas = [json.loads(l[len("##OPCIONES "):]) for l in salida.getvalue().splitlines()
                  if l.startswith("##OPCIONES ")]
        self.assertIn("Webclass no respondió", lineas[0]["error"])
        self.assertEqual(len(lineas[1]["opciones"]), 2)


if __name__ == "__main__":
    unittest.main()
