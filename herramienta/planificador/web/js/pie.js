// Página «Guía PIE»: genera guías visuales para estudiantes no lectoras y las exporta a HTML, PDF y Word.
import { api } from "./api.js";
import { compartido } from "./estado.js";
import { conTexto, etiquetaDeRuta, textosDeGuia, valorEn } from "./logica.js";
import { $, $$, aviso, cargando, cronometro, descargar, esc } from "./util.js";
import { panelRecurso } from "./recurso.js";

let material = null;  // {id, imagenes, vision, max_vision} del material leído
let guia = null;      // última guía generada: {spec, html, archivo, ortografia, avisos, usado, datos}
let pdf = null, word = null;
let omitir = [];      // partes de la guía que no son texto para leer (las indica el servidor) + el tipo de cierre

export async function montarPie(cont) {
  const [{ asignaturas }, { niveles, claves_sin_texto: sinTexto = [] }, { guias }] = await Promise.all([
    api.get("/api/curriculo/asignaturas"), api.get("/api/pie/niveles"), api.get("/api/pie/guardadas")]);
  omitir = [...sinTexto, "tipo"];
  material = null;
  guia = null; pdf = null; word = null;
  const colegio = compartido.perfil?.colegio;
  cont.innerHTML = `
    <header class="cabecera"><h1>Guía PIE</h1>
      <p>Guías visuales con pictogramas para estudiantes no lectoras${colegio ? ` · ${esc(colegio)}` : ""}. Todo en mayúsculas, frases cortas y actividades de escribir, marcar y unir.</p></header>
    <section class="tarjeta"><h2><span class="paso">1</span>Datos de la guía</h2>
      <div class="rejilla espaciada">
        <div class="campo"><label for="p-asig">Asignatura</label>
          <select id="p-asig">${asignaturas.map((a) => `<option>${esc(a)}</option>`).join("")}<option value="__otra">+ Otra</option></select>
          <input type="text" id="p-asig-otra" placeholder="Nombre de la asignatura" hidden></div>
        <div class="campo"><label for="p-nivel">Nivel</label><select id="p-nivel">${niveles.map((n) => `<option>${esc(n)}</option>`).join("")}</select></div>
        <div class="campo ancho"><label for="p-tema">Tema de la guía</label><input type="text" id="p-tema" placeholder="Ej: Las fracciones · El ciclo del agua · La Colonia en Chile"></div>
        <div class="campo ancho"><label for="p-indic">Indicaciones <span class="ayuda">(opcional)</span></label>
          <textarea id="p-indic" placeholder="Ej: Objetivo: … / Enfocarse en … / Cerrar con un dibujo"></textarea></div>
      </div></section>
    <section class="tarjeta"><h2><span class="paso">2</span>Material de la clase <span class="ayuda">(opcional)</span></h2>
      <p class="sub">PDF, PowerPoint o Word. La guía usa su texto y, si quieres, sus imágenes.</p>
      <div class="campo"><input type="file" id="p-archivos" multiple accept=".pdf,.pptx,.docx" aria-label="Material de la clase"></div>
      <div class="barra espaciada"><button class="btn" id="p-leer" type="button" disabled>🖼️ Elegir imágenes del material</button>
        <span class="ayuda">Si no eliges imágenes, la guía usa fotos libres de Wikimedia Commons.</span></div>
      <div id="p-imagenes" class="espaciada"></div></section>
    <section class="tarjeta"><h2><span class="paso">3</span>Generar</h2>
      <div class="barra espaciada"><button class="btn primario grande" id="p-generar" type="button">✨ Generar guía PIE</button></div>
      <div id="p-estado" class="espaciada"></div></section>
    <div id="p-resultado"></div>
    ${guias.length ? `<details class="plegable"><summary>📁 Guías anteriores (${guias.length})</summary>
      ${guias.slice(0, 40).map((g) => `<div class="historial-fila"><div>${esc(g)}</div>
        <a class="btn chico" href="/api/pie/guardadas/${encodeURIComponent(g)}" target="_blank" rel="noopener">Abrir</a></div>`).join("")}</details>` : ""}`;

  $("#p-asig").onchange = () => { $("#p-asig-otra").hidden = $("#p-asig").value !== "__otra"; };
  $("#p-archivos").onchange = () => { $("#p-leer").disabled = !$("#p-archivos").files.length; material = null; $("#p-imagenes").innerHTML = ""; };
  $("#p-leer").onclick = leerMaterial;
  $("#p-generar").onclick = generar;
}

