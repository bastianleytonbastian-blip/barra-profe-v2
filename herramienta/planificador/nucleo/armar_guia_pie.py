# -*- coding: utf-8 -*-
"""Arma la guía PIE en HTML a partir del contenido (dict) usando el motor del kit (kit_pie/generar.py)."""
import html as _h
import json
import os
import re
import sys
import tempfile
import threading

KIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kit_pie")
if KIT not in sys.path:
    sys.path.insert(0, KIT)
import generar as g  # noqa: E402

_BLOQUEO = threading.Lock()  # el motor del kit guarda estado global (carpeta de imágenes y caché)

INSTRUCCION_POR_DEFECTO = {
    "ESCRIBIR": "ESCRIBIR LAS FRASES.",
    "COMPLETAR": "COMPLETAR LAS PALABRAS.",
    "MARCAR": "MARCAR LA RESPUESTA CORRECTA.",
    "RECONOCER": "RECONOCER LAS IMÁGENES.",
    "UNIR": "UNIR CADA IMAGEN CON SU NOMBRE.",
    "COPIAR": "COPIAR LOS CONCEPTOS.",
    "DIBUJAR": "DIBUJAR LO QUE APRENDISTE.",
}


def may(texto):
    return " ".join(str(texto or "").split()).upper()


def instruccion_valida(texto, verbo):
    """La instrucción debe partir con el verbo de la actividad (lleva su pictograma y va en rojo)."""
    t = may(texto)
    if not t or g.norm(t.split(" ")[0]) != g.norm(verbo):
        return INSTRUCCION_POR_DEFECTO[verbo]
    return t


def frases_validas(lista):
    return [may(f) for f in (lista or []) if str(f).strip()]


def objetivo_grid(frase):
    """Objetivo en cuadrícula: primer verbo en rojo, artículos en verde con su pictograma (igual que la plantilla)."""
    flat = []
    for wi, w in enumerate(frase.split(" ")):
        art = g.norm(w) in g.ARTS
        for ch in w:
            flat.append(("letter", ch, art, wi == 0))
        flat.append(("space", "", False, False))
    flat.pop()
    lines, cur = [], []
    for c in flat:
        cur.append(c)
        if len(cur) >= g.MAX_CELLS and c[0] == "space":
            lines.append(cur[:-1])
            cur = []
    if cur:
        lines.append(cur)
    out = ['<div class="grid-block">']
    for ln in lines:
        d = [{"type": t, "ch": ch, "is_art": a} for t, ch, a, v in ln]
        top = "".join(
            '<td class="sp"></td>' if t == "space" else
            f'<td class="c" style="color:{g.ROJO if v else (g.VERDE if a else "#000")}">{_h.escape(ch)}</td>'
            for t, ch, a, v in ln
        )
        bot = "".join('<td class="sp"></td>' if t == "space" else '<td class="c"></td>' for t, ch, a, v in ln)
        out.append(f'<table class="grid">{g._picto_row(d)}<tr>{top}</tr><tr>{bot}</tr></table>')
    return "".join(out) + "</div>"


def recuadro(texto):
    return f'<div class="grid-block"><div class="recuadro">{texto}</div></div>'


def recuadro_dibujo(instr):
    return (g.instruccion(instruccion_valida(instr, "DIBUJAR")) +
            '<div class="grid-block"><div class="recuadro" style="height:15cm;background:#fff"></div></div>')


