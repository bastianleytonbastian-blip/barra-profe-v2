"""Registrar el libro hacia atrás, elegir la clase a mano y listar lo pendiente.

Todo con una sesión falsa: nada toca Webclass.
"""

import contextlib
import datetime
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import webclass_libro as L  # noqa: E402
import webclass_tareas as w  # noqa: E402

PERFIL = {"iduser": "7", "curso_ids": {"4BA": 1}}
LUNES, MARTES, MIERCOLES = (datetime.date(2026, 10, d) for d in (5, 6, 7))
SABADO = datetime.date(2026, 10, 3)


def bloque(inicio, id_detalle, oa=False, lecc=False, asist=True, firma=False):
    return {"id": 1, "id_bloque_detalle": id_detalle, "inicio": inicio, "termino": "00:00",
            "nombreAsignatura": "Ciencias Naturales", "profesor_id": "7", "nivel": 24,
            "val_oa": oa, "val_leccionario": lecc, "val_asistencia": asist, "val_firma": firma}


CLASES = [{"idclase": "c19", "nombre": "19. Fuerzas: Deformación", "fechaini": "30/09/2026"},
          {"idclase": "c18", "nombre": "18. Repaso de fuerzas", "fechaini": "29/09/2026"},
          {"idclase": "c20", "nombre": "20. Fuerzas de contacto", "fechaini": "14/10/2026"},
          {"idclase": "cx", "nombre": "Para más adelante", "fechaini": None}]


class Base(unittest.TestCase):
    def setUp(self):
        w.ITEMS.clear()
        self.escrituras = []
        self.leidos = []
        nombres = ("bloques_de_cursos", "unidades_vigentes", "api_post", "asignatura_del_bloque",
                   "registrar", "replicar_asistencia")
        self.guardados = {n: getattr(L, n) for n in nombres}
        self.listar_original = w.listar_clases
        w.listar_clases = lambda session, id_unidad: self.clases
        self.clases = list(CLASES)
        L.registrar = lambda fila: None
        L.api_post = lambda s, ruta, params, token: self.escrituras.append((ruta, params))
        L.asignatura_del_bloque = lambda *a, **k: 99
        L.unidades_vigentes = lambda *a, **k: [{"id": 5, "nombre": "Unidad 3"}]
        L.replicar_asistencia = lambda *a, **k: (object(), "replicada desde 11:20")
        self.por_fecha = {}
        self.bloques_pedidos = []

        def bloques(s, cursos, fecha, iduser, token, solo_mios=True, trabajadores=4, al_terminar=None):
            self.bloques_pedidos.append(fecha)
            if al_terminar:
                for i, c in enumerate(cursos, 1):
                    al_terminar(c, i, len(cursos))
            return {c: self.por_fecha.get(fecha, []) for c in cursos}
        L.bloques_de_cursos = bloques

    def tearDown(self):
        for n, v in self.guardados.items():
            setattr(L, n, v)
        w.listar_clases = self.listar_original
        w.ITEMS.clear()

    def correr_dia(self, fecha, **k):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            return L.registrar_dia(None, PERFIL, fecha, "t", datetime.datetime.now(), None,
                                   k.pop("simular", False), **k)

    def correr_rango(self, desde, hasta, **k):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            r = L.registrar_rango(None, PERFIL, desde, hasta, "t", datetime.datetime.now(), None,
                                  k.pop("simular", False), **k)
        return r, salida.getvalue()


