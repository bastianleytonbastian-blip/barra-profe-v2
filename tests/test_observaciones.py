"""Observaciones de estudiantes: formulario, validación, envío por alumna y aviso de las nuevas (sin tocar Webclass)."""

import datetime
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


def fila_lista(ident, alumna="ANA RIOS", profesor="LUZ SOTO", tipo="Negativa", fecha="03-11-2026", texto="Llegó tarde",
               asignatura="Música"):
    """Una fila tal como la entrega Webclass: el title de la observación trae las comillas sin escapar."""
    def col(n, attrs="", dentro=None):
        return (f'<div class="i-col-1 i-center i-table-rows col-obs-{n}"{attrs}>'
                + (dentro if dentro is not None else "") + "</div>")
    def span(t):
        return f'<span class="i-label-clear">{t}</span>'
    return ('<div class="i-row i-center i-table-body i-table-body-hover">'
            + col(1, "", span(int(ident) % 5000)) + col(2, "", span(asignatura)) + col(3, "", span(profesor))
            + col(4, "", span(alumna))
            + col(5, f' title="{tipo}"', f'<a href="#" title="{tipo}"><i class="fa fa-frown-o"></i></a>')
            + col(6, "", span(fecha)) + col(7, ' title=""', span(""))
            + col(8, f' title="{texto}"', span(texto)) + col(9, "", span("2do Semestre"))
            + col(10, "", f'<a onclick="EditarAnotacion({ident},237559)"></a><a onclick="imprimirObservacion({ident})"></a>'
                          f'<a onclick="BorrarAnotacion({ident})"></a>')
            + "</div>")


def pagina_lista(filas, total):
    """Encabezado, filas y el pie con el paginador (que usa la misma clase que las filas, pero no es una)."""
    return ('<div class="i-container i-table"><div class="i-row i-center i-table-head">'
            '<div class="col-obs-1"><span class="i-label-clear">N°</span></div></div>' + "".join(filas)
            + '<div class="i-row i-center i-table-body"><span><a onclick="rmvPageObs(1);"></a>'
            f'<input value="0" disabled type="number" id="obsFin"/><input value="{total}" disabled type="number" '
            'id="totalObs" name="totalObs"/><a onclick="addPageObs(1);"></a></span></div></div>')


COMBO_CURSOS = ('<select id="cursoSelector"><option value="-1"> Todos </option><option value="237559"> 5BA </option>'
                '<option value="237573">4MB</option></select>')


class WebclassFalso:
    """Lista de observaciones en memoria, de a 15 por página. Cuenta lo que le piden y falla si le piden algo más."""

    def __init__(self, **por_curso):
        self.cursos = {237559: list(por_curso.get("c5ba", [])), 237573: list(por_curso.get("c4mb", []))}
        self.pedidos = []

    def post(self, url, data=None, **_k):
        self.pedidos.append(dict(data))
        if url != O.URL_LISTA or data["caso"] not in (2, 5):
            raise AssertionError(f"la vigilancia solo puede leer: {url} {data}")
        if data["caso"] == 5:
            texto = COMBO_CURSOS
        else:
            filas = self.cursos[data["curso"]]
            inicio = data["pagFin"] * 15
            texto = pagina_lista(filas[inicio:inicio + 15], len(filas))
        return mock.Mock(text=texto, raise_for_status=lambda: None)

    def consultas_de_lista(self):
        return [p for p in self.pedidos if p["caso"] == 2]


AHORA = datetime.datetime(2026, 11, 4, 10, 30)
IDS = {"5BA": 237559, "4MB": 237573}


class Lista(unittest.TestCase):
    def test_lee_las_columnas_sin_confundir_el_pie_con_una_fila(self):
        filas, total = O.parsear_lista(pagina_lista([fila_lista(5550001)], 118))
        self.assertEqual(total, 118)
        self.assertEqual(filas, [{"id": "5550001", "asignatura": "Música", "profesor": "Luz Soto", "alumna": "Ana Rios",
                                  "tipo": "Negativa", "fecha": "03-11-2026", "texto": "Llegó tarde"}])

    def test_comillas_y_simbolos_en_el_texto(self):
        filas, _ = O.parsear_lista(pagina_lista([fila_lista(1, texto='Dijo "hola" &amp; se fue > afuera')], 1))
        self.assertEqual(filas[0]["texto"], 'Dijo "hola" & se fue > afuera')

    def test_una_pagina_que_no_es_la_lista_es_un_error_y_no_una_lista_vacia(self):
        with self.assertRaises(ValueError):
            O.parsear_lista("<html>Su sesión expiró</html>")

    def test_curso_sin_observaciones(self):
        self.assertEqual(O.parsear_lista(pagina_lista([], 0)), ([], 0))

    def test_cursos_del_selector_sin_todos(self):
        self.assertEqual(O.parsear_cursos(COMBO_CURSOS), {"5BA": 237559, "4MB": 237573})

    def test_propia_ignora_tildes_mayusculas_y_segundo_apellido(self):
        fila = {"profesor": "BASTIAN LEYTON"}
        self.assertTrue(O.es_propia(fila, "Bastián Leyton Rojas"))
        self.assertFalse(O.es_propia(fila, "Luz Soto Rojas"))
        self.assertFalse(O.es_propia({"profesor": ""}, "Luz Soto"))
        self.assertFalse(O.es_propia(fila, ""))


