// Utilidades compartidas: escape de HTML, avisos, descargas, portapapeles y almacenamiento local.

export const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const $ = (sel, raiz = document) => raiz.querySelector(sel);
export const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

export function aviso(texto, tipo = "ok", ms = 4500) {
  const caja = document.getElementById("avisos");
  const el = document.createElement("div");
  el.className = "toast" + (tipo === "error" ? " error" : "");
  el.textContent = texto;
  caja.appendChild(el);
  setTimeout(() => el.remove(), tipo === "error" ? Math.max(ms, 9000) : ms);
}

export function descargar(blob, nombre) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: nombre });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export async function copiar(texto) {
  try {
    await navigator.clipboard.writeText(texto);
    return true;
  } catch {
    const t = Object.assign(document.createElement("textarea"), { value: texto });
    document.body.appendChild(t);
    t.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { /* sin permiso */ }
    t.remove();
    return ok;
  }
}

export const guardarLocal = (clave, valor) => { try { localStorage.setItem(clave, JSON.stringify(valor)); } catch { /* modo privado */ } };
export const leerLocal = (clave, defecto = null) => { try { return JSON.parse(localStorage.getItem(clave)) ?? defecto; } catch { return defecto; } };

// "2026-10-14" -> "14/10/2026"
export const fechaChilena = (iso) => (iso ? iso.split("-").reverse().join("/") : "");
export const hoyISO = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

export function cargando(texto) {
  return `<div class="nota cargando" role="status"><span class="rueda"></span><span>${esc(texto)}</span></div>`;
}

export function autoajustar(ta) {
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight + 4, 900) + "px";
}

const ICONOS = {
  plan: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  pie: '<rect x="3" y="3" width="8" height="8" rx="2"/><rect x="13" y="3" width="8" height="8" rx="2"/><rect x="3" y="13" width="8" height="8" rx="2"/><path d="M17 13v8M13 17h8"/>',
  subir: '<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>',
  perfil: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
};
export function pintarIconos(raiz = document) {
  $$(".ico[data-ico]", raiz).forEach((el) => { el.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONOS[el.dataset.ico] || ""}</svg>`; });
}
