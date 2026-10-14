# Cambios de Barra Profe

Regla: cada cambio que se reparta sube el número de `VERSION` y agrega una línea aquí.
Formato del número: MAYOR.MENOR.PARCHE (MAYOR: cambia cómo se usa · MENOR: función nueva · PARCHE: arreglo).

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
