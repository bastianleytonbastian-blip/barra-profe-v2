// «Subir a WebClass»: panel reutilizable para preparar un recurso y copiarlo para el marcador.
import { api } from "./api.js";
import { compartido } from "./estado.js";
import { $, aviso, copiar, esc } from "./util.js";

/** Dibuja el formulario del recurso dentro de `caja`. archivo: File o Blob con nombre (propiedad .name). */
export async function panelRecurso(caja, { archivo, nombreSugerido = "", curso = "", tipoSugerido = "" }) {
  const c = await api.get("/api/webclass/constantes");
  const sug = await api.get(`/api/webclass/sugerencias?curso=${encodeURIComponent(curso)}&archivo=${encodeURIComponent(archivo.name)}`);
  const mb = archivo.size / 1024 / 1024;
  if (mb > c.max_mb) {
    caja.innerHTML = `<div class="nota aviso">El archivo pesa ${mb.toFixed(1)} MB: es demasiado grande para pasarlo con el marcador (máximo ${c.max_mb} MB). Súbelo a mano en WebClass.</div>`;
    return;
  }
  const tipo = tipoSugerido || sug.tipo;
  caja.innerHTML = `
    <div class="rejilla">
      <div class="campo"><label for="r-nombre">Nombre del recurso</label><input type="text" id="r-nombre" value="${esc(nombreSugerido)}"></div>
      <div class="campo"><label for="r-autor">Autor</label><input type="text" id="r-autor" value="${esc(compartido.perfil?.nombre_docente || "")}"></div>
      <div class="campo"><label for="r-tipo">Tipo en WebClass</label>
        <select id="r-tipo">${c.tipos_recurso.map((t) => `<option ${t === tipo ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div>
      <div class="campo"><label for="r-asig">Asignatura</label>
        <select id="r-asig">${c.asignaturas_recurso.map((a) => `<option>${esc(a)}</option>`).join("")}</select>
        <span class="ayuda">¿Falta tu asignatura? Agrégala en <a href="#/perfil">Mi perfil</a> con su id de WebClass.</span></div>
      <div class="campo ancho"><span class="etiqueta">Nivel(es)</span><div class="opciones">${c.niveles.map((n) => `
        <label class="casilla"><input type="checkbox" data-nivel="${esc(n)}" ${n === sug.nivel ? "checked" : ""}><span>${esc(n)}</span></label>`).join("")}</div></div>
      <label class="casilla ancho"><input type="checkbox" id="r-visible" checked><span>Visible para las estudiantes</span></label>
    </div>
    <div class="barra espaciada"><button class="btn exito" id="r-copiar" type="button">📤 Copiar recurso para WebClass</button>
      <span class="ayuda">Archivo: ${esc(archivo.name)} (${mb.toFixed(1)} MB)</span></div>
    <p class="ayuda espaciada">Luego, en WebClass abre Recursos → «Subir recurso» y haz clic en tu marcador «Llenar WebClass». Revisa y presiona «Guardar».</p>`;
  $("#r-copiar", caja).onclick = async () => {
    const niveles = [...caja.querySelectorAll("[data-nivel]:checked")].map((i) => i.dataset.nivel);
    const nombre = $("#r-nombre", caja).value.trim(), autor = $("#r-autor", caja).value.trim();
    if (!nombre || !autor || !niveles.length) { aviso("Escribe el nombre y el autor, y elige al menos un nivel.", "error"); return; }
    try {
      const r = await api.form("/api/webclass/recurso", { nombre, autor, niveles, asignatura: $("#r-asig", caja).value,
        visible: $("#r-visible", caja).checked, tipo: $("#r-tipo", caja).value }, { archivo });
      const ok = await copiar(r.json);
      aviso(ok ? "✓ Copiado. En WebClass: Recursos → «Subir recurso» y tu marcador." : "No se pudo copiar automáticamente.", ok ? "ok" : "error");
    } catch (e) { aviso(e.message, "error"); }
  };
}

export async function montarRecurso(cont) {
  const c = await api.get("/api/webclass/constantes");
  cont.innerHTML = `
    <header class="cabecera"><h1>Subir a WebClass</h1>
      <p>Sube guías, evaluaciones u otros archivos a Recursos de WebClass con el marcador «Llenar WebClass».</p></header>
    <section class="tarjeta"><h2>Archivo</h2>
      <div class="campo espaciada"><label for="r-archivo">Archivo a subir (PDF, Word, Excel, PowerPoint, imagen, audio o video)</label>
        <input type="file" id="r-archivo" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.png,.mp3,.mp4"></div>
      <div id="panel-recurso" class="espaciada"></div></section>
    <section class="tarjeta"><h2>¿Cómo funciona?</h2>
      <ol><li>Sube el archivo, revisa nombre, tipo, nivel y asignatura, y presiona <b>Copiar recurso para WebClass</b>.</li>
      <li>En WebClass ve a <b>Recursos → Subir recurso</b>.</li>
      <li>Haz clic en tu marcador <b>Llenar WebClass</b>: elige el tipo, escribe nombre y autor, marca niveles, asignatura y visibilidad, y adjunta el archivo.</li>
      <li>Revisa y presiona <b>Guardar</b>.</li></ol>
      <p class="ayuda">Es el mismo marcador de las clases. Si lo creaste antes de esta versión, reemplaza su URL por este código (clic derecho sobre el marcador → Editar):</p>
      <textarea class="codigo" readonly id="codigo-marcador">${esc(c.enlace_marcador)}</textarea>
      <div class="barra"><button class="btn" id="copiar-marcador" type="button">Copiar código del marcador</button></div></section>`;
  $("#copiar-marcador").onclick = async () => aviso((await copiar(c.enlace_marcador)) ? "Código copiado." : "No se pudo copiar.", "ok");
  $("#r-archivo").onchange = (e) => {
    const f = e.target.files[0];
    if (f) panelRecurso($("#panel-recurso"), { archivo: f, nombreSugerido: f.name.replace(/\.[^.]+$/, "").replace(/_/g, " ") });
    else $("#panel-recurso").innerHTML = "";
  };
}
