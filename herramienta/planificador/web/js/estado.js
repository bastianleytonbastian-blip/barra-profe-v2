// Estado compartido entre páginas: perfil del docente, estado de la IA y de Barra Profe.
import { api } from "./api.js";
import { $, guardarLocal, leerLocal } from "./util.js";

// barra: si hay Barra Profe para trabajar con WebClass · unidades: las de la cuenta en Barra (se piden una vez por cuenta)
export const compartido = { perfil: null, ia: null, cuenta: null, barra: null, unidades: null };

export const hayBarra = (estado) => !!(estado?.valida && estado.compatible !== false);

/** ¿Se puede trabajar con WebClass a través de Barra? (lo que entrega /api/barra/estado) */
export async function estadoBarra() {
  if (!compartido.barra) {
    try { compartido.barra = await api.get("/api/barra/estado"); } catch { return { valida: false, compatible: false, mensaje: "" }; }
  }
  return compartido.barra;
}

/** Unidades de la cuenta según Barra (no entra a WebClass). [] si no hay Barra o no se pudieron leer. */
export async function unidadesDeBarra() {
  if (compartido.unidades) return compartido.unidades;
  if (!hayBarra(await estadoBarra())) return [];
  try {
    compartido.unidades = (await api.post("/api/barra/unidades", { cuenta: compartido.cuenta?.clave || "" })).unidades || [];
  } catch { return []; }
  guardarLocal(`unidades:${compartido.cuenta?.clave || ""}`, compartido.unidades);
  return compartido.unidades;
}

/** Las unidades de la última vez (al tiro, sin esperar a Barra): así la pantalla parte ya con el curso correcto. */
export const unidadesRecordadas = () => compartido.unidades || leerLocal(`unidades:${compartido.cuenta?.clave || ""}`, []);

/** Olvida lo que se sabía de Barra (al cambiar de cuenta o de carpeta de Barra). */
export const olvidarBarra = () => { compartido.barra = null; compartido.unidades = null; };

/** Etiqueta de la cuenta de Barra con la que se está trabajando. */
export const etiquetaCuenta = () => {
  const c = compartido.cuenta;
  if (!c) return "";
  const nombre = c.nombre || compartido.perfil?.nombre_docente || "";
  return c.en_barra ? `${nombre || c.clave} · cuenta ${c.clave}` : nombre;
};

export async function recargarPerfil() {
  const antes = compartido.cuenta?.clave;
  compartido.perfil = await api.get("/api/perfil");
  compartido.cuenta = compartido.perfil.cuenta;
  if (antes && antes !== compartido.cuenta?.clave) olvidarBarra();
  $("#docente-nombre").textContent = etiquetaCuenta();
  return compartido.perfil;
}

export async function recargarIA() {
  try {
    compartido.ia = await api.get("/api/ia/estado");
  } catch {
    compartido.ia = { lista: false, proveedores: {} };
  }
  const ia = compartido.ia;
  $("#punto-ia").className = "punto " + (ia.lista ? "ok" : "mal");
  $("#texto-ia").textContent = ia.lista ? `IA lista · ${(ia.proveedor || "").split(" ")[0]}` : "Conectar la IA";
  return ia;
}
