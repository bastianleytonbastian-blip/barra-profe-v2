"""Servidor local del Planificador: API (FastAPI) + interfaz web (HTML/CSS/JS en web/).

Uso:  python servidor.py   (abre http://127.0.0.1:8501 en el navegador)
Solo escucha en tu equipo (127.0.0.1): las claves de IA no salen de aquí.
"""
import getpass
import hmac
import io
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
import uuid
import webbrowser
from dataclasses import asdict
from datetime import date

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from nucleo import actualizador, barra, curriculo, guia_pie as pie, historial, ia, perfil as P, planificador, rutas, version, webclass as wc
from nucleo.exportar_pdf import html_a_pdf
from nucleo.exportar_word import guia_a_word
from nucleo.exportar_xlsx import generar_excel

RAIZ = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(RAIZ, "web")
def carpeta_guias():
    return os.path.join(rutas.datos_usuario(), "guias_pie")     # las guías de la cuenta activa


def carpeta_materiales():
    return os.path.join(rutas.datos_usuario(), "materiales")    # el material de las planificaciones de la cuenta activa
PUERTO = int(os.environ.get("PLANIFICADOR_PUERTO", "8501"))

app = FastAPI(title="Planificador de clases", docs_url="/api/docs", redoc_url=None)
ACTIVIDAD = {"ultima": time.time()}

# ── Seguridad del servidor local ──
# Solo el navegador del propio equipo, abriendo la interfaz desde «/», puede escribir: una página web cualquiera abierta en
# el mismo navegador no puede crear clases, cambiar claves de IA ni apagar el servidor.
TOKEN = secrets.token_urlsafe(32)                                  # cambia cada vez que arranca el servidor
HOSTS_VALIDOS = {f"127.0.0.1:{PUERTO}", f"localhost:{PUERTO}"}     # contra DNS rebinding
ORIGENES_VALIDOS = {f"http://{h}" for h in HOSTS_VALIDOS}
METODOS_SEGUROS = ("GET", "HEAD", "OPTIONS")


def _igual(a, b):
    return hmac.compare_digest(str(a).encode("utf-8"), str(b).encode("utf-8"))
HORAS_INACTIVO = float(os.environ.get("PLANIFICADOR_INACTIVIDAD_HORAS", "4"))


@app.middleware("http")
async def sin_cache(request, call_next):
    """La interfaz se revisa siempre: así una actualización llega al navegador sin tener que vaciar la caché."""
    ACTIVIDAD["ultima"] = time.time()
    respuesta = await call_next(request)
    if not request.url.path.startswith("/api/"):
        respuesta.headers["Cache-Control"] = "no-cache"
    return respuesta


@app.middleware("http")
async def seguridad(request, call_next):
    """403 si la petición no viene de esta dirección u origen; 401 si una escritura no trae el token de la sesión."""
    if request.headers.get("host", "") not in HOSTS_VALIDOS:
        return JSONResponse({"error": "Dirección no permitida."}, status_code=403)
    if request.method not in METODOS_SEGUROS:
        origen = request.headers.get("origin")
        if origen is not None and origen not in ORIGENES_VALIDOS:
            return JSONResponse({"error": "Origen no permitido."}, status_code=403)
        if not (_igual(request.headers.get("x-planificador-token", ""), TOKEN)
                and _igual(request.cookies.get("planificador_token", ""), TOKEN)):
            return JSONResponse({"error": "La sesión del planificador ya no es válida. Recarga la página (F5)."}, status_code=401)
    return await call_next(request)


@app.exception_handler(HTTPException)
async def error_http(_, e):
    return JSONResponse({"error": e.detail}, status_code=e.status_code)


@app.exception_handler(Exception)
async def error_general(_, e):
    """Los errores llegan a la interfaz como {error: mensaje} legible."""
    return JSONResponse({"error": str(e) or e.__class__.__name__}, status_code=500)


def _datos(cadena):
    try:
        return json.loads(cadena or "{}")
    except Exception:
        raise HTTPException(400, "Datos del formulario inválidos.")


def _nombre_seguro(texto, ext):
    base = re.sub(r"[^0-9A-Za-zÁÉÍÓÚáéíóúÑñ]+", "_", texto or "archivo").strip("_")[:80] or "archivo"
    return f"{base}{ext}"


