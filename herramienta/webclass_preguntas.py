"""
Carga de preguntas de selección múltiple al banco de preguntas de Webclass.

Permite subir una prueba completa desde Python, sin pasar por el navegador.

Uso típico:

    import webclass_tareas as w
    from webclass_preguntas import crear_pregunta, imagen_embebida

    session = w.crear_session()
    w.login(session, w.RUT_USUARIO, w.obtener_password())

    crear_pregunta(
        session,
        nombre="U3 P01 - Definición de energía",
        enunciado="<p>¿Cómo se puede definir el concepto de energía?</p>",
        alternativas=[
            "<p>Como el movimiento de electrones en un cable.</p>",
            "<p>Como la capacidad de producir cambios en otros objetos.</p>",
            "<p>Como lo que tienen las personas para realizar actividades.</p>",
            "<p>Como la capacidad de brillar en la oscuridad.</p>",
        ],
        correcta=1,          # índice 0-7; la correcta queda en 100%
        nivel=NIVELES["Sexto Básico"],
        sector=SECTORES["Ciencias Naturales"],
    )

Notas importantes:

* El paso de "Clasificar pregunta" (asignar eje curricular) es OPCIONAL. La
  pregunta queda visible y usable en el banco sin él.
* Cada pregunta queda suelta en el banco. Si varias comparten un enunciado
  común (una imagen, un experimento, una tabla), hay que repetir ese contexto
  dentro de cada una o quedan incomprensibles.
* El enunciado se guarda en un campo TEXT de 65.535 bytes. Con imágenes
  embebidas en base64 es fácil pasarse: el HTML se corta a la mitad y la
  imagen aparece rota, sin ningún error visible. Usar imagen_embebida(), que
  comprime hasta que quepa.

Endpoints: controlador/controladorPregunta.php
    caso=1 & accion=1  ->  crear   (devuelve el id de la pregunta)
    caso=1 & accion=0  ->  editar  (requiere id_pregunta)
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import requests

import webclass_tareas as w

# Tamaño del campo TEXT del enunciado. Dejamos margen para el HTML que rodea
# a la imagen (párrafos, tabla de datos, texto de la pregunta).
LIMITE_ENUNCIADO = 65535
MARGEN_SEGURO = 55000

NIVELES = {
    "Primero Básico": "21", "Segundo Básico": "22", "Tercero Básico": "23",
    "Cuarto Básico": "24", "Quinto Básico": "25", "Sexto Básico": "26",
    "Séptimo Básico": "27", "Octavo Básico": "28", "Primero Medio": "29",
    "Segundo Medio": "30", "Tercero Medio": "31", "Cuarto Medio": "32",
}

SECTORES = {
    "Ciencias Naturales": "218", "Matemáticas": "219",
    "Lenguaje y Comunicación": "220", "Historia, Geografía y Cs. Sociales": "221",
    "Inglés": "222", "Educación Física": "223", "Artes Visuales": "224",
    "Música": "225", "Tecnología": "226", "Orientación": "227",
}


def imagen_embebida(ruta: str | Path, alt: str, limite: int = MARGEN_SEGURO) -> str:
    """Devuelve un <img> con la imagen embebida en base64, comprimida si hace falta.

    Los PNG de captura suelen pesar demasiado para el campo del enunciado.
    Convertir a JPEG basta casi siempre; si aún no cabe se baja la calidad y,
    como último recurso, el ancho. Requiere Pillow.
    """
    ruta = Path(ruta)
    crudo = ruta.read_bytes()
    b64 = base64.b64encode(crudo).decode()

    if len(b64) < limite:
        tipo = "png" if ruta.suffix.lower() == ".png" else "jpeg"
        return f'<p><img src="data:image/{tipo};base64,{b64}" alt="{alt}" /></p>'

    from PIL import Image  # import diferido: solo se necesita al comprimir

    imagen = Image.open(ruta).convert("RGB")
    ancho, calidad = imagen.width, 82
    while True:
        copia = imagen.copy()
        if copia.width > ancho:
            alto = round(copia.height * ancho / copia.width)
            copia = copia.resize((ancho, alto), Image.LANCZOS)

        buffer = io.BytesIO()
        copia.save(buffer, "JPEG", quality=calidad, optimize=True)
        b64 = base64.b64encode(buffer.getvalue()).decode()

        if len(b64) < limite or ancho <= 400:
            break
        ancho -= 80
        calidad = max(60, calidad - 4)

    if len(b64) >= limite:
        raise RuntimeError(
            f"No se pudo comprimir {ruta.name} bajo {limite} caracteres. "
            "Recórtala o súbela a mano."
        )
    return f'<p><img src="data:image/jpeg;base64,{b64}" alt="{alt}" /></p>'


def _payload(
    *, nombre, enunciado, alternativas, correcta, nivel, sector,
    retroalimentacion_general, correccion,
) -> dict:
    if not 0 <= correcta < len(alternativas):
        raise ValueError(f"El índice de la correcta ({correcta}) está fuera de rango.")
    if len(enunciado.encode("utf-8")) >= LIMITE_ENUNCIADO:
        raise ValueError(
            f"El enunciado de '{nombre}' supera los {LIMITE_ENUNCIADO} bytes del "
            "campo. Webclass lo cortaría en silencio; comprime las imágenes con "
            "imagen_embebida()."
        )

    datos = {
        "nivel": nivel, "idSector": sector,
        "nombreTipoPregunta": "multichoice",
        "nombrePregunta": nombre,
        "textoPregunta": enunciado,
        "retroalimentacionGeneral": retroalimentacion_general,
        "correccion": correccion,
        "variableIdRecurso": "-1",   # -1 = sin recurso asociado
        "ambitos": "",
        "crc": "", "crpc": "", "cri": "",
    }
    # El formulario siempre manda 8 alternativas; las no usadas van vacías.
    for i in range(8):
        datos[f"respuesta{i + 1}"] = alternativas[i] if i < len(alternativas) else ""
        datos[f"calificacionRespuesta{i + 1}"] = "1" if i == correcta else "0"
        datos[f"retroalimentacionRespuesta{i + 1}"] = ""
    return datos


def crear_pregunta(
    session: requests.Session,
    *,
    nombre: str,
    enunciado: str,
    alternativas: list[str],
    correcta: int,
    nivel: str,
    sector: str,
    retroalimentacion_general: str = "",
    correccion: str = "",
) -> str:
    """Crea una pregunta de selección múltiple y devuelve su id."""
    datos = _payload(
        nombre=nombre, enunciado=enunciado, alternativas=alternativas,
        correcta=correcta, nivel=nivel, sector=sector,
        retroalimentacion_general=retroalimentacion_general, correccion=correccion,
    )
    datos.update({"caso": 1, "accion": 1})

    resp = session.post(
        f"{w.BASE}/home/preguntas/controlador/controladorPregunta.php",
        data=datos, headers=w.HEADERS, timeout=180,
    )
    resp.raise_for_status()

    idpregunta = resp.text.strip()
    if not idpregunta.isdigit():
        raise RuntimeError(
            f"Webclass no devolvió un id al crear '{nombre}'. "
            f"Respuesta: {idpregunta[:200]!r}"
        )
    return idpregunta


def editar_pregunta(
    session: requests.Session,
    *,
    id_pregunta: str,
    nombre: str,
    enunciado: str,
    alternativas: list[str],
    correcta: int,
    nivel: str,
    sector: str,
    idcolegio: str,
    idprofesor: str,
    retroalimentacion_general: str = "",
    correccion: str = "",
) -> None:
    """Reescribe una pregunta existente, conservando su id.

    Sirve para corregir sin dejar duplicados en el banco. Hay que reenviar
    todos los campos, no solo los que cambian.
    """
    datos = _payload(
        nombre=nombre, enunciado=enunciado, alternativas=alternativas,
        correcta=correcta, nivel=nivel, sector=sector,
        retroalimentacion_general=retroalimentacion_general, correccion=correccion,
    )
    datos.update({
        "caso": 1, "accion": 0,
        "id_pregunta": id_pregunta,
        "ColegioDelapregunta": idcolegio,
        "ProfeDelapregunta": idprofesor,
    })

    resp = session.post(
        f"{w.BASE}/home/preguntas/controlador/controladorPregunta.php",
        data=datos, headers=w.HEADERS, timeout=180,
    )
    resp.raise_for_status()
