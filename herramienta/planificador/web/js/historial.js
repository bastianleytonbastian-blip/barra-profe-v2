// Página «Historial»: las clases guardadas y las creadas en WebClass, en una sola lista con búsqueda y filtro por curso.
import { api } from "./api.js";
import { compartido, estadoBarra, hayBarra } from "./estado.js";
import { etiquetaNivel, filtrarHistorial, nivelesDelHistorial } from "./logica.js";
import { abrirEnPlanificador, enlaceClase } from "./planificar.js";
import { $, $$, aviso, cargando, confirmar, esc, hoyISO } from "./util.js";

let items = [];        // lo que entrega /api/historial/todo
let conBarra = false;  // con Barra se puede comprobar y eliminar en WebClass
const existe = {};     // idclase -> true/false, después de «Comprobar en WebClass»

const cuenta = () => compartido.cuenta?.clave || "";
const fechaCorta = (iso) => {
  const [dia, hora = ""] = String(iso || "").split("T");
  return `${dia.split("-").reverse().join("/")} ${hora.slice(0, 5)}`.trim();
};

export async function montarHistorial(cont) {
  cont.innerHTML = `
    <header class="cabecera"><h1>Historial</h1>
      <p>Tus clases guardadas y las que creaste en WebClass, de la más reciente a la más antigua. Ábrelas para seguir
      editándolas o duplícalas para otra fecha o curso.</p></header>
    <section class="tarjeta">
      <div class="filtros" role="search">
        <input type="search" id="h-buscar" placeholder="Buscar por nombre, tema, curso o unidad…" aria-label="Buscar en el historial">
        <select id="h-nivel" aria-label="Filtrar por curso"><option value="">Todos los cursos</option></select>
        <button class="btn chico" id="h-comprobar" type="button" hidden>Comprobar en WebClass</button>
      </div>
      <p class="ayuda" id="h-estado" aria-live="polite"></p>
      <div id="h-lista">${cargando("Cargando el historial…")}</div></section>`;
  $("#h-buscar").oninput = pintar;
  $("#h-nivel").onchange = pintar;
  $("#h-comprobar").onclick = comprobar;
  conBarra = hayBarra(await estadoBarra());
  await cargar();
}

async function cargar() {
  items = (await api.get("/api/historial/todo")).items;
  const nivel = $("#h-nivel").value;
  $("#h-nivel").innerHTML = `<option value="">Todos los cursos</option>`
    + nivelesDelHistorial(items).map((n) => `<option value="${n}" ${n === nivel ? "selected" : ""}>${etiquetaNivel(n)}</option>`).join("");
  $("#h-comprobar").hidden = !(conBarra && items.some((it) => it.webclass.some((w) => !w.eliminada)));
  pintar();
}

function pintar() {
  const caja = $("#h-lista");
  if (!caja) return;
  if (!items.length) {
    caja.innerHTML = `<p class="vacio">Todavía no hay clases. Las que guardes o envíes a WebClass desde
      <a href="#/planificar">Planificar una clase</a> aparecerán aquí.</p>`;
    return;
  }
  const lista = filtrarHistorial(items, { texto: $("#h-buscar").value, nivel: $("#h-nivel").value });
  if (!lista.length) { caja.innerHTML = `<p class="vacio">Nada coincide con la búsqueda.</p>`; return; }
  caja.innerHTML = lista.map((it) => {
    const i = items.indexOf(it);
    const detalle = [it.asignatura, it.curso, it.fecha_clase && `clase del ${it.fecha_clase}`,
      it.fecha && `${it.archivo ? "guardada" : "creada"} el ${fechaCorta(it.fecha)}`].filter(Boolean).join(" · ");
    const enlaces = it.webclass.map((w, j) => {
      const vive = w.eliminada ? false : existe[w.idclase];
      return `<span class="etiqueta-wc">${esc(w.curso || "WebClass")}${w.unidad ? ` · ${esc(w.unidad)}` : ""}
        ${vive === true ? '<span class="estado si">✓ existe</span>' : ""}
        ${vive === false ? `<span class="estado no">✕ ${w.eliminada ? "eliminada" : "ya no existe"}</span>` : ""}
        ${vive === false ? "" : `<a class="btn chico" target="_blank" rel="noopener" href="${enlaceClase(w.id_unidad, w.idclase)}">Ver en WebClass</a>`}
        ${conBarra && vive !== false ? `<button class="btn chico peligro" type="button" data-eliminar-wc="${i}:${j}">Eliminar…</button>` : ""}</span>`;
    }).join("");
    return `<article class="item-historial">
      <div class="titulo"><b>${esc(it.nombre)}</b><small>${esc(detalle)}</small></div>
      ${enlaces ? `<div class="enlaces-wc">${enlaces}</div>` : ""}
      <div class="barra">${it.archivo ? `
        <button class="btn chico primario" type="button" data-abrir="${i}">Abrir</button>
        <button class="btn chico" type="button" data-duplicar="${i}">Duplicar para otra fecha o curso</button>
        <button class="btn chico peligro" type="button" data-quitar="${i}">Quitar del historial</button>`
        : `<span class="ayuda">Creada antes de que el planificador guardara cada clase enviada: su contenido está en WebClass.</span>`}</div>
    </article>`;
  }).join("");
  $$("[data-abrir]", caja).forEach((b) => (b.onclick = () => abrir(items[Number(b.dataset.abrir)], false)));
  $$("[data-duplicar]", caja).forEach((b) => (b.onclick = () => abrir(items[Number(b.dataset.duplicar)], true)));
  $$("[data-quitar]", caja).forEach((b) => (b.onclick = () => quitar(items[Number(b.dataset.quitar)])));
  $$("[data-eliminar-wc]", caja).forEach((b) => (b.onclick = () => {
    const [i, j] = b.dataset.eliminarWc.split(":").map(Number);
    eliminarDeWebclass(items[i], items[i].webclass[j]);
  }));
}

