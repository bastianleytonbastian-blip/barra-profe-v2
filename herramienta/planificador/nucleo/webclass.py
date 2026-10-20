"""Exportación a WebClass: texto con formato (HTML para CKEditor / Excel), datos de clase y recurso, y el marcador "Llenar WebClass"."""
import base64
import html
import json
import re
from urllib.parse import quote

from nucleo import perfil as _perfil

MARCA = "planificador_webclass"
TIPOS_CLASE = {"Universal": "1", "Adaptada": "2", "Remedial": "3"}
# Pautas DUA del Paso 4 de WebClass (número = valor de la casilla checkDua_N)
PAUTAS_DUA = {
    1: "Permita la modificación y personalización de la presentación de su información.",
    2: "Ofrezca alternativas de información auditiva.",
    3: "Ofrezca alternativas de información visual.",
    4: "Aclare vocabulario y símbolos.",
    5: "Aclare la sintaxis y estructura.",
    6: "Apoye la decodificación de textos, notaciones matemáticas y símbolos.",
    7: "Promueva la comprensión entre diferentes idiomas y lenguas.",
    8: "Ilustre las ideas principales de aprendizaje a través de múltiples medios.",
    9: "Active y proporcione conocimientos previos.",
    10: "Destaque patrones, características fundamentales, ideas principales y relaciones entre ellas.",
    11: "Guíe el procesamiento, visualización y manipulación de la información.",
    12: "Potencie técnicas para desarrollar la memoria y la transferencia de información.",
    13: "Varíe los métodos de respuesta, navegación e interacción.",
    14: "Facilite el acceso a herramientas y tecnologías de accesibilidad universal.",
    15: "Use múltiples medios para la comunicación.",
    16: "Use múltiples herramientas y tecnologías para la resolución de problemas.",
    17: "Entregue opciones de apoyo para la práctica y desempeño de tareas.",
    18: "Guíe el proceso para establecer metas adecuadas.",
    19: "Enseñe a planificar y desarrollar estrategias.",
    20: "Facilite la gestión de información y recursos.",
    21: "Aumente la capacidad para monitorear el proceso de seguimiento de un plan.",
    22: "Permita la elección individual y autonomía.",
    23: "Proporcione opciones que resalten la importancia, el valor y la autenticidad de lo aprendido.",
    24: "Reduzca las amenazas y distracciones.",
    25: "Resalte la relevancia de las metas y los objetivos del aprendizaje.",
    26: "Varíe los niveles de apoyos, recursos y desafíos.",
    27: "Fomente el trabajo colaborativo.",
    28: "Fomente la evaluación formativa como estrategia de compromiso.",
    29: "Promueva expectativas que garanticen el éxito para aumentar la motivación.",
    30: "Promueva acciones que apoyen habilidades para la resolución de problemas y enfrentar desafíos.",
    31: "Promueva la autoevaluación y la reflexión.",
}
# Pautas que la estructura fija de las clases siempre aplica (conocimientos previos, pregunta problematizadora,
# PPT, conceptos, fuentes, trabajo en pareja, evaluación formativa, guía PIE, síntesis del cierre, reflexión)
DUA_POR_DEFECTO = [9, 23, 3, 4, 11, 27, 28, 26, 10, 31]
MIN_DUA = 3  # WebClass pide marcar al menos 3 pautas


def completar_dua(pautas):
    """Pautas elegidas (sin repetir) y, si son menos de MIN_DUA, se completan con las de la estructura fija de la clase."""
    pautas = [n for n in dict.fromkeys(pautas) if n in PAUTAS_DUA]
    for n in DUA_POR_DEFECTO:
        if len(pautas) >= MIN_DUA:
            break
        if n not in pautas:
            pautas.append(n)
    return pautas

# ---------- Recursos (Recursos → Subir recurso) ----------
# Tipo de recurso -> (id del botón de tipo, valor de la subcategoría) en el formulario de WebClass
TIPOS_RECURSO = {
    "Guía PIE (NEE → Necesidades Especiales)": ("tipoEspecial", "70"),
    "PDF (Ofimática)": ("tipoOfimatica", "44"),
    "Word (Ofimática)": ("tipoOfimatica", "41"),
    "Excel (Ofimática)": ("tipoOfimatica", "42"),
    "Power point (Ofimática)": ("tipoOfimatica", "43"),
    "Documento pedagógico (Documentos)": ("tipoManuales", "80"),
}
ASIGNATURAS_RECURSO = {
    "Historia, Geografía y Ciencias Sociales": "4",
    "Programa de Integración Escolar": "107",
    "Orientación": "9",
    "Filosofía y Psicología": "16",
    "Lenguaje y Comunicación": "1",
}
NIVELES_WEBCLASS = ["Primero Básico", "Segundo Básico", "Tercero Básico", "Cuarto Básico", "Quinto Básico",
                    "Sexto Básico", "Séptimo Básico", "Octavo Básico", "Primero Medio", "Segundo Medio",
                    "Tercero Medio", "Cuarto Medio"]
