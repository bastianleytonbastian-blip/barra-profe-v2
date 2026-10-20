"""Colores y letra de Barra Profe: una sola fuente para la barra y para el planificador.

Cada paleta es un juego completo de colores con nombre (fondo, botón, acento, texto…). Las ventanas usan esos nombres y
nunca un color escrito a mano, así una paleta clara o de alto contraste se ve bien en todas partes. Las pruebas
(tests/test_tema.py) comprueban que el texto chico tenga contraste de al menos 4,5 : 1 en cada paleta.

Solo usa la biblioteca estándar: el planificador lo lee directo desde el archivo (sin ventanas ni red).
"""

from __future__ import annotations

# Colores de cada paleta:
#   fondo · boton (superficie de botones y tarjetas) · hover · pulsado · acento · texto · tenue (texto secundario)
#   suave (detalles discretos: subtítulos de botones, enlaces) · lengueta · alerta (lengüeta con bloques sin firmar)
#   ok · aviso · error (estados) · consola / consola_texto (detalle técnico) · sobre_acento (texto sobre un botón
#   de acento) · sobre_lengueta · web (acento del planificador: modo claro y modo oscuro)
PALETAS: dict[str, dict] = {
    "morado": {"nombre": "Morado", "fondo": "#17122a", "boton": "#241c3d", "hover": "#3b2d66", "pulsado": "#513c8c",
               "acento": "#a78bfa", "texto": "#ffffff", "tenue": "#b3a8d6", "suave": "#9b90bc",
               "lengueta": "#7c5cff", "alerta": "#e0455f", "ok": "#6fd18c", "aviso": "#f0c775", "error": "#ff8b9a",
               "consola": "#120e1f", "consola_texto": "#e9e4ff", "sobre_acento": "#17122a",
               "sobre_lengueta": "#ffffff", "web": {"claro": "#5b3fc4", "oscuro": "#a78bfa"}},
    "azul": {"nombre": "Azul noche", "fondo": "#0f1829", "boton": "#1b2740", "hover": "#2a3c63", "pulsado": "#3a5288",
             "acento": "#7cb3ff", "texto": "#ffffff", "tenue": "#a3b8d9", "suave": "#8b9ebd",
             "lengueta": "#4a8cff", "alerta": "#e0455f", "ok": "#6fd18c", "aviso": "#f0c775", "error": "#ff8b9a",
             "consola": "#0a1120", "consola_texto": "#e4ecff", "sobre_acento": "#0f1829",
             "sobre_lengueta": "#0f1829", "web": {"claro": "#1f5aa8", "oscuro": "#7cb3ff"}},
    "verde": {"nombre": "Verde pizarra", "fondo": "#10211c", "boton": "#1a3129", "hover": "#27493d",
              "pulsado": "#336152", "acento": "#6ee7b7", "texto": "#ffffff", "tenue": "#a4cdbd", "suave": "#88ae9f",
              "lengueta": "#34d399", "alerta": "#e0455f", "ok": "#6fd18c", "aviso": "#f0c775", "error": "#ff8b9a",
              "consola": "#0b1814", "consola_texto": "#e3f5ee", "sobre_acento": "#10211c",
              "sobre_lengueta": "#10211c", "web": {"claro": "#0f6e52", "oscuro": "#6ee7b7"}},
    "vino": {"nombre": "Vino", "fondo": "#231016", "boton": "#391a23", "hover": "#5a2936", "pulsado": "#7a3646",
             "acento": "#fb9eb5", "texto": "#ffffff", "tenue": "#d9aeb8", "suave": "#b68d97",
             "lengueta": "#e35d7d", "alerta": "#e0455f", "ok": "#6fd18c", "aviso": "#f0c775", "error": "#ff8b9a",
             "consola": "#1a0b10", "consola_texto": "#fbe7ec", "sobre_acento": "#231016",
             "sobre_lengueta": "#231016", "web": {"claro": "#9c2f4b", "oscuro": "#fb9eb5"}},
    "grafito": {"nombre": "Grafito", "fondo": "#16181d", "boton": "#23262e", "hover": "#343843", "pulsado": "#464b59",
                "acento": "#cbd5e1", "texto": "#ffffff", "tenue": "#a7aebb", "suave": "#9298a4",
                "lengueta": "#94a3b8", "alerta": "#e0455f", "ok": "#6fd18c", "aviso": "#f0c775", "error": "#ff8b9a",
                "consola": "#101215", "consola_texto": "#e7e9ee", "sobre_acento": "#16181d",
                "sobre_lengueta": "#16181d", "web": {"claro": "#3b4655", "oscuro": "#cbd5e1"}},
    "claro": {"nombre": "Claro", "fondo": "#f6f5fb", "boton": "#ffffff", "hover": "#ebe7f8", "pulsado": "#d9d1f3",
              "acento": "#5b3fc4", "texto": "#1d1630", "tenue": "#4f4668", "suave": "#6b6286",
              "lengueta": "#6d4fe0", "alerta": "#d93a56", "ok": "#1d7a3c", "aviso": "#8a5a00", "error": "#b3261e",
              "consola": "#efedf6", "consola_texto": "#1d1630", "sobre_acento": "#ffffff",
              "sobre_lengueta": "#ffffff", "web": {"claro": "#5b3fc4", "oscuro": "#a78bfa"}},
    "contraste": {"nombre": "Alto contraste", "fondo": "#000000", "boton": "#141414", "hover": "#2a2a2a",
                  "pulsado": "#3d3d3d", "acento": "#ffd400", "texto": "#ffffff", "tenue": "#e6e6e6", "suave": "#c8c8c8",
                  "lengueta": "#ffd400", "alerta": "#ff4d4d", "ok": "#5df08a", "aviso": "#ffd400", "error": "#ff7a7a",
                  "consola": "#000000", "consola_texto": "#ffffff", "sobre_acento": "#000000",
                  "sobre_lengueta": "#000000", "web": {"claro": "#1d1d1d", "oscuro": "#ffd400"}},
}
PALETA_INICIAL = "morado"

# Escala de letra (puntos). Nada por debajo de 9: en los notebooks del colegio el texto de 8 pt no se lee.
LETRA = {"titulo": 13, "subtitulo": 11, "cuerpo": 10, "chico": 9}
LETRA_MINIMA = 9
# Tamaño de letra elegido por el docente (Ajustes → Apariencia).
TAMANOS_LETRA = {"chica": 0.9, "normal": 1.0, "grande": 1.15}
# Ancho de la barra desplegada, en píxeles a escala 100 %.
ANCHOS_BARRA = {"estrecha": 190, "normal": 210, "ancha": 250}


def paleta(clave: str) -> dict:
    """La paleta pedida o, si no existe, la inicial."""
    return PALETAS.get(clave) or PALETAS[PALETA_INICIAL]


def _luminancia(color: str) -> float:
    color = color.lstrip("#")
    canales = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lineal = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lineal[0] + 0.7152 * lineal[1] + 0.0722 * lineal[2]


def contraste(a: str, b: str) -> float:
    """Contraste entre dos colores (#rrggbb), de 1 a 21. Para texto chico se pide al menos 4,5."""
    claro, oscuro = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


def tamano_letra(puntos: int, escala: float = 1.0) -> int:
    """Puntos finales de una letra: nunca menos de LETRA_MINIMA, multiplicados por el tamaño elegido."""
    return max(LETRA_MINIMA, round(max(puntos, LETRA_MINIMA) * escala))
