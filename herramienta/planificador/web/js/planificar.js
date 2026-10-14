// Página «Planificar una clase»: formulario en 3 pasos, resultado editable y exportación.
import { api } from "./api.js";
import { compartido } from "./estado.js";
import { claveCurso, hermanas, sinTildes, sugerirOA } from "./logica.js";

const cuentaActual = () => compartido.cuenta?.clave || "";
import { $, $$, aviso, autoajustar, cargando, copiar, descargar, esc, fechaChilena, guardarLocal, hoyISO, leerLocal } from "./util.js";

const BORRADOR = () => `plan_borrador:${cuentaActual()}`;   // el borrador es de la cuenta de Barra que lo escribió
const CAMPOS = ["inicio", "desarrollo", "cierre", "evaluacion", "recursos", "adecuaciones", "motivacion"];
let plan = null;       // planificación en pantalla
let constantes = null; // pautas DUA, tipos de clase…
let oaCurso = [];      // OA oficiales del curso de la planificación
let archivosMaterial = []; // archivos que se subieron como material (se pueden adjuntar a la clase en WebClass)
let unidadBarra = null; // unidad elegida en Barra Profe (llega por el enlace: #/planificar?unidad=ID)

export async function montarPlanificar(cont) {
  constantes = constantes || (await api.get("/api/webclass/constantes"));
  const { asignaturas, hay } = await api.get("/api/curriculo/asignaturas");
  const perfil = compartido.perfil || {};
  plan = leerLocal(BORRADOR());
  if (plan && !plan.hora) plan.hora = HORA_POR_DEFECTO;
  unidadBarra = null;

  cont.innerHTML = `
    <div id="nota-unidad"></div>
    <header class="cabecera"><h1>Planificar una clase</h1>
      <p>Cuéntale a la IA qué vas a enseñar y obtén Inicio, Desarrollo y Cierre listos para revisar y subir a WebClass.</p></header>
    ${perfil.completo ? "" : `<div class="nota info">Completa <a href="#/perfil">Mi perfil</a> (tu nombre y el colegio) para personalizar los textos y documentos.</div>`}
    ${hay ? "" : `<div class="nota aviso">No hay currículo descargado, así que no habrá lista de OA. Descárgalo desde <a href="#/perfil">Mi perfil</a>.</div>`}
    <section class="tarjeta" aria-labelledby="t1"><h2 id="t1"><span class="paso">1</span>¿Qué vas a enseñar?</h2>
      <p class="sub">Elige la asignatura y el curso, y escribe el tema.</p>
      <div class="rejilla">
        <div class="campo"><label for="f-asig">Asignatura</label>
          <select id="f-asig">${asignaturas.map((a) => `<option>${esc(a)}</option>`).join("")}<option value="__otra">+ Otra / personalizada</option></select>
          <input type="text" id="f-asig-otra" placeholder="Nombre de la asignatura" hidden></div>
        <div class="campo"><label for="f-curso">Curso</label><select id="f-curso"></select>
          <input type="text" id="f-curso-otro" placeholder="Nombre del curso" hidden></div>
        <div class="campo ancho"><label for="f-tema">Tema o contenido de la clase</label>
          <textarea id="f-tema" placeholder="Ej: Las fracciones equivalentes · La Revolución Industrial · El ciclo del agua…"></textarea></div>
        <div class="campo ancho"><label for="f-indic">Indicaciones propias <span class="ayuda">(opcional)</span></label>
          <textarea id="f-indic" placeholder="Ej: Objetivo: … / Actividad: … / Trabajar la fuente de la página 32"></textarea>
          <span class="ayuda">Si escribes «Objetivo:» o «Actividad:», la planificación usa exactamente lo que pongas.</span></div>
        <div class="campo"><label for="f-duracion">Duración de la clase (minutos)</label>
          <input type="number" id="f-duracion" min="30" max="240" step="5" value="${perfil.duracion_defecto || 90}"></div>
        <div class="campo" id="extras-curso"></div>
      </div></section>
    <section class="tarjeta" aria-labelledby="t2"><h2 id="t2"><span class="paso">2</span>Material de apoyo <span class="ayuda">(opcional)</span></h2>
      <details class="plegable"><summary>Subir archivos, enlaces o video</summary>
        <div class="rejilla">
          <div class="campo"><label for="f-archivos">Guías, presentaciones, imágenes, audio o video (PDF, Word, PowerPoint, TXT, JPG, PNG, MP3, WAV o MP4)</label><input type="file" id="f-archivos" multiple accept=".pdf,.docx,.pptx,.txt,.jpg,.jpeg,.png,.mp3,.wav,.mp4">
            <span class="ayuda">La IA lee el texto de los documentos; las imágenes no se leen, pero se pueden adjuntar a la clase en WebClass.</span></div>
          <div class="campo"><label for="f-video">Video de YouTube</label><input type="text" id="f-video" placeholder="https://www.youtube.com/watch?v=…"></div>
          <div class="campo"><label for="f-canva">Enlace de Canva</label><input type="text" id="f-canva" placeholder="https://www.canva.com/design/…"></div>
          <div class="campo"><label for="f-guia">Guía PIE de esta clase</label><input type="file" id="f-guia" accept=".html,.pdf,.docx">
            <span class="ayuda">Su objetivo pasa a ser el «Objetivo adaptado» y sus actividades se describen en «Actividad».</span></div>
        </div></details></section>
    <section class="tarjeta" aria-labelledby="t3"><h2 id="t3"><span class="paso">3</span>Generar y revisar</h2>
      <div class="barra espaciada"><button class="btn primario grande" id="generar" type="button">✨ Generar planificación</button>
        <span class="ayuda" id="estado-generar"></span></div></section>
    <div id="resultado"></div>
    <div id="historial"></div>
    <div id="creadas"></div>`;

  const selAsig = $("#f-asig"), selCurso = $("#f-curso");
  async function cargarCursos() {
    const otra = selAsig.value === "__otra";
    $("#f-asig-otra").hidden = !otra;
    let cursos = [];
    if (!otra) cursos = (await api.get(`/api/curriculo/cursos?asignatura=${encodeURIComponent(selAsig.value)}`)).cursos;
    selCurso.innerHTML = cursos.map((c) => `<option>${esc(c)}</option>`).join("") + `<option value="__otro">+ Otro / personalizado</option>`;
    actualizarCurso();
  }
  function actualizarCurso() {
    $("#f-curso-otro").hidden = selCurso.value !== "__otro";
    const extras = (perfil.actividades_extra || []).filter((e) => e.curso && selCurso.value.includes(e.curso));
    $("#extras-curso").innerHTML = extras.length
      ? `<span class="etiqueta">Actividades especiales</span>` + extras.map((e, i) => `
          <label class="casilla"><input type="checkbox" data-extra="${i}"><span>Incluir «${esc(e.nombre)}» (${e.minutos} min)</span></label>`).join("")
      : "";
  }
  selAsig.onchange = cargarCursos;
  selCurso.onchange = actualizarCurso;
  await cargarCursos();
  const idUnidad = new URLSearchParams(location.hash.split("?")[1] || "").get("unidad");
  if (idUnidad) await preseleccionarUnidad(idUnidad, selAsig, selCurso, cargarCursos);

  $("#generar").onclick = () => generar(extrasElegido(perfil));
  await pintarResultado();
  const pestana = new URLSearchParams(location.hash.split("?")[1] || "").get("tab");
  if (pestana && plan) activarPestana(pestana);
  pintarHistorial();
  pintarCreadas();
}

