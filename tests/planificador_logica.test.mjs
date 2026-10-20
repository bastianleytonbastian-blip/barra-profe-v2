// Pruebas de la lógica pura del planificador (sin DOM). Se ejecutan con:  node --test tests/planificador_logica.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import {
  asignaturaCurricular, claveCurso, conTexto, contraste, cursoEquivalente, cursosPrimero, eleccionInicial, etiquetaDeRuta, etiquetaNivel,
  filtrarHistorial, hermanas, nivelesDelHistorial, partesEnVivo, similitud, sinTildes, sugerirOA, textoSobre, textosDeGuia, valorEn,
} from "../herramienta/planificador/web/js/logica.js";

const unidades = [
  { id: 1, curso: "5BA", asignatura: "Ciencias Naturales", nombre: "5BA - Unidad 1: El agua en la Tierra" },
  { id: 2, curso: "5BB", asignatura: "Ciencias Naturales", nombre: "5BB - Unidad 1:El agua en la Tierra" },
  { id: 3, curso: "5BB", asignatura: "Ciencias Naturales", nombre: "5BB - Unidad 2: Seres vivos y alimentación." },
  { id: 4, curso: "5BA", asignatura: "Ciencias Naturales", nombre: "5A - Energía y circuitos eléctricos." },
  { id: 5, curso: "5BB", asignatura: "Ciencias Naturales", nombre: "5B - Energía y circuitos eléctricos." },
  { id: 6, curso: "5BB", asignatura: "Orientación", nombre: "Unidad: Trabajo Escolar." },
  { id: 7, curso: "8BB", asignatura: "Ciencias Naturales", nombre: "8BB - Unidad 1: Estructura celular" },
];

test("claveCurso entiende «5° Básico», «5BA», «1° Medio» y «1MA»", () => {
  assert.equal(claveCurso("5° Básico"), "5b");
  assert.equal(claveCurso("5BA"), "5b");
  assert.equal(claveCurso("1° Medio"), "1m");
  assert.equal(claveCurso("1MA"), "1m");
  assert.equal(claveCurso("sin nivel"), "");
  assert.equal(claveCurso(null), "");
});

test("sinTildes quita tildes y mayúsculas", () => {
  assert.equal(sinTildes("  Orientación "), "orientacion");
  assert.equal(sinTildes(undefined), "");
});

test("similitud ignora el prefijo del curso y distingue unidades", () => {
  assert.equal(similitud("5A - Energía y circuitos eléctricos.", "5B - Energía y circuitos eléctricos."), 1);
  assert.ok(similitud(unidades[0].nombre, unidades[1].nombre) >= 0.5, "la misma unidad en el otro curso");
  assert.ok(similitud(unidades[0].nombre, unidades[2].nombre) < 0.5, "Unidad 1 no es Unidad 2");
});

test("hermanas sugiere la unidad equivalente del otro curso, de la misma asignatura y nivel", () => {
  const h = hermanas(unidades[0], unidades);
  assert.equal(h.length, 1);
  assert.equal(h[0].curso, "5BB");
  assert.equal(h[0].sugerida.id, 2);
  const ids = h[0].opciones.map((u) => u.id);
  assert.ok(!ids.includes(6), "otra asignatura no entra");
  assert.ok(!ids.includes(7), "otro nivel no entra");
  assert.ok(!ids.includes(1), "no se ofrece a sí misma");
});

test("hermanas también empareja unidades de nombre con distinto prefijo (5A ↔ 5B)", () => {
  assert.equal(hermanas(unidades[3], unidades)[0].sugerida.id, 5);
});

test("hermanas no sugiere nada si ninguna unidad se parece", () => {
  const raro = { id: 9, curso: "5BA", asignatura: "Ciencias Naturales", nombre: "5BA - Taller de robótica avanzada" };
  assert.equal(hermanas(raro, [raro, ...unidades])[0].sugerida, null);
});

