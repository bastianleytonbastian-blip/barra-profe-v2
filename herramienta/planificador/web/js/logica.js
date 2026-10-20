// Lógica pura del planificador (sin DOM ni variables globales): se prueba con `node --test tests/planificador_logica.test.mjs`.

export const sinTildes = (t) => String(t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
export const claveCurso = (t) => { const m = String(t || "").match(/(\d)\s*°?\s*(b|m)/i); return m ? m[1] + m[2].toLowerCase() : ""; };

/** OA de la unidad que mejor calzan con la clase: primero los que la IA propuso, y si no, por palabras en común. */
export function sugerirOA(catalogo, plan) {
  const propuestos = new Set([...(plan.oa_sel || []), ...(plan.oa_texto || "").split(/[\s,;]+/).filter(Boolean)]);
  const exactos = catalogo.filter((o) => propuestos.has(o.etiqueta));
  if (exactos.length) return new Set(exactos.map((o) => o.etiqueta));
  const palabras = (t) => new Set(sinTildes(t).split(/[^a-z0-9ñ]+/).filter((p) => p.length > 4));
  const objetivo = (plan.inicio || "").match(/Objetivo de Aprendizaje:\s*(.+)/i)?.[1] || "";
  const clase = palabras([plan.nombre, plan.tema, objetivo, plan.oa_claves].join(" "));
  const puntajes = catalogo.map((o) => [o, [...palabras(o.texto)].filter((p) => clase.has(p)).length]);
  const mejor = Math.max(0, ...puntajes.map(([, n]) => n));
  return new Set(mejor >= 2 ? puntajes.filter(([, n]) => n === mejor).slice(0, 2).map(([o]) => o.etiqueta) : []);
}

// ── Cursos hermanos: la misma unidad en el otro curso (5BA ↔ 5BB) ──
const PREFIJO_CURSO = /^\s*\d+\s*[a-z]{1,2}\b[\s\-:.]*/i;
export const palabrasUnidad = (n) => new Set(sinTildes(String(n).replace(PREFIJO_CURSO, "")).split(/[^a-z0-9ñ]+/).filter((p) => p.length > 2 || /^\d+$/.test(p)));
export function similitud(a, b) {
  const A = palabrasUnidad(a), B = palabrasUnidad(b);
  return [...A].filter((x) => B.has(x)).length / Math.max(1, new Set([...A, ...B]).size);
}
export function hermanas(principal, unidadesBarra) {
  const porCurso = {};
  unidadesBarra.filter((u) => String(u.id) !== String(principal.id) && sinTildes(u.asignatura) === sinTildes(principal.asignatura)
    && claveCurso(u.curso) === claveCurso(principal.curso) && u.curso !== principal.curso)
    .forEach((u) => (porCurso[u.curso] ||= []).push({ u, p: similitud(u.nombre, principal.nombre) }));
  return Object.entries(porCurso).map(([curso, lista]) => {
    lista.sort((a, b) => b.p - a.p);
    return { curso, opciones: lista.map((x) => x.u), sugerida: lista[0].p >= 0.5 ? lista[0].u : null };
  });
}

// ── Asignatura y curso con que parte «Planificar una clase» ──

/** La asignatura del currículo que corresponde a un nombre de WebClass. "" si ninguna.
 * Primero igual (sin tildes); después la que es el comienzo del nombre («Ciencias Naturales 5°»); y por último la que
 * empieza con el nombre completo («Historia» → «Historia, Geografía y Ciencias Sociales»). */
export function asignaturaCurricular(asignaturas, nombre) {
  const t = sinTildes(nombre);
  if (!t) return "";
  const exacta = asignaturas.find((a) => sinTildes(a) === t);
  if (exacta) return exacta;
  const sigueOtraPalabra = (texto, inicio) => texto.startsWith(inicio) && /^[^a-z0-9ñ]/.test(texto.slice(inicio.length));
  const larga = asignaturas.filter((a) => sigueOtraPalabra(t, sinTildes(a))).sort((a, b) => b.length - a.length)[0];
  if (larga) return larga;
  return asignaturas.filter((a) => sigueOtraPalabra(sinTildes(a), t)).sort((a, b) => a.length - b.length)[0] || "";
}

/** Qué asignatura y curso dejar elegidos al abrir «Planificar una clase». Manda la unidad que llegó desde la barra;
 * luego lo fijado en Mi perfil; luego lo último que eligió esta cuenta; y si no, su primera unidad de Barra.
 * Devuelve {asignatura, curso, origen}; la asignatura siempre es una de la lista ("" si la lista está vacía). */
export function eleccionInicial({ asignaturas = [], unidad = null, defecto = {}, ultima = null, unidades = [] } = {}) {
  const de = (asig, curso, origen) => {
    const a = asignaturaCurricular(asignaturas, asig);
    return a ? { asignatura: a, curso: curso || defecto?.curso || "", origen } : null;
  };
  return (unidad && de(unidad.asignatura, unidad.curso, "unidad"))
    || (defecto?.asignatura && de(defecto.asignatura, defecto.curso, "perfil"))
    || (ultima?.asignatura && de(ultima.asignatura, ultima.curso, "ultima"))
    || unidades.map((u) => de(u.asignatura, u.curso, "barra")).find(Boolean)
    || { asignatura: asignaturas[0] || "", curso: defecto?.curso || "", origen: "" };
}

/** Cursos de la lista separados en los del docente (los de sus unidades de Barra en esa asignatura) y los demás. */
export function cursosPrimero(cursos, unidades, asignatura) {
  const claves = new Set(unidades.filter((u) => asignaturaCurricular([asignatura], u.asignatura))
    .map((u) => claveCurso(u.curso)).filter(Boolean));
  const mios = cursos.filter((c) => claves.has(claveCurso(c)));
  return { mios, otros: cursos.filter((c) => !mios.includes(c)) };
}

/** El curso de la lista que corresponde a otro escrito distinto («5BA» ↔ «5° Básico»). "" si ninguno. */
export const cursoEquivalente = (cursos, curso) =>
  cursos.find((c) => c === curso) || (claveCurso(curso) && cursos.find((c) => claveCurso(c) === claveCurso(curso))) || "";

// ── Texto en vivo mientras la IA escribe ──
const SECCIONES_IA = { INICIO: "Inicio", DESARROLLO: "Desarrollo", CIERRE: "Cierre", NOMBRE: "Nombre de la clase",
  EVALUACION: "Método de evaluación", RECURSOS: "Recursos", ADECUACIONES: "Adecuación curricular", MOTIVACION: "Motivación",
  OA: "Objetivos de aprendizaje", DUA: "Pautas DUA" };

/** Lo que la IA lleva escrito, separado en sus partes: [{titulo, texto}]. Quita las marcas <<<INICIO>>>… y también
 * una marca que todavía viene a medio llegar al final («<<<DESA»). */
export function partesEnVivo(bruto) {
  const limpio = String(bruto || "").replace(/<{1,3}[A-ZÁÉÍÓÚÑ_ ]*>{0,2}$/, "");
  const partes = [];
  let actual = { titulo: "", texto: "" };
  for (const pedazo of limpio.split(/(<<<[A-ZÁÉÍÓÚÑ_ ]+>>>)/)) {
    const marca = pedazo.match(/^<<<([A-ZÁÉÍÓÚÑ_ ]+)>>>$/);
    if (!marca) { actual.texto += pedazo; continue; }
    if (actual.titulo || actual.texto.trim()) partes.push(actual);
    const clave = sinTildes(marca[1]).toUpperCase().trim();
    actual = { titulo: SECCIONES_IA[clave] || marca[1].trim(), texto: "" };
  }
  if (actual.titulo || actual.texto.trim()) partes.push(actual);
  return partes.map((p) => ({ titulo: p.titulo, texto: p.texto.trim() }));
}

// ── Colores: el de la barra como color principal del planificador ──
const luminancia = (hex) => {
  const canales = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * canales[0] + 0.7152 * canales[1] + 0.0722 * canales[2];
};
/** Contraste entre dos colores #rrggbb (de 1 a 21; el texto chico pide al menos 4,5). */
export const contraste = (a, b) => {
  const [claro, oscuro] = [luminancia(a), luminancia(b)].sort((x, y) => y - x);
  return (claro + 0.05) / (oscuro + 0.05);
};
/** Color del texto sobre un botón de ese color: blanco si se lee bien; si no, casi negro. */
export const textoSobre = (hex) => (contraste(hex, "#ffffff") >= 4.5 ? "#ffffff" : "#0c1219");

// ── Editor de la guía PIE por campos ──
const NOMBRES_GUIA = {
  objetivo: "Objetivo", secciones: "Sección", titulo: "Título", pie_imagen: "Pie de la imagen", foto_web: "Foto de internet",
  pie: "Pie de foto", escribir: "Escribir", marcar: "Marcar", completar: "Completar", instruccion: "Instrucción", frases: "Frase",
  pregunta: "Pregunta", opciones: "Opción", reconocer_unir: "Reconocer y unir", instruccion_reconocer: "Instrucción de reconocer",
  instruccion_unir: "Instrucción de unir", pares: "Par", concepto: "Concepto", para_pensar: "Para pensar",
  pregunta_conversar: "Pregunta para conversar", conceptos_clave: "Concepto clave", cierre: "Cierre",
};

/** Textos de la guía para editarlos uno por uno: [{ruta, texto}] en orden de lectura. `omitir`: claves que no son texto
 * para leer (ids de imagen, búsquedas web, respuesta correcta, pictogramas…), que entrega el servidor. */
export function textosDeGuia(spec, omitir = []) {
  const fuera = new Set(omitir), salida = [];
  const recorrer = (valor, ruta) => {
    if (fuera.has(ruta.findLast((p) => typeof p === "string"))) return;
    if (typeof valor === "string") { if (valor.trim()) salida.push({ ruta, texto: valor }); }
    else if (Array.isArray(valor)) valor.forEach((v, i) => recorrer(v, [...ruta, i]));
    else if (valor && typeof valor === "object") Object.entries(valor).forEach(([k, v]) => recorrer(v, [...ruta, k]));
  };
  recorrer(spec, []);
  return salida;
}

/** Valor de la guía en esa ruta (undefined si no existe). */
export const valorEn = (spec, ruta) => ruta.reduce((v, p) => (v == null ? undefined : v[p]), spec);

/** Copia de la guía con un texto cambiado (no modifica la original). */
export function conTexto(spec, ruta, texto) {
  if (!ruta.length) return texto;
  const [cabeza, ...resto] = ruta;
  const copia = Array.isArray(spec) ? [...spec] : { ...spec };
  copia[cabeza] = conTexto(spec?.[cabeza], resto, texto);
  return copia;
}

/** Nombre legible de una ruta: ["secciones", 1, "escribir", "frases", 2] → «Sección 2 · Escribir · Frase 3». */
export function etiquetaDeRuta(ruta) {
  const partes = [];
  for (const p of ruta) {
    if (typeof p === "number") partes.push(`${partes.pop() ?? ""} ${p + 1}`.trim());
    else partes.push(NOMBRES_GUIA[p] || p.replace(/_/g, " "));
  }
  return partes.join(" · ");
}

// ── Historial ──
/** "5b" → «5° Básico»; "2m" → «2° Medio». */
export const etiquetaNivel = (clave) => (clave ? `${clave[0]}° ${clave[1] === "b" ? "Básico" : "Medio"}` : "");
const ordenNivel = (a, b) => (a[1] === b[1] ? Number(a[0]) - Number(b[0]) : a[1] === "b" ? -1 : 1);
const nivelesDe = (it) => [it.curso, ...(it.webclass || []).map((w) => w.curso)].map(claveCurso).filter(Boolean);

/** Niveles presentes en el historial, de 1° Básico a 4° Medio (para el filtro). */
export const nivelesDelHistorial = (items) => [...new Set(items.flatMap(nivelesDe))].sort(ordenNivel);

/** Historial filtrado por texto (nombre, tema, asignatura, curso o unidad) y por nivel ("5b"). */
export function filtrarHistorial(items, { texto = "", nivel = "" } = {}) {
  const q = sinTildes(texto);
  return items.filter((it) => (!nivel || nivelesDe(it).includes(nivel)) && (!q || sinTildes([it.nombre, it.tema, it.asignatura, it.curso,
    ...(it.webclass || []).flatMap((w) => [w.curso, w.unidad])].join(" ")).includes(q)));
}
