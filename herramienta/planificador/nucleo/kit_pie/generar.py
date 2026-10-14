# -*- coding: utf-8 -*-
import base64, os, html, unicodedata
import pictos

BASE = os.path.dirname(os.path.abspath(__file__))
ROJO="#CC0000"; VERDE="#2E7D32"; GRIS_G="#AAAAAA"; AZUL="#1787C8"
GRIS_E="#CCCCCC"; NAVY="#1F3B57"; BARRA="#DCE6F1"; MAX_CELLS=14
ARTS={"EL","LA","LOS","LAS","UN","UNA","UNOS","UNAS","LO"}

# Palabra del texto (sin tilde, mayúscula) -> término que se busca en ARASAAC. Se rearma en cada guía
# (configurar_pictos) según la asignatura; ver pictos.py.
PICTO_MAP = {}

def configurar_pictos(asignatura="", extras=None):
    """Reinicia el diccionario con el de la asignatura y las equivalencias que la IA propuso para esta guía."""
    PICTO_MAP.clear()
    PICTO_MAP.update(pictos.para(asignatura))
    for palabra, termino in (extras or {}).items():
        if palabra and termino:
            PICTO_MAP[norm(str(palabra))] = str(termino)

# Palabras de 4+ letras que no llevan pictograma automático (conectores, cuantificadores, verbos auxiliares)
PALABRAS_SIN_PICTO = {
    "PARA","COMO","PERO","ESTE","ESTA","ESTO","ESTOS","ESTAS","ESOS","ESAS","SOBRE","ENTRE","DESDE","HASTA",
    "CUANDO","DONDE","MUCHO","MUCHA","MUCHOS","MUCHAS","TODO","TODA","TODOS","TODAS","OTRO","OTRA","OTROS","OTRAS",
    "CADA","ANTES","DESPUES","DURANTE","TAMBIEN","SOLO","SOLA","PORQUE","SEGUN","CUAL","CUALES","QUIEN","QUIENES",
    "AQUI","ALLI","AHORA","SIEMPRE","NUNCA","CASI","TRAS","CONTRA","HACIA","MISMO","MISMA","ESTAN","ERAN","HABIA",
    "TENIA","TIENE","TIENEN","FUERON","SIDO","SERA","PUEDE","PUEDEN","ALGO","ALGUN","ALGUNOS","ALGUNAS","NADA",
    "OBJETIVO",
}
AUTO_PICTOS = True  # busca en ARASAAC un pictograma para cada palabra con contenido (si no existe, no se muestra)

def termino_picto(palabra):
    """Término de búsqueda en ARASAAC para una palabra, o None si no lleva pictograma."""
    nw = norm(palabra)
    if nw in PICTO_MAP:
        return PICTO_MAP[nw]
    if AUTO_PICTOS and len(nw) >= 4 and nw not in PALABRAS_SIN_PICTO and nw not in ARTS:
        return "".join(ch for ch in palabra if ch.isalpha()).lower()
    return None

def picto_frase(texto, cls="picto-mini"):
    """Un pictograma para una frase corta (opción de MARCAR, rótulo de RECONOCER o concepto de UNIR):
    la primera palabra del diccionario o, si no hay, la primera palabra con contenido."""
    palabras = texto.split()
    termino = next((PICTO_MAP[norm(w)] for w in palabras if norm(w) in PICTO_MAP), None) or \
              next((t for t in (termino_picto(w) for w in palabras) if t), None)
    if not termino:
        return ""
    return f'<img class="pw {cls}" data-picto="{html.escape(termino)}" alt="" title="Clic para cambiar el pictograma">'

_cache={}
def b64(path):
    if path not in _cache:
        with open(path,"rb") as f: raw=f.read()
        _cache[path]=(base64.b64encode(raw).decode(),
                      "image/jpeg" if raw[:3]==b'\xff\xd8\xff' else "image/png")
    return _cache[path]

def img_tag(path,cls="",style=""):
    data,mime=b64(path)
    c=f' class="{cls}"' if cls else ""; s=f' style="{style}"' if style else ""
    return f'<img{c}{s} src="data:{mime};base64,{data}" alt="">'

