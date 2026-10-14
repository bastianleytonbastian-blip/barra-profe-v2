"""Proveedores de IA (todos con API compatible con OpenAI) y paso automático al siguiente cuando uno llega a su límite."""
import json
import os
import re
import time

from openai import OpenAI, Timeout

from nucleo import rutas


def _ruta_claves():
    return os.path.join(rutas.personal_usuario(), "claves.json")      # claves de IA de la cuenta activa


def _ruta_config():
    return os.path.join(rutas.personal_usuario(), "config_ia.json")   # proveedor, modelo y respaldo elegidos


# max_material: caracteres del material que se envían (según el límite gratuito de cada proveedor)
# vision: el modelo puede ver imágenes (se usa en la guía PIE)
PROVEEDORES = {
    "Gemini (Google)": {
        "secreto": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "modelo": "gemini-flash-latest",
        "max_material": 150000,
        "vision": True,
        "razonamiento": True,
        "ayuda": "aistudio.google.com/apikey",
    },
    "Groq": {
        "secreto": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "modelo": "openai/gpt-oss-120b",
        "max_material": 7000,
        "vision": False,
        "razonamiento": "gpt-oss",
        "ayuda": "console.groq.com/keys",
    },
    "Cerebras": {
        "secreto": "CEREBRAS_API_KEY",
        "base_url": "https://api.cerebras.ai/v1",
        "modelo": "gpt-oss-120b",
        "max_material": 40000,
        "vision": False,
        "razonamiento": "gpt-oss",
        "ayuda": "cloud.cerebras.ai",
    },
    "OpenRouter": {
        "secreto": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "modelo": "openai/gpt-oss-120b:free",
        "max_material": 40000,
        "vision": False,
        "razonamiento": False,
        "ayuda": "openrouter.ai/settings/keys",
    },
}


def _leer_json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _escribir_json(ruta, datos):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)


def clave_guardada(nombre_secreto):
    """Clave desde variable de entorno o data/claves.json."""
    return os.environ.get(nombre_secreto) or _leer_json(_ruta_claves()).get(nombre_secreto, "")


def guardar_claves(claves):
    """claves: {nombre_proveedor: clave}. Una clave vacía borra la guardada; None la deja como está."""
    actuales = _leer_json(_ruta_claves())
    for proveedor, clave in claves.items():
        if clave is None or proveedor not in PROVEEDORES:
            continue
        secreto = PROVEEDORES[proveedor]["secreto"]
        if clave.strip():
            actuales[secreto] = clave.strip()
        else:
            actuales.pop(secreto, None)
    _escribir_json(_ruta_claves(), actuales)
    _cache_modelos.clear()


def guardar_config(proveedor=None, modelo=None, respaldo=True):
    _escribir_json(_ruta_config(), {"proveedor": proveedor, "modelo": modelo, "respaldo": bool(respaldo)})


def estado_claves():
    """{proveedor: {guardada: bool, final: '…abcd'}} sin exponer la clave completa."""
    salida = {}
    for nombre, info in PROVEEDORES.items():
        clave = clave_guardada(info["secreto"])
        salida[nombre] = {"guardada": bool(clave), "final": ("…" + clave[-4:]) if clave else "", "ayuda": info["ayuda"],
                          "vision": info["vision"]}
    return salida


def cliente(proveedor, clave, streaming=False):
    # Con streaming, 'read' es el máximo de silencio entre trozos: un modelo colgado se abandona a los 45 s,
    # pero una respuesta larga que sigue llegando puede tardar lo que necesite.
    espera = Timeout(45, connect=15, write=60) if streaming else 150
    return OpenAI(api_key=clave, base_url=PROVEEDORES[proveedor]["base_url"], max_retries=0, timeout=espera)


_cache_modelos = {}  # (proveedor, clave) -> (instante, lista)


def modelos_disponibles(proveedor, clave):
    """Modelos de texto del proveedor (se guardan una hora); el predeterminado queda primero."""
    guardado = _cache_modelos.get((proveedor, clave))
    if guardado and time.time() - guardado[0] < 3600:
        return guardado[1]
    lista = _listar_modelos(proveedor, clave)
    _cache_modelos[(proveedor, clave)] = (time.time(), lista)
    return lista


