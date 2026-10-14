# Barra Profe v2

Barra flotante para Windows (Python + tkinter) que vive pegada al borde de la
pantalla. Sirve para firmar el libro de clases en Webclass, ver el horario,
llevar una lista de pendientes, anotar notas para el asistente y lanzar las
herramientas de Webclass.

## Estructura

```
herramienta\   el código (se actualiza y se reparte)
  barra_profe.pyw   la ventana de la barra
  barra_utiles.py   lo que no depende de la ventana (se prueba solo)
  rutas.py          dónde vive cada cosa
  webclass*.py ...  las herramientas contra Webclass
personal\      configuración de cada docente (NO se reparte, NO va a git)
  herramientas.json   los botones de la barra
  perfiles\<clave>.json   RUT, cursos y unidades del docente
datos\         lo que se va generando (NO va a git)
tests\         pruebas
Abrir Barra v2.bat   abre la barra
```

## Requisitos

Python 3.12 en Windows y `pip install -r requirements.txt`
(`tkinterdnd2` es opcional: sin él no se pueden arrastrar archivos a la barra).

## Uso

* Un clic en la lengüeta la abre; Escape la esconde; la ✕ la cierra.
* Si el contenido no cabe en la pantalla: haz clic en la barra y usa la rueda
  del mouse, RePág/AvPág o arrastra la barrita de la derecha.
* Con el teclado: Tab y flechas recorren los botones; Enter o espacio los acciona.
* Si hay otra barra abierta, esta solo le avisa y se cierra (mismo puerto local).

## Actividad de los botones

Al pulsar un botón que ejecuta una herramienta se abre una ventana de actividad
con el estado (**En proceso**, **Completado**, **Con avisos**, **Con error**,
**Cancelado**), una barra de carga, un resumen en lenguaje simple y, plegado,
el detalle técnico (con Cancelar, Reintentar, Copiar detalle y Abrir registro).

* En la barra, cada botón muestra el estado (◐ ✓ ⚠ ✕), una barrita fina y
  cuándo corrió por última vez. Eso se guarda en
  `datos\ultimas_ejecuciones_<perfil>.json`.
* La lengüeta pulsa mientras algo corre y destella al terminar. Si la ventana
  de la actividad no se ve, aparece un cartelito junto a la barra.
* El estado sale del código de salida del script y de las marcas que imprime al
  inicio de línea: `[OK]`, `[YA]`, `[SALTADA]`, `[PENDIENTE]`, `[ERROR]`.
* **Progreso real**: un script puede imprimir `##PROGRESO <hecho>/<total> <texto>`
  (por ejemplo `##PROGRESO 3/8 6BA`) y la barra de carga avanza; la línea no se
  muestra en el detalle. Sin esas líneas la barra va en vaivén. Hoy lo imprimen
  `webclass_tareas.py` (por unidad), `webclass_libro.py` (por curso o por día) y
  `subir_carpeta.py` (por archivo).

## Vista previa antes de escribir en Webclass

Los botones con `vista_previa` abren primero una ventana «Antes de empezar»
con lo que se va a hacer, y recién al pulsar **Continuar** se ejecuta:

| valor | de dónde sale el resumen | demora |
|---|---|---|
| `libro` | la última revisión del libro (`estado_firmas_<perfil>.json`): qué bloques tienen OA, leccionario o asistencia por completar y cuántos quedan por firmar | instantánea |
| `subir` | los archivos que hay en cada carpeta de nivel de `Subir a Webclass` | instantánea |
| `simular` | la propia herramienta con `--simular`, que consulta Webclass pero no escribe nada (hoy lo soporta `webclass_tareas.py`) | la de Webclass |

Si no hay nada que hacer, lo dice y ofrece «Cerrar» o «Ejecutar igual».

### Casillas: elegir qué se aplica

Cada cosa que se haría (un bloque del libro, una clase por asignar, un archivo
por subir) tiene una casilla ☑/☐, y todas parten marcadas. Con **Seleccionar
todo** y **Ninguno** se marcan o desmarcan en bloque; el botón dice
«Continuar (3)» según lo marcado y no deja continuar con 0. **Lo que dejas sin
marcar no se toca** y aparece después como «Omitido por ti».

