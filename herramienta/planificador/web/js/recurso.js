// «Subir a WebClass»: sube un archivo al banco de recursos. Con Barra Profe, directo; sin ella, con el marcador del navegador.
import { api } from "./api.js";
import { compartido, estadoBarra, hayBarra } from "./estado.js";
import { asignaturaCurricular } from "./logica.js";
import { $, aviso, cargando, copiar, cronometro, esc } from "./util.js";

let constantes = null;
const leerConstantes = async () => (constantes ||= await api.get("/api/webclass/constantes"));
const AUTOMATICO = "";   // tipo en WebClass: Barra lo deduce del archivo (PDF, Word, imagen…)

/** Dibuja el formulario del recurso dentro de `caja`. archivo: File (o Blob con .name). */
export async function panelRecurso(caja, { archivo, nombreSugerido = "", curso = "", asignatura = "", tipoSugerido = "" }) {
  caja.innerHTML = cargando("Preparando el formulario…");
  const perfil = compartido.perfil || {};
  const [c, sug, barra] = await Promise.all([leerConstantes(),
    api.get(`/api/webclass/sugerencias?curso=${encodeURIComponent(curso || perfil.curso_defecto || "")}&archivo=${encodeURIComponent(archivo.name)}`),
    estadoBarra()]);
  const directo = hayBarra(barra);
  const mb = archivo.size / 1024 / 1024;
  if (!directo && mb > c.max_mb) {
    caja.innerHTML = `<div class="nota aviso">El archivo pesa ${mb.toFixed(1)} MB: es demasiado grande para pasarlo con el marcador (máximo ${c.max_mb} MB). Súbelo a mano en WebClass.</div>`;
    return;
  }
  const tipo = tipoSugerido || (directo ? AUTOMATICO : sug.tipo);
  const asig = asignaturaCurricular(c.asignaturas_recurso, asignatura || perfil.asignatura_defecto || "");
  caja.innerHTML = `
    <div class="rejilla">
      <div class="campo"><label for="r-nombre">Nombre del recurso</label><input type="text" id="r-nombre" value="${esc(nombreSugerido)}"></div>
      <div class="campo"><label for="r-autor">Autor</label><input type="text" id="r-autor" value="${esc(perfil.nombre_docente || "")}"></div>
      <div class="campo"><label for="r-tipo">Tipo en WebClass</label>
        <select id="r-tipo">${directo ? `<option value="" ${tipo === AUTOMATICO ? "selected" : ""}>Automático (según el archivo)</option>` : ""}
          ${c.tipos_recurso.map((t) => `<option ${t === tipo ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div>
      <div class="campo"><label for="r-asig">Asignatura</label>
        <select id="r-asig">${c.asignaturas_recurso.map((a) => `<option ${a === asig ? "selected" : ""}>${esc(a)}</option>`).join("")}</select>
        <span class="ayuda">¿Falta tu asignatura? Agrégala en <a href="#/perfil">Mi perfil</a> con su id de WebClass.</span></div>
      <div class="campo ancho"><span class="etiqueta">Nivel(es)</span><div class="opciones">${c.niveles.map((n) => `
        <label class="casilla"><input type="checkbox" data-nivel="${esc(n)}" ${n === sug.nivel ? "checked" : ""}><span>${esc(n)}</span></label>`).join("")}</div></div>
      <label class="casilla ancho"><input type="checkbox" id="r-visible" checked><span>Visible para las estudiantes</span></label>
    </div>
    <div class="barra espaciada">
      ${directo ? `<button class="btn primario" id="r-subir" type="button">📤 Subir a WebClass</button>`
        : `<button class="btn exito" id="r-copiar" type="button">📤 Copiar recurso para WebClass</button>`}
      <span class="ayuda">Archivo: ${esc(archivo.name)} (${mb.toFixed(1)} MB)</span></div>
    <div id="r-resultado" class="espaciada" aria-live="polite"></div>
    ${directo
      ? `<p class="ayuda">Se sube con tu cuenta activa en Barra Profe${compartido.cuenta?.nombre ? ` (${esc(compartido.cuenta.nombre)})` : ""}. Si en tu banco ya hay un recurso tuyo con el mismo nombre, se reutiliza en vez de subirlo de nuevo.</p>`
      : `<p class="ayuda">Luego, en WebClass abre Recursos → «Subir recurso» y haz clic en tu marcador «Llenar WebClass». Revisa y presiona «Guardar».</p>`}`;

  const leer = () => ({
    nombre: $("#r-nombre", caja).value.trim(), autor: $("#r-autor", caja).value.trim(), asignatura: $("#r-asig", caja).value,
    niveles: [...caja.querySelectorAll("[data-nivel]:checked")].map((i) => i.dataset.nivel), visible: $("#r-visible", caja).checked,
    tipo: $("#r-tipo", caja).value,
  });
  const valido = (d) => {
    if (d.nombre && d.autor && d.niveles.length) return true;
    aviso("Escribe el nombre y el autor, y elige al menos un nivel.", "error");
    return false;
  };
  if (directo) {
    $("#r-subir", caja).onclick = async () => {
      const d = leer();
      if (!valido(d)) return;
      const boton = $("#r-subir", caja), res = $("#r-resultado", caja);
      boton.disabled = true;
      res.innerHTML = cargando("Subiendo a tu banco de recursos de WebClass…");
      const detener = cronometro($(".cargando span:last-child", res), "Subiendo a tu banco de recursos de WebClass");
      try {
        const r = await api.form("/api/barra/subir", { ...d, cuenta: compartido.cuenta?.clave || "" }, { archivo });
        res.innerHTML = r.subido
          ? `<div class="nota ok">✓ <b>Subido</b> a tu banco de recursos como «${esc(r.nombre)}» (id ${esc(r.id)}). Ya puedes adjuntarlo a tus clases.</div>`
          : `<div class="nota ok">○ Ya tenías en tu banco un recurso con ese nombre (id ${esc(r.id)}), así que no se subió otra vez. Si es un archivo distinto, cámbiale el nombre.</div>`;
        aviso(r.subido ? "Recurso subido a WebClass ✓" : "Ya estaba en tu banco de recursos.");
      } catch (e) {
        res.innerHTML = `<div class="nota error">No se pudo subir: ${esc(e.message)}</div>`;
      } finally {
        detener();
        boton.disabled = false;
      }
    };
    return;
  }
  $("#r-copiar", caja).onclick = async () => {
    const d = leer();
    if (!valido(d)) return;
    try {
      const r = await api.form("/api/webclass/recurso", d, { archivo });
      const ok = await copiar(r.json);
      aviso(ok ? "✓ Copiado. En WebClass: Recursos → «Subir recurso» y tu marcador." : "No se pudo copiar automáticamente.", ok ? "ok" : "error");
    } catch (e) { aviso(e.message, "error"); }
  };
}

export async function montarRecurso(cont) {
  const [c, barra] = await Promise.all([leerConstantes(), estadoBarra()]);
  const directo = hayBarra(barra);
  cont.innerHTML = `
    <header class="cabecera"><h1>Subir a WebClass</h1>
      <p>${directo ? "Sube guías, evaluaciones u otros archivos a tu banco de recursos de WebClass, directo con Barra Profe."
        : "Sube guías, evaluaciones u otros archivos a Recursos de WebClass con el marcador «Llenar WebClass»."}</p></header>
    <section class="tarjeta"><h2>Archivo</h2>
      <div class="campo espaciada"><label for="r-archivo">Archivo a subir (PDF, Word, Excel, PowerPoint, imagen, audio o video)</label>
        <input type="file" id="r-archivo" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.mp3,.wav,.mp4"></div>
      <div id="panel-recurso" class="espaciada"></div></section>
    ${directo ? "" : `<section class="tarjeta"><h2>¿Cómo funciona?</h2>
      <ol><li>Sube el archivo, revisa nombre, tipo, nivel y asignatura, y presiona <b>Copiar recurso para WebClass</b>.</li>
      <li>En WebClass ve a <b>Recursos → Subir recurso</b>.</li>
      <li>Haz clic en tu marcador <b>Llenar WebClass</b>: elige el tipo, escribe nombre y autor, marca niveles, asignatura y visibilidad, y adjunta el archivo.</li>
      <li>Revisa y presiona <b>Guardar</b>.</li></ol>
      <p class="ayuda">Es el mismo marcador de las clases. Si lo creaste antes de esta versión, reemplaza su URL por este código (clic derecho sobre el marcador → Editar):</p>
      <textarea class="codigo" readonly id="codigo-marcador">${esc(c.enlace_marcador)}</textarea>
      <div class="barra"><button class="btn" id="copiar-marcador" type="button">Copiar código del marcador</button></div></section>`}`;
  $("#copiar-marcador")?.addEventListener("click", async () => aviso((await copiar(c.enlace_marcador)) ? "Código copiado." : "No se pudo copiar.", "ok"));
  $("#r-archivo").onchange = (e) => {
    const f = e.target.files[0];
    if (f) panelRecurso($("#panel-recurso"), { archivo: f, nombreSugerido: f.name.replace(/\.[^.]+$/, "").replace(/_/g, " ") });
    else $("#panel-recurso").innerHTML = "";
  };
}
