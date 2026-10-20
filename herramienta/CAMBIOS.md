# Cambios de Barra Profe

Regla: cada cambio que se reparta sube el número de `VERSION` y agrega una línea aquí.
Formato del número: MAYOR.MENOR.PARCHE (MAYOR: cambia cómo se usa · MENOR: función nueva · PARCHE: arreglo).

## 2.11.0
- Buzón del colegio: el administrador publica desde su barra y llega a todos los profes en unos minutos (la barra lo
  consulta al abrirse y cada 20 minutos). Viaja por GitHub: lo que va para todos, sin cifrar (se ve sin configurar
  nada); los mensajes a profes en particular y las claves de IA, CIFRADOS con la «clave del colegio».
  - **Mensajes** para todos o para algunos profes (por RUT o nombre): se ven hasta que el profe los marca «Listo».
  - **Avisos del día**: se ven solo ese día.
  - Aparecen arriba de la tarjeta «Hoy» (📣 Avisos) y, lo nuevo, con un cartelito una sola vez. Con la barra bloqueada
    (PIN) se avisa recién cuando el profe entra.
  - **Claves de IA del colegio**: el planificador de cada profe las usa sin poder verlas (trae el planificador 1.5.0).
- ⚙ Ajustes → Profesor → «Clave del colegio»: se pega una vez por PC (queda en el Administrador de credenciales de
  Windows) para recibir los mensajes dirigidos y las claves de IA. Antes de guardarla se revisa que abra lo publicado.
- ⚙ Ajustes → Administrador (solo en el PC con GitHub CLI y permiso en el repositorio): crear y copiar la clave del
  colegio, publicar y quitar mensajes y avisos, y publicar las claves de IA.
- Si vienes de la 2.5.4, esta versión también trae (detalle en las secciones de abajo):
  - **PIN de 4 números** en los equipos con varios profesores: la barra parte bloqueada. Si no tienes PIN o lo
    olvidaste, entras con tu contraseña de WebClass y creas uno.
  - **Días sin clases** (feriados, vacaciones): «No hubo clase ▾» en la vista previa y el botón «Días sin clases».
  - La barra cabe en una pantalla: tarjeta «Hoy» plegable, botones en grupos con ★ Favoritos y ⚙ Ajustes para todo
    (colores, letra, botones, profesor, respaldo), sin tocar archivos.
  - «Ahora / Luego» desde Mi horario de WebClass, «Mis registros» con filtros y planificador más rápido, con historial
    y envío en 3 pasos.

## 2.10.0
- Días sin clases (feriados, salidas, vacaciones): lo que marques deja de aparecer como pendiente.
  - En la vista previa de «Registrar libro», «Registrar libro pendiente» y «Asignar clases», cada fila trae
    «No hubo clase ▾»: «no hubo esta clase» o «ese día no hubo clases». Sale de la lista al tiro.
  - Botón nuevo «Días sin clases» (también en ⚙ Ajustes → Profesor y en el detalle de la tarjeta «Hoy»): ofrece los días
    que el libro muestra con bloques pendientes, deja marcar un día o un rango (unas vacaciones) con su motivo y
    deshacer lo marcado con «Quitar».
  - Lo marcado no se registra, no se asigna como tarea ni se cuenta en la tarjeta «Hoy» ni en el «Informe del mes».
    Si marcas hoy, la tarjeta dice «Hoy: sin clases».
  - «Elegir la clase» (después de registrar) ofrece también «no hubo clase» para cada bloque.
  - Se guarda por profesor en `datos\sin_clases_<cuenta>.json`.

## 2.9.0
- PIN de 4 números por profesor en los equipos con varios profesores (para no usar por error la barra de otro):
  - La barra parte bloqueada; para usarla se escribe el PIN. «Soy otro profesor» cambia a otra cuenta con su PIN.
  - Cambiar de profesor (⚙ Ajustes → Profesor) pide el PIN de quien entra.
  - Si alguien no tiene PIN todavía, o lo olvidó, entra con su contraseña de Webclass y crea uno nuevo.
  - ⚙ Ajustes → Profesor: cambiar mi PIN y bloquear la barra. La ✕ ofrece «Bloquear y esconder».
  - Bloqueada no se pueden usar los botones, Ajustes ni arrastrar archivos; el libro se sigue revisando igual.
  - Del PIN solo se guarda su huella (nunca el número). En un equipo de un solo profesor no se pide.
- Se quitan las «Notas para el asistente».
- Favoritos de fábrica: «Escala de notas» en vez de «Abrir y firmar» (los favoritos que ya elegiste no cambian).
- Un clic en la línea del libro («1 sin firmar…») o en la de ausentes muestra el detalle, como «HOY». Desde el detalle,
  «Abrir el libro en Webclass».

