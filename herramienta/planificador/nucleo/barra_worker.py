"""Proceso auxiliar que usa las funciones de «Barra Profe v2» para escribir en WebClass.

Se ejecuta aparte (nucleo/barra.py lo lanza) para que ni la sesión ni la contraseña de WebClass pasen por el servidor
del planificador, y para no mezclar módulos. No modifica la carpeta de Barra: solo importa su código (con la
escritura de archivos .pyc desactivada) y llama a sus funciones.

Entrada: un JSON por stdin {"op", "ruta_barra", ...}. Salida: una línea  ##RESULTADO {json}
La contraseña sale del Administrador de credenciales de Windows, igual que en Barra; si no está, avisa en vez de pedirla.

Operaciones:  unidades · catalogo · comprobar (solo lectura)  ·  crear (una clase en una o varias unidades, con recursos
adjuntos)  ·  subir (un archivo al banco de recursos)  ·  eliminar (clases que creó el planificador)
"""
import difflib
import json
import os
import re
import sys
import time

sys.dont_write_bytecode = True

PASO = {"actual": "iniciar"}
TIEMPOS = []   # [(paso, segundos, reintentos)] para saber dónde se va el tiempo
MOMENTOS = {"inicio": 1, "desarrollo": 2, "cierre": 3}


class ErrorDePaso(Exception):
    """Un fallo con el nombre del paso en que ocurrió (para que el mensaje diga qué se estaba haciendo)."""


def con_reintentos(paso, funcion, intentos=4):
    """Repite una operación de LECTURA cuando WebClass corta la conexión a mitad de la respuesta (pasa seguido).
    Nunca se usa para crear: ahí un reintento ciego podría duplicar la clase."""
    import requests
    PASO["actual"] = paso
    ultimo = None
    inicio = time.time()
    for n in range(intentos):
        try:
            resultado = funcion()
            TIEMPOS.append((paso, round(time.time() - inicio, 1), n))
            return resultado
        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            ultimo = exc
            time.sleep(1.5 * (n + 1))
    raise ErrorDePaso(f"WebClass cortó la conexión {intentos} veces seguidas ({ultimo.__class__.__name__}).")


def salir(obj):
    if TIEMPOS and isinstance(obj, dict):
        obj.setdefault("tiempos", TIEMPOS)
    print("##RESULTADO " + json.dumps(obj, ensure_ascii=False), flush=True)
    sys.exit(0)


def abrir(datos):
    """Importa los módulos de Barra y devuelve (w, c, pl, rec)."""
    herramienta = os.path.join(datos["ruta_barra"], "herramienta")
    if not os.path.exists(os.path.join(herramienta, "webclass_clases.py")):
        salir({"error": "La carpeta de Barra Profe no es válida: no encuentro herramienta\\webclass_clases.py."})
    sys.path.insert(0, herramienta)
    import webclass_clases as c
    import webclass_planificacion as pl
    import webclass_recursos as rec
    import webclass_tareas as w
    return w, c, pl, rec


def perfil_de(w, datos):
    nombre = datos.get("perfil") or w.PERFIL_POR_DEFECTO
    if nombre not in w.PERFILES:
        salir({"error": f"Barra no tiene el perfil «{nombre}». Perfiles: {', '.join(sorted(w.PERFILES)) or 'ninguno'}."})
    if datos.get("exigir_activo") and nombre != w.PERFIL_POR_DEFECTO:
        # Seguro final: nunca se escribe con una cuenta que no sea la que Barra tiene activa en este momento
        salir({"error": f"La cuenta activa en Barra es «{w.PERFIL_POR_DEFECTO}», no «{nombre}». No se hizo nada."})
    return nombre, w.PERFILES[nombre]


def iniciar_sesion(w, nombre, perfil):
    import keyring
    if not keyring.get_password(w.KEYRING_SERVICE, perfil["rut"]):
        salir({"error": "La contraseña de WebClass no está guardada en este equipo. Abre Barra Profe y entra a WebClass "
                        "una vez para guardarla."})

    def entrar():
        sesion = w.crear_session()
        w.login(sesion, perfil["rut"], w.obtener_password(perfil["rut"]))
        w.verificar_sesion(sesion, nombre, perfil["iduser"])   # aborta si la sesión no es de ese docente
        return sesion
    return con_reintentos("iniciar sesión en WebClass", entrar)


