"""Unidades nuevas: qué ofrece Webclass frente a lo que el perfil ya conoce.

Nada toca Webclass: la consulta se reemplaza por una función de juguete.
"""

import datetime
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import unidades as U  # noqa: E402
import webclass_tareas as w  # noqa: E402


def unidad(id_, curso="5BA", nombre="Unidad", asignatura="Ciencias Naturales", **extra):
    return {"id": id_, "curso": curso, "nombre": nombre, "asignatura": asignatura, **extra}


PERFIL = {"nombre": "Docente", "iduser": "7", "curso_ids": {"5BA": 10},
          "unidades": [unidad(1, nombre="Unidad 1"), unidad(2, nombre="Unidad 2")]}


class Pura(unittest.TestCase):
    def test_nuevas_son_las_que_el_perfil_no_conoce(self):
        ofrecidas = [unidad(1), unidad(2), unidad(3, nombre="Unidad 3"), unidad(3), unidad(4)]
        self.assertEqual([u["id"] for u in U.nuevas_entre(PERFIL, ofrecidas)], [3, 4])   # sin repetir

    def test_lo_rechazado_no_se_vuelve_a_ofrecer(self):
        perfil = {**PERFIL, "unidades_ignoradas": [3]}
        self.assertEqual([u["id"] for u in U.nuevas_entre(perfil, [unidad(3), unidad(4)])], [4])

    def test_los_ids_se_comparan_como_texto(self):
        self.assertEqual(U.nuevas_entre({"unidades": [{"id": "7", "curso": "x"}]}, [unidad(7)]), [])

    def test_asignaturas_por_curso(self):
        perfil = {"unidades": [unidad(1, "5BA", asignatura="Ciencias Naturales"),
                               unidad(2, "5BA", asignatura="Orientación"),
                               {"id": 3, "curso": "6BA", "nombre": "sin asignatura"}]}
        self.assertEqual(U.asignaturas_por_curso(perfil),
                         {"5BA": {"ciencias naturales", "orientacion"}})       # sin tildes ni mayúsculas

    def test_vigencia_de_lo_guardado(self):
        ahora = datetime.datetime(2026, 10, 7, 12, 0)
        def con(hora): return {"revisado": hora.isoformat()}
        self.assertTrue(U.fresco(con(ahora - datetime.timedelta(minutes=90)), ahora))
        self.assertFalse(U.fresco(con(ahora - datetime.timedelta(hours=3)), ahora))
        self.assertFalse(U.fresco(con(ahora + datetime.timedelta(hours=1)), ahora))    # del futuro: no sirve
        for malo in (None, {}, {"revisado": "ayer"}):
            self.assertFalse(U.fresco(malo, ahora))

    def test_incluir_suma_la_unidad_sin_tocar_el_original(self):
        original = json.loads(json.dumps(PERFIL))
        nuevo = U.aplicar_decision(PERFIL, [unidad(3, nombre="Unidad 3", curso_id=10, nivel=5)], [])
        self.assertEqual([u["id"] for u in nuevo["unidades"]], [1, 2, 3])
        self.assertEqual(nuevo["unidades"][2], {"curso": "5BA", "id": 3, "nombre": "Unidad 3",
                                                "asignatura": "Ciencias Naturales"})
        self.assertEqual(PERFIL, original)                       # el original no cambió

    def test_incluir_una_unidad_de_un_curso_nuevo_suma_el_curso(self):
        nuevo = U.aplicar_decision(PERFIL, [unidad(9, "7BA", curso_id=77, nivel=7)], [])
        self.assertEqual(nuevo["curso_ids"], {"5BA": 10, "7BA": 77})
        self.assertEqual(nuevo["curso_niveles"], {"7BA": 7})

    def test_rechazar_la_anota_para_no_preguntar_otra_vez(self):
        nuevo = U.aplicar_decision(PERFIL, [], ["5", "4"])
        self.assertEqual(nuevo["unidades_ignoradas"], ["4", "5"])
        self.assertEqual(U.nuevas_entre(nuevo, [unidad(4), unidad(5)]), [])

    def test_incluir_algo_antes_rechazado_lo_saca_de_rechazadas(self):
        perfil = {**PERFIL, "unidades_ignoradas": ["3"]}
        nuevo = U.aplicar_decision(perfil, [unidad(3)], [])
        self.assertEqual(nuevo["unidades_ignoradas"], [])
        self.assertIn(3, [u["id"] for u in nuevo["unidades"]])

    def test_una_unidad_que_el_perfil_ya_tiene_no_se_duplica_ni_se_rechaza(self):
        nuevo = U.aplicar_decision(PERFIL, [unidad(1)], ["2"])
        self.assertEqual([u["id"] for u in nuevo["unidades"]], [1, 2])
        self.assertEqual(nuevo["unidades_ignoradas"], [])

    def test_enriquecer_anota_la_asignatura_que_faltaba(self):
        perfil = {"unidades": [{"id": 1, "curso": "4BA", "nombre": "a mano"},
                               {"id": 2, "curso": "4BA", "nombre": "x", "asignatura": "Otra"}]}
        perfil, cambio = U.enriquecer(perfil, [unidad(1, "4BA", asignatura="Ciencias Naturales"),
                                               unidad(2, "4BA", asignatura="Distinta")])
        self.assertTrue(cambio)
        self.assertEqual([u["asignatura"] for u in perfil["unidades"]], ["Ciencias Naturales", "Otra"])
        self.assertFalse(U.enriquecer(perfil, [unidad(1, "4BA")])[1])         # ya estaba: sin cambios