La selección viaja a la herramienta en un archivo (`--seleccion archivo.json`
con `{"claves": [...]}`), que entienden `webclass_libro.py`, `webclass_tareas.py`
y `subir_carpeta.py`. Si se marcó todo, no se pasa nada y la herramienta hace
lo de siempre. Las claves son: bloque = `curso|hora|id`, clase = `idclase`,
archivo = `nivel/archivo`.

## Resultado claro: qué intenté, qué hice y qué no

Las herramientas informan cada cosa con una línea
`##ITEM {"clave", "estado", "titulo", "grupo", "que", "detalle", "motivo"}`
(estado: `propuesto`, `hecho`, `ya`, `pendiente`, `error` u `omitido`). Con eso
la ventana de actividad, al terminar, muestra en bloques: **Intenté** (cuántas),
**✓ Hice**, **⚠ No pude** (con la razón en lenguaje simple y qué hacer, p. ej.
«Tu planificación no tiene una clase con esa fecha → agrégala o ponle fecha»),
**○ Ya estaba hecho**, **– Omitido por ti** y **✍ Te falta firmar** (la firma
siempre la haces tú). Nunca dice «Completado» si algo quedó sin hacer. Los
mismos bloques se imprimen en el texto de la corrida (`=== Resultado ===`).

Cada docente tiene sus propios registros (`registro_libro_<perfil>.csv`,
`registro_asignaciones_<perfil>.csv`); el archivo «de siempre» queda para el
primer perfil (se anota en `datos\registro_historico.txt`). Así, en un PC
compartido, nadie ve las filas de otro. Los botones de registro usan
`%REGISTRO_LIBRO%` y `%REGISTRO_TAREAS%`.

## A dónde asigno cada unidad (editor)

El botón `tipo: "destinos"` abre todas las unidades de una vez (sin consultar a
Webclass) con su destino actual. Se marcan **solo las que se quieren cambiar** y
se pulsa «Elegir destino»: únicamente para esas se piden las opciones a Webclass
(`asignar --opciones-destino id,id`, un solo inicio de sesión) y quedan guardadas
en `datos\destinos_opciones.json`. Cada una muestra un desplegable con los
cursos y talleres reales; «Guardar» escribe solo lo que cambió en
`personal\destinos.json` y nada se manda a Webclass. Hay filtro por texto y
«Solo las que cambié».

## Tour inicial

La primera vez que se abre la barra (por docente) un recorrido de 6 pasos
resalta cada parte y la explica. Se puede saltar, y se repite con **Ver tour**
al pie. Se recuerda en `datos\tour_<perfil>.json`.

## Períodos con tickets (`tipo: "periodos"`)

Algunos botones abren primero una lista de tickets (casillas) para elegir **uno o
varios** períodos; el resultado reemplaza a `{valor}` en el `destino`:

| `selector` | opciones | `{valor}` | lo usa |
|---|---|---|---|
| `meses` | los meses del año escolar hasta hoy (marzo … mes actual); parten marcados este mes y el anterior | `09/2026,10/2026` | **Asignar lo pendiente** (`asignar --meses {valor}`): solo las clases pendientes de esos meses (hasta hoy); después, la vista previa con casillas por clase |
| `periodos` | Hoy · Ayer · Esta semana · Semana anterior · Este mes · Mes anterior · Todo el año (desde marzo) · y una fecha escrita | `05/10/2026,06/10/2026,…` (días hábiles, sin repetir) | **Diagnóstico del libro** (`libro --diagnostico --fechas {valor}`) |

El diagnóstico de **un** día es el informe detallado (lista del curso, bloques
anteriores, planificación); el de **varios** días es una simulación de solo
lectura que explica por qué cada bloque pendiente se podría o no registrar (no
deja filas en el registro). Los ya hechos se resumen en un conteo.

## Si la barra «no conoce» un botón nuevo

La barra recarga `herramientas.json` sola, pero el **programa** solo se lee al
abrirla: un botón nuevo en una barra que sigue abierta con el programa viejo no
funcionaba (y abría la carpeta de la barra). Ahora:

* un botón de un tipo desconocido y sin destino avisa «Ciérrala con la ✕ y ábrela
  de nuevo» en vez de abrir la carpeta;
* al abrir una copia con programa **más nuevo** mientras hay una barra abierta
  (`Abrir Barra v2.bat`, el acceso directo o el atajo), la abierta se reinicia
  sola con el programa nuevo (`VERSION_CODIGO` = el mayor mtime de los .py/.pyw).

## Registrar el libro pendiente hacia atrás