# ───────────────────────── Perfil ─────────────────────────

def _cuenta():
    return {"clave": rutas.clave_activa(), "nombre": rutas.nombre_de_cuenta(), "en_barra": rutas.EN_BARRA,
            "perfiles": rutas.perfiles_barra()}


@app.get("/api/identidad")
def identidad():
    """Usuario de Windows que inició este servidor (el lanzador no abre el de otra persona)."""
    return {"usuario_windows": getpass.getuser(), "app": "planificador"}


@app.get("/api/version")
def version_get():
    """Versión del planificador y de Barra, y si son compatibles."""
    return version.resumen()


@app.get("/api/cuenta")
def cuenta_get():
    """La cuenta que Barra Profe tiene activa (la única con la que trabaja el planificador)."""
    return _cuenta()


@app.get("/api/perfil")
def perfil_get():
    perfil = P.cargar()
    return {**asdict(perfil), "completo": perfil.completo, "voces": list(P.VOCES), "cuenta": _cuenta()}


@app.put("/api/perfil")
async def perfil_put(request: Request):
    nuevo = await request.json()
    actual = P.cargar()
    datos = {**asdict(actual), **{k: v for k, v in nuevo.items() if k in asdict(actual) and k != "ruta_logo"}}
    datos["duracion_defecto"] = int(datos.get("duracion_defecto") or 90)
    datos["actividades_extra"] = [
        {"nombre": str(e.get("nombre", "")).strip(), "curso": str(e.get("curso", "")).strip(),
         "minutos": int(e.get("minutos") or 0), "descripcion": str(e.get("descripcion", "")).strip()}
        for e in datos.get("actividades_extra", []) if str(e.get("nombre", "")).strip()]
    datos["asignaturas_webclass"] = {str(k).strip(): str(v).strip() for k, v in (datos.get("asignaturas_webclass") or {}).items()
                                     if str(k).strip() and str(v).strip()}
    perfil = P.Perfil(**P._sanear(datos))
    P.guardar(perfil)
    return {"ok": True, "completo": perfil.completo}


@app.post("/api/perfil/logo")
async def perfil_logo(archivo: UploadFile = File(...)):
    perfil = P.cargar()
    perfil.ruta_logo = P.guardar_logo(archivo.filename, await archivo.read())
    P.guardar(perfil)
    return {"ok": True}


@app.delete("/api/perfil/logo")
def perfil_logo_borrar():
    perfil = P.cargar()
    ruta = P.ruta_logo_completa(perfil)
    if ruta:
        os.remove(ruta)
    perfil.ruta_logo = ""
    P.guardar(perfil)
    return {"ok": True}


@app.get("/api/perfil/logo")
def perfil_logo_ver():
    ruta = P.ruta_logo_completa(P.cargar())
    if not ruta:
        raise HTTPException(404)
    return FileResponse(ruta, headers={"Cache-Control": "no-cache"})


# ───────────────────────── IA ─────────────────────────

@app.get("/api/ia/estado")
def ia_estado():
    cfg = ia.config()
    return {"proveedores": ia.estado_claves(), "proveedor": cfg["proveedor"], "modelo": cfg["modelo"],
            "respaldo": cfg["respaldo"], "lista": bool(ia.hay_proveedor())}


@app.post("/api/ia/claves")
async def ia_claves(request: Request):
    ia.guardar_claves(await request.json())  # {proveedor: clave}; null = sin cambios, "" = borrar
    return ia_estado()


@app.post("/api/ia/config")
async def ia_config(request: Request):
    d = await request.json()
    ia.guardar_config(d.get("proveedor"), d.get("modelo"), d.get("respaldo", True))
    return ia_estado()


@app.get("/api/ia/modelos")
def ia_modelos(proveedor: str):
    clave = ia.clave_guardada(ia.PROVEEDORES[proveedor]["secreto"]) if proveedor in ia.PROVEEDORES else ""
    if not clave:
        raise HTTPException(400, "Ese proveedor no tiene clave guardada.")
    try:
        return {"modelos": ia.modelos_disponibles(proveedor, clave), "conectado": True}
    except Exception as e:
        return {"modelos": [ia.PROVEEDORES[proveedor]["modelo"]], "conectado": False, "error": str(e)[:200]}


# ───────────────────────── Currículo ─────────────────────────

