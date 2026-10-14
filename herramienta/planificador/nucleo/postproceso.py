"""Limpieza y reglas deterministas aplicadas a la respuesta de la IA (sin Streamlit)."""
import re

# Campos adicionales que pide WebClass; solo se reconocen por su delimitador <<<NOMBRE>>>, etc.
SECCIONES_EXTRA = ("NOMBRE", "EVALUACION", "RECURSOS", "ADECUACIONES", "MOTIVACION", "OA", "DUA")

ETIQUETA_CAMPO = r'(?:objetivo(?:\s+de\s+(?:la\s+clase|aprendizaje)|\s+adaptado)?|actividad(?:\s+de\s+cierre)?)\s*:'

REEMPLAZOS_FEMENINO = [
    (r'\b([Tt])odos los estudiantes\b', r'\1odas las estudiantes'),
    (r'\bLos estudiantes\b', 'Las estudiantes'),
    (r'\blos estudiantes\b', 'las estudiantes'),
    (r'\bLos alumnos\b', 'Las alumnas'),
    (r'\blos alumnos\b', 'las alumnas'),
    (r'\balumnos\b', 'alumnas'),
    (r'\bcon el compañero\b', 'con la compañera'),
    (r'\bcon su compañero\b', 'con su compañera'),
    (r'\b(Analista|Evaluadora|Investigadora|Lectora|Redactora)\s+crítico\b', r'\1 crítica'),
    (r'(?<!\bel )(?<!\bun )\b(Investigador|Evaluador|Redactor|Moderador|Relator|Lector|Coordinador)\b(?!a)', r'\1a'),
    (r'(?<!\bel )(?<!\bun )\b(Secretari|Vocer)o\b', r'\1a'),
]


def limpiar_y_separar_secciones(texto):
    """Devuelve (inicio, desarrollo, cierre, extras), donde extras es {NOMBRE: ..., EVALUACION: ..., ...}."""
    if not texto:
        return "", "", "", {}

    # 1. Eliminar asteriscos o formato residual de negrita
    texto_limpio = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', texto)
    texto_limpio = texto_limpio.replace('*', '')

    # 2. Eliminar encabezados Markdown (#) y cursivas con guion bajo
    texto_limpio = re.sub(r'(?m)^[ \t]*#+[ \t]*', '', texto_limpio)
    texto_limpio = re.sub(r'(?<!\w)_(\S(?:.*?\S)?)_(?!\w)', r'\1', texto_limpio)

    # 3. Ubicar las secciones: primero por delimitadores, luego por cabeceras sueltas
    marcas = {}
    for nombre in ("INICIO", "DESARROLLO", "CIERRE"):
        m = re.search(rf'<<<\s*{nombre}\s*>>>', texto_limpio, re.IGNORECASE)
        if not m:
            m = re.search(rf'(?im)^[ \t]*(?:\d+[\.\)][ \t]*)?{nombre}[ \t]*:?[ \t]*$', texto_limpio)
        if m:
            marcas[nombre] = m
    for nombre in SECCIONES_EXTRA:
        m = re.search(rf'<<<\s*{nombre}\s*>>>', texto_limpio, re.IGNORECASE)
        if m:
            marcas[nombre] = m

    orden = sorted(marcas.items(), key=lambda item: item[1].start())
    secciones = dict.fromkeys(("INICIO", "DESARROLLO", "CIERRE") + SECCIONES_EXTRA, "")
    for i, (nombre, m) in enumerate(orden):
        fin = orden[i + 1][1].start() if i + 1 < len(orden) else len(texto_limpio)
        secciones[nombre] = texto_limpio[m.end():fin]

    if not orden:
        secciones["DESARROLLO"] = texto_limpio

    # 4. Quitar etiquetas prohibidas y metatítulos que hayan quedado dentro de los cuadros
    def depurar(seccion):
        seccion = re.sub(r'<<<\s*\w+\s*>>>', '', seccion)
        seccion = re.sub(r'(?im)^[ \t]*(?:INICIO|DESARROLLO|CIERRE)[ \t]*:?[ \t]*$\n?', '', seccion)
        seccion = re.sub(r'(?im)^[ \t]*(?:Fase|Momento)[ \t]+\d+[ \t]*[:.\-–]?[^.\n]{0,60}\n?', '', seccion)
        seccion = re.sub(r'\n{3,}', '\n\n', seccion)
        return seccion.strip()

    extras = {nombre: depurar(secciones[nombre]) for nombre in SECCIONES_EXTRA}
    return depurar(secciones["INICIO"]), depurar(secciones["DESARROLLO"]), depurar(secciones["CIERRE"]), extras


