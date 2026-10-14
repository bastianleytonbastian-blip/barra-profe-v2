"""Copiar la asistencia del bloque anterior: caso real de 4BA (retiradas y talleres).

Reproduce lo que pasó el 06/10 con una docente de 4BA: el curso tiene 42
alumnas en la nómina, 3 retiradas; los bloques anteriores traen 40 registros
(las 39 activas más una) y los contadores nunca suman justo las 39 activas.
"""

import datetime
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import webclass_libro as L  # noqa: E402

FECHA = datetime.date(2026, 10, 6)
PERFIL = {"iduser": "7", "nombre": "Docente Prueba"}


def nomina(total=42, retiradas=3):
    return [{"id": 1000 + i, "retirado": 1 if i < retiradas else 0, "nombrecurso": "4BA",
             "nombre_usuario": f"A{i}", "apellido_paterno": f"B{i}"} for i in range(total)]


def registros(ids, estado=1):
    return [{"alumno_id": i, "apoderado_id": -1, "estado_asistencia": estado, "modalidad": 1}
            for i in ids]


def bloque(inicio, val_asistencia=True, taller=False, id_bloque=1, contadas=(33, 7, 0, 0)):
    return {"id": id_bloque, "id_bloque_detalle": 500 + id_bloque, "inicio": inicio,
            "termino": "00:00", "nivel": 24, "val_asistencia": val_asistencia,
            "es_electivo": taller, "nombreAsignatura": "Tecnología",
            "cnt_presente": contadas[0], "cnt_ausente": contadas[1],
            "cnt_atrasado": contadas[2], "cnt_retirado": contadas[3]}


class Respuesta:
    def raise_for_status(self):
        pass


class Sesion:
    def __init__(self):
        self.posts = []

    def post(self, url, data=None, **k):
        self.posts.append((url, data))
        return Respuesta()


