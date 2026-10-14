// Página «Mi perfil»: datos del docente y del colegio, actividades especiales, ids de WebClass y currículo.
import { api } from "./api.js";
import { recargarPerfil } from "./estado.js";
import { $, $$, aviso, esc } from "./util.js";

const VOCES = { neutra: "Neutra (estudiantes)", femenina: "Femenina (las estudiantes)", masculina: "Masculina (los estudiantes)" };

export async function montarPerfil(cont) {
  const [p, { todas, hay }] = await Promise.all([api.get("/api/perfil"), api.get("/api/curriculo/asignaturas")]);
  cont.innerHTML = `
    <header class="cabecera"><h1>Mi perfil</h1>
      <p>Estos datos personalizan las planificaciones, las guías PIE y los archivos que genera la app. Se guardan solo en este equipo.</p></header>
    ${p.completo ? "" : `<div class="nota info">Completa al menos tu nombre y el colegio para empezar.</div>`}
    <section class="tarjeta"><h2>Docente y colegio</h2>
      <div class="rejilla espaciada">
        <div class="campo"><label for="f-nombre">Tu nombre</label><input type="text" id="f-nombre" value="${esc(p.nombre_docente)}" placeholder="Ej: Ana Pérez"></div>
        <div class="campo"><label for="f-colegio">Colegio</label><input type="text" id="f-colegio" value="${esc(p.colegio)}"></div>
        <div class="campo"><label for="f-depto">Departamento o área <span class="ayuda">(opcional)</span></label><input type="text" id="f-depto" value="${esc(p.departamento)}" placeholder="Ej: Departamento de Matemática"></div>
        <div class="campo"><label for="f-trat">Cómo se nombra al docente en el texto</label><input type="text" id="f-trat" value="${esc(p.tratamiento_docente)}">
          <span class="ayuda">Ej: el profesor, la profesora, la docente.</span></div>
        <div class="campo ancho"><label for="f-contexto">Contexto del colegio <span class="ayuda">(opcional)</span></label>
          <textarea id="f-contexto" placeholder="Ej: colegio católico de Recoleta, con fuerte vínculo comunitario">${esc(p.contexto_colegio)}</textarea></div>
        <div class="campo"><label for="f-logo">Logo del colegio <span class="ayuda">(opcional, sale en las guías PIE)</span></label>
          <input type="file" id="f-logo" accept="image/png,image/jpeg">
          ${p.ruta_logo ? `<div class="barra"><img src="/api/perfil/logo?t=${Date.now()}" alt="Logo actual" height="44"><button class="btn chico peligro" id="quitar-logo" type="button">Quitar</button></div>` : ""}</div>
      </div></section>
    <section class="tarjeta"><h2>Cómo planificas</h2>
      <div class="rejilla espaciada">
        <div class="campo"><span class="etiqueta">Cómo se redacta el curso</span><div class="opciones">${p.voces.map((v) => `
          <label class="casilla"><input type="radio" name="f-voz" value="${v}" ${p.voz === v ? "checked" : ""}><span>${VOCES[v]}</span></label>`).join("")}</div></div>
        <div class="campo"><label for="f-dur">Duración habitual de una clase (minutos)</label><input type="number" id="f-dur" min="30" max="240" step="5" value="${p.duracion_defecto}"></div>
        <div class="campo"><label for="f-apertura">Primera línea fija del Inicio <span class="ayuda">(opcional)</span></label><input type="text" id="f-apertura" value="${esc(p.apertura_fija)}">
          <span class="ayuda">Un lema o saludo institucional al comienzo de cada clase.</span></div>
        <div class="campo ancho"><label for="f-enfoque">Enfoque pedagógico que debe seguir la IA <span class="ayuda">(opcional)</span></label>
          <textarea id="f-enfoque" placeholder="Si lo dejas vacío, se usa un enfoque estándar según la asignatura.">${esc(p.enfoque_pedagogico)}</textarea></div>
        <div class="campo ancho"><span class="etiqueta">Asignaturas que enseñas</span>
          <span class="ayuda">Solo estas aparecen al planificar. Si no marcas ninguna, aparecen todas.</span>
          <div class="lista-scroll">${todas.map((a) => `<label class="casilla"><input type="checkbox" data-asig="${esc(a)}" ${p.asignaturas.includes(a) ? "checked" : ""}><span>${esc(a)}</span></label>`).join("") || '<p class="vacio">Descarga el currículo para ver las asignaturas.</p>'}</div></div>
      </div></section>
    <section class="tarjeta"><h2>Actividades especiales</h2>
      <p class="sub">Actividades que se reservan dentro de la clase en ciertos cursos (por ejemplo, mindfulness o lectura silenciosa).</p>
      <div id="extras"></div><button class="btn chico" id="mas-extra" type="button">+ Agregar actividad</button></section>
    <section class="tarjeta"><h2>Asignaturas de WebClass</h2>
      <p class="sub">WebClass identifica cada asignatura con un número. Si la tuya no aparece al subir un recurso, agrégala aquí. El número es el <i>value</i> de la opción en el selector «Asignatura» del formulario «Subir recurso» (clic derecho → Inspeccionar).</p>
      <div id="asig-wc"></div><button class="btn chico" id="mas-asig" type="button">+ Agregar asignatura</button></section>
    <section class="tarjeta"><h2>Cuenta de Barra Profe</h2>
      ${p.cuenta.en_barra ? `
        <p class="sub">Este planificador viaja dentro de Barra Profe y trabaja <b>siempre con la cuenta que está activa en la barra</b>. Lo que ves aquí
        (perfil, claves de IA, historial y archivos) es de esa cuenta; si en la barra cambias de profesor, esto cambia con ella. Tu contraseña de WebClass
        nunca pasa por aquí: la usa solo Barra, desde el Administrador de credenciales de Windows.</p>
        <div class="nota ok"><b>Cuenta activa:</b> ${esc(p.cuenta.nombre || p.cuenta.clave)} · <code>${esc(p.cuenta.clave)}</code>
          ${p.cuenta.perfiles.length > 1 ? `<br><span class="ayuda">Otras cuentas en este equipo: ${esc(p.cuenta.perfiles.filter((c) => c !== p.cuenta.clave).join(", "))}. Para cambiar, usa «Cambiar de profesor» en la barra.</span>` : ""}</div>`
      : `
        <p class="sub">Si usas «Barra Profe» para manejar WebClass, esta app puede crear tus clases directamente en WebClass, sin copiar y pegar.
        Solo lee su código: no modifica nada de esa carpeta, y tu contraseña de WebClass nunca pasa por aquí.</p>
        <div class="rejilla">
          <div class="campo ancho"><label for="f-barra">Carpeta de Barra Profe</label>
            <div class="barra"><input type="text" id="f-barra" value="${esc(p.ruta_barra)}" placeholder="Ej: C:\Users\tu-usuario\Desktop\Barra Profe v2" style="flex:1">
              <button class="btn" id="verificar-barra" type="button">Verificar</button></div>
            <span class="ayuda" id="barra-estado"></span></div>
        </div>`}</section>
    <section class="tarjeta"><h2>Currículo oficial (MINEDUC)</h2>
      <p class="sub">${hay ? "Los Objetivos de Aprendizaje están descargados." : "Aún no hay currículo descargado."} Se descarga de curriculumnacional.cl: todas las asignaturas, de 1° Básico a 4° Medio.</p>
      <div class="barra"><button class="btn" id="actualizar-curr" type="button">${hay ? "Actualizar currículo" : "Descargar currículo"}</button><span class="ayuda" id="curr-estado"></span></div></section>
    <div class="barra"><button class="btn primario grande" id="guardar-perfil" type="button">💾 Guardar perfil</button></div>`;

  const filaExtra = (e = {}) => `<div class="fila-editable" data-extra>
    <input type="text" data-k="nombre" placeholder="Nombre" value="${esc(e.nombre || "")}" aria-label="Nombre">
    <input type="text" data-k="curso" placeholder="Curso (ej. 7° Básico)" value="${esc(e.curso || "")}" aria-label="Curso">
    <input type="number" data-k="minutos" placeholder="Min" min="0" value="${esc(e.minutos || "")}" aria-label="Minutos">
    <input type="text" data-k="descripcion" placeholder="Qué hacen" value="${esc(e.descripcion || "")}" aria-label="Descripción">
    <button class="btn chico peligro" type="button" data-quitar aria-label="Quitar">✕</button></div>`;
  const filaAsig = (n = "", i = "") => `<div class="fila-editable dos" data-asigwc>
    <input type="text" data-k="nombre" placeholder="Nombre de la asignatura" value="${esc(n)}" aria-label="Nombre de la asignatura">
    <input type="text" data-k="id" placeholder="Id en WebClass" value="${esc(i)}" aria-label="Id en WebClass">
    <button class="btn chico peligro" type="button" data-quitar aria-label="Quitar">✕</button></div>`;
  $("#extras").innerHTML = (p.actividades_extra || []).map(filaExtra).join("");
  $("#asig-wc").innerHTML = Object.entries(p.asignaturas_webclass || {}).map(([n, i]) => filaAsig(n, i)).join("");
  $("#mas-extra").onclick = () => $("#extras").insertAdjacentHTML("beforeend", filaExtra());
  $("#mas-asig").onclick = () => $("#asig-wc").insertAdjacentHTML("beforeend", filaAsig());
  cont.onclick = (e) => { const q = e.target.closest("[data-quitar]"); if (q) q.parentElement.remove(); };
  $("#quitar-logo")?.addEventListener("click", async () => { await api.borrar("/api/perfil/logo"); montarPerfil(cont); });

  $("#guardar-perfil").onclick = async () => {
    const leer = (fila) => Object.fromEntries($$("[data-k]", fila).map((i) => [i.dataset.k, i.value]));
    const cuerpo = {
      nombre_docente: $("#f-nombre").value.trim(), colegio: $("#f-colegio").value.trim(), departamento: $("#f-depto").value.trim(),
      tratamiento_docente: $("#f-trat").value.trim() || "el profesor", contexto_colegio: $("#f-contexto").value.trim(),
      voz: $("input[name=f-voz]:checked")?.value || "neutra", duracion_defecto: Number($("#f-dur").value) || 90,
      apertura_fija: $("#f-apertura").value.trim(), enfoque_pedagogico: $("#f-enfoque").value.trim(),
      ...($("#f-barra") ? { ruta_barra: $("#f-barra").value.trim().replace(/^"|"$/g, "") } : {}),
      asignaturas: $$("[data-asig]:checked").map((i) => i.dataset.asig),
      actividades_extra: $$("[data-extra]").map(leer),
      asignaturas_webclass: Object.fromEntries($$("[data-asigwc]").map(leer).map((r) => [r.nombre, r.id])),
    };
    try {
      await api.put("/api/perfil", cuerpo);
      const logo = $("#f-logo").files[0];
      if (logo) await api.subir("/api/perfil/logo", "archivo", [logo]);
      await recargarPerfil();
      aviso("Perfil guardado.");
      if (logo) montarPerfil(cont);
    } catch (e) { aviso(e.message, "error"); }
  };

  const verificarBarra = async () => {
    const r = await api.get(`/api/barra/estado?ruta=${encodeURIComponent($("#f-barra").value.trim().replace(/^"|"$/g, ""))}`);
    $("#barra-estado").textContent = r.configurada ? (r.valida ? "✓ " : "✕ ") + r.mensaje : "";
  };
  if ($("#verificar-barra")) {
    $("#verificar-barra").onclick = () => verificarBarra().catch((e) => aviso(e.message, "error"));
    if (p.ruta_barra) verificarBarra().catch(() => {});
  }

  $("#actualizar-curr").onclick = async () => {
    const btn = $("#actualizar-curr"), est = $("#curr-estado");
    btn.disabled = true;
    await api.post("/api/curriculo/actualizar", {});
    const vigilar = async () => {
      const s = await api.get("/api/curriculo/estado");
      if (s.corriendo) { est.textContent = s.total ? `Descargando… ${s.avance} de ${s.total}` : "Descargando…"; setTimeout(vigilar, 1500); return; }
      btn.disabled = false;
      if (s.error) est.textContent = `Error: ${s.error}`;
      else { est.textContent = "✓ Currículo actualizado."; aviso("Currículo actualizado."); montarPerfil(cont); }
    };
    vigilar();
  };
}