El botón `tipo: "libro-atras"` abre «¿Hasta cuándo miro hacia atrás?» con atajos
(**Ayer · Últimos 7 días · Últimos 15 días · Este mes · Desde una fecha…**). Nunca
llega más allá de hoy ni a más de 62 días atrás. Con el rango elegido se abre una
vista previa **instantánea** (`libro --desde F --hasta F --solo-listar`, que solo
lee) con los bloques que tienen algo por completar, agrupados por día y con
casillas. «Continuar (n)» corre `libro --desde F --hasta F --seleccion archivo` y
registra solo lo marcado, día por día, con avance por día. El resultado trae la
fecha en cada línea.

Por dentro, el mes de cada curso se lee **una sola vez** (4 cursos a la vez) y
sirve para todos los días del rango; las clases de la planificación y las
unidades (por fecha) también se reutilizan.

## Cuando no hay clase en la planificación (o hay varias)

Si a un bloque no se le encuentra la clase de ese día (la planificación no llega
hasta esa fecha, o hay 2 clases con la misma fecha), el bloque queda pendiente y
el informe dice hasta dónde llega: «la última con fecha es «19. …» del 30/09; la
siguiente es …». La ventana de actividad muestra **«Elegir clase…»**: para cada
bloque pendiente ofrece las clases más cercanas por fecha (más un «no declarar»,
que es lo predeterminado). Al aceptar, la herramienta vuelve a correr **solo esos
bloques** con la clase elegida (`--seleccion` con `"elecciones": {clave: idclase}`);
nunca se adivina.

## Asistencia: de qué bloque se copia

Se prueban los bloques anteriores del mismo día, del más cercano al más lejano
(máx. 4, sin talleres), y sirve el primero cuya asistencia **incluye a todas las
alumnas activas** (por id), aunque los contadores no sumen justo (retiradas,
ingresos). Si ninguno sirve, el mensaje dice qué pasó con cada uno
(«11:20: le faltan 4 de 39 alumnas»).

Cada estado se copia con su marca (presente, **ausente**, atrasada, retirada). Nunca se
envía un estado en blanco: si el origen trae un código desconocido, el bloque queda
pendiente. Después de escribir se **relee el destino** y se compara alumna por alumna;
el informe dice «replicada y verificada: 33 presentes · 7 ausentes · 0 atrasadas», o
queda pendiente con «Webclass guardó distinto… (ausentes sin marcar: N)».

## Unidades nuevas

**Registrar libro** busca las unidades en Webclass cada vez. **Asignar** usa las del
perfil (`personal\perfiles\<perfil>.json`), pero al empezar busca (como mucho cada 2 h,
`datos\unidades_ofrecidas_<perfil>.json`) las que el perfil no conoce y las muestra en la
vista previa, grupo «UNIDADES NUEVAS», con casilla: marcada → se suma al perfil y se asigna;
sin marcar → se anota como rechazada y no se vuelve a preguntar. Sin vista previa (corrida
automática) nada se incluye solo. En «A dónde asigno cada unidad», el botón **Buscar
unidades nuevas** hace lo mismo sin asignar (`asignar --buscar-unidades`, solo lectura).
Solo se miran los cursos que el perfil ya tiene.

## Observaciones de estudiantes

Botón **Registrar observación** (`observar`): eliges curso, marcas las alumnas (ninguna
viene marcada), tipo (positiva, negativa, neutra), fecha, asignatura y descripción. La
vista previa muestra una línea por alumna con casilla y solo al continuar se guarda **una
observación por alumna**. Por defecto la ven solo los perfiles del colegio, no el alumno ni
el apoderado (hay una casilla para cambiarlo). Webclass responde un número al guardar; si
no lo hace, esa alumna queda pendiente y se dice en el informe. Lo que guarda es lo mismo
que el botón Guardar de Libro digital > Observaciones. Incidentes y entrevistas no están.

## Planificar (sin IA)

Botón **Planificar** (`planificar`): la barra ordena y completa, el contenido lo escribes tú.
Cada opción termina en una vista previa con casillas.

- **Crear clases vacías según tu horario:** una clase («Clase N», numerada a continuación de las
  que ya tiene la unidad) por cada día que tienes esa asignatura en ese curso, entre dos fechas.
  No repite días que ya tienen clase.