/** Llegó desde Barra Profe con una unidad: se eligen su asignatura y su curso. */
async function preseleccionarUnidad(id, selAsig, selCurso, cargarCursos) {
  try {
    const r = await api.post("/api/barra/unidades", { cuenta: cuentaActual() });
    const u = r.unidades.find((x) => String(x.id) === String(id));
    if (!u) return;
    unidadBarra = u;
    const asig = [...selAsig.options].find((o) => sinTildes(o.value) === sinTildes(u.asignatura));
    if (asig) { selAsig.value = asig.value; await cargarCursos(); }
    const curso = [...selCurso.options].find((o) => claveCurso(o.value) === claveCurso(u.curso));
    if (curso) { selCurso.value = curso.value; selCurso.dispatchEvent(new Event("change")); }
    $("#nota-unidad").innerHTML = `<div class="nota info">Unidad elegida en Barra Profe: <b>${esc(u.curso)} · ${esc(u.asignatura)} · ${esc(u.nombre)}</b>.
      ${asig && curso ? "Ya dejé elegidos la asignatura y el curso." : "Elige la asignatura y el curso que corresponden."}</div>`;
  } catch { /* sin Barra configurada: se usa el formulario normal */ }
}

function extrasElegido(perfil) {
  const marcada = $("[data-extra]:checked");
  if (!marcada) return null;
  const curso = $("#f-curso").value;
  return (perfil.actividades_extra || []).filter((e) => e.curso && curso.includes(e.curso))[Number(marcada.dataset.extra)] || null;
}