MAX_MB_RECURSO = 8  # más grande no cabe con seguridad en el portapapeles


def nivel_webclass(curso):
    """'6° Básico (Historia)' -> 'Sexto Básico'; '3° Medio (…)' -> 'Tercero Medio'."""
    m = re.search(r"(\d)°\s*(Básico|Medio)", curso or "")
    if not m:
        return None
    n, ciclo = int(m.group(1)), m.group(2)
    indice = n - 1 if ciclo == "Básico" else 7 + n
    return NIVELES_WEBCLASS[indice] if 0 <= indice < len(NIVELES_WEBCLASS) else None


def tipo_por_archivo(nombre):
    ext = (nombre or "").lower().rsplit(".", 1)[-1]
    return {"pdf": "PDF (Ofimática)", "doc": "Word (Ofimática)", "docx": "Word (Ofimática)",
            "xls": "Excel (Ofimática)", "xlsx": "Excel (Ofimática)", "ppt": "Power point (Ofimática)",
            "pptx": "Power point (Ofimática)"}.get(ext, "Documento pedagógico (Documentos)")


def asignaturas_de_barra():
    """Nombre -> id de las asignaturas con que la cuenta activa puede subir recursos, según Barra: las que leyó de su
    WebClass o, si no, su tabla única ({} si el planificador está suelto o Barra es antigua)."""
    from nucleo import barra, rutas
    utiles = barra.modulo_de_barra(rutas.BARRA, "barra_utiles")
    de_la_cuenta = getattr(utiles, "asignaturas_de_la_cuenta", None)
    if de_la_cuenta is not None:
        perfil = {"asignaturas_webclass": rutas.asignaturas_webclass_de_cuenta()}
        return {nombre: str(codigo) for _clave, nombre, codigo in de_la_cuenta(perfil)}
    ids = getattr(utiles, "ID_ASIGNATURA", None) or {}
    return {nombre: str(ids[clave]) for clave, nombre in getattr(utiles, "ASIGNATURAS_SUBIDA", ()) if clave in ids}


def asignaturas_recurso():
    """Asignaturas de WebClass (nombre -> id): primero las de Barra (la misma tabla con que sube la barra), luego las
    propias de aquí que Barra no tenga, y al final las que el docente agregó en su perfil."""
    de_barra = asignaturas_de_barra()
    conocidas = set(de_barra.values())
    propias = {n: i for n, i in ASIGNATURAS_RECURSO.items() if i not in conocidas}
    return {**de_barra, **propias, **_perfil.cargar().asignaturas_webclass}


def datos_recurso(nombre, autor, niveles, asignatura, visible, tipo, archivo_bytes, archivo_nombre, mime):
    tipo_id, subcategoria = TIPOS_RECURSO[tipo]
    return json.dumps({MARCA: 1, "recurso": {
        "nombre": nombre, "autor": autor, "niveles": list(niveles), "asignatura": asignaturas_recurso()[asignatura],
        "visible": bool(visible), "tipo_id": tipo_id, "subcategoria": subcategoria,
        "archivo_nombre": archivo_nombre, "archivo_tipo": mime or "application/octet-stream",
        "archivo_b64": base64.b64encode(archivo_bytes).decode()}}, ensure_ascii=False)


# Rótulos que van en negrita al inicio de una línea (en WebClass y en el Excel)
ROTULOS = r"(Objetivo de Aprendizaje:|Objetivo General:|Objetivo adaptado:|Actividad:|LINK DE CANVA)"


def es_subtitulo(linea):
    """Línea corta sin puntuación final: subtítulo de bloque (ej. 'Pregunta problematizadora', 'ACTIVIDAD')."""
    t = linea.strip()
    if not t or t.startswith("-") or re.match(r"https?:", t):
        return False
    if t == "V.J.E.":
        return True
    return len(t) <= 120 and not re.search(r"[.?!;:,…)\]]$", t)


