"""Convierte un Markdown de docs/ en un HTML con el estilo de la aplicación, listo para imprimir a PDF.

Uso:  python docs/generar_pdf.py <archivo.md> <salida.html> "<título>" "<bajada>" [carpeta_de_capturas]
Después:  node docs/generar_pdf.js <salida.html> <salida.pdf> "<pie de página>"
"""
import base64
import html
import io
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def inl(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)


def imagen(ruta):
    """Captura reducida y embebida, para que el PDF no pese de más."""
    from PIL import Image
    im = Image.open(ruta).convert("RGB")
    if im.width > 1700:
        im = im.resize((1700, round(im.height * 1700 / im.width)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def cuerpo(lineas, capturas):
    out, toc, i, primero = [], [], 0, True
    while i < len(lineas):
        l = lineas[i]
        if l.startswith("# "):
            i += 1
        elif l.startswith("## "):
            m = re.match(r"(\d+)\. (.*)", l[3:])
            n, t = m.group(1), m.group(2)
            toc.append((n, t))
            out.append(("" if primero else "</section>") + f'<section class="cap"><h2 id="s{n}"><span class="num">{n}</span>{inl(t)}</h2>')
            primero = False
            i += 1
        elif l.startswith("### "):
            out.append(f"<h3>{inl(l[4:])}</h3>")
            i += 1
        elif l.startswith("!["):
            m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", l)
            out.append(f'<figure><img src="{imagen(os.path.join(capturas, m.group(2)))}" alt="{html.escape(m.group(1))}"></figure>')
            i += 1
        elif l.startswith("|"):
            filas = []
            while i < len(lineas) and lineas[i].startswith("|"):
                filas.append([c.strip() for c in lineas[i].strip().strip("|").split("|")])
                i += 1
            out.append("<table><thead><tr>" + "".join(f"<th>{inl(c)}</th>" for c in filas[0]) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inl(c)}</td>" for c in f) + "</tr>" for f in filas[2:])
                       + "</tbody></table>")
        elif re.match(r"\d+\. ", l):
            items = []
            while i < len(lineas) and re.match(r"\d+\. ", lineas[i]):
                items.append(re.sub(r"^\d+\. ", "", lineas[i]))
                i += 1
            out.append("<ol>" + "".join(f"<li>{inl(x)}</li>" for x in items) + "</ol>")
        elif l.startswith("- "):
            items = []
            while i < len(lineas) and lineas[i].startswith("- "):
                items.append(lineas[i][2:])
                i += 1
            out.append("<ul>" + "".join(f"<li>{inl(x)}</li>" for x in items) + "</ul>")
        else:
            if l.strip():
                clase = "portal" if l.startswith("Portal:") else "rot" if re.fullmatch(r"\*\*[^*]+\*\*", l.strip()) \
                    else "sigue" if l.rstrip().endswith(":") else ""
                out.append(f'<p class="{clase}">{inl(l)}</p>' if clase else f"<p>{inl(l)}</p>")
            i += 1
    out.append("</section>")
    return "".join(out), toc


def fuente(nombre):
    with open(os.path.join(RAIZ, "app", "static", "fonts", nombre), "rb") as f:
        return base64.b64encode(f.read()).decode()


CSS = """
@font-face{font-family:"Montserrat";font-weight:100 900;src:url(data:font/woff2;base64,__EXT__) format("woff2");unicode-range:U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF}
@font-face{font-family:"Montserrat";font-weight:100 900;src:url(data:font/woff2;base64,__LAT__) format("woff2");unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD}
@page{size:A4;margin:22mm 18mm 20mm}
@page:first{margin:0}
:root{--navy:#1e3a8a;--tinta:#1d2740;--suave:#56617a;--linea:#e3e8f1}
*{box-sizing:border-box}
body{margin:0;font:500 9.6pt/1.55 "Montserrat",sans-serif;color:var(--tinta);-webkit-print-color-adjust:exact;print-color-adjust:exact}
.tapa{height:297mm;padding:34mm 24mm 26mm;display:flex;flex-direction:column;background:linear-gradient(120deg,#152a6b 0%,#1e3a8a 50%,#4a70c8 100%);color:#fff;page-break-after:always}
.tapa .marca{font-size:15pt;font-weight:800;line-height:1.1}.tapa .marca span{display:block;font-size:6.5pt;font-weight:700;letter-spacing:.18em;color:#b9c8ee;margin-top:4px}
.tapa h1{font-size:40pt;font-weight:800;letter-spacing:-.02em;line-height:1.05;margin:auto 0 10mm;max-width:11em}
.tapa p{font-size:11pt;color:#d6e0f7;max-width:30em;margin:0}
.tapa .pie{margin-top:14mm;font-size:7.5pt;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#b9c8ee;display:flex;justify-content:space-between}
.indice{page-break-after:always}
.indice h2{font-size:18pt;margin:0 0 8mm;display:block}
.indice ol{list-style:none;padding:0;margin:0}
.indice li{display:flex;gap:10px;align-items:baseline;padding:6px 0;border-bottom:1px solid var(--linea);font-weight:600}
.indice li b{color:var(--navy);font-weight:800;width:2em;font-variant-numeric:tabular-nums}
.indice a{color:inherit;text-decoration:none}
.intro{font-size:10.5pt;color:var(--suave);margin:0 0 8mm;max-width:38em}
.cap{page-break-before:always}.cap:first-of-type{page-break-before:auto}
h2{font-size:17pt;font-weight:800;color:var(--navy);letter-spacing:-.015em;margin:0 0 5mm;padding-bottom:3mm;border-bottom:2px solid var(--navy);display:flex;align-items:baseline;gap:10px}
h2 .num{font-size:9pt;background:var(--navy);color:#fff;border-radius:999px;padding:3px 11px;font-variant-numeric:tabular-nums;position:relative;top:-3px}
h3{font-size:11pt;font-weight:800;color:var(--navy);margin:7mm 0 2.5mm;page-break-after:avoid}
p{margin:0 0 3mm;orphans:3;widows:3}
p.rot{margin-top:5mm;page-break-after:avoid;color:var(--navy)}
p.sigue{page-break-after:avoid}
p.portal{font-size:8.5pt;color:var(--suave);font-weight:600}
b{font-weight:700}
code{font:600 8.6pt ui-monospace,Menlo,Consolas,monospace;background:#eef2fb;color:var(--navy);padding:1px 5px;border-radius:4px}
ol,ul{margin:0 0 3.5mm;padding-left:6mm}li{margin-bottom:1.6mm;padding-left:1mm}
ol li::marker{color:var(--navy);font-weight:800}ul li::marker{color:#8ea3d8}
table{width:100%;border-collapse:collapse;margin:1mm 0 4.5mm;font-size:8.6pt}
thead{display:table-header-group}
th{text-align:left;font-size:6.8pt;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--navy);padding:6px 8px;border-bottom:1.5px solid var(--navy);vertical-align:bottom}
td{padding:6px 8px;border-bottom:1px solid var(--linea);vertical-align:top}
tr{page-break-inside:avoid}
td:first-child{font-weight:600}
figure{margin:0 0 5mm;page-break-inside:avoid}
figure img{display:block;width:100%;border:1px solid var(--linea);border-radius:8px;box-shadow:0 3px 12px rgba(23,45,110,.12)}
.pasos .cap{page-break-before:auto;page-break-inside:avoid;margin-bottom:9mm}
.pasos h2{font-size:13pt;margin-bottom:3.5mm;padding-bottom:2mm;border-bottom-width:1.5px}
"""


def main():
    md, salida, titulo, bajada = sys.argv[1:5]
    capturas = sys.argv[5] if len(sys.argv) > 5 else ""
    with open(md, encoding="utf-8") as f:
        lineas = f.read().split("\n")
    intro = next((l for l in lineas[1:] if l.strip() and not l.startswith("#")), "") if capturas else ""
    if intro:
        lineas.remove(intro)
    contenido, toc = cuerpo(lineas, capturas)
    css = CSS.replace("__EXT__", fuente("montserrat-latin-ext-wght-normal.woff2")).replace(
        "__LAT__", fuente("montserrat-latin-wght-normal.woff2"))
    indice = "".join(f'<li><b>{n}</b><a href="#s{n}">{html.escape(t)}</a></li>' for n, t in toc)
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{html.escape(titulo)} · Facturación Obras Sociales</title>
<style>{css}</style></head><body>
<div class="tapa"><div class="marca">Facturación<span>OBRAS SOCIALES · C.M.S.C</span></div>
<h1>{html.escape(titulo)}</h1><p>{html.escape(bajada)}</p>
<div class="pie"><span>Rol operador</span><span>Noviembre 2026</span></div></div>
<div class="indice"><h2>Contenido</h2><ol>{indice}</ol></div>
<div class="{'pasos' if capturas else ''}">{f'<p class="intro">{inl(intro)}</p>' if intro else ''}{contenido}</div></body></html>"""
    with open(salida, "w", encoding="utf-8") as f:
        f.write(doc)
    print(salida, len(doc) // 1024, "KB ·", len(toc), "secciones")


if __name__ == "__main__":
    main()