def _listar_modelos(proveedor, clave):
    ids = [m.id.removeprefix("models/") for m in cliente(proveedor, clave).models.list().data]
    excluir = ("whisper", "guard", "orpheus", "safeguard", "embedding", "tts", "image", "audio", "aqa", "veo", "imagen",
               "live", "banana", "transcribe", "robotics", "computer-use", "customtools", "streaming")
    ids = [i for i in ids if not any(x in i.lower() for x in excluir)]
    if proveedor == "OpenRouter":
        ids = [i for i in ids if i.endswith(":free")]
    if proveedor == "Gemini (Google)":
        ids = [i for i in ids if i.startswith("gemini")]
    predeterminado = PROVEEDORES[proveedor]["modelo"]

    def version(i):
        m = re.search(r"(\d+(?:\.\d+)?)", i)
        return float(m.group(1)) if m else 0.0

    if proveedor == "Gemini (Google)":
        # Primero el "gemini-X.Y-flash" estable más nuevo (rápido y con buen límite gratuito)
        ids = sorted(set(ids), key=lambda i: (not re.fullmatch(r"gemini-[\d.]+-flash", i), -version(i), i))
    else:
        # Más nuevo primero; luego se prefieren el predeterminado y los modelos estables / grandes
        ids = sorted(set(ids), reverse=True)
        ids.sort(key=lambda i: (i != predeterminado, "pro" in i or "lite" in i, "preview" in i or "exp" in i))
    return ids


def modelo_para(proveedor, clave):
    """Modelo a usar cuando el proveedor entra como respaldo."""
    try:
        return (modelos_disponibles(proveedor, clave) or [PROVEEDORES[proveedor]["modelo"]])[0]
    except Exception:
        return PROVEEDORES[proveedor]["modelo"]


def config():
    """Configuración vigente: {proveedor, modelo, respaldo, claves}. Si no se eligió proveedor, usa el primero con clave."""
    guardada = _leer_json(_ruta_config())
    claves = {n: clave_guardada(i["secreto"]) for n, i in PROVEEDORES.items()}
    proveedor = guardada.get("proveedor")
    if not claves.get(proveedor):
        proveedor = next((n for n in PROVEEDORES if claves[n]), None)
        guardada = {}
    return {"proveedor": proveedor, "modelo": guardada.get("modelo"), "respaldo": guardada.get("respaldo", True),
            "claves": claves}


def proveedor_actual_tiene_vision():
    return PROVEEDORES.get(config().get("proveedor") or "", {}).get("vision", False)


def es_error_de_limite(error):
    texto = str(error).lower()
    codigo = getattr(error, "status_code", None)
    return codigo in (413, 429) or any(x in texto for x in (
        "rate_limit", "rate limit", "quota", "resource_exhausted", "too large", "tokens per", "requests per"))


def _orden_de_intento():
    cfg = config()
    principal = cfg.get("proveedor")
    claves = cfg.get("claves", {})
    orden = [principal] if claves.get(principal) else []
    if cfg.get("respaldo", True):
        orden += [p for p in PROVEEDORES if p != principal and claves.get(p)]
    return orden


def hay_proveedor():
    return bool(_orden_de_intento())


# Modelos que fallaron hace poco: no se reintentan hasta que pase este tiempo (segundos)
_BLOQUEO_POR_CODIGO = {503: 120, 429: 600, 404: 86400, 400: 86400}
_bloqueados = {}  # (proveedor, modelo) -> instante hasta el que no se intenta


def _bloquear(proveedor, modelo, error):
    codigo = getattr(error, "status_code", None)
    if codigo is None and "timed out" in str(error).lower():
        codigo = 503  # sin respuesta en el tiempo de espera: se trata como saturado
    segundos = _BLOQUEO_POR_CODIGO.get(codigo)
    if segundos:
        _bloqueados[(proveedor, modelo)] = time.time() + segundos


def _prioridad_respaldo(modelo):
    """Orden para probar modelos del mismo proveedor: flash estables, otros flash/preview, lite, y el resto."""
    m = modelo.lower()
    if any(x in m for x in ("pro", "argon", "omni")):
        return 9  # sin cuota en el plan gratuito: no se usan como respaldo
    if re.fullmatch(r"gemini-[\d.]+-flash", m) or m == "gemini-flash-latest":
        return 0
    if "flash" in m and "lite" not in m:
        return 1
    if "lite" in m:
        return 2
    return 3