async function generar(extra) {
  const asignatura = $("#f-asig").value === "__otra" ? $("#f-asig-otra").value.trim() : $("#f-asig").value;
  const curso = $("#f-curso").value === "__otro" ? $("#f-curso-otro").value.trim() : $("#f-curso").value;
  const tema = $("#f-tema").value, archivos = [...$("#f-archivos").files], video = $("#f-video").value;
  if (!compartido.ia?.lista) { aviso("Primero conecta la IA.", "error"); document.dispatchEvent(new CustomEvent("abrir-ia")); return; }
  if (!asignatura || !curso) { aviso("Indica la asignatura y el curso.", "error"); return; }
  if (!tema.trim() && !archivos.length && !video.trim()) { aviso("Escribe el tema, o sube un archivo o un video.", "error"); $("#f-tema").focus(); return; }
  const btn = $("#generar");
  btn.disabled = true;
  $("#resultado").innerHTML = cargando("Leyendo el material y redactando la clase. Puede tardar un minuto…");
  try {
    const r = await api.form("/api/planificacion/generar", {
      asignatura, curso, tema, indicaciones: $("#f-indic").value, duracion: Number($("#f-duracion").value) || 90,
      actividad_extra: extra, canva: $("#f-canva").value, video,
    }, { archivos, guia_pie: $("#f-guia").files[0] });
    archivosMaterial = archivos;
    plan = { ...r, fecha: hoyISO(), hora: HORA_POR_DEFECTO, tipo: "Universal", oa_exactos: false, dua_ia: [...(r.dua || [])] };
    guardarBorrador();
    await pintarResultado();
    $("#resultado").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    $("#resultado").innerHTML = `<div class="nota error">No se pudo generar la planificación: ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

const guardarBorrador = () => guardarLocal(BORRADOR(), plan);

async function pintarResultado() {
  const caja = $("#resultado");
  if (!plan) { caja.innerHTML = ""; return; }
  oaCurso = plan.asignatura && plan.curso
    ? (await api.get(`/api/curriculo/oa?asignatura=${encodeURIComponent(plan.asignatura)}&curso=${encodeURIComponent(plan.curso)}`).catch(() => ({ oa: [] }))).oa : [];
  const notas = [
    ...(plan.avisos || []).map((a) => `<div class="nota aviso">${esc(a)}</div>`),
    ...(plan.infos || []).map((a) => `<div class="nota info">${esc(a)}</div>`),
    plan.modo_cierre === "B" ? `<div class="nota info">El cierre parte de la actividad que trae tu material. Revisa que calce con lo que quieres.</div>` : "",
    plan.intentos_previos?.length ? `<div class="nota">Antes se probó: ${esc(plan.intentos_previos.join(" · "))}</div>` : "",
  ].join("");
  caja.innerHTML = `
    <section class="tarjeta"><h2>Planificación lista para revisar</h2>
      <p class="sub">${esc(plan.asignatura)} · ${esc(plan.curso)} · ${esc(plan.tiempo)}${plan.modelo ? ` · generada con ${esc(plan.modelo)}` : ""}. Puedes editar cualquier cuadro antes de exportar.</p>
      ${notas}
      <div class="pestanas" role="tablist">
        ${[["inicio", "⏳ Inicio"], ["desarrollo", "⚙️ Desarrollo"], ["cierre", "🎯 Cierre"], ["webclass", "🚀 WebClass"]]
          .map(([id, t], i) => `<button role="tab" id="tab-${id}" aria-controls="panel-${id}" aria-selected="${i === 0}" data-tab="${id}">${t}</button>`).join("")}
      </div>
      ${["inicio", "desarrollo", "cierre"].map((id, i) => `
        <div class="panel-pestana" role="tabpanel" id="panel-${id}" aria-labelledby="tab-${id}" ${i ? "hidden" : ""}>
          <textarea class="grande" data-campo="${id}" aria-label="${id}">${esc(plan[id])}</textarea></div>`).join("")}
      <div class="panel-pestana" role="tabpanel" id="panel-webclass" aria-labelledby="tab-webclass" hidden>${panelWebclass()}</div>
    </section>
    <section class="tarjeta"><h2>Exportar</h2>
      <div class="barra espaciada">
        <button class="btn primario" id="x-excel" type="button">📥 Descargar en Excel</button>
        <button class="btn exito" id="x-copiar" type="button">📋 Copiar para WebClass</button>
        <button class="btn" id="x-guardar" type="button">💾 Guardar en historial</button>
        <button class="btn primario" id="x-barra" type="button">🚀 Enviar a WebClass</button></div>
      <details class="plegable espaciada"><summary>¿Cómo subir la clase a WebClass?</summary><div id="ayuda-marcador"></div></details></section>`;
  enlazarResultado();
}

const GRUPOS_DUA = [["Representación", "cómo presento la información", 1, 12], ["Acción y expresión", "cómo responden las estudiantes", 13, 21],
  ["Implicación", "cómo las motivo", 22, 31]];
const vista = (t) => String(t || "").replace(/\s+/g, " ").trim().slice(0, 90);
const HORA_POR_DEFECTO = "08:00";

function panelWebclass() {
  const c = constantes;
  const acordeon = (id, titulo, alto) => `
    <details class="plegable acordeon"><summary>${titulo}<span class="vista" id="v-${id}">${esc(vista(plan[id]))}</span></summary>
      <textarea id="c-${id}" data-campo="${id}" style="min-height:${alto}px" aria-label="${titulo}">${esc(plan[id])}</textarea></details>`;
  const oaLista = oaCurso.length ? `
      <input type="search" id="oa-filtro" placeholder="Buscar por código o palabra…" aria-label="Buscar OA">
      <div class="lista-scroll" id="oa-lista">${oaCurso.map((o) => `
        <label class="casilla" data-texto="${esc((o.codigo + " " + o.eje + " " + o.texto).toLowerCase())}">
          <input type="checkbox" data-oa="${esc(o.codigo)}" ${plan.oa_sel?.includes(o.codigo) ? "checked" : ""}>
          <span><span class="oa-cod">${esc(o.codigo)}</span><span class="oa-eje">${esc(o.eje)}</span><br>${esc(o.texto)}</span></label>`).join("")}</div>
      <label class="casilla"><input type="checkbox" id="oa-exactos" ${plan.oa_exactos ? "checked" : ""}><span>Marcar exactamente estos OA (solo para el marcador del navegador)</span></label>`
    : `<div class="rejilla"><div class="campo"><label for="oa-texto">OA a marcar</label><input type="text" id="oa-texto" value="${esc(plan.oa_texto)}" placeholder="Ej: OA9, OA18"></div>
       <div class="campo"><label for="oa-claves">Palabras clave del OA</label><input type="text" id="oa-claves" value="${esc(plan.oa_claves)}"></div></div>`;
  const grupoDua = ([nombre, ayuda, a, b]) => `
    <div class="grupo-dua">${nombre} <small>· ${ayuda}</small></div>
    <div class="chips">${Object.entries(c.pautas_dua).filter(([n]) => n >= a && n <= b).map(([n, t]) => `
      <label class="chip" title="${esc(t)}"><input type="checkbox" data-dua="${n}" ${plan.dua?.includes(Number(n)) ? "checked" : ""}><span>${n}. ${esc(t.length > 52 ? t.slice(0, 50) + "…" : t)}</span></label>`).join("")}</div>`;
  return `
    <p class="sub">Ya dejé listo lo que WebClass pide además del texto. Revisa lo básico y envíala.</p>
    <div class="rejilla tres">
      <div class="campo ancho"><label for="w-nombre">Nombre de la clase</label><input type="text" id="w-nombre" value="${esc(plan.nombre)}"></div>
      <div class="campo"><label for="w-fecha">Fecha</label><input type="date" id="w-fecha" value="${esc(plan.fecha)}"></div>
      <div class="campo"><label for="w-hora">Hora de inicio</label><input type="time" id="w-hora" value="${esc(plan.hora || HORA_POR_DEFECTO)}"></div>
      <div class="campo"><label for="w-dur">Duración</label><select id="w-dur">${[1, 2, 3, 4, 5, 6].map((n) => `
        <option value="${n}" ${String(plan.duracion_horas) === String(n) ? "selected" : ""}>${n} hora${n > 1 ? "s" : ""} pedagógica${n > 1 ? "s" : ""} (${n * 45} min)</option>`).join("")}</select></div>
      <div class="campo ancho"><span class="etiqueta">Tipo de clase</span><div class="segmentado" role="radiogroup">${c.tipos_clase.map((t) => `
        <label><input type="radio" name="w-tipo" value="${esc(t)}" ${plan.tipo === t ? "checked" : ""}>${esc(t)}</label>`).join("")}</div></div>
    </div>
    <div class="espaciada">
      ${acordeon("evaluacion", "Método de evaluación", 120)}${acordeon("recursos", "Recursos", 130)}
      ${acordeon("adecuaciones", "Adecuación curricular", 130)}${acordeon("motivacion", "Motivación", 90)}
      <details class="plegable acordeon"><summary>Objetivos de Aprendizaje<span class="vista" id="v-oa"></span></summary>${oaLista}
        <p class="ayuda">Al enviar, eliges los OA de la unidad de WebClass; estos son los que propuso la IA.</p></details>
      <details class="plegable acordeon"><summary>Pautas DUA<span class="vista" id="dua-estado"></span></summary>
        <div class="barra"><button class="btn chico" id="dua-ia" type="button">Volver a las sugeridas por la IA</button></div>
        ${GRUPOS_DUA.map(grupoDua).join("")}</details>
    </div>
    <div id="revision" class="revision" aria-live="polite"></div>
    <div class="barra espaciada"><button class="btn primario grande" id="w-enviar" type="button">🚀 Enviar a WebClass</button>
      <button class="btn" id="w-copiar" type="button">📋 Copiar para el marcador</button></div>
    <div id="envio" class="espaciada"></div>`;
}

function leerCamposDeLaPantalla() {
  $$("[data-campo]").forEach((t) => { plan[t.dataset.campo] = t.value; });
  const val = (id) => $(id)?.value;
  if ($("#w-nombre")) {
    Object.assign(plan, { nombre: val("#w-nombre"), fecha: val("#w-fecha"), hora: val("#w-hora") || HORA_POR_DEFECTO,
      duracion_horas: val("#w-dur"), tipo: $("input[name=w-tipo]:checked")?.value || "Universal" });
    plan.dua = $$("[data-dua]:checked").map((i) => Number(i.dataset.dua));
    if (oaCurso.length) { plan.oa_sel = $$("[data-oa]:checked").map((i) => i.dataset.oa); plan.oa_exactos = !!$("#oa-exactos")?.checked; }
    else { plan.oa_texto = val("#oa-texto"); plan.oa_claves = val("#oa-claves"); }
  }
}

function activarPestana(id) {
  $$("[data-tab]").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.tab === id)));
  $$("#resultado .panel-pestana").forEach((p) => (p.hidden = p.id !== `panel-${id}`));
  const ta = $(`#panel-${id} textarea.grande`);
  if (ta) autoajustar(ta);
}

function actualizarRevision() {
  const el = $("#revision");
  if (!el) return;
  const nDua = $$("[data-dua]:checked").length;
  const nOa = oaCurso.length ? $$("[data-oa]:checked").length : (plan.oa_texto || "").split(/[\s,;]+/).filter(Boolean).length;
  const completo = ["inicio", "desarrollo", "cierre"].every((k) => (plan[k] || "").trim());
  const fila = (clase, texto) => `<div class="${clase}">${texto}</div>`;
  el.innerHTML = [
    fila((plan.nombre || "").trim() ? "ok" : "falta", "Nombre de la clase"),
    fila(plan.fecha ? "ok" : "falta", plan.fecha ? `Fecha: ${fechaChilena(plan.fecha)} a las ${plan.hora || HORA_POR_DEFECTO}` : "Falta la fecha"),
    fila(completo ? "ok" : "falta", "Inicio, Desarrollo y Cierre con contenido"),
    fila(nDua >= constantes.min_dua ? "ok" : "aviso", `${nDua} pautas DUA${nDua < constantes.min_dua ? ` (WebClass pide ${constantes.min_dua}; se completan solas)` : ""}`),
    fila("aviso", nOa ? `${nOa} OA propuestos por la IA; al enviar eliges los de tu unidad` : "Al enviar eliges los OA de tu unidad"),
  ].join("");
  const dua = $("#dua-estado"), oa = $("#v-oa");
  if (dua) dua.textContent = `${nDua} marcadas`;
  if (oa) oa.textContent = nOa ? `${nOa} propuestos` : "";
  $$("[data-campo]").forEach((t) => { const v = $(`#v-${t.dataset.campo}`); if (v) v.textContent = vista(t.value); });
}

function enlazarResultado() {
  const caja = $("#resultado");
  const tabs = $$("[data-tab]", caja);
  tabs.forEach((t) => t.addEventListener("click", () => activarPestana(t.dataset.tab)));
  $$("textarea.grande", caja).forEach((ta) => ta.addEventListener("input", () => autoajustar(ta)));
  if ($("textarea.grande")) autoajustar($("textarea.grande"));
  caja.oninput = caja.onchange = () => { leerCamposDeLaPantalla(); guardarBorrador(); actualizarRevision(); };
  actualizarRevision();
  $("#dua-ia")?.addEventListener("click", () => {
    $$("[data-dua]").forEach((i) => { i.checked = (plan.dua_ia || []).includes(Number(i.dataset.dua)); });
    leerCamposDeLaPantalla(); guardarBorrador(); actualizarRevision();
  });
  $("#w-enviar").onclick = abrirEnvio;
  $("#w-copiar").onclick = copiarWebclass;
  $("#oa-filtro")?.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    $$("#oa-lista [data-texto]").forEach((l) => (l.hidden = !!q && !l.dataset.texto.includes(q)));
  });
  $("#x-excel").onclick = exportarExcel;
  $("#x-copiar").onclick = copiarWebclass;
  $("#x-barra").onclick = () => { activarPestana("webclass"); abrirEnvio(); };
  $("#x-guardar").onclick = async () => {
    leerCamposDeLaPantalla();
    try { await api.post("/api/historial", plan); aviso("Guardada en el historial."); pintarHistorial(); } catch (e) { aviso(e.message, "error"); }
  };
  cargarAyudaMarcador();
}

