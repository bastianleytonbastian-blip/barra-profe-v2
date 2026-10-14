// Pruebas de la lógica pura del planificador (sin DOM). Se ejecutan con:  node --test tests/planificador_logica.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { claveCurso, hermanas, similitud, sinTildes, sugerirOA } from "../herramienta/planificador/web/js/logica.js";

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