/** Abre la clase en «Planificar una clase»; la copia parte con la fecha de hoy y sin enlaces a WebClass. */
async function abrir(it, duplicar) {
  try {
    const { guardado, ...clase } = await api.get(`/api/historial/clase/${encodeURIComponent(it.archivo)}`);
    if (!duplicar) { abrirEnPlanificador(clase); return; }
    const { archivo_historial, webclass, ...copia } = clase;
    abrirEnPlanificador({ ...copia, fecha: hoyISO() }, { pestana: "webclass", copia: true });
  } catch (e) { aviso(e.message, "error"); }
}

async function quitar(it) {
  const si = await confirmar({ titulo: `¿Quitar «${it.nombre}» del historial?`, si: "Quitar del historial", peligro: true,
    texto: it.webclass.some((w) => !w.eliminada) ? "Solo se borra de este historial: la clase sigue en WebClass." : "Se borra la clase guardada en este equipo." });
  if (!si) return;
  try {
    await api.borrar(`/api/historial/${encodeURIComponent(it.archivo)}`);
    aviso("Quitada del historial.");
    await cargar();
  } catch (e) { aviso(e.message, "error"); }
}

/** Deshacer: elimina en WebClass una clase que creó el planificador (Barra rechaza cualquier otra). */
async function eliminarDeWebclass(it, w) {
  const si = await confirmar({ titulo: `¿Eliminar «${it.nombre}» de WebClass?`, si: "Sí, eliminar de WebClass", peligro: true,
    texto: `${[w.curso, w.unidad, w.fecha_clase && `clase del ${w.fecha_clase}`].filter(Boolean).join(" · ")}. No se puede deshacer. `
      + "Los archivos que subiste al banco de recursos se conservan." });
  if (!si) return;
  $("#h-estado").textContent = "Eliminando en WebClass…";
  try {
    const r = await api.post("/api/registro/eliminar", { cuenta: cuenta(), clases: [{ id_unidad: w.id_unidad, idclase: w.idclase }] });
    const x = r.resultados[0];
    if (x.estado === "eliminada" || x.estado === "ya") {
      existe[w.idclase] = false;
      aviso(x.estado === "ya" ? "La clase ya no existía en WebClass." : "Clase eliminada de WebClass.");
      if (it.archivo) await marcarEliminada(it.archivo, w.idclase);
    } else {
      aviso(`No se eliminó: ${x.motivo || x.estado}`, "error");
    }
  } catch (e) { aviso(e.message, "error"); }
  $("#h-estado").textContent = "";
  await cargar();
}

/** La clase guardada recuerda que su copia en WebClass ya no está (así el historial no la ofrece de nuevo). */
async function marcarEliminada(archivo, idclase) {
  try {
    const clase = await api.get(`/api/historial/clase/${encodeURIComponent(archivo)}`);
    clase.webclass = (clase.webclass || []).map((x) => (String(x.idclase) === String(idclase) ? { ...x, eliminada: true } : x));
    await api.post("/api/historial", clase);
  } catch { /* el aviso de WebClass ya se mostró */ }
}

/** Solo lectura en WebClass: cuáles de estas clases siguen existiendo. */
async function comprobar() {
  const clases = items.flatMap((it) => it.webclass).filter((w) => !w.eliminada).map((w) => ({ id_unidad: w.id_unidad, idclase: w.idclase }));
  if (!clases.length) return;
  const boton = $("#h-comprobar");
  boton.disabled = true;
  $("#h-estado").textContent = "Consultando WebClass (solo lectura)…";
  try {
    const r = await api.post("/api/registro/comprobar", { cuenta: cuenta(), clases });
    Object.assign(existe, r.existen);
    const faltan = Object.values(r.existen).filter((v) => v === false).length;
    $("#h-estado").textContent = faltan ? `${faltan} clase(s) ya no están en WebClass.` : "Todas siguen en WebClass.";
  } catch (e) { $("#h-estado").textContent = e.message; }
  boton.disabled = false;
  pintar();
}