## 2.8.0
- La barra sirve igual a docentes sin el asistente personal:
  - «Ahora / Luego» sale de «Mi horario» de WebClass; si nunca se leyó o tiene más de una semana, se vuelve a leer solo.
    Sin ningún horario ya no dice «Hoy no hay clases».
  - Las notas para el asistente y su paso del recorrido aparecen solo si hay asistente; el atajo de teclado abre la barra.
  - «Mi horario» muestra la asignatura de cada bloque (antes, solo Orientación).
  - Las carpetas del buzón con nivel y asignatura en el nombre («5 basico Orientacion», «7 basico Musica») se
    reconocen solas, sin una lista fija.
  - Al configurar o actualizar la cuenta se leen las asignaturas que ofrece WebClass para subir recursos (Inglés,
    Artes, Música, Religión…). La tabla de siempre queda de respaldo.
- «Mis registros»: los botones «Registro del libro», «de subidas» y «de tareas» abren una ventana con pestañas, filtros
  por período, curso y estado, el detalle de la fila elegida y «Abrir en Excel».
- Arreglo: «Mi horario» actualizaba su ventana desde otro hilo al terminar de leer WebClass.
- Trae el planificador 1.4.1.

## 2.7.1
- ⚙ Ajustes → Comportamiento → «Dejarlo listo al abrir la barra»: el planificador queda corriendo en segundo plano y
  «Planificar» abre al tiro.
- Trae el planificador 1.4.0: se ve el texto mientras la IA lo escribe y arranca más rápido.

## 2.7.0
- Ajustes sin tocar archivos (⚙ → pestañas a la izquierda):
  - **Apariencia:** color (también «Claro» y «Alto contraste»), tamaño de la letra y ancho de la barra. Se aplica al
    tiro, sin cerrar la barra.
  - **Botones:** mostrar u ocultar, ★ favoritos, subir o bajar, editar nombre, ícono, grupo y ayuda, y agregar
    botones propios (página web, carpeta o archivo). «Volver a los botones de fábrica» guarda una copia de los tuyos.
  - **Comportamiento:** abrirla al pasar el mouse, cuánto espera para esconderse, dejarla fija, y cuánto dura el
    aviso al terminar una tarea (con sonido si quieres).
  - **Windows y sonido:** elegir o quitar el sonido de inicio, abrir la barra al encender el PC, atajo de teclado
    (Ctrl + Alt + una letra) y reparar accesos directos que apuntan a una carpeta que ya no existe.
  - **Profesor:** cambiar de profesor sin cerrar la barra, agregar uno nuevo y actualizar los cursos y unidades.
  - **Respaldo:** exportar e importar tu configuración en un .zip (sin contraseñas ni claves de IA).
- Configurar la cuenta ya no necesita la consola: RUT, contraseña (va directo al Administrador de credenciales de
  Windows) y nombre en una ventana; después eliges el curso del que eres profesor jefe. Se abre sola la primera vez.
- Trae el planificador 1.3.0 (historial, envío en 3 pasos, subida directa, preferencias y el color de tu barra).
  Subir al banco de recursos acepta además el tipo de WebClass (el planificador lo usa para las guías PIE).

## 2.6.0
- La barra cabe en una pantalla:
  - Cabecera fija con tu nombre, ⚙ Ajustes, 📌 y ✕.
  - Tarjeta «Hoy» plegable: una línea por tema; un clic en «HOY» muestra el detalle.
  - Notas para el asistente plegables.
  - Botones en grupos que se abren con un clic, con ★ Favoritos arriba. Clic derecho en un botón para sumarlo o
    quitarlo de favoritos.
- ⚙ Ajustes reúne el color, el cambio de profesor, las actualizaciones y la ayuda (registro, editar botones,
  recorrido). El pie de enlaces desaparece.
- La ✕ pregunta si esconder la barra (sigue revisando el libro) o cerrarla.
- La barra busca versiones nuevas al abrirse y luego cada 6 horas. El aviso aparece bajo la cabecera.
- Ventana de arrastrar archivos:
  - Niveles en orden y con tilde, con tus cursos primero (los demás, plegados).
  - Botón «Subir ahora» para subir solo lo que acabas de soltar.
- Colores y letra desde un solo lugar (`tema.py`):
  - Mejor contraste y nada en letra menor a 9 pt.
  - Paletas nuevas «Claro» y «Alto contraste».
  - Campos de texto con borde y barras de desplazamiento con los colores de la paleta.