def partes_con_formato(texto):
    """Divide el texto en líneas marcadas: ('titulo'|'rotulo'|'vineta'|'parrafo'|'blanco', contenido...)."""
    partes = []
    for linea in (texto or "").split("\n"):
        t = linea.strip()
        if not t:
            partes.append(("blanco", ""))
        elif t.startswith("- "):
            partes.append(("vineta", t[2:].strip()))
        elif re.match(ROTULOS, t):
            rotulo = re.match(ROTULOS, t).group(1)
            partes.append(("rotulo", rotulo, t[len(rotulo):].strip()))
        elif es_subtitulo(t):
            partes.append(("titulo", t))
        else:
            partes.append(("parrafo", t))
    return partes


def texto_a_html(texto):
    """Texto plano de la app -> HTML para los editores CKEditor de WebClass (negritas y viñetas)."""
    salida, en_lista = [], False
    for parte in partes_con_formato(texto):
        tipo = parte[0]
        if tipo == "vineta":
            if not en_lista:
                salida.append("<ul>")
                en_lista = True
            salida.append(f"<li>{html.escape(parte[1])}</li>")
            continue
        if en_lista:
            salida.append("</ul>")
            en_lista = False
        if tipo == "titulo":
            salida.append(f"<p><strong>{html.escape(parte[1])}</strong></p>")
        elif tipo == "rotulo":
            resto = html.escape(parte[2])
            if parte[1] == "LINK DE CANVA" and re.match(r"https?://", parte[2]):
                resto = f'<a href="{html.escape(parte[2], quote=True)}">{resto}</a>'
            salida.append(f"<p><strong>{html.escape(parte[1])}</strong> {resto}</p>")
        elif tipo == "parrafo":
            salida.append(f"<p>{html.escape(parte[1])}</p>")
    if en_lista:
        salida.append("</ul>")
    return "".join(salida)


def horas_webclass(tiempo_str):
    """Duración en horas pedagógicas para WebClass: 45 min = 1, 90 min = 2, 135 min = 3."""
    m = re.search(r"\d+", tiempo_str or "")
    minutos = int(m.group(0)) if m else 90
    return str(max(1, round(minutos / 45)))


def codigos_oa(texto):
    """'OA9, OA 10' -> ['OA9', 'OA10']"""
    return list(dict.fromkeys(f"OA{n}" for n in re.findall(r"\bOA\s*(\d+)\b", texto or "", re.IGNORECASE)))


def datos_webclass(nombre, fecha, hora, horas, tipo, campos, oa="", oa_claves="", dua=(), oa_exactos=False,
                   oa_textos=None):
    """JSON que copia la app y lee el marcador. campos: {evaluacion, inicio, desarrollo, cierre, recursos, adecuaciones, motivacion} en texto plano.
    oa: códigos sugeridos ('OA9'); oa_claves: palabras para buscar el OA si el código no está en la unidad; dua: números de pautas."""
    datos = {MARCA: 1, "nombre": nombre, "fechaini": fecha, "fechatermino": fecha,
             "hora_inicio": hora, "duracion": horas, "tipo": TIPOS_CLASE.get(tipo, "1"),
             "oa": codigos_oa(oa), "oa_claves": oa_claves, "oa_exactos": bool(oa_exactos),
            "oa_textos": oa_textos or {},  # redacción oficial de los OA elegidos: se buscan por su texto en la unidad
            "dua": completar_dua(int(n) for n in dua)}
    datos.update({clave: texto_a_html(valor) for clave, valor in campos.items()})
    return json.dumps(datos, ensure_ascii=False)