class ConArchivos(unittest.TestCase):
    """Caché y perfil en una carpeta temporal; la consulta a Webclass es un contador."""

    def setUp(self):
        self.carpeta = tempfile.mkdtemp()
        self.perfil_guardado = dict(w.PERFILES)
        self.originales = (U.ruta_cache, U.ruta_perfil)
        U.ruta_cache = lambda clave: os.path.join(self.carpeta, f"cache_{clave}.json")
        U.ruta_perfil = lambda clave: os.path.join(self.carpeta, f"{clave}.json")
        self.consultas = 0
        self.ofrece = [unidad(1), unidad(2), unidad(3, nombre="Unidad nueva")]
        self.perfil = json.loads(json.dumps(PERFIL))

        def consultar(perfil):
            self.consultas += 1
            return list(self.ofrece)
        self.consultar = consultar

    def tearDown(self):
        U.ruta_cache, U.ruta_perfil = self.originales
        w.PERFILES.clear()
        w.PERFILES.update(self.perfil_guardado)

    def test_consulta_una_vez_y_despues_usa_lo_guardado(self):
        U.buscar_nuevas("ana", self.perfil, consultar=self.consultar)
        U.buscar_nuevas("ana", self.perfil, consultar=self.consultar)
        self.assertEqual(self.consultas, 1)

    def test_forzar_vuelve_a_preguntar(self):
        U.buscar_nuevas("ana", self.perfil, consultar=self.consultar)
        U.buscar_nuevas("ana", self.perfil, forzar=True, consultar=self.consultar)
        self.assertEqual(self.consultas, 2)

    def test_lo_guardado_vencido_se_vuelve_a_pedir(self):
        U.buscar_nuevas("ana", self.perfil, consultar=self.consultar)
        vieja = (datetime.datetime.now() - datetime.timedelta(hours=5)).isoformat()
        with open(U.ruta_cache("ana"), "w", encoding="utf-8") as f:
            json.dump({"revisado": vieja, "unidades": []}, f)
        U.buscar_nuevas("ana", self.perfil, consultar=self.consultar)
        self.assertEqual(self.consultas, 2)

    def test_encuentra_la_unidad_nueva(self):
        nuevas = U.buscar_nuevas("ana", self.perfil, consultar=self.consultar)
        self.assertEqual([(u["id"], u["nombre"]) for u in nuevas], [(3, "Unidad nueva")])

    def test_la_decision_se_guarda_en_el_perfil_y_no_se_vuelve_a_preguntar(self):
        nuevas = U.buscar_nuevas("ana", self.perfil, consultar=self.consultar)
        self.perfil = U.decidir("ana", self.perfil, nuevas, ["3"], [])
        with open(U.ruta_perfil("ana"), encoding="utf-8") as f:
            guardado = json.load(f)
        self.assertEqual([u["id"] for u in guardado["unidades"]], [1, 2, 3])
        self.assertEqual(w.PERFILES["ana"]["unidades"], guardado["unidades"])     # también en memoria
        self.assertEqual(U.buscar_nuevas("ana", self.perfil, consultar=self.consultar), [])

    def test_rechazar_se_recuerda(self):
        nuevas = U.buscar_nuevas("ana", self.perfil, consultar=self.consultar)
        self.perfil = U.decidir("ana", self.perfil, nuevas, [], ["3"])
        self.ofrece.append(unidad(4, nombre="Otra más"))
        U.buscar_nuevas("ana", self.perfil, forzar=True, consultar=self.consultar)
        nuevas = U.buscar_nuevas("ana", self.perfil, consultar=self.consultar)
        self.assertEqual([u["id"] for u in nuevas], [4])                          # la 3 no vuelve

    def test_sin_decision_no_se_escribe_el_perfil(self):
        U.decidir("ana", self.perfil, [], [], [])
        self.assertFalse(os.path.exists(U.ruta_perfil("ana")))

    def test_un_perfil_a_mano_recibe_las_asignaturas_y_queda_liviano(self):
        perfil = {"iduser": "7", "curso_ids": {"4BA": 1},
                  "unidades": [{"id": 1, "curso": "4BA", "nombre": "a mano"}]}
        self.ofrece = [unidad(1, "4BA", asignatura="Ciencias Naturales")]
        U.buscar_nuevas("ana", perfil, consultar=self.consultar)
        self.assertEqual(w.PERFILES["ana"]["unidades"][0]["asignatura"], "Ciencias Naturales")
        self.assertEqual(U.asignaturas_por_curso(w.PERFILES["ana"]), {"4BA": {"ciencias naturales"}})


