"""
Lo que la barra hace con el informe de personalidad que lee `webclass_personalidad.py`: el borrador de lo que el docente
va respondiendo, lo que hay que guardar en WebClass y el informe en Word de cada alumna.

El borrador vive en este PC hasta que se guarda en WebClass (así no se pierde nada si se cierra la ventana):
    {"alumnas": {"1234567": {"valores": {conducta: calificador}, "observacion": "texto", "revisada": true}}}
Solo guarda lo que difiere de WebClass: al volver a leer, lo que ya quedó guardado se borra solo.
"""

from __future__ import annotations

import os
import re


# ------------------------------------------------------------------ borrador
def _de(borrador: dict, alumna: str) -> dict:
    return (borrador.get("alumnas") or {}).get(alumna) or {}


def valores_de(alumna: dict, borrador: dict) -> dict[str, str]:
    """Lo que se ve de una alumna: lo de WebClass con lo respondido encima."""
    return {**alumna["valores"], **(_de(borrador, alumna["id"]).get("valores") or {})}


def observacion_de(alumna: dict, borrador: dict) -> str:
    propia = _de(borrador, alumna["id"]).get("observacion")
    return (alumna.get("observacion") or "") if propia is None else propia


def responder(borrador: dict, alumna: dict, conducta: str | None = None, valor: str | None = None,
              observacion: str | None = None, revisada: bool | None = None) -> dict:
    """Anota una respuesta en el borrador (lo que vuelve a quedar como en WebClass deja de ser un cambio)."""
    datos = (borrador.setdefault("alumnas", {})).setdefault(alumna["id"], {})
    if conducta is not None:
        valores = datos.setdefault("valores", {})
        if valor == alumna["valores"].get(conducta):
            valores.pop(conducta, None)
        else:
            valores[conducta] = valor
    if observacion is not None:
        if " ".join(observacion.split()) == " ".join((alumna.get("observacion") or "").split()):
            datos.pop("observacion", None)
        else:
            datos["observacion"] = observacion.strip()
    if revisada is not None:
        datos["revisada"] = revisada
    return borrador


def limpiar_borrador(encuesta: dict, borrador: dict) -> dict:
    """Saca del borrador lo que WebClass ya tiene (lo guardado) y las alumnas que ya no están en el curso."""
    limpio: dict = {"alumnas": {}}
    for alumna in encuesta["alumnas"]:
        antes = _de(borrador, alumna["id"])
        if not antes:
            continue
        responder(limpio, alumna, revisada=bool(antes.get("revisada")))
        for conducta, valor in (antes.get("valores") or {}).items():
            if conducta in alumna["valores"]:
                responder(limpio, alumna, conducta, valor)
        if antes.get("observacion") is not None:
            responder(limpio, alumna, observacion=antes["observacion"])
    return limpio


def tiene_cambios(alumna: dict, borrador: dict) -> bool:
    datos = _de(borrador, alumna["id"])
    return bool(datos.get("valores")) or bool((datos.get("observacion") or "").strip())


def revisada(alumna: dict, borrador: dict) -> bool:
    return bool(_de(borrador, alumna["id"]).get("revisada"))


def cambios(encuesta: dict, borrador: dict) -> dict:
    """Lo que `personalidad --datos` guarda en WebClass: solo las alumnas con algo distinto."""
    alumnas = []
    for alumna in encuesta["alumnas"]:
        if not tiene_cambios(alumna, borrador):
            continue
        datos = _de(borrador, alumna["id"])
        alumnas.append({"id": alumna["id"], "nombre": alumna["nombre"], "valores": dict(datos.get("valores") or {}),
                        "observacion": (datos.get("observacion") or "").strip() or None})
    return {"curso": encuesta["curso"], "curso_id": encuesta["curso_id"], "periodo": encuesta["periodo"],
            "alumnas": alumnas}


def avance(encuesta: dict, borrador: dict) -> str:
    """«12 de 42 revisadas · 5 con cambios sin guardar en WebClass»."""
    total = len(encuesta["alumnas"])
    vistas = sum(revisada(a, borrador) for a in encuesta["alumnas"])
    pendientes = sum(tiene_cambios(a, borrador) for a in encuesta["alumnas"])
    texto = f"{vistas} de {total} revisadas"
    if pendientes:
        texto += f" · {pendientes} con cambios sin guardar en WebClass"
    return texto


