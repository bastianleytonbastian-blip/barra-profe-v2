"""Informe de personalidad: leer la grilla de WebClass, guardar solo lo que cambió, borrador e informe en Word.

Nada de esto toca WebClass: un WebClass falso imita las páginas reales (las mismas etiquetas y llamadas).
"""

import datetime
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))

import informe_personalidad as ip  # noqa: E402
import webclass_personalidad as P  # noqa: E402
import webclass_tareas as w  # noqa: E402

CALIFICADORES = [("1503", "D"), ("1504", "E/D"), ("1505", "N/D"), ("1506", "N/E")]
CONDUCTAS = [("901", 1, "Emite juicios constructivos"), ("902", 2, "Opina sobre un tema dado"),
             ("903", 3, "Demuestra conductas de autocontrol")]
AREAS = [("AUTOFORMACIÓN PERSONAL", [1, 2]), ("FORMACIÓN ÉTICA", [3])]


def pagina_tabla(alumnas: dict, periodo="2") -> str:
    """alumnas: {id: (nombre, {conducta: calificador})}. Como la de WebClass: el nombre es el enlace a la observación."""
    ths = "".join(f'<th id="head_columna_{c}" ondblclick="editarNombreConducta({c});"><strong style="x">C {n}</strong>'
                  f'<input onclick="editarNombreConducta({c});" type="button"><div class="tooltip"><strong>C {n}</strong>'
                  f'</div><input type="hidden" id="Conducta_{c}" value="{nombre}"></th>' for c, n, nombre in CONDUCTAS)
    filas = []
    for i, (ident, (nombre, valores)) in enumerate(alumnas.items(), 1):
        celdas = ""
        for c, _n, _nombre in CONDUCTAS:
            opciones = '<option value=""></option>' + "".join(
                f'<option value="{v}" {"selected" if valores.get(c) == v else ""} > {s} </option>' for v, s in CALIFICADORES)
            celdas += (f'<td align="center" class="td-select"><div class="C{c}"><div class="tooltip"><strong>{nombre}'
                       f'</strong></div><div id="F{ident}C{c}">[x]</div><div id="edit_F{ident}C{c}">'
                       f'<select id="Combo_F{ident}C{c}" onchange="editarConductaAlumno({ident},{c},{ident}{c});" '
                       f'style="x">{opciones}</select></div></div></td>')
        filas.append(f'<tr id="cuerpo_tabla_{i}" class="F{ident} normalRow"><td class="td-numero" style="x"> {i} </td>'
                     f'<td class="td-alumno"><div id="nombre_alumno_{ident}" title=""><span><a href="#inline4" '
                     f'class="fancybox" title="Observación" onclick="cargarObservacion({ident}, {periodo});" > '
                     f'&nbsp;{nombre} </a></span></div><input type="hidden" class="Y{i}" value="{ident}"></td>{celdas}</tr>')
    return f'<table><thead><tr><th>N°</th><th>Alumnos</th>{ths}</tr></thead><tbody>{"".join(filas)}</tbody></table>'


def pagina_items() -> str:
    trozos = []
    for area, numeros in AREAS:
        trozos.append(f'<tr><th class="" style="x">\n <strong>{area}</strong></th></tr>')
        for n in numeros:
            nombre = next(x for _c, m, x in CONDUCTAS if m == n)
            trozos.append(f'<tr><td style="x">\n   <strong>C{n}.-{nombre}</strong> </td></tr>')
    return f'<table class="table">{"".join(trozos)}</table>'


def pagina_observacion(ident_obs: str, texto: str, alumna: str, periodo="2") -> str:
    return (f'<br><table><tr><td><strong>Observación</strong></td><td><textarea id="observacion" >{texto}</textarea>'
            f'</td></tr><tr><td><input type="checkbox" onclick="cargarObservacion({alumna},0)"></td></tr><tr><td>'
            f'<input type="button" value="Aceptar" onclick="guardarObservacion({ident_obs},{periodo},{alumna})" >'
            f'</td></tr></table>')


CALIFICADORES_COLEGIO = "".join(
    f'<input id="enombcal_{i}" value="{n}"><input id="enomccal_{i}" value="{s}">' for i, (n, s) in
    enumerate((("DESARROLLO", "D"), ("EN DESARROLLO", "E/D"), ("NO DESARROLLADO", "N/D"), ("NO EVALUADO", "N/E")), 1))