class EnTareas(unittest.TestCase):
    """Cómo webclass_tareas informa y filtra las unidades nuevas (sin tocar Webclass)."""

    def setUp(self):
        self.items = list(w.ITEMS)
        w.ITEMS.clear()

    def tearDown(self):
        w.ITEMS[:] = self.items

    def test_informa_la_unidad_con_su_clave_y_grupo(self):
        w.informar_unidad_nueva(unidad(9, "5BA", nombre="Unidad 9"), 4)
        it = w.ITEMS[0]
        self.assertEqual((it["clave"], it["estado"], it["grupo"]),
                         ("unidad:9", "propuesto", "UNIDADES NUEVAS"))
        self.assertEqual(it["detalle"], "4 clases pendientes")

    def test_si_no_pudo_contar_lo_dice(self):
        w.informar_unidad_nueva(unidad(9), None)
        self.assertIn("no se pudo contar", w.ITEMS[0]["detalle"])

    def test_un_fallo_de_red_al_buscar_no_frena_la_corrida(self):
        import unittest.mock as m
        with m.patch.object(U, "buscar_nuevas", side_effect=OSError("sin red")):
            self.assertEqual(w.unidades_nuevas("ana", PERFIL), ([], False))

    def test_el_filtro_de_cursos_aplica_a_las_nuevas(self):
        import unittest.mock as m
        nuevas = [unidad(3, "5BA"), unidad(4, "6BA")]
        with m.patch.object(U, "buscar_nuevas", return_value=(nuevas, True)):
            self.assertEqual([u["id"] for u in w.unidades_nuevas("ana", PERFIL, {"6BA"})[0]], [4])


if __name__ == "__main__":
    unittest.main()
