"""Portal de Financiadores: datos de contacto y de presentación de cada obra social.

Cada financiador tiene sus referentes, mails, plazo, portal y credenciales del portal, y la modalidad con
la que se le presenta la facturación (portal, mail o las dos). Cada presentación queda registrada.

Las contraseñas de los portales se guardan cifradas. La clave de cifrado sale de la variable de entorno
PORTALES_KEY o, si no está, de un archivo que se crea solo en /data (portales.key, permiso 0600).
Ese archivo NO forma parte de las copias de seguridad de la base: una copia sin él no deja leer las
contraseñas, así que hay que resguardarlo aparte.
"""
import io
import os
import re
from datetime import datetime
from urllib.parse import quote

import pandas as pd
from cryptography.fernet import Fernet, InvalidToken
from openpyxl import load_workbook

from . import db

ARCHIVO_CLAVE = os.path.join(db.DATA_DIR, "portales.key")
MODALIDADES = ("portal", "mail", "portal y mail", "manual")
# Direcciones que van siempre en copia en los mails de presentación (se pueden cambiar desde la pantalla)
CC_POR_DEFECTO = os.environ.get("PRESENTACIONES_CC", "cynthia_acosta@hotmail.com; colmedcr@gmail.com")


def copias():
    f = db.q1("SELECT valor FROM ajustes WHERE clave='presentaciones_cc'")
    return limpiar_mails(f["valor"]) if f else limpiar_mails(CC_POR_DEFECTO)