- **Importar desde una planilla** (Excel o CSV; el botón *Plantilla* deja una de ejemplo):
  columnas `nombre, fecha, inicio, desarrollo, cierre, recursos, adecuaciones, evaluacion, oa,
  habilidades, dua`. Los OA y habilidades se escriben por etiqueta (`OA12`, `Hab_d` o solo `d`),
  nunca por número: la barra los busca en la unidad (`OA1` no se confunde con `OA12`). Una clase
  con el mismo nombre y fecha no se vuelve a crear; un OA que la unidad no tiene deja esa fila
  pendiente sin crear nada.
- **Marcar OA, habilidades y DUA en lote** en las clases que elijas (DUA habitual, con TIC o no tocar).

Solo crea y marca: no edita ni borra el texto de clases existentes. Para leer Excel hace falta
`openpyxl` (viene en `requirements.txt`).

## Enviar guías al equipo PIE

Botón **Enviar al equipo PIE** (`correo`): eliges los archivos, revisas asunto y mensaje, y
la vista previa muestra el destinatario y los archivos antes de enviar. Va por Gmail
(SMTP con SSL) a `impresionespiemtc@gmail.com`. La primera vez pide tu Gmail y una
**contraseña de aplicación** (Cuenta de Google > Seguridad > Verificación en dos pasos >
Contraseñas de aplicaciones): se guarda en el Administrador de credenciales de Windows, no
en un archivo, y se puede revocar desde Google. El perfil solo anota tu correo y el del
equipo PIE. Un solo correo por envío con todos los adjuntos (máx. ~18 MB; no admite
.exe, .bat, .js…). El botón *Prueba* manda un correo solo a tu propia dirección. Si Gmail
rechaza la clave o no hay internet, el informe lo dice y el correo no se da por enviado.

**Asunto y mensaje:** el asunto sale como «Guía NEEP <título> <curso>» (con varios archivos,
«Guías NEEP t1, t2 <curso>»). El título es el nombre del archivo sin extensión y el curso se
toma del propio nombre (5BA, 1MA…); si no aparece, se escribe en la casilla *Curso*. Lo que
escribas a mano en el asunto o el mensaje no se vuelve a pisar. El mensaje trae solo el
saludo, la lista de archivos y tu firma. Si sueltas otro archivo mientras la ventana de
arrastre o la del correo siguen abiertas, se suma al mismo correo y salen juntos.

**Subir a Webclass y avisar al PIE en un solo paso:** al arrastrar archivos a la barra, la
ventana «¿A qué nivel lo dejo?» trae una casilla **«Además, enviarlo al equipo PIE por
correo»** (siempre desmarcada) y una fila **«Solo enviarlo al equipo PIE»** para lo que no
va a Webclass. Lo que no marques sigue su camino de siempre. Si marcas el PIE, el archivo se
copia al buzón y se abre el correo con ese archivo ya elegido; nada se envía hasta que tú
pasas por la vista previa y confirmas.

## Mensajes del equipo (entre barras, por la red del colegio)

Botón **Mensajes del equipo** (`mensajeria_red.py`): avisos cortos entre las personas que
tienen la barra, sin servidor, sin internet y sin IA. Cada barra se anuncia por la red local
y se envían los mensajes directo de un computador a otro. **Todo va cifrado y firmado con una
clave de grupo** (Fernet): quien no la tiene no puede leer, escribir ni aparecer en la lista.

- **La clave:** la crea una sola persona (botón *Crear nueva* de la ventana de mensajes), la
  copia y se la entrega a cada compañero por un canal privado; cada uno la pega una vez. Se
  guarda en el Administrador de credenciales de Windows, no en un archivo. Si alguien sale
  del grupo o la clave se filtra, se crea otra y se reparte de nuevo.
- **Entrega:** se confirma cada mensaje. Si el destinatario no está conectado, queda
  «⏳ pendiente» y sale apenas esa barra aparezca en la red; el historial vive solo en cada
  computador (`datos\mensajes_<perfil>.json`).
- **En la barra:** el panel muestra «💬 N mensajes nuevos» (o cuántos hay en línea) y aparece un
  aviso al llegar uno. Se puede escribir a una persona o a «Todos».
- **Límites:** solo funciona con ambos equipos en la **misma red a la vez** (la wifi del colegio
  no debe aislar dispositivos; para comprobarlo está `Probar red.bat`). Un mensaje a alguien
  que nunca se ha visto no tiene a dónde ir. Windows pedirá permiso de red la primera vez.
  Máximo 4000 letras por aviso; no hay archivos adjuntos.
