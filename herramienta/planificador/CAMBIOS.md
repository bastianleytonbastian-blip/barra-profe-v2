# Cambios del planificador con IA

Regla: cada cambio que se reparta sube el número de `VERSION` y agrega una línea aquí.
Requiere Barra Profe 2.6.0 o más nueva (`BARRA_MINIMA` en `nucleo/version.py`).

## 1.5.1
- Si a este PC le faltan complementos de Python (fastapi, openai…), «Planificar» lo dice al tiro y ofrece instalarlos,
  en vez de esperar un minuto y mostrar un error sin explicación.

## 1.5.0
- Claves de IA del colegio: el administrador las reparte con la barra (cifradas) y el planificador las usa sin mostrarlas
  (ni siquiera sus últimas letras). Basta con que el PC tenga la «clave del colegio».
- «Claves de IA» muestra qué proveedores trae el colegio. Cada profe puede agregar una clave propia como extra: se usa
  primero y, si llega a su límite, sigue la del colegio del mismo proveedor (el límite se cuenta por clave).
  «Quitar la mía» borra solo la propia.
- Si el colegio reparte claves pero falta (o está mal) la clave del colegio en el PC, se explica qué hacer.
- Con Barra anterior a 2.11.0 funciona igual que antes, sin claves del colegio.

## 1.4.1
- «Subir a WebClass» y los recursos de las clases usan las asignaturas que Barra leyó del WebClass de la cuenta (Música,
  Inglés, Religión…); si no las tiene, la tabla de siempre.

## 1.4.0
- Al generar se ve el texto mientras la IA lo escribe, con sus etapas (leer el material, redactar, escribir el cierre) y
  el modelo que escribe. Si esa conexión en vivo falla, la pantalla espera el resultado igual que antes.
- Abre más rápido: la IA, Word, Excel, PowerPoint, PDF e imágenes se cargan recién cuando se usan (el servidor arranca
  en ~1,8 s en vez de ~5 s).
- `lanzar_planificador.pyw --solo-servidor` deja el planificador listo en segundo plano, sin abrir el navegador (lo usa
  la opción de la barra «Dejarlo listo al abrir la barra»).

## 1.3.0
- «Planificar una clase» parte con la asignatura y el curso de tus unidades de Barra (o con lo último que usaste, o con
  lo que fijes en Mi perfil). En el curso, «Tus cursos» van primero.
- El botón «Generar» queda fijo abajo mientras completas el formulario, muestra cuánto lleva y responde a Ctrl + Enter.
- Enviar a WebClass en 3 pasos: unidad y OA · archivos y réplica · revisar y crear. «Excel» y el marcador del navegador
  pasan a «Otras opciones».
- Sección nueva «Historial»: une las clases guardadas y las creadas en WebClass, con búsqueda, filtro por curso, Abrir,
  Duplicar para otra fecha o curso, Ver en WebClass, Comprobar y Eliminar. Lo que envías queda guardado solo, con su enlace.
- «Subir a WebClass» y la guía PIE suben directo al banco de recursos con Barra (el marcador queda solo sin Barra).
- Guía PIE: los textos se editan campo por campo (el JSON queda en «Avanzado»).
- Mi perfil → Preferencias: claro, oscuro o como Windows; el color de tu barra; asignatura, curso, duración y hora con que
  parte cada clase. Plantillas de indicaciones reutilizables (también «Guardar como plantilla» al planificar).
- El nombre del docente es el de su cuenta de Barra (uno solo para las dos apps).
- Diálogos propios en vez de los del navegador, aviso claro si el planificador se cerró, título de la pestaña por sección y
  pestañas que se manejan con las flechas.
- Mientras WebClass o la IA responden, el servidor sigue atendiendo la pantalla (antes quedaba esperando).

## 1.2.1
- «Subir a WebClass» ofrece las mismas asignaturas que Barra: vuelven Ciencias Naturales y Matemática.
- Al adjuntar un recurso a una clase de «Historia, Geografía y Ciencias Sociales», ya no se firma como Ciencias.

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