class WebclassFalso:
    """Guarda las calificaciones y observaciones en memoria. Falla con cualquier pedido que no sea de los conocidos."""

    def __init__(self, alumnas=None, obedece=True):
        todas = {c: "1503" for c, _n, _x in CONDUCTAS}
        self.alumnas = alumnas or {"101": ("ARAVENA PEREZ ANA", dict(todas)), "102": ("Bustos Rios Luz", dict(todas))}
        self.observaciones = {}               # alumna -> (id, texto)
        self.obedece = obedece                # False: responde bien, pero no guarda nada
        self.pedidos = []

    def get(self, url, params=None, **_k):
        return mock.Mock(text="<input type ='hidden' id='colegio' value='1795' ><input type ='hidden' id='anio' "
                              "value='2026' >", raise_for_status=lambda: None)

    def post(self, url, data=None, **_k):
        archivo = url.rsplit("/", 1)[-1]
        self.pedidos.append((archivo, dict(data)))
        caso = data["caso"]
        if archivo == "filtros.php" and caso == 2:
            texto = ('<select id="ComboCurso" onchange="x"><option value="-1">--</option>'
                     '<option value="237559">5BA</option></select>')
        elif archivo == "filtros.php" and caso == 3:
            texto = ('<select id="ComboPeriodo"><option value="1">Primer Semestre</option><option value="2">'
                     'Segundo Semestre</option></select><input type="hidden" id="TipoPeriodo" value="1">')
        elif caso == 1:
            texto = pagina_tabla(self.alumnas)
        elif caso == 7:
            texto = pagina_items()
        elif caso == 10:
            texto = CALIFICADORES_COLEGIO
        elif caso == 8:
            ident, obs = self.observaciones.get(str(data["alumno"]), ("0", ""))
            texto = pagina_observacion(ident, obs, data["alumno"])
        elif caso == 3:
            alumna, conducta = str(data["idVinculo"])[:3], str(data["idVinculo"])[3:]
            if self.obedece:
                self.alumnas[alumna][1][conducta] = str(data["calificacion"])
            texto = "[x]"
        elif caso == 9:
            if self.obedece:
                self.observaciones[str(data["alumno"])] = ("77", data["observacion"])
            texto = "1"
        else:
            raise AssertionError(f"pedido inesperado: {archivo} {data}")
        return mock.Mock(text=texto, raise_for_status=lambda: None)

    def escrituras(self):
        return [d for a, d in self.pedidos if a == "controlador.php" and d["caso"] in (3, 9)]


PERFIL = {"rut": "1", "iduser": "7", "curso_ids": {"5BA": 237559}, "nombre": "Ana Profe"}