class ReplicarAsistencia(unittest.TestCase):
    def setUp(self):
        self.guardados = {n: getattr(L, n) for n in ("nomina_curso", "asistencia_bloque")}
        self.leidos = []
        self.registros_de = {}
        L.nomina_curso = lambda *a, **k: self.nomina
        self.nomina = nomina()
        activas = [a["id"] for a in self.nomina if a["retirado"] != 1]
        self.activas = activas

        self.guardado = None          # lo que Webclass devuelve del destino; None = lo que se envió

        def leer(s, curso_id, b, fecha, iduser, token):
            if b["id"] == self.destino["id"]:                # releer el destino tras escribir
                if isinstance(self.guardado, Exception):
                    raise self.guardado
                if self.guardado is not None:
                    return self.guardado
                enviado = json.loads(self.s.posts[-1][1]["attendance"])
                return [{"alumno_id": e["alumno"], "estado_asistencia": e["estado_numero"]}
                        for e in enviado]
            self.leidos.append(b["inicio"])
            valor = self.registros_de[b["inicio"]]
            if isinstance(valor, Exception):
                raise valor
            return valor
        L.asistencia_bloque = leer
        # 40 registros: las 39 activas y una alumna retirada más (como pasó en 4BA)
        self.completa = registros(activas + [1000])
        self.destino = bloque("12:50", val_asistencia=False, id_bloque=9)
        self.s = Sesion()

    def tearDown(self):
        for n, v in self.guardados.items():
            setattr(L, n, v)
        L._BLOQUES_DEL_MES.clear()

    def replicar(self, dia, simular=False):
        return L.replicar_asistencia(self.s, PERFIL, 237557, dia, self.destino, FECHA, "t", simular)

    def test_sirve_un_bloque_aunque_los_contadores_no_sumen_las_activas(self):
        previo = bloque("11:20", id_bloque=2)                 # contadas = 40, activas = 39
        self.registros_de = {"11:20": self.completa}
        fuente, detalle = self.replicar([previo, self.destino])
        self.assertIs(fuente, previo)
        self.assertIn("replicada y verificada desde 11:20", detalle)
        _url, datos = self.s.posts[0]
        copiadas = json.loads(datos["attendance"])
        self.assertEqual(len(copiadas), 39)                    # solo las activas, no las retiradas
        self.assertEqual(datos["profesor"], "7")

    def test_no_copia_a_las_retiradas(self):
        self.registros_de = {"11:20": self.completa}
        self.replicar([bloque("11:20", id_bloque=2), self.destino])
        copiadas = json.loads(self.s.posts[0][1]["attendance"])
        self.assertNotIn(1000, {c["alumno"] for c in copiadas})

    def test_simular_no_escribe(self):
        self.registros_de = {"11:20": self.completa}
        fuente, detalle = self.replicar([bloque("11:20", id_bloque=2), self.destino], simular=True)
        self.assertIsNotNone(fuente)
        self.assertIn("copiaría de 11:20", detalle)
        self.assertEqual(self.s.posts, [])

    def test_prueba_el_siguiente_si_el_mas_cercano_esta_incompleto(self):
        cercano = bloque("11:20", id_bloque=2)
        lejano = bloque("07:50", id_bloque=1)
        self.registros_de = {"11:20": registros(self.activas[:30]), "07:50": self.completa}
        fuente, _ = self.replicar([lejano, cercano, self.destino])
        self.assertIs(fuente, lejano)
        self.assertEqual(self.leidos, ["11:20", "07:50"])      # primero el más cercano

    def test_un_bloque_con_error_no_impide_usar_otro(self):
        self.registros_de = {"11:20": RuntimeError("500 Server Error"), "07:50": self.completa}
        fuente, _ = self.replicar([bloque("07:50", id_bloque=1), bloque("11:20", id_bloque=2),
                                   self.destino])
        self.assertEqual(fuente["inicio"], "07:50")

    def test_los_talleres_no_son_fuente(self):
        taller = bloque("09:40", taller=True, id_bloque=3)
        self.registros_de = {"09:40": self.completa}
        fuente, detalle = self.replicar([taller, self.destino])
        self.assertIsNone(fuente)
        self.assertEqual(self.leidos, [])                       # ni siquiera se consultó
        self.assertIn("sin bloque anterior con el curso completo", detalle)

    def test_si_ninguno_cubre_explica_que_pasó_con_cada_uno(self):
        self.registros_de = {"11:20": registros(self.activas[:35]),
                             "07:50": RuntimeError("500 Server Error")}
        fuente, detalle = self.replicar([bloque("07:50", id_bloque=1), bloque("11:20", id_bloque=2),
                                         self.destino])
        self.assertIsNone(fuente)
        self.assertIn("sin bloque anterior con el curso completo (39 alumnas)", detalle)
        self.assertIn("11:20: le faltan 4 de 39 alumnas", detalle)
        self.assertIn("07:50: no se pudo leer", detalle)
        self.assertEqual(self.s.posts, [])

    def test_sin_bloques_anteriores(self):
        fuente, detalle = self.replicar([self.destino])
        self.assertIsNone(fuente)
        self.assertIn("no hay un bloque anterior con asistencia tomada", detalle)

    def test_nomina_vacia(self):
        self.nomina = []
        fuente, detalle = self.replicar([bloque("11:20"), self.destino])
        self.assertIsNone(fuente)
        self.assertIn("no se pudo leer la nómina", detalle)

    def test_taller_de_destino_no_copia(self):
        self.destino["es_electivo"] = True
        self.destino["electivo_nombre"] = "Danza"
        fuente, detalle = self.replicar([bloque("11:20"), self.destino])
        self.assertIsNone(fuente)
        self.assertIn("se toma a mano", detalle)

    def mezcla(self, ausentes=3, atrasadas=2, extra=None):
        estados = [4] * ausentes + [2] * atrasadas
        estados += [1] * (len(self.activas) - len(estados))
        regs = [{"alumno_id": i, "apoderado_id": -1, "estado_asistencia": e, "modalidad": 1}
                for i, e in zip(self.activas, estados)]
        return regs + (extra or [])

    def test_copia_ausentes_y_atrasadas_con_su_marca(self):
        self.registros_de = {"11:20": self.mezcla()}
        fuente, detalle = self.replicar([bloque("11:20", id_bloque=2), self.destino])
        self.assertIsNotNone(fuente)
        copiadas = json.loads(self.s.posts[0][1]["attendance"])
        marcas = [c["estado"] for c in copiadas]
        self.assertEqual((marcas.count("A"), marcas.count("AT"), marcas.count("P")), (3, 2, 34))
        self.assertNotIn("", marcas)
        self.assertIn("34 presentes · 3 ausentes · 2 atrasadas", detalle)

    def test_la_simulacion_cuenta_ausentes(self):
        self.registros_de = {"11:20": self.mezcla()}
        _f, detalle = self.replicar([bloque("11:20", id_bloque=2), self.destino], simular=True)
        self.assertIn("34 presentes · 3 ausentes · 2 atrasadas", detalle)

    def test_estado_desconocido_no_se_envia_en_blanco(self):
        self.registros_de = {"11:20": self.mezcla(extra=[])}
        self.registros_de["11:20"][0]["estado_asistencia"] = 7          # p. ej. una justificada nueva
        fuente, detalle = self.replicar([bloque("11:20", id_bloque=2), self.destino])
        self.assertIsNone(fuente)
        self.assertIn("estado que la barra no conoce (7)", detalle)
        self.assertEqual(self.s.posts, [])

    def test_retirada_en_el_origen_no_se_copia_ni_cuenta(self):
        self.registros_de = {"11:20": self.mezcla(extra=[
            {"alumno_id": 1000, "apoderado_id": -1, "estado_asistencia": 4, "modalidad": 1}])}
        _f, detalle = self.replicar([bloque("11:20", id_bloque=2), self.destino])
        self.assertIn("3 ausentes", detalle)

    def test_verificacion_que_falla_deja_pendiente_y_dice_cuantas_ausentes(self):
        self.registros_de = {"11:20": self.mezcla()}
        self.guardado = [{"alumno_id": i, "estado_asistencia": 1} for i in self.activas]   # todo presente
        fuente, detalle = self.replicar([bloque("11:20", id_bloque=2), self.destino])
        self.assertIsNone(fuente)
        self.assertIn("Webclass guardó distinto en 5 alumnas (ausentes sin marcar: 3)", detalle)

    def test_si_no_puede_releer_lo_dice(self):
        self.registros_de = {"11:20": self.mezcla()}
        self.guardado = RuntimeError("timeout")
        fuente, detalle = self.replicar([bloque("11:20", id_bloque=2), self.destino])
        self.assertIsNone(fuente)
        self.assertIn("no pude comprobarla", detalle)

    def test_se_prueban_como_mucho_cuatro_bloques(self):
        previos = [bloque(f"0{h}:00", id_bloque=h) for h in range(1, 7)]
        self.registros_de = {b["inicio"]: registros(self.activas[:5]) for b in previos}
        self.replicar(previos + [self.destino])
        self.assertEqual(len(self.leidos), L.MAX_FUENTES)


if __name__ == "__main__":
    unittest.main()
