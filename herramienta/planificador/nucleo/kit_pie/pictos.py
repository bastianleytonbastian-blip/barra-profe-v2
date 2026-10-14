# -*- coding: utf-8 -*-
"""Palabras (sin tilde, en mayúscula) -> término que se busca en ARASAAC, según la asignatura de la guía.

GENERAL sirve para cualquier guía; POR_ASIGNATURA se suma según el nombre de la asignatura (coincidencia parcial,
sin tildes ni mayúsculas). La IA agrega además sus propias equivalencias en cada guía ("picto_extra").
"""
import unicodedata

GENERAL = {
    "CASA": "casa", "ESCUELA": "escuela", "CIUDAD": "ciudad", "CAMPO": "campo", "MAPA": "mapa", "PAIS": "país",
    "CHILE": "Chile", "SUR": "sur", "NORTE": "norte", "MAR": "mar", "OCEANO": "mar", "RIO": "río", "LAGO": "lago",
    "MONTANA": "montaña", "BOSQUE": "bosque", "DESIERTO": "desierto", "ISLA": "isla", "PUERTO": "puerto",
    "SOL": "sol", "AGUA": "agua", "TIERRA": "tierra", "FAMILIA": "familia", "NINOS": "niño", "PERSONAS": "persona",
    "TRABAJO": "trabajar", "DINERO": "dinero", "LIBRO": "libro", "PRESIDENTE": "presidente", "BARCO": "barco",
    "BARCOS": "barco", "ANIMALES": "animal", "PLANTAS": "planta", "ALIMENTOS": "comida", "COMIDA": "comida",
}

POR_ASIGNATURA = {
    "historia": {
        "GUERRA": "guerra", "EJERCITO": "soldado", "TERRITORIO": "mapa", "TRATADO": "firmar", "COLONOS": "inmigrante",
        "INMIGRANTES": "inmigrante", "ESPANOLES": "España", "AGRICULTURA": "agricultura", "INDUSTRIA": "fábrica",
        "MINERIA": "mina", "SALITRE": "mina", "IGLESIA": "iglesia", "FUERTE": "castillo", "TRIGO": "trigo",
        "GANADO": "vaca", "REY": "rey", "REINO": "rey", "CASTILLO": "castillo", "CABALLERO": "caballero",
        "PERU": "Perú", "BOLIVIA": "Bolivia", "ARGENTINA": "Argentina", "ALEMANES": "Alemania",
        "DEMOCRACIA": "votar", "CONSTITUCION": "ley", "LEY": "ley", "PUEBLO": "pueblo", "INDIGENAS": "indígena",
    },
    "matem": {
        "SUMA": "sumar", "SUMAR": "sumar", "RESTA": "restar", "RESTAR": "restar", "MULTIPLICAR": "multiplicar",
        "DIVIDIR": "dividir", "FRACCION": "pizza", "FRACCIONES": "pizza", "NUMERO": "número", "NUMEROS": "número",
        "MITAD": "mitad", "TRIANGULO": "triángulo", "CUADRADO": "cuadrado", "CIRCULO": "círculo",
        "RECTANGULO": "rectángulo", "FIGURA": "figura", "FIGURAS": "figura", "MEDIR": "medir", "REGLA": "regla",
        "GRAFICO": "gráfico", "TABLA": "tabla", "DINERO": "dinero", "PESO": "balanza", "LARGO": "largo",
    },
    "ciencias": {
        "ENERGIA": "luz", "CALOR": "calor", "FRIO": "frío", "HIELO": "hielo", "VAPOR": "vapor", "LLUVIA": "lluvia",
        "NUBE": "nube", "NUBES": "nube", "EVAPORACION": "calor", "CONDENSACION": "nube", "PRECIPITACION": "lluvia",
        "CELULA": "célula", "CELULAS": "célula", "ANIMAL": "animal", "VEGETAL": "planta", "SEMILLA": "semilla",
        "HOJA": "hoja", "RAIZ": "raíz", "FLOR": "flor", "ARBOL": "árbol", "HUESO": "hueso", "CORAZON": "corazón",
        "PULMONES": "pulmón", "MICROSCOPIO": "microscopio", "TERMOMETRO": "termómetro", "IMAN": "imán",
        "PLANETA": "planeta", "LUNA": "luna", "ESTRELLA": "estrella", "VOLCAN": "volcán", "TEMPERATURA": "termómetro",
        "LIQUIDO": "agua", "SOLIDO": "hielo", "GAS": "vapor", "PARTICULAS": "átomo", "ATOMO": "átomo",
    },
    "lengua": {
        "LEER": "leer", "ESCRIBIR": "escribir", "CUENTO": "cuento", "POEMA": "poema", "LIBRO": "libro",
        "PALABRA": "palabra", "LETRA": "letra", "ORACION": "frase", "TEXTO": "texto", "AUTOR": "escritor",
        "PERSONAJE": "personaje", "HISTORIA": "cuento", "CARTA": "carta", "NOTICIA": "periódico", "FABULA": "cuento",
    },
    "ingl": {
        "HELLO": "hola", "COLOR": "color", "COLORS": "color", "ANIMAL": "animal", "FAMILY": "familia", "HOUSE": "casa",
        "SCHOOL": "escuela", "FOOD": "comida", "WATER": "agua",
    },
    "arte": {"DIBUJO": "dibujar", "PINTURA": "pintar", "COLOR": "color", "COLORES": "color", "PINCEL": "pincel",
             "ESCULTURA": "escultura", "FORMA": "forma", "LINEA": "línea"},
    "musica": {"CANCION": "canción", "INSTRUMENTO": "instrumento", "TAMBOR": "tambor", "GUITARRA": "guitarra",
               "CANTAR": "cantar", "RITMO": "ritmo", "SONIDO": "sonido"},
    "educacion fisica": {"CORRER": "correr", "SALTAR": "saltar", "PELOTA": "pelota", "JUEGO": "jugar", "EQUIPO": "equipo",
                         "DEPORTE": "deporte", "EJERCICIO": "ejercicio", "AGUA": "agua"},
    "tecnolog": {"COMPUTADOR": "computador", "INTERNET": "internet", "HERRAMIENTA": "herramienta", "MAQUINA": "máquina",
                 "MATERIAL": "material", "OBJETO": "objeto", "DISENO": "dibujar"},
}


def _norm(t):
    t = unicodedata.normalize("NFD", t or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def para(asignatura):
    """Diccionario completo para una asignatura: general + las categorías cuyo nombre aparece en ella."""
    a = _norm(asignatura)
    d = dict(GENERAL)
    for clave, palabras in POR_ASIGNATURA.items():
        coincide = clave in a
        if clave == "ciencias":
            coincide = "educacion fisica" not in a and "sociales" not in a and (coincide or any(x in a for x in ("biolog", "fisica", "quimica", "naturales")))
        elif clave == "lengua":
            coincide = coincide or "lenguaje" in a
        if coincide:
            d.update(palabras)
    return d