class Lectura(unittest.TestCase):
    def test_tabla_conductas_alumnas_valores_y_vinculos(self):
        t = P.parsear_tabla(pagina_tabla({"101": ("ARAVENA PEREZ ANA", {"901": "1504"})}))
        self.assertEqual([(c["id"], c["numero"], c["nombre"]) for c in t["conductas"]],
                         [(c, n, x) for c, n, x in CONDUCTAS])
        self.assertEqual(t["calificadores"], CALIFICADORES)
        a = t["alumnas"][0]
        self.assertEqual((a["id"], a["numero"], a["nombre"]), ("101", 1, "Aravena Perez Ana"))
        self.assertEqual(a["valores"], {"901": "1504", "902": "", "903": ""})
        self.assertEqual(a["vinculos"]["902"], "101902")

    def test_nombre_que_no_viene_en_mayusculas_se_respeta(self):
        t = P.parsear_tabla(pagina_tabla({"101": ("Luz de la Fuente (Lucía)", {})}))
        self.assertEqual(t["alumnas"][0]["nombre"], "Luz de la Fuente (Lucía)")

    def test_una_pagina_que_no_es_la_tabla_es_un_error(self):
        with self.assertRaises(ValueError):
            P.parsear_tabla("<html>Sesión expirada</html>")

    def test_areas_con_sus_numeros(self):
        self.assertEqual(P.parsear_areas(pagina_items()),
                         [{"nombre": "AUTOFORMACIÓN PERSONAL", "numeros": [1, 2]},
                          {"nombre": "FORMACIÓN ÉTICA", "numeros": [3]}])

    def test_encuesta_agrupa_y_no_pierde_conductas_sin_area(self):
        tabla = P.parsear_tabla(pagina_tabla({"101": ("A", {})}))
        e = P.armar_encuesta(tabla, [{"nombre": "UNA", "numeros": [1]}], {"D": "Desarrollo"})
        self.assertEqual([(a["nombre"], [c["numero"] for c in a["conductas"]]) for a in e["areas"]],
                         [("UNA", [1]), ("OTRAS CONDUCTAS", [2, 3])])
        self.assertEqual(e["calificadores"][0], {"id": "1503", "sigla": "D", "nombre": "Desarrollo"})
        self.assertEqual(e["calificadores"][1]["nombre"], "E/D", "sin nombre conocido queda la sigla")
        self.assertNotIn("vinculos", e["alumnas"][0], "a la barra no le sirven")

    def test_nombres_de_calificadores_y_observacion(self):
        self.assertEqual(P.parsear_nombres_calificadores(CALIFICADORES_COLEGIO)["E/D"], "En desarrollo")
        self.assertEqual(P.parsear_observacion(pagina_observacion("55", "Muy &quot;atenta&quot;", "101")),
                         {"id": "55", "texto": 'Muy "atenta"'})
        with self.assertRaises(ValueError):
            P.parsear_observacion("<html></html>")

    def test_periodo_por_fecha(self):
        periodos = [("1", "Primer Semestre"), ("2", "Segundo Semestre")]
        self.assertEqual(P.periodo_por_fecha(periodos, datetime.date(2026, 4, 1)), "1")
        self.assertEqual(P.periodo_por_fecha(periodos, datetime.date(2026, 11, 11)), "2")
        self.assertEqual(P.periodo_por_fecha(periodos, datetime.date(2026, 1, 5)), "1")
        self.assertEqual(P.periodo_por_fecha([], datetime.date(2026, 4, 1)), "")

    def test_leer_todo_el_curso_sin_escribir(self):
        s = WebclassFalso()
        s.observaciones["102"] = ("33", "Muy participativa")
        with mock.patch.object(w, "crear_session", return_value=s), mock.patch.object(w, "login"), \
                mock.patch.object(w, "obtener_password", return_value="x"), mock.patch.object(w, "verificar_sesion"), \
                mock.patch.dict(w.PERFILES, {"ana": PERFIL}):
            e = P.leer("ana", "5BA", None)
        self.assertEqual((e["curso"], e["curso_id"], e["periodo_nombre"]), ("5BA", "237559", e["periodo_nombre"]))
        self.assertEqual(e["periodos"], [("1", "Primer Semestre"), ("2", "Segundo Semestre")])
        self.assertEqual([a["observacion"] for a in e["alumnas"]], ["", "Muy participativa"])
        self.assertEqual(s.escrituras(), [])