# ------------------------------------------------------------------ informe
def nombre_de_archivo(alumna: dict) -> str:
    limpio = re.sub(r'[<>:"/\\|?*]+', "", alumna["nombre"]).strip() or alumna["id"]
    return f"{int(alumna.get('numero') or 0):02d} {limpio}.docx"


def carpeta_de_informes(documentos: str, encuesta: dict) -> str:
    anio = (encuesta.get("leido") or "")[6:10]
    return os.path.join(documentos, "Informes de personalidad",
                        f"{encuesta['curso']} {encuesta.get('periodo_nombre') or encuesta['periodo']} {anio}".strip())


def crear_informe(ruta: str, encuesta: dict, alumna: dict, valores: dict[str, str], observacion: str,
                  colegio: str = "", docente: str = "", jefatura: bool = False) -> str:
    """El informe de una alumna en Word: datos, una tabla por área con la calificación marcada, observación y firma."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    calificadores = encuesta["calificadores"]
    doc = Document()
    for seccion in doc.sections:
        seccion.top_margin = seccion.bottom_margin = Cm(1.8)
        seccion.left_margin = seccion.right_margin = Cm(2)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10)

    def parrafo(texto: str, negrita: bool = False, tamano: float | None = None, centrado: bool = False,
                despues: float = 4):
        p = doc.add_paragraph()
        corrida = p.add_run(texto)
        corrida.bold = negrita
        if tamano:
            corrida.font.size = Pt(tamano)
        if centrado:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(despues)
        return p

    if colegio:
        parrafo(colegio, negrita=True, tamano=11, centrado=True, despues=0)
    parrafo("Informe de personalidad", negrita=True, tamano=15, centrado=True, despues=10)
    anio = (encuesta.get("leido") or "")[6:10]
    datos = [("Alumna", alumna["nombre"]), ("N° de lista", str(alumna.get("numero") or "")),
             ("Curso", encuesta["curso"]), ("Periodo", f"{encuesta.get('periodo_nombre') or ''} {anio}".strip())]
    if docente:
        datos.append(("Profesor(a) jefe" if jefatura else "Profesor(a)", docente))
    tabla = doc.add_table(rows=0, cols=2)
    tabla.style = "Table Grid"
    for etiqueta, valor in datos:
        celdas = tabla.add_row().cells
        celdas[0].text, celdas[1].text = etiqueta, valor
        celdas[0].paragraphs[0].runs[0].bold = True
        celdas[0].width, celdas[1].width = Cm(4), Cm(13)
    parrafo("", despues=2)

    for area in encuesta["areas"]:
        tabla = doc.add_table(rows=1, cols=1 + len(calificadores))
        tabla.style = "Table Grid"
        cabecera = tabla.rows[0].cells
        cabecera[0].text = area["nombre"]
        for i, c in enumerate(calificadores, 1):
            cabecera[i].text = c["sigla"]
            cabecera[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        for celda in cabecera:
            celda.paragraphs[0].runs[0].bold = True
        for conducta in area["conductas"]:
            fila = tabla.add_row().cells
            fila[0].text = f"{conducta['numero']}. {conducta['nombre']}"
            for i, c in enumerate(calificadores, 1):
                if valores.get(conducta["id"]) == c["id"]:
                    fila[i].text = "X"
                    fila[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        for fila in tabla.rows:
            fila.cells[0].width = Cm(11.5)
            for celda in fila.cells[1:]:
                celda.width = Cm(1.4)
        parrafo("", despues=2)

    parrafo("Observaciones", negrita=True, despues=2)
    parrafo(observacion.strip() or "Sin observaciones.", despues=8)
    parrafo("  ·  ".join(f"{c['sigla']}: {c['nombre']}" for c in calificadores), tamano=8.5, despues=36)
    parrafo("_" * 34, centrado=True, despues=0)
    parrafo(docente or "Firma", centrado=True, despues=0)
    if docente:
        parrafo("Profesor(a) jefe" if jefatura else "Profesor(a)", tamano=9, centrado=True)
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    doc.save(ruta)
    return ruta
