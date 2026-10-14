"""Planificaciones en bloque: planilla, esqueleto por horario, marcas (sin tocar Webclass)."""

import datetime
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import webclass_planificacion as P  # noqa: E402
import webclass_tareas as w  # noqa: E402

OA = [("2099", "> OA1 Reconocer y explicar"), ("2105", "> OA12 Investigar"), ("2106", "> OA8 Energía")]
HAB = [("1021", "> Hab_a Seleccionar preguntas"), ("1024", "> Hab_d Medir y registrar")]


class Pura(unittest.TestCase):
    def test_texto_plano_pasa_a_parrafos_y_el_html_se_respeta(self):
        self.assertEqual(P.a_html("uno\n\ndos & tres"), "<p>uno</p><p>dos &amp; tres</p>")
        self.assertEqual(P.a_html("<p>ya es html</p>"), "<p>ya es html</p>")
        self.assertEqual(P.a_html("  "), "")

    def test_oa1_no_se_confunde_con_oa12(self):
        ids, faltan = P.resolver_atributos(["OA1", "oa12", "OA99"], OA)
        self.assertEqual((ids, faltan), (["2099", "2105"], ["OA99"]))

    def test_habilidades_con_o_sin_prefijo(self):
        ids, faltan = P.resolver_atributos(["a", "Hab_d", "z"], HAB)
        self.assertEqual((ids, faltan), (["1021", "1024"], ["z"]))

    def test_planilla_valida_cada_fila(self):
        filas, problemas = P.filas_de_planilla([
            {"Nombre": "Clase 1", "Fecha": "12/10/2026", "Inicio": "texto", "OA": "OA1;OA8", "dua": "TIC"},
            {"nombre": "", "fecha": "12/10/2026"},
            {"nombre": "Mala", "fecha": "31/02/2026"},
            {"nombre": "", "fecha": ""},                                   # fila vacía: se ignora
        ])
        self.assertEqual([f["nombre"] for f in filas], ["Clase 1"])
        self.assertEqual((filas[0]["oa"], filas[0]["dua"], filas[0]["fila"]), (["OA1", "OA8"], "tic", 2))
        self.assertEqual(len(problemas), 2)
        self.assertIn("fila 3", problemas[0])
        self.assertIn("DD/MM/AAAA", problemas[1])

    def test_lee_csv_con_punto_y_coma_y_con_coma(self):
        carpeta = tempfile.mkdtemp()
        for sep in (";", ","):
            ruta = os.path.join(carpeta, f"p{ord(sep)}.csv")
            with open(ruta, "w", encoding="utf-8-sig") as f:
                f.write(f"nombre{sep}fecha\nClase 1{sep}12/10/2026\n")
            self.assertEqual(P.leer_planilla(ruta), [{"nombre": "Clase 1", "fecha": "12/10/2026"}])

    def test_plantilla_se_puede_volver_a_leer(self):
        ruta = P.escribir_plantilla(os.path.join(tempfile.mkdtemp(), "x", "plantilla.csv"))
        filas, problemas = P.filas_de_planilla(P.leer_planilla(ruta))
        self.assertEqual((len(filas), problemas), (1, []))

    def test_dias_con_clase_filtra_asignatura_y_toma_el_primer_bloque(self):
        lunes, martes = datetime.date(2026, 10, 12), datetime.date(2026, 10, 13)
        bloques = {lunes: [{"inicio": "13:00", "nombreAsignatura": "Ciencias Naturales"},
                           {"inicio": "09:40", "nombreAsignatura": "Ciencias Naturales"}],
                   martes: [{"inicio": "08:00", "nombreAsignatura": "Orientación"}]}
        dias = P.dias_con_clase(bloques, "ciencias naturales")
        self.assertEqual([(d["fecha"], d["hora"], d["bloques"]) for d in dias], [(lunes, "09:40", 2)])
        self.assertEqual(len(P.dias_con_clase(bloques, "")), 2)             # sin asignatura: todos

    def test_esqueleto_numera_a_continuacion_y_no_repite_dias(self):
        dias = [{"fecha": datetime.date(2026, 10, 12), "hora": "09:40", "bloques": 1},
                {"fecha": datetime.date(2026, 10, 14), "hora": "07:50", "bloques": 2}]
        existentes = [{"fechaini": "12/10/2026"}, {"fechaini": "05/10/2026"}]
        self.assertEqual(P.esqueleto(dias, existentes),
                         [{"nombre": "Clase 3", "fecha": "14/10/2026", "hora": "07:50", "horas": "2"}])


class Etiquetas(unittest.TestCase):
    def test_etiqueta_del_catalogo(self):
        self.assertEqual(P.etiqueta("> OA12 Investigar"), "OA12")
        self.assertEqual(P.etiqueta("> Hab_d Medir"), "Hab_d")
        self.assertEqual(P.etiqueta(""), "")