_estado_actualizacion = {"corriendo": False, "avance": 0, "total": 0, "error": "", "fin": None}


@app.get("/api/curriculo/asignaturas")
def curriculo_asignaturas():
    todas = curriculo.asignaturas()
    propias = [a for a in P.cargar().asignaturas if a in todas]
    return {"asignaturas": propias or todas, "todas": todas, "hay": curriculo.hay_curriculo()}


@app.get("/api/curriculo/cursos")
def curriculo_cursos(asignatura: str = ""):
    return {"cursos": curriculo.cursos(asignatura or None)}


@app.get("/api/curriculo/oa")
def curriculo_oa(asignatura: str, curso: str):
    return {"oa": curriculo.oa_del_curso(asignatura, curso)}


def _actualizar_en_segundo_plano():
    est = _estado_actualizacion
    est.update(corriendo=True, avance=0, total=0, error="", fin=None)
    try:
        actualizador.actualizar(lambda i, t, n: est.update(avance=i, total=t))
        est["fin"] = time.time()
    except Exception as e:
        est["error"] = str(e)
    finally:
        est["corriendo"] = False


@app.post("/api/curriculo/actualizar")
def curriculo_actualizar():
    if not _estado_actualizacion["corriendo"]:
        threading.Thread(target=_actualizar_en_segundo_plano, daemon=True).start()
    return _estado_actualizacion


@app.get("/api/curriculo/estado")
def curriculo_estado():
    return {**_estado_actualizacion, "hay": curriculo.hay_curriculo()}


# ───────────────────────── WebClass ─────────────────────────

@app.get("/api/webclass/constantes")
def webclass_constantes():
    return {"pautas_dua": wc.PAUTAS_DUA, "dua_defecto": wc.DUA_POR_DEFECTO, "min_dua": wc.MIN_DUA,
            "tipos_clase": list(wc.TIPOS_CLASE), "tipos_recurso": list(wc.TIPOS_RECURSO),
            "asignaturas_recurso": list(wc.asignaturas_recurso()), "niveles": wc.NIVELES_WEBCLASS,
            "max_mb": wc.MAX_MB_RECURSO, "enlace_marcador": wc.ENLACE_MARCADOR}


@app.post("/api/webclass/clase")
async def webclass_clase(request: Request):
    d = await request.json()
    oas = {o["codigo"]: o for o in curriculo.oa_del_curso(d.get("asignatura"), d.get("curso"))}
    sel = [c for c in d.get("oa_sel", []) if c in oas]
    claves = " ".join([d.get("oa_claves", ""), d.get("nombre", ""), d.get("objetivo", "")] + [oas[c]["texto"] for c in sel])
    texto = wc.datos_webclass(
        d.get("nombre", ""), d.get("fecha", ""), d.get("hora", "").strip(), str(d.get("duracion", "")).strip(),
        d.get("tipo", "Universal"), d.get("campos", {}), oa=", ".join(sel) if oas else d.get("oa_texto", ""),
        oa_claves=claves, dua=d.get("dua", []), oa_exactos=d.get("oa_exactos", False),
        oa_textos={c: oas[c]["texto"] for c in sel})
    return {"json": texto}


@app.post("/api/webclass/recurso")
async def webclass_recurso(datos: str = Form(...), archivo: UploadFile = File(...)):
    d = _datos(datos)
    contenido = await archivo.read()
    if len(contenido) / 1024 / 1024 > wc.MAX_MB_RECURSO:
        raise HTTPException(400, f"El archivo pesa más de {wc.MAX_MB_RECURSO} MB: súbelo a mano en WebClass.")
    mime = archivo.content_type or "application/octet-stream"
    texto = wc.datos_recurso(d["nombre"], d["autor"], d["niveles"], d["asignatura"], d.get("visible", True), d["tipo"],
                             contenido, archivo.filename, mime)
    return {"json": texto}


@app.get("/api/webclass/sugerencias")
def webclass_sugerencias(curso: str = "", archivo: str = ""):
    return {"nivel": wc.nivel_webclass(curso), "tipo": wc.tipo_por_archivo(archivo)}


# ───────────────────────── Barra Profe (envío a WebClass) ─────────────────────────

