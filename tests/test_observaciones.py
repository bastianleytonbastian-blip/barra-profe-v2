"""Observaciones de estudiantes: formulario, validación, envío por alumna (sin tocar Webclass)."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import webclass_observaciones as O  # noqa: E402
import webclass_tareas as w  # noqa: E402

PAGINA = """
<select id="combo_alumnos"><option value="0">Todos</option>
<option value="101"> ARAVENA PEREZ ANA </option><option value="102">BUSTOS RIOS LUZ</option></select>
<select id="combo_asignatura"><option value="-172"> PROFESORA JEFE </option>
<option value="55">Ciencias Naturales</option></select>
<input id="visto_1" value="31"><input id="visto_2" value="21"><input id="visto_3" value="13">
<input id="fechaanot" readonly="readonly" value='2026-10-07'/>
"""
BASE = {"curso": "5BA", "alumnas": ["101", "102"], "tipo": 2, "fecha": "07/10/2026",
        "texto": "Llegó tarde a clases", "asignatura": "55", "visible": "equipo"}


class Formulario(unittest.TestCase):
    def test_parsea_alumnas_asignaturas_roles_y_fecha(self):
        f = O.parsear_formulario(PAGINA)
        self.assertEqual([a[0] for a in f["alumnas"]], ["101", "102"])        # sin «Todos»
        self.assertEqual(f["asignaturas"][1], ("55", "Ciencias Naturales"))
        self.assertEqual(f["roles"], [("1", "31"), ("2", "21"), ("3", "13")])
        self.assertEqual(f["fecha"], "2026-10-07")

    def test_equipo_deja_fuera_a_alumno_y_apoderado(self):
        roles = [("1", "31"), ("2", "21"), ("3", "13")]
        self.assertEqual(O.valores_visibles(roles, "equipo"), "13;")
        self.assertEqual(O.valores_visibles(roles, "todos"), "31;21;13;")

    def test_asignatura_probable_ignora_tildes_y_mayusculas(self):
        asig = [("1", "Educación Física"), ("2", "CIENCIAS NATURALES")]
        self.assertEqual(O.asignatura_probable(asig, {"ciencias naturales"}), "2")
        self.assertEqual(O.asignatura_probable(asig, {"Matemática"}), "")


class Validacion(unittest.TestCase):
    def test_datos_correctos(self):
        self.assertEqual(O.validar(BASE), [])

    def test_cada_problema_se_explica(self):
        malo = {**BASE, "tipo": -1, "texto": "  ", "alumnas": [], "asignatura": "", "fecha": "ayer"}
        self.assertEqual(len(O.validar(malo)), 5)

    def test_texto_demasiado_largo(self):
        self.assertTrue(any("pasa de" in p for p in O.validar({**BASE, "texto": "x" * 2000})))


class Envio(unittest.TestCase):
    def test_cuerpo_igual_al_del_boton_guardar(self):
        c = O.cuerpo_de_envio(BASE, "101", 237559, "1", "3076947", "13;")
        self.assertEqual((c["caso"], c["accion"], c["seleccionados"]), (2, 1, "101::"))
        self.assertEqual((c["tipo_anot"], c["anotacion_tipo"], c["fecha_anot"]), (2, 2, "2026-10-07"))
        self.assertEqual((c["curso"], c["sector"], c["profesor"], c["verSolo"]),
                         (237559, "55", "3076947", "13;"))

    def test_un_texto_con_simbolos_viaja_en_un_campo_aparte(self):
        c = O.cuerpo_de_envio({**BASE, "texto": "a&b=c"}, "101", 1, "1", "7", "13;")
        self.assertEqual(c["anotacion"], "a&b=c")          # requests lo codifica: no rompe el envío

    def test_respuesta_numerica_es_exito(self):
        s = mock.Mock()
        for texto, esperado in (("5231", 5231), (" 17\n", 17), ("0", 0), ("Error", 0), ("", 0)):
            s.post.return_value = mock.Mock(text=texto, raise_for_status=lambda: None)
            self.assertEqual(O.guardar_una(s, {}), esperado)


class Corrida(unittest.TestCase):
    """main() completo con Webclass simulado."""

    def correr(self, extra, datos=BASE, respuestas=("9", "9")):
        carpeta = tempfile.mkdtemp()
        ruta = os.path.join(carpeta, "obs.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f)
        s = mock.Mock()
        s.post.side_effect = lambda url, data=None, **k: mock.Mock(
            text=PAGINA if data.get("caso") == 1 else next(self.respuestas), raise_for_status=lambda: None)
        s.get.return_value = mock.Mock(text='<input id="t_periodo" value="1">')
        self.respuestas = iter(respuestas)
        perfil = {"rut": "1", "iduser": "7", "curso_ids": {"5BA": 237559}, "unidades": []}
        w.ITEMS.clear()
        with mock.patch.object(O, "abrir_sesion", return_value=(s, perfil)), \
                mock.patch.dict(w.PERFILES, {"ana": perfil}), \
                mock.patch.object(sys, "argv", ["observar", "--perfil", "ana", "--datos", ruta, *extra]):
            O.w.PERFIL_POR_DEFECTO = "ana"
            O.main()
        return s, {i["clave"]: i["estado"] for i in w.ITEMS}

    def test_simular_no_envia_nada(self):
        s, estados = self.correr(["--simular"])
        self.assertEqual(estados, {"101": "propuesto", "102": "propuesto"})
        self.assertFalse([c for c in s.post.call_args_list if c.kwargs["data"].get("caso") == 2])

    def test_guarda_una_por_alumna(self):
        s, estados = self.correr([])
        self.assertEqual(estados, {"101": "hecho", "102": "hecho"})
        escritas = [c.kwargs["data"] for c in s.post.call_args_list if c.kwargs["data"].get("caso") == 2]
        self.assertEqual([e["seleccionados"] for e in escritas], ["101::", "102::"])

    def test_solo_las_marcadas(self):
        carpeta = tempfile.mkdtemp()
        sel = os.path.join(carpeta, "s.json")
        with open(sel, "w") as f:
            json.dump({"claves": ["102"]}, f)
        s, estados = self.correr(["--seleccion", sel], respuestas=("9",))
        self.assertEqual(estados, {"101": "omitido", "102": "hecho"})

    def test_si_webclass_no_confirma_queda_pendiente(self):
        _s, estados = self.correr([], respuestas=("9", "0"))
        self.assertEqual(estados, {"101": "hecho", "102": "pendiente"})

    def test_alumna_que_no_es_del_curso_no_se_envia(self):
        s, estados = self.correr([], datos={**BASE, "alumnas": ["101", "999"]}, respuestas=("9",))
        self.assertEqual(estados["999"], "pendiente")


if __name__ == "__main__":
    unittest.main()