const asignatura = () => ($("#p-asig").value === "__otra" ? $("#p-asig-otra").value.trim() : $("#p-asig").value);

async function leerMaterial() {
  const files = [...$("#p-archivos").files];
  if (!files.length) return;
  $("#p-imagenes").innerHTML = cargando("Leyendo el material (con archivos grandes puede tardar un poco)…");
  try {
    material = await api.subir("/api/pie/material", "archivos", files);
    pintarImagenes();
  } catch (e) { $("#p-imagenes").innerHTML = `<div class="nota error">${esc(e.message)}</div>`; }
}

function pintarImagenes() {
  const caja = $("#p-imagenes");
  const avisos = (material.avisos || []).map((a) => `<div class="nota aviso">${esc(a)}</div>`).join("");
  if (!material.imagenes.length) { caja.innerHTML = avisos + `<div class="nota info">No se encontraron imágenes en el material; la guía usará fotos de Wikimedia Commons.</div>`; return; }
  caja.innerHTML = avisos + `<p class="sub">${material.vision
    ? `La IA puede ver estas imágenes: márcalas si quieres elegirlas tú. Si no marcas ninguna, la IA elige entre las primeras ${material.max_vision}.`
    : "Marca las imágenes que sirven y escribe qué muestra cada una (este proveedor no ve imágenes). Con Gemini como proveedor principal, la IA las ve sola."}</p>
    <div class="imagenes">${material.imagenes.map((im) => `
      <div class="imagen-tarjeta"><img loading="lazy" alt="${esc(im.id)}" src="/api/pie/imagen/${material.id}/${im.id}">
        <small title="${esc(im.origen)}">${esc(im.id)} · ${esc(im.origen)}</small>
        <label class="casilla"><input type="checkbox" data-img="${esc(im.id)}"><span>Usar</span></label>
        <input type="text" data-desc="${esc(im.id)}" placeholder="¿Qué muestra?" aria-label="¿Qué muestra ${esc(im.id)}?"></div>`).join("")}</div>`;
}

function datosGuia() {
  const seleccion = $$("[data-img]:checked").map((i) => i.dataset.img);
  const descripciones = {};
  seleccion.forEach((id) => { descripciones[id] = $(`[data-desc="${id}"]`).value.trim(); });
  return { material_id: material?.id || null, nivel: $("#p-nivel").value, asignatura: asignatura(), tema: $("#p-tema").value.trim(),
    indicaciones: $("#p-indic").value, seleccion, descripciones };
}

async function generar() {
  if (!compartido.ia?.lista) { aviso("Primero conecta la IA.", "error"); document.dispatchEvent(new CustomEvent("abrir-ia")); return; }
  if (!$("#p-tema").value.trim()) { aviso("Escribe el tema de la guía.", "error"); $("#p-tema").focus(); return; }
  const btn = $("#p-generar");
  btn.disabled = true;
  let detener = () => {};
  try {
    const files = [...$("#p-archivos").files];
    if (files.length && !material) {
      $("#p-estado").innerHTML = cargando("Leyendo el material…");
      material = await api.subir("/api/pie/material", "archivos", files);
      pintarImagenes();
    }
    $("#p-estado").innerHTML = cargando("Creando la guía PIE y revisando la ortografía. Puede tardar un minuto…");
    detener = cronometro($("#p-estado .cargando span:last-child"), "Creando la guía PIE y revisando la ortografía");
    const d = datosGuia();
    const r = await api.post("/api/pie/generar", d);
    guia = { ...r, datos: { ...d, seleccion: r.seleccion } };
    pdf = word = null;
    $("#p-estado").innerHTML = "";
    pintarGuia();
    $("#p-resultado").scrollIntoView({ behavior: "smooth" });
  } catch (e) {
    $("#p-estado").innerHTML = `<div class="nota error">No se pudo crear la guía: ${esc(e.message)}</div>`;
  } finally { detener(); btn.disabled = false; }
}

