# Cambios del planificador con IA

Regla: cada cambio que se reparta sube el número de `VERSION` y agrega una línea aquí.
Requiere Barra Profe 2.1.0 o más nueva (`BARRA_MINIMA` en `nucleo/version.py`).

## 1.2.0
- Los recursos de la clase también admiten audio (MP3, WAV) y video (MP4). Los tipos de archivo los define ahora Barra
  (`webclass_recursos.SUBCATEGORIA`): el planificador pide Barra 2.2.0 o más nueva.

## 1.1.0
- Los recursos de la clase ahora admiten imágenes JPG y PNG (WebClass: categoría «Imágenes», subcategoría «Fotos»), tanto desde
  «Agregar otro archivo» como entre el material con que se genera la planificación (la IA no lee imágenes; solo se adjuntan).

## 1.0.0
- Primera versión repartible: planifica cualquier asignatura (1° Básico a 4° Medio), guías PIE, envío a WebClass con OA, DUA,
  recurso, guía PIE y réplica en el curso hermano; trabaja siempre con la cuenta activa de Barra.
- Servidor local protegido: solo acepta peticiones del propio navegador (Host, Origen y token de sesión).
- Registro de lo creado en WebClass (`datos\registro_planificaciones*.csv`) con vista «Creadas en WebClass», comprobación de cuáles
  siguen existiendo y «Eliminar» (solo clases que el propio planificador creó, nunca con tarea asignada).
- Versiones del planificador y de Barra visibles en la interfaz; si Barra es más vieja de lo que se necesita, no escribe nada.
- Pruebas automáticas en `tests\test_planificador_*.py` y `tests\planificador_logica.test.mjs`.