# Marcador fijo: lee la clase del portapapeles (o de un cuadro para pegar) y completa el formulario "Nueva clase".
# No presiona Guardar ni marca las pautas DUA (esas se guardan apenas se marcan).
_CODIGO_MARCADOR = r"""
(async function(){
 var MARCA='%s';
 function aviso(t,ok){var d=document.createElement('div');d.textContent=t;
  d.style.cssText='position:fixed;top:12px;right:12px;z-index:2147483647;padding:12px 16px;border-radius:8px;font:bold 15px sans-serif;color:#fff;box-shadow:0 2px 8px rgba(0,0,0,.35);background:'+(ok?'#2E7D32':'#C62828');
  document.body.appendChild(d);setTimeout(function(){d.remove();},15000);}
 var esRecurso=!!document.getElementById('formlocal');
 if(!esRecurso&&(typeof CKEDITOR==='undefined'||!document.getElementById('nombre'))){aviso('Abre primero «Nueva clase» (para una clase) o Recursos → «Subir recurso» (para un archivo) en WebClass.',false);return;}
 function esperar(cond,listo,n){n=n||0;if(cond())return listo(true);if(n>60)return listo(false);setTimeout(function(){esperar(cond,listo,n+1);},250);}
 function subir(r){
  var f=document.getElementById('formlocal');
  var radio=document.getElementById(r.tipo_id);if(!radio){aviso('No se encontró el tipo de recurso en el formulario.',false);return;}
  radio.click();radio.checked=true;
  var sinCargas=function(){return !window.jQuery||jQuery.active===0;};
  esperar(function(){return document.querySelector('#TipoFile option[value="'+r.subcategoria+'"]');},function(ok){
   if(!ok){aviso('No cargó la subcategoría. Elige el tipo a mano y vuelve a usar el marcador.',false);return;}
   var tf=document.getElementById('TipoFile');tf.value=r.subcategoria;
   if(window.jQuery)jQuery(tf).trigger('change');else tf.dispatchEvent(new Event('change',{bubbles:true}));
   /* WebClass recarga niveles y asignaturas tras elegir la subcategoría: se espera a que termine antes de llenar */
   esperar(function(){return sinCargas()&&document.querySelector('#selectSectorLocal option[value="'+r.asignatura+'"]');},function(ok2){
    setTimeout(function(){
     var bin=atob(r.archivo_b64),u=new Uint8Array(bin.length);for(var i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);
     var archivo=new File([u],r.archivo_nombre,{type:r.archivo_tipo});
     function aplicar(){
      var s=document.getElementById('selectSectorLocal');if(ok2&&s.value!==r.asignatura){s.value=r.asignatura;s.dispatchEvent(new Event('change',{bubbles:true}));}
      document.getElementById('nombreLocal').value=r.nombre;document.getElementById('autorLocal').value=r.autor;
      var quiero=r.niveles.map(function(n){return n.toLowerCase();});
      [].slice.call(f.querySelectorAll('input[name="optionLocal[]"]')).forEach(function(c){
       var t=((c.closest('label')||c.closest('td,div,p,li')||c.parentElement).innerText||'').trim().toLowerCase();
       if(quiero.indexOf(t)>=0&&!c.checked)c.click();});
      var vis=[].slice.call(document.querySelectorAll('#visibleFormStudent')).filter(function(v){return v.form===f;})[0];if(vis&&vis.checked!==!!r.visible)vis.click();
      var inp=document.getElementById('archivo');
      if(!inp.files.length){var dt=new DataTransfer();dt.items.add(archivo);inp.files=dt.files;inp.dispatchEvent(new Event('change',{bubbles:true}));}
      radio.checked=true;
     }
     aplicar();
     /* Revisión: si alguna recarga tardía borró algo, se vuelve a aplicar */
     setTimeout(function(){aplicar();
      var nn=[].slice.call(f.querySelectorAll('input[name="optionLocal[]"]')).filter(function(c){return c.checked;}).length;
      var okArchivo=document.getElementById('archivo').files.length>0,okAsig=document.getElementById('selectSectorLocal').value===r.asignatura;
      aviso((okArchivo&&okAsig?'✓ Recurso listo: ':'⚠ Revisa: ')+r.nombre+' · '+nn+' nivel(es) · '+(okArchivo?'archivo '+r.archivo_nombre:'⚠ adjunta el archivo')+(okAsig?'':' · ⚠ elige la asignatura')+'. Revisa y presiona Guardar.',okArchivo&&okAsig);
     },1500);
    },600);});});
 }
 function procesar(d){
  if(esRecurso){if(!d.recurso){aviso('Lo copiado es una clase: ábrelo en «Nueva clase».',false);return;}subir(d.recurso);}
  else{if(d.recurso){aviso('Lo copiado es un recurso: ábrelo en Recursos → «Subir recurso».',false);return;}llenar(d);}
 }
 function leer(t){try{var d=JSON.parse(t);if(d&&d[MARCA])return d;}catch(e){}return null;}
 function llenar(d){
  ['nombre','fechaini','fechatermino','hora_inicio','duracion'].forEach(function(k){var e=document.getElementById(k);
   if(e&&d[k]!=null&&d[k]!==''){e.value=d[k];e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}});
  var r=document.querySelector('input[name=tipo][value="'+d.tipo+'"]');if(r)r.checked=true;
  var ed={evaluacion:'id_evaluacion',inicio:'id_inicio',desarrollo:'id_desarrollo',cierre:'id_cierre',recursos:'id_recursos',adecuaciones:'id_adecuaciones',motivacion:'id_motivacion'};
  for(var k in ed){if(d[k]&&CKEDITOR.instances[ed[k]])CKEDITOR.instances[ed[k]].setData(d[k]);}
  var nd=0;(d.dua||[]).forEach(function(n){var c=document.getElementById('checkDua_'+n);if(c&&!c.checked){c.click();nd++;}});
  /* OA: se elige entre los OA de la unidad abierta comparando su redacción con la clase; el código sugerido por la IA solo desempata */
  var sin=function(s){return s.normalize('NFD').replace(/[̀-ͯ]/g,'');};
  var comunes='analizar explicar comprender identificar reconocer caracterizar considerando ejemplo entre sobre desde mediante traves otros otras estudiantes clase fuentes'.split(' ');
  var pal=sin((d.oa_claves||'').toLowerCase()).split(/[^a-zñ0-9]+/).filter(function(p,i,a){return p.length>4&&a.indexOf(p)===i&&comunes.indexOf(p)<0;});
  var filas=[].slice.call(document.querySelectorAll('#paso2 input[name="oft[]"]')).map(function(c){var tr=c.closest('tr');
   var f={c:c,cod:tr?tr.cells[0].innerText.replace(/\s+/g,'').toUpperCase():'',txt:sin(tr?tr.innerText.toLowerCase():''),s:0};
   pal.forEach(function(p){if(f.txt.indexOf(p)>=0)f.s++;});return f;});
  var max=filas.reduce(function(m,f){return Math.max(m,f.s);},0),mejor=filas.filter(function(f){return f.s===max;})[0];
  var sugeridos=filas.filter(function(f){return (d.oa||[]).indexOf(f.cod)>=0;}),elegidos=[],nota='';
  var norm=function(s){return sin(String(s).toLowerCase()).replace(/[^a-zñ0-9]+/g,' ').trim();},verificados=[];
  Object.keys(d.oa_textos||{}).forEach(function(cod){var ref=norm(d.oa_textos[cod]).slice(0,50);
   if(ref.length<20)return;filas.forEach(function(f){if(norm(f.txt).indexOf(ref)>=0&&verificados.indexOf(f)<0)verificados.push(f);});});
  if(verificados.length){elegidos=verificados;}
  else if(d.oa_exactos&&sugeridos.length){elegidos=sugeridos;}
  else if(filas.length===1){elegidos=filas;}
  else if(max>=2){elegidos=sugeridos.filter(function(f){return f.s>=max*0.6;});
   if(!elegidos.length){elegidos=[mejor];nota=' (elegido por contenido'+((d.oa||[]).length?'; la IA sugería '+d.oa.join(', '):'')+')';}}
  else{elegidos=sugeridos;}
  elegidos.forEach(function(f){if(!f.c.checked)f.c.click();});
  var faltan=d.oa_exactos?(d.oa||[]).filter(function(cod){return !sugeridos.some(function(f){return f.cod===cod;});}):[];
  if(faltan.length)nota+=' (no existen en esta unidad: '+faltan.join(', ')+')';
  var oaTxt=elegidos.length?'OA marcado'+(elegidos.length>1?'s':'')+': '+elegidos.map(function(f){return f.cod;}).join(', ')+nota+'. '
   :'⚠ No se pudo elegir el OA en esta unidad: márcalo en el Paso 2. ';
  aviso('✓ Clase cargada. '+oaTxt+'Pautas DUA marcadas: '+nd+'. Revisa los pasos 1 a 4 y presiona Guardar.',true);}
 var d=null;try{d=leer(await Promise.race([navigator.clipboard.readText(),new Promise(function(r){setTimeout(function(){r('');},2500);})]));}catch(e){}
 if(d){procesar(d);return;}
 var c=document.createElement('div');
 c.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:2147483646;display:flex;align-items:center;justify-content:center';
 c.innerHTML='<div style="background:#fff;padding:16px;border-radius:8px;width:min(560px,90vw);font:14px sans-serif"><b>Pega aquí la clase copiada desde el Planificador (Ctrl+V)</b><textarea style="width:100%%;height:160px;margin:8px 0;box-sizing:border-box"></textarea><button>Llenar</button> <button>Cancelar</button></div>';
 document.body.appendChild(c);var ta=c.querySelector('textarea'),b=c.querySelectorAll('button');ta.focus();
 b[1].onclick=function(){c.remove();};
 b[0].onclick=function(){var x=leer(ta.value);if(!x){ta.style.outline='3px solid #C62828';return;}c.remove();procesar(x);};
})();
""" % MARCA

# El marcador queda en una sola línea: un comentario '//' anularía todo el código que le sigue
assert "//" not in _CODIGO_MARCADOR.replace("://", ""), "Usa /* */ para comentar dentro del marcador"
ENLACE_MARCADOR = "javascript:" + quote(" ".join(_CODIGO_MARCADOR.split()), safe="(){}[];,:='+!.*/?&")
