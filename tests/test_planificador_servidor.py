"""Servidor del planificador: protección contra otras páginas, cuenta de Barra, versiones y armado de lo que se envía a WebClass.

Usa una Barra falsa y simula `barra.ejecutar`: no toca WebClass ni la IA.
"""

import csv
import json
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # para encontrar planificador_comun con o sin «discover»
import planificador_comun as comun  # noqa: E402

if not comun.HAY_PLANIFICADOR:                                    # pragma: no cover
    raise unittest.SkipTest("Esta copia de Barra no trae el planificador.")
try:
    from fastapi.testclient import TestClient
    import servidor
except Exception as exc:                                          # pragma: no cover  (faltan complementos en este equipo)
    raise unittest.SkipTest(f"Faltan complementos del planificador para probar el servidor: {exc}")

BASE = "http://127.0.0.1:8501"
ORIGEN = BASE


def nuevo_cliente():
    """(cliente, token): como el navegador, que recibe el token y la cookie al abrir «/»."""
    c = TestClient(servidor.app, base_url=BASE)
    r = c.get("/")
    token = re.search(r'name="planificador-token" content="([^"]+)"', r.text).group(1)
    return c, token, r


def cab(token, **extra):
    return {"X-Planificador-Token": token, "Origin": ORIGEN, **extra}


class Seguridad(unittest.TestCase):
    def setUp(self):
        self.barra = comun.BarraFalsa()
        self.barra.__enter__()
        self.addCleanup(self.barra.__exit__, None, None, None)
        self.c, self.token, self.pagina = nuevo_cliente()

    def test_la_pagina_inicial_entrega_el_token_y_una_cookie_httponly_samesite(self):
        self.assertNotIn("__TOKEN__", self.pagina.text)
        cookie = self.pagina.headers["set-cookie"].lower()
        self.assertIn("planificador_token=", cookie)
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)

    def test_leer_no_pide_token(self):
        self.assertEqual(self.c.get("/api/cuenta").status_code, 200)
        self.assertEqual(self.c.get("/api/version").status_code, 200)

    def test_escribir_sin_token_es_401_en_todas_las_rutas_de_escritura(self):
        limpio = TestClient(servidor.app, base_url=BASE)            # sin pasar por «/»: ni token ni cookie
        for metodo, ruta in (("post", "/api/apagar"), ("put", "/api/perfil"), ("post", "/api/ia/claves"), ("post", "/api/ia/config"),
                             ("post", "/api/barra/crear"), ("post", "/api/barra/unidades"), ("post", "/api/historial"),
                             ("post", "/api/registro/eliminar"), ("post", "/api/curriculo/actualizar")):
            with self.subTest(ruta=ruta):
                r = getattr(limpio, metodo)(ruta, json={}, headers={"Origin": ORIGEN})
                self.assertEqual(r.status_code, 401, r.text)

    def test_hacen_falta_las_dos_cosas_token_y_cookie(self):
        solo_token = TestClient(servidor.app, base_url=BASE)
        self.assertEqual(solo_token.post("/api/ia/config", json={}, headers=cab(self.token)).status_code, 401)
        solo_cookie = TestClient(servidor.app, base_url=BASE)
        solo_cookie.cookies.set("planificador_token", self.token)
        self.assertEqual(solo_cookie.post("/api/ia/config", json={}, headers={"Origin": ORIGEN}).status_code, 401)
        self.assertEqual(self.c.post("/api/ia/config", json={}, headers=cab("x" * 43)).status_code, 401)

    def test_un_origen_ajeno_es_403_aunque_traiga_token_y_cookie(self):
        r = self.c.post("/api/ia/config", json={}, headers=cab(self.token, Origin="http://pagina-maliciosa.example"))
        self.assertEqual(r.status_code, 403)

    def test_un_host_ajeno_es_403_contra_dns_rebinding(self):
        self.assertEqual(self.c.get("/api/cuenta", headers={"Host": "evil.example:8501"}).status_code, 403)
        self.assertEqual(self.c.post("/api/ia/config", json={}, headers=cab(self.token, Host="evil.example:8501")).status_code, 403)

    def test_la_peticion_legitima_pasa(self):
        r = self.c.post("/api/ia/config", json={"proveedor": None, "modelo": None, "respaldo": True}, headers=cab(self.token))
        self.assertEqual(r.status_code, 200, r.text)

    def test_apagar_sin_token_no_apaga(self):
        with mock.patch.object(servidor.os, "_exit") as salir, mock.patch.object(servidor.threading, "Timer") as reloj:
            r = TestClient(servidor.app, base_url=BASE).post("/api/apagar", headers={"Origin": ORIGEN})
        self.assertEqual(r.status_code, 401)
        reloj.assert_not_called()
        salir.assert_not_called()