class Vigilar(unittest.TestCase):
    def correr(self, s, estado=None, cursos=("5BA",), nombre="Bastián Leyton Rojas", ids=None):
        return O.vigilar(s, list(cursos), ids or IDS, estado or {}, nombre, AHORA)

    def test_la_primera_vez_solo_anota_y_no_avisa_de_lo_antiguo(self):
        s = WebclassFalso(c5ba=[fila_lista(i) for i in range(1, 41)])
        estado = self.correr(s)
        self.assertEqual(estado["nuevas"], [])
        self.assertEqual(estado["cursos"]["5BA"]["total"], 40)
        self.assertEqual(len(estado["cursos"]["5BA"]["vistas"]), 40)

    def test_si_nada_cambio_basta_una_consulta(self):
        s = WebclassFalso(c5ba=[fila_lista(i) for i in range(1, 41)])
        estado = self.correr(s)
        s.pedidos.clear()
        despues = self.correr(s, estado)
        self.assertEqual(despues["nuevas"], [])
        self.assertEqual(len(s.consultas_de_lista()), 1)

    def test_avisa_la_observacion_nueva_una_sola_vez(self):
        s = WebclassFalso(c5ba=[fila_lista(1)])
        estado = self.correr(s)
        s.cursos[237559].insert(0, fila_lista(2, alumna="LUZ BUSTOS", texto="No trajo materiales"))
        estado = self.correr(s, estado)
        self.assertEqual([o["id"] for o in estado["nuevas"]], ["obs-2"])
        o = estado["nuevas"][0]
        self.assertEqual((o["curso"], o["tipo"], o["alumnas"], o["profesor"], o["texto"], o["creado"]),
                         ("5BA", "Negativa", ["Luz Bustos"], "Luz Soto", "No trajo materiales", "2026-11-04 10:30"))
        estado = self.correr(s, estado)
        self.assertEqual(len(estado["nuevas"]), 1, "ya estaba anotada: no se agrega de nuevo")

    def test_encuentra_una_con_fecha_atrasada_que_no_sale_en_la_primera_pagina(self):
        """La lista va por fecha de la observación: registrar una de la semana pasada la deja más abajo."""
        s = WebclassFalso(c5ba=[fila_lista(i) for i in range(1, 41)])
        estado = self.correr(s)
        s.cursos[237559].insert(30, fila_lista(99, fecha="01-10-2026", texto="Atrasada"))
        estado = self.correr(s, estado)
        self.assertEqual([o["texto"] for o in estado["nuevas"]], ["Atrasada"])

    def test_no_avisa_de_las_propias_pero_las_anota(self):
        s = WebclassFalso(c5ba=[fila_lista(1)])
        estado = self.correr(s)
        s.cursos[237559].insert(0, fila_lista(2, profesor="BASTIAN LEYTON"))
        estado = self.correr(s, estado)
        self.assertEqual(estado["nuevas"], [])
        self.assertIn("2", estado["cursos"]["5BA"]["vistas"])

    def test_la_misma_observacion_a_varias_alumnas_se_avisa_una_vez(self):
        s = WebclassFalso(c5ba=[fila_lista(1)])
        estado = self.correr(s)
        s.cursos[237559][:0] = [fila_lista(2, alumna="ANA"), fila_lista(3, alumna="LUZ"), fila_lista(4, texto="Otra cosa")]
        estado = self.correr(s, estado)
        self.assertEqual(sorted((o["texto"], tuple(o["alumnas"])) for o in estado["nuevas"]),
                         [("Llegó tarde", ("Ana", "Luz")), ("Otra cosa", ("Ana Rios",))])

    def test_una_lista_vacia_por_un_rato_no_hace_saltar_todo_como_nuevo(self):
        s = WebclassFalso(c5ba=[fila_lista(i) for i in range(1, 21)])
        estado = self.correr(s)
        guardadas, s.cursos[237559] = s.cursos[237559], []
        estado = self.correr(s, estado)
        s.cursos[237559] = guardadas
        estado = self.correr(s, estado)
        self.assertEqual(estado["nuevas"], [])

    def test_una_borrada_no_hace_saltar_nada_y_deja_de_releer(self):
        s = WebclassFalso(c5ba=[fila_lista(i) for i in range(1, 21)])
        estado = self.correr(s)
        del s.cursos[237559][3]
        estado = self.correr(s, estado)
        self.assertEqual(estado["nuevas"], [])
        s.pedidos.clear()
        self.correr(s, estado)
        self.assertEqual(len(s.consultas_de_lista()), 1)

    def test_curso_recien_elegido_parte_sin_avisar_y_el_que_se_quita_sale(self):
        s = WebclassFalso(c5ba=[fila_lista(1)], c4mb=[fila_lista(7)])
        estado = self.correr(s)
        estado = self.correr(s, estado, cursos=("4MB",))
        self.assertEqual(estado["nuevas"], [])
        self.assertEqual(list(estado["cursos"]), ["4MB"], "si vuelve a elegir el 5BA, no le salta lo de todo este tiempo")

    def test_si_el_curso_cambia_de_id_parte_de_cero(self):
        """Año nuevo: el 5BA es otro curso en Webclass, con otras observaciones."""
        s = WebclassFalso(c5ba=[fila_lista(1)], c4mb=[fila_lista(7)])
        estado = self.correr(s)
        estado = self.correr(s, estado, ids={"5BA": 237573})
        self.assertEqual(estado["nuevas"], [])
        self.assertEqual(estado["cursos"]["5BA"]["id"], 237573)

    def test_lo_nuevo_sin_marcar_se_conserva_con_un_tope(self):
        s = WebclassFalso(c5ba=[fila_lista(1)])
        viejas = [{"id": f"obs-v{i}"} for i in range(O.MAX_NUEVAS)]
        estado = self.correr(s, {"cursos": {}, "nuevas": viejas})
        self.assertEqual(estado["nuevas"], viejas)
        s.cursos[237559].insert(0, fila_lista(2))
        estado = self.correr(s, estado)
        self.assertEqual(len(estado["nuevas"]), O.MAX_NUEVAS)
        self.assertEqual(estado["nuevas"][-1]["id"], "obs-2")

    def test_un_curso_que_no_existe_se_explica(self):
        s = WebclassFalso(c5ba=[fila_lista(1)])
        estado = self.correr(s, cursos=("5BA", "9ZZ"))
        self.assertIn("9ZZ", estado["error"])
        self.assertEqual(list(estado["cursos"]), ["5BA"])

    def test_solo_lee_nunca_escribe_ni_borra(self):
        """WebclassFalso falla con cualquier otro caso: caso=4 en este mismo archivo borra observaciones."""
        s = WebclassFalso(c5ba=[fila_lista(i) for i in range(1, 41)])
        estado = self.correr(s)
        s.cursos[237559].insert(0, fila_lista(99))
        self.correr(s, estado)
        self.assertEqual({p["caso"] for p in s.pedidos}, {2})
        O.leer_cursos(s)
        self.assertEqual({p["caso"] for p in s.pedidos}, {2, 5})