def detectar_objetivo_adaptado(texto):
    """'Objetivo adaptado: ...' escrito por el docente en el recuadro de instrucciones."""
    m = re.search(r'(?i)\bobjetivo\s+adaptado\s*:\s*(.+?)(?=\s+/\s+|\n|$)', texto or "")
    return m.group(1).strip() if m else ""


def detectar_campos_manuales(texto):
    """Extrae del recuadro del docente el objetivo y la actividad escritos a mano."""
    objetivo, actividad = "", ""
    if not texto:
        return objetivo, actividad
    m_obj = re.search(r'(?i)\bobjetivo(?:\s+de\s+(?:la\s+clase|aprendizaje))?\s*:\s*(.+?)(?=\s+/\s+|\n|$)', texto)
    if m_obj:
        objetivo = m_obj.group(1).strip()
    m_act = re.search(
        rf'(?i)\bactividad(?:\s+de\s+cierre)?\s*:\s*(.+?)(?=\s+/\s+|\n\s*{ETIQUETA_CAMPO}|\Z)', texto, re.DOTALL
    )
    if m_act:
        actividad = m_act.group(1).strip()
    return objetivo, actividad


_MARCA_PAGINA = re.compile(r'(?m)^[ \t]*---[^\n]*---[ \t]*$')       # '--- Página 3 ---', '--- archivo · Diapositiva 2 ---'
_MARCA_DOCUMENTO = re.compile(r'(?m)^\[(?:DOCUMENTO|ARCHIVO|TRANSCRIPCIÓN|VIDEO)')


def compactar_lineas(texto):
    """Las presentaciones se extraen con una línea por trozo ('Libro de clases.' / 'Respuesta en' / 'El libro'): se unen
    en un solo párrafo legible."""
    return re.sub(r'\s+', ' ', texto or '').strip()


def _hasta_fin_de_pagina(texto, inicio):
    """Texto desde `inicio` hasta la siguiente marca de página/diapositiva o de documento."""
    resto = texto[inicio:]
    cortes = [m.start() for m in (_MARCA_PAGINA.search(resto, 1), _MARCA_DOCUMENTO.search(resto, 1)) if m]
    return resto[:min(cortes)] if cortes else resto


def extraer_bloque_actividad(texto_materiales, max_caracteres=1200):
    """Actividad de cierre que trae el material, o ''. Se busca, por prioridad: ACTIVIDAD FINAL / DE CIERRE, TICKET DE
    SALIDA, CIERRE y, si no hay, la última ACTIVIDAD. Solo se toma la página o diapositiva donde está el rótulo
    (nunca el resto del documento) y se devuelve compactada."""
    t = texto_materiales or ""
    prioridades = [
        r'(?m)^[ \t]*(?:\d+[\.\)][ \t]*)?ACTIVIDAD[ \t]+(?:FINAL|DE CIERRE)\b[^\n]{0,80}$',
        r'(?im)^[ \t]*(?:\d+[\.\)][ \t]*)?TICKET DE SALIDA\b[^\n]{0,80}$',
        r'(?m)^[ \t]*(?:\d+[\.\)][ \t]*)?CIERRE\b[^\n]{0,80}$',
        r'(?m)^[ \t]*(?:\d+[\.\)][ \t]*)?ACTIVIDAD\b[^\n]{0,80}$',
    ]
    for patron in prioridades:
        coincidencias = list(re.finditer(patron, t))
        if coincidencias:
            bloque = compactar_lineas(_hasta_fin_de_pagina(t, coincidencias[-1].start()))
            return bloque[:max_caracteres]
    return ""


def ultima_pagina(texto_materiales, max_caracteres=700):
    """Texto de la última página o diapositiva con contenido (suele traer la dinámica de cierre: 3-2-1, ticket de salida…)."""
    partes = [p for p in _MARCA_PAGINA.split(texto_materiales or "") if compactar_lineas(p)]
    return compactar_lineas(partes[-1])[:max_caracteres] if partes else ""


def limpiar_cierre(texto):
    """Quita formato markdown, delimitadores, marcas de página y encabezados sobrantes de un cierre redactado por la IA."""
    t = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', texto or "").replace('*', '')
    t = re.sub(r'(?m)^[ \t]*#+[ \t]*', '', t)
    t = re.sub(r'<<<\s*\w+\s*>>>', '', t)
    t = _MARCA_PAGINA.sub('', t)
    t = re.sub(r'(?im)^[ \t]*(?:CIERRE|Opción [ABC]\)?)[ \t]*:?[ \t]*$\n?', '', t)
    return re.sub(r'\n{3,}', '\n\n', t).strip()