class CuentaYVersion(unittest.TestCase):
    def _llamar(self, barra, cuerpo):
        c, token, _ = nuevo_cliente()
        with mock.patch.object(servidor.barra, "ejecutar", return_value={"unidades": [], "perfil": "x"}) as ejecutar:
            r = c.post("/api/barra/unidades", json=cuerpo, headers=cab(token))
        return r, ejecutar

    def test_una_pantalla_con_la_cuenta_vieja_se_rechaza_con_409(self):
        with comun.BarraFalsa(activa="beto") as barra:
            r, ejecutar = self._llamar(barra, {"cuenta": "ana"})
            self.assertEqual(r.status_code, 409)
            self.assertIn("cambió", r.json()["error"])
            ejecutar.assert_not_called()

    def test_con_la_cuenta_correcta_se_trabaja_siempre_con_la_activa(self):
        with comun.BarraFalsa(activa="beto") as barra:
            r, ejecutar = self._llamar(barra, {"cuenta": "beto"})
            self.assertEqual(r.status_code, 200, r.text)
            datos = ejecutar.call_args.args[2]
            self.assertEqual((datos["perfil"], datos["exigir_activo"]), ("beto", True))

    def test_una_barra_vieja_bloquea_todo_sin_llamar_a_webclass(self):
        with comun.BarraFalsa(version="2.0.0") as barra:
            r, ejecutar = self._llamar(barra, {"cuenta": "beto"})
            self.assertEqual(r.status_code, 409)
            self.assertIn("ACTUALIZAR.bat", r.json()["error"])
            ejecutar.assert_not_called()

    def test_el_estado_y_la_version_informan_la_compatibilidad(self):
        with comun.BarraFalsa(version="2.0.0"):
            c, _, _ = nuevo_cliente()
            self.assertFalse(c.get("/api/version").json()["compatible"])
            self.assertFalse(c.get("/api/barra/estado", params={"ruta": comun.RAIZ_BARRA}).json()["compatible"])
        with comun.BarraFalsa(version="2.6.0"):
            c, _, _ = nuevo_cliente()
            v = c.get("/api/version").json()
            self.assertTrue(v["compatible"])
            self.assertEqual(v["barra"], "2.6.0")
            self.assertRegex(v["planificador"], r"^\d+\.\d+\.\d+$")

    def test_la_ruta_antigua_de_enviar_explica_que_hay_que_recargar(self):
        with comun.BarraFalsa():
            c, token, _ = nuevo_cliente()
            r = c.post("/api/barra/enviar", json={}, headers=cab(token))
            self.assertEqual(r.status_code, 409)
            self.assertIn("Recárgala", r.json()["error"])