const catalogo = [
  { id: "1", etiqueta: "OA12", texto: "Describir la distribución del agua dulce y salada en la Tierra, considerando océanos, glaciares, ríos" },
  { id: "2", etiqueta: "OA14", texto: "Investigar y explicar efectos de la actividad humana en océanos, lagos, ríos, glaciares" },
];

test("sugerirOA respeta los OA que propuso la IA si existen en la unidad", () => {
  assert.deepEqual([...sugerirOA(catalogo, { oa_sel: ["OA14"] })], ["OA14"]);
});

test("sugerirOA elige por palabras en común cuando los OA propuestos no existen en la unidad", () => {
  const plan = { oa_sel: ["OA1"], nombre: "Distribución del agua dulce y salada", tema: "agua salada océanos", inicio: "", oa_claves: "" };
  assert.deepEqual([...sugerirOA(catalogo, plan)], ["OA12"]);
});

test("sugerirOA no marca nada si no hay coincidencias suficientes", () => {
  const plan = { oa_sel: [], nombre: "Fracciones equivalentes", tema: "matemática", inicio: "", oa_claves: "" };
  assert.equal(sugerirOA(catalogo, plan).size, 0);
});

// ── Asignatura y curso con que parte «Planificar una clase» ──
const ASIGNATURAS = ["Ciencias Naturales", "Ciencias de la salud", "Educación Física y Salud", "Física",
  "Historia, Geografía y Ciencias Sociales", "Lenguaje y Comunicación", "Orientación", "Taller de literatura"];

test("asignaturaCurricular calza nombres de WebClass con el currículo sin confundir parecidos", () => {
  assert.equal(asignaturaCurricular(ASIGNATURAS, "Ciencias Naturales"), "Ciencias Naturales");
  assert.equal(asignaturaCurricular(ASIGNATURAS, "  orientacion "), "Orientación");
  assert.equal(asignaturaCurricular(ASIGNATURAS, "Ciencias Naturales 5° Básico"), "Ciencias Naturales");
  assert.equal(asignaturaCurricular(ASIGNATURAS, "Historia"), "Historia, Geografía y Ciencias Sociales");
  assert.equal(asignaturaCurricular(ASIGNATURAS, "Ciencias"), "Ciencias Naturales", "entre varias, la más corta");
  assert.equal(asignaturaCurricular(ASIGNATURAS, "Educación Física"), "Educación Física y Salud", "no «Física»");
  assert.equal(asignaturaCurricular(ASIGNATURAS, "Taller Jec Ciencias"), "", "un taller propio no es «Taller de literatura»");
  assert.equal(asignaturaCurricular(ASIGNATURAS, ""), "");
});

const MIS_UNIDADES = [
  { id: 1, curso: "5BA", asignatura: "Ciencias Naturales", nombre: "U1" },
  { id: 2, curso: "5BA", asignatura: "Orientación", nombre: "Trabajo escolar" },
  { id: 3, curso: "8BB", asignatura: "Ciencias Naturales", nombre: "Célula" },
];

test("eleccionInicial: manda la unidad de la barra, luego Mi perfil, luego lo último y al final las unidades", () => {
  const base = { asignaturas: ASIGNATURAS, unidades: MIS_UNIDADES };
  assert.deepEqual(eleccionInicial({ ...base, unidad: MIS_UNIDADES[1], defecto: { asignatura: "Física" }, ultima: { asignatura: "Historia" } }),
    { asignatura: "Orientación", curso: "5BA", origen: "unidad" });
  assert.equal(eleccionInicial({ ...base, defecto: { asignatura: "Física", curso: "1° Medio" }, ultima: { asignatura: "Orientación" } }).origen, "perfil");
  assert.deepEqual(eleccionInicial({ ...base, ultima: { asignatura: "Orientación", curso: "5° Básico" } }),
    { asignatura: "Orientación", curso: "5° Básico", origen: "ultima" });
  assert.deepEqual(eleccionInicial(base), { asignatura: "Ciencias Naturales", curso: "5BA", origen: "barra" });
  assert.deepEqual(eleccionInicial({ asignaturas: ASIGNATURAS }), { asignatura: "Ciencias Naturales", curso: "", origen: "" });
  assert.equal(eleccionInicial({ asignaturas: ASIGNATURAS, ultima: { asignatura: "Asignatura borrada" } }).origen, "",
    "lo último que ya no existe no se usa");
  assert.equal(eleccionInicial({ asignaturas: ASIGNATURAS, defecto: { curso: "7° Básico" } }).curso, "7° Básico",
    "un curso fijado en Mi perfil vale aunque no haya asignatura fijada");
});