- **Requiere** la librería `cryptography` (en `requirements.txt`).

## Diagnóstico del libro

`libro --diagnostico --fecha ayer --cursos 4BA` (botón «Diagnóstico del libro»):
informe de **solo lectura**, sin nombres de alumnas, de por qué un día no se puede
registrar solo: bloques del día con sus marcas, la lista del curso, la cobertura de
cada bloque anterior, las asignaturas y unidades del plan y las clases con fecha
cercana. Útil para pasárselo a quien mantiene la herramienta («Copiar detalle»).

## Velocidad del libro

`registrar libro` y la revisión del libro consultan a Webclass una vez por
curso, y cada consulta puede tardar decenas de segundos cuando el servidor anda
lento. Los cursos se piden **a la vez** (4 en paralelo) y lo ya leído se reutiliza
durante la corrida (`bloques_de_cursos` en `webclass_libro.py`). Escribir en un
bloque no obliga a releer el resto.

## Pruebas

```
python -m unittest discover -s tests -v
```

`test_barra_ventana.py` abre una barra de verdad unos segundos (en otro puerto).

## Formato de los archivos

### herramientas.json (los botones)

Lista de objetos. Se recarga sola al guardar.

| campo | significado |
|---|---|
| `grupo` | título de la sección donde se agrupa el botón |
| `nombre`, `icono`, `ayuda` | texto, emoji y ayuda al pasar el mouse |
| `tipo` | qué hace (tabla de abajo) |
| `destino` | ruta, URL o subcomando, según el tipo |
| `confirmar` | (`webclass-confirmar`) pregunta que se muestra antes |
| `vista_previa` | `"libro"`, `"subir"` o `"simular"`: muestra qué se va a hacer antes de ejecutar (ver abajo) |
| `pregunta`, `opciones`, `escribir`, `interactivo` | (`preguntar`) ver ejemplos en `personal\herramientas.json` |

Tipos: `url` (navegador), `consola` (ejecuta un `.bat` y muestra su salida),
`webclass` (subcomando, p. ej. `asignar --hoy --dias-atras 7`),
`webclass-confirmar` (igual, pero pregunta antes), `preguntar` (pide un dato y
lanza la herramienta), `destinos` (editor de destinos), `horario`, `color`,
`perfil`, y cualquier otro valor abre `destino` con el programa predeterminado
(carpetas, `.csv`, …).

Variables en `destino`: `%BARRA%`, `%WEBCLASS%`, `%BUZON%`, `%DATOS%`,
`%PERSONAL%`, `%RAIZ%`, `%REGISTRO_LIBRO%`, `%REGISTRO_TAREAS%` y las de
Windows (`%USERPROFILE%`…).

### estado_firmas_<perfil>.json (lo escribe `estado_firmas.py`)

```json
{"fecha": "05/10/2026", "error": null,
 "bloques": [...], "sin_firmar": [{"curso": "5BA", "hora": "08:00-08:45"}],
 "sin_registro": [...],
 "jefatura": {"curso": "5BA", "ausentes": ["..."], "atrasadas": ["..."], "estado": ""}}
```

Si `fecha` no es hoy, o `error` viene con texto, la barra vuelve a revisar
(a los 3 minutos si hubo error; si no, pasados 20).

### bandeja.jsonl (notas para el asistente)

Una línea JSON por nota: `{"id": "<fecha-hora>", "texto": "...", "estado": "pendiente", "origen": "barra"}`.

### horario_semanal.json (del asistente)

```json
{"vigencia": {"desde": "2026-03-02", "hasta": "2026-12-18"},
 "excepciones": ["2026-10-12"],
 "dias": {"lunes": [{"inicio": "08:00", "fin": "08:45", "titulo": "5BA Ciencias"}]}}
```

### Otros

`posicion.json` (lado, alto, monitor, fijada), `lista_tareas_<perfil>.json`
(`[{"texto", "hecha", "creada"}]`), `tema_<perfil>.json` (`{"paleta": "morado"}`).

## Datos personales

El RUT, el id de usuario y los cursos de cada docente viven solo en
`personal\perfiles\`. El código no los trae escritos, y `personal\` y `datos\`
están en `.gitignore`: no se versionan ni se reparten. La contraseña va en el
Administrador de credenciales de Windows, nunca en un archivo.
