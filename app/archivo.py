"""Archivo mensual: el día 25 se copian a un Excel y se quitan de la vista los datos
del período ya presentado (el de octubre se presenta hasta el 15 de noviembre: el 20
de noviembre se archiva octubre y todo lo anterior)."""
import io
import json
import os
import re
from datetime import date, datetime

import pandas as pd

from . import db, logic, seguridad

ARCHIVO_DIR = os.path.join(db.DATA_DIR, "archivo")
DIA_ARCHIVO = int(os.environ.get("ARCHIVE_DAY", "25"))
_RE = re.compile(r"^Archivo_(AVALIAN|SANCOR|GALENO|SWISS)_hasta_\d{6}_\d{8}_\d{6}\.xlsx$")


def periodo_a_archivar(hoy=None):
    """MMAAAA del mes anterior si ya pasó el día de archivo; si no, el de dos meses atrás."""
    hoy = hoy or date.today()
    atras = 1 if hoy.day >= DIA_ARCHIVO else 2
    m, a = hoy.month - atras, hoy.year
    while m < 1:
        m, a = m + 12, a - 1
    return f"{m:02d}{a}"


def _corte(periodo):
    return f"{periodo[2:]}-{periodo[:2]}"          # AAAA-MM


def _evweb_a_archivar(c, os_key, corte):
    # fecha de la prestación; si la fila no la tiene, la de la extracción
    return c.execute(
        "SELECT f.id, f.data, f.fecha FROM evweb_filas f LEFT JOIN evweb_extracciones e ON e.id=f.extraccion_id "
        "WHERE f.os=? AND CASE WHEN COALESCE(f.fecha,'')<>'' THEN substr(f.fecha,1,7) "
        "ELSE substr(e.fecha,7,4)||'-'||substr(e.fecha,4,2) END <= ?", (os_key, corte)).fetchall()


def pendiente(os_key, periodo):
    corte = _corte(periodo)
    with db._lock:
        ev = len(_evweb_a_archivar(db.conn(), os_key, corte))
    lin = db.scalar("SELECT COUNT(*) FROM lineas WHERE os=? AND estado='template' AND substr(periodo,3,4)||'-'||substr(periodo,1,2) <= ?",
                    (os_key, corte))
    return {"evweb": ev, "lineas": lin}


def archivar(os_key, periodo):
    """Copia a un Excel y quita de la base: lo extraído de EVWEB y las líneas ya emitidas en
    templates, del período indicado y anteriores. Lo pendiente (pre-facturación y facturación) no se toca."""
    periodo = logic.validar_periodo(periodo)
    corte = _corte(periodo)
    os.makedirs(ARCHIVO_DIR, mode=0o700, exist_ok=True)
    with db.tx() as c:
        ev = [dict(r) for r in _evweb_a_archivar(c, os_key, corte)]
        lin = [dict(r) for r in c.execute(
            "SELECT * FROM lineas WHERE os=? AND estado='template' AND substr(periodo,3,4)||'-'||substr(periodo,1,2) <= ?",
            (os_key, corte)).fetchall()]
        if not ev and not lin:
            return None
        nombres = {r["id"]: r["nombre"] for r in c.execute("SELECT id, nombre FROM templates").fetchall()}
        for l in lin:
            l["template"] = nombres.get(l.pop("template_id"), "")
            l.pop("estado", None)
        nombre = f"Archivo_{os_key}_hasta_{periodo}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        ruta = os.path.join(ARCHIVO_DIR, nombre)
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as w:
            pd.DataFrame([json.loads(r["data"]) for r in ev]).to_excel(w, index=False, sheet_name="Datos EVWEB")
            pd.DataFrame(lin).to_excel(w, index=False, sheet_name="Lineas emitidas")
            for h in w.sheets.values():
                logic.sin_formulas(h)
        with open(ruta, "wb") as f:
            f.write(out.getvalue())
        os.chmod(ruta, 0o600)
        # solo se borra después de comprobar que el archivo quedó escrito y completo
        chk = pd.read_excel(ruta, sheet_name=None)
        if len(chk["Datos EVWEB"]) != len(ev) or len(chk["Lineas emitidas"]) != len(lin):
            os.remove(ruta)
            raise RuntimeError("El archivo no se pudo verificar; no se quitó ningún dato.")
        for bloque in (ev[i:i + 500] for i in range(0, len(ev), 500)):
            c.execute(f"DELETE FROM evweb_filas WHERE id IN ({','.join('?' * len(bloque))})", [r["id"] for r in bloque])
        for bloque in (lin[i:i + 500] for i in range(0, len(lin), 500)):
            c.execute(f"DELETE FROM lineas WHERE id IN ({','.join('?' * len(bloque))})", [r["id"] for r in bloque])
    return {"archivo": nombre, "evweb": len(ev), "lineas": len(lin), "hasta_periodo": periodo,
            "bytes": os.path.getsize(ruta)}


def listar():
    if not os.path.isdir(ARCHIVO_DIR):
        return []
    out = []
    for n in sorted(os.listdir(ARCHIVO_DIR), reverse=True):
        if _RE.match(n):
            st = os.stat(os.path.join(ARCHIVO_DIR, n))
            p = n.split("_")
            out.append({"nombre": n, "os": p[1], "hasta_periodo": p[3], "bytes": st.st_size,
                        "fecha": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M")})
    return out


def ruta(nombre):
    if not _RE.match(nombre or ""):
        return None
    r = os.path.join(ARCHIVO_DIR, nombre)
    return r if os.path.isfile(r) else None


def automatico():
    """Lo llama el ciclo de mantenimiento: desde el día 25, archiva el período anterior."""
    if date.today().day < DIA_ARCHIVO:
        return
    periodo = periodo_a_archivar()
    for os_key in logic.OBRAS:
        p = pendiente(os_key, periodo)
        if not (p["evweb"] or p["lineas"]):
            continue
        b = seguridad.crear_backup()      # copia de seguridad completa antes de quitar nada
        r = archivar(os_key, periodo)
        if r:
            seguridad.auditar("sistema", "", "archivo.automatico", os_key, "archivo", r["archivo"],
                              {**r, "backup_previo": b["nombre"]})