function pintarGuia() {
  const base = guia.archivo.replace(/\.html$/, "");
  const notas = [
    ...(guia.avisos || []).map((a) => `<div class="nota aviso">${esc(a)}</div>`),
    guia.recorte ? `<div class="nota info">El material es largo: solo se envió el comienzo. Si la guía debe centrarse en otra parte, indícalo en las indicaciones.</div>` : "",
    guia.avisos_ia?.length ? `<div class="nota">Antes se probó: ${esc(guia.avisos_ia.map((a) => a.split(";")[0]).join(" · "))}</div>` : "",
    guia.ortografia?.length ? `<div class="nota info"><b>Ortografía corregida:</b><br>${guia.ortografia.map(esc).join("<br>")}</div>`
      : `<div class="ayuda">✓ Ortografía revisada: sin errores encontrados.</div>`,
  ].join("");
  $("#p-resultado").innerHTML = `
    <section class="tarjeta"><h2>Guía lista</h2>
      <p class="sub">Guardada en <code>guias_pie/${esc(guia.archivo)}</code> · generada con ${esc(guia.usado)}</p>${notas}
      <div class="barra espaciada">
        <button class="btn primario" id="g-html" type="button">📥 Descargar HTML</button>
        <button class="btn" id="g-pdf" type="button">📄 Preparar PDF</button>
        <button class="btn" id="g-word" type="button">📝 Preparar Word</button>
        <button class="btn" id="g-orto" type="button">🔤 Revisar ortografía otra vez</button></div>
      <div class="barra espaciada" id="g-listos"></div>
      <p class="ayuda espaciada">El PDF y el Word usan los pictogramas automáticos; los que cambies a mano en la vista previa solo quedan en el HTML (para conservarlos, ábrelo en el navegador y usa Imprimir → Guardar como PDF).</p></section>
    <section class="tarjeta" id="g-subir" hidden><h2>Subir la guía a WebClass</h2>
      <p class="sub">Prepara el PDF o el Word (arriba) y súbelo desde aquí.</p><div id="g-subir-panel" class="espaciada"></div></section>
    <details class="plegable"><summary>Editar los textos de la guía (sin volver a generarla)</summary>
      <p class="ayuda">Cambia lo que quieras y presiona «Rearmar». Las imágenes y pictogramas se mantienen.</p>
      <div class="editor-guia espaciada" id="g-campos"></div>
      <div class="barra espaciada"><button class="btn primario" id="g-rearmar" type="button">Rearmar la guía con estos textos</button></div>
      <details class="plegable espaciada"><summary>Avanzado: editar todo el contenido (JSON)</summary>
        <p class="ayuda">Para cambiar imágenes (img1, img2…) o búsquedas de fotos. Un error de formato no se guarda.</p>
        <div class="campo"><textarea class="grande" id="g-json" spellcheck="false" aria-label="Contenido de la guía en JSON"></textarea></div>
        <div class="barra espaciada"><button class="btn" id="g-rearmar-json" type="button">Rearmar con este contenido</button></div></details></details>
    <section class="tarjeta espaciada"><h2>Vista previa</h2>
      <iframe class="vista-previa espaciada" id="g-previa" title="Vista previa de la guía" sandbox="allow-scripts allow-popups"></iframe></section>`;
  $("#g-previa").srcdoc = guia.html;
  $("#g-html").onclick = () => descargar(new Blob([guia.html], { type: "text/html" }), `${base}.html`);
  $("#g-pdf").onclick = () => preparar("pdf", base);
  $("#g-word").onclick = () => preparar("word", base);
  $("#g-orto").onclick = reOrtografia;
  $("#g-rearmar").onclick = rearmarConCampos;
  $("#g-rearmar-json").onclick = rearmarConJson;
  pintarCampos();
  mostrarListos(base);
}

/** Un campo de texto por cada texto de la guía, agrupados por parte (Sección 1, Sección 2, Cierre…). */
function pintarCampos() {
  const grupos = new Map();
  for (const { ruta, texto } of textosDeGuia(guia.spec, omitir)) {
    // objetivo → «General» · secciones[2].… → «Sección 3» · conceptos_clave[0] y cierre.… → su propio grupo
    const largo = ruta.length === 1 ? 0 : typeof ruta[1] === "number" && ruta.length > 2 ? 2 : 1;
    const clave = largo ? ruta.slice(0, largo).join(".") : "general";
    const resto = ruta.slice(largo);
    if (!grupos.has(clave)) grupos.set(clave, { titulo: tituloDeGrupo(ruta.slice(0, largo)), campos: [] });
    grupos.get(clave).campos.push({ ruta, texto, etiqueta: etiquetaDeRuta(typeof resto[0] === "number" || !resto.length ? ruta : resto) });
  }
  $("#g-campos").innerHTML = [...grupos.values()].map((g) => `<fieldset><legend>${esc(g.titulo)}</legend>
    ${g.campos.map((c) => `<label><span>${esc(c.etiqueta)}${esCorrecta(c.ruta) ? " (correcta)" : ""}</span>
      <input type="text" data-ruta="${esc(JSON.stringify(c.ruta))}" value="${esc(c.texto)}"></label>`).join("")}</fieldset>`).join("");
  $("#g-json").value = JSON.stringify(guia.spec, null, 2);
}

