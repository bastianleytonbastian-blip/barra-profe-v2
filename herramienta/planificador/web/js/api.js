// Cliente de la API local. Todas las llamadas devuelven JSON (o Blob) y lanzan Error con un mensaje legible.

const token = () => document.querySelector('meta[name="planificador-token"]')?.content || "";

async function pedir(ruta, opciones = {}) {
  let resp;
  try {
    // Toda escritura lleva el token de esta sesión (el servidor rechaza las que no lo traen)
    if ((opciones.method || "GET").toUpperCase() !== "GET") {
      opciones = { ...opciones, headers: { ...(opciones.headers || {}), "X-Planificador-Token": token() } };
    }
    resp = await fetch(ruta, opciones);
  } catch {
    throw new Error("No se pudo conectar con el planificador. ¿Sigue abierta la ventana del servidor?");
  }
  if (!resp.ok) {
    let mensaje = resp.status === 405 ? "Esta página quedó desactualizada. Recárgala con Ctrl+F5 y vuelve a intentar." : `Error ${resp.status}`;
    if (resp.status === 401) mensaje = "El planificador se reinició o esta página quedó vieja. Recárgala (F5) y vuelve a intentar.";
    try { const d = await resp.json(); mensaje = d.error || d.detail || mensaje; } catch { /* sin cuerpo JSON */ }
    throw new Error(typeof mensaje === "string" ? mensaje : JSON.stringify(mensaje));
  }
  return resp;
}

const json = (cuerpo, metodo = "POST") => ({ method: metodo, headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });

export const api = {
  get: async (ruta) => (await pedir(ruta)).json(),
  post: async (ruta, cuerpo) => (await pedir(ruta, json(cuerpo))).json(),
  put: async (ruta, cuerpo) => (await pedir(ruta, json(cuerpo, "PUT"))).json(),
  borrar: async (ruta) => (await pedir(ruta, { method: "DELETE" })).json(),
  /** Formulario con archivos: campos simples + {archivos: File[], archivo: File, ...} */
  form: async (ruta, datos, archivos = {}) => {
    const f = new FormData();
    f.append("datos", JSON.stringify(datos));
    for (const [campo, valor] of Object.entries(archivos)) {
      (Array.isArray(valor) ? valor : [valor]).filter(Boolean).forEach((a) => f.append(campo, a));
    }
    return (await pedir(ruta, { method: "POST", body: f })).json();
  },
  /** Solo archivos (sin campo de datos) */
  subir: async (ruta, campo, archivos) => {
    const f = new FormData();
    archivos.forEach((a) => f.append(campo, a));
    return (await pedir(ruta, { method: "POST", body: f })).json();
  },
  blob: async (ruta, cuerpo) => (await pedir(ruta, json(cuerpo))).blob(),
};
