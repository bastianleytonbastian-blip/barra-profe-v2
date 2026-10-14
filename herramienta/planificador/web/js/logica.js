// Lógica pura de la pantalla de planificación (sin DOM ni variables globales): se prueba con `node --test web/js/logica.test.mjs`.

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