def _modelos_a_probar(proveedor, clave):
    """El modelo elegido (o el mejor disponible) y, si falla o está saturado, los demás útiles del mismo proveedor,
    saltando los que fallaron hace poco."""
    cfg = config()
    try:
        disponibles = modelos_disponibles(proveedor, clave)
    except Exception:
        disponibles = []
    primero = cfg["modelo"] if proveedor == cfg.get("proveedor") and cfg.get("modelo") else (
        disponibles[0] if disponibles else PROVEEDORES[proveedor]["modelo"])
    otros = sorted((m for m in disponibles if m != primero and _prioridad_respaldo(m) < 9),
                   key=lambda m: (_prioridad_respaldo(m), disponibles.index(m)))
    ahora = time.time()
    lista = [m for m in [primero] + otros if _bloqueados.get((proveedor, m), 0) <= ahora]
    return lista[:8] or [primero]


def _motivo(error):
    codigo = getattr(error, "status_code", None)
    if es_error_de_limite(error):
        return "llegó a su límite"
    if codigo == 503 or "high demand" in str(error).lower():
        return "está saturado en este momento"
    if "timed out" in str(error).lower():
        return "no respondió a tiempo"
    if codigo == 404:
        return "ya no está disponible"
    if codigo in (401, 403):
        return "rechazó la clave"
    return f"falló ({str(error)[:100]})"


def completar(construir_mensajes, max_tokens, temperature=0.2, json=False, razonamiento_bajo=False):
    """
    Llama al proveedor principal y, si llega a su límite (o falla), al siguiente con clave.
    construir_mensajes(info_proveedor) -> lista de mensajes (permite ajustar el material y las imágenes a cada proveedor).
    Devuelve (texto, proveedor_usado, finish_reason, avisos).
    """
    cfg = config()
    avisos, ultimo_error = [], None
    for proveedor in _orden_de_intento():
        info = PROVEEDORES[proveedor]
        clave = cfg["claves"][proveedor]
        for modelo in _modelos_a_probar(proveedor, clave):
            extra = {}
            if json:
                extra["response_format"] = {"type": "json_object"}
            if info["razonamiento"] is True:
                # Gemini: el razonamiento descuenta del largo de la respuesta; "low" deja espacio para la clase completa
                extra["reasoning_effort"] = "low"
            elif info["razonamiento"] == "gpt-oss" and "gpt-oss" in modelo:
                extra["reasoning_effort"] = "low" if razonamiento_bajo else "medium"
            # Groq no admite streaming con el modo JSON; en el resto se usa streaming (detecta modelos colgados)
            streaming = not (json and proveedor == "Groq")
            try:
                crear = cliente(proveedor, clave, streaming).chat.completions.create
                argumentos = dict(model=modelo, messages=construir_mensajes(info), temperature=temperature,
                                  max_tokens=max_tokens, **extra)
                if streaming:
                    partes, fin = [], None
                    for trozo in crear(stream=True, **argumentos):
                        if trozo.choices:
                            if trozo.choices[0].delta and trozo.choices[0].delta.content:
                                partes.append(trozo.choices[0].delta.content)
                            fin = trozo.choices[0].finish_reason or fin
                    texto = "".join(partes)
                else:
                    res = crear(**argumentos)
                    texto, fin = res.choices[0].message.content or "", res.choices[0].finish_reason
                if not texto.strip():
                    raise RuntimeError("respuesta vacía")
                return texto, f"{proveedor} · {modelo}", fin, avisos
            except Exception as e:
                ultimo_error = e
                # Groq rechaza a veces el JSON mal formado pero entrega lo generado: se devuelve para repararlo
                cuerpo = getattr(e, "body", None)
                if json and isinstance(cuerpo, dict):
                    generado = (cuerpo.get("error") or cuerpo).get("failed_generation")
                    if generado:
                        return generado, f"{proveedor} · {modelo}", "stop", avisos
                _bloquear(proveedor, modelo, e)
                avisos.append(f"{proveedor} · {modelo} {_motivo(e)}; se intentó con otra opción.")
                if getattr(e, "status_code", None) in (401, 403):
                    break  # clave inválida: no sirve probar otros modelos de este proveedor
    if ultimo_error is None:
        raise RuntimeError("No hay ninguna clave de IA configurada: agrégala en «Claves de IA».")
    if es_error_de_limite(ultimo_error):
        raise RuntimeError("Todos los proveedores configurados llegaron a su límite. Espera un minuto (o hasta mañana "
                           "si es el límite diario) o agrega otra clave en «Claves de IA».") from ultimo_error
    raise ultimo_error

