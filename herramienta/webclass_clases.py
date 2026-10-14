"""
Creación de clases (planificaciones) dentro de una unidad de Webclass.

Complementa a webclass_tareas.py, que asigna las clases ya existentes.
Aquí se crean desde cero, con su objetivo, secuencia didáctica y recursos.

Uso típico:

    import webclass_tareas as w
    from webclass_clases import crear_clase

    session = w.crear_session()
    w.login(session, w.RUT_USUARIO, w.obtener_password())

    crear_clase(
        session,
        id_unidad=7516413,
        nombre="Circuitos eléctricos",
        fecha="31/08/2026",
        motivacion="<p>Objetivo de la clase...</p>",
        inicio="<p>Actividades de inicio...</p>",
        desarrollo="<p>Actividades de desarrollo...</p>",
        cierre="<p>Actividades de cierre...</p>",
        recursos="<p>Proyector, cuaderno y lápiz.</p>",
        adecuaciones="<p>Nota para el docente...</p>",
        evaluacion="<p>Formativa (ticket de salida).</p>",
    )

Los campos de contenido aceptan HTML (en el formulario son editores CKEditor).

Endpoint: controladores/controladorClase.php  ->  caso=4 & accion=1
La respuesta del servidor es el id de la clase recién creada.
"""

from __future__ import annotations

import html
import re

import requests

import webclass_tareas as w

# tipo=1 es "Universal" (el que viene marcado por defecto en el formulario).
# Los otros dos son 2 = Adaptada y 3 = Remedial.
TIPO_UNIVERSAL = 1
TIPO_ADAPTADA = 2
TIPO_REMEDIAL = 3


def datos_unidad(session: requests.Session, id_unidad: int) -> dict:
    """Lee del formulario de nueva clase los ids que hay que reenviar.

    El `sector` (asignatura) es propio de cada unidad, así que no se puede
    hardcodear: se lee del formulario de la unidad en la que vamos a crear.
    """
    resp = session.get(
        f"{w.BASE}/home/planificacion/agregar_clase.php",
        params={"idUnidad": id_unidad},
        headers=w.HEADERS,
        timeout=90,
    )

    def campo(nombre: str) -> str | None:
        m = re.search(rf'id="{nombre}"[^>]*value="([^"]*)"', resp.text)
        return m.group(1) if m else None

    datos = {"user": campo("user"), "sector": campo("sector")}
    if not datos["user"] or not datos["sector"]:
        raise RuntimeError(
            f"No se pudieron leer los datos de la unidad {id_unidad}. "
            "Puede que la sesión haya expirado o que la unidad no exista."
        )
    return datos


def crear_clase(
    session: requests.Session,
    *,
    id_unidad: int,
    nombre: str,
    fecha: str,
    fecha_termino: str | None = None,
    motivacion: str = "",
    inicio: str = "",
    desarrollo: str = "",
    cierre: str = "",
    recursos: str = "",
    adecuaciones: str = "",
    evaluacion: str = "",
    link_inicial: str = "",
    hora: str = "08:00",
    horas: str = "2",
    tipo: int = TIPO_UNIVERSAL,
) -> str:
    """Crea una clase y devuelve su id.

    fecha / fecha_termino en formato DD/MM/AAAA. Si no se da fecha_termino,
    la clase empieza y termina el mismo día.

    link_inicial, si se entrega, se antepone como primera línea del bloque
    Inicio (sirve para dejar a mano el material de la clase).
    """
    datos = datos_unidad(session, id_unidad)

    if link_inicial:
        inicio = f'<p><a href="{link_inicial}">{link_inicial}</a></p>{inicio}'

    payload = {
        "user": datos["user"],
        "idUnidad": id_unidad,
        "clase": 0,  # 0 = clase nueva
        "sector": datos["sector"],
        "nombre": nombre,
        "fechaini": fecha,
        "fechafin": fecha_termino or fecha,
        "hora_inicio": hora,
        "horas": horas,
        "tipo": tipo,
        "motivacion": motivacion,
        "inicio": inicio,
        "desarrollo": desarrollo,
        "cierre": cierre,
        "recursos": recursos,
        "adecuaciones": adecuaciones,
        "evaluacion": evaluacion,
        "visible": 1,
        "caso": 4,
        "accion": 1,
    }

    resp = session.post(
        f"{w.BASE}/home/planificacion/controladores/controladorClase.php",
        data=payload,
        headers=w.HEADERS,
        timeout=180,
    )
    resp.raise_for_status()

    idclase = resp.text.strip()
    if not idclase.isdigit():
        raise RuntimeError(
            f"Webclass no devolvió un id de clase al crear '{nombre}'. "
            f"Respuesta: {idclase[:200]!r}"
        )
    return idclase