class ArmadoDelEnvio(unittest.TestCase):
    def setUp(self):
        self.barra = comun.BarraFalsa(activa="beto")
        self.barra.__enter__()
        self.addCleanup(self.barra.__exit__, None, None, None)
        self.c, self.token, _ = nuevo_cliente()

    def test_el_material_guardado_solo_se_resuelve_dentro_de_su_carpeta(self):
        mid, guardados, info = servidor.guardar_material([("Guía.docx", b"contenido")], ("guia.html", b"<html></html>"))
        self.assertRegex(mid, r"^[0-9a-f]{12}$")
        self.assertEqual([g["nombre"] for g in guardados], ["Guía.docx"])
        self.assertTrue(servidor.ruta_material(mid, "Guía.docx"))
        self.assertTrue(servidor.ruta_material(mid, info["guardado"]))
        for peligroso in ("../../perfil.json", "..\\..\\perfil.json", "inexistente.pdf", ""):
            self.assertIsNone(servidor.ruta_material(mid, peligroso), peligroso)
        for mal_id in ("../x", "", "ZZZZZZZZZZZZ", "0" * 11):
            self.assertIsNone(servidor.ruta_material(mal_id, "Guía.docx"))

    def test_crear_arma_destinos_hora_por_defecto_y_recursos(self):
        mid, _, info = servidor.guardar_material([("Guía.docx", b"PK-docx")], ("guia.html", b"<html>hola</html>"))
        visto = {}

        def ejecutar(ruta, op, datos=None, timeout=0):
            visto.update(op=op, datos=datos, existe=[os.path.isfile(r["ruta"]) for r in datos["recursos"]])
            return {"resultados": []}

        datos = {
            "cuenta": "beto",
            "clase": {"nombre": "Clase de prueba", "fecha": "15/10/2026", "hora": "", "horas": "2", "tipo": "Universal",
                      "campos": {"inicio": "Hola\n- punto"}, "dua": [3, 4]},
            "destinos": [{"id_unidad": "100", "fecha": "15/10/2026"}, {"id_unidad": "200", "fecha": "16/10/2026"}],
            "oa": ["OA12"], "oa_textos": {"OA12": "texto"}, "nivel_hint": "5° Básico",
            "recursos": [
                {"archivo": "Guía.docx", "nombre": "Guía", "momento": "inicio", "material_id": mid},
                {"archivo": info["guardado"], "nombre": "Guía PIE - x", "momento": "cierre", "material_id": mid},
                {"archivo": "extra.pdf", "nombre": "Extra", "momento": "desarrollo"},
                {"archivo": "foto.PNG", "nombre": "Foto", "momento": "inicio"},
                {"archivo": "paisaje.jpg", "nombre": "Paisaje", "momento": "cierre"},
                {"archivo": "notas.txt", "nombre": "Notas", "momento": "desarrollo"},
                {"archivo": "no_existe.pdf", "nombre": "Nada", "momento": "desarrollo", "material_id": mid},
            ],
        }
        with mock.patch.object(servidor.barra, "ejecutar", ejecutar), \
                mock.patch.object(servidor, "html_a_pdf", return_value=b"%PDF-1.4 falso"):
            r = self.c.post("/api/barra/crear", headers=cab(self.token), data={"datos": json.dumps(datos)},
                            files=[("recursos", ("extra.pdf", b"%PDF-1.4", "application/pdf")),
                                   ("recursos", ("foto.PNG", b"\x89PNG\r\n", "image/png")),
                                   ("recursos", ("paisaje.jpg", b"\xff\xd8\xff", "image/jpeg")),
                                   ("recursos", ("notas.txt", b"texto", "text/plain"))])
        self.assertEqual(r.status_code, 200, r.text)
        enviado = visto["datos"]
        self.assertEqual(visto["op"], "crear")
        self.assertEqual((enviado["perfil"], enviado["exigir_activo"]), ("beto", True))
        self.assertEqual([(d["id_unidad"], d["fecha"]) for d in enviado["destinos"]], [("100", "15/10/2026"), ("200", "16/10/2026")])
        self.assertEqual(enviado["clase"]["hora"], "08:00", "sin hora se marca a las 08:00")
        self.assertEqual(enviado["nivel_hint"], "5° Básico")
        nombres = [(os.path.basename(x["ruta"]), x["nombre"], x["momento"]) for x in enviado["recursos"]]
        self.assertEqual([n[1:] for n in nombres], [("Guía", "inicio"), ("Guía PIE - x", "cierre"), ("Extra", "desarrollo"),
                                                    ("Foto", "inicio"), ("Paisaje", "cierre")], "las imágenes JPG y PNG sí se adjuntan")
        self.assertTrue(nombres[1][0].endswith(".pdf"), "la guía PIE en HTML se convierte a PDF")
        self.assertEqual(visto["existe"], [True] * 5, "todos los archivos existen cuando se llama a Barra")
        avisos = " ".join(r.json()["avisos"])
        self.assertIn("notas.txt", avisos)
        self.assertIn("no_existe.pdf", avisos)

    def test_crear_exige_unidad_y_nombre(self):
        base = {"cuenta": "beto", "clase": {"nombre": "x", "fecha": "15/10/2026", "campos": {}}, "destinos": [], "recursos": []}
        r = self.c.post("/api/barra/crear", headers=cab(self.token), data={"datos": json.dumps(base)})
        self.assertEqual(r.status_code, 400)
        base["destinos"] = [{"id_unidad": "1", "fecha": "mañana"}]
        r = self.c.post("/api/barra/crear", headers=cab(self.token), data={"datos": json.dumps(base)})
        self.assertEqual(r.status_code, 400)

    def test_el_registro_se_lee_de_la_cuenta_activa_con_lo_mas_nuevo_primero(self):
        with open(os.path.join(self.barra.carpeta, "datos", "registro_historico.txt"), "w", encoding="utf-8") as f:
            f.write("ana")
        archivo = os.path.join(self.barra.carpeta, "datos", "registro_planificaciones_beto.csv")
        with open(archivo, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["fecha_creacion", "cuenta", "unidad", "idunidad", "curso", "idclase", "clase", "fecha_clase", "oa_marcados",
                        "recursos_ids", "origen"])
            w.writerow(["2026-10-01T10:00:00", "beto", "U1", "1", "5BA", "11", "Primera", "02/10/2026", "1", "", "planificador"])
            w.writerow(["2026-10-02T10:00:00", "beto", "U1", "1", "5BA", "12", "Segunda", "03/10/2026", "1", "", "planificador"])
        r = self.c.get("/api/registro").json()
        self.assertEqual([c["clase"] for c in r["clases"]], ["Segunda", "Primera"])
        self.barra.cambiar_cuenta("ana")
        self.assertEqual(self.c.get("/api/registro").json()["clases"], [], "otra cuenta no ve el registro de beto")

    def test_eliminar_pasa_por_barra_con_la_cuenta_activa_y_pide_al_menos_una_clase(self):
        r = self.c.post("/api/registro/eliminar", headers=cab(self.token), json={"cuenta": "beto", "clases": []})
        self.assertEqual(r.status_code, 400)
        with mock.patch.object(servidor.barra, "ejecutar", return_value={"resultados": []}) as ejecutar:
            r = self.c.post("/api/registro/eliminar", headers=cab(self.token),
                            json={"cuenta": "beto", "clases": [{"id_unidad": 5, "idclase": 6}]})
        self.assertEqual(r.status_code, 200)
        _, op, datos = ejecutar.call_args.args[:3]
        self.assertEqual((op, datos["perfil"], datos["clases"]), ("eliminar", "beto", [{"id_unidad": "5", "idclase": "6"}]))
        with mock.patch.object(servidor.barra, "ejecutar") as ejecutar:
            r = self.c.post("/api/registro/eliminar", headers=cab(self.token), json={"cuenta": "ana", "clases": [{"id_unidad": 5, "idclase": 6}]})
        self.assertEqual(r.status_code, 409)
        ejecutar.assert_not_called()