def _bloques_seccion(s, archivos, avisos, usadas):
    """Imagen + ESCRIBIR + MARCAR + COMPLETAR de una sección, aplicando las reglas PIE.
    Devuelve bloques neutros (tuplas) que luego se dibujan en HTML (bloque_html) o en Word (exportar_word)."""
    titulo = may(s.get("titulo")) or "SECCIÓN"
    bloques, tiene_imagen = [], False

    img = s.get("imagen")
    if img:
        if img in archivos:
            if img in usadas:
                avisos.append(f"La imagen {img} se usó en más de una sección ({titulo}).")
            usadas.add(img)
            bloques.append(("ilus", img, may(s.get("pie_imagen"))))
            tiene_imagen = True
        else:
            avisos.append(f"La sección «{titulo}» pedía la imagen {img}, que no está seleccionada; se omitió.")

    foto = s.get("foto_web") or {}
    if foto.get("busqueda"):
        bloques.append(("web", foto["busqueda"], may(foto.get("pie")) or titulo))
        tiene_imagen = True

    esc = s.get("escribir") or {}
    frases = frases_validas(esc.get("frases"))
    if frases:
        bloques.append(("escribir", instruccion_valida(esc.get("instruccion"), "ESCRIBIR"), frases))

    mar = s.get("marcar") or {}
    opciones = frases_validas(mar.get("opciones"))
    if len(opciones) >= 2 and mar.get("pregunta"):
        if not frases and not tiene_imagen:
            avisos.append(f"Se quitó un MARCAR en «{titulo}»: no tenía antes un ESCRIBIR ni una imagen con la respuesta.")
        else:
            if not tiene_imagen:
                # MARCAR siempre lleva imagen de referencia
                bloques.insert(0, ("web", titulo.lower(), titulo))
                avisos.append(f"Se agregó una foto web de referencia para el MARCAR de «{titulo}» (revísala).")
            idx = mar.get("correcta")
            if isinstance(idx, int) and 0 <= idx < len(opciones) and frases:
                if g.norm(opciones[idx]) not in g.norm(" ".join(frases)):
                    avisos.append(f"En «{titulo}», la respuesta de MARCAR («{opciones[idx]}») no aparece literal en el ESCRIBIR.")
            bloques.append(("marcar", instruccion_valida(mar.get("instruccion"), "MARCAR"),
                            may(mar.get("pregunta")), opciones[:5]))

    comp = s.get("completar") or {}
    frases_comp = frases_validas(comp.get("frases"))
    if frases_comp:
        bloques.append(("completar", instruccion_valida(comp.get("instruccion"), "COMPLETAR"), frases_comp))

    if s.get("pregunta_conversar"):
        bloques.append(("conversar", may(s["pregunta_conversar"])))

    return titulo, bloques


def bloque_html(b, archivos):
    """Dibuja un bloque neutro con el motor del kit. archivos: {id_imagen: nombre en kit_pie/content}."""
    tipo = b[0]
    if tipo == "ilus":
        return g.ilustracion(archivos[b[1]], b[2])
    if tipo == "web":
        return g.ilustracion_web(b[1], b[2])
    if tipo in ("escribir", "copiar"):
        return g.escribir_grids(b[1], b[2])
    if tipo == "completar":
        return g.completar_grids(b[1], b[2])
    if tipo == "marcar":
        return g.marcar(b[1], b[2], b[3])
    if tipo == "conversar":
        return recuadro("PREGUNTA PARA CONVERSAR EN CLASE:<br>" + _h.escape(b[1]))
    if tipo == "reconocer":
        return g.reconocer(b[1], [(archivos[i], c) for i, c in b[2]])
    if tipo == "unir":
        return g.unir(b[1], [(archivos[i], c) for i, c in b[2]])
    if tipo == "dibujo":
        return recuadro_dibujo(b[1])
    return ""