def _contexto_barra(cuenta_esperada=None):
    """(carpeta de Barra, cuenta de Barra con la que trabajar). Dentro de Barra siempre es la cuenta ACTIVA, y si cambió desde
    que se abrió la pantalla se aborta: jamás se escribe con la cuenta de otra persona."""
    compatible, mensaje = version.compatibilidad()
    if not compatible:
        raise HTTPException(409, mensaje)
    clave = rutas.clave_activa()
    if rutas.EN_BARRA and cuenta_esperada and cuenta_esperada != clave:
        raise HTTPException(409, f"La cuenta activa en Barra cambió de «{cuenta_esperada}» a «{clave}». "
                                 "Recarga la página para trabajar con la cuenta actual.")
    return rutas.ruta_barra(P.cargar().ruta_barra), (clave if rutas.EN_BARRA else "")


@app.get("/api/barra/estado")
def barra_estado(ruta: str | None = None):
    ruta = ruta if ruta is not None else rutas.ruta_barra(P.cargar().ruta_barra)
    ok, mensaje = barra.validar_ruta(ruta)
    compatible, aviso_version = version.compatibilidad()
    return {"configurada": bool((ruta or "").strip()), "valida": ok, "mensaje": mensaje, "en_barra": rutas.EN_BARRA,
            "cuenta": _cuenta(), "compatible": compatible, "mensaje_version": aviso_version}


@app.post("/api/barra/unidades")
async def barra_unidades(request: Request):
    d = await request.json()
    ruta, cuenta = _contexto_barra(d.get("cuenta"))
    return barra.ejecutar(ruta, "unidades", {"perfil": cuenta, "exigir_activo": rutas.EN_BARRA}, timeout=60)


@app.post("/api/barra/catalogo")
async def barra_catalogo(request: Request):
    """OA de una unidad, tal como los tiene WebClass (solo lectura)."""
    d = await request.json()
    ruta, cuenta = _contexto_barra(d.get("cuenta"))
    return barra.ejecutar(ruta, "catalogo", {"perfil": cuenta, "exigir_activo": rutas.EN_BARRA,
                                             "id_unidad": str(d["id_unidad"])}, timeout=240)


@app.get("/api/registro")
def registro_get():
    """Lo que el planificador creó en WebClass con la cuenta activa (más reciente primero)."""
    import csv
    ruta = rutas.registro_planificaciones()
    if not ruta or not os.path.isfile(ruta):
        return {"clases": [], "archivo": ruta}
    with open(ruta, newline="", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    return {"clases": filas[::-1][:200], "archivo": ruta}


@app.post("/api/registro/comprobar")
async def registro_comprobar(request: Request):
    """Solo lectura en WebClass: marca cuáles de esas clases siguen existiendo."""
    d = await request.json()
    ruta, cuenta = _contexto_barra(d.get("cuenta"))
    return barra.ejecutar(ruta, "comprobar", {"perfil": cuenta, "exigir_activo": rutas.EN_BARRA,
                                              "clases": [{"id_unidad": c["id_unidad"], "idclase": c["idclase"]} for c in d.get("clases", [])]},
                          timeout=240)


@app.post("/api/registro/eliminar")
async def registro_eliminar(request: Request):
    """Deshacer: elimina en WebClass clases que creó el planificador (solo las del registro de esta cuenta)."""
    d = await request.json()
    ruta, cuenta = _contexto_barra(d.get("cuenta"))
    clases = [{"id_unidad": str(c["id_unidad"]), "idclase": str(c["idclase"])} for c in d.get("clases", [])]
    if not clases:
        raise HTTPException(400, "No se indicó ninguna clase.")
    return barra.ejecutar(ruta, "eliminar", {"perfil": cuenta, "exigir_activo": rutas.EN_BARRA, "clases": clases}, timeout=300)


@app.post("/api/barra/enviar")
def barra_enviar_antigua():
    raise HTTPException(409, "Esta página quedó desactualizada. Recárgala con Ctrl+F5 y vuelve a intentar.")


def html_a_pdf_guardado(ruta_html):
    """PDF de una guía HTML (se guarda al lado para no convertirla dos veces). Con las imágenes y pictogramas ya cargados."""
    destino = os.path.splitext(ruta_html)[0] + ".pdf"
    if not os.path.isfile(destino):
        with open(ruta_html, encoding="utf-8") as f:
            datos = html_a_pdf(f.read())
        with open(destino, "wb") as f:
            f.write(datos)
    return destino


# Mismos tipos que `webclass_recursos.SUBCATEGORIA` de Barra (una prueba comprueba que no se desfasen)
EXTENSIONES_RECURSO = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".jpg", ".jpeg", ".png", ".mp3", ".wav", ".mp4")


