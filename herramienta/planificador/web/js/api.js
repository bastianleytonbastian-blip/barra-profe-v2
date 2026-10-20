// Cliente de la API local. Todas las llamadas devuelven JSON (o Blob) y lanzan Error con un mensaje legible.

const token = () => document.querySelector('meta[name="planificador-token"]')?.content || "";
let caido = false;   // el servidor dejó de responder (se avisa una vez con «servidor-caido» y al volver con «servidor-vuelve»)

async function pedir(ruta, opciones = {}) {
  let resp;
  try {
    // Toda escritura lleva el token de esta sesión (el servidor rechaza las que no lo traen)
    if ((opciones.method || "GET").toUpperCase() !== "GET") {
      opciones = { ...opciones, headers: { ...(opciones.headers || {}), "X-Planificador-Token": token() } };
    }
    resp = await fetch(ruta, opciones);
  } catch {
    if (!caido) { caido = true; document.dispatchEvent(new CustomEvent("servidor-caido")); }
    throw new Error("No se pudo conectar con el planificador. Ábrelo de nuevo desde la barra (botón «Planificar»).");
  }
  if (caido) { caido = false; document.dispatchEvent(new CustomEvent("servidor-vuelve")); }
  if (!resp.ok) {
    let mensaje = resp.status === 405 ? "Esta página quedó desactualizada. Recárgala con Ctrl+F5 y vuelve a intentar." : `Error ${resp.status}`;
    if (resp.status === 401) mensaje = "El planificador se reinició o esta página quedó vieja. Recárgala (F5) y vuelve a intentar.";
    try { const d = await resp.json(); mensaje = d.error || d.detail || mensaje; } catch { /* sin cuerpo JSON */ }
    throw Object.assign(new Error(typeof mensaje === "string" ? mensaje : JSON.stringify(mensaje)), { estado: resp.status });
  }
  return resp;
}

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

/** Sigue un trabajo largo del servidor: avisa cada avance con alAvanzar(tipo, datos) y termina con su resultado.
 * En vivo (EventSource); si esa conexión falla seguido, pregunta por el resultado cada segundo. */
function seguir(id, alAvanzar) {
  return new Promise((resolver, rechazar) => {
    let terminado = false;
    const consultar = async () => {
      try {
        for (;;) {
          const r = await (await pedir(`/api/trabajos/${id}/resultado`)).json();
          if (r.estado === "listo") { resolver(r.resultado); return; }
          if (r.estado === "error") { rechazar(new Error(r.error)); return; }
          if (r.etapa) alAvanzar("etapa", r.etapa);
          await esperar(1000);
        }
      } catch (e) { rechazar(e); }
    };
    if (!window.EventSource) { consultar(); return; }
    const fuente = new EventSource(`/api/trabajos/${id}`);
    let cortes = 0;
    const terminar = () => { terminado = true; fuente.close(); };
    for (const tipo of ["etapa", "intento", "trozo"]) {
      fuente.addEventListener(tipo, (ev) => { cortes = 0; alAvanzar(tipo, JSON.parse(ev.data)); });
    }
    fuente.addEventListener("fin", (ev) => { terminar(); resolver(JSON.parse(ev.data)); });
    fuente.addEventListener("falla", (ev) => { terminar(); rechazar(new Error(JSON.parse(ev.data).error)); });
    fuente.onerror = () => {   // corte de la conexión: EventSource reintenta sola; si sigue fallando, se pregunta a mano
      if (terminado) return;
      if (++cortes >= 3 || fuente.readyState === EventSource.CLOSED) { terminar(); consultar(); }
    };
  });
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
  seguir,
};
