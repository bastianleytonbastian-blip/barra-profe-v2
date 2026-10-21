"""Instalador y actualizador: botones del planificador en la copia personal de cada docente, versiones y lógica JavaScript."""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # para encontrar planificador_comun con o sin «discover»
import planificador_comun as comun  # noqa: E402

import barra_utiles  # noqa: E402
import instalar  # noqa: E402

DESTINO_PLANIFICADOR = "%BARRA%\\planificador\\lanzar_planificador.pyw"

BOTONES_VIEJOS = [
    {"grupo": "Webclass", "nombre": "Planificar", "icono": "🗓️", "tipo": "planificar", "destino": "", "ayuda": "ayuda de antes"},
    {"grupo": "Webclass", "nombre": "Mensajes del equipo", "icono": "💬", "tipo": "mensajes", "destino": "", "ayuda": "x"},
    {"grupo": "Webclass", "nombre": "Abrir y firmar", "icono": "✍️", "tipo": "url", "destino": "https://webclass.example", "ayuda": "x"},
    {"grupo": "Correo y nube", "nombre": "Correo del colegio", "icono": "✉️", "tipo": "url", "destino": "https://mail.example", "ayuda": "x"},
]


def escribir_personal(carpeta, botones=BOTONES_VIEJOS, crlf=True, bom=False):
    texto = json.dumps(botones, ensure_ascii=False, indent=2)
    if crlf:
        texto = texto.replace("\n", "\r\n")
    with open(os.path.join(carpeta, "herramientas.json"), "wb") as f:
        f.write((b"\xef\xbb\xbf" if bom else b"") + texto.encode("utf-8"))


def leer_personal(carpeta):
    with open(os.path.join(carpeta, "herramientas.json"), "rb") as f:
        crudo = f.read()
    return json.loads(crudo.decode("utf-8-sig")), crudo