@app.post("/api/barra/crear")
async def barra_crear(datos: str = Form(...), recursos: list[UploadFile] = File(default=[])):
    """Crea la clase en WebClass (unidad principal + réplicas en otros cursos) y adjunta los archivos al banco de recursos."""
    d = _datos(datos)
    ruta_barra, cuenta = _contexto_barra(d.get("cuenta"))
    c = d["clase"]
    c["hora"] = (c.get("hora") or "").strip() or "08:00"   # las clases se marcan siempre a las 08:00 si no se indica otra hora
    if not re.fullmatch(r"\d{1,2}:\d{2}", c["hora"]):
        raise HTTPException(400, "La hora de inicio no es válida.")
    if not c.get("nombre", "").strip():
        raise HTTPException(400, "La clase necesita un nombre.")
    destinos = d.get("destinos") or []
    if not destinos:
        raise HTTPException(400, "Elige la unidad donde se creará la clase.")
    for dest in destinos:
        fecha = dest.get("fecha") or c.get("fecha", "")
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", fecha):
            raise HTTPException(400, "Indica la fecha de la clase.")
        dest["fecha"] = fecha
    campos = {k: wc.texto_a_html(c.get("campos", {}).get(k, "")) for k in
              ("motivacion", "inicio", "desarrollo", "cierre", "recursos", "adecuaciones", "evaluacion")}
    dua = [int(n) for n in c.get("dua", []) if str(n).isdigit() and 1 <= int(n) <= 31]
    clase = {"nombre": c["nombre"].strip(), "fecha": c.get("fecha") or destinos[0]["fecha"], "hora": c["hora"].rjust(5, "0"),
             "horas": str(c.get("horas") or "2"), "tipo": wc.TIPOS_CLASE.get(c.get("tipo", "Universal"), "1"),
             "campos": campos, "dua": wc.completar_dua(dua)}

    with tempfile.TemporaryDirectory() as carpeta:
        subidos, avisos = {}, []      # «subidos»: archivos agregados a mano en esta petición
        for archivo in recursos:
            nombre = os.path.basename(archivo.filename or "")
            if not nombre.lower().endswith(EXTENSIONES_RECURSO):
                avisos.append(f"«{nombre}» no se adjunta: aquí solo se pueden subir PDF, Word, Excel, PowerPoint, imágenes (JPG, PNG), audio (MP3, WAV) y video (MP4).")
                continue
            ruta = os.path.join(carpeta, nombre)
            with open(ruta, "wb") as f:
                f.write(await archivo.read())
            subidos[nombre] = ruta
        lista = []
        for r in d.get("recursos", []):
            ruta = ruta_material(r.get("material_id"), r.get("archivo")) if r.get("material_id") else subidos.get(r.get("archivo"))
            if not ruta:
                avisos.append(f"No encontré el archivo «{r.get('archivo')}»: súbelo de nuevo para adjuntarlo.")
                continue
            if ruta.lower().endswith((".html", ".htm")):
                try:
                    ruta = html_a_pdf_guardado(ruta)
                except Exception as e:
                    avisos.append(f"No pude convertir «{os.path.basename(ruta)}» a PDF para subirla: {str(e)[:120]}")
                    continue
            if not ruta.lower().endswith(EXTENSIONES_RECURSO):
                avisos.append(f"«{os.path.basename(ruta)}» no se adjunta: aquí solo se pueden subir PDF, Word, Excel, PowerPoint, imágenes (JPG, PNG), audio (MP3, WAV) y video (MP4).")
                continue
            lista.append({"ruta": ruta, "nombre": (r.get("nombre") or os.path.splitext(os.path.basename(ruta))[0]).strip(),
                          "momento": r.get("momento", "desarrollo")})
        resultado = barra.ejecutar(ruta_barra, "crear", {
            "perfil": cuenta, "exigir_activo": rutas.EN_BARRA, "destinos": destinos, "clase": clase, "oa": d.get("oa", []),
            "oa_textos": d.get("oa_textos", {}), "recursos": lista, "nivel_hint": d.get("nivel_hint", ""), "permitir_sin_oa": bool(d.get("permitir_sin_oa", True))},
            timeout=900)
    resultado["avisos"] = avisos
    return resultado