def modificar_fechas(
    session: requests.Session,
    *,
    idclase: str,
    id_unidad: int,
    fecha_inicio: str,
    fecha_termino: str,
    fecha_inicio_actual: str | None = None,
) -> None:
    """Cambia las fechas propias de una clase ya creada.

    Webclass valida que la fecha de inicio no sea posterior a la de término,
    así que primero se mueve el término y después el inicio; hacerlo al revés
    hace que rechace el cambio cuando se adelanta una clase hacia el futuro.

    fecha_inicio_actual es la fecha que la clase tiene hoy; si no se entrega
    se usa la nueva, lo que sirve cuando solo se corre el término.
    """
    endpoint = f"{w.BASE}/home/planificacion/controladores/controladorClase.php"
    base = {"caso": 15, "idClase": idclase, "cod_unidad": id_unidad}

    # accion=2 mueve el término; accion=1 mueve el inicio.
    session.post(
        endpoint,
        data={**base, "accion": 2,
              "fechaini": fecha_inicio_actual or fecha_inicio,
              "fechafin": fecha_termino},
        headers=w.HEADERS, timeout=90,
    )
    session.post(
        endpoint,
        data={**base, "accion": 1,
              "fechaini": fecha_inicio, "fechafin": fecha_termino},
        headers=w.HEADERS, timeout=90,
    )


# ---------------------------------------------------------------------------
# Editar una clase que ya existe
# ---------------------------------------------------------------------------
#
# Webclass guarda cada bloque (inicio, desarrollo, cierre...) como un campo
# completo: al editar, lo que se envía REEMPLAZA todo el campo. Por eso, antes
# de editar hay que rescatar las imágenes y videos que el docente pegó a mano
# —no se pueden volver a insertar desde el script— y escribir el texto nuevo
# alrededor de ellos.

CAMPOS = ("motivacion", "inicio", "desarrollo", "cierre",
          "recursos", "adecuaciones", "evaluacion")

# Etiquetas que el docente pega en el editor y que hay que conservar.
INCRUSTADOS = re.compile(
    r"<(?:img|object|iframe|embed)[^>]*>(?:.*?</(?:object|iframe)>)?", re.S)


def leer_clase(session: requests.Session, *, id_unidad: int, idclase: str) -> dict:
    """Contenido actual de una clase, campo por campo, tal como está guardado."""
    resp = session.get(
        f"{w.BASE}/home/planificacion/editar_clase.php",
        params={"idUnidad": id_unidad, "c": idclase},
        headers=w.HEADERS, timeout=120,
    )
    resp.raise_for_status()
    campos = {m.group(1).replace("id_", ""): html.unescape(m.group(2))
              for m in re.finditer(r'<textarea[^>]*id="(\w+)"[^>]*>(.*?)</textarea>',
                                   resp.text, re.S)}
    nombre = re.search(r'id="nombre"[^>]*value="([^"]*)"', resp.text)
    campos["nombre"] = nombre.group(1) if nombre else ""
    return campos


def incrustados(session: requests.Session, *, id_unidad: int, idclase: str) -> dict:
    """Imágenes y videos pegados en cada campo, en su orden original."""
    actual = leer_clase(session, id_unidad=id_unidad, idclase=idclase)
    return {k: INCRUSTADOS.findall(v) for k, v in actual.items() if k != "nombre"}


def _envolver(etiqueta: str) -> str:
    return f'<p dir="ltr">{etiqueta}</p>'