class ClaseAMano(Base):
    def setUp(self):
        super().setUp()
        self.por_fecha[MARTES] = [bloque("12:50", 701, asist=True)]

    def test_sin_clase_ese_dia_explica_hasta_donde_llega_la_planificacion(self):
        self.correr_dia(MARTES)
        it = [i for i in w.ITEMS if i["que"] == "OA y leccionario"][0]
        self.assertEqual(it["estado"], "pendiente")
        self.assertIn("no hay clase con esa fecha en la planificación", it["motivo"])
        self.assertIn("la última con fecha es «19. Fuerzas: Deformación» del 30/09", it["motivo"])
        self.assertIn("la siguiente es «20. Fuerzas de contacto» del 14/10", it["motivo"])
        self.assertEqual(self.escrituras, [])

    def test_ofrece_las_clases_mas_cercanas_para_elegir(self):
        self.correr_dia(MARTES)
        it = [i for i in w.ITEMS if i["que"] == "OA y leccionario"][0]
        textos = [o["texto"] for o in it["opciones"]]
        self.assertEqual(it["opciones"][0]["id"], "c19")                # la más cercana primero
        self.assertIn("19. Fuerzas: Deformación · 30/09", textos)
        self.assertTrue(any("sin fecha" in t for t in textos))          # también las sin fecha

    def test_la_clase_elegida_a_mano_se_declara(self):
        clave = L.clave_bloque("4BA", "12:50-00:00", 701)
        self.correr_dia(MARTES, elecciones={clave: "c19"})
        escrituras = dict(self.escrituras)
        self.assertEqual(escrituras["plan-add-class"]["classID"], "c19")
        self.assertEqual(escrituras["plan-add-class"]["date"], "2026-10-06")   # en el día del bloque
        self.assertEqual([i["estado"] for i in w.ITEMS if i["que"] == "OA y leccionario"], ["hecho"])

    def test_una_eleccion_inexistente_no_inventa_nada(self):
        clave = L.clave_bloque("4BA", "12:50-00:00", 701)
        self.correr_dia(MARTES, elecciones={clave: "no_existe"})
        self.assertEqual(self.escrituras, [])
        self.assertEqual([i["estado"] for i in w.ITEMS if i["que"] == "OA y leccionario"], ["pendiente"])

    def test_dos_clases_la_misma_fecha_ofrece_las_dos(self):
        self.clases = CLASES + [{"idclase": "dup", "nombre": "19b. Otra del mismo día",
                                 "fechaini": "06/10/2026"},
                                {"idclase": "dup2", "nombre": "19c. Y otra", "fechaini": "06/10/2026"}]
        self.correr_dia(MARTES)
        it = [i for i in w.ITEMS if i["que"] == "OA y leccionario"][0]
        self.assertIn("2 clases con esa fecha", it["motivo"])
        self.assertEqual({o["id"] for o in it["opciones"]}, {"dup", "dup2"})

    def test_sin_unidades_para_la_asignatura_lo_dice(self):
        L.unidades_vigentes = lambda *a, **k: []
        self.correr_dia(MARTES)
        it = [i for i in w.ITEMS if i["que"] == "OA y leccionario"][0]
        self.assertIn("no encontré unidades de «Ciencias Naturales»", it["motivo"])
        self.assertEqual(it.get("opciones", []), [])

    def test_la_asistencia_sigue_su_camino_aunque_falte_la_clase(self):
        self.por_fecha[MARTES] = [bloque("12:50", 701, asist=False)]
        self.correr_dia(MARTES)
        estados = {i["que"]: i["estado"] for i in w.ITEMS}
        self.assertEqual(estados["asistencia"], "hecho")
        self.assertEqual(estados["OA y leccionario"], "pendiente")