async function exportarExcel() {
  leerCamposDeLaPantalla();
  try {
    const campos = Object.fromEntries(CAMPOS.map((c) => [c, plan[c] || ""]));
    const blob = await api.blob("/api/planificacion/excel", {
      meta: { asignatura: plan.asignatura, curso: plan.curso, nombre: plan.nombre, tiempo: plan.tiempo, tema: plan.tema, fecha: fechaChilena(plan.fecha) },
      campos, oa_sel: plan.oa_sel || [], oa_texto: plan.oa_texto || "", dua: plan.dua || [],
    });
    descargar(blob, `Planificacion_${(plan.curso || "clase").replace(/[^\w]+/g, "_")}_${hoyISO()}.xlsx`);
  } catch (e) { aviso(e.message, "error"); }
}

async function copiarWebclass() {
  leerCamposDeLaPantalla();
  const objetivo = (plan.inicio.match(/^\s*Objetivo de Aprendizaje:\s*(.+)$/im) || [])[1] || "";
  try {
    const campos = Object.fromEntries(CAMPOS.map((c) => [c, plan[c] || ""]));
    const r = await api.post("/api/webclass/clase", {
      nombre: plan.nombre, fecha: fechaChilena(plan.fecha), hora: plan.hora || HORA_POR_DEFECTO, duracion: plan.duracion_horas, tipo: plan.tipo, campos,
      oa_sel: plan.oa_sel || [], oa_texto: plan.oa_texto || "", oa_claves: plan.oa_claves || "", oa_exactos: plan.oa_exactos,
      dua: plan.dua || [], asignatura: plan.asignatura, curso: plan.curso, objetivo,
    });
    if (await copiar(r.json)) aviso("✓ Copiado. Abre «Nueva clase» en WebClass y usa tu marcador «Llenar WebClass».");
    else aviso("No se pudo copiar automáticamente.", "error");
  } catch (e) { aviso(e.message, "error"); }
}

