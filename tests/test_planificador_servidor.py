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
        with comun.BarraFalsa(version="2.2.0"):
            c, _, _ = nuevo_cliente()
            v = c.get("/api/version").json()
            self.assertTrue(v["compatible"])
            self.assertEqual(v["barra"], "2.2.0")
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


if __name__ == "__main__":
    unittest.main()
