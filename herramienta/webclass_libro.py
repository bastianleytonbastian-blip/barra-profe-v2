"""
Registro diario del libro de clases (OA y leccionario) en Webclass.

Para cada bloque del día que sea tuyo y esté sin registrar, busca la clase de tu
planificación con esa fecha, la asocia al bloque y declara el OA y el leccionario.
Lo que no calza queda PENDIENTE y se anota en el registro, nunca se inventa.

La FIRMA no se toca: es tu clave personal con autenticador y la haces tú. El
script te lista al final qué bloques quedaron esperando tu firma.

Uso:
  python webclass_libro.py                 registra el día de hoy
  python webclass_libro.py --fecha 25/09/2026      (también «hoy» o «ayer»)
  python webclass_libro.py --desde 29/09/2026      lo pendiente de ese día hasta hoy
  python webclass_libro.py --desde 29/09/2026 --solo-listar   solo lista, sin escribir
  python webclass_libro.py --diagnostico --fecha ayer --cursos 4BA   por qué un día no calza
  python webclass_libro.py --simular       muestra lo que haría, sin escribir
  python webclass_libro.py --informe       solo el estado del mes, sin escribir
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import webclass_tareas as w

WEBICP = "https://webicp2.webescuela.cl"
API = f"{WEBICP}/api/portadaProfesor"
COLEGIO = "1795"
REGISTRO = os.path.join(w.carpeta_datos(), "registro_libro.csv")
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def sesion_libro(perfil: dict):
    """Inicia sesión en Webclass y entra al módulo del libro, devolviendo el token."""
    global COLEGIO
    COLEGIO = str(perfil.get("colegio") or COLEGIO)      # cada docente, su colegio
    s = w.crear_session()
    w.login(s, perfil["rut"], w.obtener_password(perfil["rut"]))
    w.verificar_sesion(s, perfil.get("nombre") or perfil["rut"], perfil["iduser"])
    s.get(f"{w.BASE}/home/planificacion/index.php", params={"wc": 1},
          headers=w.HEADERS, timeout=90)
    entrada = s.post(f"{WEBICP}/loginFromWebclass",
                     data={"username": w.usuario_del_libro(s, perfil["rut"]),
                           "module": "/classbook"},
                     headers=w.HEADERS, timeout=120)
    resp = s.get(f"{WEBICP}/portada-profesor", headers=w.HEADERS, timeout=120)
    m = re.search(r'name="csrf-token" content="([^"]+)"', resp.text)
    if not m:
        raise RuntimeError(w.por_que_no_entro(resp, resp.text, entrada))
    return s, m.group(1)


def api_get(s, ruta: str, params: dict, token: str):
    r = s.get(f"{API}/{ruta}", params=params,
              headers={**w.HEADERS, "X-CSRF-TOKEN": token,
                       "X-Requested-With": "XMLHttpRequest"}, timeout=120)
    r.raise_for_status()
    return r.json().get("data", {})


def api_post(s, ruta: str, params: dict, token: str):
    # Esta API recibe los parámetros en la query string, no en el cuerpo.
    r = s.post(f"{API}/{ruta}", params=params,
               headers={**w.HEADERS, "X-CSRF-TOKEN": token,
                        "X-Requested-With": "XMLHttpRequest"}, timeout=120)
    if r.status_code == 419:
        raise RuntimeError("Webclass respondió 419 (sesión expirada): vuelve a correr el script.")
    r.raise_for_status()
    return r.json()


def abrir_electivos(bloque: dict) -> list[dict]:
    """Un bloque de talleres se abre en uno por taller.

    En un «Bloque Electivo» el curso se reparte en talleres, cada uno con su
    profesora, sus alumnas y su propio OA, leccionario, asistencia y firma. El
    bloque que los contiene no tiene profesor ni asignatura: viene con
    profesor_id en None y los talleres dentro de curso_electivo_detalle.

    Tratar ese bloque como uno solo es lo que hacía que declarar un taller
    escribiera en el curso entero, y que los talleres no aparecieran nunca en
    el horario (ningún bloque calzaba con el id de la profesora).
    """
    talleres = bloque.get("curso_electivo_detalle") or []
    if not talleres:
        return [bloque]
    abiertos = []
    for t in talleres:
        propio = dict(bloque)
        propio.update({
            # Lo que identifica al taller, no al bloque que lo contiene.
            "id_bloque_detalle": t["id"],
            "profesor_id": t.get("profesor_id"),
            "nombreAsignatura": t.get("asignatura_nombre"),
            "asignatura_id": t.get("asignatura_id"),
            "val_oa": t.get("val_oa"), "val_leccionario": t.get("val_leccionario"),
            "val_asistencia": t.get("val_asistencia"), "val_firma": t.get("val_firma"),
            "cnt_presente": t.get("cnt_presente"), "cnt_ausente": t.get("cnt_ausente"),
            "cnt_atrasado": t.get("cnt_atrasado"), "cnt_retirado": t.get("cnt_retirado"),
            "lista_inasistentes": t.get("lista_inasistentes"),
            # Marcas propias del taller, para escribir en el lugar correcto.
            "es_electivo": True,
            "electivo_id": t.get("sp_id"),
            "electivo_nombre": t.get("electivo_nombre") or t.get("sp_nom") or "",
            "curso_electivo_detalle": None,
        })
        abiertos.append(propio)
    return abiertos


# Lo que Webclass devuelve para un curso es el MES entero, y cada consulta puede
# tardar decenas de segundos cuando el servidor anda lento. Se guarda lo leído
# para no pedir lo mismo dos veces en una corrida. No se vacía al escribir: cada
# bloque se lee una sola vez por corrida (antes de escribirlo), y escribir en un
# bloque no cambia los demás días ni los demás cursos; vaciarla obligaba a releer
# todo el mes de cada curso después de cada día.
_BLOQUES_DEL_MES: dict = {}
_CANDADO_BLOQUES = threading.Lock()


def _bloques_del_mes(s, curso_id: int, anio: int, mes: int, token: str) -> dict:
    clave = (id(s), curso_id, anio, mes)
    with _CANDADO_BLOQUES:
        if clave in _BLOQUES_DEL_MES:
            return _BLOQUES_DEL_MES[clave]
    data = api_get(s, "getBlocksByCourseID",
                   {"courseID": curso_id, "anio": anio, "mes": f"{mes:02d}",
                    "courseVisible": 1}, token)
    with _CANDADO_BLOQUES:
        _BLOQUES_DEL_MES[clave] = data
    return data


def bloques_de_cursos(s, cursos: dict, fecha: datetime.date, iduser: str, token: str,
                      solo_mios: bool = True, trabajadores: int = 4, al_terminar=None) -> dict:
    """Pide los bloques de varios cursos A LA VEZ y los devuelve en el mismo orden.

    Cada curso es una consulta aparte. Pedirlas de una en una hacía que 8 cursos
    tardaran 8 veces lo que tarda uno; en paralelo tardan lo que la más lenta.
    `al_terminar(curso, hechos, total)` avisa cada vez que llega una.
    """
    if not cursos:
        return {}
    resultados: dict = {}
    pool = ThreadPoolExecutor(max_workers=max(1, min(trabajadores, len(cursos))))
    try:
        futuros = {pool.submit(bloques_del_dia, s, curso_id, fecha, iduser, token, solo_mios):
                   curso for curso, curso_id in cursos.items()}
        for futuro in as_completed(futuros):
            curso = futuros[futuro]
            resultados[curso] = futuro.result()          # si una falla, se propaga el error
            if al_terminar:
                al_terminar(curso, len(resultados), len(cursos))
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    return {curso: resultados[curso] for curso in cursos}


def bloques_del_dia(s, curso_id: int, fecha: datetime.date, iduser: str, token: str,
                    solo_mios: bool = True):
    """Bloques de ese día; por defecto solo los del profesor del perfil.

    Con solo_mios=False devuelve todos los del curso, que es lo que se necesita
    para buscar de qué bloque anterior replicar la asistencia.
    """
    data = _bloques_del_mes(s, curso_id, fecha.year, fecha.month, token)
    iso = fecha.strftime("%Y-%m-%d")
    dia = []
    for b in data.get("bloques", []):
        if b.get("fecha") == iso:
            dia += abrir_electivos(b)
    if not solo_mios:
        return dia
    return [b for b in dia if str(b.get("profesor_id")) == str(iduser)]


def asignatura_del_bloque(s, curso_id: int, fecha: datetime.date, bloque: dict, token: str):
    """El id de asignatura que espera declare-oas (el del detalle, no el del horario)."""
    data = api_get(s, "getBlockDetailByDateAndBlockID",
                   {"bloqueID": f"[{bloque['id']}]", "fecha": fecha.strftime("%Y-%m-%d"),
                    "courseID": curso_id,
                    "detailID": f"[{bloque['id_bloque_detalle']}]"}, token)
    detalles = data.get("details", [])
    return detalles[0]["asignatura_id"] if detalles else None


def unidades_vigentes(s, token, curso_id: int, nivel: int, asignatura: str,
                      fecha: datetime.date, cache: dict, perfil: dict) -> list[dict]:
    """Unidades que Webclass ofrece hoy para ese curso y asignatura.

    Se preguntan cada vez en vez de tenerlas escritas en el perfil: cuando el
    colegio cambia de unidad (pasa varias veces al año) el script sigue
    encontrando las clases sin que haya que tocar nada.
    """
    clave = (curso_id, asignatura, fecha.isoformat())
    if clave in cache:
        return cache[clave]
    subs = api_get(s, "get-plan-subjects",
                   {"schoolID": COLEGIO, "gradeID": curso_id, "levelID": nivel}, token)
    ids = [x["id"] for x in subs.get("subjects", [])
           if str(x.get("sectornombre", "")).strip().lower() == (asignatura or "").strip().lower()]
    unidades = []
    for sub_id in ids:
        datos = api_get(s, "get-plan-units",
                        {"subjectID": sub_id, "schoolID": COLEGIO,
                         "profesorID": perfil["iduser"], "rolID": perfil.get("rol", 13),
                         "cursoID": curso_id, "levelID": nivel,
                         "date": fecha.strftime("%Y-%m-%d")}, token)
        unidades += datos.get("units", [])
    cache[clave] = unidades
    return unidades


def clase_del_dia(session_plan, unidades: list[dict], fecha: datetime.date, cache: dict):
    """Clases de la planificación con esa fecha, entre las unidades indicadas."""
    dia = fecha.strftime("%d/%m/%Y")
    candidatas = []
    for u in unidades:
        uid = u["id"]
        if uid not in cache:
            cache[uid] = w.listar_clases(session_plan, uid)
        for c in cache[uid]:
            if c["fechaini"] == dia:
                candidatas.append((u, c))
    return candidatas


# estado_asistencia de Webclass -> letra que espera el formulario
ESTADOS = {1: "P", 2: "AT", 3: "R", 4: "A"}


def texto_cuentas(estados) -> str:
    """«33 presentes · 7 ausentes · 0 atrasadas» a partir de los códigos de estado."""
    estados = list(estados)
    return (f"{estados.count(1)} presentes · {estados.count(4)} ausentes · "
            f"{estados.count(2)} atrasadas")


def nomina_curso(s, curso_id: int, nivel: int, fecha: datetime.date, anio: int, token: str,
                 electivo: int | str = ""):
    """Nómina del curso ese día (para saber cuántas alumnas son en total).

    Con electivo se pide la de ese taller, que es un subconjunto del curso.
    """
    data = api_get(s, "getStudentBySchool",
                   {"schoolID": COLEGIO, "year": anio, "levelID": nivel,
                    "fecha": fecha.strftime("%Y-%m-%d"), "course": curso_id,
                    "courseVisible": 0, "courseElectivo": electivo or "",
                    "calendario": 1}, token)
    if isinstance(data, dict):
        for clave in ("students", "alumnos", "data"):
            if isinstance(data.get(clave), list):
                return data[clave]
        return []
    return data or []


def asistencia_bloque(s, curso_id: int, bloque: dict, fecha: datetime.date,
                      iduser: str, token: str):
    electivo = bool(bloque.get("es_electivo"))
    data = api_get(s, "getAttendanceByCourseAndDate",
                   {"userID": iduser, "blockID": bloque["id"],
                    "date": fecha.strftime("%Y-%m-%d"), "curso": curso_id,
                    "detalle": bloque["id_bloque_detalle"], "courseVisible": 0,
                    "courseElectivo": bloque.get("electivo_id") or "" if electivo else "",
                    "isElectivo": 1 if electivo else 0}, token)
    return data.get("asistencia", []) if isinstance(data, dict) else []


MAX_FUENTES = 4          # cuántos bloques anteriores se prueban como fuente de asistencia


def bloques_fuente(bloques_dia: list, destino: dict) -> list[dict]:
    """Bloques anteriores del mismo día con asistencia tomada, del más cercano al más lejano.

    Los talleres se dejan fuera: tienen solo una parte del curso. No se exige que
    los contadores sumen exacto (con retiradas o ingresos nunca cuadran): lo que
    decide si sirve es que la asistencia incluya a todas las alumnas activas, y
    eso lo comprueba replicar_asistencia leyendo sus registros.
    """
    previos = [b for b in bloques_dia
               if b.get("inicio") and b["inicio"] < destino["inicio"]
               and b.get("val_asistencia") and not b.get("es_electivo")]
    return sorted(previos, key=lambda x: x["inicio"], reverse=True)[:MAX_FUENTES]


def elegir_fuente(candidatos: list[dict], ids_activas: set, leer) -> tuple[dict | None, list, list[str]]:
    """Primer candidato cuya asistencia cubre a todas las alumnas activas.

    `leer(bloque)` devuelve los registros de asistencia de ese bloque. Devuelve
    (bloque elegido, sus registros, qué pasó con los que se descartaron).
    """
    descartados = []
    for cand in candidatos:
        try:
            registros = leer(cand)
        except Exception as exc:  # noqa: BLE001  (un bloque con error no impide probar el siguiente)
            descartados.append(f"{cand['inicio']}: no se pudo leer ({str(exc)[:40]})")
            continue
        ids_registro = {r.get("alumno_id") for r in registros}
        faltan = len(ids_activas - ids_registro)
        if not faltan:
            return cand, registros, descartados
        descartados.append(f"{cand['inicio']}: le faltan {faltan} de {len(ids_activas)} alumnas")
    return None, [], descartados


def replicar_asistencia(s, perfil: dict, curso_id: int, bloques_dia: list, destino: dict,
                        fecha: datetime.date, token: str, simular: bool):
    """Copia al bloque la asistencia del bloque anterior que cubra al curso completo."""
    if destino.get("es_electivo"):
        # Un taller tiene solo una parte del curso. Copiarle la asistencia del
        # bloque anterior le pondría presente a alumnas que no son suyas, así
        # que se deja en blanco y queda anotado: esa asistencia se toma a mano.
        return None, (f"taller «{destino.get('electivo_nombre', '')[:28]}»: "
                      "la asistencia se toma a mano, no se copia del curso")
    nomina = nomina_curso(s, curso_id, destino.get("nivel"), fecha, fecha.year, token)
    # Las alumnas retiradas siguen en la nómina pero no se les pasa asistencia.
    activas = [a for a in nomina if a.get("retirado") != 1]
    if not activas:
        return None, "no se pudo leer la nómina del curso"
    ids_activas = {a.get("id") for a in activas}
    total = len(activas)
    candidatos = bloques_fuente(bloques_dia, destino)
    if not candidatos:
        return None, (f"sin bloque anterior con el curso completo ({total} alumnas): "
                      "ese día no hay un bloque anterior con asistencia tomada")
    fuente, registros, descartados = elegir_fuente(
        candidatos, ids_activas,
        lambda b: asistencia_bloque(s, curso_id, b, fecha, perfil["iduser"], token))
    if not fuente:
        return None, (f"sin bloque anterior con el curso completo ({total} alumnas): "
                      + "; ".join(descartados))

    por_alumna = {r["alumno_id"]: r for r in registros}
    origen = {al["id"]: por_alumna[al["id"]]["estado_asistencia"] for al in activas}
    desconocidos = sorted({str(e) for e in origen.values() if e not in ESTADOS})
    if desconocidos:
        # Nunca se envía un estado en blanco: la alumna quedaría sin marca en Webclass.
        return None, (f"la asistencia de {fuente['inicio']} trae un estado que la barra no conoce "
                      f"({', '.join(desconocidos)}): se toma a mano")
    cuentas = texto_cuentas(origen.values())
    detalle = (f"{fuente['inicio']} {(fuente.get('nombreAsignatura') or '')[:18]} "
               f"({cuentas})")
    if simular:
        return fuente, f"copiaría de {detalle}"

    attendance = []
    for al in activas:
        r = por_alumna[al.get("id")]          # la cobertura ya está comprobada
        attendance.append({
            "alumno": al["id"], "apoderado_id": r.get("apoderado_id", -1),
            "estado": ESTADOS[r["estado_asistencia"]],
            "estado_numero": r["estado_asistencia"],
            "bloque": destino["id"], "fecha": fecha.strftime("%Y-%m-%d"),
            "curso": curso_id, "nombrecurso": al.get("nombrecurso", ""),
            "nivel": destino.get("nivel"), "colegio": COLEGIO, "anio": fecha.year,
            "observaciones": "",  # las observaciones son del otro bloque, no se copian
            "lugar": r.get("modalidad", 1),
            "nombre_alumno": " ".join(filter(None, [al.get("nombre_usuario"),
                                                    al.get("apellido_paterno"),
                                                    al.get("apellido_materno")])),
            "retirado": al.get("retirado") == 1,
        })
    datos = {"profesor": perfil["iduser"],
             "profesor_nombre": perfil.get("nombre") or "",
             "attendance": json.dumps(attendance, ensure_ascii=False),
             "bloque_id": destino["id"], "detail": destino["id_bloque_detalle"],
             "curso": curso_id, "fecha": fecha.strftime("%Y-%m-%d"),
             "colegio": COLEGIO, "fechaInicio": destino.get("inicio") or "00:00:00",
             "isElectivo": 0}
    r = s.post(f"{API}/registerAttendanceOfClass", data=datos,
               headers={**w.HEADERS, "X-CSRF-TOKEN": token,
                        "X-Requested-With": "XMLHttpRequest"}, timeout=180)
    r.raise_for_status()
    # Comprobación: se relee el destino y se compara alumna por alumna con lo enviado.
    try:
        guardado = {x["alumno_id"]: x["estado_asistencia"]
                    for x in asistencia_bloque(s, curso_id, destino, fecha, perfil["iduser"], token)}
    except Exception as exc:  # noqa: BLE001
        return None, (f"se envió la asistencia pero no pude comprobarla ({str(exc)[:40]}): "
                      "revísala en Webclass")
    distintas = [i for i, e in origen.items() if guardado.get(i) != e]
    if distintas:
        faltan_a = sum(1 for i in distintas if origen[i] == 4)
        return None, (f"Webclass guardó distinto en {len(distintas)} alumnas "
                      f"(ausentes sin marcar: {faltan_a}): revísala en Webclass")
    return fuente, f"replicada y verificada desde {detalle}"


def ver_bloques(s, perfil: dict, fecha: datetime.date, token: str, filtro: str | None) -> None:
    """Despliega los bloques del día para revisar antes de escribir.

    Marca con «>» los que el script tomaría como tuyos. Sirve sobre todo con
    los talleres, donde un mismo horario se reparte en varios y hay que ver
    cuál es cuál.
    """
    cursos = {c.strip().upper() for c in filtro.split(",")} if filtro else None
    mio = str(perfil["iduser"])
    print(f"\n=== Bloques del {fecha:%d/%m/%Y} ===")
    print("  («>» = lo que el script registraría como tuyo)\n")
    algo = False
    for curso, curso_id in perfil["curso_ids"].items():
        if cursos and curso not in cursos:
            continue
        dia = bloques_del_dia(s, curso_id, fecha, perfil["iduser"], token, solo_mios=False)
        if not dia:
            continue
        print(f"  {curso}")
        for b in sorted(dia, key=lambda x: x.get("inicio") or ""):
            tuyo = str(b.get("profesor_id")) == mio
            algo = algo or tuyo
            if b.get("es_electivo"):
                que = f"[taller] {(b.get('electivo_nombre') or '')[:30]}"
            else:
                que = b.get("nombreAsignatura") or "(sin asignatura: recreo o bloque libre)"
            estado = "".join(c if b.get(k) else "·" for c, k in
                             (("O", "val_oa"), ("L", "val_leccionario"),
                              ("A", "val_asistencia"), ("F", "val_firma")))
            print(f"    {'>' if tuyo else ' '} {b['inicio']}-{b['termino']}  {estado}  {que}")
        print()
    print("  O=OA  L=leccionario  A=asistencia  F=firma  (· = falta)")
    if not algo:
        print("\n  Ningún bloque de ese día figura a tu nombre.")


def clave_bloque(curso: str, hora: str, id_detalle=None) -> str:
    """Identifica un bloque: es la misma clave de la casilla en la vista previa."""
    return f"{curso}|{hora}|{id_detalle}" if id_detalle not in (None, "") else f"{curso}|{hora}"


def esta_elegido(seleccion: set | None, curso: str, hora: str, clave: str) -> bool:
    """¿El docente dejó marcado este bloque? Sin selección, todos."""
    return seleccion is None or clave in seleccion or f"{curso}|{hora}" in seleccion


def registrar(fila: list):
    existe = os.path.exists(REGISTRO)
    with open(REGISTRO, "a", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f, delimiter=";")
        if not existe:
            wr.writerow(["corrida", "fecha_clase", "curso", "hora", "asignatura",
                         "clase", "estado", "firma"])
        wr.writerow(fila)


def informe_mes(s, perfil: dict, fecha: datetime.date, token: str, todo: bool = False):
    """El 'Informe' del calendario: estado de cada bloque del mes, curso por curso.

    Solo cuenta lo que ya pasó: una clase del viernes que viene no está
    «pendiente», todavía no ocurre, y mezclarla con lo atrasado hacía que el
    informe mostrara deudas que no existen. Con todo=True se ve el mes entero.
    """
    hoy = datetime.date.today()
    corte = hoy if (fecha.year, fecha.month) == (hoy.year, hoy.month) else None
    titulo = f"=== Registro de control de asignatura — {MESES[fecha.month - 1]} {fecha.year} ==="
    print(titulo)
    if corte and not todo:
        print(f"  (hasta hoy {corte:%d/%m}; con --mes-completo se ve el mes entero)")
    pendientes = por_venir = 0
    for curso, curso_id in perfil["curso_ids"].items():
        data = api_get(s, "getControlAsignatura",
                       {"idColegio": COLEGIO, "anio": 0,
                        "mesActual": MESES[fecha.month - 1], "cursoId": curso_id,
                        "firmanteId": 0, "profesorId": 0, "rCompletos": 0,
                        "rIncompletos": 0, "rSin": 0, "rTodosBloques": 0,
                        "profesor": perfil["iduser"]}, token)
        filas = data.get("controlAsignaturaData", [])
        if not filas:
            continue
        mostrables = []
        for b in filas:
            futuro = corte is not None and dia_de(b.get("fecha")) and dia_de(b["fecha"]) > corte
            if futuro:
                por_venir += 1
                if not todo:
                    continue
            mostrables.append((b, futuro))
        if not mostrables:
            continue
        print(f"\n  {curso}: {len(mostrables)} bloques")
        for b, futuro in mostrables:
            falta = [n for n, v in (("OA", b["val_oa"]), ("leccionario", b["val_leccionario"]),
                                    ("asistencia", b["val_asistencia"]), ("firma", b["val_firma"]))
                     if not v]
            if futuro:
                estado = "aún no es la clase"
            elif falta:
                estado = "falta " + ", ".join(falta)
                pendientes += 1
            else:
                estado = "completo"
            print(f"    {b['fecha']} {b['hora_inicio']} {b['asignatura_nombre'][:22]:22} {estado}")
    print(f"\n  Bloques con algo pendiente: {pendientes}")
    if por_venir and not todo:
        print(f"  (además hay {por_venir} bloque(s) de días que todavía no llegan)")


def mes_pedido(texto: str | None, por_defecto: datetime.date) -> datetime.date:
    """Convierte «09» o «09/2026» en una fecha de ese mes."""
    if not texto:
        return por_defecto
    partes = texto.replace("-", "/").split("/")
    try:
        mes = int(partes[0])
        anio = int(partes[1]) if len(partes) > 1 else por_defecto.year
        if not 1 <= mes <= 12:
            raise ValueError
    except (ValueError, IndexError):
        raise SystemExit(f"No entiendo el mes «{texto}». Usa 09 o 09/2026.") from None
    return datetime.date(anio, mes, 1)


def dia_de(texto: str | None) -> datetime.date | None:
    """La fecha de una fila del informe, venga como venga."""
    for formato in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime((texto or "").strip()[:10], formato).date()
        except ValueError:
            continue
    return None



DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _dias_habiles(desde: datetime.date, hasta: datetime.date) -> list[datetime.date]:
    dias, d = [], desde
    while d <= hasta:
        if d.weekday() < 5:             # sábado y domingo no hay clases
            dias.append(d)
        d += datetime.timedelta(days=1)
    return dias


def _clase_por_id(unidades: list[dict], idclase: str, cache: dict):
    """(unidad, clase) de la planificación con ese id, o None."""
    for u in unidades:
        for c in cache.get(u["id"], []):
            if str(c["idclase"]) == str(idclase):
                return u, c
    return None


def _opciones_de_clases(unidades: list[dict], fecha: datetime.date, cache: dict,
                        maximo: int = 8) -> list[dict]:
    """Las clases de la planificación más cercanas a esa fecha, para elegir a mano."""
    con_fecha, sin_fecha = [], []
    for u in unidades:
        for c in cache.get(u["id"], []):
            try:
                d = datetime.datetime.strptime(c.get("fechaini") or "", "%d/%m/%Y").date()
            except ValueError:
                sin_fecha.append((u, c))
                continue
            con_fecha.append((abs((d - fecha).days), d, u, c))
    con_fecha.sort(key=lambda x: (x[0], x[1]))
    elegidas = [(u, c, d.strftime("%d/%m")) for _, d, u, c in con_fecha[:maximo]]
    elegidas += [(u, c, "sin fecha") for u, c in sin_fecha[:2]]
    return [{"id": str(c["idclase"]), "texto": f"{c['nombre'][:46]} · {cuando}"}
            for u, c, cuando in elegidas]


def _cercanas_texto(unidades: list[dict], fecha: datetime.date, cache: dict) -> str:
    """«la última clase con fecha es …»: ayuda a ver hasta dónde llega la planificación."""
    fechadas = []
    for u in unidades:
        for c in cache.get(u["id"], []):
            try:
                fechadas.append((datetime.datetime.strptime(c.get("fechaini") or "", "%d/%m/%Y").date(), c))
            except ValueError:
                continue
    antes = [x for x in fechadas if x[0] < fecha]
    despues = [x for x in fechadas if x[0] > fecha]
    partes = []
    if antes:
        d, c = max(antes, key=lambda x: x[0])
        partes.append(f"la última con fecha es «{c['nombre'][:40]}» del {d:%d/%m}")
    if despues:
        d, c = min(despues, key=lambda x: x[0])
        partes.append(f"la siguiente es «{c['nombre'][:40]}» del {d:%d/%m}")
    return f" ({'; '.join(partes)})" if partes else ""


def completar_mes(s, perfil: dict, fecha: datetime.date, token: str, inicio,
                  filtro_cursos: str | None, simular: bool) -> tuple[list, list]:
    """Registra todos los días hábiles del mes que ya pasaron.

    Para ponerse al día con un mes atrasado sin ir día por día. No toca lo que
    no ha ocurrido: el último día es hoy, o el fin de mes si es un mes pasado.
    """
    import calendar

    ultimo_dia = calendar.monthrange(fecha.year, fecha.month)[1]
    hasta = min(datetime.date(fecha.year, fecha.month, ultimo_dia), datetime.date.today())
    desde = datetime.date(fecha.year, fecha.month, 1)
    print(f"\n=== Completando {MESES[fecha.month - 1]} {fecha.year}: "
          f"{len(_dias_habiles(desde, hasta))} días hábiles hasta el {hasta:%d/%m} ===")
    return registrar_rango(s, perfil, desde, hasta, token, inicio, filtro_cursos, simular)


def registrar_rango(s, perfil: dict, desde: datetime.date, hasta: datetime.date, token: str, inicio,
                    filtro_cursos: str | None, simular: bool, seleccion: set | None = None,
                    elecciones: dict | None = None, solo_listar: bool = False,
                    dias: list | None = None) -> tuple[list, list]:
    """Registra (o solo lista) los días hábiles de un rango, de uno en uno.

    Con `dias` se usan exactamente esos días (por ejemplo, los de varios
    períodos marcados) en vez del rango corrido de `desde` a `hasta`.

    El mes entero de cada curso se lee una sola vez, todos a la vez, y sirve para
    todos los días del rango; después cada día usa lo ya leído. Los cursos y las
    clases de la planificación también se comparten entre días.
    """
    dias = list(dias) if dias is not None else _dias_habiles(desde, hasta)
    cursos = {c.strip().upper() for c in filtro_cursos.split(",")} if filtro_cursos else None
    elegidos = {c: i for c, i in perfil["curso_ids"].items() if not cursos or c in cursos}
    meses = sorted({(d.year, d.month) for d in dias})
    total = len(meses) * len(elegidos) + len(dias)
    hechos_lectura = 0
    for anio, mes in meses:
        base = next(d for d in dias if (d.year, d.month) == (anio, mes))

        def leido(curso: str, _h: int, _t: int) -> None:
            nonlocal hechos_lectura
            hechos_lectura += 1
            print(f"##PROGRESO {hechos_lectura}/{total} Leyendo {curso} ({mes:02d}/{anio})", flush=True)

        bloques_de_cursos(s, elegidos, base, perfil["iduser"], token, solo_mios=False,
                          al_terminar=leido)
    resumen, sin_firma = [], []
    caches = {"clases": {}, "unidades": {}}
    for n, dia in enumerate(dias, 1):
        print(f"\n--- {DIAS_CORTOS[dia.weekday()]} {dia:%d/%m/%Y} ({n} de {len(dias)}) ---")
        print(f"##PROGRESO {hechos_lectura + n - 1}/{total} {dia:%d/%m}", flush=True)
        try:
            r, sf = registrar_dia(s, perfil, dia, token, inicio, filtro_cursos, simular,
                                  progreso=False, seleccion=seleccion, elecciones=elecciones,
                                  caches=caches, con_fecha=True, solo_listar=solo_listar)
        except Exception as exc:                     # noqa: BLE001
            # Un día que falle no puede dejar el resto sin registrar.
            print(f"  [ERROR] {dia:%d/%m}: {str(exc)[:120]}")
            w.item(f"dia|{dia:%Y-%m-%d}", "error", f"Día {dia:%d/%m}", "", "día",
                   motivo=str(exc)[:200])
            resumen.append((f"{dia:%d/%m}", f"ERROR: {str(exc)[:80]}"))
            continue
        resumen += r
        sin_firma += sf
    print(f"##PROGRESO {total}/{total}", flush=True)
    return resumen, sin_firma


def registrar_dia(s, perfil: dict, fecha: datetime.date, token: str, inicio,
                  filtro_cursos: str | None, simular: bool,
                  progreso: bool = True, seleccion: set | None = None,
                  elecciones: dict | None = None, caches: dict | None = None,
                  con_fecha: bool = False, solo_listar: bool = False) -> tuple[list, list]:
    """Declara OA, leccionario y asistencia de ese día.

    Devuelve (lo que hizo, lo que quedó sin firmar). Está aparte de main()
    para poder repetirlo día por día (registrar_rango). Con `solo_listar` no
    consulta la planificación ni escribe: solo informa qué bloques tienen algo
    por completar. `elecciones` son las clases que el docente escogió a mano
    ({clave del bloque: id de la clase}).
    """
    cursos = {c.strip().upper() for c in filtro_cursos.split(",")} if filtro_cursos else None
    caches = caches if caches is not None else {"clases": {}, "unidades": {}}
    cache, cache_unidades = caches["clases"], caches["unidades"]
    resumen, sin_firma = [], []
    elecciones = elecciones or {}

    elegidos = [(c, i) for c, i in perfil["curso_ids"].items() if not cursos or c in cursos]
    total = 2 * len(elegidos)           # primero se lee cada curso, después se registra

    def leido(curso: str, hechos: int, _cuantos: int) -> None:
        if progreso:
            print(f"##PROGRESO {hechos}/{total} Leyendo {curso}", flush=True)

    del_dia = bloques_de_cursos(s, dict(elegidos), fecha, perfil["iduser"], token,
                                solo_mios=False, al_terminar=leido)

    def clases_de(unidades: list[dict]) -> None:
        """Deja en la caché las clases de esas unidades (una consulta por unidad)."""
        for u in unidades:
            if u["id"] not in cache:
                cache[u["id"]] = w.listar_clases(s, u["id"])

    def procesar(b: dict, curso: str, curso_id: int, dia_completo: list, etiqueta: str,
                 clave: str, hora: str, asig: str, grupo: str) -> None:
        """Un bloque: asistencia, OA y leccionario. Cada resultado se informa como ítem."""
        # Asistencia: se replica del bloque anterior con el curso completo.
        if not b["val_asistencia"]:
            fuente, detalle_asis = replicar_asistencia(
                s, perfil, curso_id, dia_completo, b, fecha, token, simular)
            marca = "ASISTENCIA" if fuente else "ASISTENCIA EN BLANCO"
            print(f"  [{marca}] {etiqueta}: {detalle_asis}")
            if fuente:
                w.item(clave, "propuesto" if simular else "hecho", etiqueta, grupo,
                       "asistencia", detalle_asis)
            else:
                w.item(clave, "pendiente", etiqueta, grupo, "asistencia", motivo=detalle_asis)
            if not simular:
                registrar([inicio.strftime("%d/%m/%Y %H:%M"), fecha.strftime("%d/%m/%Y"),
                           curso, hora, asig, "", f"asistencia: {detalle_asis}",
                           "firmada" if b["val_firma"] else "sin firmar"])
            resumen.append((etiqueta, f"asistencia: {detalle_asis}"))
        if b["val_oa"] and b["val_leccionario"]:
            print(f"  [YA] {etiqueta}: OA y leccionario ya estaban.")
            w.item(clave, "ya", etiqueta, grupo, "OA y leccionario")
            return

        unidades = unidades_vigentes(s, token, curso_id, b.get("nivel"), asig,
                                     fecha, cache_unidades, perfil)
        clases_de(unidades)
        candidatas = clase_del_dia(s, unidades, fecha, cache)
        escogida = elecciones.get(clave)
        if escogida:                       # el docente eligió la clase a mano
            par = _clase_por_id(unidades, escogida, cache)
            if par:
                candidatas = [par]
        if len(candidatas) != 1:
            if not unidades:
                motivo = f"no encontré unidades de «{asig}» en tu planificación para ese curso"
                opciones = []
            elif not candidatas:
                motivo = ("no hay clase con esa fecha en la planificación"
                          + _cercanas_texto(unidades, fecha, cache))
                opciones = _opciones_de_clases(unidades, fecha, cache)
            else:
                motivo = f"{len(candidatas)} clases con esa fecha, no sé cuál usar"
                opciones = [{"id": str(c["idclase"]),
                             "texto": f"{c['nombre'][:46]} · {c.get('fechaini') or 'sin fecha'}"}
                            for _u, c in candidatas]
            print(f"  [PENDIENTE] {etiqueta}: {motivo}.")
            w.item(clave, "pendiente", etiqueta, grupo, "OA y leccionario", motivo=motivo,
                   opciones=opciones)
            resumen.append((etiqueta, "PENDIENTE: " + motivo))
            if not simular:
                registrar([inicio.strftime("%d/%m/%Y %H:%M"), fecha.strftime("%d/%m/%Y"),
                           curso, hora, asig, "", "PENDIENTE: " + motivo,
                           "firmada" if b["val_firma"] else "sin firmar"])
            return

        unidad, clase = candidatas[0]
        actividad = f"Clase realizada según planificación: {clase['nombre']}"
        if simular:
            print(f"  [SIMULAR] {etiqueta} -> {clase['nombre'][:45]}")
            w.item(clave, "propuesto", etiqueta, grupo, "OA y leccionario",
                   f"clase «{clase['nombre'][:60]}»")
            resumen.append((etiqueta, f"se declararía: {clase['nombre']}"))
            return

        # En un taller, la asignatura y el detalle son los suyos, y hay que
        # decirle a Webclass que es electivo: si no, escribe en el bloque
        # entero y el OA le queda puesto a todo el curso.
        electivo = bool(b.get("es_electivo"))
        asignatura_id = (b.get("asignatura_id") if electivo
                         else asignatura_del_bloque(s, curso_id, fecha, b, token))
        api_post(s, "plan-add-class",
                 {"classID": clase["idclase"], "detalle": b["id_bloque_detalle"],
                  "date": fecha.strftime("%Y-%m-%d"), "start": b["inicio"],
                  "end": b["termino"], "asignatura": asignatura_id,
                  "idusuario": perfil["iduser"],
                  "isElectivo": "true" if electivo else "false"}, token)
        api_post(s, "declare-oas",
                 {"bloque": 0, "detalle": b["id_bloque_detalle"],
                  "idusuario": perfil["iduser"], "asignatura": asignatura_id,
                  "actividad": actividad,
                  "isElectivo": 1 if electivo else 0}, token)
        print(f"  [OK] {etiqueta} -> {clase['nombre'][:45]}")
        w.item(clave, "hecho", etiqueta, grupo, "OA y leccionario",
               f"clase «{clase['nombre'][:60]}»")
        resumen.append((etiqueta, "declarado"))
        registrar([inicio.strftime("%d/%m/%Y %H:%M"), fecha.strftime("%d/%m/%Y"),
                   curso, hora, asig, clase["nombre"], "declarado",
                   "firmada" if b["val_firma"] else "sin firmar"])

    for n_curso, (curso, curso_id) in enumerate(elegidos, 1):
        if progreso:
            print(f"##PROGRESO {len(elegidos) + n_curso - 1}/{total} {curso}", flush=True)
        dia_completo = del_dia[curso]
        for b in [x for x in dia_completo
                  if str(x.get("profesor_id")) == str(perfil["iduser"])]:
            hora = f"{b['inicio']}-{b['termino']}"
            asig = b.get("nombreAsignatura") or ""
            etiqueta = f"{curso} {hora} {asig[:20]}"
            if b.get("es_electivo"):
                etiqueta = f"{curso} {hora} [taller] {(b.get('electivo_nombre') or '')[:24]}"
            clave = clave_bloque(curso, hora, b.get("id_bloque_detalle"))
            grupo = curso
            if con_fecha:               # varios días en una corrida: la fecha distingue
                etiqueta = f"{fecha:%d/%m} {etiqueta}"
                clave += f"|{fecha:%Y-%m-%d}"
                grupo = f"{DIAS_CORTOS[fecha.weekday()]} {fecha:%d/%m}"
            if not b["val_firma"]:
                sin_firma.append(etiqueta)

            if solo_listar:             # solo informar qué tiene algo por completar
                faltan = [n for n, k in (("OA", "val_oa"), ("leccionario", "val_leccionario"),
                                         ("asistencia", "val_asistencia")) if not b.get(k)]
                if faltan:
                    w.item(clave, "propuesto", etiqueta, grupo, "bloque",
                           "se completará: " + ", ".join(faltan))
                    resumen.append((etiqueta, "por completar: " + ", ".join(faltan)))
                continue

            if not esta_elegido(seleccion, curso, hora, clave):
                print(f"  Omitido por ti: {etiqueta}")
                w.item(clave, "omitido", etiqueta, grupo, "bloque")
                resumen.append((etiqueta, "omitido por ti"))
                continue
            try:
                procesar(b, curso, curso_id, dia_completo, etiqueta, clave, hora, asig, grupo)
            except Exception as exc:                      # noqa: BLE001
                # Un bloque que falle no deja sin informar a los demás: se
                # cuenta como "no pude" con su motivo y se sigue con el resto.
                print(f"  [ERROR] {etiqueta}: {str(exc)[:140]}")
                w.item(clave, "error", etiqueta, grupo, "bloque", motivo=str(exc)[:200])
                resumen.append((etiqueta, f"ERROR: {str(exc)[:80]}"))

    if progreso:
        print(f"##PROGRESO {total}/{total}", flush=True)
    return resumen, sin_firma


def _normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni signos: para comparar nombres de asignaturas."""
    import unicodedata
    sin_tildes = unicodedata.normalize("NFD", texto or "")
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", sin_tildes.lower()).strip()