# ───────────────────────── Planificación ─────────────────────────

def guardar_material(adjuntos, guia=None):
    """Guarda en disco los archivos con que se generó la planificación (y la guía PIE, si se adjuntó).
    Devuelve (id, [{nombre, tamano}], info_guia|None)."""
    if not adjuntos and not guia:
        return "", [], None
    mid = uuid.uuid4().hex[:12]
    carpeta = os.path.join(carpeta_materiales(), mid)
    os.makedirs(carpeta, exist_ok=True)
    guardados = []
    for nombre, contenido in adjuntos:
        limpio = os.path.basename(nombre)
        with open(os.path.join(carpeta, limpio), "wb") as f:
            f.write(contenido)
        guardados.append({"nombre": limpio, "tamano": len(contenido)})
    info_guia = None
    if guia:
        nombre_guardado = "GUIA-PIE_" + os.path.basename(guia[0])
        with open(os.path.join(carpeta, nombre_guardado), "wb") as f:
            f.write(guia[1])
        info_guia = {"nombre": os.path.basename(guia[0]), "guardado": nombre_guardado, "tamano": len(guia[1])}
    # Se conservan las últimas 40 planificaciones con material; las más antiguas se borran para no llenar el disco
    carpetas = sorted((os.path.join(carpeta_materiales(), c) for c in os.listdir(carpeta_materiales())), key=os.path.getmtime)
    for vieja in carpetas[:-40]:
        shutil.rmtree(vieja, ignore_errors=True)
    return mid, guardados, info_guia


def ruta_material(mid, nombre):
    """Ruta de un archivo guardado, o None si no existe (el id solo admite hexadecimal: sin rutas por el medio)."""
    if not re.fullmatch(r"[0-9a-f]{12}", mid or ""):
        return None
    ruta = os.path.join(carpeta_materiales(), mid, os.path.basename(nombre or ""))
    return ruta if os.path.isfile(ruta) else None


@app.post("/api/planificacion/generar")
async def planificacion_generar(datos: str = Form(...), archivos: list[UploadFile] = File(default=[]),
                                guia_pie: UploadFile | None = File(default=None)):
    d = _datos(datos)
    if not ia.hay_proveedor():
        raise HTTPException(400, "Falta conectar la IA: agrega una clave en «Claves de IA».")
    perfil = P.cargar()
    adjuntos = [(a.filename, await a.read()) for a in archivos if a.filename]
    guia = (guia_pie.filename, await guia_pie.read()) if guia_pie is not None and guia_pie.filename else None
    resultado = planificador.generar(
        perfil, d["asignatura"], d["curso"], d.get("tema", ""), d.get("indicaciones", ""), int(d.get("duracion") or 90),
        actividad_extra=d.get("actividad_extra"), link_canva=d.get("canva", ""), url_video=d.get("video", ""),
        archivos=adjuntos, guia_pie=guia)
    # El material original queda guardado: es el que se sube a WebClass como recurso y se asigna a la clase
    resultado["material_id"], resultado["archivos_material"], resultado["guia_pie"] = guardar_material(adjuntos, guia)
    return resultado