def guardar_copias(texto):
    cc = limpiar_mails(texto)
    if _n(texto) and not cc:
        raise ValueError("No hay ninguna dirección de mail válida.")
    with db.tx() as c:
        c.execute("INSERT INTO ajustes(clave,valor) VALUES ('presentaciones_cc',?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (cc,))
    return cc
CAMPOS = ("nombre", "ref_principal", "ref_suplente", "ref_os", "ref_os2", "plazo", "mails", "telefono",
          "url_portal", "usuario", "modalidad", "notas")
_fernet = None


def _cifrador():
    global _fernet
    if _fernet is None:
        clave = os.environ.get("PORTALES_KEY", "").strip().encode()
        if not clave:
            if not os.path.exists(ARCHIVO_CLAVE):
                os.makedirs(db.DATA_DIR, mode=0o700, exist_ok=True)
                fd = os.open(ARCHIVO_CLAVE, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as f:
                    f.write(Fernet.generate_key())
            with open(ARCHIVO_CLAVE, "rb") as f:
                clave = f.read().strip()
        try:
            _fernet = Fernet(clave)
        except Exception:
            raise ValueError("La clave de cifrado de los portales (PORTALES_KEY) no es válida.") from None
    return _fernet


def cifrar(texto):
    return _cifrador().encrypt(texto.encode()).decode() if texto else ""


def descifrar(cifrado):
    if not cifrado:
        return ""
    try:
        return _cifrador().decrypt(cifrado.encode()).decode()
    except InvalidToken:
        raise ValueError("No se puede leer la contraseña guardada: la clave de cifrado cambió. Volvé a cargarla.") from None


def _n(v):
    s = "" if v is None or (isinstance(v, float) and pd.isna(v)) else " ".join(str(v).split())
    return "" if s.lower() in ("nan", "none") else s


def _clave_nombre(nombre):
    return re.sub(r"[^a-z0-9]", "", _n(nombre).lower())


def limpiar_mails(texto):
    """Direcciones válidas de un texto libre («a@x.com ; <b@y.com>» → a@x.com; b@y.com)."""
    vistos, out = set(), []
    for m in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", _n(texto)):
        if m.lower() not in vistos:
            vistos.add(m.lower())
            out.append(m)
    return "; ".join(out)


def url_segura(url):
    u = _n(url)
    if u and not re.match(r"^https?://", u, re.I):
        u = "https://" + u if re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", u, re.I) else ""
    return u


def clasificar_modalidad(texto):
    t = _n(texto).lower()
    if not t:
        return ""
    portal, mail = "portal" in t, "mail" in t
    if portal and mail:
        return "portal y mail"
    if portal:
        return "portal"
    if mail:
        return "mail"
    if any(x in t for x in ("manual", "fisic", "sede", "retiran")):
        return "manual"
    return ""


def publico(f):
    """Fila para mostrar: nunca incluye la contraseña, solo si está cargada."""
    d = {k: f[k] for k in ("id",) + CAMPOS + ("actualizado",)}
    d["tiene_clave"] = bool(f["clave"])
    return d


def listar():
    filas = db.q("SELECT * FROM financiadores ORDER BY nombre COLLATE NOCASE")
    ult = {r["financiador_id"]: r for r in db.q(
        "SELECT e.* FROM entregas e JOIN (SELECT financiador_id, MAX(id) m FROM entregas GROUP BY financiador_id) x ON x.m=e.id")}
    out = []
    for f in filas:
        d = publico(f)
        u = ult.get(f["id"])
        d["ultima"] = {k: u[k] for k in ("numero", "periodo", "factura", "importe", "fecha", "via")} if u else None
        out.append(d)
    return out


def guardar(d, fid=None):
    vals = {k: _n(d.get(k)) for k in CAMPOS}
    if not vals["nombre"]:
        raise ValueError("El nombre de la obra social es obligatorio.")
    if vals["modalidad"] and vals["modalidad"] not in MODALIDADES:
        raise ValueError("La modalidad debe ser: " + ", ".join(MODALIDADES) + ".")
    vals["url_portal"] = url_segura(vals["url_portal"])
    vals["mails"] = limpiar_mails(vals["mails"]) or vals["mails"]
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    with db.tx() as c:
        otro = c.execute("SELECT id FROM financiadores WHERE nombre=? COLLATE NOCASE AND id<>?", (vals["nombre"], fid or 0)).fetchone()
        if otro:
            raise ValueError(f"Ya hay un financiador llamado {vals['nombre']}.")
        if fid:
            c.execute(f"UPDATE financiadores SET {','.join(k + '=?' for k in CAMPOS)}, actualizado=? WHERE id=?",
                      [vals[k] for k in CAMPOS] + [ahora, fid])
        else:
            fid = c.execute(f"INSERT INTO financiadores({','.join(CAMPOS)},clave,actualizado) VALUES ({','.join('?' * len(CAMPOS))},'',?)",
                            [vals[k] for k in CAMPOS] + [ahora]).lastrowid
        if "clave" in d and d["clave"] is not None and str(d["clave"]) != "":      # vacío = no cambiar
            c.execute("UPDATE financiadores SET clave=? WHERE id=?", (cifrar(str(d["clave"])), fid))
        elif d.get("borrar_clave"):
            c.execute("UPDATE financiadores SET clave='' WHERE id=?", (fid,))
    return db.q1("SELECT * FROM financiadores WHERE id=?", (fid,))


def importar(contenido):
    """Excel «Portal de OS»: solapa de contactos (Obra Social, referentes, plazo, mails, teléfono, URL del portal,
    usuario y contraseña) y, si está, la de seguimiento de entregas, de la que se toma la modalidad más usada.
    Actualiza por nombre de obra social; no borra las que no vienen en el archivo."""
    try:
        wb = load_workbook(io.BytesIO(contenido))
    except Exception:
        raise ValueError("No se pudo leer el archivo: debe ser un Excel (.xlsx).") from None
    hoja = None
    for ws in wb.worksheets:
        cab = [_n(c.value).lower() for c in next(ws.iter_rows(min_row=1, max_row=1), [])]
        if any(x.startswith("obra social") for x in cab) and any("mail" in x for x in cab):
            hoja, cabecera = ws, cab
            break
    if hoja is None:
        raise ValueError("El archivo no tiene la solapa de contactos (columnas Obra Social, Mails, URL Portal…).")

    def col(*nombres):
        for n in nombres:
            for i, x in enumerate(cabecera):
                if x == n or x.startswith(n):
                    return i
        return None

    i_nom, i_rp, i_rs = col("obra social"), col("referente principal"), col("referente suplente")
    i_ro = [i for i, x in enumerate(cabecera) if x.replace("-", "").replace(" ", "") == "referenteos"]
    i_pl, i_ma, i_te = col("plazo"), col("mails", "mail"), col("telefono", "teléfono")
    i_url, i_us, i_cl = col("url"), col("usuario"), col("contraseña", "contrasena", "clave")

    # modalidad más frecuente por obra social, de la solapa de seguimiento
    modal = {}
    for ws in wb.worksheets:
        cab = [_n(c.value).lower() for c in next(ws.iter_rows(min_row=1, max_row=1), [])]
        if ws is hoja or not any("modalidad" in x for x in cab):
            continue
        j_os, j_mod = next(i for i, x in enumerate(cab) if x.startswith("obra social")), next(i for i, x in enumerate(cab) if "modalidad" in x)
        cuenta = {}
        for r in ws.iter_rows(min_row=2, values_only=True):
            m = clasificar_modalidad(r[j_mod] if j_mod < len(r) else "")
            k = _clave_nombre(r[j_os] if j_os < len(r) else "")
            if m and k:
                cuenta.setdefault(k, {})[m] = cuenta.setdefault(k, {}).get(m, 0) + 1
        modal = {k: max(v, key=v.get) for k, v in cuenta.items()}

    nuevos = actualizados = con_clave = 0
    for fila in hoja.iter_rows(min_row=2):
        v = lambda i: _n(fila[i].value) if i is not None and i < len(fila) else ""  # noqa: E731
        nombre = v(i_nom)
        if not nombre:
            continue
        url = ""
        if i_url is not None and i_url < len(fila):
            celda = fila[i_url]
            url = url_segura(celda.hyperlink.target if celda.hyperlink and celda.hyperlink.target else celda.value)
        mails = limpiar_mails(v(i_ma))
        modalidad = modal.get(_clave_nombre(nombre)) or ("portal y mail" if url and mails else "portal" if url else "mail" if mails else "")
        if modalidad in ("portal", "portal y mail") and not url:
            modalidad = "mail" if mails else "manual"
        d = dict(nombre=nombre, ref_principal=v(i_rp), ref_suplente=v(i_rs), ref_os=v(i_ro[0]) if i_ro else "",
                 ref_os2=v(i_ro[1]) if len(i_ro) > 1 else "", plazo=v(i_pl), mails=mails or v(i_ma), telefono=v(i_te),
                 url_portal=url, usuario=v(i_us), modalidad=modalidad)
        clave = v(i_cl)
        ya = db.q1("SELECT * FROM financiadores WHERE nombre=? COLLATE NOCASE", (nombre,))
        if ya:
            d["notas"] = ya["notas"]
        if clave:
            d["clave"] = clave
            con_clave += 1
        guardar(d, ya["id"] if ya else None)
        nuevos, actualizados = nuevos + (not ya), actualizados + bool(ya)
    return {"nuevos": nuevos, "actualizados": actualizados, "con_clave": con_clave}


def periodo_legible(periodo):
    return f"{periodo[:2]}/{periodo[2:]}"


def presentar(fid, d, usuario):
    """Registra la presentación y devuelve lo necesario para hacerla: el portal con sus credenciales
    y/o el mail armado (destinatarios, asunto y cuerpo)."""
    f = db.q1("SELECT * FROM financiadores WHERE id=?", (fid,))
    if not f:
        raise ValueError("Financiador inexistente.")
    periodo = _n(d.get("periodo")).replace("/", "").replace("-", "")
    if not re.fullmatch(r"(0[1-9]|1[0-2])\d{4}", periodo):
        raise ValueError("El período debe tener formato MMAAAA (ej: 102026).")
    factura = _n(d.get("factura"))
    if not factura:
        raise ValueError("Indicá el número de factura.")
    try:
        t = _n(d.get("importe")).replace("$", "").replace(" ", "")
        importe = round(float(t.replace(".", "").replace(",", ".") if "," in t else t), 2)
    except ValueError:
        raise ValueError("El importe total de la factura no es un número válido.") from None
    if importe <= 0:
        raise ValueError("El importe total de la factura debe ser mayor que cero.")
    link = _n(d.get("link"))
    if link and not re.match(r"^https?://", link, re.I):
        raise ValueError("El link de la documentación debe empezar con http:// o https://.")
    via = _n(d.get("via")) or ("portal" if f["modalidad"] == "portal" else "mail" if f["modalidad"] == "mail" else "")
    if via not in ("portal", "mail"):
        raise ValueError("Elegí cómo se presenta: por portal o por mail.")
    if via == "portal" and not f["url_portal"]:
        raise ValueError("Este financiador no tiene cargada la dirección del portal.")
    if via == "mail" and not limpiar_mails(f["mails"]):
        raise ValueError("Este financiador no tiene mails cargados.")
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    # copias del mail: las que vienen del formulario o, si no, las de por defecto
    cc = limpiar_mails(d.get("cc")) if d.get("cc") is not None else copias()
    if via != "mail":
        cc = ""
    with db.tx() as c:
        eid = c.execute("INSERT INTO entregas(financiador_id,nombre,periodo,factura,importe,link,via,fecha,usuario,cc) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (fid, f["nombre"], periodo, factura, importe, link, via, ahora, usuario, cc)).lastrowid
        numero = f"P-{eid:06d}"          # número de presentación: correlativo y único
        c.execute("UPDATE entregas SET numero=? WHERE id=?", (numero, eid))
    r = {"id": eid, "numero": numero, "via": via, "nombre": f["nombre"], "periodo": periodo, "factura": factura,
         "importe": importe, "link": link}
    if via == "portal":
        r.update(url=f["url_portal"], usuario=f["usuario"], clave=descifrar(f["clave"]))
    else:
        asunto = f"Facturacion Mensual_{periodo}"
        cuerpo = ("Estimados,\n\n"
                  f"Presentamos la facturación correspondiente al mes {periodo_legible(periodo)}.\n\n"
                  "Se adjunta:\n"
                  "1) Facturación\n"
                  "2) Detalle de prestaciones\n"
                  f"3) Link de facturación: {link or '(sin link)'}\n\n"
                  f"N° de presentación: {numero}\n")
        para = limpiar_mails(f["mails"])
        r.update(para=para, cc=cc, asunto=asunto, cuerpo=cuerpo,
                 mailto="mailto:" + quote(para.replace("; ", ","), safe="@,") + "?"
                 + (("cc=" + quote(cc.replace("; ", ","), safe="@,") + "&") if cc else "")
                 + "subject=" + quote(asunto) + "&body=" + quote(cuerpo))
    return r