class Guardar(unittest.TestCase):
    def correr(self, s, cambios, extra=()):
        carpeta = tempfile.mkdtemp()
        ruta = os.path.join(carpeta, "cambios.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"curso": "5BA", "curso_id": "237559", "periodo": "2", "alumnas": cambios}, f)
        w.ITEMS.clear()
        with mock.patch.object(w, "crear_session", return_value=s), mock.patch.object(w, "login"), \
                mock.patch.object(w, "obtener_password", return_value="x"), mock.patch.object(w, "verificar_sesion"), \
                mock.patch.dict(w.PERFILES, {"ana": PERFIL}), \
                mock.patch.object(sys, "argv", ["personalidad", "--perfil", "ana", "--datos", ruta, *extra]):
            P.main()
        return {i["clave"]: (i["estado"], i["detalle"]) for i in w.ITEMS}

    def test_simular_dice_que_cambiaria_y_no_escribe(self):
        s = WebclassFalso()
        items = self.correr(s, [{"id": "101", "nombre": "Ana", "valores": {"902": "1505", "901": "1503"},
                                 "observacion": "Atenta"}], ["--simular"])
        self.assertEqual(items["101"], ("propuesto", "1 conducta (C2 N/D) y la observación"))
        self.assertEqual(s.escrituras(), [])

    def test_guarda_solo_lo_que_cambio_y_lo_comprueba(self):
        s = WebclassFalso()
        items = self.correr(s, [{"id": "101", "nombre": "Ana", "valores": {"902": "1505", "903": "1504", "901": "1503"},
                                 "observacion": None}])
        self.assertEqual(items["101"][0], "hecho")
        self.assertEqual([(d["caso"], d["idVinculo"], d["calificacion"]) for d in s.escrituras()],
                         [(3, "101902", "1505"), (3, "101903", "1504")])
        self.assertEqual(s.alumnas["101"][1]["902"], "1505")

    def test_observacion_nueva_y_la_que_ya_estaba(self):
        s = WebclassFalso()
        s.observaciones["102"] = ("33", "Muy participativa")
        items = self.correr(s, [{"id": "101", "nombre": "Ana", "valores": {}, "observacion": "Atenta y   ordenada"},
                                {"id": "102", "nombre": "Luz", "valores": {}, "observacion": "Muy participativa\r\n"}])
        self.assertEqual(items["101"][0], "hecho")
        self.assertEqual(items["102"], ("ya", "ya estaba así en WebClass"))
        self.assertEqual([(d["caso"], d["alumno"], d["idobservacion"]) for d in s.escrituras()], [(9, "101", "0")])

    def test_observacion_que_ya_existia_se_actualiza_con_su_id(self):
        s = WebclassFalso()
        s.observaciones["101"] = ("33", "Antes")
        self.correr(s, [{"id": "101", "nombre": "Ana", "valores": {}, "observacion": "Después"}])
        self.assertEqual(s.escrituras()[0]["idobservacion"], "33")

    def test_si_webclass_no_lo_guarda_queda_pendiente(self):
        s = WebclassFalso(obedece=False)
        items = self.correr(s, [{"id": "101", "nombre": "Ana", "valores": {"902": "1505"}, "observacion": "Atenta"}])
        self.assertEqual(items["101"][0], "pendiente")

    def test_solo_las_marcadas_en_la_vista_previa(self):
        s = WebclassFalso()
        carpeta = tempfile.mkdtemp()
        sel = os.path.join(carpeta, "s.json")
        with open(sel, "w") as f:
            json.dump({"claves": ["102"]}, f)
        items = self.correr(s, [{"id": "101", "nombre": "Ana", "valores": {"902": "1505"}, "observacion": None},
                                {"id": "102", "nombre": "Luz", "valores": {"902": "1504"}, "observacion": None}],
                            ["--seleccion", sel])
        self.assertEqual((items["101"][0], items["102"][0]), ("omitido", "hecho"))
        self.assertEqual([d["idVinculo"] for d in s.escrituras()], ["102902"])

    def test_alumna_que_ya_no_esta_y_calificador_desconocido(self):
        s = WebclassFalso()
        items = self.correr(s, [{"id": "999", "nombre": "X", "valores": {"901": "1505"}, "observacion": None},
                                {"id": "101", "nombre": "Ana", "valores": {"901": "666"}, "observacion": None}])
        self.assertEqual(items["999"][0], "pendiente")
        self.assertEqual(items["101"][0], "ya")
        self.assertEqual(s.escrituras(), [])

    def test_nunca_pide_algo_que_borre(self):
        """controlador.php borra conductas con caso=14 y calificadores con caso=16: ni siquiera se envían."""
        s = WebclassFalso()
        for caso in (2, 4, 5, 11, 13, 14, 15, 16, "DesactivarConductasCurso"):
            with self.assertRaises(ValueError):
                P.pedir(s, "controlador.php", {"caso": caso}, escribir=True)
        with self.assertRaises(ValueError):
            P.pedir(s, "controlador.php", {"caso": 3}, escribir=False)       # leer nunca escribe
        self.assertEqual(s.pedidos, [])


def encuesta_de_prueba():
    tabla = P.parsear_tabla(pagina_tabla(WebclassFalso().alumnas))
    e = P.armar_encuesta(tabla, P.parsear_areas(pagina_items()), P.parsear_nombres_calificadores(CALIFICADORES_COLEGIO))
    for a in e["alumnas"]:
        a["observacion"] = ""
    return {"curso": "5BA", "curso_id": "237559", "periodo": "2", "periodo_nombre": "Segundo Semestre",
            "periodos": [["1", "Primer Semestre"], ["2", "Segundo Semestre"]], "leido": "11/11/2026 10:00", **e}


class Borrador(unittest.TestCase):
    def setUp(self):
        self.e = encuesta_de_prueba()
        self.ana = self.e["alumnas"][0]

    def test_responder_y_volver_a_lo_de_webclass_no_es_un_cambio(self):
        b = ip.responder({}, self.ana, "902", "1505")
        self.assertEqual(ip.valores_de(self.ana, b)["902"], "1505")
        self.assertTrue(ip.tiene_cambios(self.ana, b))
        ip.responder(b, self.ana, "902", "1503")
        self.assertFalse(ip.tiene_cambios(self.ana, b))

    def test_observacion(self):
        b = ip.responder({}, self.ana, observacion="  Muy atenta \n")
        self.assertEqual(ip.observacion_de(self.ana, b), "Muy atenta")
        self.assertEqual(ip.observacion_de(self.e["alumnas"][1], b), "")
        ip.responder(b, self.ana, observacion="\n")
        self.assertFalse(ip.tiene_cambios(self.ana, b))

    def test_cambios_solo_de_quien_tiene_algo_distinto(self):
        b = ip.responder({}, self.ana, "902", "1505")
        ip.responder(b, self.e["alumnas"][1], revisada=True)
        c = ip.cambios(self.e, b)
        self.assertEqual((c["curso"], c["curso_id"], c["periodo"]), ("5BA", "237559", "2"))
        self.assertEqual(c["alumnas"], [{"id": "101", "nombre": "Aravena Perez Ana", "valores": {"902": "1505"},
                                         "observacion": None}])
        self.assertEqual(ip.avance(self.e, b), "1 de 2 revisadas · 1 con cambios sin guardar en WebClass")

    def test_al_volver_a_leer_lo_ya_guardado_sale_del_borrador(self):
        b = ip.responder({}, self.ana, "902", "1505", revisada=True)
        ip.responder(b, self.ana, "903", "1504")
        ip.responder(b, self.ana, observacion="Atenta")
        b["alumnas"]["999"] = {"valores": {"901": "1505"}}          # ya no está en el curso
        self.ana["valores"]["902"] = "1505"                         # esto ya quedó en WebClass
        self.ana["observacion"] = "Atenta"
        limpio = ip.limpiar_borrador(self.e, b)
        self.assertEqual(limpio["alumnas"], {"101": {"revisada": True, "valores": {"903": "1504"}}})


class InformeWord(unittest.TestCase):
    def test_un_informe_por_alumna_con_su_marca_en_cada_conducta(self):
        from docx import Document
        e = encuesta_de_prueba()
        ana = e["alumnas"][0]
        b = ip.responder({}, ana, "902", "1505")
        carpeta = ip.carpeta_de_informes(tempfile.mkdtemp(), e)
        self.assertTrue(carpeta.endswith(os.path.join("Informes de personalidad", "5BA Segundo Semestre 2026")))
        ruta = ip.crear_informe(os.path.join(carpeta, ip.nombre_de_archivo(ana)), e, ana, ip.valores_de(ana, b),
                                "Muy atenta", "Colegio Ejemplo", "Ana Profe", jefatura=True)
        self.assertTrue(ruta.endswith("01 Aravena Perez Ana.docx"))
        doc = Document(ruta)
        texto = "\n".join(p.text for p in doc.paragraphs)
        for esperado in ("Colegio Ejemplo", "Informe de personalidad", "Muy atenta", "D: Desarrollo",
                         "Profesor(a) jefe"):
            self.assertIn(esperado, texto)
        celdas = [c.text for t in doc.tables for fila in t.rows for c in fila.cells]
        self.assertIn("Aravena Perez Ana", celdas)
        self.assertIn("AUTOFORMACIÓN PERSONAL", celdas)
        self.assertEqual(celdas.count("X"), 3, "una marca por conducta")
        fila_c2 = next(fila for t in doc.tables for fila in t.rows if fila.cells[0].text.startswith("2. "))
        self.assertEqual([c.text for c in fila_c2.cells[1:]], ["", "", "X", ""], "C2 quedó en N/D")

    def test_sin_observacion_ni_docente(self):
        from docx import Document
        e = encuesta_de_prueba()
        ruta = ip.crear_informe(os.path.join(tempfile.mkdtemp(), "x.docx"), e, e["alumnas"][1],
                                e["alumnas"][1]["valores"], "")
        self.assertIn("Sin observaciones.", "\n".join(p.text for p in Document(ruta).paragraphs))

    def test_nombre_de_archivo_sin_caracteres_prohibidos(self):
        self.assertEqual(ip.nombre_de_archivo({"id": "1", "numero": 3, "nombre": 'Ana "La" Rios/Paz?'}),
                         "03 Ana La RiosPaz.docx")


if __name__ == "__main__":
    unittest.main()
