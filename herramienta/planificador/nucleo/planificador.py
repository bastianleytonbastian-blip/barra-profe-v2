"""Generación de una planificación de clase: arma el pedido a la IA, limpia la respuesta y devuelve todos los campos.
Sin Streamlit; lo usa el servidor web (servidor.py)."""
import re

from nucleo import cierre, curriculo, extraccion, ia, postproceso as pp, prompts
from nucleo.armar_guia_pie import leer_guia_html
from nucleo.webclass import PAUTAS_DUA, codigos_oa, completar_dua, horas_webclass


def leer_guia_pie(nombre, contenido, avisos):
    """Devuelve (objetivo, resumen_actividades, texto) de la guía PIE subida (.html exacta; .pdf/.docx como texto)."""
    if not nombre:
        return "", "", ""
    bajo = nombre.lower()
    try:
        if bajo.endswith(".html"):
            objetivo, resumen = leer_guia_html(contenido.decode("utf-8", errors="ignore"))
            return objetivo, resumen, ""
        if bajo.endswith(".pdf"):
            from io import BytesIO
            return "", "", extraccion.texto_pdf(BytesIO(contenido))[:6000]
        if bajo.endswith(".docx"):
            from io import BytesIO
            return "", "", extraccion.texto_docx(BytesIO(contenido))[:6000]
    except Exception as e:
        avisos.append(f"No se pudo leer la guía PIE: {e}")
    return "", "", ""


