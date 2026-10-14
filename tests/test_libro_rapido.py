"""Pruebas de la lectura de bloques del libro (sin tocar Webclass).

Webclass puede tardar decenas de segundos por consulta; estas pruebas
comprueban que los cursos se piden a la vez, que lo leído se reutiliza y que
una escritura invalida lo guardado.
"""

import datetime
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import webclass_libro as L  # noqa: E402

FECHA = datetime.date(2026, 10, 5)
CURSOS = {f"{n}B": 100 + n for n in range(8)}


class SesionFalsa:
    """Responde a post() como Webclass cuando todo sale bien."""

    class _Respuesta:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def post(self, *_a, **_k):
        return self._Respuesta()


class LecturaDeBloques(unittest.TestCase):
    def setUp(self):
        self.llamadas = []
        self.original = L.api_get

        def falso(s, ruta, params, token):
            self.llamadas.append(params["courseID"])
            time.sleep(0.3)
            return {"bloques": [{"fecha": FECHA.isoformat(), "profesor_id": 7,
                                 "id_bloque_detalle": params["courseID"],
                                 "curso_electivo_detalle": None}]}

        L.api_get = falso
        L._BLOQUES_DEL_MES.clear()
        self.sesion = SesionFalsa()

    def tearDown(self):
        L.api_get = self.original
        L._BLOQUES_DEL_MES.clear()

    def test_pide_los_cursos_a_la_vez_y_en_orden(self):
        t0 = time.time()
        resultado = L.bloques_de_cursos(self.sesion, CURSOS, FECHA, "7", "token")
        demora = time.time() - t0
        self.assertEqual(list(resultado), list(CURSOS))               # mismo orden
        self.assertLess(demora, 0.3 * len(CURSOS) / 2)                # claramente menos que en fila
        for curso, curso_id in CURSOS.items():
            self.assertEqual(resultado[curso][0]["id_bloque_detalle"], curso_id)

    def test_avisa_cada_curso_que_llega(self):
        avisos = []
        L.bloques_de_cursos(self.sesion, CURSOS, FECHA, "7", "token",
                            al_terminar=lambda c, hechos, total: avisos.append((hechos, total)))
        self.assertEqual(sorted(avisos), [(n, 8) for n in range(1, 9)])

    def test_reutiliza_lo_leido(self):
        L.bloques_de_cursos(self.sesion, CURSOS, FECHA, "7", "token")
        self.assertEqual(len(self.llamadas), 8)
        L.bloques_de_cursos(self.sesion, CURSOS, FECHA, "7", "token", solo_mios=False)
        self.assertEqual(len(self.llamadas), 8)                       # no volvió a preguntar

    def test_escribir_no_obliga_a_releer_el_mes(self):
        """Hacia atrás se escribe día tras día: releer el mes cada vez costaría minutos."""
        L.bloques_del_dia(self.sesion, 100, FECHA, "7", "token")
        L.api_post(self.sesion, "declare-oas", {}, "token")
        L.bloques_del_dia(self.sesion, 100, FECHA + datetime.timedelta(days=1), "7", "token")
        self.assertEqual(self.llamadas, [100])                        # el mes ya estaba leído

    def test_otro_mes_si_se_lee(self):
        L.bloques_del_dia(self.sesion, 100, FECHA, "7", "token")
        L.bloques_del_dia(self.sesion, 100, datetime.date(2026, 9, 28), "7", "token")
        self.assertEqual(self.llamadas, [100, 100])

    def test_filtra_los_bloques_del_profesor(self):
        mios = L.bloques_del_dia(self.sesion, 100, FECHA, "7", "token")
        ajenos = L.bloques_del_dia(self.sesion, 100, FECHA, "999", "token")
        self.assertEqual(len(mios), 1)
        self.assertEqual(ajenos, [])

    def test_un_error_se_propaga(self):
        def roto(s, ruta, params, token):
            raise RuntimeError("Webclass no respondió")
        L.api_get = roto
        with self.assertRaises(RuntimeError):
            L.bloques_de_cursos(self.sesion, CURSOS, FECHA, "7", "token")

    def test_sin_cursos(self):
        self.assertEqual(L.bloques_de_cursos(self.sesion, {}, FECHA, "7", "token"), {})


if __name__ == "__main__":
    unittest.main()