def diagnosticar(s, perfil: dict, fecha: datetime.date, token: str, filtro: str | None) -> None:
    """Informe de SOLO LECTURA de por qué un día no se puede registrar solo.

    Para cada bloque del docente muestra qué ve Webclass (flags y contadores), si
    hay un bloque anterior del que copiar la asistencia y por qué se descarta,
    qué asignaturas y unidades ofrece la planificación y qué clases tienen fecha
    cerca. No escribe nada y no imprime nombres de alumnas: solo conteos.
    """
    cursos = {c.strip().upper() for c in filtro.split(",")} if filtro else None
    mio = str(perfil["iduser"])
    print(f"=== Diagnóstico del libro · {fecha:%d/%m/%Y} ===")
    print(f"  Colegio usado: {COLEGIO} · rol: {perfil.get('rol', '(no está en el perfil, se usa 13)')}"
          f" · iduser: {mio}")
    print(f"  Datos del perfil que faltan: "
          f"{', '.join(k for k in ('nombre', 'colegio', 'rol', 'curso_niveles', 'curso_asignaturas') if k not in perfil) or 'ninguno'}")
    for curso, curso_id in perfil["curso_ids"].items():
        if cursos and curso not in cursos:
            continue
        dia = bloques_del_dia(s, curso_id, fecha, perfil["iduser"], token, solo_mios=False)
        print(f"\n--- {curso} (id {curso_id}) · {len(dia)} bloque(s) ese día ---")
        for b in sorted(dia, key=lambda x: x.get("inicio") or ""):
            es_mio = str(b.get("profesor_id")) == mio
            flags = "".join(c if b.get(k) else "·" for c, k in
                            (("O", "val_oa"), ("L", "val_leccionario"),
                             ("A", "val_asistencia"), ("F", "val_firma")))
            cuentas = "/".join(str(b.get(k) or 0) for k in
                               ("cnt_presente", "cnt_ausente", "cnt_atrasado", "cnt_retirado"))
            print(f"  {'>' if es_mio else ' '} {b.get('inicio')}-{b.get('termino')} {flags} "
                  f"P/A/At/R={cuentas} nivel={b.get('nivel')} detalle={b.get('id_bloque_detalle')} "
                  f"{'[taller] ' if b.get('es_electivo') else ''}{b.get('nombreAsignatura') or '(sin asignatura)'}")
        mios = [b for b in dia if str(b.get("profesor_id")) == mio]
        if not mios:
            print("  (ningún bloque de ese día figura a tu nombre)")
            continue
        nivel = mios[0].get("nivel")
        # --- la lista del curso
        nomina = nomina_curso(s, curso_id, nivel, fecha, fecha.year, token)
        activas = [a for a in nomina if a.get("retirado") != 1]
        print(f"\n  Nómina (levelID={nivel}): {len(nomina)} alumnas · {len(nomina) - len(activas)} "
              f"retiradas · {len(activas)} activas")
        if nomina:
            print(f"  Campos de cada alumna: {', '.join(sorted(nomina[0]))}")
        ids_activas = {a.get("id") for a in activas}
        # --- de dónde se podría copiar la asistencia
        for destino in mios:
            if destino.get("val_asistencia"):
                continue
            print(f"\n  Bloque {destino.get('inicio')} SIN asistencia: ¿de qué bloque anterior se copia?")
            previos = sorted([b for b in dia if b.get("inicio") and b["inicio"] < destino["inicio"]
                              and b.get("val_asistencia")],
                             key=lambda x: x["inicio"], reverse=True)
            if not previos:
                print("    No hay ningún bloque anterior con asistencia tomada ese día.")
            for b in previos:
                contadas = sum(b.get(k) or 0 for k in
                               ("cnt_presente", "cnt_ausente", "cnt_atrasado", "cnt_retirado"))
                regla_vieja = "sirve" if (activas and contadas == len(activas)) else \
                    f"se descarta (contadas {contadas} ≠ activas {len(activas)})"
                try:
                    registros = asistencia_bloque(s, curso_id, b, fecha, perfil["iduser"], token)
                except Exception as exc:  # noqa: BLE001
                    registros, error = [], str(exc)[:80]
                else:
                    error = ""
                ids_reg = {r.get("alumno_id") for r in registros}
                faltan = len(ids_activas - ids_reg)
                print(f"    {b.get('inicio')} {b.get('nombreAsignatura') or ''}: regla de contadores: "
                      f"{regla_vieja} · registros leídos: {len(registros)}"
                      + (f" · error: {error}" if error else "")
                      + f" · cobertura de alumnas activas: {len(ids_activas) - faltan}/{len(ids_activas)}"
                      + ("  ← serviría por cobertura" if not faltan and ids_activas else ""))
        # --- planificación
        asignaturas = sorted({(b.get("nombreAsignatura") or "") for b in mios})
        print(f"\n  Planificación. Asignatura(s) del bloque: {', '.join(asignaturas) or '(ninguna)'}")
        subs = api_get(s, "get-plan-subjects",
                       {"schoolID": COLEGIO, "gradeID": curso_id, "levelID": nivel}, token)
        subjects = subs.get("subjects", [])
        print(f"  El plan ofrece {len(subjects)} asignatura(s) para este curso:")
        for x in subjects:
            igual = any((x.get("sectornombre") or "").strip().lower() == a.strip().lower()
                        for a in asignaturas)
            parecida = any(_normalizar(a) and (_normalizar(a) in _normalizar(x.get("sectornombre", ""))
                                               or _normalizar(x.get("sectornombre", "")) in _normalizar(a))
                           for a in asignaturas)
            print(f"    id={x.get('id')} «{x.get('sectornombre')}»"
                  + ("  ← coincide exacto" if igual else "  ← se parece (la regla actual NO la tomaría)"
                     if parecida else ""))
        if subjects:
            print(f"  Campos de cada asignatura del plan: {', '.join(sorted(subjects[0]))}")
        unidades_api = []
        for x in subjects:
            datos = api_get(s, "get-plan-units",
                            {"subjectID": x["id"], "schoolID": COLEGIO, "profesorID": perfil["iduser"],
                             "rolID": perfil.get("rol", 13), "cursoID": curso_id, "levelID": nivel,
                             "date": fecha.strftime("%Y-%m-%d")}, token)
            for u in datos.get("units", []):
                unidades_api.append((x.get("sectornombre"), u))
        print(f"  Unidades que devuelve la API para ese día: {len(unidades_api)}")
        for asig, u in unidades_api:
            print(f"    unidad {u.get('id')} «{u.get('nombre')}» (asignatura «{asig}»)")
        del_perfil = [u for u in perfil.get("unidades", []) if u.get("curso") == curso]
        print(f"  Unidades del perfil para {curso}: {len(del_perfil)}")
        for u in del_perfil:
            print(f"    unidad {u.get('id')} «{u.get('nombre')}»"
                  + ("" if any(str(u.get('id')) == str(a.get('id')) for _, a in unidades_api)
                     else "  ← la API no la devolvió para ese día"))
        # --- clases con fecha cercana
        vistas = {str(u["id"]): u for _, u in unidades_api}
        vistas.update({str(u["id"]): u for u in del_perfil})
        for id_unidad, u in vistas.items():
            resp = s.post(f"{w.BASE}/home/planificacion/controladores/controladorPlanificacion.php",
                          data={"caso": 2, "accion": 2, "idclase": 0, "idplan": id_unidad},
                          headers=w.HEADERS, timeout=180)
            crudas = len(re.findall(r'data-clase="\d+"', resp.text))
            clases = w.listar_clases(s, int(id_unidad))
            con_fecha = [c for c in clases if c["fechaini"]]
            cercanas = []
            for c in con_fecha:
                try:
                    d = datetime.datetime.strptime(c["fechaini"], "%d/%m/%Y").date()
                except ValueError:
                    continue
                if abs((d - fecha).days) <= 3:
                    cercanas.append((d, c))
            print(f"\n  Unidad {id_unidad} «{u.get('nombre')}»: {len(clases)} clases leídas "
                  f"({crudas} marcas en el HTML) · {len(con_fecha)} con fecha")
            for d, c in sorted(cercanas, key=lambda x: x[0]):
                marca = "  ← es la del día" if d == fecha else ""
                print(f"    {d:%d/%m} {c['nombre'][:60]} (id {c['idclase']}){marca}")
            if not cercanas:
                print("    ninguna clase con fecha dentro de ±3 días")


