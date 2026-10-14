// Estado compartido entre páginas: perfil del docente y estado de la IA.
import { api } from "./api.js";
import { $ } from "./util.js";

export const compartido = { perfil: null, ia: null, cuenta: null };

/** Etiqueta de la cuenta de Barra con la que se está trabajando. */
export const etiquetaCuenta = () => {
  const c = compartido.cuenta;
  if (!c) return "";
  const nombre = c.nombre || compartido.perfil?.nombre_docente || "";
  return c.en_barra ? `${nombre || c.clave} · cuenta ${c.clave}` : nombre;
};

export async function recargarPerfil() {
  compartido.perfil = await api.get("/api/perfil");
  compartido.cuenta = compartido.perfil.cuenta;
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