function cargarAyudaMarcador() {
  $("#ayuda-marcador").innerHTML = `
    <p><b>Una sola vez, crear el marcador</b> (si no ves la barra de marcadores: Ctrl+Mayús+B):</p>
    <ol><li>Copia el código con el botón de abajo.</li>
    <li>En Chrome, clic derecho sobre la barra de marcadores → <b>Agregar página…</b></li>
    <li>En <b>Nombre</b> escribe <code>Llenar WebClass</code> y en <b>URL</b> pega el código. Guarda.</li></ol>
    <div class="barra"><button class="btn" id="copiar-marcador" type="button">Copiar código del marcador</button>
      <a class="btn" href="${esc(constantes.enlace_marcador)}" onclick="event.preventDefault()" draggable="true">📋 Llenar WebClass</a>
      <span class="ayuda">← o arrástralo a la barra de marcadores</span></div>
    <p class="espaciada"><b>Cada clase:</b> 1) presiona <b>Copiar para WebClass</b>; 2) en WebClass abre la unidad y entra a <b>Nueva clase</b>;
    3) haz clic en el marcador: completa nombre, fecha, duración, evaluación y las pestañas, y marca el OA y las pautas DUA;
    4) revisa y presiona <b>Guardar</b>.</p>`;
  $("#copiar-marcador").onclick = async () => aviso((await copiar(constantes.enlace_marcador)) ? "Código del marcador copiado." : "No se pudo copiar.", "ok");
}

async function pintarHistorial() {
  const caja = $("#historial");
  let clases = [];
  try { clases = (await api.get("/api/historial")).clases; } catch { /* sin historial */ }
  if (!clases.length) { caja.innerHTML = ""; return; }
  caja.innerHTML = `<details class="plegable"><summary>📚 Historial (${clases.length} clases guardadas)</summary>
    ${clases.map((r) => `<div class="historial-fila"><div><b>${esc(r.nombre || "Sin nombre")}</b>
      <small>${esc(r.asignatura)} · ${esc(r.curso)} · ${esc((r.guardado || "").slice(0, 10))}</small></div>
      <button class="btn chico" data-abrir="${esc(r.archivo)}">Abrir</button>
      <button class="btn chico peligro" data-borrar="${esc(r.archivo)}" aria-label="Borrar">🗑</button></div>`).join("")}</details>`;
  $$("[data-abrir]", caja).forEach((b) => (b.onclick = async () => {
    const r = clases.find((c) => c.archivo === b.dataset.abrir);
    const { archivo, guardado, ...resto } = r;
    plan = resto;
    guardarBorrador();
    await pintarResultado();
    $("#resultado").scrollIntoView({ behavior: "smooth" });
  }));
  $$("[data-borrar]", caja).forEach((b) => (b.onclick = async () => { await api.borrar(`/api/historial/${encodeURIComponent(b.dataset.borrar)}`); pintarHistorial(); }));
}

// ───────────── Enviar a WebClass con Barra Profe ─────────────
const URL_WEBCLASS = "https://proyecto.webescuela.cl/sistema/webclass";
const EXT_RECURSO = /\.(pdf|docx?|xlsx?|pptx?|jpe?g|png|mp3|wav|mp4)$/i;

let catalogoUnidad = null;   // OA de la unidad elegida: [{id, etiqueta, texto}] (null = no se pudo leer)
let unidadesBarra = [];      // todas las unidades del perfil de Barra
let recursos = [];           // archivos a adjuntar: [{guardado|file, nombre, momento, usar}]
const baseNombre = (n) => String(n).replace(/\.[^.]+$/, "");

/** El material con que se generó la planificación (guardado en el servidor) es el que viaja a WebClass como recurso. */
function recursosDeLaPlanificacion() {
  const guardados = (plan.archivos_material || []).filter((a) => EXT_RECURSO.test(a.nombre) && plan.material_id)
    .map((a) => ({ guardado: { material_id: plan.material_id, nombre: a.nombre }, tamano: a.tamano, nombre: baseNombre(a.nombre), momento: "desarrollo", usar: true }));
  const pie = plan.guia_pie && plan.material_id ? [{
    guardado: { material_id: plan.material_id, nombre: plan.guia_pie.guardado }, tamano: plan.guia_pie.tamano, esPie: true,
    html: /\.html?$/i.test(plan.guia_pie.nombre), nombre: `Guía PIE - ${plan.nombre || baseNombre(plan.guia_pie.nombre)}`, momento: "desarrollo", usar: true }] : [];
  if (guardados.length || pie.length) return [...guardados, ...pie];
  // planificaciones anteriores a esta versión: se usan los archivos que sigan en el formulario
  return archivosMaterial.filter((f) => EXT_RECURSO.test(f.name)).map((file) => ({ file, tamano: file.size, nombre: baseNombre(file.name), momento: "desarrollo", usar: true }));
}

function datosClase() {
  leerCamposDeLaPantalla();
  return {
    nombre: plan.nombre, fecha: fechaChilena(plan.fecha), hora: plan.hora || HORA_POR_DEFECTO, horas: plan.duracion_horas, tipo: plan.tipo,
    campos: Object.fromEntries(["motivacion", ...CAMPOS].map((c) => [c, plan[c] || ""])), dua: plan.dua || [],
  };
}

/** OA elegidos: los marcados de la unidad (o, si no se pudo leer su lista, los que propuso la IA). */
function oaElegidos() {
  if (catalogoUnidad) return $$("[data-oau]:checked").map((i) => i.dataset.oau);
  return plan.oa_sel?.length ? plan.oa_sel : (plan.oa_texto || "").split(/[\s,;]+/).filter(Boolean);
}