class PlanificadorDirecto(unittest.TestCase):
    """Fase 3: color de la barra, subida directa con Barra, historial unido y perfil con preferencias."""

    def setUp(self):
        self.barra = comun.BarraFalsa(activa="beto")
        self.barra.__enter__()
        self.addCleanup(self.barra.__exit__, None, None, None)
        self.c, self.token, _ = nuevo_cliente()

    def _escribir(self, relativa, contenido):
        ruta = os.path.join(self.barra.carpeta, relativa)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        return ruta

    def test_el_tema_trae_el_color_de_la_barra_de_la_cuenta_activa(self):
        import shutil
        shutil.copy(os.path.join(comun.HERRAMIENTA, "tema.py"), os.path.join(self.barra.carpeta, "herramienta", "tema.py"))
        self._escribir(os.path.join("datos", "tema_beto.json"), json.dumps({"paleta": "verde", "letra": "normal"}))
        t = self.c.get("/api/tema").json()
        self.assertEqual((t["paleta"], t["claro"], t["oscuro"]), ("verde", "#0f6e52", "#6ee7b7"))
        self.assertEqual((t["tema"], t["color_barra"]), ("sistema", True), "valores iniciales del perfil")
        self.barra.cambiar_cuenta("ana")                                # ana no eligió color: la paleta inicial
        self.assertEqual(self.c.get("/api/tema").json()["paleta"], "morado")

    def test_sin_tema_py_en_barra_no_hay_color_pero_no_falla(self):
        t = self.c.get("/api/tema").json()
        self.assertEqual((t["paleta"], t["claro"]), ("", ""))

    def test_el_nombre_viene_de_la_cuenta_de_barra_y_no_se_cambia_desde_el_planificador(self):
        self.assertEqual(self.c.get("/api/perfil").json()["nombre_docente"], "Beto Soto")
        r = self.c.put("/api/perfil", headers=cab(self.token), json={"nombre_docente": "Otro Nombre", "colegio": "Colegio X"})
        self.assertEqual(r.status_code, 200, r.text)
        p = self.c.get("/api/perfil").json()
        self.assertEqual((p["nombre_docente"], p["colegio"]), ("Beto Soto", "Colegio X"))
        self.assertTrue(p["completo"])

    def test_las_preferencias_se_guardan_saneadas(self):
        r = self.c.put("/api/perfil", headers=cab(self.token), json={
            "tema": "rosado", "color_barra": False, "hora_defecto": "25:99", "asignatura_defecto": " Ciencias Naturales ",
            "plantillas": [{"nombre": "", "texto": "Objetivo: leer\nActividad: parejas"}, {"nombre": "vacía", "texto": "  "}, "basura"]})
        self.assertEqual(r.status_code, 200, r.text)
        p = self.c.get("/api/perfil").json()
        self.assertEqual((p["tema"], p["color_barra"], p["hora_defecto"], p["asignatura_defecto"]),
                         ("sistema", False, "08:00", "Ciencias Naturales"))
        self.assertEqual(p["plantillas"], [{"nombre": "Objetivo: leer", "texto": "Objetivo: leer\nActividad: parejas"}])
        self.c.put("/api/perfil", headers=cab(self.token), json={"tema": "oscuro", "hora_defecto": "7:45"})
        p = self.c.get("/api/perfil").json()
        self.assertEqual((p["tema"], p["hora_defecto"], p["color_barra"]), ("oscuro", "07:45", False),
                         "lo que no se envía queda como estaba")

    def test_subir_directo_pasa_por_barra_con_niveles_asignatura_y_tipo(self):
        visto = {}

        def ejecutar(ruta, op, datos=None, timeout=0):
            visto.update(op=op, datos=dict(datos), existe=os.path.isfile(datos["ruta"]))
            return {"id": "123", "subido": True, "nombre": datos["nombre"]}

        asignaturas = servidor.wc.asignaturas_recurso()
        nombre_asignatura = next(iter(asignaturas))
        datos = {"cuenta": "beto", "nombre": "Guía PIE - El agua", "autor": "", "niveles": ["Quinto Básico", "Segundo Medio", "Kínder"],
                 "asignatura": nombre_asignatura, "visible": False, "tipo": "Guía PIE (NEE → Necesidades Especiales)"}
        with mock.patch.object(servidor.barra, "ejecutar", ejecutar):
            r = self.c.post("/api/barra/subir", headers=cab(self.token), data={"datos": json.dumps(datos)},
                            files=[("archivo", ("guia.pdf", b"%PDF-1.4", "application/pdf"))])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["id"], "123")
        enviado = visto["datos"]
        self.assertEqual(visto["op"], "subir")
        self.assertTrue(visto["existe"], "el archivo existe mientras Barra lo sube")
        self.assertEqual((enviado["perfil"], enviado["exigir_activo"]), ("beto", True))
        self.assertEqual(enviado["niveles"], ["5", "2M"], "los niveles desconocidos se descartan")
        self.assertEqual(enviado["asignatura"], asignaturas[nombre_asignatura])
        self.assertEqual(enviado["tipo_file"], "70")
        self.assertEqual(enviado["autor"], "Beto Soto", "sin autor, el nombre de la cuenta")
        self.assertFalse(enviado["visible"])

    def test_subir_directo_valida_antes_de_llamar_a_barra(self):
        base = {"cuenta": "beto", "nombre": "Guía", "autor": "Beto", "niveles": ["Quinto Básico"],
                "asignatura": next(iter(servidor.wc.asignaturas_recurso())), "tipo": ""}
        casos = [({**base, "niveles": []}, "guia.pdf", 400), ({**base, "asignatura": "Astrología"}, "guia.pdf", 400),
                 (base, "notas.txt", 400), ({**base, "cuenta": "ana"}, "guia.pdf", 409)]
        for datos, archivo, codigo in casos:
            with self.subTest(archivo=archivo, datos=datos), mock.patch.object(servidor.barra, "ejecutar") as ejecutar:
                r = self.c.post("/api/barra/subir", headers=cab(self.token), data={"datos": json.dumps(datos)},
                                files=[("archivo", (archivo, b"x", "application/octet-stream"))])
                self.assertEqual(r.status_code, codigo, r.text)
                ejecutar.assert_not_called()

    def test_el_historial_une_lo_guardado_y_lo_creado_en_webclass(self):
        historial = servidor.historial
        con_enlace = historial.guardar({"nombre": "El agua", "curso": "5° Básico", "asignatura": "Ciencias Naturales", "fecha": "2026-10-15",
                                        "webclass": [{"id_unidad": "1", "idclase": "11", "curso": "5BA", "unidad": "U1", "fecha": "15/10/2026"}]})
        sin_enlace = historial.guardar({"nombre": "Célula", "curso": "8° Básico"})
        archivo = os.path.join(self.barra.carpeta, "datos", "registro_planificaciones.csv")    # beto es la primera cuenta
        with open(os.path.join(self.barra.carpeta, "datos", "registro_historico.txt"), "w", encoding="utf-8") as f:
            f.write("beto")
        with open(archivo, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["fecha_creacion", "cuenta", "unidad", "idunidad", "curso", "idclase", "clase", "fecha_clase", "oa_marcados",
                        "recursos_ids", "origen"])
            w.writerow(["2026-10-15T10:00:00", "beto", "U1", "1", "5BA", "11", "El agua", "15/10/2026", "1", "", "planificador"])
            w.writerow(["2020-01-01T10:00:00", "beto", "U2", "2", "6BA", "22", "Antigua", "02/01/2020", "0", "", "planificador"])
        items = self.c.get("/api/historial/todo").json()["items"]
        self.assertEqual(len(items), 3, "la clase enviada aparece una sola vez")
        agua = next(it for it in items if it["archivo"] == con_enlace)
        self.assertEqual([w["idclase"] for w in agua["webclass"]], ["11"])
        self.assertEqual(agua["fecha_clase"], "15/10/2026")
        antigua = items[-1]
        self.assertEqual((antigua["nombre"], antigua["archivo"], antigua["webclass"][0]["idclase"]), ("Antigua", "", "22"))
        self.assertIn(sin_enlace, [it["archivo"] for it in items])
        completa = self.c.get(f"/api/historial/clase/{con_enlace}").json()
        self.assertEqual((completa["nombre"], completa["archivo_historial"]), ("El agua", con_enlace))
        self.assertEqual(self.c.get("/api/historial/clase/no_existe.json").status_code, 404)

    def test_guardar_de_nuevo_una_clase_actualiza_el_mismo_archivo(self):
        primero = self.c.post("/api/historial", headers=cab(self.token), json={"nombre": "Clase", "curso": "5° Básico"}).json()["archivo"]
        segundo = self.c.post("/api/historial", headers=cab(self.token),
                              json={"nombre": "Clase v2", "curso": "5° Básico", "archivo_historial": primero}).json()["archivo"]
        self.assertEqual(primero, segundo)
        self.assertEqual([c["nombre"] for c in self.c.get("/api/historial").json()["clases"]], ["Clase v2"])
        otro = self.c.post("/api/historial", headers=cab(self.token),
                           json={"nombre": "Copia", "archivo_historial": "../../perfil.json"}).json()["archivo"]
        self.assertNotEqual(otro, "perfil.json", "un nombre ajeno no se sobrescribe: se crea uno nuevo")

    def test_la_guia_pie_informa_que_partes_no_son_texto(self):
        r = self.c.get("/api/pie/niveles").json()
        self.assertIn("5° Básico", r["niveles"])
        self.assertTrue({"imagen", "busqueda", "correcta", "picto_extra"} <= set(r["claves_sin_texto"]))