def corregir_texto(texto, voz="neutra"):
    """Sin etiquetas de tipo de pregunta ni '(sin autor)', mayúscula inicial en cada línea y, si la voz es femenina,
    concordancia en femenino."""
    if voz == "femenina":
        for patron, reemplazo in REEMPLAZOS_FEMENINO:
            texto = re.sub(patron, reemplazo, texto)
    texto = re.sub(
        r'[ \t]*\((?:pregunta[ \t]+)?(?:descriptiva|explicativ[oa][- ]causal|causal|evaluativa)\)', '', texto,
        flags=re.IGNORECASE
    )
    texto = re.sub(r'[ \t]*\(\s*sin autor\s*\)', '', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\(\s*sin autor\s*,\s*', '(', texto, flags=re.IGNORECASE)
    texto = re.sub(r',\s*sin autor\s*(?=[,)])', '', texto, flags=re.IGNORECASE)
    texto = re.sub(
        r'(?m)^([ \t]*(?:-[ \t]*)?[¿¡]?)(?!https?:|www\.)([a-záéíóúñü])',
        lambda m: m.group(1) + m.group(2).upper(), texto
    )
    return texto


def aplicar_reglas(inicio, desarrollo, cierre, perfil, objetivo_manual="", link_canva=""):
    """Correcciones deterministas que no se dejan solo al prompt."""
    voz = perfil.voz
    inicio, desarrollo, cierre = (corregir_texto(t, voz) for t in (inicio, desarrollo, cierre))

    apertura = perfil.apertura_fija.strip()
    if apertura:
        inicio = "\n".join(l for l in inicio.split("\n") if l.strip() != apertura).strip()
        inicio = f"{apertura}\n{inicio}"

    patron_obj = r'(?im)^[ \t]*Objetivo(?:\s+de\s+(?:la\s+clase|aprendizaje))?\s*:.*$'
    if objetivo_manual:
        linea = f"Objetivo de Aprendizaje: {objetivo_manual}"
        if re.search(patron_obj, inicio):
            inicio = re.sub(patron_obj, lambda _: linea, inicio, count=1)
        elif apertura and inicio.startswith(apertura + "\n"):
            inicio = inicio.replace(apertura + "\n", f"{apertura}\n{linea}\n", 1)
        else:
            inicio = f"{linea}\n{inicio}"
    else:
        inicio = re.sub(r'(?im)^([ \t]*)Objetivo de la clase\s*:', r'\1Objetivo de Aprendizaje:', inicio)

    if link_canva and link_canva not in inicio:
        inicio = inicio.rstrip() + f"\nLINK DE CANVA {link_canva}"
    return inicio, desarrollo, cierre


def _fijar_linea(texto, rotulo, valor, despues_de=None):
    """Reemplaza la línea 'rotulo: ...' por el valor dado, o la agrega (tras la línea 'despues_de' si existe)."""
    linea = f"{rotulo}: {valor}"
    patron = rf'(?im)^[ \t]*{re.escape(rotulo)}:.*$'
    if re.search(patron, texto):
        return re.sub(patron, lambda _: linea, texto, count=1)
    if despues_de:
        m = re.search(rf'(?im)^[ \t]*{re.escape(despues_de)}:.*$', texto)
        if m:
            return texto[:m.end()] + "\n" + linea + texto[m.end():]
    return f"{linea}\n{texto}".strip()


def objetivo_de(inicio):
    """Texto del 'Objetivo de Aprendizaje:' del Inicio (o cadena vacía)."""
    m = re.search(r'(?im)^[ \t]*Objetivo de Aprendizaje:[ \t]*(.+)$', inicio or "")
    return m.group(1).strip() if m else ""


def ajustar_adecuacion(texto, inicio, objetivo_adaptado=""):
    """Objetivo General (el de la clase, tomado del Inicio), Objetivo adaptado (si se conoce) y Actividad."""
    m = re.search(r'(?im)^[ \t]*Objetivo de Aprendizaje:[ \t]*(.+)$', inicio)
    if objetivo_adaptado:
        texto = _fijar_linea(texto, "Objetivo adaptado", objetivo_adaptado)
    if m:
        texto = _fijar_linea(texto, "Objetivo General", m.group(1).strip())
        lineas = texto.split("\n")
        general = [l for l in lineas if l.strip().startswith("Objetivo General:")]
        texto = "\n".join(general + [l for l in lineas if not l.strip().startswith("Objetivo General:")])
    return texto.strip()
