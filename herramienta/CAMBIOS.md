# Cambios de Barra Profe

Regla: cada cambio que se reparta sube el número de `VERSION` y agrega una línea aquí.
Formato del número: MAYOR.MENOR.PARCHE (MAYOR: cambia cómo se usa · MENOR: función nueva · PARCHE: arreglo).

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