def en_silencio(funcion, *args, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return funcion(*args, **kw)


class BotonesDeCadaDocente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="personal_prueba_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        escribir_personal(self.tmp)

    def nombres(self):
        return [b["nombre"] for b in leer_personal(self.tmp)[0]]

    def test_planificar_abre_el_asistente_y_la_ventana_de_antes_pasa_a_otro_boton(self):
        self.assertTrue(en_silencio(instalar.planificador_en_botones, personal=self.tmp))
        botones, _ = leer_personal(self.tmp)
        por_nombre = {b["nombre"]: b for b in botones}
        self.assertEqual(por_nombre["Planificar"]["destino"], DESTINO_PLANIFICADOR)
        self.assertEqual(por_nombre["Planificar en bloque"]["destino"], "")
        self.assertEqual(self.nombres().index("Planificar en bloque"), self.nombres().index("Planificar") + 1)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "herramientas.json.antes-del-planificador")))

    def test_es_idempotente(self):
        en_silencio(instalar.planificador_en_botones, personal=self.tmp)
        antes = leer_personal(self.tmp)[1]
        self.assertFalse(en_silencio(instalar.planificador_en_botones, personal=self.tmp))
        self.assertEqual(en_silencio(instalar.botones_nuevos_en_propios, personal=self.tmp),
                         ["Escala de notas", "Días sin clases"])
        self.assertEqual(en_silencio(instalar.botones_nuevos_en_propios, personal=self.tmp), [])
        self.assertEqual(en_silencio(instalar.botones_retirados_de_propios, personal=self.tmp), ["Mensajes del equipo"])
        self.assertEqual(en_silencio(instalar.botones_retirados_de_propios, personal=self.tmp), [])
        self.assertNotEqual(antes, leer_personal(self.tmp)[1])

    def test_un_boton_nuevo_entra_despues_del_que_lo_antecede_en_la_plantilla(self):
        en_silencio(instalar.botones_nuevos_en_propios, personal=self.tmp)
        nombres = self.nombres()
        self.assertEqual(nombres[nombres.index("Escala de notas") - 1], "Abrir y firmar")

    def test_quien_nunca_tuvo_planificar_lo_recibe(self):
        """Antes solo se convertía un «Planificar» que ya existiera: quien no lo tenía, nunca lo veía."""
        botones = [b for b in BOTONES_VIEJOS if b["nombre"] != "Planificar"]
        escribir_personal(self.tmp, botones)
        self.assertFalse(en_silencio(instalar.planificador_en_botones, personal=self.tmp))
        agregados = en_silencio(instalar.botones_nuevos_en_propios, personal=self.tmp)
        self.assertIn("Planificar", agregados)
        self.assertIn("Planificar en bloque", agregados)
        por_nombre = {b["nombre"]: b for b in leer_personal(self.tmp)[0]}
        self.assertEqual(por_nombre["Planificar"]["destino"], DESTINO_PLANIFICADOR)
        self.assertEqual(por_nombre["Planificar"]["grupo"], "Webclass")

    def test_un_boton_oculto_no_vuelve_a_aparecer(self):
        botones = [dict(b, oculto=True) if b["nombre"] == "Planificar" else b for b in BOTONES_VIEJOS]
        escribir_personal(self.tmp, botones)
        en_silencio(instalar.planificador_en_botones, personal=self.tmp)
        en_silencio(instalar.botones_nuevos_en_propios, personal=self.tmp)
        planificar = [b for b in leer_personal(self.tmp)[0] if b["nombre"] == "Planificar"]
        self.assertEqual(len(planificar), 1, "no se duplica")
        self.assertTrue(planificar[0].get("oculto"), "lo que el docente ocultó sigue oculto")

    def test_si_pip_no_puede_instalar_se_sigue_con_lo_demas(self):
        import builtins
        from unittest import mock

        def falla(*_a, **_k):
            raise subprocess.CalledProcessError(1, "pip")
        reales = builtins.__import__

        def sin_fastapi(nombre, *a, **k):
            if nombre == "fastapi":
                raise ImportError(nombre)
            return reales(nombre, *a, **k)
        with mock.patch.object(instalar.subprocess, "run", falla), mock.patch("builtins.__import__", sin_fastapi):
            salida = io.StringIO()
            with contextlib.redirect_stdout(salida):
                instalar.revisar_complementos()               # antes se caía aquí y no llegaba a los botones
        self.assertIn("No se pudieron instalar", salida.getvalue())

    def test_dias_sin_clases_va_despues_del_libro_pendiente(self):
        botones = BOTONES_VIEJOS + [{"grupo": "Webclass", "nombre": "Registrar libro pendiente", "icono": "⏪",
                                     "tipo": "libro-atras", "destino": "", "ayuda": "x"},
                                    {"grupo": "Webclass", "nombre": "Registrar observación", "icono": "📝",
                                     "tipo": "observacion", "destino": "", "ayuda": "x"}]
        escribir_personal(self.tmp, botones)
        en_silencio(instalar.botones_nuevos_en_propios, personal=self.tmp)
        nombres = self.nombres()
        self.assertEqual(nombres[nombres.index("Días sin clases") - 1], "Registrar libro pendiente")
        nuevo = next(b for b in leer_personal(self.tmp)[0] if b["nombre"] == "Días sin clases")
        self.assertEqual(nuevo["tipo"], "sin-clases")

    def test_un_boton_retirado_se_quita_y_los_demas_quedan_intactos(self):
        en_silencio(instalar.botones_retirados_de_propios, personal=self.tmp)
        self.assertNotIn("Mensajes del equipo", self.nombres())
        esperados = [b for b in BOTONES_VIEJOS if b["nombre"] != "Mensajes del equipo"]
        self.assertEqual(leer_personal(self.tmp)[0], esperados)

    def test_conserva_saltos_de_linea_y_bom_del_archivo_de_cada_docente(self):
        for crlf in (True, False):
            for bom in (True, False):
                with self.subTest(crlf=crlf, bom=bom):
                    escribir_personal(self.tmp, crlf=crlf, bom=bom)
                    for f in (instalar.planificador_en_botones, instalar.botones_nuevos_en_propios, instalar.botones_retirados_de_propios):
                        en_silencio(f, personal=self.tmp)
                    crudo = leer_personal(self.tmp)[1]
                    self.assertEqual(b"\r\n" in crudo, crlf)
                    self.assertEqual(crudo.startswith(b"\xef\xbb\xbf"), bom)
                    for archivo in os.listdir(self.tmp):                # limpia las copias de seguridad entre variantes
                        if archivo != "herramientas.json":
                            os.remove(os.path.join(self.tmp, archivo))

    def test_sin_archivo_personal_no_hace_nada(self):
        vacio = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, vacio, ignore_errors=True)
        self.assertFalse(en_silencio(instalar.planificador_en_botones, personal=vacio))
        self.assertEqual(en_silencio(instalar.botones_nuevos_en_propios, personal=vacio), [])
        self.assertEqual(en_silencio(instalar.botones_retirados_de_propios, personal=vacio), [])

    def test_un_archivo_roto_no_se_toca(self):
        with open(os.path.join(self.tmp, "herramientas.json"), "w", encoding="utf-8") as f:
            f.write("{esto no es json")
        self.assertFalse(en_silencio(instalar.planificador_en_botones, personal=self.tmp))
        self.assertEqual(en_silencio(instalar.botones_retirados_de_propios, personal=self.tmp), [])
        with open(os.path.join(self.tmp, "herramientas.json"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "{esto no es json")


MES_ATRASADO_VIEJO = {
    "grupo": "Webclass", "nombre": "Completar mes atrasado", "icono": "📚", "tipo": "preguntar",
    "destino": "libro --completar-mes --mes {valor}", "ayuda": "Pone al dia el libro de un mes completo",
    "pregunta": "Recorre los dias habiles de ese mes que ya pasaron y declara OA, leccionario y asistencia donde falte. "
                "Tarda varios minutos y escribe en Webclass.",
    "opciones": [{"texto": "Octubre (este mes)", "valor": "10/2026"}, {"texto": "Septiembre", "valor": "09/2026"}],
    "interactivo": False}


class BotonesCorregidos(unittest.TestCase):
    """Los arreglos de la plantilla (meses calculados, tildes) llegan a la copia de cada docente sin pisar sus cambios."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="personal_prueba_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_meses_fijos_pasan_a_calcularse_y_los_textos_se_corrigen(self):
        botones = [dict(MES_ATRASADO_VIEJO),
                   {"grupo": "Webclass", "nombre": "A donde asigno cada unidad", "icono": "🎯", "tipo": "destinos",
                    "destino": "", "ayuda": "x"},
                   {"grupo": "La barra", "nombre": "Cambiar color", "icono": "🎨", "tipo": "color", "destino": "",
                    "ayuda": "Pasa a la siguiente paleta de colores"}]
        escribir_personal(self.tmp, botones)
        cambiados = en_silencio(instalar.botones_corregidos_en_propios, personal=self.tmp)
        self.assertEqual(cambiados, ["Completar mes atrasado", "A dónde asigno cada unidad", "Cambiar color"])
        por_nombre = {b["nombre"]: b for b in leer_personal(self.tmp)[0]}
        mes = por_nombre["Completar mes atrasado"]
        self.assertEqual(mes["opciones"], "meses")
        self.assertIn("días hábiles", mes["pregunta"])
        self.assertEqual(mes["ayuda"], "Pone al día el libro de un mes completo")
        self.assertIn("A dónde asigno cada unidad", por_nombre)
        self.assertIn("Elige el color", por_nombre["Cambiar color"]["ayuda"])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "herramientas.json.antes-de-actualizar")))
        self.assertEqual(en_silencio(instalar.botones_corregidos_en_propios, personal=self.tmp), [], "es idempotente")

    def test_respeta_lo_que_el_docente_cambio(self):
        propio = dict(MES_ATRASADO_VIEJO, ayuda="Mi ayuda", opciones=[{"texto": "Marzo", "valor": "marzo"}])
        escribir_personal(self.tmp, [propio])
        en_silencio(instalar.botones_corregidos_en_propios, personal=self.tmp)
        boton = leer_personal(self.tmp)[0][0]
        self.assertEqual(boton["ayuda"], "Mi ayuda")
        self.assertEqual(boton["opciones"], [{"texto": "Marzo", "valor": "marzo"}], "no es la lista de meses de la plantilla")

    def test_conserva_formato_y_no_toca_un_archivo_roto(self):
        for crlf in (True, False):
            for bom in (True, False):
                with self.subTest(crlf=crlf, bom=bom):
                    escribir_personal(self.tmp, [dict(MES_ATRASADO_VIEJO)], crlf=crlf, bom=bom)
                    en_silencio(instalar.botones_corregidos_en_propios, personal=self.tmp)
                    crudo = leer_personal(self.tmp)[1]
                    self.assertEqual((b"\r\n" in crudo, crudo.startswith(b"\xef\xbb\xbf")), (crlf, bom))
                    for archivo in os.listdir(self.tmp):
                        if archivo != "herramientas.json":
                            os.remove(os.path.join(self.tmp, archivo))
        with open(os.path.join(self.tmp, "herramientas.json"), "w", encoding="utf-8") as f:
            f.write("{esto no es json")
        self.assertEqual(en_silencio(instalar.botones_corregidos_en_propios, personal=self.tmp), [])

    def test_la_plantilla_ya_viene_corregida(self):
        with open(os.path.join(comun.HERRAMIENTA, "herramientas.json"), encoding="utf-8-sig") as f:
            plantilla = json.load(f)
        mes = next(b for b in plantilla if b.get("nombre") == "Completar mes atrasado")
        self.assertEqual(mes["opciones"], "meses", "sin meses escritos a mano")
        textos = json.dumps(plantilla, ensure_ascii=False)
        for viejo in (v for _campo, v, _nuevo in instalar.TEXTOS_CORREGIDOS):
            self.assertNotIn(viejo, textos)


class TareaDeLas16(unittest.TestCase):
    """La tarea programada de las 16:00 ya no existe: no se crea y se retira de los PC que la tenían."""

    def test_retirar_borra_solo_esa_tarea(self):
        from unittest import mock
        llamadas = []
        def falso(orden, **kw):
            llamadas.append(orden)
            return subprocess.CompletedProcess(orden, 0, "", "")
        with mock.patch.object(instalar.subprocess, "run", falso), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(instalar.retirar_tarea_asignar())
        self.assertEqual(llamadas, [["schtasks", "/delete", "/f", "/tn", instalar.TAREA_ASIGNAR]])

    def test_si_no_habia_tarea_no_pasa_nada(self):
        from unittest import mock
        falso = lambda orden, **kw: subprocess.CompletedProcess(orden, 1, "", "no existe")
        with mock.patch.object(instalar.subprocess, "run", falso), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(instalar.retirar_tarea_asignar())

    def test_instalar_solo_crea_la_subida_automatica(self):
        from unittest import mock
        llamadas = []
        def falso(orden, **kw):
            llamadas.append(orden)
            return subprocess.CompletedProcess(orden, 0, "", "")
        with mock.patch.object(instalar.subprocess, "run", falso), contextlib.redirect_stdout(io.StringIO()):
            instalar.tareas_programadas("ana")
        creadas = [o[o.index("/tn") + 1] for o in llamadas if "/create" in o]
        self.assertEqual(creadas, [instalar.TAREA_SUBIR])
        self.assertNotIn("16:00", " ".join(" ".join(o) for o in llamadas))


class PlantillaQueSeReparte(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(comun.HERRAMIENTA, "herramientas.json"), encoding="utf-8-sig") as f:
            self.botones = json.load(f)
        self.por_nombre = {b["nombre"]: b for b in self.botones}

    def test_trae_los_botones_nuevos_y_no_los_retirados(self):
        self.assertEqual(self.por_nombre["Planificar"]["destino"], DESTINO_PLANIFICADOR)
        self.assertEqual(self.por_nombre["Planificar en bloque"]["tipo"], "planificar")
        self.assertEqual(self.por_nombre["Planificar en bloque"]["destino"], "")
        for nombre in instalar.BOTONES_NUEVOS:
            self.assertIn(nombre, self.por_nombre)
        for nombre in instalar.BOTONES_RETIRADOS:
            self.assertNotIn(nombre, self.por_nombre)

    def test_los_nombres_no_se_repiten(self):
        nombres = [b["nombre"] for b in self.botones]
        self.assertEqual(len(nombres), len(set(nombres)))

    def test_el_lanzador_del_asistente_existe_donde_apunta_el_boton(self):
        self.assertTrue(os.path.isfile(os.path.join(comun.PLANIFICADOR, "lanzar_planificador.pyw")))

    def test_el_codigo_de_mensajes_se_conserva_aunque_el_boton_no_este(self):
        with open(os.path.join(comun.HERRAMIENTA, "barra_profe.pyw"), encoding="utf-8") as f:
            codigo = f.read()
        for pieza in ("class VentanaMensajes", "def abrir_mensajes", 'tipo == "mensajes"'):
            self.assertIn(pieza, codigo)
        self.assertTrue(os.path.isfile(os.path.join(comun.HERRAMIENTA, "mensajeria_red.py")))


class Versiones(unittest.TestCase):
    def test_leer_version(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.assertEqual(barra_utiles.leer_version(tmp), "")
        for texto, esperado in (("2.1.0\n", "2.1.0"), ("﻿10.20.30", "10.20.30"), ("2.1", ""), ("v2.1.0", ""), ("", "")):
            with open(os.path.join(tmp, "VERSION"), "w", encoding="utf-8") as f:
                f.write(texto)
            self.assertEqual(barra_utiles.leer_version(tmp), esperado, repr(texto))

    def test_el_instalador_muestra_ambas_versiones(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            instalar.mostrar_versiones()
        texto = salida.getvalue()
        self.assertIn("Barra Profe: versión", texto)
        self.assertIn("Planificador con IA: versión", texto)


@unittest.skipUnless(shutil.which("node"), "Node.js no está instalado: se omiten las pruebas de la lógica JavaScript")
class LogicaJavaScript(unittest.TestCase):
    def test_pruebas_de_node(self):
        r = subprocess.run(["node", "--test", os.path.join(comun.RAIZ_BARRA, "tests", "planificador_logica.test.mjs")],
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-500:])


if __name__ == "__main__":
    unittest.main()