def generar(perfil, asignatura, curso, tema, indicaciones, duracion, actividad_extra=None, link_canva="", url_video="",
            archivos=(), guia_pie=None, al_avanzar=None):
    """archivos: [(nombre, bytes)]; guia_pie: (nombre, bytes) o None. Devuelve un dict con la planificación y avisos.

    al_avanzar(tipo, datos) recibe el avance para mostrarlo en vivo: ("etapa", {etapa, texto}) al empezar cada parte,
    ("intento", {modelo}) cuando la IA empieza (o reintenta con otro modelo) y ("trozo", texto) mientras escribe.
    """
    def avanzar(tipo, datos):
        if al_avanzar:
            try:
                al_avanzar(tipo, datos)
            except Exception:  # noqa: BLE001  (mostrar el avance nunca debe botar la planificación)
                pass

    avisos, infos = [], []
    if archivos or url_video.strip() or guia_pie:
        avanzar("etapa", {"etapa": "material", "texto": "Leyendo el material"})
    texto_materiales = ""
    for nombre, contenido in archivos:
        texto_materiales += extraccion.texto_archivo(nombre, contenido, avisos)
    if url_video.strip():
        texto_materiales += extraccion.texto_video(url_video.strip(), avisos)

    minutos_extra = int((actividad_extra or {}).get("minutos") or 0)
    if actividad_extra:
        tiempo_str = (f"{duracion} minutos ({minutos_extra} min {actividad_extra['nombre']} + "
                      f"{duracion - minutos_extra} min de clase)")
    else:
        tiempo_str = f"{duracion} minutos"

    link_canva = link_canva.strip()
    info_canva = f"LINK DE CANVA {link_canva}" if link_canva else "NO SE PROPORCIONÓ LINK DE CANVA."
    objetivo_manual, actividad_manual = pp.detectar_campos_manuales(indicaciones)
    modo_cierre, fuente_cierre = cierre.elegir_modo(actividad_manual, texto_materiales)

    guia_objetivo, guia_actividades, guia_texto = leer_guia_pie(*(guia_pie or ("", b"")), avisos)
    objetivo_adaptado = pp.detectar_objetivo_adaptado(indicaciones) or guia_objetivo
    partes = ["ADECUACIÓN CURRICULAR (sección <<<ADECUACIONES>>>):"]
    if objetivo_adaptado:
        partes.append(f"- Objetivo adaptado (usar literal): {objetivo_adaptado}")
    if guia_actividades:
        partes.append(f"- La «Actividad» debe describir estas actividades reales de la guía PIE:\n{guia_actividades}")
    if guia_texto:
        partes.append("- Se adjuntó la guía PIE de esta clase. Toma de ella el objetivo adaptado y describe en «Actividad» "
                      f"sus actividades reales:\n{guia_texto}")
    if not (objetivo_adaptado or guia_actividades or guia_texto):
        partes.append("- No se adjuntó guía PIE: redacta el objetivo adaptado y la actividad según la plantilla.")
    regla_adecuacion = "\n".join(partes)

    regla_objetivo = (f"OBJETIVO DE APRENDIZAJE ESCRITO POR EL DOCENTE (usar literal): {objetivo_manual}"
                      if objetivo_manual else "El docente no escribió objetivo; tómalo del material adjunto.")
    regla_extra = ""
    if actividad_extra:
        regla_extra = (f"- ACTIVIDAD ESPECIAL «{actividad_extra['nombre']}»: los primeros {minutos_extra} minutos se dedican "
                       f"a ella ({actividad_extra.get('descripcion', '')}); el Inicio la menciona en una línea y la "
                       "secuencia de la clase se ajusta a los minutos restantes.\n")

    material = re.sub(r"[ \t]+", " ", texto_materiales)
    material = re.sub(r"\n\s*\n+", "\n", material).strip()
    recorte = {}
    prompt_sistema = prompts.construir_sistema(perfil, asignatura, PAUTAS_DUA)
    oas = curriculo.oa_del_curso(asignatura, curso)

    def construir_mensajes(info):
        limite = info["max_material"]
        recorte["limite"] = limite if len(material) > limite else None
        bloque_oa = ("LISTA OFICIAL DE OA DEL CURSO (Bases Curriculares MINEDUC; elige de aquí los códigos de <<<OA>>>):\n"
                     + curriculo.lista_para_prompt(oas, largo_max=None if limite > 20000 else 110)) if oas else ""
        usuario = f"""
Asignatura: {asignatura}
Curso: {curso}
Tiempo: {tiempo_str}
Contenido o tema: {tema if tema.strip() else 'Extraer del material adjunto.'}

INSTRUCCIONES DIRECTAS DEL DOCENTE (MÁXIMA PRIORIDAD):
{indicaciones if indicaciones.strip() else 'No se especificaron indicaciones adicionales.'}

{info_canva}

{regla_objetivo}

{regla_adecuacion}

{bloque_oa}

MATERIALES DE CLASE SUBIDOS POR EL DOCENTE:
{material[:limite] or 'No se adjuntaron archivos; basarse en el contenido curricular estándar.'}

INSTRUCCIÓN VITAL:
- Cero asteriscos (*) y cero etiquetas entre paréntesis.
- Separa los momentos con <<<INICIO>>>, <<<DESARROLLO>>> y <<<CIERRE>>>, y agrega al final <<<NOMBRE>>>, <<<EVALUACION>>>, <<<RECURSOS>>>, <<<ADECUACIONES>>>, <<<MOTIVACION>>>, <<<OA>>> y <<<DUA>>>.
- El desarrollo se organiza en bloques temáticos que siguen las secciones del material.
- Usa solo páginas, títulos, autores y datos reales del material de este tema.
- No redactes el cierre de la clase ni escribas <<<CIERRE>>>: se redacta aparte.
{regla_extra}"""
        return [{"role": "system", "content": prompt_sistema}, {"role": "user", "content": usuario}]

    avanzar("etapa", {"etapa": "redactando", "texto": "Redactando la clase"})
    bruto, usado, fin, avisos_ia = ia.completar(construir_mensajes, max_tokens=8192, temperature=0.15,
                                                al_intento=lambda modelo: avanzar("intento", {"modelo": modelo}),
                                                al_trozo=lambda texto: avanzar("trozo", texto))
    if recorte.get("limite"):
        infos.append(f"El material es largo: {usado.split(' · ')[0]} recibió sus primeros {recorte['limite']:,} caracteres. "
                     "Si importan páginas posteriores, indícalas en las indicaciones propias.".replace(",", "."))
    ini, des, cie, extras = pp.limpiar_y_separar_secciones(bruto)
    ini, des, cie = pp.aplicar_reglas(ini, des, cie, perfil, objetivo_manual, link_canva)
    extras = {k: pp.corregir_texto(v, perfil.voz) for k, v in extras.items()}

    # El cierre se redacta aparte, con su propia validación (ver nucleo/cierre.py)
    avanzar("etapa", {"etapa": "cierre", "texto": "Escribiendo el cierre"})
    cie, origen_cierre = cierre.redactar(perfil, asignatura, curso, tema, pp.objetivo_de(ini) or objetivo_manual, des,
                                         modo_cierre, fuente_cierre, pp.ultima_pagina(texto_materiales))
    if origen_cierre == "respaldo":
        avisos.append("No se pudo redactar el cierre con la IA; se usó un cierre base. Revísalo y ajústalo.")

    nombre_clase = extras["NOMBRE"].split("\n")[0].strip().rstrip(".") or tema.strip()[:80]
    if link_canva and link_canva not in extras["RECURSOS"]:
        extras["RECURSOS"] = (extras["RECURSOS"] + f"\n- Presentación en Canva: {link_canva}").strip()
    oficiales = [o["codigo"] for o in oas]
    m_claves = re.search(r'(?i)palabras\s+clave\s*:\s*(.+)', extras["OA"])
    if fin == "length":
        avisos.append("La respuesta llegó al límite de largo y puede estar incompleta (revisa el Cierre y las secciones de WebClass).")
    return {
        "inicio": ini, "desarrollo": des, "cierre": cie, "nombre": nombre_clase,
        "evaluacion": extras["EVALUACION"], "recursos": extras["RECURSOS"], "motivacion": extras["MOTIVACION"],
        "adecuaciones": pp.ajustar_adecuacion(extras["ADECUACIONES"], ini, objetivo_adaptado),
        "oa_sel": [c for c in codigos_oa(extras["OA"]) if c in oficiales], "oa_texto": ", ".join(codigos_oa(extras["OA"])),
        "oa_claves": m_claves.group(1).strip() if m_claves else "",
        "dua": completar_dua([int(n) for n in re.findall(r"\d+", extras["DUA"]) if 1 <= int(n) <= 31]),
        "duracion_horas": horas_webclass(tiempo_str), "tiempo": tiempo_str, "asignatura": asignatura, "curso": curso,
        "tema": tema.strip() or "Según material adjunto", "modelo": usado, "modo_cierre": modo_cierre, "origen_cierre": origen_cierre,
        "avisos": avisos, "infos": infos, "intentos_previos": [a.split(";")[0] for a in avisos_ia],
    }