def sin_tildes(t):
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFD", str(t or "")) if unicodedata.category(ch) != "Mn").lower().strip()


def limpiar_oa(texto):
    """Texto de un OA del catálogo sin la basura de la página ('> OA12 Describir… <tr…')."""
    t = re.sub(r"^>\s*", "", texto or "")
    return re.split(r"\s*(?:<tr|Agregue su|Agregar\s+He finalizado)", t)[0].strip()


def resolver_oa(elegidos, textos, catalogo):
    """Ids del catálogo de ESTA unidad para los OA elegidos. Primero por etiqueta (OA12) y, si no está, por parecido
    del texto con el OA original. Devuelve (ids, faltantes)."""
    por_etiqueta, por_texto = {}, []
    for id_, crudo in catalogo:
        partes = limpiar_oa(crudo).split(None, 1)
        if partes:
            por_etiqueta[sin_tildes(partes[0])] = id_
            por_texto.append((id_, sin_tildes(partes[1] if len(partes) > 1 else "")))
    ids, faltan = [], []
    for etiqueta in elegidos:
        id_ = por_etiqueta.get(sin_tildes(etiqueta))
        if not id_ and textos.get(etiqueta):
            ref = sin_tildes(textos[etiqueta])
            puntaje, mejor = max(((difflib.SequenceMatcher(None, ref[:200], t[:200]).ratio(), i) for i, t in por_texto),
                                 default=(0, None))
            if puntaje >= 0.88:
                id_ = mejor
        if id_ and id_ not in ids:
            ids.append(id_)
        elif not id_:
            faltan.append(etiqueta)
    return ids, faltan


# ───────────────────────── operaciones ─────────────────────────

def op_unidades(datos):
    w, _c, _pl, _rec = abrir(datos)
    nombre, perfil = perfil_de(w, datos)
    salir({"perfiles": sorted(w.PERFILES), "perfil": nombre, "unidades": [
        {"id": u["id"], "curso": u["curso"], "nombre": u["nombre"], "asignatura": u.get("asignatura", "")}
        for u in perfil.get("unidades", [])]})


def op_catalogo(datos):
    """OA de una unidad tal como los muestra WebClass (solo lectura)."""
    w, c, pl, _rec = abrir(datos)
    nombre, perfil = perfil_de(w, datos)
    unidad = pl.unidad_del_perfil(perfil, datos["id_unidad"])
    s = iniciar_sesion(w, nombre, perfil)
    id_unidad = int(unidad["id"])
    existentes = con_reintentos("leer las clases de la unidad", lambda: w.listar_clases(s, id_unidad))
    if not existentes:
        salir({"error": "La unidad no tiene clases: no se puede leer su catálogo."})
    oa = con_reintentos("leer los OA de la unidad", lambda: c.catalogo(s, id_unidad=id_unidad, idclase=existentes[0]["idclase"], tipo="oft"))
    salir({"unidad": unidad["nombre"], "oa": [{"id": i, "texto": limpiar_oa(t)} for i, t in oa]})


CAMPOS_REGISTRO = ("fecha_creacion", "cuenta", "unidad", "idunidad", "curso", "idclase", "clase", "fecha_clase",
                   "oa_marcados", "recursos_ids", "origen")