def componer(texto, etiquetas: list) -> str:
    """Arma un campo escribiendo el texto ALREDEDOR de lo ya incrustado.

    - texto como str: las etiquetas quedan al final del campo.
    - texto como lista de partes: va una etiqueta después de cada parte, que es
      lo que permite rodear cada imagen con el párrafo que le corresponde. Las
      que sobren se agregan al final, para no perder ninguna.
    """
    if isinstance(texto, str):
        return texto + "".join(_envolver(e) for e in etiquetas)
    partes, pendientes, salida = list(texto), list(etiquetas), []
    for i, parte in enumerate(partes):
        salida.append(parte)
        if pendientes and i < len(partes) - 1:
            salida.append(_envolver(pendientes.pop(0)))
    salida.extend(_envolver(e) for e in pendientes)
    return "".join(salida)


def editar_clase(
    session: requests.Session,
    *,
    id_unidad: int,
    idclase: str,
    nombre: str = None,
    fecha: str = None,
    fecha_termino: str = None,
    conservar_incrustados: bool = True,
    hora: str = "08:00",
    horas: str = "2",
    tipo: int = TIPO_UNIVERSAL,
    **campos,
) -> dict:
    """Reescribe una clase conservando lo que el docente pegó a mano.

    Cada campo (inicio, desarrollo, cierre, recursos, adecuaciones, evaluacion,
    motivacion) acepta un str o una lista de partes; con lista, las imágenes de
    ese campo se intercalan entre ellas. Los campos que no se pasen quedan tal
    como estaban.

    Devuelve un resumen con el conteo de incrustados antes y después, para
    comprobar de inmediato que no se perdió nada.
    """
    actual = leer_clase(session, id_unidad=id_unidad, idclase=idclase)
    previos = {k: INCRUSTADOS.findall(v) for k, v in actual.items() if k != "nombre"}

    payload = {}
    for campo in CAMPOS:
        if campos.get(campo) is not None:
            etiquetas = previos.get(campo, []) if conservar_incrustados else []
            payload[campo] = componer(campos[campo], etiquetas)
        else:
            payload[campo] = actual.get(campo, "")

    fechas = [c for c in w.listar_clases(session, id_unidad) if c["idclase"] == str(idclase)]
    fecha_ini = fecha or (fechas[0]["fechaini"] if fechas else "")
    fecha_fin = fecha_termino or fecha or (fechas[0]["fechafin"] if fechas else fecha_ini)

    payload.update({
        "visible": 1, "caso": 4, "accion": 2,
        "user": w.PERFILES[w.PERFIL_POR_DEFECTO]["iduser"],
        "idUnidad": id_unidad, "idClase": idclase,
        "nombre": nombre if nombre is not None else actual.get("nombre", ""),
        "fechaini": fecha_ini, "fechafin": fecha_fin,
        "hora_inicio": hora, "horas": horas, "tipo": tipo,
    })

    resp = session.post(
        f"{w.BASE}/home/planificacion/controladores/controladorClase.php",
        data=payload, headers=w.HEADERS, timeout=300,
    )
    resp.raise_for_status()

    if fecha:
        modificar_fechas(session, idclase=idclase, id_unidad=id_unidad,
                         fecha_inicio=fecha, fecha_termino=fecha_termino or fecha)

    despues = incrustados(session, id_unidad=id_unidad, idclase=idclase)
    return {
        "idclase": idclase,
        "incrustados_antes": sum(len(v) for v in previos.values()),
        "incrustados_despues": sum(len(v) for v in despues.values()),
    }


# ---------------------------------------------------------------------------
# Paso 2 (OA y habilidades) y Paso 3 (DUA)
# ---------------------------------------------------------------------------