def verbo_picto(v): return os.path.join(BASE,"pictos","verbos",v.lower()+".png")
def art_picto(a):   return os.path.join(BASE,"pictos","articulos","art_"+a.lower()+".png")
CONTENT_DIR=os.path.join(BASE,"content")  # armar_guia_pie lo apunta a una carpeta temporal por guía
def content_img(n): return os.path.join(CONTENT_DIR,n)

def norm(w):
    w=unicodedata.normalize("NFD",w)
    return "".join(c for c in w if c.isalpha() and not unicodedata.combining(c)).upper()
_strip_punct=lambda w: "".join(ch for ch in w if ch.isalpha())

def _wrap_lines(phrase):
    lines,cur=[],[]
    for w in phrase.split(" "):
        art=norm(w) in ARTS
        wc=[{"type":"letter","ch":ch,"is_art":art} for ch in w]
        if not cur: cur=list(wc)
        elif len(cur)+1+len(wc)<=MAX_CELLS: cur.append({"type":"space"}); cur+=wc
        else: lines.append(cur); cur=list(wc)
    if cur: lines.append(cur)
    return lines

def _guides_for_line(line):
    guides=set(); n=len(line); i=0
    while i<n:
        if line[i]["type"]=="letter":
            j=i; idx=[]
            while j<n and line[j]["type"]=="letter":
                if line[j]["ch"].isalpha(): idx.append(j)
                j+=1
            if idx:
                guides.add(idx[0])
                if len(idx)>4: guides.add(idx[len(idx)//2])
            i=j
        else: i+=1
    return guides

def _picto_row(line):
    """Fila de pictogramas: artículos (imagen local) y palabras clave (ARASAAC, las carga el navegador)."""
    n=len(line); spans={}; i=0
    while i<n:
        if line[i]["type"]=="letter":
            j=i
            while j<n and line[j]["type"]=="letter": j+=1
            palabra="".join(x["ch"] for x in line[i:j]); nw=norm(palabra)
            if nw in ARTS and os.path.exists(art_picto(nw)): spans[i]=(j,"art",nw)
            elif termino_picto(palabra): spans[i]=(j,"kw",termino_picto(palabra))
            i=j
        else: i+=1
    if not spans: return ""
    tds=[]; i=0
    while i<n:
        if i in spans:
            j,kind,key=spans[i]
            if kind=="art": inner=img_tag(art_picto(key),cls="picto-grid")
            else: inner=f'<img class="pw picto-grid" data-picto="{html.escape(key)}" alt="" title="Clic para cambiar el pictograma">'
            tds.append(f'<td class="pic" colspan="{j-i}">{inner}</td>'); i=j
        else:
            tds.append('<td class="pic"></td>'); i+=1
    return f"<tr>{''.join(tds)}</tr>"

def _cell_td(cell,row,guides=None):
    if cell["type"]=="space": return '<td class="sp"></td>'
    ch=html.escape(cell["ch"])
    if row=="model":
        color=ROJO if cell.get("_verbo") else (VERDE if cell["is_art"] else "#000000")
        return f'<td class="c" style="color:{color}">{ch}</td>'
    if row=="copy": return '<td class="c"></td>'
    if guides and cell.get("_idx") in guides: return f'<td class="c" style="color:{GRIS_G}">{ch}</td>'
    return '<td class="c"></td>'

def _emit_line(line,bottom,guides=None):
    top="".join(_cell_td(c,"model") for c in line)
    bot="".join(_cell_td(c,bottom,guides) for c in line)
    return f'<table class="grid">{_picto_row(line)}<tr>{top}</tr><tr>{bot}</tr></table>'

def grid_copy(phrase):
    return '<div class="grid-block">'+"".join(_emit_line(l,"copy") for l in _wrap_lines(phrase))+'</div>'

def grid_complete(phrase):
    out=['<div class="grid-block">']
    for line in _wrap_lines(phrase):
        for k,c in enumerate(line): c["_idx"]=k
        out.append(_emit_line(line,"guide",_guides_for_line(line)))
    out.append('</div>'); return "".join(out)

def instruccion(texto):
    toks=[]
    for i,w in enumerate(texto.split(" ")):
        base=norm(w); pic,color="","#000000"
        if i==0:
            p=verbo_picto(base)
            if os.path.exists(p): pic=img_tag(p,cls="tok-pic-img")
            color=ROJO
        elif base in ARTS:
            p=art_picto(base)
            if os.path.exists(p): pic=img_tag(p,cls="tok-pic-img")
            color=VERDE
        pd=f'<div class="tok-pic">{pic}</div>' if pic else '<div class="tok-pic"></div>'
        toks.append(f'<span class="tok">{pd}<div class="tok-word" style="color:{color}">{html.escape(w)}</div></span>')
    return '<div class="instruccion"><div class="instr-line">'+"".join(toks)+'</div></div>'

def reconocer(instr,pairs):
    celdas="".join(f'<td class="rec-cell"><div class="rec-img-wrap">{img_tag(content_img(im),cls="rec-img")}</div>'
                   f'<div class="rec-label">{picto_frase(c)}<br>{html.escape(c)}</div></td>' for im,c in pairs)
    return instruccion(instr)+f'<div class="grid-block"><table class="reconocer"><tr>{celdas}</tr></table></div>'

def marcar(instr,pregunta,opciones,correcta_idx=None):
    filas="".join(f'<tr><td class="mar-circ"></td><td class="mar-let">{"ABCDE"[i]}</td>'
                  f'<td class="mar-pic">{picto_frase(op)}</td><td class="mar-txt">{html.escape(op)}</td></tr>'
                  for i,op in enumerate(opciones))
    return instruccion(instr)+(f'<div class="grid-block"><p class="mar-pregunta">{picto_frase(pregunta)} {html.escape(pregunta)}</p>'
                               f'<table class="marcar">{filas}</table></div>')

def unir(instr,pairs):
    n=len(pairs); imgs=[p[0] for p in pairs]; concs=[pairs[(i+1)%n][1] for i in range(n)]
    rows="".join(f'<tr><td class="u-num">{i+1}</td><td class="u-imgcell">{img_tag(content_img(imgs[i]),cls="unir-img")}</td>'
                 f'<td class="u-gap"></td><td class="u-let">{"ABCDE"[i]}</td><td class="u-conc">{picto_frase(concs[i])} {html.escape(concs[i])}</td></tr>'
                 for i in range(n))
    return instruccion(instr)+f'<div class="grid-block"><table class="unir">{rows}</table></div>'

def ilustracion(image,caption):
    return (f'<div class="ilustracion">{img_tag(content_img(image),cls="ilus-img")}'
            f'<div class="ilus-cap">{html.escape(caption)}</div></div>')

def ilustracion_web(query,caption):
    """Imagen libre que busca y carga el navegador (Wikimedia Commons + Openverse).
    Botones para cambiarla y para buscar en sitios chilenos y pegar la URL (no se imprimen)."""
    q=html.escape(query,quote=True)
    return (f'<div class="ilustracion web-img empty" data-query="{q}">'
            f'<div class="web-frame"><img class="wimg" alt=""><div class="wph no-print">IMAGEN: {q}</div></div>'
            f'<div class="ilus-cap">{html.escape(caption)}</div><div class="wcred"></div>'
            f'<div class="wctl no-print"><button data-act="prev">◀</button><button data-act="next">▶</button>'
            f'<button data-act="q">BUSCAR OTRA</button><button data-act="url">PEGAR URL</button><br>'
            f'<span class="wsitios">BUSCAR EN:</span><button data-act="mc">MEMORIA CHILENA</button>'
            f'<button data-act="bnd">BIBLIOTECA NACIONAL</button><button data-act="surdoc">SURDOC</button></div></div>')

def seccion(num,titulo,bloques):
    head=(f'<div class="sec-head"><span class="sec-num">{num}</span>'
          f'<span class="sec-title">{html.escape(titulo)}</span></div>')
    return f'<div class="seccion">{head}{"".join(str(b) for b in bloques)}</div>'

escribir_grids=lambda instr,frases: instruccion(instr)+"".join(grid_copy(f) for f in frases)
completar_grids=lambda instr,frases: instruccion(instr)+"".join(grid_complete(f) for f in frases)
copiar_grids=escribir_grids

def lineas_encabezado(nivel, enc=None):
    """(colegio, departamento, tercera línea) del encabezado; enc = {logo, colegio, departamento, asignatura, docente}."""
    enc=enc or {}
    # "Sextos" -> "Sextos Básicos"; un nivel completo como "Primeros Medios" se respeta tal cual
    curso=nivel if " " in nivel.strip() else f"{nivel} Básicos"
    partes=[p for p in (enc.get("asignatura",""),curso,enc.get("docente","")) if p]
    return enc.get("colegio",""), enc.get("departamento",""), "  |  ".join(partes)

def encabezado(nivel="Séptimos", enc=None):
    enc=enc or {}
    colegio,depto,linea3=lineas_encabezado(nivel,enc)
    ruta=enc.get("logo")
    logo=img_tag(ruta,cls="logo") if ruta and os.path.exists(ruta) else ""
    fecha='<table class="fecha"><tr><td class="f-lbl">FECHA</td><td></td><td></td><td></td></tr><tr><td></td><td></td><td></td><td></td></tr></table>'
    lineas="".join(f'<div class="{c}">{html.escape(t).replace("  |  "," &nbsp;|&nbsp; ")}</div>'
                   for c,t in (("enc-1",colegio),("enc-2",depto),("enc-2",linea3)) if t)
    return f'<div class="encabezado">{logo}<div class="enc-text">{lineas}</div></div>{fecha}'

CSS=f"""
*{{box-sizing:border-box}} @page{{size:A4 portrait;margin:1.2cm}}
body{{font-family:Calibri,'Segoe UI',sans-serif;font-size:24pt;font-weight:bold;color:#000;margin:0;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.page{{max-width:720px;margin:0 auto;padding:8px}}
.encabezado{{display:flex;align-items:flex-start;gap:12px;margin-bottom:6px}} .logo{{width:64px;height:auto}}
.enc-text{{line-height:1.15}} .enc-1{{font-size:14pt}} .enc-2{{font-size:10.5pt}}
.fecha{{border-collapse:collapse;margin:6px 0 14px 120px}} .fecha td{{border:1px solid #000;width:70px;height:38px}}
.fecha .f-lbl{{width:150px;font-size:20pt;text-align:center}}
.seccion{{break-before:page;page-break-before:always}}
.sec-head{{display:flex;align-items:stretch;margin:10px 0 8px;break-inside:avoid}}
.sec-num{{background:{NAVY};color:#fff;font-size:20pt;padding:6px 16px;display:flex;align-items:center;justify-content:center;min-width:52px}}
.sec-title{{background:{BARRA};color:{NAVY};font-size:18pt;padding:6px 14px;display:flex;align-items:center;flex:1}}
.ilustracion{{text-align:center;margin:8px 0;break-inside:avoid}} .ilus-img{{max-width:380px;max-height:330px;height:auto}}
.ilus-cap{{font-size:12pt;margin-top:2px;color:#333}}
.instruccion{{margin:14px 0 6px;break-inside:avoid}} .instr-line{{display:flex;flex-wrap:wrap;align-items:flex-end;column-gap:12px;row-gap:2px}}
.tok{{display:inline-flex;flex-direction:column;align-items:center}} .tok-pic{{height:44px;display:flex;align-items:flex-end;justify-content:center}}
img.tok-pic-img{{height:42px;width:auto;object-fit:contain}} .tok-word{{font-size:20pt;line-height:1.1;white-space:nowrap}}
.grid-block{{margin:0 0 12px}} .grid-block table.grid{{break-inside:avoid;margin-bottom:2px}}
table.grid{{border-collapse:collapse;margin:0 0 2px;table-layout:fixed;width:100%}}
table.grid td.c{{height:60px;border:1px solid #000;text-align:center;vertical-align:middle;font-size:24pt;padding:0;overflow:hidden}}
table.grid td.sp{{height:60px;border:1px solid #000;background:{GRIS_E};padding:0}}
table.grid td.pic{{height:42px;border:none;background:transparent;text-align:center;vertical-align:bottom;padding:0 0 1px}}
img.picto-grid{{height:38px;width:auto;max-width:100%;object-fit:contain;display:inline-block}}
img.pw{{display:none;cursor:pointer}}
img.picto-mini{{height:42px;width:auto;max-width:70px;object-fit:contain;vertical-align:middle}}
.pw-mas{{display:none;cursor:pointer;font:bold 16px Calibri,sans-serif;color:#999;border:1px dashed #bbb;border-radius:4px;padding:0 6px;line-height:20px}}
.pw-mas:hover{{color:#1F3B57;border-color:#1F3B57}}
.pw-menu{{position:absolute;z-index:1000;background:#fff;border:2px solid #1F3B57;border-radius:6px;padding:6px;
  box-shadow:0 3px 10px rgba(0,0,0,.25);font:bold 11pt Calibri,sans-serif;display:flex;flex-direction:column;gap:4px}}
.pw-menu button{{font:bold 11pt Calibri,sans-serif;padding:4px 8px;cursor:pointer;text-align:left}}
td.mar-pic{{width:56px;text-align:center;vertical-align:middle}}
table.reconocer{{border-collapse:collapse;width:100%;margin:6px 0}}
td.rec-cell{{border:2px solid #000;text-align:center;vertical-align:top;padding:8px 4px 6px;width:33%}}
.rec-img-wrap{{display:flex;justify-content:center;align-items:center;min-height:90px}}
img.rec-img{{max-width:190px;max-height:170px;height:auto;object-fit:contain}}
.rec-label{{font-size:14pt;margin-top:6px;text-align:center;line-height:1.2}}
.mar-pregunta{{font-size:18pt;margin:8px 0 4px}} table.marcar{{border-collapse:collapse;width:100%;margin:4px 0}}
table.marcar tr{{border-bottom:1px solid #ccc}} td.mar-circ{{width:44px;height:54px;text-align:center;vertical-align:middle}}
td.mar-circ::before{{content:'';display:inline-block;width:32px;height:32px;border:3px solid #000;border-radius:50%}}
td.mar-let{{width:44px;font-size:20pt;text-align:center;vertical-align:middle;color:{AZUL}}}
td.mar-txt{{font-size:18pt;vertical-align:middle;padding:4px 6px}}
table.unir{{border-collapse:collapse;margin:4px 0}} table.unir td{{vertical-align:middle}}
.u-num{{background:{AZUL};color:#fff;font-size:20pt;text-align:center;width:44px;border:2px solid #000}}
.u-imgcell{{border:2px solid #000;padding:4px;text-align:center;width:200px}} .unir-img{{max-width:190px;max-height:160px;height:auto}}
.u-gap{{width:40px;border:none;background:#fff}} .u-let{{background:{ROJO};color:#fff;font-size:20pt;text-align:center;width:44px;border:2px solid #000}}
.u-conc{{border:2px solid #000;padding:6px 12px;font-size:18pt}}
.recuadro{{border:3px solid #000;border-radius:8px;padding:10px 14px;margin:12px 0;font-size:18pt;background:#F5F5F5;break-inside:avoid}}
.web-frame{{min-height:60px;text-align:center}} img.wimg{{display:none;max-width:380px;max-height:300px;height:auto}}
.wph{{font-size:12pt;color:#777;border:2px dashed #999;padding:14px}}
.wcred{{font-size:9pt;color:#444}} .wctl button{{font:bold 11pt Calibri,sans-serif;margin:2px;padding:3px 8px;cursor:pointer}}
.wsitios{{font-size:10pt;color:#555;margin-right:4px}}
.barra-prof{{background:#FFF8E1;border:2px solid #FF8F00;border-radius:6px;padding:8px 12px;margin:0 0 10px;font-size:11pt}}
@media print{{.no-print{{display:none!important}} .web-img.empty{{display:none!important}}}}
"""

JS = r"""
(function(){
 var OV={}; try{OV=JSON.parse(localStorage.getItem('pie_ov')||'{}');}catch(e){}
 function save(){try{localStorage.setItem('pie_ov',JSON.stringify(OV));}catch(e){}}
 // Búsquedas en ARASAAC: una sola por término (se recuerda) y como máximo 4 a la vez
 var PC={},cola=[],activos=0;
 function siguiente(){while(activos<4&&cola.length){cola.shift()();}}
 // Si la palabra exacta no está en ARASAAC, se prueba su forma base: plural -> singular, verbo conjugado -> infinitivo
 function variantes(q){
   var v=[q],s=q.normalize('NFD').replace(/[̀-ͯ]/g,'');
   var reglas=[[/es$/,''],[/s$/,''],[/aron$/,'ar'],[/ieron$/,'er'],[/ieron$/,'ir'],[/aba(n)?$/,'ar'],
     [/ia(n)?$/,'er'],[/ia(n)?$/,'ir'],[/io$/,'er'],[/io$/,'ir'],[/o$/,'ar'],[/an$/,'ar'],[/en$/,'er'],[/en$/,'ir']];
   if(s!==q)v.push(s);
   reglas.forEach(function(r){if(r[0].test(s)){var c=s.replace(r[0],r[1]);if(c.length>=3&&v.indexOf(c)<0)v.push(c);}});
   return v.slice(0,5);
 }
 function sinTilde(s){return String(s||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').trim();}
 // 1) ARASAAC
 function pedir(q){
   return fetch('https://api.arasaac.org/v1/pictograms/es/search/'+encodeURIComponent(q))
     .then(function(r){return r.ok?r.json():[];})
     .then(function(j){return j&&j.length?'https://static.arasaac.org/pictograms/'+j[0]._id+'/'+j[0]._id+'_300.png':null;})
     .catch(function(){return null;});
 }
 // 2) Global Symbols (Mulberry, Sclera, Tawasol y otras colecciones abiertas): solo coincidencias exactas
 function pedirGS(q){
   return fetch('https://globalsymbols.com/api/v1/labels/search?query='+encodeURIComponent(q)+'&language=spa&language_iso_format=639-3&limit=10')
     .then(function(r){return r.ok?r.json():[];})
     .then(function(j){var n=sinTilde(q);
       // Se excluyen los símbolos Bliss (colección 16): son signos abstractos, no sirven a estudiantes no lectoras
       var m=(j||[]).filter(function(x){return x.picto&&x.picto.image_url&&x.picto.symbolset_id!==16&&sinTilde(x.text).split(/[\s,()]+/).indexOf(n)>=0;})[0];
       return m?m.picto.image_url:null;})
     .catch(function(){return null;});
 }
 function buscarPicto(q){
   if(PC[q])return PC[q];
   PC[q]=new Promise(function(listo){
     cola.push(function(){activos++;
       var vs=variantes(q),intentos=[];
       vs.forEach(function(v){intentos.push(function(){return pedir(v);});});
       vs.slice(0,2).forEach(function(v){intentos.push(function(){return pedirGS(v);});});
       var i=0;
       (function probar(){intentos[i]().then(function(u){
         if(u||++i>=intentos.length){listo(u);activos--;siguiente();}else{probar();}});})();});
     siguiente();});
   return PC[q];
 }
 function mostrar(img,u){
   if(u){img.src=u;img.style.display='inline-block';}else{img.style.display='none';}
   if(img._mas)img._mas.style.display=u?'none':'inline-block';
 }
 function setPicto(img,term){
   var o=OV['p:'+term];
   if(o&&o.quitar){mostrar(img,null);return;}
   if(o&&o.url){mostrar(img,o.url);return;}
   buscarPicto((o&&o.q)||term).then(function(u){mostrar(img,u);});
 }
 // Menú (no se imprime) para cambiar un pictograma: otra palabra, Google Imágenes, pegar URL o quitarlo
 var menu=null;
 function cerrarMenu(){if(menu){menu.remove();menu=null;}}
 document.addEventListener('click',function(e){if(menu&&!menu.contains(e.target)&&!e.target.classList.contains('pw')&&!e.target.classList.contains('pw-mas'))cerrarMenu();});
 function abrirMenu(img,term,ancla){
   cerrarMenu();menu=document.createElement('div');menu.className='pw-menu no-print';
   var r=ancla.getBoundingClientRect();menu.style.left=(window.scrollX+r.left)+'px';menu.style.top=(window.scrollY+r.bottom+4)+'px';
   menu.innerHTML='<b>'+term.toUpperCase()+'</b><button data-a="q">OTRA PALABRA</button><button data-a="g">GOOGLE IMÁGENES</button>'+
     '<button data-a="u">PEGAR URL</button><button data-a="x">QUITAR</button>';
   menu.addEventListener('click',function(e){var a=e.target.getAttribute('data-a');if(!a)return;
     if(a==='g'){window.open('https://www.google.com/search?tbm=isch&q='+encodeURIComponent(term+' pictograma'),'_blank');
       alert('Elige una imagen en Google, haz clic derecho sobre ella → «Copiar dirección de imagen» y luego usa PEGAR URL.');return;}
     if(a==='q'){var v=prompt('Buscar otro pictograma para "'+term+'" (ARASAAC y Global Symbols):',term);if(!v)return;OV['p:'+term]={q:v.trim()};}
     if(a==='u'){var u=prompt('Pega la URL de la imagen para "'+term+'":');if(!u||!/^https?:/i.test(u.trim()))return;OV['p:'+term]={url:u.trim()};}
     if(a==='x'){OV['p:'+term]={quitar:1};}
     save();setPicto(img,term);cerrarMenu();});
   document.body.appendChild(menu);
 }
 document.querySelectorAll('img.pw').forEach(function(img){
   var term=img.getAttribute('data-picto');
   // "+" visible solo en pantalla cuando la palabra no tiene pictograma, para poder agregarle uno
   var mas=document.createElement('span');mas.className='pw-mas no-print';mas.textContent='+';mas.title='Agregar pictograma';
   img.parentNode.insertBefore(mas,img.nextSibling);img._mas=mas;
   setPicto(img,term);
   img.addEventListener('click',function(){abrirMenu(img,term,img);});
   mas.addEventListener('click',function(){abrirMenu(img,term,mas);});
 });
 function strip(h){var d=document.createElement('div');d.innerHTML=h||'';return d.textContent||'';}
 // Nombre de la fuente según el sitio de la imagen pegada por el profesor
 var SITIOS=[[/memoriachilena/i,'Memoria Chilena'],[/bibliotecanacionaldigital|bncatalogo|bibliotecanacional/i,'Biblioteca Nacional Digital'],
   [/surdoc/i,'SURDOC'],[/wikimedia|wikipedia/i,'Wikimedia Commons'],[/museohistoriconacional|mhn\.gob/i,'Museo Histórico Nacional'],
   [/openverse|flickr/i,'Openverse']];
 function fuente(u){
   for(var i=0;i<SITIOS.length;i++){if(SITIOS[i][0].test(u))return SITIOS[i][1];}
   try{return new URL(u).hostname.replace(/^www\./,'');}catch(e){return 'Imagen elegida por el profesor';}
 }
 // Búsquedas en sitios chilenos (se abren en otra pestaña; la imagen se trae con PEGAR URL)
 var BUSCADORES={
   mc:function(q){return 'https://www.memoriachilena.gob.cl/602/w3-search.php?keywords='+encodeURIComponent(q)+'&start=0&searchmode=and';},
   bnd:function(q){return 'https://www.google.com/search?tbm=isch&q='+encodeURIComponent('site:bibliotecanacionaldigital.gob.cl '+q);},
   surdoc:function(q){return 'https://www.surdoc.cl/colecciones?query='+encodeURIComponent(q);}
 };
 function showWiki(box){
   var img=box.querySelector('img.wimg'),cred=box.querySelector('.wcred'),ph=box.querySelector('.wph');
   var p=box._res&&box._res[box._i];
   if(!p){box.classList.add('empty');img.style.display='none';if(ph)ph.style.display='block';return;}
   img.onerror=p.alt?function(){img.onerror=null;img.src=p.alt;}:null;
   img.src=p.src;img.style.display='inline-block';box.classList.remove('empty');if(ph)ph.style.display='none';
   cred.textContent=p.cred+'  ('+(box._i+1)+'/'+box._res.length+')';
 }
 function setCred(box,texto){var c=box.querySelector('.wcred');c.textContent=texto;}
 function buscarWikimedia(q){
   var u='https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrlimit=10&gsrsearch='+
     encodeURIComponent('filetype:bitmap '+q)+'&prop=imageinfo&iiprop=url|extmetadata|mime&iiurlwidth=800&format=json&origin=*';
   return fetch(u).then(function(r){return r.json();}).then(function(j){
     return Object.keys((j.query&&j.query.pages)||{}).map(function(k){return j.query.pages[k];})
       .filter(function(p){return p.imageinfo&&/jpeg|png/.test(p.imageinfo[0].mime);})
       .sort(function(a,b){return (a.index||0)-(b.index||0);})
       .map(function(p){var ii=p.imageinfo[0],md=ii.extmetadata||{};
         var a=strip(md.Artist&&md.Artist.value),l=strip(md.LicenseShortName&&md.LicenseShortName.value);
         return {src:ii.thumburl||ii.url,cred:'Fuente: Wikimedia Commons'+(a?' · '+a.slice(0,60):'')+(l?' · '+l:'')};});
   }).catch(function(){return [];});
 }
 function buscarOpenverse(q){
   var u='https://api.openverse.org/v1/images/?page_size=10&excluded_source=wikimedia&q='+encodeURIComponent(q);
   return fetch(u).then(function(r){return r.json();}).then(function(j){
     return (j.results||[]).map(function(x){
       var lic=x.license?('CC '+x.license.toUpperCase()+(x.license_version?' '+x.license_version:'')):'';
       return {src:x.url,alt:x.thumbnail,cred:'Fuente: Openverse'+(x.source?' / '+x.source:'')+
         (x.creator?' · '+String(x.creator).slice(0,60):'')+(lic?' · '+lic:'')};});
   }).catch(function(){return [];});
 }
 function loadWiki(box,q){
   Promise.all([buscarWikimedia(q),buscarOpenverse(q)]).then(function(r){
     box._res=r[0].concat(r[1]);box._i=0;showWiki(box);
   });
 }
 function ponerUrl(box,u){
   var im=box.querySelector('img.wimg');im.onerror=null;im.src=u;im.style.display='inline-block';
   box.classList.remove('empty');var ph=box.querySelector('.wph');if(ph)ph.style.display='none';
   setCred(box,'Fuente: '+fuente(u));
 }
 document.querySelectorAll('.web-img').forEach(function(box){
   var q0=box.getAttribute('data-query'),o=OV['w:'+q0];
   if(o&&o.url){ponerUrl(box,o.url);}
   else loadWiki(box,(o&&o.q)||q0);
   box.querySelectorAll('button').forEach(function(b){b.addEventListener('click',function(){
     var act=b.getAttribute('data-act');o=OV['w:'+q0];
     if(act==='next'||act==='prev'){if(!box._res||!box._res.length)return;
       box._i=(box._i+(act==='next'?1:box._res.length-1))%box._res.length;showWiki(box);}
     else if(act==='q'){var v=prompt('Buscar en Wikimedia Commons y Openverse:',(o&&o.q)||q0);if(v){OV['w:'+q0]={q:v.trim()};save();loadWiki(box,v.trim());}}
     else if(act==='url'){var u=prompt('Pega la URL de la imagen (clic derecho sobre la imagen → Copiar dirección de imagen):');
       if(u&&/^https?:/i.test(u.trim())){OV['w:'+q0]={url:u.trim()};save();ponerUrl(box,u.trim());}}
     else if(BUSCADORES[act]){window.open(BUSCADORES[act]((o&&o.q)||q0),'_blank');}
   });});
 });
})();
"""
