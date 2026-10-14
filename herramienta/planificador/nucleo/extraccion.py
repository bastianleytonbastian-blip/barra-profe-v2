"""Lectura de materiales (PDF, Word, TXT, PPTX, YouTube). Sin Streamlit: los avisos se devuelven como lista."""
import re
from io import BytesIO

from docx import Document
from pypdf import PdfReader


def texto_pdf(archivo, avisos=None, nombre=""):
    """archivo: ruta o file-like. Marca cada página con '--- Página N ---' (el prompt cita esas páginas)."""
    lector = PdfReader(archivo)
    texto, vacias = "", 0
    for num, pagina in enumerate(lector.pages):
        contenido = pagina.extract_text() or ""
        if not contenido.strip():
            vacias += 1
        texto += f"\n--- Página {num + 1} ---\n{contenido}"
    total = len(lector.pages)
    if avisos is not None and total and vacias > total / 2:
        avisos.append(f"El PDF '{nombre}' parece escaneado: no se pudo leer el texto de {vacias} de {total} páginas.")
    return texto


def texto_docx(archivo):
    doc = Document(archivo)
    partes = [p.text for p in doc.paragraphs if p.text.strip()]
    for tabla in doc.tables:
        for fila in tabla.rows:
            celdas = []
            for celda in fila.cells:
                t = celda.text.strip()
                # Las celdas combinadas se repiten en python-docx; se omiten duplicados contiguos
                if t and (not celdas or celdas[-1] != t):
                    celdas.append(t)
            if celdas:
                partes.append(" | ".join(celdas))
    return "\n".join(partes)


def texto_pptx(archivo):
    """Texto de cada diapositiva, marcado como '--- Diapositiva N ---' (el prompt cita esas páginas)."""
    from pptx import Presentation
    partes = []
    for n, lamina in enumerate(Presentation(archivo).slides, start=1):
        textos = [f.text_frame.text for f in lamina.shapes if getattr(f, "has_text_frame", False) and f.text_frame.text.strip()]
        partes.append(f"\n--- Página {n} ---\n" + "\n".join(textos))
    return "".join(partes)


def texto_archivo(nombre, contenido, avisos=None):
    """Texto de un archivo subido, rotulado para el prompt. contenido: bytes."""
    bajo = nombre.lower()
    if bajo.endswith(".pdf"):
        return f"\n\n[DOCUMENTO PDF: {nombre}]\n" + texto_pdf(BytesIO(contenido), avisos, nombre)
    if bajo.endswith(".docx"):
        return f"\n\n[DOCUMENTO WORD: {nombre}]\n" + texto_docx(BytesIO(contenido))
    if bajo.endswith(".pptx"):
        return f"\n\n[PRESENTACIÓN: {nombre}]\n" + texto_pptx(BytesIO(contenido))
    if bajo.endswith(".txt"):
        return f"\n\n[ARCHIVO TXT: {nombre}]\n" + contenido.decode("utf-8", errors="ignore")
    return ""


def id_youtube(url):
    patron = r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/|v/)|youtu\.be/)([0-9A-Za-z_-]{11})"
    m = re.search(patron, url or "")
    return m.group(1) if m else None


def transcripcion_youtube(video_id):
    from youtube_transcript_api import YouTubeTranscriptApi
    try:  # youtube-transcript-api >= 1.0
        return " ".join(f.text for f in YouTubeTranscriptApi().fetch(video_id, languages=["es", "en"]))
    except Exception:
        pass
    try:  # versiones anteriores a 1.0
        return " ".join(f["text"] for f in YouTubeTranscriptApi.get_transcript(video_id, languages=["es", "en"]))
    except Exception:
        return None


def texto_video(url, avisos=None):
    """Bloque de texto para el prompt a partir de un enlace de YouTube ('' si no se reconoce)."""
    vid = id_youtube(url)
    if not vid:
        if avisos is not None:
            avisos.append("No se reconoció el enlace de YouTube; se omite el video.")
        return ""
    t = transcripcion_youtube(vid)
    if t:
        return f"\n\n[TRANSCRIPCIÓN DE VIDEO DE YOUTUBE]:\n{t[:6000]}"
    return f"\n\n[VIDEO INDICADO]: {url} (No se pudieron extraer subtítulos automáticos)."