class TextoEnVivo(unittest.TestCase):
    """Fase 4: generar es un trabajo cuyo avance se sigue en vivo (Server-Sent Events), con respaldo por consulta."""

    def setUp(self):
        self.barra = comun.BarraFalsa(activa="beto")
        self.barra.__enter__()
        self.addCleanup(self.barra.__exit__, None, None, None)
        self.c, self.token, _ = nuevo_cliente()
        parche = mock.patch.object(servidor.ia, "hay_proveedor", return_value=True)
        parche.start()
        self.addCleanup(parche.stop)

    @staticmethod
    def generar_bien(perfil, asignatura, curso, tema, *_a, al_avanzar=None, **_k):
        al_avanzar = al_avanzar or (lambda *_: None)          # el modo de respaldo no sigue el avance
        al_avanzar("etapa", {"etapa": "material", "texto": "Leyendo el material"})
        al_avanzar("etapa", {"etapa": "redactando", "texto": "Redactando la clase"})
        al_avanzar("intento", {"modelo": "Gemini (Google) · m1"})
        for trozo in ("<<<INI", "CIO>>>\nHola", " mundo"):
            al_avanzar("trozo", trozo)
        al_avanzar("etapa", {"etapa": "cierre", "texto": "Escribiendo el cierre"})
        return {"nombre": "Clase", "inicio": "Hola mundo", "asignatura": asignatura, "curso": curso}

    def _leer(self, tid, ultimo=None):
        """[(tipo, datos, id)] de la transmisión, como los recibe el navegador."""
        eventos, actual = [], {}
        with self.c.stream("GET", f"/api/trabajos/{tid}", headers={"Last-Event-ID": str(ultimo)} if ultimo is not None else {}) as r:
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.headers["content-type"].startswith("text/event-stream"))
            for linea in r.iter_lines():
                if not linea:
                    if "event" in actual:
                        eventos.append((actual["event"], json.loads(actual["data"]), int(actual["id"])))
                    actual = {}
                    continue
                campo, _, valor = linea.partition(": ")
                actual[campo] = valor
        return eventos

    def _empezar(self, generar):
        with mock.patch.object(servidor.planificador, "generar", generar):
            r = self.c.post("/api/planificacion/trabajo", headers=cab(self.token),
                            data={"datos": json.dumps({"asignatura": "Ciencias Naturales", "curso": "5° Básico", "tema": "agua"})},
                            files=[("archivos", ("guia.docx", b"PK-docx", "application/octet-stream"))])
            self.assertEqual(r.status_code, 200, r.text)
            tid = r.json()["id"]
            return tid, self._leer(tid)

    def test_el_avance_llega_en_orden_con_el_texto_y_termina_con_el_resultado(self):
        tid, eventos = self._empezar(self.generar_bien)
        tipos = [e[0] for e in eventos]
        self.assertEqual([e[1]["etapa"] for e in eventos if e[0] == "etapa"], ["material", "redactando", "cierre"])
        self.assertEqual("".join(e[1]["t"] for e in eventos if e[0] == "trozo"), "<<<INICIO>>>\nHola mundo")
        self.assertLess(tipos.index("intento"), tipos.index("trozo"))
        self.assertEqual(tipos[-1], "fin")
        resultado = eventos[-1][1]
        self.assertEqual((resultado["nombre"], resultado["curso"]), ("Clase", "5° Básico"))
        self.assertRegex(resultado["material_id"], r"^[0-9a-f]{12}$", "el material queda guardado como antes")
        self.assertEqual([a["nombre"] for a in resultado["archivos_material"]], ["guia.docx"])
        consulta = self.c.get(f"/api/trabajos/{tid}/resultado").json()
        self.assertEqual((consulta["estado"], consulta["resultado"]["nombre"], consulta["etapa"]["etapa"]), ("listo", "Clase", "cierre"))

    def test_si_la_conexion_se_corta_sigue_donde_iba(self):
        tid, eventos = self._empezar(self.generar_bien)
        intento = next(e for e in eventos if e[0] == "intento")
        resto = self._leer(tid, ultimo=intento[2])
        self.assertNotIn("intento", [e[0] for e in resto])
        self.assertEqual([e[0] for e in resto][-1], "fin")
        self.assertEqual("".join(e[1]["t"] for e in resto if e[0] == "trozo"), "<<<INICIO>>>\nHola mundo")

    def test_un_error_de_la_ia_llega_como_falla_y_por_consulta(self):
        def generar_mal(*_a, al_avanzar=None, **_k):
            al_avanzar("etapa", {"etapa": "redactando", "texto": "Redactando la clase"})
            raise RuntimeError("Todos los proveedores configurados llegaron a su límite.")
        tid, eventos = self._empezar(generar_mal)
        self.assertEqual(eventos[-1][:2], ("falla", {"error": "Todos los proveedores configurados llegaron a su límite."}))
        consulta = self.c.get(f"/api/trabajos/{tid}/resultado").json()
        self.assertEqual((consulta["estado"], consulta["resultado"]), ("error", None))
        self.assertIn("límite", consulta["error"])

    def test_un_trabajo_que_no_existe_se_explica(self):
        self.assertEqual(self.c.get("/api/trabajos/no-existe").status_code, 404)
        r = self.c.get("/api/trabajos/no-existe/resultado")
        self.assertEqual(r.status_code, 404)
        self.assertIn("genera de nuevo", r.json()["error"])

    def test_sin_ia_no_empieza_ningun_trabajo(self):
        with mock.patch.object(servidor.ia, "hay_proveedor", return_value=False), \
                mock.patch.object(servidor.threading, "Thread") as hilo:
            r = self.c.post("/api/planificacion/trabajo", headers=cab(self.token), data={"datos": "{}"})
        self.assertEqual(r.status_code, 400)
        hilo.assert_not_called()

    def test_escribir_un_trabajo_pide_el_token(self):
        r = TestClient(servidor.app, base_url=BASE).post("/api/planificacion/trabajo", data={"datos": "{}"}, headers={"Origin": ORIGEN})
        self.assertEqual(r.status_code, 401)

    def test_el_modo_de_respaldo_sigue_generando_de_una_vez(self):
        with mock.patch.object(servidor.planificador, "generar", self.generar_bien):
            r = self.c.post("/api/planificacion/generar", headers=cab(self.token),
                            data={"datos": json.dumps({"asignatura": "Historia", "curso": "6° Básico"})})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["nombre"], r.json()["material_id"]), ("Clase", ""))


class ArranqueLiviano(unittest.TestCase):
    def test_al_abrir_el_planificador_no_se_cargan_las_bibliotecas_pesadas(self):
        import subprocess
        pesadas = ("openai", "docx", "pptx", "openpyxl", "pypdf", "PIL")
        codigo = f"import sys, servidor; print(','.join(m for m in {pesadas!r} if m in sys.modules))"
        r = subprocess.run([sys.executable, "-B", "-c", codigo], cwd=comun.PLANIFICADOR, capture_output=True, text=True,
                           timeout=180, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertEqual(r.stdout.strip(), "", "se cargan cuando se usan (IA, Word, Excel, PowerPoint, PDF, imágenes)")


if __name__ == "__main__":
    unittest.main()