class Corrida(unittest.TestCase):
    """main() con Webclass simulado."""

    def setUp(self):
        w.ITEMS.clear()
        self.creadas, self.marcadas, self.duas = [], [], []
        self.perfil = {"rut": "1", "iduser": "7", "curso_ids": {"5BA": 1},
                       "unidades": [{"id": 50, "curso": "5BA", "nombre": "U1", "asignatura": "Ciencias"}]}
        self.existentes = [{"idclase": "900", "nombre": "Clase 0", "fechaini": "05/10/2026",
                            "fechafin": "05/10/2026", "asignados": 0}]

    def correr(self, *args, simular=True):
        import webclass_clases as C
        carpeta = tempfile.mkdtemp()
        argv = ["planificar", "--perfil", "ana", *args] + (["--simular"] if simular else [])
        patches = [
            mock.patch.object(P, "abrir_sesion", return_value=(mock.Mock(), self.perfil)),
            mock.patch.dict(w.PERFILES, {"ana": self.perfil}),
            mock.patch.object(P.w, "listar_clases", side_effect=lambda *_a, **_k: list(self.existentes)),
            mock.patch.object(P, "catalogos", return_value=(OA, HAB)),
            mock.patch.object(C, "crear_clase", side_effect=lambda s, **k: self.creadas.append(k) or "7001"),
            mock.patch.object(C, "marcar_atributos", side_effect=lambda s, **k: self.marcadas.append(k)),
            mock.patch.object(C, "marcar_dua", side_effect=lambda s, **k: self.duas.append(k)),
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(P.rutas, "dato", side_effect=lambda x: os.path.join(carpeta, x)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        P.w.PERFIL_POR_DEFECTO = "ana"
        P.main()
        return {i["clave"]: i["estado"] for i in w.ITEMS}

    def planilla(self, filas):
        ruta = os.path.join(tempfile.mkdtemp(), "p.csv")
        with open(ruta, "w", encoding="utf-8-sig") as f:
            f.write("nombre;fecha;inicio;oa;habilidades;dua\n" + "\n".join(filas) + "\n")
        return ruta

    def test_importar_simulado_no_crea_nada(self):
        ruta = self.planilla(["Clase 1;12/10/2026;hola;OA1;a;habitual"])
        estados = self.correr("--unidad", "50", "--importar", ruta)
        self.assertEqual(estados, {"fila:2": "propuesto"})
        self.assertEqual(self.creadas, [])

    def test_importar_crea_y_marca(self):
        ruta = self.planilla(["Clase 1;12/10/2026;hola mundo;OA1;a;tic"])
        estados = self.correr("--unidad", "50", "--importar", ruta, simular=False)
        self.assertEqual(estados, {"fila:2": "hecho"})
        self.assertEqual((self.creadas[0]["nombre"], self.creadas[0]["fecha"]), ("Clase 1", "12/10/2026"))
        self.assertEqual(self.creadas[0]["inicio"], "<p>hola mundo</p>")
        self.assertEqual([(m["tipo"], m["ids"]) for m in self.marcadas],
                         [("oft", ["2099"]), ("hab", ["1021"])])
        self.assertEqual(len(self.duas[0]["casillas"]), 10)                   # DUA con TIC

    def test_importar_no_duplica_una_clase_que_ya_existe(self):
        ruta = self.planilla(["Clase 0;05/10/2026;;;;habitual"])
        self.assertEqual(self.correr("--unidad", "50", "--importar", ruta, simular=False), {"fila:2": "ya"})
        self.assertEqual(self.creadas, [])

    def test_oa_inexistente_deja_pendiente_y_no_crea(self):
        ruta = self.planilla(["Clase 1;12/10/2026;;OA99;;habitual"])
        self.assertEqual(self.correr("--unidad", "50", "--importar", ruta, simular=False),
                         {"fila:2": "pendiente"})
        self.assertEqual(self.creadas, [])

    def test_marcar_en_lote(self):
        estados = self.correr("--unidad", "50", "--marcar", "--clases", "900,999", "--oa", "OA1;OA8",
                              "--dua", "habitual", simular=False)
        self.assertEqual(estados, {"900": "hecho", "999": "pendiente"})
        self.assertEqual(self.marcadas[0]["ids"], ["2099", "2106"])

    def test_dua_ninguno_no_toca_el_dua(self):
        self.correr("--unidad", "50", "--marcar", "--clases", "900", "--dua", "ninguno", simular=False)
        self.assertEqual(self.duas, [])

    def test_unidad_ajena_se_rechaza(self):
        with self.assertRaises(ValueError):
            self.correr("--unidad", "12345", "--catalogo")


if __name__ == "__main__":
    unittest.main()