def registrar_creacion(nombre_perfil, unidad, idclase, clase_nombre, fecha_clase, oa_marcados, recursos_ids, origen="planificador"):
    """Agrega una fila a datos\\registro_planificaciones[_<cuenta>].csv (misma carpeta y regla que los registros de Barra)."""
    import csv
    import datetime
    import rutas as rutas_barra
    archivo = rutas_barra.registro("registro_planificaciones", nombre_perfil)
    os.makedirs(os.path.dirname(archivo), exist_ok=True)
    existe = os.path.exists(archivo)
    with open(archivo, "a", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        if not existe:
            escritor.writerow(CAMPOS_REGISTRO)
        escritor.writerow([datetime.datetime.now().isoformat(timespec="seconds"), nombre_perfil, unidad["nombre"], unidad["id"],
                           unidad["curso"], idclase, clase_nombre, fecha_clase, oa_marcados, ";".join(recursos_ids), origen])


def op_comprobar(datos):
    """Solo lectura: de las clases pedidas [{id_unidad, idclase}], cuáles siguen existiendo en WebClass."""
    w, _c, pl, _rec = abrir(datos)
    nombre, perfil = perfil_de(w, datos)
    s = iniciar_sesion(w, nombre, perfil)
    por_unidad, existen = {}, {}
    for it in datos["clases"]:
        por_unidad.setdefault(str(it["id_unidad"]), []).append(str(it["idclase"]))
    for id_unidad, ids in por_unidad.items():
        try:
            pl.unidad_del_perfil(perfil, id_unidad)          # solo unidades de esta cuenta
        except ValueError:
            continue
        vivas = {c["idclase"] for c in con_reintentos("leer las clases de la unidad", lambda: w.listar_clases(s, int(id_unidad)))}
        existen.update({idc: idc in vivas for idc in ids})
    salir({"existen": existen})


def clases_registradas(nombre_perfil):
    """{(idunidad, idclase)} que el planificador anotó en el registro de esa cuenta."""
    import csv
    import rutas as rutas_barra
    archivo = rutas_barra.registro("registro_planificaciones", nombre_perfil)
    if not os.path.isfile(archivo):
        return set()
    with open(archivo, newline="", encoding="utf-8") as f:
        return {(str(fila.get("idunidad", "")), str(fila.get("idclase", ""))) for fila in csv.DictReader(f)}


def op_eliminar(datos):
    """Elimina clases que el planificador creó, con el mismo pedido que usa el botón «Eliminar» de WebClass.

    Seguros: solo clases que están en el registro de ESTA cuenta, solo en unidades de esta cuenta, y nunca una que ya tenga
    tarea asignada a las alumnas. Cada una se vuelve a leer después para comprobar que desapareció.
    """
    w, _c, pl, _rec = abrir(datos)
    nombre, perfil = perfil_de(w, datos)
    registradas = clases_registradas(nombre)
    s = iniciar_sesion(w, nombre, perfil)
    resultados = []
    for it in datos["clases"]:
        id_unidad, idclase = str(it["id_unidad"]), str(it["idclase"])
        base = {"id_unidad": id_unidad, "idclase": idclase}
        if (id_unidad, idclase) not in registradas:
            resultados.append({**base, "estado": "rechazada", "motivo": "No está en el registro del planificador: solo se eliminan "
                                                                         "las clases que él creó."})
            continue
        try:
            pl.unidad_del_perfil(perfil, id_unidad)
        except ValueError:
            resultados.append({**base, "estado": "rechazada", "motivo": "La unidad no es de esta cuenta."})
            continue
        try:
            vivas = {c["idclase"]: c for c in con_reintentos("leer las clases de la unidad", lambda: w.listar_clases(s, int(id_unidad)))}
            if idclase not in vivas:
                resultados.append({**base, "estado": "ya", "motivo": "La clase ya no existe."})
                continue
            if vivas[idclase].get("asignados"):
                resultados.append({**base, "estado": "rechazada", "motivo": f"La clase ya tiene tarea asignada a "
                                                                           f"{vivas[idclase]['asignados']} alumnas: no se elimina desde aquí."})
                continue
            PASO["actual"] = "eliminar la clase"
            s.post(f"{w.BASE}/home/planificacion/controladores/controladorPlanificacion.php",
                   data={"accion": 4, "caso": 3, "idClase": idclase, "idplan": id_unidad, "idUsuario": perfil["iduser"]},
                   headers=w.HEADERS, timeout=120).raise_for_status()
            despues = {c["idclase"] for c in con_reintentos("comprobar que se eliminó", lambda: w.listar_clases(s, int(id_unidad)))}
            if idclase in despues:
                resultados.append({**base, "estado": "error", "motivo": "WebClass no eliminó la clase (sigue en la unidad)."})
            else:
                resultados.append({**base, "estado": "eliminada", "clase": vivas[idclase]["nombre"]})
        except Exception as exc:
            resultados.append({**base, "estado": "error", "motivo": f"Falló al {PASO['actual']}. {str(exc)[:160]}"})
    salir({"resultados": resultados})


def op_subir(datos):
    """Sube un archivo al banco de recursos (o reutiliza uno propio con el mismo nombre y autor), sin adjuntarlo a una clase.

    datos: ruta, nombre, autor, niveles (claves de Barra: '5', '2M'), asignatura (id de WebClass), visible y, si se eligió,
    tipo_file (el tipo del formulario de WebClass; si no, Barra lo deduce de la extensión).
    """
    import inspect
    w, _c, _pl, rec = abrir(datos)
    nombre, perfil = perfil_de(w, datos)
    niveles = [rec.NIVELES[n] for n in datos.get("niveles") or [] if n in rec.NIVELES]
    if not niveles:
        salir({"error": "Elige al menos un nivel."})
    extra = {}
    if str(datos.get("tipo_file") or "").isdigit() and "tipo_file" in inspect.signature(rec.subir_o_reutilizar).parameters:
        extra["tipo_file"] = int(datos["tipo_file"])
    s = iniciar_sesion(w, nombre, perfil)
    PASO["actual"] = f"subir «{datos['nombre']}» al banco de recursos"
    inicio = time.time()
    id_recurso, subido = rec.subir_o_reutilizar(s, datos["ruta"], nombre=datos["nombre"], autor=datos["autor"],
                                                niveles=niveles, asignatura=int(datos["asignatura"]),
                                                visible=bool(datos.get("visible", True)), **extra)
    TIEMPOS.append((PASO["actual"], round(time.time() - inicio, 1), 0))
    salir({"id": str(id_recurso), "subido": bool(subido), "nombre": datos["nombre"]})


def niveles_de_curso(rec, curso):
    m = re.match(r"(\d)([BM])", str(curso).upper())
    if not m:
        return []
    clave = m.group(1) if m.group(2) == "B" else f"{m.group(1)}M"
    return [rec.NIVELES[clave]] if clave in rec.NIVELES else []


def id_asignatura(rec, nombre_asignatura):
    """Código de WebClass de la asignatura de una unidad, según la tabla única de Barra (rec.ASIGNATURAS).

    Manda la palabra que aparece primero: «Historia, Geografía y Ciencias Sociales» es Historia, no Ciencias.
    """
    t = sin_tildes(nombre_asignatura)
    halladas = [(t.index(clave), clave) for clave in rec.ASIGNATURAS if clave in t]
    return rec.ASIGNATURAS[min(halladas)[1]] if halladas else None


def asignatura_de_la_unidad(rec, perfil, nombre_asignatura):
    """Código de WebClass de la asignatura de una unidad: con las asignaturas que Barra leyó del WebClass de la cuenta
    (Música, Inglés, Religión…) y, si no las tiene o no calza, con la tabla única. None si no se reconoce."""
    if perfil.get("asignaturas_webclass"):
        try:
            import barra_utiles as bu
            hallada = bu.asignatura_de_texto(nombre_asignatura, bu.asignaturas_de_la_cuenta(perfil))
            if hallada:
                return hallada[2]
        except (ImportError, AttributeError):       # una Barra anterior a la lista por cuenta
            pass
    return id_asignatura(rec, nombre_asignatura)


def subir_recursos(s, rec, perfil, nombre_perfil, unidad, recursos, cache):
    """Sube al banco (o reutiliza) cada recurso. Devuelve ([(id_recurso, momento, nombre)], avisos). `cache` evita repetir
    la búsqueda y la subida cuando la misma clase se replica en otro curso."""
    ok, avisos = [], []
    niveles = cache.get("__niveles__") or niveles_de_curso(rec, unidad["curso"])
    # WebClass exige una asignatura en el formulario de subida. Barra la rellena sola con la que más dicta el docente
    # (o Ciencias si no la conoce); aquí se usa la de la unidad y, si no se reconoce, esa misma regla. Nunca bloquea.
    asignatura = asignatura_de_la_unidad(rec, perfil, unidad.get("asignatura", ""))
    if asignatura is None:
        import subir_carpeta as sc
        asignatura = sc.asignatura_principal(perfil)
    autor = perfil.get("nombre") or nombre_perfil.title()
    for r in recursos:
        clave = (r["ruta"], r["nombre"])
        if clave not in cache:
            if not niveles:
                avisos.append(f"No pude subir «{r['nombre']}»: no reconozco el nivel del curso «{unidad['curso']}».")
                cache[clave] = None
                continue
            PASO["actual"] = f"subir «{r['nombre']}» al banco de recursos"
            inicio = time.time()
            try:
                id_recurso, subido = rec.subir_o_reutilizar(s, r["ruta"], nombre=r["nombre"], autor=autor, niveles=niveles,
                                                            asignatura=asignatura, visible=True)
                TIEMPOS.append((PASO["actual"], round(time.time() - inicio, 1), 0))
                cache[clave] = (id_recurso, subido)
            except Exception as exc:
                avisos.append(f"No se pudo subir «{r['nombre']}»: {str(exc)[:140]}")
                cache[clave] = None
        if cache[clave]:
            ok.append((cache[clave][0], MOMENTOS.get(r.get("momento"), 2), r["nombre"]))
    return ok, avisos


def crear_en_unidad(s, w, c, pl, rec, perfil, nombre_perfil, destino, clase, oa_elegidos, oa_textos, recursos, cache, permitir_sin_oa):
    import requests
    unidad = pl.unidad_del_perfil(perfil, destino["id_unidad"])
    id_unidad = int(unidad["id"])
    fecha = destino.get("fecha") or clase["fecha"]
    existentes = con_reintentos("leer las clases de la unidad", lambda: w.listar_clases(s, id_unidad))
    base = {"unidad": unidad["nombre"], "curso": unidad["curso"], "id_unidad": id_unidad,
            "clases_en_la_unidad": len(existentes), "fecha": fecha}
    igual = [e for e in existentes if e["fechaini"] == fecha and pl.normal(e["nombre"]) == pl.normal(clase["nombre"])]
    if igual:
        return {**base, "estado": "ya", "idclase": igual[0]["idclase"],
                "motivo": "Ya existe una clase con ese nombre y esa fecha en la unidad."}

    ids_oa, faltan = [], []
    catalogo_conocido = bool(existentes)
    if existentes and oa_elegidos:
        oa_cat = con_reintentos("leer los OA de la unidad", lambda: c.catalogo(
            s, id_unidad=id_unidad, idclase=existentes[0]["idclase"], tipo="oft"))
        ids_oa, faltan = resolver_oa(oa_elegidos, oa_textos, oa_cat)
    if faltan and not permitir_sin_oa:
        return {**base, "estado": "pendiente", "oa_faltantes": faltan,
                "motivo": "La unidad no tiene estos OA: " + ", ".join(faltan) + ". No se creó nada."}

    campos = clase["campos"]
    PASO["actual"] = "crear la clase"

    def crear():
        return c.crear_clase(
            s, id_unidad=id_unidad, nombre=clase["nombre"], fecha=fecha, hora=clase["hora"], horas=str(clase["horas"]),
            tipo=int(clase.get("tipo") or 1), motivacion=campos.get("motivacion", ""), inicio=campos.get("inicio", ""),
            desarrollo=campos.get("desarrollo", ""), cierre=campos.get("cierre", ""), recursos=campos.get("recursos", ""),
            adecuaciones=campos.get("adecuaciones", ""), evaluacion=campos.get("evaluacion", ""))

    idclase = None
    for _ in range(3):
        try:
            idclase = crear()
            break
        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            # La respuesta se cortó, pero WebClass pudo haber creado la clase igual: se mira antes de reintentar
            time.sleep(2)
            ahora = con_reintentos("comprobar si la clase quedó creada", lambda: w.listar_clases(s, id_unidad))
            antes = {x["idclase"] for x in existentes}
            creada = [e for e in ahora if e["fechaini"] == fecha and pl.normal(e["nombre"]) == pl.normal(clase["nombre"])
                      and e["idclase"] not in antes]
            if creada:
                idclase = creada[0]["idclase"]
                break
    if not idclase:
        raise ErrorDePaso("WebClass cortó la conexión al crear la clase y no quedó creada. Intenta de nuevo en un momento.")

    avisos = []
    if oa_elegidos and not catalogo_conocido:
        # La unidad estaba vacía: ahora que existe la clase, ya se puede leer su catálogo de OA
        oa_cat = con_reintentos("leer los OA de la unidad", lambda: c.catalogo(s, id_unidad=id_unidad, idclase=idclase, tipo="oft"))
        ids_oa, faltan = resolver_oa(oa_elegidos, oa_textos, oa_cat)
    try:
        if ids_oa:
            con_reintentos("marcar los OA", lambda: c.marcar_atributos(s, idclase=idclase, ids=ids_oa, tipo="oft"))
        if clase.get("dua"):
            con_reintentos("marcar las pautas DUA", lambda: c.marcar_dua(s, idclase=idclase, casillas=[int(n) for n in clase["dua"]]))
    except Exception as exc:  # la clase ya existe: se informa qué falló en vez de ocultarlo
        avisos.append(f"La clase se creó, pero no se pudieron marcar OA o DUA: {str(exc)[:140]}")

    vinculados, ids_vinculados = 0, []
    if recursos:
        listos, av = subir_recursos(s, rec, perfil, nombre_perfil, unidad, recursos, cache)
        avisos += av
        for id_recurso, momento, nombre_recurso in listos:
            try:
                con_reintentos(f"adjuntar «{nombre_recurso}» a la clase",
                               lambda: rec.vincular(s, id_recurso, id_unidad, idclase, momento))
                vinculados += 1
                ids_vinculados.append(str(id_recurso))
            except Exception as exc:
                avisos.append(f"No se pudo adjuntar «{nombre_recurso}»: {str(exc)[:140]}")

    guardado = con_reintentos("verificar lo guardado", lambda: c.leer_clase(s, id_unidad=id_unidad, idclase=idclase))
    vacios = [k for k in ("inicio", "desarrollo", "cierre") if campos.get(k, "").strip() and not guardado.get(k, "").strip()]
    despues = con_reintentos("contar las clases", lambda: w.listar_clases(s, id_unidad))
    if vacios:
        avisos.append("WebClass guardó vacíos estos campos: " + ", ".join(vacios))
    if faltan:
        avisos.append("No están en esta unidad y quedaron sin marcar: " + ", ".join(faltan))
    try:                                   # el registro nunca debe impedir ni ocultar una creación que ya ocurrió
        registrar_creacion(nombre_perfil, unidad, idclase, clase["nombre"], fecha, len(ids_oa), ids_vinculados)
    except Exception as exc:
        avisos.append(f"La clase se creó, pero no pude anotarla en el registro: {str(exc)[:100]}")
    return {**base, "estado": "hecho" if not avisos else "con_avisos", "idclase": idclase, "oa_marcados": len(ids_oa),
            "oa_faltantes": faltan, "dua": len(clase.get("dua") or []), "recursos_adjuntos": vinculados,
            "clases_despues": len(despues), "avisos": avisos}


def op_crear(datos):
    """Crea la clase en una o más unidades (la primera es la principal; las demás son réplicas) con una sola sesión."""
    w, c, pl, rec = abrir(datos)
    nombre, perfil = perfil_de(w, datos)
    s = iniciar_sesion(w, nombre, perfil)
    resultados, cache = [], {}
    # El nivel del recurso es el de la unidad donde se crea la planificación (la principal y las réplicas)
    niveles = []
    for destino in datos["destinos"]:
        u = pl.unidad_del_perfil(perfil, destino["id_unidad"])
        niveles += [n for n in niveles_de_curso(rec, u["curso"]) if n not in niveles]
    if not niveles and datos.get("nivel_hint"):          # último recurso: el nivel con que se planificó en la app
        m = re.search(r"(\d)\s*°?\s*(B|M)", datos["nivel_hint"], re.I)
        if m:
            niveles = niveles_de_curso(rec, m.group(1) + m.group(2))
    cache["__niveles__"] = niveles
    for destino in datos["destinos"]:
        try:
            r = crear_en_unidad(s, w, c, pl, rec, perfil, nombre, destino, datos["clase"], datos.get("oa") or [],
                                datos.get("oa_textos") or {}, datos.get("recursos") or [], cache,
                                bool(datos.get("permitir_sin_oa")))
        except Exception as exc:   # un destino que falla no debe impedir los demás
            detalle = str(exc) if isinstance(exc, ErrorDePaso) else f"{exc.__class__.__name__}: {str(exc)[:200]}"
            r = {"estado": "error", "id_unidad": destino["id_unidad"], "motivo": f"Falló al {PASO['actual']}. {detalle}"}
        resultados.append(r)
    salir({"resultados": resultados})


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    datos = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    ops = {"unidades": op_unidades, "catalogo": op_catalogo, "crear": op_crear, "comprobar": op_comprobar, "eliminar": op_eliminar,
           "subir": op_subir}
    try:
        ops[datos["op"]](datos)
    except SystemExit:
        raise
    except Exception as exc:
        detalle = str(exc) if isinstance(exc, ErrorDePaso) else f"{exc.__class__.__name__}: {str(exc)[:300]}"
        salir({"error": f"Falló al {PASO['actual']}. {detalle}"})


if __name__ == "__main__":
    main()
