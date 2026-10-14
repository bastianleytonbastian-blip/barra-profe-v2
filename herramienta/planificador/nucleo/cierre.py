"""El cierre de la clase se redacta en un pedido propio (no dentro del pedido grande de Inicio y Desarrollo).

Tres modos, según de dónde sale la actividad:
  A  el docente la escribió  -> se redacta con sus palabras, sin inventar otra
  B  el material trae una actividad -> se redacta con claridad a partir del texto extraído (que viene desordenado)
  C  no hay ninguna -> síntesis: esquema en la pizarra + discusión en pareja + 3 o 4 preguntas
El resultado se valida; si no cumple, se reintenta una vez y, si aun así falla, se arma un cierre de respaldo
que siempre es correcto. Sin Streamlit.
"""
import re

from nucleo import ia, postproceso as pp
from nucleo.perfil import VOCES

MODO_A, MODO_B, MODO_C = "A", "B", "C"

EJEMPLO_C = (
    "El docente construye en la pizarra, con las intervenciones del curso, un esquema que relaciona la fracción con la "
    "división y con la parte de un todo, usando los ejemplos de los bloques. Luego discuten en pareja durante seis minutos "
    "y dos parejas voluntarias comparten cada respuesta con el curso.\n"
    "- ¿Qué representan el numerador y el denominador de una fracción?\n"
    "- ¿Por qué dos fracciones distintas pueden representar la misma cantidad?\n"
    "- ¿Qué estrategia te parece más clara para comparar fracciones? Justifica con un ejemplo de la clase.")


def elegir_modo(actividad_manual, texto_materiales):
    """Devuelve (modo, fuente): la actividad del docente, la del material (ya compactada) o nada."""
    if actividad_manual.strip():
        return MODO_A, pp.compactar_lineas(actividad_manual)
    bloque = pp.extraer_bloque_actividad(texto_materiales)
    if bloque:
        return MODO_B, bloque
    return MODO_C, ""


def _instrucciones(modo, fuente, ultima_pagina):
    if modo == MODO_A:
        return ("El docente escribió la actividad de cierre. Redáctala con claridad y corrección, con el mismo contenido y "
                "orden que él indicó. No agregues tareas, preguntas ni detalles que él no dijo, y deja los números de "
                "página y de pregunta como cifras (183, no «ciento ochenta y tres»).\n\nACTIVIDAD DEL DOCENTE:\n" + fuente +
                "\n\nFORMATO: la primera línea es solo la palabra ACTIVIDAD; después, una a tres oraciones. Máximo 450 caracteres.")
    if modo == MODO_B:
        return ("El material de la clase trae una actividad de cierre. El texto de abajo fue extraído de una presentación "
                "o un PDF: viene con trozos de frases cortados, mayúsculas irregulares y a veces solo remite a un libro o "
                "cuaderno. NO lo copies tal cual: entiende qué se pide y redáctalo en pasos claros, diciendo qué hace el "
                "curso y citando las páginas o recursos que se nombran. No inventes preguntas ni tareas que el material "
                "no mencione. Si solo remite a una página del libro o del cuaderno, basta una o dos oraciones que lo "
                "digan.\n\nTEXTO EXTRAÍDO DEL MATERIAL:\n" + fuente +
                "\n\nFORMATO: la primera línea es solo la palabra ACTIVIDAD; después, una a tres oraciones. Máximo 450 caracteres.")
    pista = (f"\nLa última página del material dice: «{ultima_pagina}». Si propone una dinámica de cierre (por ejemplo "
             "3-2-1, ticket de salida o resumen en el cuaderno), incorpórala dentro del párrafo.\n") if ultima_pagina else ""
    return ("No hay actividad indicada: redacta la síntesis de la clase SIN la palabra ACTIVIDAD, con esta forma exacta:\n"
            "1) Un párrafo: el docente construye en la pizarra, con las intervenciones del curso, un esquema o diagrama "
            "breve que resume los bloques de la clase (di qué relaciona u ordena); luego el curso discute en pareja durante "
            "seis minutos y dos parejas voluntarias comparten cada respuesta con el curso.\n"
            "2) De 3 a 4 preguntas, cada una en su propia línea y empezando con guion y espacio (- ¿...?), de lo simple a lo "
            "complejo: descriptivas (qué, quién, cuándo, dónde), luego explicativas (por qué, cómo se relaciona) y la última "
            "evaluativa, que exige tomar postura y justificarla con lo aprendido.\n" + pista +
            "\nEJEMPLO DE FORMA (clase de fracciones; adapta al tema real, no copies su contenido):\n" + EJEMPLO_C)