async function abrirEnvio() {
  leerCamposDeLaPantalla();
  const caja = $("#envio");
  if (!(plan.nombre || "").trim() || !plan.fecha) { aviso("Completa el nombre y la fecha de la clase.", "error"); return; }
  caja.innerHTML = cargando("Buscando tus unidades en Barra Profe…");
  caja.scrollIntoView({ behavior: "smooth", block: "nearest" });
  let r;
  try {
    const estado = await api.get("/api/barra/estado");
    if (!estado.valida) {
      caja.innerHTML = `<div class="nota aviso">${esc(estado.mensaje)} Configúrala en <a href="#/perfil">Mi perfil</a>.</div>`;
      return;
    }
    if (estado.compatible === false) {
      caja.innerHTML = `<div class="nota error">${esc(estado.mensaje_version)}</div>`;
      return;
    }
    r = await api.post("/api/barra/unidades", { cuenta: cuentaActual() });
  } catch (e) { caja.innerHTML = `<div class="nota error">${esc(e.message)}</div>`; return; }
  unidadesBarra = r.unidades;
  recursos = recursosDeLaPlanificacion();

  const sugeridas = r.unidades.filter((u) => claveCurso(u.curso) === claveCurso(plan.curso) && sinTildes(u.asignatura) === sinTildes(plan.asignatura));
  const resto = r.unidades.filter((u) => !sugeridas.includes(u));
  const opcion = (u, estrella) => `<option value="${esc(u.id)}">${estrella ? "★ " : ""}${esc(u.curso)} · ${esc(u.asignatura)} · ${esc(u.nombre)}</option>`;
  caja.innerHTML = `
    <div class="nota info">Se creará una clase nueva en WebClass con la cuenta activa en Barra Profe: <b>${esc(compartido.cuenta?.nombre || r.perfil)}</b> (${esc(r.perfil)}). Si no es la tuya, cámbiala en Barra con «Cambiar de profesor». La firma del libro sigue siendo solo tuya.</div>
    <div class="campo"><label for="e-unidad">¿En qué unidad?</label>
      <select id="e-unidad">${sugeridas.map((u) => opcion(u, true)).join("")}${resto.map((u) => opcion(u, false)).join("")}</select>
      <span class="ayuda">${sugeridas.length ? "★ = coincide con el curso y la asignatura de esta planificación." : "Ninguna unidad coincide con este curso y asignatura: elige la correcta."}</span></div>
    <div id="e-oa" class="espaciada"></div>
    <div id="e-recursos" class="espaciada"></div>
    <div id="e-replicas" class="espaciada"></div>
    <div id="e-confirmar" class="espaciada"></div>
    <div id="e-resultado" class="espaciada"></div>`;
  const select = $("#e-unidad");
  if (unidadBarra && [...select.options].some((o) => o.value === String(unidadBarra.id))) select.value = String(unidadBarra.id);
  select.onchange = () => { pintarReplicas(); cargarCatalogo(select.value); };
  pintarRecursos();
  pintarReplicas();
  cargarCatalogo(select.value);
}

function pintarRecursos() {
  const caja = $("#e-recursos");
  const noSubibles = (plan.archivos_material || []).filter((a) => !EXT_RECURSO.test(a.nombre)).map((a) => a.nombre);
  caja.innerHTML = `<span class="etiqueta">Recurso de la clase</span>
    <p class="ayuda">${recursos.length ? "Este es el material con que generaste la planificación: se sube a tu banco de recursos de WebClass y se asigna a la clase. Si ya tienes uno con el mismo nombre, se reutiliza." : "Esta planificación no tiene material para subir."}</p>
    ${noSubibles.length ? `<p class="ayuda">No se puede subir a WebClass (solo PDF, Word, Excel, PowerPoint, imágenes JPG/PNG, audio MP3/WAV o video MP4): ${esc(noSubibles.join(", "))}.</p>` : ""}
    ${recursos.map((r, i) => `
      <div class="fila-recurso">
        <label class="casilla"><input type="checkbox" data-rec-usar="${i}" ${r.usar ? "checked" : ""}><span></span></label>
        <input type="text" data-rec-nombre="${i}" value="${esc(r.nombre)}" aria-label="Nombre del recurso en WebClass">
        <select data-rec-momento="${i}" aria-label="Momento de la clase">
          ${[["inicio", "Inicio"], ["desarrollo", "Desarrollo"], ["cierre", "Cierre"]].map(([v, t]) => `<option value="${v}" ${r.momento === v ? "selected" : ""}>${t}</option>`).join("")}</select>
        <small class="ayuda">${r.esPie ? "Guía PIE adjunta · " : ""}${esc(r.file?.name || (r.esPie ? plan.guia_pie.nombre : r.guardado.nombre))} · ${((r.file?.size ?? r.tamano ?? 0) / 1048576).toFixed(1)} MB${r.html ? " · se convertirá a PDF al enviar (tarda unos segundos)" : ""}</small></div>`).join("") || '<p class="ayuda">No hay archivos para adjuntar.</p>'}
    <div class="campo"><label for="e-mas">Agregar otro archivo a la clase <span class="ayuda">(PDF, Word, Excel, PowerPoint, JPG, PNG, MP3, WAV o MP4)</span></label>
      <input type="file" id="e-mas" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.mp3,.wav,.mp4"></div>`;
  $$("[data-rec-usar]", caja).forEach((el) => (el.onchange = () => { recursos[el.dataset.recUsar].usar = el.checked; }));
  $$("[data-rec-nombre]", caja).forEach((el) => (el.oninput = () => { recursos[el.dataset.recNombre].nombre = el.value; }));
  $$("[data-rec-momento]", caja).forEach((el) => (el.onchange = () => { recursos[el.dataset.recMomento].momento = el.value; }));
  $("#e-mas").onchange = (e) => {
    [...e.target.files].filter((f) => EXT_RECURSO.test(f.name)).forEach((file) => recursos.push({ file, tamano: file.size, nombre: baseNombre(file.name), momento: "desarrollo", usar: true }));
    pintarRecursos();
  };
}

function unidadPrincipal() { return unidadesBarra.find((u) => String(u.id) === $("#e-unidad").value); }

