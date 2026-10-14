"""Actualizaciones en línea: interpretar el release de GitHub, verificar el paquete y copiarlo sin tocar lo del docente."""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramienta"))
import actualizador as act  # noqa: E402
import publicar  # noqa: E402


def release(version="2.3.0", con_sha=True, **extra):
    activos = [{"name": f"barra-profe-{version}.zip", "browser_download_url": f"https://github.com/x/y/releases/download/v{version}/z.zip"}]
    if con_sha:
        activos.append({"name": f"barra-profe-{version}.zip.sha256", "browser_download_url": "https://github.com/x/y/releases/download/s.sha256"})
    return {"tag_name": f"v{version}", "assets": activos, "body": "Cambios", "html_url": "https://github.com/x/y/releases/tag/v" + version, **extra}


class Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Versiones(unittest.TestCase):
    def test_comparacion(self):
        self.assertTrue(act.es_mas_nueva("2.2.0", "2.10.0"))
        self.assertTrue(act.es_mas_nueva("2.2.0", "v3.0.0"))
        self.assertFalse(act.es_mas_nueva("2.2.0", "2.2.0"))
        self.assertFalse(act.es_mas_nueva("2.2.0", "2.1.9"))
        self.assertFalse(act.es_mas_nueva("", "2.3.0"))
        self.assertFalse(act.es_mas_nueva("2.2.0", "basura"))

    def test_release_valido_y_descartes(self):
        self.assertEqual(act.interpretar_release(release())["version"], "2.3.0")
        self.assertIsNone(act.interpretar_release(release(con_sha=False)), "sin suma de verificación no se usa")
        self.assertIsNone(act.interpretar_release(release(prerelease=True)))
        self.assertIsNone(act.interpretar_release(release(draft=True)))
        self.assertIsNone(act.interpretar_release({"tag_name": "nightly", "assets": []}))

    def test_buscar_nueva(self):
        abrir = lambda pedido, timeout=0: Respuesta(json.dumps(release("2.3.0")).encode())
        self.assertEqual(act.buscar_nueva("2.2.0", abrir=abrir)["version"], "2.3.0")
        self.assertIsNone(act.buscar_nueva("2.3.0", abrir=abrir), "ya está al día")

    def test_sin_red_no_molesta(self):
        def falla(*a, **k):
            raise OSError("sin red")
        self.assertIsNone(act.buscar_nueva("2.2.0", abrir=falla))
        self.assertIsNone(act.buscar_nueva("2.2.0", abrir=lambda *a, **k: Respuesta(b"no es json")))

    def test_solo_se_descarga_de_github(self):
        for url in ("http://github.com/x", "https://evil.example/a.zip", "https://github.com.evil.example/a", "file:///c:/x"):
            self.assertFalse(act._url_segura(url), url)
        self.assertTrue(act._url_segura("https://github.com/x/y/releases/download/v1/a.zip"))