def mensajes(perfil, asignatura, curso, objetivo, desarrollo, modo, fuente, ultima_pagina, observacion=""):
    sistema = (f"Eres un asistente pedagógico de {perfil.tratamiento_docente or 'el profesor'} de {asignatura} en Chile. "
               f"Redactas SOLO el cierre de una clase. {VOCES.get(perfil.voz, VOCES['neutra'])} Texto plano en español: sin "
               "asteriscos, sin almohadillas, sin títulos como «Cierre», sin marcas como «--- Página 3 ---» ni texto "
               "entre corchetes.")
    usuario = (f"Curso: {curso}\nObjetivo de Aprendizaje de la clase: {objetivo or '(según el desarrollo)'}\n\n"
               f"DESARROLLO DE LA CLASE (el cierre debe ser coherente con lo trabajado aquí):\n{desarrollo[:5000]}\n\n"
               + _instrucciones(modo, fuente, ultima_pagina)
               + (f"\n\nCORRECCIÓN: el intento anterior no sirvió porque {observacion}. Corrígelo." if observacion else ""))
    return [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]


def validar(texto, modo):
    """None si el cierre sirve; si no, el motivo (para pedir la corrección)."""
    t = (texto or "").strip()
    if re.search(r'---|Página \d+ ---|\[[^\]]{3,}\]', t):
        return "contiene marcas de página o texto entre corchetes"
    if modo == MODO_C:
        if len(t) < 140:
            return "es demasiado corto"
        if len([l for l in t.split("\n") if l.strip().startswith("-") and "?" in l]) < 3:
            return "no tiene al menos 3 preguntas, cada una en su línea con guion"
        if re.match(r'(?i)\s*actividad\b', t):
            return "no debe llevar la palabra ACTIVIDAD"
        return None
    cuerpo = re.sub(r'(?i)^\s*actividad\s*\n?', '', t).strip()
    if len(cuerpo) < 40:
        return "es demasiado corto"
    if len(t) > 1800:
        return "es demasiado largo"
    return None


def _normalizar(texto, modo, perfil):
    t = pp.corregir_texto(pp.limpiar_cierre(texto), perfil.voz)
    if modo in (MODO_A, MODO_B) and not re.match(r'(?i)\s*actividad\b', t):
        t = "ACTIVIDAD\n" + t
    return re.sub(r'(?i)^\s*actividad\b[ \t]*[:.\-–]?[ \t]*', 'ACTIVIDAD\n', t, count=1).replace("ACTIVIDAD\n\n", "ACTIVIDAD\n")


def respaldo(modo, fuente, tema, perfil):
    """Cierre que siempre es correcto, sin IA, para cuando la redacción falla."""
    if modo in (MODO_A, MODO_B):
        return "ACTIVIDAD\n" + (pp.corregir_texto(fuente[:700], perfil.voz) or "Las estudiantes desarrollan la actividad indicada en el material.")
    tema = (tema or "la clase").strip().rstrip(".")
    return (f"El docente construye en la pizarra, con las intervenciones del curso, un esquema que resume los bloques "
            f"trabajados sobre {tema}. Luego discuten en pareja durante seis minutos y dos parejas voluntarias comparten "
            f"cada respuesta con el curso.\n"
            f"- ¿Cuáles son las ideas principales que trabajamos hoy sobre {tema}?\n"
            f"- ¿Cómo se relacionan entre sí las ideas del esquema?\n"
            f"- ¿Qué conclusión o postura te parece más sólida sobre {tema}? Justifica con lo aprendido en la clase.")


def redactar(perfil, asignatura, curso, tema, objetivo, desarrollo, modo, fuente, ultima_pagina):
    """Devuelve (texto_del_cierre, origen) con origen 'ia', 'ia-corregido' o 'respaldo'."""
    observacion = ""
    for intento in range(2):
        try:
            texto, _, _, _ = ia.completar(
                lambda info: mensajes(perfil, asignatura, curso, objetivo, desarrollo, modo, fuente, ultima_pagina, observacion),
                max_tokens=1500, temperature=0.25 if intento == 0 else 0.4, razonamiento_bajo=True)
        except Exception:
            break
        candidato = _normalizar(texto, modo, perfil)
        motivo = validar(candidato, modo)
        if not motivo:
            return candidato, "ia" if intento == 0 else "ia-corregido"
        observacion = motivo
    return respaldo(modo, fuente, tema, perfil), "respaldo"