def _fecha_pedida(texto: str | None) -> datetime.date:
    """«hoy», «ayer» o DD/MM/AAAA (vacío = hoy)."""
    t = (texto or "").strip().lower()
    hoy = datetime.date.today()
    if t in ("", "hoy"):
        return hoy
    if t == "ayer":
        return hoy - datetime.timedelta(days=1)
    return datetime.datetime.strptime(t, "%d/%m/%Y").date()


def _lista_de_fechas(texto: str) -> list[datetime.date]:
    """«05/10/2026,06/10/2026» (o «hoy», «ayer») -> días hábiles, sin repetir y en orden."""
    dias = {_fecha_pedida(t) for t in (texto or "").split(",") if t.strip()}
    return sorted(d for d in dias if d.weekday() < 5)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fecha", metavar="DD/MM/YYYY", help="Día a registrar (por defecto, hoy).")
    p.add_argument("--cursos", metavar="6BB,8BA", help="Solo estos cursos.")
    p.add_argument("--simular", action="store_true", help="No escribe nada; muestra el plan.")
    p.add_argument("--informe", action="store_true",
                   help="Solo muestra el estado del mes (el botón 'Informe'), sin escribir.")
    p.add_argument("--perfil", choices=sorted(w.PERFILES), default=w.PERFIL_POR_DEFECTO,
                   help="Docente cuyo libro se registra.")
    p.add_argument("--mes", metavar="MM o MM/YYYY",
                   help="Mes del informe (por defecto el actual). Ej: --mes 09")
    p.add_argument("--mes-completo", action="store_true",
                   help="En el informe, muestra también los días que no han llegado.")
    p.add_argument("--completar-mes", action="store_true",
                   help="Registra TODOS los días hábiles del mes que ya pasaron, "
                        "no solo hoy. Para ponerse al día con un mes atrasado.")
    p.add_argument("--seleccion", metavar="ARCHIVO.json",
                   help="Solo registra los bloques cuya clave esté en {\"claves\": [...]} "
                        "(lo que se marcó en la vista previa de la barra).")
    p.add_argument("--desde", metavar="DD/MM/YYYY",
                   help="Registra los días hábiles desde esta fecha hasta --hasta (hacia atrás).")
    p.add_argument("--hasta", metavar="DD/MM/YYYY",
                   help="Último día del rango de --desde (por defecto, hoy).")
    p.add_argument("--fechas", metavar="DD/MM/YYYY,DD/MM/YYYY",
                   help="Esos días exactos (los de varios períodos marcados). Con --diagnostico "
                        "revisa cada bloque sin escribir; sin él registra esos días.")
    p.add_argument("--solo-listar", action="store_true",
                   help="No escribe ni consulta la planificación: solo lista los bloques que "
                        "tienen algo por completar (la vista previa de la barra).")
    p.add_argument("--diagnostico", action="store_true",
                   help="Informe de solo lectura de por qué un día no se puede registrar solo "
                        "(lista del curso, bloques anteriores, planificación). No escribe nada.")
    p.add_argument("--ver-bloques", action="store_true",
                   help="Lista todos los bloques del día, con su profesor y sus "
                        "talleres, marcando cuáles son tuyos. No escribe nada.")
    args = p.parse_args()

    perfil = w.PERFILES[args.perfil]
    global REGISTRO
    REGISTRO = w.rutas.registro("registro_libro", args.perfil)      # el CSV de este docente
    seleccion = w.leer_seleccion(args.seleccion)
    elecciones = w.leer_elecciones(args.seleccion)
    fecha = _fecha_pedida(args.fecha)
    inicio = datetime.datetime.now()
    print(f"=== Libro de clases: {fecha.strftime('%d/%m/%Y')} "
          f"({inicio.strftime('%H:%M:%S')}) ===")

    s, token = sesion_libro(perfil)
    if args.informe:
        informe_mes(s, perfil, mes_pedido(args.mes, fecha), token, args.mes_completo)
        return
    if args.ver_bloques:
        ver_bloques(s, perfil, fecha, token, args.cursos)
        return
    if args.diagnostico:
        dias = _lista_de_fechas(args.fechas) if args.fechas else [fecha]
        hoy = datetime.date.today()
        if not dias or any(d > hoy for d in dias) or len(dias) > 250:
            raise ValueError("Las fechas no sirven: hace falta al menos un día hábil que ya haya "
                             "pasado, y como máximo 250.")
        if len(dias) == 1:
            diagnosticar(s, perfil, dias[0], token, args.cursos)
            return
        print(f"=== Diagnóstico de {len(dias)} días ({dias[0]:%d/%m/%Y} al {dias[-1]:%d/%m/%Y}) ===")
        print("  Es una simulación: no se escribe nada, y se explica por qué cada bloque pendiente "
              "se podría o no registrar.")
        _resumen, sin_firma = registrar_rango(s, perfil, dias[0], dias[-1], token, inicio, args.cursos,
                                              True, None, None, False, dias)
        w.imprimir_resultado(w.ITEMS, sin_firma, vacio="No hay bloques tuyos en esos días.")
        return

    if args.completar_mes:
        # --mes vale igual acá: "completar octubre" y "completar septiembre"
        # son la misma orden con otro mes, no dos botones distintos.
        resumen, sin_firma = completar_mes(s, perfil, mes_pedido(args.mes, fecha), token,
                                           inicio, args.cursos, args.simular)
    elif args.fechas:
        dias = _lista_de_fechas(args.fechas)
        hoy = datetime.date.today()
        if not dias or any(d > hoy for d in dias) or len(dias) > 62:
            raise ValueError("Las fechas no sirven: hace falta al menos un día hábil que ya haya "
                             "pasado, y como máximo 62 por vez.")
        print(f"=== {len(dias)} días elegidos: {dias[0]:%d/%m/%Y} al {dias[-1]:%d/%m/%Y} ===")
        resumen, sin_firma = registrar_rango(s, perfil, dias[0], dias[-1], token, inicio, args.cursos,
                                             args.simular, seleccion, elecciones, args.solo_listar, dias)
    elif args.desde or args.solo_listar:
        hoy = datetime.date.today()
        desde = _fecha_pedida(args.desde) if args.desde else fecha
        hasta = _fecha_pedida(args.hasta) if args.hasta else (hoy if args.desde else fecha)
        if desde > hasta or hasta > hoy:
            raise ValueError("El rango no sirve: el inicio no puede ser después del fin ni "
                             "llegar más allá de hoy.")
        if (hasta - desde).days > 62:
            raise ValueError("Es demasiado tiempo: como máximo 62 días hacia atrás por vez.")
        print(f"=== Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}: "
              f"{len(_dias_habiles(desde, hasta))} días hábiles ===")
        resumen, sin_firma = registrar_rango(s, perfil, desde, hasta, token, inicio, args.cursos,
                                             args.simular, seleccion, elecciones, args.solo_listar)
    else:
        resumen, sin_firma = registrar_dia(s, perfil, fecha, token, inicio,
                                           args.cursos, args.simular, seleccion=seleccion,
                                           elecciones=elecciones)

    w.imprimir_resultado(w.ITEMS, sin_firma,
                         vacio="No tienes clases ese día." if not w.ITEMS else "")
    print(f"\nRegistro guardado en {os.path.basename(REGISTRO)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