class VigilarGuardar(unittest.TestCase):
    def setUp(self):
        self.salida = os.path.join(tempfile.mkdtemp(), "v.json")
        self.s = WebclassFalso(c5ba=[fila_lista(1)])
        self.perfil = {"rut": "1", "iduser": "7", "nombre": "Bastián Leyton Rojas", "curso_ids": {"5BA": 237559}}

    def correr(self, *argumentos):
        with mock.patch.object(O, "abrir_sesion", return_value=(self.s, self.perfil)), \
                mock.patch.dict(w.PERFILES, {"ana": self.perfil}), \
                mock.patch.object(sys, "argv", ["observar", "--perfil", "ana", *argumentos]):
            O.main()

    def test_guarda_y_a_la_siguiente_encuentra_lo_nuevo(self):
        self.correr("--vigilar", "5ba", "--salida", self.salida)          # minúsculas: da igual
        self.s.cursos[237559].insert(0, fila_lista(2))
        self.correr("--vigilar", "5BA", "--salida", self.salida)
        with open(self.salida, encoding="utf-8") as f:
            estado = json.load(f)
        self.assertEqual([o["id"] for o in estado["nuevas"]], ["obs-2"])
        self.assertEqual(estado["error"], "")

    def test_si_webclass_falla_no_se_pierde_lo_anotado(self):
        self.correr("--vigilar", "5BA", "--salida", self.salida)
        with open(self.salida, encoding="utf-8") as f:
            antes = json.load(f)
        with mock.patch.object(O, "abrir_sesion", side_effect=OSError("sin internet")), \
                mock.patch.dict(w.PERFILES, {"ana": self.perfil}), \
                mock.patch.object(sys, "argv", ["observar", "--perfil", "ana", "--vigilar", "5BA", "--salida", self.salida]):
            O.main()
        with open(self.salida, encoding="utf-8") as f:
            despues = json.load(f)
        self.assertEqual(despues["cursos"], antes["cursos"])
        self.assertIn("sin internet", despues["error"])

    def test_vigilar_necesita_salida(self):
        with self.assertRaises(ValueError):
            self.correr("--vigilar", "5BA")

    def test_cursos_los_entrega_como_items(self):
        w.ITEMS.clear()
        self.correr("--cursos")
        self.assertEqual([(i["clave"], i["que"]) for i in w.ITEMS], [("5BA", "curso"), ("4MB", "curso")])
        self.assertFalse(self.s.consultas_de_lista())


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