# Habilidades científicas por nivel, leídas del catálogo del colegio. 5° y 6°
# usan el formato antiguo "Hab_a"; 7° y 8°, las letras del currículum nuevo.
# En 7° la unidad del colegio solo tiene las tres primeras.
HABILIDADES = {
    5: {"a": 1021, "b": 1022, "c": 1023, "d": 1024,
        "e": 1025, "f": 1026, "g": 1027, "h": 1028},
    6: {"a": 1140, "b": 1141, "c": 1142, "d": 1143, "e": 1144, "f": 1145},
    7: {"a": 10356, "b": 10357, "c": 10358},
    8: {"a": 10370, "b": 10371, "c": 10372, "d": 10373, "e": 10374, "f": 10375,
        "g": 10376, "h": 10377, "i": 10378, "j": 10379, "k": 10380,
        "l": 10381, "m": 10382},
}

# Casillas DUA que se marcan siempre (son generales, no dependen del nivel):
# Representación 3, 4, 8 y 9 · Expresión 13, 15 y 16 · Compromiso 23, 26 y 27.
DUA_HABITUAL = [3, 4, 8, 9, 13, 15, 23, 26, 27]
DUA_CON_TIC = [3, 4, 8, 9, 13, 15, 16, 23, 26, 27]


def catalogo(session: requests.Session, *, id_unidad: int, idclase: str,
             tipo: str = "oft") -> list:
    """(id, texto) de los OA (tipo='oft') o de las habilidades (tipo='hab').

    Sirve para no adivinar ids: cada unidad numera sus OA de forma distinta.
    """
    accion = 1 if tipo == "oft" else 2
    resp = session.post(
        f"{w.BASE}/home/planificacion/controladores/controladorClase.php",
        data={"idClase": idclase, "tipoAtributo": tipo, "caso": 2,
              "accion": accion, "idUnidad": id_unidad},
        headers=w.HEADERS, timeout=120,
    )
    salida = []
    for m in re.finditer(r'id="filaAtributo_(\d+)"(.*?)(?=id="filaAtributo_|\Z)',
                         resp.text, re.S):
        texto = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", m.group(2))).split())
        salida.append((m.group(1), texto))
    return salida


def marcar_atributos(session: requests.Session, *, idclase: str,
                     ids: list, tipo: str = "oft") -> int:
    """Marca las casillas del Paso 2: tipo='oft' para OA, 'hab' para habilidades."""
    resp = session.post(
        f"{w.BASE}/home/planificacion/controladores/controladorClase.php",
        data=[(f"{tipo}[]", str(v)) for v in ids] + [
            ("idClase", idclase), ("tipoAtributo", tipo),
            ("caso", "1"), ("accion", "1")],
        headers=w.HEADERS, timeout=180,
    )
    resp.raise_for_status()
    return resp.status_code


def marcar_dua(session: requests.Session, *, idclase: str,
               casillas: list = None) -> int:
    """Marca las casillas DUA del Paso 3.

    El valor viaja con comillas dobles dentro del propio parámetro, tal como lo
    manda la página: selecciones="[3,4,8]".
    """
    casillas = DUA_HABITUAL if casillas is None else casillas
    resp = session.post(
        f"{w.BASE}/home/planificacion/controladores/controladorPlanificacionInclusion.php",
        data={"idClase": idclase, "seleccion": "null", "caso": 5,
              "selecciones": '"[' + ",".join(str(c) for c in casillas) + ']"'},
        headers=w.HEADERS, timeout=180,
    )
    resp.raise_for_status()
    return resp.status_code


def aplicar_plan(
    session: requests.Session,
    *,
    id_unidad: int,
    idclase: str,
    oa: list = (),
    habilidades: list = (),
    dua: list = None,
    **kwargs,
) -> dict:
    """Edita la clase y deja marcados OA, habilidades y DUA de una sola vez.

    Es el ciclo completo que se repite en cada planificación: reescribir el
    contenido sin perder imágenes y volver a marcar las casillas, porque la
    edición puede limpiarlas.
    """
    resumen = editar_clase(session, id_unidad=id_unidad, idclase=idclase, **kwargs)
    if oa:
        resumen["oa"] = marcar_atributos(session, idclase=idclase,
                                         ids=list(oa), tipo="oft")
    if habilidades:
        resumen["hab"] = marcar_atributos(session, idclase=idclase,
                                          ids=list(habilidades), tipo="hab")
    resumen["dua"] = marcar_dua(session, idclase=idclase, casillas=dua)
    return resumen