function tituloDeGrupo(ruta) {
  if (!ruta.length) return "General";
  if (ruta.length === 1 && ruta[0] === "conceptos_clave") return "Conceptos clave";
  const titulo = valorEn(guia.spec, [...ruta, "titulo"]);
  return `${etiquetaDeRuta(ruta)}${typeof titulo === "string" && titulo.trim() ? `: ${titulo}` : ""}`;
}

/** ¿Es la opción correcta de un «Marcar»? (se muestra al lado para no cambiarla sin querer) */
function esCorrecta(ruta) {
  if (ruta.at(-2) !== "opciones") return false;
  return valorEn(guia.spec, ruta.slice(0, -2))?.correcta === ruta.at(-1);
}

async function preparar(tipo, base) {
  const boton = $(tipo === "pdf" ? "#g-pdf" : "#g-word");
  boton.disabled = true;
  const original = boton.textContent;
  boton.textContent = tipo === "pdf" ? "Creando PDF (~20 s)…" : "Creando Word…";
  try {
    const d = guia.datos;
    const blob = tipo === "pdf"
      ? await api.blob("/api/pie/pdf", { html: guia.html })
      : await api.blob("/api/pie/word", { spec: guia.spec, nivel: d.nivel, asignatura: d.asignatura, material_id: d.material_id, seleccion: d.seleccion });
    if (tipo === "pdf") pdf = blob; else word = blob;
    mostrarListos(base);
  } catch (e) { aviso(e.message, "error"); }
  finally { boton.disabled = false; boton.textContent = original; }
}

function mostrarListos(base) {
  const caja = $("#g-listos");
  if (!caja) return;
  caja.innerHTML = "";
  const archivos = [];
  if (pdf) archivos.push(["PDF", pdf, `${base}.pdf`, "application/pdf"]);
  if (word) archivos.push(["Word", word, `${base}.docx`, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]);
  archivos.forEach(([etq, blob, nombre]) => {
    const b = Object.assign(document.createElement("button"), { className: "btn exito", type: "button", textContent: `📥 Descargar ${etq}` });
    b.onclick = () => descargar(blob, nombre);
    caja.appendChild(b);
  });
  $("#g-subir").hidden = !archivos.length;
  if (archivos.length) {
    const [, blob, nombre, mime] = archivos[0];
    const file = new File([blob], nombre, { type: mime });
    panelRecurso($("#g-subir-panel"), { archivo: file, nombreSugerido: `Guía PIE - ${guia.datos.tema}`, curso: guia.datos.nivel,
      asignatura: guia.datos.asignatura, tipoSugerido: "Guía PIE (NEE → Necesidades Especiales)" });
  }
}

function rearmarConCampos() {
  let spec = guia.spec;
  $$("#g-campos [data-ruta]").forEach((campo) => {
    const ruta = JSON.parse(campo.dataset.ruta);
    if (campo.value !== valorEn(spec, ruta)) spec = conTexto(spec, ruta, campo.value);
  });
  return rearmar(spec);
}

function rearmarConJson() {
  try { return rearmar(JSON.parse($("#g-json").value)); } catch (e) { aviso(`El contenido tiene un error de formato: ${e.message}`, "error"); }
}

async function rearmar(spec) {
  try {
    const r = await api.post("/api/pie/rearmar", { ...guia.datos, spec });
    Object.assign(guia, { spec, html: r.html, avisos: r.avisos, archivo: r.archivo });
    pdf = word = null;
    $("#g-previa").srcdoc = guia.html;
    pintarCampos();
    mostrarListos(guia.archivo.replace(/\.html$/, ""));
    aviso("Guía rearmada.");
  } catch (e) { aviso(e.message, "error"); }
}

async function reOrtografia() {
  const b = $("#g-orto");
  b.disabled = true;
  try {
    const r = await api.post("/api/pie/ortografia", { ...guia.datos, spec: guia.spec });
    Object.assign(guia, { spec: r.spec, html: r.html, avisos: r.avisos, archivo: r.archivo, ortografia: r.ortografia });
    pdf = word = null;
    pintarGuia();
  } catch (e) { aviso(e.message, "error"); b.disabled = false; }
}
