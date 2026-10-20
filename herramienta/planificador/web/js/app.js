// Enrutador, estado de la IA y datos compartidos (perfil).
import { api } from "./api.js";
import { compartido, olvidarBarra, recargarIA, recargarPerfil } from "./estado.js";
import { $, $$, aviso, confirmar, esc, pintarIconos } from "./util.js";
import { cargarTema } from "./tema.js";
import { montarPlanificar } from "./planificar.js";
import { montarHistorial } from "./historial.js";
import { montarPie } from "./pie.js";
import { montarRecurso } from "./recurso.js";
import { montarPerfil } from "./perfil.js";

const RUTAS = {
  planificar: [montarPlanificar, "Planificar una clase"],
  historial: [montarHistorial, "Historial"],
  "guia-pie": [montarPie, "Guía PIE"],
  webclass: [montarRecurso, "Subir a WebClass"],
  perfil: [montarPerfil, "Mi perfil"],
};

async function navegar() {
  const pedida = (location.hash.replace(/^#\//, "") || "planificar").split("?")[0];
  const ruta = RUTAS[pedida] ? pedida : "planificar";
  const [montar, titulo] = RUTAS[ruta];
  document.title = `${titulo} · Planificador`;
  $$("#menu a").forEach((a) => (a.dataset.ruta === ruta ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  const cont = $("#contenido");
  cont.innerHTML = "";
  try {
    await montar(cont);
  } catch (e) {
    cont.innerHTML = `<div class="nota error">No se pudo cargar esta sección: ${esc(e.message)}</div>`;
  }
  cont.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

// ── Si el servidor se cierra (se apagó el PC, se cerró desde la barra o pasaron horas sin uso), se dice qué hacer ──
function vigilarServidor() {
  const banner = $("#caido");
  document.addEventListener("servidor-caido", () => { banner.hidden = false; });
  document.addEventListener("servidor-vuelve", () => { banner.hidden = true; });
  $("#reintentar").addEventListener("click", async () => {
    try {
      await api.get("/api/identidad");
      banner.hidden = true;
      aviso("El planificador volvió. Si algo falla, recarga la página (F5).");
    } catch { aviso("Todavía no responde. Ábrelo desde la barra con el botón «Planificar».", "error"); }
  });
}

// ── Diálogo de claves y proveedor de IA ──
async function abrirDialogoIA() {
  const ia = await recargarIA();
  const form = $("#form-ia");
  const proveedores = Object.entries(ia.proveedores || {});
  const delColegio = proveedores.some(([, p]) => p.colegio);
  // Las claves del colegio nunca llegan al navegador: solo se sabe si el proveedor trae una.
  const filas = proveedores.map(([nombre, p]) => `
    <div class="campo">
      <label for="clave-${esc(nombre)}">${esc(nombre)}
        ${p.colegio ? `<span class="ayuda">· incluida por el colegio ✓</span>` : ""}
        ${p.guardada ? `<span class="ayuda">· tu clave ${esc(p.final)}</span>
          <button class="btn chico" type="button" data-quitar="${esc(nombre)}">Quitar la mía</button>` : ""}</label>
      <input type="password" id="clave-${esc(nombre)}" data-prov="${esc(nombre)}" autocomplete="off"
             placeholder="${p.guardada ? "Deja vacío para conservarla" : p.colegio ? "Opcional: agrega tu propia clave (extra)" : "Pega tu clave"}">
      <span class="ayuda">Clave gratuita en <b>${esc(p.ayuda)}</b></span>
    </div>`).join("");
  const conClave = proveedores.filter(([, p]) => p.guardada || p.colegio).map(([n]) => n);
  const notaColegio = {
    sin_codigo: "Tu colegio reparte claves de IA, pero falta la <b>clave del colegio</b> en este PC: pégala en la barra (⚙ Ajustes → Profesor → «Clave del colegio»).",
    codigo_incorrecto: "La clave del colegio de este PC no abre las claves del colegio: revísala en la barra (⚙ Ajustes → Profesor → «Clave del colegio»).",
  }[ia.colegio];
  form.innerHTML = `
    <div><h2>Conectar la IA</h2>
    <p class="sub">${delColegio
      ? "El colegio ya trae claves de IA: no necesitas hacer nada. Si quieres, agrega una tuya como extra: se usa primero y, cuando llega a su límite, sigue la del colegio."
      : "Basta con una clave. Con varias, la app pasa sola a la siguiente cuando una llega a su límite."} Las claves se guardan solo en este equipo.</p></div>
    ${notaColegio ? `<div class="nota aviso">${notaColegio}</div>` : ""}
    ${filas}
    <div class="rejilla">
      <div class="campo"><label for="prov-principal">Proveedor principal</label>
        <select id="prov-principal">${conClave.map((n) => `<option ${n === ia.proveedor ? "selected" : ""}>${esc(n)}</option>`).join("") || "<option value=''>Guarda una clave primero</option>"}</select></div>
      <div class="campo"><label for="modelo-ia">Modelo</label><select id="modelo-ia"><option value="">Automático</option></select></div>
    </div>
    <label class="casilla"><input type="checkbox" id="respaldo-ia" ${ia.respaldo !== false ? "checked" : ""}>
      <span>Si llega al límite, usar otro proveedor automáticamente</span></label>
    <div id="estado-conexion" class="ayuda"></div>
    <div class="barra"><button class="btn primario" type="button" id="guardar-ia">Guardar</button>
      <button class="btn" type="button" id="cerrar-ia">Cerrar</button></div>`;
  const dlg = $("#dialogo-ia");
  const cargarModelos = async () => {
    const prov = $("#prov-principal").value;
    const sel = $("#modelo-ia");
    if (!prov) return;
    $("#estado-conexion").textContent = "Conectando…";
    try {
      const r = await api.get(`/api/ia/modelos?proveedor=${encodeURIComponent(prov)}`);
      sel.innerHTML = r.modelos.map((m) => `<option ${m === ia.modelo ? "selected" : ""}>${esc(m)}</option>`).join("");
      $("#estado-conexion").textContent = r.conectado ? `✓ ${prov} conectado` : `No se pudo conectar: ${r.error || "revisa la clave"}`;
    } catch (e) {
      $("#estado-conexion").textContent = e.message;
    }
  };
  $("#prov-principal").onchange = cargarModelos;
  $("#cerrar-ia").onclick = () => dlg.close();
  $$("[data-quitar]", form).forEach((b) => {
    b.onclick = async () => {
      try {
        await api.post("/api/ia/claves", { [b.dataset.quitar]: "" });    // "" borra solo la tuya; la del colegio sigue
        aviso(`Se quitó tu clave de ${b.dataset.quitar}.`);
        dlg.close();
        abrirDialogoIA();
      } catch (e) { aviso(e.message, "error"); }
    };
  });
  $("#guardar-ia").onclick = async () => {
    const claves = {};
    $$("input[data-prov]", form).forEach((i) => { if (i.value.trim()) claves[i.dataset.prov] = i.value.trim(); });
    try {
      if (Object.keys(claves).length) await api.post("/api/ia/claves", claves);
      await api.post("/api/ia/config", { proveedor: $("#prov-principal").value || null, modelo: $("#modelo-ia").value || null,
        respaldo: $("#respaldo-ia").checked });
      await recargarIA();
      aviso("Configuración de IA guardada.");
      dlg.close();
      if (Object.keys(claves).length) navegar();
    } catch (e) { aviso(e.message, "error"); }
  };
  dlg.showModal();
  cargarModelos();
}

async function iniciar() {
  pintarIconos();
  vigilarServidor();
  $("#estado-ia").addEventListener("click", abrirDialogoIA);
  document.addEventListener("abrir-ia", abrirDialogoIA);
  $("#cerrar-app").addEventListener("click", async () => {
    const si = await confirmar({ titulo: "¿Cerrar el planificador?", texto: "Para volver a usarlo, ábrelo desde la barra con el botón «Planificar».",
      si: "Cerrar el planificador" });
    if (!si) return;
    try { await api.post("/api/apagar", {}); } catch { /* el servidor se cierra antes de responder */ }
    document.body.innerHTML = '<main class="contenido"><h1>Planificador cerrado</h1><p>Ya puedes cerrar esta pestaña.</p></main>';
  });
  window.addEventListener("hashchange", navegar);
  // Si en Barra se cambia de profesor, el planificador cambia con la barra (perfil, claves de IA, historial…); y si en la
  // barra se cambió el color, también se ve aquí
  const vigilarCuenta = async () => {
    try {
      const c = await api.get("/api/cuenta");
      cargarTema();
      if (compartido.cuenta && c.clave !== compartido.cuenta.clave) {
        aviso(`Cambió la cuenta de Barra: ahora es ${c.nombre || c.clave}. Se cargaron sus datos.`);
        olvidarBarra();
        await Promise.all([recargarPerfil(), recargarIA()]);
        await navegar();
      }
    } catch { /* sin conexión: se reintenta en el próximo aviso */ }
  };
  window.addEventListener("focus", vigilarCuenta);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) vigilarCuenta(); });
  cargarTema();
  await Promise.all([recargarPerfil().catch(() => {}), recargarIA()]);
  api.get("/api/version").then((v) => {
    $("#version-app").textContent = `Planificador ${v.planificador || "?"}${v.barra ? ` · Barra ${v.barra}` : ""}`;
    if (!v.compatible) aviso(v.mensaje, "error");
  }).catch(() => {});
  await navegar();
}

iniciar();