- Abre más rápido: los grupos plegados no se arman hasta abrirlos (de 286 a 101 elementos al abrir; armar la barra
  bajó de 3,2 s a 2,1 s).
- El recorrido de bienvenida se actualizó y vuelve a aparecer una vez.

## 2.5.5
- Las ventanas de arrastrar archivos, colores, profesores, horario y «Completar mes atrasado» se ubican junto a la barra y
  siempre dentro de la pantalla. Al 150 % la de arrastrar quedaba cortada (no se veía «No volver a preguntar») y, con la
  barra a la izquierda, las otras quedaban encima de ella.
- «Completar mes atrasado» calcula los meses solo; antes eran fijos de mayo a octubre de 2026.
- Textos corregidos (tildes y la ayuda de «Cambiar color»). Al actualizar, las correcciones llegan también a los botones de
  cada docente, sin tocar lo que haya cambiado a mano.
- Una sola tabla de asignaturas para subir recursos, que también usa el planificador. Suma «Filosofía y Psicología» y
  «Programa de Integración Escolar».

## 2.5.4
- Versión de prueba de las actualizaciones en línea: no cambia nada del funcionamiento.

## 2.5.3
- Arreglo: en PC cuyo Python no confía en el certificado de GitHub («unable to get local issuer certificate») la búsqueda de actualizaciones
  fallaba aunque hubiera internet. Ahora reintenta con los certificados de `certifi` (la verificación nunca se desactiva) y, si tampoco así, explica qué hacer.

## 2.5.2
- Arreglo: la consulta de actualizaciones enviaba una cabecera que hacía que GitHub devolviera una copia vieja del aviso de versión;
  por eso una barra podía decir «ya tienes la última» con una versión nueva publicada.

## 2.5.1
- Arreglo: el pie de la barra (210 px de ancho) dejaba «Ver tour» y «Buscar actualizaciones» fuera de la vista; ahora los enlaces van en filas y todos se ven.
- Si «Buscar actualizaciones» no logra conectarse, ahora muestra el detalle técnico del error para poder diagnosticarlo.

## 2.5.0
- Nuevo enlace «Buscar actualizaciones» en el pie de la barra: consulta GitHub al momento y avisa si estás al día o si no pudo conectarse.
- Se elimina la tarea automática de las 16:00 (asignar las clases del día). El instalador ya no la crea y ACTUALIZAR.bat / INSTALAR.bat la borran
  si existía; las clases se asignan con el botón de la barra. La subida automática de recursos (cada 10 minutos) sigue igual.

## 2.4.1
- Al arrastrar archivos a la barra, la ventana también muestra con qué asignatura se subirán y deja elegirla (con «No volver a preguntar»).
  Es la misma elección de «Subir recursos» y vale para todo lo que haya en el buzón cuando corra la subida automática.

## 2.4.0
- «Subir recursos»: al subir, la ventana pregunta la asignatura (antes todo se firmaba con la del perfil o, si no se sabía, Ciencias) y trae la casilla
  «No volver a preguntar». Lo elegido se guarda por cuenta y también lo usa la subida automática; «Cambiar» vuelve a preguntar.

## 2.3.1
- La consulta de actualizaciones usa un archivo `version.json` del release en vez de la API de GitHub, que se agota con muchos profes en una misma red.

## 2.3.0
- Actualizaciones en línea: al abrirse, la barra consulta si hay un release nuevo en GitHub y, si lo hay, muestra «Hay una versión nueva»;
  con un clic descarga el paquete, comprueba su suma de verificación, guarda una copia del código actual en `respaldo_actualizacion\` y lo instala.
  No toca `personal\` ni `datos\`. Para quien publica: `python publicar.py --subir`.

## 2.2.0
- La barra (arrastrar archivos, «Subir recursos») y el planificador ahora suben también imágenes (jpg, jpeg, png), audio (mp3, wav)
  y video (mp4), además de pdf, Word, Excel y PowerPoint. La vista previa de «Subir recursos» ya incluye doc, xls y ppt.

## 2.1.0
- El botón «Planificar» abre el asistente de IA (herramienta\planificador); la ventana de antes pasó a «Planificar en bloque».
- Botón nuevo «Escala de notas». Se retiró el botón «Mensajes del equipo» (el código sigue en el programa).
- `ACTUALIZAR.bat` / `INSTALAR.bat` instalan los complementos del planificador y actualizan los botones de cada docente.
- Se muestra la versión en el pie de la barra.
- Pruebas automáticas del planificador y del instalador en `tests\`.

## 2.0.0
- Barra v2 (versión anterior a la numeración).