function pintarReplicas() {
  const caja = $("#e-replicas"), principal = unidadPrincipal();
  const otras = principal ? hermanas(principal, unidadesBarra) : [];
  if (!otras.length) { caja.innerHTML = ""; return; }
  caja.innerHTML = `<span class="etiqueta">Replicar en el otro curso</span>
    <p class="ayuda">Crea la misma clase, con sus OA, DUA y archivos, en la unidad equivalente de tu otro curso. Cambia la fecha si ese curso tiene la clase otro día.</p>
    ${otras.map((h, i) => `
      <div class="fila-replica">
        <label class="casilla"><input type="checkbox" data-rep-usar="${i}" ${h.sugerida ? "checked" : ""}><span><b>${esc(h.curso)}</b></span></label>
        <select data-rep-unidad="${i}" aria-label="Unidad de ${esc(h.curso)}">${h.opciones.map((u) => `<option value="${esc(u.id)}" ${h.sugerida && h.sugerida.id === u.id ? "selected" : ""}>${esc(u.nombre)}</option>`).join("")}</select>
        <input type="date" data-rep-fecha="${i}" value="${esc(plan.fecha)}" aria-label="Fecha en ${esc(h.curso)}"></div>`).join("")}`;
}

function replicasElegidas() {
  const principal = unidadPrincipal();
  return (principal ? hermanas(principal, unidadesBarra) : []).map((h, i) => ({ h, i }))
    .filter(({ i }) => $(`[data-rep-usar="${i}"]`)?.checked)
    .map(({ h, i }) => ({ curso: h.curso, id_unidad: $(`[data-rep-unidad="${i}"]`).value, fecha: fechaChilena($(`[data-rep-fecha="${i}"]`).value) }));
}

async function cargarCatalogo(idUnidad) {
  const caja = $("#e-oa");
  $("#e-confirmar").innerHTML = "";
  $("#e-resultado").innerHTML = "";
  catalogoUnidad = null;
  caja.innerHTML = cargando("Leyendo los OA de esa unidad en WebClass…");
  try {
    const r = await api.post("/api/barra/catalogo", { id_unidad: idUnidad, cuenta: cuentaActual() });
    catalogoUnidad = r.oa.map((o) => { const [etiqueta, ...resto] = o.texto.split(/\s+/); return { id: o.id, etiqueta, texto: resto.join(" ") }; });
  } catch (e) {
    caja.innerHTML = `<div class="nota aviso">No pude leer los OA de la unidad (${esc(e.message)}). Si la unidad aún no tiene clases, los marco después de crearla con los que propuso la IA.</div>`;
    pintarBotonCrear();
    return;
  }
  const elegidos = sugerirOA(catalogoUnidad, plan);
  const propuestos = [...(plan.oa_sel || [])];
  caja.innerHTML = `<span class="etiqueta">¿Qué OA de esta unidad trabaja la clase?</span>
    <p class="ayuda">${elegidos.size ? "Dejé marcados los que mejor calzan; cámbialos si hace falta."
      : `Esta unidad tiene sus propios OA${propuestos.length ? ` (la IA propuso ${esc(propuestos.join(", "))}, que no están aquí)` : ""}: marca los que corresponden.`}</p>
    <div class="lista-scroll oa-unidad">${catalogoUnidad.map((o) => `
      <label class="casilla"><input type="checkbox" data-oau="${esc(o.etiqueta)}" ${elegidos.has(o.etiqueta) ? "checked" : ""}>
        <span><span class="oa-cod">${esc(o.etiqueta)}</span>${esc(o.texto)}</span></label>`).join("") || '<p class="vacio">La unidad no tiene OA.</p>'}</div>`;
  pintarBotonCrear();
}

function pintarBotonCrear() {
  $("#e-confirmar").innerHTML = `<div class="barra"><button class="btn exito grande" id="e-crear" type="button">✅ Crear la clase en WebClass</button></div>`;
  $("#e-crear").onclick = pedirConfirmacion;
}

function pedirConfirmacion() {
  const c = datosClase(), principal = unidadPrincipal(), reps = replicasElegidas();
  const adjuntos = recursos.filter((r) => r.usar);
  const lineaUnidad = (curso, nombre, fecha) => `<li><b>${esc(curso)}</b> · ${esc(nombre)} · ${esc(fecha)}</li>`;
  $("#e-confirmar").innerHTML = `
    <div class="resumen-envio"><b>Se va a crear en WebClass:</b><br>
      «${esc(c.nombre)}» · ${esc(c.hora)} · ${c.horas} h pedagógica(s) · ${esc(c.tipo)}
      <ul>${lineaUnidad(principal.curso, principal.nombre, c.fecha)}
        ${reps.map((r) => lineaUnidad(r.curso, unidadesBarra.find((u) => String(u.id) === String(r.id_unidad))?.nombre || "", r.fecha)).join("")}</ul>
      OA: ${esc(oaElegidos().join(", ") || "ninguno")} · ${c.dua.length} pautas DUA
      ${adjuntos.length ? `<br>Archivos adjuntos: ${adjuntos.map((r) => esc(r.nombre)).join(", ")}` : ""}
      <div class="barra espaciada"><button class="btn exito" id="e-si" type="button">Sí, crear ahora</button>
        <button class="btn" id="e-no" type="button">Volver</button></div></div>`;
  $("#e-si").onclick = () => enviar();
  $("#e-no").onclick = pintarBotonCrear;
}

async function enviar() {
  const caja = $("#e-resultado");
  const clase = datosClase(), principal = unidadPrincipal(), reps = replicasElegidas();
  const adjuntos = recursos.filter((r) => r.usar);
  const oa = oaElegidos();
  $("#e-confirmar").innerHTML = "";
  caja.innerHTML = cargando(`Creando la clase en WebClass${reps.length ? ` (${1 + reps.length} cursos)` : ""}${adjuntos.length ? " y subiendo el material" : ""}. Puede tardar un momento…`);
  try {
    const r = await api.form("/api/barra/crear", {
      cuenta: cuentaActual(), clase, destinos: [{ id_unidad: principal.id, fecha: clase.fecha }, ...reps.map((x) => ({ id_unidad: x.id_unidad, fecha: x.fecha }))],
      oa, nivel_hint: plan.curso, oa_textos: Object.fromEntries((catalogoUnidad || []).map((o) => [o.etiqueta, o.texto])), permitir_sin_oa: true,
      recursos: adjuntos.map((x) => ({ archivo: x.file?.name || x.guardado.nombre, nombre: x.nombre.trim() || x.file?.name || x.guardado.nombre,
        momento: x.momento, material_id: x.guardado?.material_id })),
    }, { recursos: adjuntos.filter((x) => x.file).map((x) => x.file) });
    caja.innerHTML = (r.avisos || []).map((a) => `<div class="nota aviso">${esc(a)}</div>`).join("") + r.resultados.map(resultadoEnvio).join("");
    if (r.resultados.some((x) => ["hecho", "con_avisos", "ya"].includes(x.estado))) aviso("Listo: revisa el resultado ✓");
    pintarCreadas();
  } catch (e) {
    caja.innerHTML = `<div class="nota error">${esc(e.message)}</div>`;
    pintarBotonCrear();
  }
}