test("cursosPrimero pone primero los cursos de mis unidades en esa asignatura", () => {
  const cursos = ["1° Básico", "5° Básico", "6° Básico", "8° Básico"];
  assert.deepEqual(cursosPrimero(cursos, MIS_UNIDADES, "Ciencias Naturales"), { mios: ["5° Básico", "8° Básico"], otros: ["1° Básico", "6° Básico"] });
  assert.deepEqual(cursosPrimero(cursos, MIS_UNIDADES, "Orientación").mios, ["5° Básico"]);
  assert.deepEqual(cursosPrimero(cursos, [], "Orientación"), { mios: [], otros: cursos });
});

test("cursoEquivalente entiende el curso de WebClass y el del currículo", () => {
  const cursos = ["5° Básico", "1° Medio"];
  assert.equal(cursoEquivalente(cursos, "5BA"), "5° Básico");
  assert.equal(cursoEquivalente(cursos, "1° Medio"), "1° Medio");
  assert.equal(cursoEquivalente(cursos, "3MA"), "");
  assert.equal(cursoEquivalente(cursos, ""), "");
});

test("textoSobre elige texto blanco o negro con contraste suficiente", () => {
  for (const color of ["#5b3fc4", "#1f5aa8", "#a78bfa", "#ffd400", "#1d1d1d", "#6ee7b7"]) {
    assert.ok(contraste(color, textoSobre(color)) >= 4.5, color);
  }
  assert.equal(textoSobre("#1d1d1d"), "#ffffff");
  assert.equal(textoSobre("#ffd400"), "#0c1219");
});

// ── Editor de la guía PIE por campos ──
const GUIA = {
  objetivo: "COMPRENDER EL CICLO DEL AGUA.",
  secciones: [
    { titulo: "EL AGUA", imagen: "img1", foto_web: { busqueda: "lluvia", pie: "LA LLUVIA." },
      escribir: { instruccion: "ESCRIBIR.", frases: ["EL AGUA CAE.", "EL SOL CALIENTA."] },
      marcar: { instruccion: "MARCAR.", pregunta: "¿QUÉ CAE?", opciones: ["AGUA", "ARENA"], correcta: 0 }, completar: null },
  ],
  conceptos_clave: ["AGUA."],
  cierre: { titulo: "PARA TERMINAR", tipo: "dibujar", instruccion: "DIBUJAR LA LLUVIA." },
  picto_extra: { AGUA: "agua" },
};
const OMITIR = ["imagen", "busqueda", "correcta", "picto_extra", "tipo"];

test("textosDeGuia lista solo lo que se lee, en orden, sin ids, búsquedas ni pictogramas", () => {
  const textos = textosDeGuia(GUIA, OMITIR);
  const todos = textos.map((t) => t.texto);
  assert.equal(todos[0], "COMPRENDER EL CICLO DEL AGUA.");
  for (const fuera of ["img1", "lluvia", "agua", "dibujar"]) assert.ok(!todos.includes(fuera), fuera);
  assert.ok(todos.includes("LA LLUVIA."));
  assert.deepEqual(textos.find((t) => t.texto === "EL SOL CALIENTA.").ruta, ["secciones", 0, "escribir", "frases", 1]);
});