def estructura_guia(spec, ids_imagenes, avisos, asignatura=""):
    """Contenido de la guía en bloques neutros, con todas las reglas PIE aplicadas.
    Devuelve (objetivo, [(numero, titulo, bloques), ...])."""
    g.configurar_pictos(asignatura, spec.get("picto_extra"))
    disponibles = {i: i for i in ids_imagenes}

    secciones, num, usadas = [], 1, set()
    for s in spec.get("secciones") or []:
        if not isinstance(s, dict):
            avisos.append("Se omitió una sección que la IA entregó con formato inválido.")
            continue
        titulo, bloques = _bloques_seccion(s, disponibles, avisos, usadas)
        if bloques:
            secciones.append((num, titulo, bloques))
            num += 1

    # RECONOCER siempre antes de UNIR, con las mismas imágenes
    ru = spec.get("reconocer_unir") or {}
    pares = [(p["imagen"], may(p.get("concepto")))
             for p in (ru.get("pares") or []) if p.get("imagen") in disponibles and p.get("concepto")][:5]
    if len(pares) >= 2:
        secciones.append((num, may(ru.get("titulo")) or "RECONOZCO Y UNO", [
            ("reconocer", instruccion_valida(ru.get("instruccion_reconocer"), "RECONOCER"), pares),
            ("unir", instruccion_valida(ru.get("instruccion_unir"), "UNIR"), pares),
        ]))
        num += 1
    elif ru:
        avisos.append("RECONOCER/UNIR se omitió: necesita al menos 2 imágenes seleccionadas con su concepto.")

    if spec.get("para_pensar"):
        titulo, bloques = _bloques_seccion(spec["para_pensar"], disponibles, avisos, usadas)
        if bloques:
            secciones.append((num, titulo, bloques))
            num += 1

    conceptos = frases_validas(spec.get("conceptos_clave"))
    if conceptos:
        secciones.append(("★", "CONCEPTOS CLAVE", [("copiar", INSTRUCCION_POR_DEFECTO["COPIAR"], conceptos)]))

    cierre = spec.get("cierre") or {}
    if cierre:
        titulo = may(cierre.get("titulo")) or "PARA TERMINAR"
        frases_cierre = frases_validas(cierre.get("frases"))
        if cierre.get("tipo") == "escribir" and frases_cierre:
            bloque = ("escribir", instruccion_valida(cierre.get("instruccion"), "ESCRIBIR"), frases_cierre)
        else:
            bloque = ("dibujo", cierre.get("instruccion"))
        secciones.append(("✎", titulo, [bloque]))

    objetivo = may(spec.get("objetivo")) or "COMPRENDER EL TEMA DE LA CLASE."
    return objetivo, secciones


def _resumen_actividades(spec):
    """Texto breve con las secciones y actividades reales de la guía (para la adecuación curricular)."""
    lineas = []
    for s in [x for x in (spec.get("secciones") or []) if isinstance(x, dict)]:
        tipos = [nombre for clave, nombre in (("escribir", "ESCRIBIR"), ("marcar", "MARCAR"), ("completar", "COMPLETAR"))
                 if s.get(clave)]
        lineas.append(f"- {may(s.get('titulo'))}: {', '.join(tipos) or 'lectura de imagen'}")
    if (spec.get("reconocer_unir") or {}).get("pares"):
        lineas.append("- RECONOCER y UNIR imágenes con conceptos: "
                      + ", ".join(may(p.get("concepto")) for p in spec["reconocer_unir"]["pares"]))
    if spec.get("para_pensar"):
        lineas.append(f"- {may(spec['para_pensar'].get('titulo')) or 'PARA PENSAR'}: reflexión y pregunta para conversar")
    if spec.get("conceptos_clave"):
        lineas.append("- COPIAR conceptos clave: " + " ".join(frases_validas(spec["conceptos_clave"])))
    cierre = spec.get("cierre") or {}
    if cierre:
        lineas.append("- Cierre: " + ("ESCRIBIR final" if cierre.get("tipo") == "escribir" else "recuadro para DIBUJAR"))
    return "\n".join(lineas)


def leer_guia_html(texto_html):
    """Lee una guía PIE generada por la app. Devuelve (objetivo, resumen_de_actividades)."""
    m = re.search(r'<script type="application/json" id="guia-pie-datos">(.*?)</script>', texto_html, re.DOTALL)
    if m:
        try:
            spec = json.loads(m.group(1).replace("<\\/", "</"))
            return may(spec.get("objetivo")), _resumen_actividades(spec)
        except Exception:
            pass
    # Guías anteriores (sin datos incrustados): se reconstruye el objetivo desde su cuadrícula
    inicio = texto_html.find('class="grid-block objetivo"')
    fin = texto_html.find('class="seccion"', inicio)
    bloque = texto_html[inicio:fin] if inicio >= 0 else ""
    lineas = []
    for tabla in re.findall(r'<table class="grid">(.*?)</table>', bloque, re.DOTALL)[1:]:  # la 1.ª es "OBJETIVO:"
        for fila in re.findall(r"<tr>(.*?)</tr>", tabla, re.DOTALL):
            celdas = re.findall(r'<td class="(c|sp)"[^>]*>(.*?)</td>', fila, re.DOTALL)
            if any(t == "c" and v.strip() for t, v in celdas):
                lineas.append("".join(" " if t == "sp" else _h.unescape(v) for t, v in celdas))
                break
    objetivo = " ".join(" ".join(lineas).split())
    titulos = [_h.unescape(t) for t in re.findall(r'class="sec-title">(.*?)</span>', texto_html)]
    instrucciones = [" ".join(_h.unescape(w) for w in re.findall(r'class="tok-word"[^>]*>(.*?)</div>', linea))
                     for linea in re.findall(r'class="instr-line">(.*?)</div></div>', texto_html, re.DOTALL)]
    resumen = "\n".join([f"- Sección: {t}" for t in titulos] + [f"- {i}" for i in dict.fromkeys(instrucciones)])
    return objetivo, resumen