function resultadoEnvio(r) {
  const titulo = r.curso ? `<b>${esc(r.curso)}</b> · ${esc(r.unidad)}<br>` : "";
  const enlace = r.idclase && r.id_unidad
    ? `<br><a class="btn chico" target="_blank" rel="noopener" href="${URL_WEBCLASS}/home/planificacion/editar_clase.php?idUnidad=${r.id_unidad}&c=${r.idclase}">Abrir la clase en WebClass</a>` : "";
  if (r.estado === "error") return `<div class="nota error">${titulo}${esc(r.motivo)}</div>`;
  if (r.estado === "ya") return `<div class="nota ok">${titulo}○ ${esc(r.motivo)} (clase ${esc(r.idclase)}). No se creó otra.${enlace}</div>`;
  if (r.estado === "pendiente") return `<div class="nota aviso">${titulo}⚠ ${esc(r.motivo)}</div>`;
  const avisos = (r.avisos || []).map((a) => `<br>⚠ ${esc(a)}`).join("");
  return `<div class="nota ${r.estado === "hecho" ? "ok" : "aviso"}">${titulo}✓ <b>Clase creada</b> el ${esc(r.fecha)} (id ${esc(r.idclase)}). ${r.oa_marcados} OA, ${r.dua} pautas DUA`
    + `${r.recursos_adjuntos ? ` y ${r.recursos_adjuntos} archivo(s) adjunto(s)` : ""}. La unidad ahora tiene ${r.clases_despues} clases.${avisos}${enlace}</div>`;
}

// ───────────── Registro de lo creado en WebClass ─────────────
async function pintarCreadas() {
  const caja = $("#creadas");
  if (!caja) return;
  let r;
  try { r = await api.get("/api/registro"); } catch { return; }
  if (!r.clases.length) { caja.innerHTML = ""; return; }
  caja.innerHTML = `<details class="plegable"><summary>🗂️ Creadas en WebClass (${r.clases.length})</summary>
    <p class="ayuda">Lo que este planificador creó en WebClass con tu cuenta. Si necesitas borrar una clase, ábrela con el enlace: el planificador no elimina nada en WebClass.</p>
    <div class="barra"><button class="btn chico" id="c-comprobar" type="button">Comprobar cuáles siguen existiendo</button><span class="ayuda" id="c-estado"></span></div>
    ${r.clases.map((c, i) => `<div class="historial-fila"><div><b>${esc(c.clase)}</b>
      <small>${esc(c.curso)} · ${esc(c.unidad)} · clase del ${esc(c.fecha_clase)} · creada el ${esc((c.fecha_creacion || "").replace("T", " ").slice(0, 16))}${c.recursos_ids ? ` · ${c.recursos_ids.split(";").filter(Boolean).length} recurso(s)` : ""}</small></div>
      <span class="ayuda" id="c-ex-${i}"></span>
      <a class="btn chico" target="_blank" rel="noopener" href="${URL_WEBCLASS}/home/planificacion/editar_clase.php?idUnidad=${esc(c.idunidad)}&c=${esc(c.idclase)}">Abrir</a>
      <button class="btn chico peligro" type="button" data-eliminar="${i}">Eliminar…</button></div>
      <div id="c-conf-${i}" class="espaciada" hidden></div>`).join("")}
    </details>`;
  $$("[data-eliminar]").forEach((b) => (b.onclick = () => pedirEliminar(r.clases[Number(b.dataset.eliminar)], Number(b.dataset.eliminar))));
  $("#c-comprobar").onclick = async () => {
    const boton = $("#c-comprobar");
    boton.disabled = true;
    $("#c-estado").textContent = "Consultando WebClass (solo lectura)…";
    try {
      const res = await api.post("/api/registro/comprobar", { cuenta: cuentaActual(), clases: r.clases.map((c) => ({ id_unidad: c.idunidad, idclase: c.idclase })) });
      r.clases.forEach((c, i) => {
        const vive = res.existen[c.idclase];
        $(`#c-ex-${i}`).textContent = vive === undefined ? "" : vive ? "✓ existe" : "✕ ya no existe";
      });
      $("#c-estado").textContent = "";
    } catch (e) { $("#c-estado").textContent = e.message; }
    boton.disabled = false;
  };
}

/** Deshacer: elimina en WebClass una clase que creó el planificador, tras una confirmación explícita. */
function pedirEliminar(c, i) {
  const caja = $(`#c-conf-${i}`);
  caja.hidden = false;
  caja.innerHTML = `<div class="nota error"><b>¿Eliminar «${esc(c.clase)}» de WebClass?</b><br>
    ${esc(c.curso)} · ${esc(c.unidad)} · clase del ${esc(c.fecha_clase)}. Esto <b>no se puede deshacer</b>. Los archivos que subiste al banco de recursos se conservan.
    <div class="barra espaciada"><button class="btn peligro" id="c-si-${i}" type="button">Sí, eliminar</button>
      <button class="btn" id="c-no-${i}" type="button">Cancelar</button></div></div>`;
  $(`#c-no-${i}`).onclick = () => { caja.hidden = true; caja.innerHTML = ""; };
  $(`#c-si-${i}`).onclick = async () => {
    caja.innerHTML = cargando("Eliminando en WebClass…");
    try {
      const r = await api.post("/api/registro/eliminar", { cuenta: cuentaActual(), clases: [{ id_unidad: c.idunidad, idclase: c.idclase }] });
      const x = r.resultados[0];
      if (x.estado === "eliminada" || x.estado === "ya") {
        caja.innerHTML = `<div class="nota ok">✓ ${x.estado === "ya" ? "La clase ya no existía." : "Clase eliminada de WebClass."}</div>`;
        $(`#c-ex-${i}`).textContent = "✕ ya no existe";
      } else {
        caja.innerHTML = `<div class="nota aviso">No se eliminó: ${esc(x.motivo || x.estado)}</div>`;
      }
    } catch (e) { caja.innerHTML = `<div class="nota error">${esc(e.message)}</div>`; }
  };
}