class HaciaAtras(Base):
    def setUp(self):
        super().setUp()
        self.por_fecha = {
            LUNES: [bloque("08:00", 801)],                              # falta OA y leccionario
            MARTES: [bloque("12:50", 802, asist=False)],                # falta todo
            MIERCOLES: [bloque("09:40", 803, oa=True, lecc=True)],      # completo
        }

    def test_lista_solo_lo_pendiente_agrupado_por_dia(self):
        (resumen, _firmas), _salida = self.correr_rango(LUNES, MIERCOLES, solo_listar=True)
        items = [i for i in w.ITEMS if i["estado"] == "propuesto"]
        self.assertEqual([i["grupo"] for i in items], ["lun 05/10", "mar 06/10"])
        self.assertEqual(items[0]["detalle"], "se completará: OA, leccionario")
        self.assertEqual(items[1]["detalle"], "se completará: OA, leccionario, asistencia")
        self.assertTrue(items[0]["clave"].endswith("|2026-10-05"))      # la fecha va en la clave
        self.assertEqual(self.escrituras, [])

    def test_listar_no_consulta_la_planificacion(self):
        w.listar_clases = lambda *a, **k: self.fail("no debía consultar la planificación")
        L.unidades_vigentes = lambda *a, **k: self.fail("no debía consultar unidades")
        self.correr_rango(LUNES, MIERCOLES, solo_listar=True)

    def test_registra_cada_dia_con_su_fecha(self):
        self.clases = [{"idclase": "c5", "nombre": "Clase 5", "fechaini": "05/10/2026"},
                       {"idclase": "c6", "nombre": "Clase 6", "fechaini": "06/10/2026"}]
        self.correr_rango(LUNES, MIERCOLES)
        fechas = [p["date"] for ruta, p in self.escrituras if ruta == "plan-add-class"]
        self.assertEqual(fechas, ["2026-10-05", "2026-10-06"])
        hechos = {i["clave"].split("|")[-1] for i in w.ITEMS if i["estado"] == "hecho"
                  and i["que"] == "OA y leccionario"}
        self.assertEqual(hechos, {"2026-10-05", "2026-10-06"})

    def test_solo_registra_lo_marcado(self):
        self.clases = [{"idclase": "c5", "nombre": "Clase 5", "fechaini": "05/10/2026"},
                       {"idclase": "c6", "nombre": "Clase 6", "fechaini": "06/10/2026"}]
        solo_el_lunes = {L.clave_bloque("4BA", "08:00-00:00", 801) + "|2026-10-05"}
        self.correr_rango(LUNES, MIERCOLES, seleccion=solo_el_lunes)
        fechas = [p["date"] for ruta, p in self.escrituras if ruta == "plan-add-class"]
        self.assertEqual(fechas, ["2026-10-05"])
        omitidos = [i for i in w.ITEMS if i["estado"] == "omitido"]
        self.assertEqual(len(omitidos), 2)                              # martes y miércoles

    def test_solo_los_dias_elegidos(self):
        """Varios períodos marcados (p. ej. hoy y el lunes) no incluyen los días del medio."""
        self.correr_rango(LUNES, MIERCOLES, solo_listar=True, dias=[LUNES, MIERCOLES])
        grupos = {i["grupo"] for i in w.ITEMS}
        self.assertEqual(grupos, {"lun 05/10"})                     # el martes no se miró

    def test_una_simulacion_no_deja_filas_en_el_registro(self):
        anotadas = []
        L.registrar = lambda fila: anotadas.append(fila)
        L.replicar_asistencia = lambda *a, **k: (None, "sin bloque anterior con el curso completo")
        self.correr_rango(MARTES, MARTES, simular=True)
        self.assertEqual(anotadas, [])                              # simular no escribe ni en el CSV
        self.correr_rango(MARTES, MARTES, simular=False)
        self.assertTrue(anotadas)                                   # en serio, sí queda anotado

    def test_los_fines_de_semana_no_cuentan(self):
        self.correr_rango(SABADO, LUNES, solo_listar=True)
        self.assertEqual({d.weekday() for d in self.bloques_pedidos if d != LUNES}, set())

    def test_el_mes_se_lee_una_sola_vez_aunque_sean_varios_dias(self):
        self.correr_rango(LUNES, MIERCOLES, solo_listar=True)
        # una lectura por mes para el rango; cada día reutiliza lo leído (en la prueba, el
        # falso devuelve por fecha, así que se cuentan las lecturas «de mes»)
        self.assertEqual(self.bloques_pedidos.count(LUNES), 2)          # lectura del mes + el día

    def test_un_dia_que_falla_no_corta_el_resto(self):
        original = L.registrar_dia

        def roto(s, perfil, dia, *a, **k):
            if dia == MARTES:
                raise RuntimeError("Webclass respondió 500")
            return original(s, perfil, dia, *a, **k)
        L.registrar_dia = roto
        try:
            self.correr_rango(LUNES, MIERCOLES, solo_listar=True)
        finally:
            L.registrar_dia = original
        estados = {i["clave"]: i["estado"] for i in w.ITEMS}
        self.assertEqual(estados["dia|2026-10-06"], "error")
        self.assertTrue(any(i["estado"] == "propuesto" and "2026-10-05" in i["clave"] for i in w.ITEMS))


class PrimeraVistaDeCaches(unittest.TestCase):
    def test_las_unidades_se_piden_por_fecha(self):
        pedidas = []
        original_api = L.api_get

        def api(s, ruta, params, token):
            if ruta == "get-plan-subjects":
                return {"subjects": [{"id": 1, "sectornombre": "Ciencias Naturales"}]}
            pedidas.append(params["date"])
            return {"units": [{"id": 9}]}
        L.api_get = api
        try:
            cache = {}
            for dia in (LUNES, LUNES, MARTES):
                L.unidades_vigentes(None, "t", 1, 24, "Ciencias Naturales", dia, cache, {"iduser": "7"})
        finally:
            L.api_get = original_api
        self.assertEqual(pedidas, ["2026-10-05", "2026-10-06"])         # lunes una vez, martes aparte


if __name__ == "__main__":
    unittest.main()
