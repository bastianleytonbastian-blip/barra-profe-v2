// Apariencia: claro, oscuro o como el sistema, y el color que la cuenta eligió en la barra (Mi perfil → Preferencias).
import { api } from "./api.js";
import { textoSobre } from "./logica.js";
import { guardarLocal } from "./util.js";

const VARIABLES = ["--marca-claro", "--marca-oscuro", "--marca-sobre-claro", "--marca-sobre-oscuro"];

/** Aplica lo que entrega /api/tema ({tema, color_barra, claro, oscuro}) y lo recuerda para pintar igual la próxima carga. */
export function aplicarTema(t = {}) {
  const raiz = document.documentElement;
  if (t.tema === "claro" || t.tema === "oscuro") raiz.dataset.tema = t.tema;
  else delete raiz.dataset.tema;
  const vars = t.color_barra && t.claro && t.oscuro
    ? { "--marca-claro": t.claro, "--marca-oscuro": t.oscuro, "--marca-sobre-claro": textoSobre(t.claro), "--marca-sobre-oscuro": textoSobre(t.oscuro) }
    : {};
  VARIABLES.forEach((v) => (vars[v] ? raiz.style.setProperty(v, vars[v]) : raiz.style.removeProperty(v)));
  guardarLocal("planificador_tema", { tema: t.tema || "sistema", vars });
}

export async function cargarTema() {
  try { aplicarTema(await api.get("/api/tema")); } catch { /* sin servidor: queda el último */ }
}