test("conTexto cambia un texto sin tocar la guía original ni lo demás", () => {
  const ruta = ["secciones", 0, "marcar", "opciones", 1];
  const nueva = conTexto(GUIA, ruta, "TIERRA");
  assert.equal(valorEn(nueva, ruta), "TIERRA");
  assert.equal(valorEn(GUIA, ruta), "ARENA", "la original queda igual");
  assert.equal(nueva.secciones[0].marcar.correcta, 0);
  assert.equal(nueva.secciones[0].imagen, "img1");
  assert.deepEqual(nueva.picto_extra, GUIA.picto_extra);
});

test("etiquetaDeRuta nombra cada campo en castellano", () => {
  assert.equal(etiquetaDeRuta(["secciones", 1, "escribir", "frases", 2]), "Sección 2 · Escribir · Frase 3");
  assert.equal(etiquetaDeRuta(["conceptos_clave", 0]), "Concepto clave 1");
  assert.equal(etiquetaDeRuta(["objetivo"]), "Objetivo");
});

// ── Historial ──
const HISTORIAL = [
  { nombre: "El ciclo del agua", tema: "agua", asignatura: "Ciencias Naturales", curso: "5° Básico",
    webclass: [{ curso: "5BA", unidad: "Unidad 1" }, { curso: "5BB", unidad: "Unidad 1" }] },
  { nombre: "Célula animal", tema: "", asignatura: "Ciencias Naturales", curso: "8° Básico", webclass: [] },
  { nombre: "Trabajo escolar", tema: "", asignatura: "", curso: "1MA", webclass: [{ curso: "1MA", unidad: "Orientación" }] },
];

test("el historial se filtra por texto sin tildes y por nivel", () => {
  assert.deepEqual(filtrarHistorial(HISTORIAL, { texto: "celula" }).map((x) => x.nombre), ["Célula animal"]);
  assert.deepEqual(filtrarHistorial(HISTORIAL, { texto: "orientacion" }).map((x) => x.nombre), ["Trabajo escolar"]);
  assert.deepEqual(filtrarHistorial(HISTORIAL, { nivel: "5b" }).map((x) => x.nombre), ["El ciclo del agua"]);
  assert.equal(filtrarHistorial(HISTORIAL, {}).length, 3);
  assert.deepEqual(nivelesDelHistorial(HISTORIAL), ["5b", "8b", "1m"]);
  assert.equal(etiquetaNivel("1m"), "1° Medio");
});

// ── Texto en vivo ──
test("partesEnVivo separa lo escrito en sus partes y quita las marcas", () => {
  const bruto = "<<<INICIO>>>\nObjetivo: leer.\n<<<DESARROLLO>>>\nBloque 1\n<<<EVALUACIÓN>>>\nFormativa";
  assert.deepEqual(partesEnVivo(bruto), [
    { titulo: "Inicio", texto: "Objetivo: leer." }, { titulo: "Desarrollo", texto: "Bloque 1" },
    { titulo: "Método de evaluación", texto: "Formativa" }]);
});

test("partesEnVivo no muestra una marca que viene a medio llegar", () => {
  for (const cola of ["<", "<<<", "<<<DESA", "<<<DESARROLLO>", "<<<DESARROLLO>>"]) {
    const partes = partesEnVivo(`<<<INICIO>>>\nHola${cola}`);
    assert.deepEqual(partes, [{ titulo: "Inicio", texto: "Hola" }], cola);
  }
  assert.deepEqual(partesEnVivo("<<<INICIO>>>\nHola<<<DESARROLLO>>>").map((p) => p.titulo), ["Inicio", "Desarrollo"],
    "una marca completa al final sí abre su parte");
  assert.deepEqual(partesEnVivo(""), []);
  assert.deepEqual(partesEnVivo("Texto sin marcas"), [{ titulo: "", texto: "Texto sin marcas" }]);
});