@app.post("/api/planificacion/excel")
async def planificacion_excel(request: Request):
    d = await request.json()
    meta, campos = d["meta"], d["campos"]
    oas = {o["codigo"]: o for o in curriculo.oa_del_curso(meta.get("asignatura"), meta.get("curso"))}
    oa_sel = [c for c in d.get("oa_sel", []) if c in oas]
    filas = [("Inicio", campos["inicio"]), ("Desarrollo", campos["desarrollo"]), ("Cierre", campos["cierre"]),
             ("Método de evaluación", campos["evaluacion"]), ("Recursos", campos["recursos"]),
             ("Adecuación curricular", campos["adecuaciones"]), ("Motivación", campos["motivacion"]),
             ("Objetivo de aprendizaje (OA)",
              "\n".join(f"- {c}: {oas[c]['texto']}" for c in oa_sel) if oas else d.get("oa_texto", "")),
             ("Pautas DUA", "\n".join(f"- {wc.PAUTAS_DUA[int(n)]}" for n in d.get("dua", [])))]
    nombre = _nombre_seguro(f"Planificacion_{meta.get('curso', 'clase')}_{date.today():%Y-%m-%d}", ".xlsx")
    return Response(generar_excel(meta, filas),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


# ───────────────────────── Historial ─────────────────────────

@app.get("/api/historial")
def historial_listar():
    return {"clases": [{"archivo": a, **r} for a, r in historial.listar()[:60]]}


@app.post("/api/historial")
async def historial_guardar(request: Request):
    return {"archivo": historial.guardar(await request.json())}


@app.delete("/api/historial/{archivo}")
def historial_borrar(archivo: str):
    historial.eliminar(archivo)
    return {"ok": True}


# ───────────────────────── Guías PIE ─────────────────────────

_materiales = {}  # id -> {texto, imagenes, t}: el material leído se reutiliza entre «elegir imágenes» y «generar»


def _guardar_material(material):
    mid = uuid.uuid4().hex[:12]
    _materiales[mid] = {**material, "t": time.time()}
    for viejo in sorted(_materiales, key=lambda k: _materiales[k]["t"])[:-6]:
        _materiales.pop(viejo, None)
    return mid


def _material(mid):
    if not mid:
        return {"texto": "", "imagenes": []}
    if mid not in _materiales:
        raise HTTPException(410, "El material ya no está en memoria: vuelve a subir los archivos.")
    return _materiales[mid]


@app.get("/api/pie/niveles")
def pie_niveles():
    return {"niveles": list(pie.NIVELES)}


@app.post("/api/pie/material")
async def pie_material(archivos: list[UploadFile] = File(...)):
    avisos = []
    texto, imagenes = pie.extraer_material([(a.filename, await a.read()) for a in archivos], avisos)
    mid = _guardar_material({"texto": texto, "imagenes": imagenes})
    return {"id": mid, "avisos": avisos, "vision": ia.proveedor_actual_tiene_vision(),
            "max_vision": pie.MAX_IMAGENES_VISION,
            "imagenes": [{"id": i["id"], "origen": i["origen"]} for i in imagenes]}


@app.get("/api/pie/imagen/{mid}/{img_id}")
def pie_imagen(mid: str, img_id: str, mini: int = 1):
    im = next((i for i in _material(mid)["imagenes"] if i["id"] == img_id), None)
    if not im:
        raise HTTPException(404)
    datos = im["datos"]
    if mini:
        pil = Image.open(io.BytesIO(datos))
        pil.thumbnail((320, 320))
        salida = io.BytesIO()
        pil.convert("RGB").save(salida, "JPEG", quality=70)
        return Response(salida.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})
    return Response(datos, media_type="image/png" if im["ext"] == "png" else "image/jpeg")


def _guardar_guia(html_guia, tema, nivel):
    os.makedirs(carpeta_guias(), exist_ok=True)
    nombre = f"guia_pie_{pie.slug(tema)}_{pie.slug(nivel)}.html"
    with open(os.path.join(carpeta_guias(), nombre), "w", encoding="utf-8") as f:
        f.write(html_guia)
    return nombre


def _armar(d, spec):
    perfil = P.cargar()
    html_guia, avisos = pie.armar_html(perfil, spec, d["nivel"], d.get("asignatura", ""), d.get("tema", ""),
                                       _material(d.get("material_id")), d.get("seleccion", []))
    return {"html": html_guia, "avisos": avisos, "archivo": _guardar_guia(html_guia, d.get("tema", ""), d["nivel"])}


@app.post("/api/pie/generar")
async def pie_generar(request: Request):
    d = await request.json()
    if not ia.hay_proveedor():
        raise HTTPException(400, "Falta conectar la IA: agrega una clave en «Claves de IA».")
    if not d.get("tema", "").strip():
        raise HTTPException(400, "Escribe el tema de la guía.")
    perfil = P.cargar()
    material = _material(d.get("material_id"))
    seleccion = d.get("seleccion") or []
    if not seleccion and ia.proveedor_actual_tiene_vision():
        seleccion = [i["id"] for i in material["imagenes"][:pie.MAX_IMAGENES_VISION]]  # la IA elige entre las primeras
    descripciones = d.get("descripciones", {})
    if not ia.proveedor_actual_tiene_vision():
        faltan = [i for i in seleccion if not descripciones.get(i, "").strip()]
        if faltan:
            raise HTTPException(400, "Escribe qué muestra cada imagen marcada: " + ", ".join(faltan))
    r = pie.generar(perfil, material, d.get("asignatura", ""), d["nivel"], d["tema"].strip(), d.get("indicaciones", ""),
                    seleccion, descripciones)
    armado = _armar({**d, "seleccion": seleccion}, r["spec"])
    return {**r, **armado, "seleccion": seleccion}