class Paquete(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="act_prueba_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.herr = os.path.join(self.tmp, "herramienta")
        os.makedirs(os.path.join(self.herr, "planificador"))
        self.escribir(self.herr, "VERSION", "2.2.0\n")
        self.escribir(self.herr, "viejo.py", "viejo")
        self.escribir(self.herr, "registro_asignaciones.csv", "datos del docente")
        self.respaldo = os.path.join(self.tmp, "respaldo_actualizacion")

    def escribir(self, base, nombre, texto):
        with open(os.path.join(base, nombre), "w", encoding="utf-8") as f:
            f.write(texto)

    def hacer_zip(self, miembros, nombre="paquete.zip"):
        ruta = os.path.join(self.tmp, nombre)
        with zipfile.ZipFile(ruta, "w") as z:
            for n, contenido in miembros.items():
                z.writestr(n, contenido)
        return ruta, act.suma_sha256(ruta)

    def test_aplica_respalda_y_no_toca_lo_del_docente(self):
        ruta, sha = self.hacer_zip({"herramienta/VERSION": "2.3.0\n", "herramienta/nuevo.py": "nuevo",
                                    "herramienta/planificador/servidor.py": "s",
                                    "herramienta/registro_asignaciones.csv": "NO debe pisar",
                                    "herramienta/__pycache__/x.pyc": "cache"})
        escritos = act.aplicar_zip(ruta, sha, "2.3.0", self.herr, self.respaldo)
        self.assertNotIn("herramienta/registro_asignaciones.csv", escritos)
        self.assertEqual(open(os.path.join(self.herr, "VERSION")).read().strip(), "2.3.0")
        self.assertTrue(os.path.isfile(os.path.join(self.herr, "planificador", "servidor.py")))
        self.assertFalse(os.path.exists(os.path.join(self.herr, "__pycache__")))
        self.assertEqual(open(os.path.join(self.herr, "registro_asignaciones.csv")).read(), "datos del docente")
        self.assertTrue(os.path.isfile(os.path.join(self.herr, "viejo.py")), "no se borra nada que el paquete no mencione")
        copia = os.path.join(self.respaldo, "herramienta-2.2.0.zip")
        with zipfile.ZipFile(copia) as z:
            self.assertEqual(z.read("herramienta/VERSION").decode().strip(), "2.2.0")

    def test_suma_incorrecta_no_instala_nada(self):
        ruta, _ = self.hacer_zip({"herramienta/VERSION": "2.3.0\n", "herramienta/nuevo.py": "x"})
        with self.assertRaises(act.ErrorActualizacion):
            act.aplicar_zip(ruta, "0" * 64, "2.3.0", self.herr, self.respaldo)
        self.assertFalse(os.path.exists(os.path.join(self.herr, "nuevo.py")))
        self.assertEqual(open(os.path.join(self.herr, "VERSION")).read().strip(), "2.2.0")

    def test_rutas_peligrosas_se_rechazan(self):
        for malo in ("herramienta/../../fuera.py", "../fuera.py", "/abs.py", "C:/abs.py", "otra/cosa.py"):
            with self.subTest(malo=malo):
                ruta, sha = self.hacer_zip({"herramienta/VERSION": "2.3.0\n", malo: "x"}, nombre="malo.zip")
                with self.assertRaises(act.ErrorActualizacion):
                    act.aplicar_zip(ruta, sha, "2.3.0", self.herr, self.respaldo)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "fuera.py")))

    def test_la_version_del_paquete_debe_coincidir_con_la_anunciada(self):
        ruta, sha = self.hacer_zip({"herramienta/VERSION": "9.9.9\n"})
        with self.assertRaises(act.ErrorActualizacion):
            act.aplicar_zip(ruta, sha, "2.3.0", self.herr, self.respaldo)

    def test_actualizar_de_punta_a_punta_con_descarga_simulada(self):
        ruta, sha = self.hacer_zip({"herramienta/VERSION": "2.3.0\n", "herramienta/nuevo.py": "nuevo"})
        archivos = {"https://github.com/x/y/releases/download/v2.3.0/z.zip": open(ruta, "rb").read(),
                    "https://github.com/x/y/releases/download/s.sha256": f"{sha}  barra-profe-2.3.0.zip\n".encode()}
        abrir = lambda pedido, timeout=0: Respuesta(archivos[pedido.full_url])
        info = act.interpretar_release(release("2.3.0"))
        r = act.actualizar(info, self.herr, self.respaldo, abrir=abrir, con_pasos=False)
        self.assertEqual(r["version"], "2.3.0")
        self.assertTrue(os.path.isfile(os.path.join(self.herr, "nuevo.py")))

    def test_sin_internet_en_la_descarga_no_cambia_nada(self):
        def falla(*a, **k):
            raise OSError("sin red")
        with self.assertRaises(act.ErrorActualizacion):
            act.actualizar(act.interpretar_release(release()), self.herr, self.respaldo, abrir=falla, con_pasos=False)
        self.assertEqual(open(os.path.join(self.herr, "VERSION")).read().strip(), "2.2.0")


class Publicar(unittest.TestCase):
    def test_el_paquete_publicado_sirve_para_actualizar_y_no_lleva_datos_del_docente(self):
        tmp = tempfile.mkdtemp(prefix="pub_prueba_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        ruta, ruta_sha = publicar.armar_zip("9.9.9", salida=tmp)
        with zipfile.ZipFile(ruta) as z:
            nombres = z.namelist()
        self.assertTrue(all(n.startswith("herramienta/") for n in nombres))
        self.assertFalse([n for n in nombres if "__pycache__" in n or n.endswith((".pyc", ".log")) or n.endswith("registro_asignaciones.csv")])
        self.assertIn("herramienta/actualizador.py", nombres)
        self.assertIn("herramienta/planificador/servidor.py", nombres)
        self.assertEqual(open(ruta_sha).read().split()[0], act.suma_sha256(ruta))

    def test_las_notas_salen_de_cambios(self):
        from barra_utiles import leer_version
        version = leer_version(publicar.AQUI)
        self.assertTrue(publicar.notas_de(version), "CAMBIOS.md debe tener la sección de la versión actual")


if __name__ == "__main__":
    unittest.main()