def armar_guia(spec, nivel, imagenes, titulo_doc="Guía PIE", encabezado=None):
    """
    spec: contenido de la guía (dict, ver PROMPT en guia_pie.py).
    nivel: texto del encabezado ("Sextos", "Séptimos" o "Primeros Medios").
    imagenes: {id: (bytes, extension)} con las imágenes elegidas por el docente.
    encabezado: {logo, colegio, departamento, asignatura, docente} (ver nucleo.perfil.Perfil.encabezado).
    Devuelve (html, avisos).
    """
    avisos = []
    with _BLOQUEO, tempfile.TemporaryDirectory() as carpeta:
        return _armar(spec, nivel, imagenes, titulo_doc, encabezado, carpeta, avisos)


def _armar(spec, nivel, imagenes, titulo_doc, encabezado, carpeta, avisos):
    # Imágenes del material -> carpeta temporal (el motor las lee y las incrusta en el HTML)
    g.CONTENT_DIR = carpeta
    g._cache.clear()
    archivos = {}
    for img_id, (datos, ext) in imagenes.items():
        nombre = f"{img_id}.{ext}"
        with open(os.path.join(carpeta, nombre), "wb") as f:
            f.write(datos)
        archivos[img_id] = nombre

    objetivo, secciones = estructura_guia(spec, archivos, avisos, (encabezado or {}).get("asignatura", ""))
    S = [g.seccion(num, titulo, [bloque_html(b, archivos) for b in bloques]) for num, titulo, bloques in secciones]
    barra = ('<div class="barra-prof no-print">MODO PROFESOR (no se imprime): las imágenes y los pictogramas se cargan solos desde internet. '
             'Haz clic en un pictograma para cambiarlo (otra palabra, GOOGLE IMÁGENES, pegar URL o quitarlo); el «+» '
             'marca las palabras sin pictograma para agregarles uno. Bajo cada foto: ◀ ▶ recorre fotos libres de Wikimedia Commons y Openverse; '
             'MEMORIA CHILENA, BIBLIOTECA NACIONAL y SURDOC abren la búsqueda en ese sitio: copia la dirección de la imagen '
             '(clic derecho → Copiar dirección de imagen) y pégala con PEGAR URL. '
             'Revisa las fotos antes de imprimir.</div>')
    ob = '<div class="grid-block objetivo">' + g._emit_line(
        [{"type": "letter", "ch": c, "is_art": False} for c in "OBJETIVO:"], "copy") + '</div>'
    cuerpo = ['<div class="page">', barra, g.encabezado(nivel, encabezado), ob, objetivo_grid(objetivo)] + S + ['</div>']
    # Contenido de la guía incrustado (no se ve): la planificación lo lee para el objetivo adaptado y la actividad
    datos = json.dumps(spec, ensure_ascii=False).replace("</", "<\\/")
    doc = ('<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
           f'<title>{_h.escape(titulo_doc)}</title><style>{g.CSS}</style>'
           f'<script type="application/json" id="guia-pie-datos">{datos}</script></head><body>'
           + "".join(cuerpo) + f'<script>{g.JS}</script></body></html>')
    return doc, avisos