@app.post("/api/pie/rearmar")
async def pie_rearmar(request: Request):
    d = await request.json()
    return _armar(d, d["spec"])


@app.post("/api/pie/ortografia")
async def pie_ortografia(request: Request):
    d = await request.json()
    spec, cambios = pie.revisar_ortografia(d["spec"])
    return {"spec": spec, "ortografia": cambios, **_armar(d, spec)}


@app.post("/api/pie/pdf")
async def pie_pdf(request: Request):
    d = await request.json()
    return Response(html_a_pdf(d["html"]), media_type="application/pdf")


@app.post("/api/pie/word")
async def pie_word(request: Request):
    d = await request.json()
    perfil = P.cargar()
    material = _material(d.get("material_id"))
    imagenes = {i["id"]: (i["datos"], i["ext"]) for i in material["imagenes"] if i["id"] in d.get("seleccion", [])}
    datos, _ = guia_a_word(d["spec"], pie.NIVELES[d["nivel"]], imagenes, encabezado=perfil.encabezado(d.get("asignatura", "")))
    return Response(datos, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.get("/api/pie/guardadas")
def pie_guardadas():
    if not os.path.isdir(carpeta_guias()):
        return {"guias": []}
    archivos = sorted((f for f in os.listdir(carpeta_guias()) if f.endswith(".html")),
                      key=lambda f: os.path.getmtime(os.path.join(carpeta_guias(), f)), reverse=True)
    return {"guias": archivos}


@app.get("/api/pie/guardadas/{archivo}")
def pie_guardada(archivo: str):
    ruta = os.path.join(carpeta_guias(), os.path.basename(archivo))
    if not os.path.exists(ruta):
        raise HTTPException(404)
    return FileResponse(ruta, media_type="text/html")


@app.post("/api/apagar")
def apagar():
    """Cierra el servidor (botón «Cerrar el planificador»), útil cuando se inició en segundo plano desde Barra Profe."""
    threading.Timer(0.6, lambda: os._exit(0)).start()
    return {"ok": True}


# ───────────────────────── Interfaz web ─────────────────────────

@app.get("/")
def inicio():
    """La interfaz lleva el token de la sesión (en la página y en una cookie HttpOnly): sin él no se puede escribir."""
    with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
        pagina = f.read().replace("__TOKEN__", TOKEN)
    respuesta = HTMLResponse(pagina, headers={"Cache-Control": "no-cache"})
    respuesta.set_cookie("planificador_token", TOKEN, httponly=True, samesite="strict")
    return respuesta


app.mount("/", StaticFiles(directory=WEB), name="web")


def _vigilar_inactividad():
    """El servidor se inicia en segundo plano desde la barra: si nadie lo usa por varias horas, se cierra solo."""
    while True:
        time.sleep(300)
        if time.time() - ACTIVIDAD["ultima"] > HORAS_INACTIVO * 3600:
            os._exit(0)


def _ya_corriendo(url):
    """¿Ya hay un planificador de ESTE usuario de Windows en esa dirección?"""
    try:
        import urllib.request
        with urllib.request.urlopen(url + "/api/identidad", timeout=1.5) as r:
            d = json.load(r)
        return d.get("app") == "planificador" and d.get("usuario_windows") == getpass.getuser()
    except Exception:
        return False


if __name__ == "__main__":
    url = f"http://127.0.0.1:{PUERTO}"
    if _ya_corriendo(url):                      # ya hay un planificador abierto: solo se muestra
        webbrowser.open(url)
        raise SystemExit(0)
    if os.environ.get("PLANIFICADOR_SIN_NAVEGADOR") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    threading.Thread(target=_vigilar_inactividad, daemon=True).start()
    print(f"Planificador en {url}  (Ctrl+C para cerrar)")
    uvicorn.run(app, host="127.0.0.1", port=PUERTO, log_level="warning")
