"""Lectura de archivos, cruces, valorización, templates y conversores."""
import calendar
import hashlib
import io
import json
import os
import re
import unicodedata
from datetime import datetime, date

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from . import db, grillas, smg

OBRAS = {
    "AVALIAN": {"codigo": "10067", "nombre": "10067 - A.C.A. SALUD (AVALIAN)"},
    "SANCOR": {"codigo": "10117", "nombre": "10117 - ASOCIACION MUTUAL SANCOR"},
    "GALENO": {"codigo": "10099", "nombre": "10099 - GALENO Argentina S.A. AZUL/BLANCO/ORO/PLATA"},
    # SWISS MEDICAL tiene dos códigos en EVWEB: el bot extrae primero 11062 (I.V.A.) y después 11060
    "SWISS": {"codigo": "11060 / 11062", "codigos": ["11062", "11060"],
              "nombre": "11060 - SWISS MEDICAL S.A. · 11062 - SWISS MEDICAL S.A. (I.V.A.)"},
}


def codigos_evweb(os_key):
    """Códigos de obra social que el bot debe extraer, en orden."""
    return OBRAS[os_key].get("codigos") or [OBRAS[os_key]["codigo"]]

ASSETS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
SEED = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seed")


# ───────────────────────── helpers ─────────────────────────

def norm(texto):
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return ""
    t = str(texto).strip().lower()
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return " ".join(t.replace("...", "").replace(",", " ").replace(".", " ").split())


def limpiar_id(val):
    """ID a string entero limpio (maneja float, .0, notación científica, apóstrofe)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip().lstrip("'\"").strip()
    if not s or s.lower() == "nan":
        return ""
    if s.endswith(".0"):
        s = s[:-2]
    try:
        return str(int(float(s)))
    except Exception:
        return s


def txt(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "nat", "none"):
        return ""
    if re.fullmatch(r"-?\d+\.0", s):
        s = s[:-2]
    return s


def num(val, default=0.0):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("$", "").replace(" ", "")
    if not s:
        return default
    if "," in s:  # formato 45.956,30
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return default


def fecha_ddmmaaaa(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if isinstance(val, (datetime, date)):
        return val.strftime("%d/%m/%Y")
    s = str(val).strip()
    if not s:
        return ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
    return s


def validar_periodo(p):
    p = (p or "").strip().replace("/", "").replace("-", "")
    if not re.fullmatch(r"(0[1-9]|1[0-2])\d{4}", p):
        raise ValueError("El período debe tener formato MMAAAA (ej: 112026).")
    return p


def leer_tabla(contenido: bytes, nombre: str, claves=None, hoja=None) -> pd.DataFrame:
    """Lee xlsx / xls / csv como texto. Si se pasan `claves`, busca la fila de
    encabezado (la primera que contenga alguna de esas columnas)."""
    nombre = (nombre or "").lower()
    if nombre.endswith(".csv") or nombre.endswith(".txt"):
        for enc in ("utf-8-sig", "latin-1"):
            try:
                texto = contenido.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        sep = ";" if texto.split("\n", 1)[0].count(";") >= texto.split("\n", 1)[0].count(",") else ","
        df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, keep_default_na=False)
    else:
        # Muchos ".xls" de los portales son en realidad xlsx (zip)
        engine = "openpyxl" if contenido[:2] == b"PK" else "xlrd"
        crudo = pd.read_excel(io.BytesIO(contenido), header=None, dtype=str,
                              engine=engine, sheet_name=hoja or 0)
        fila_h = 0
        if claves:
            cl = [norm(c) for c in claves]
            for i in range(min(len(crudo), 40)):
                vals = [norm(v) for v in crudo.iloc[i].tolist()]
                if any(c in vals for c in cl):
                    fila_h = i
                    break
        cols = [txt(v) or f"col{j}" for j, v in enumerate(crudo.iloc[fila_h].tolist())]
        df = crudo.iloc[fila_h + 1:].copy()
        df.columns = cols
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all").reset_index(drop=True)
    return df


def col(df, *candidatos, parcial=True):
    """Devuelve el nombre real de la primera columna que coincida."""
    normas = {norm(c): c for c in df.columns}
    for c in candidatos:
        if norm(c) in normas:
            return normas[norm(c)]
    if parcial:
        for c in candidatos:
            for n, real in normas.items():
                if norm(c) and norm(c) in n:
                    return real
    return None


def df_a_xlsx(df: pd.DataFrame, hoja="Datos") -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=hoja[:31])
        sin_formulas(w.sheets[hoja[:31]])
    return out.getvalue()


def sin_formulas(ws):
    """Los datos vienen de archivos externos: un texto que empieza con '=' no debe
    quedar como fórmula ejecutable en el Excel que se descarga."""
    for fila in ws.iter_rows():
        for c in fila:
            if c.data_type == "f":
                c.data_type = "s"


# ───────────────────────── padrón ─────────────────────────

def codigo_iva(resp_fiscal):
    """Código de IVA del profesional: 1 = calcula IVA (Responsable Inscripto), 0 = no calcula IVA."""
    return 1 if norm(resp_fiscal) == "responsable inscripto" else 0


def importar_padron(os_key, contenido, nombre, reemplazar=True):
    return importar_padron_df(os_key, leer_tabla(contenido, nombre, claves=["Profesional", "Nombre", "CUIT"]), reemplazar)


def importar_padron_df(os_key, df, reemplazar=True):
    c_nombre = col(df, "Profesional", "Nombre")
    if not c_nombre:
        raise ValueError("No se encontró la columna Profesional/Nombre en el padrón.")
    c_cuenta = col(df, "Cuenta", "Etiquetas de fila", parcial=False)
    c_mp = col(df, "Matricula", "MP", parcial=False)
    # En la base de GALENO la columna 'Matricula' trae la cuenta (C123) y no hay MP
    if not c_cuenta and c_mp:
        muestra = [txt(v) for v in df[c_mp].head(20)]
        if sum(1 for v in muestra if re.match(r"^[A-Za-z]", v)) > len(muestra) / 2:
            c_cuenta, c_mp = c_mp, None
    c_cuit = col(df, "CUIT")
    c_esp = col(df, "Especialidad")
    c_cat = col(df, "Categoria", "Arancel")
    c_rf = col(df, "Responsabilidad fiscal")
    c_ef = col(df, "Efector", parcial=False)
    filas = []
    for _, r in df.iterrows():
        nom = txt(r[c_nombre])
        if not nom:
            continue
        filas.append((
            os_key,
            txt(r[c_cuenta]) if c_cuenta else "",
            nom,
            re.sub(r"\D", "", limpiar_id(r[c_cuit])) if c_cuit else "",      # el CUIT se guarda sin guiones
            txt(r[c_esp]) if c_esp else "",
            txt(r[c_cat]) if c_cat else "",
            txt(r[c_rf]) if c_rf else "",
            limpiar_id(r[c_mp]) if c_mp else "",
            norm(nom),
            limpiar_id(r[c_ef]) if c_ef else "",
            codigo_iva(r[c_rf]) if c_rf else 0,      # siempre sale de la responsabilidad fiscal
        ))
    if not filas:
        raise ValueError("El padrón no trae ningún profesional.")
    with db.tx() as c:
        if reemplazar:
            c.execute("DELETE FROM profesionales WHERE os=?", (os_key,))
        c.executemany(
            "INSERT INTO profesionales(os,cuenta,nombre,cuit,especialidad,categoria,resp_fiscal,matricula,nombre_norm,"
            "efector,codigo_iva) VALUES (?,?,?,?,?,?,?,?,?,?,?)", filas)
    return len(filas)


def sembrar_padron():
    """Primera ejecución: carga los padrones incluidos en /seed."""
    for os_key in OBRAS:
        if db.scalar("SELECT COUNT(*) FROM profesionales WHERE os=?", (os_key,)):
            continue
        ruta = os.path.join(SEED, f"padron_{os_key}.xlsx")
        if os.path.exists(ruta):
            with open(ruta, "rb") as f:
                importar_padron(os_key, f.read(), ruta)


class Padron:
    """Índices en memoria del padrón de una obra social."""

    def __init__(self, os_key):
        self.filas = db.q("SELECT * FROM profesionales WHERE os=?", (os_key,))
        self.por_nombre, self.por_cuenta, self.por_mp, self.por_cuit = {}, {}, {}, {}
        for f in self.filas:
            self.por_nombre.setdefault(f["nombre_norm"], f)
            if f["cuenta"]:
                self.por_cuenta.setdefault(f["cuenta"].upper(), f)
            if f["matricula"]:
                self.por_mp.setdefault(f["matricula"], f)
            if f["cuit"]:
                self.por_cuit.setdefault(f["cuit"], f)
        self._tokens = [(set(f["nombre_norm"].split()), f) for f in self.filas]
        self._cache = {}
        # MP de otras obras sociales (la base de GALENO no trae matrícula provincial)
        self.mp_global = {}
        for f in db.q("SELECT cuit, matricula FROM profesionales WHERE matricula<>'' AND cuit<>''"):
            self.mp_global.setdefault(f["cuit"], f["matricula"])

    def mp(self, fila):
        if not fila:
            return ""
        return fila["matricula"] or self.mp_global.get(fila["cuit"], "")

    def buscar_nombre(self, nombre):
        """exacto → uno contiene al otro → tokens (igual que el bot de Galeno)."""
        n = norm(nombre)
        if not n or n == "revisar":
            return None
        if n in self._cache:
            return self._cache[n]
        r = self.por_nombre.get(n)
        if r is None:
            for f in self.filas:
                nu = f["nombre_norm"]
                if nu and (n in nu or nu in n):
                    r = f
                    break
        if r is None:
            tk = set(n.split())
            for tu, f in self._tokens:
                m = min(len(tk), len(tu))
                if m >= 2 and len(tk & tu) >= m:
                    r = f
                    break
        self._cache[n] = r
        return r


# ───────────────────────── valores (grillas) ─────────────────────────
# La extracción y normalización vive en grillas.py

def importar_grilla(os_key, periodo, contenido, nombre):
    if os_key == "SWISS" and smg.es_base(contenido):     # base con solapas Nomenclador, unidades y Valor Fijos
        return smg.importar_base(os_key, contenido, nombre)
    return grillas.importar(os_key, validar_periodo(periodo), contenido, nombre)


Grilla = grillas.Grilla


# ───────────────────────── Otros: valores cargados a mano ─────────────────────────

def _ar(n):
    """Importe con formato argentino: 1.234,56"""
    return f"{n:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def _clave_cod(cod):
    c = re.sub(r"[.\s/-]", "", str(cod or "")).upper()
    return c.lstrip("0") or c


def valor_otros(os_key, cod, periodo, categoria=""):
    """Valor de la solapa «Otros» para un código: la vigencia más reciente que no supere el período.
    Categoría R usa «valor R» si está cargado. Devuelve (valor, vigencia) o (None, '')."""
    k = _clave_cod(cod)
    if not k:
        return None, ""
    filas = [f for f in db.q("SELECT * FROM otros_valores WHERE os=?", (os_key,)) if _clave_cod(f["codigo"]) == k]
    clave = lambda p: (p[2:], p[:2])  # noqa: E731
    vigentes = sorted((f for f in filas if not periodo or clave(f["vigencia"]) <= clave(periodo)),
                      key=lambda f: clave(f["vigencia"]), reverse=True)
    for f in vigentes:
        v = f["valor_r"] if (str(categoria or "").strip().upper() == "R" and f["valor_r"]) else f["valor"]
        if v:
            return v, f["vigencia"]
    return None, ""


def guardar_otro(os_key, d, oid=None):
    cod = txt(d.get("codigo"))
    if not cod:
        raise ValueError("El código es obligatorio.")
    vig = validar_periodo(txt(d.get("vigencia")))

    def monto(v):
        if v in (None, ""):
            return None
        n = num(v)
        if n < 0:
            raise ValueError("El valor no puede ser negativo.")
        return round(n, 2) or None
    vals = (cod, txt(d.get("descripcion"))[:300], vig, monto(d.get("valor")), monto(d.get("valor_r")))
    otro = db.q1("SELECT id FROM otros_valores WHERE os=? AND codigo=? AND vigencia=? AND id<>?", (os_key, cod, vig, oid or 0))
    if otro:
        raise ValueError(f"Ya hay un valor cargado para el código {cod} con vigencia {vig}.")
    with db.tx() as c:
        if oid:
            c.execute("UPDATE otros_valores SET codigo=?, descripcion=?, vigencia=?, valor=?, valor_r=? WHERE id=? AND os=?",
                      vals + (oid, os_key))
        else:
            oid = c.execute("INSERT INTO otros_valores(codigo,descripcion,vigencia,valor,valor_r,os) VALUES (?,?,?,?,?,?)",
                            vals + (os_key,)).lastrowid
    return db.q1("SELECT * FROM otros_valores WHERE id=?", (oid,))


def importar_otros(os_key, contenido, nombre):
    """Excel con columnas Código, Descripción, Vigencia (MMAAAA), Valor y Valor R. Actualiza o agrega por código + vigencia."""
    df = leer_tabla(contenido, nombre, claves=["Código", "Codigo", "Vigencia"])
    c_cod, c_desc, c_vig = col(df, "Código", "Codigo"), col(df, "Descripción", "Descripcion", "Prestación"), col(df, "Vigencia")
    c_r = col(df, "Valor R", "Valor recertificado", parcial=False)
    c_val = col(df, "Valor", "Valor todas las categorías", parcial=False) or next(
        (c for c in df.columns if norm(c).startswith("valor") and c != c_r), None)
    if not c_cod or not c_vig or not c_val:
        raise ValueError("El archivo debe tener las columnas Código, Vigencia y Valor.")
    nuevos = actualizados = 0
    for _, r in df.iterrows():
        cod = limpiar_id(r[c_cod])
        if not cod:
            continue
        d = dict(codigo=cod, descripcion=txt(r[c_desc]) if c_desc else "", vigencia=limpiar_id(r[c_vig]).zfill(6),
                 valor=r[c_val], valor_r=r[c_r] if c_r else None)
        ya = db.q1("SELECT id FROM otros_valores WHERE os=? AND codigo=? AND vigencia=?", (os_key, cod, d["vigencia"]))
        guardar_otro(os_key, d, ya["id"] if ya else None)
        nuevos, actualizados = nuevos + (not ya), actualizados + bool(ya)
    return {"nuevos": nuevos, "actualizados": actualizados}


# ───────────────────────── EVWEB ─────────────────────────

def detectar_col_autorizacion(df):
    prioridades = ["nroautorizacion", "nro autorizacion", "nro_autorizacion", "autorizacion", "autoriz",
                   "transaccion", "transac", "nroaut", "numero autorizacion", "nro", "numero", "id"]
    cols = {norm(c): c for c in df.columns}
    for p in prioridades:
        if p in cols:
            return cols[p]
    for p in prioridades:
        for n, o in cols.items():
            if p in n:
                return o
    return df.columns[0]


def detectar_col_profesional(df):
    prioridades = ["prescriptor", "efector", "profesional", "medico", "nombre profesional", "nombre medico",
                   "nombre", "apellido"]
    cols = {norm(c): c for c in df.columns}
    for p in prioridades:
        if p in cols:
            return cols[p]
    for p in prioridades:
        for n, o in cols.items():
            if p in n:
                return o
    return df.columns[1] if len(df.columns) > 1 else df.columns[0]


def fecha_iso(val):
    """dd/mm/aaaa (o lo que venga) → AAAA-MM-DD; '' si no es una fecha."""
    t = fecha_ddmmaaaa(val)
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", t)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def detectar_col_fecha(columnas):
    """Columna con la fecha de la prestación en el Excel de EVWEB."""
    cand = [c for c in columnas if "fecha" in norm(c)]
    for clave in ("prest", "realiz", "atenc", "practica", "carga"):
        for c in cand:
            if clave in norm(c):
                return c
    return cand[0] if cand else None


def guardar_evweb(os_key, dfs, origen, desde="", hasta=""):
    """Guarda filas extraídas de EVWEB (solo consulta). Deduplica filas idénticas."""
    dfs = [d for d in dfs if d is not None and len(d)]
    if not dfs:
        return {"filas": 0, "nuevas": 0}
    df = pd.concat(dfs, ignore_index=True)
    df.columns = [str(c).strip() for c in df.columns]
    c_aut = detectar_col_autorizacion(df)
    c_prof = detectar_col_profesional(df)
    c_cta = next((c for c in df.columns if any(k in norm(c) for k in ("cuenta", "cta"))), None)
    c_fec = detectar_col_fecha(df.columns)
    padron = Padron(os_key)
    nuevas = 0
    with db.tx() as c:
        cur = c.execute(
            "INSERT INTO evweb_extracciones(os,origen,desde,hasta,fecha,filas,nuevas) VALUES (?,?,?,?,?,?,0)",
            (os_key, origen, desde, hasta, datetime.now().strftime("%d/%m/%Y %H:%M"), len(df)))
        eid = cur.lastrowid
        for _, r in df.iterrows():
            data = {k: (fecha_ddmmaaaa(v) if isinstance(v, (datetime, date)) else txt(v)) for k, v in r.items()}
            js = json.dumps(data, ensure_ascii=False)
            h = hashlib.sha1(js.encode()).hexdigest()
            prof = txt(r[c_prof])
            cuenta = txt(r[c_cta]) if c_cta else ""
            if not cuenta:               # la cuenta sale del padrón, por el nombre del profesional
                fila = padron.buscar_nombre(prof)
                cuenta = fila["cuenta"] if fila else ""
            cur = c.execute(
                "INSERT OR IGNORE INTO evweb_filas(extraccion_id,os,nro,profesional,cuenta,data,hash,fecha) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (eid, os_key, limpiar_id(r[c_aut]), prof, cuenta, js, h, fecha_iso(r[c_fec]) if c_fec else ""))
            nuevas += cur.rowcount
        c.execute("UPDATE evweb_extracciones SET nuevas=? WHERE id=?", (nuevas, eid))
    return {"filas": len(df), "nuevas": nuevas, "col_autorizacion": c_aut, "col_profesional": c_prof,
            "col_fecha": c_fec}


def completar_fechas_evweb():
    """Filas guardadas antes de tener la columna fecha: se completa desde los datos."""
    pend = db.q("SELECT id, data FROM evweb_filas WHERE fecha IS NULL LIMIT 200000")
    if not pend:
        return
    col = None
    with db.tx() as c:
        for f in pend:
            data = json.loads(f["data"])
            col = col if col in data else detectar_col_fecha(data.keys())
            c.execute("UPDATE evweb_filas SET fecha=? WHERE id=?", (fecha_iso(data.get(col)) if col else "", f["id"]))


def filtro_profesional(prof, campo_cuenta="cuenta", campo_nombre="profesional"):
    """'C123 - APELLIDO, Nombre' → condición SQL y parámetros."""
    prof = (prof or "").strip()
    if not prof:
        return "", []
    if " - " in prof:
        cta, nom = [x.strip() for x in prof.split(" - ", 1)]
        if cta and cta != "(sin cuenta)":
            return f" AND {campo_cuenta}=?", [cta]
        return f" AND {campo_nombre}=?", [nom]
    return f" AND ({campo_cuenta} LIKE ? OR {campo_nombre} LIKE ?)", [f"%{prof}%", f"%{prof}%"]


def opciones_profesional(tabla, os_key, extra="", params=()):
    filas = db.q(f"SELECT DISTINCT cuenta, profesional FROM {tabla} WHERE os=? {extra} AND profesional<>'' "
                 f"ORDER BY profesional LIMIT 3000", (os_key, *params))
    return [f"{f['cuenta'] or '(sin cuenta)'} - {f['profesional']}" for f in filas]


def evweb_filas(os_key, busqueda="", desde="", hasta="", prof="", nro="", limite=0, inicio=0, contar=False):
    """Filas extraídas de EVWEB. Con `contar` devuelve (filas de la página, total): si no hay texto libre,
    la base de datos cuenta y pagina, sin leer todas las filas."""
    sql, par = " FROM evweb_filas WHERE os=?", [os_key]
    if desde:
        sql += " AND fecha>=?"
        par.append(desde)
    if hasta:
        sql += " AND fecha<=? AND fecha<>''"
        par.append(hasta)
    if nro.strip():
        sql += " AND nro LIKE ?"
        par.append(f"%{limpiar_id(nro)}%")
    cond, p2 = filtro_profesional(prof)
    sql, par = sql + cond, par + p2
    orden = " ORDER BY fecha DESC, id DESC"
    if contar and not busqueda and limite > 0:
        total = db.scalar("SELECT COUNT(*)" + sql, par)
        return [json.loads(f["data"]) for f in db.q("SELECT data" + sql + orden + " LIMIT ? OFFSET ?",
                                                    par + [limite, max(0, inicio)])], total
    regs = [json.loads(f["data"]) for f in db.q("SELECT data" + sql + orden, par)]
    if busqueda:
        b = norm(busqueda)
        regs = [r for r in regs if b in norm(" ".join(r.values()))]
    if contar:
        return (regs[inicio:inicio + limite] if limite > 0 else regs), len(regs)
    return regs


def evweb_df(os_key, busqueda="", desde="", hasta="", prof="", nro=""):
    return pd.DataFrame(evweb_filas(os_key, busqueda, desde, hasta, prof, nro))


# ───────────────────────── archivo validado → líneas ─────────────────────────

def _parse_galeno(df):
    c_id = col(df, "Id Transacción", "Id Transaccion")
    if not c_id:
        raise ValueError("El archivo de GALENO no tiene la columna 'Id Transacción'.")
    c_anul = col(df, "Anulada", parcial=False)
    out, anuladas = [], 0
    for _, r in df.iterrows():
        if not limpiar_id(r[c_id]):
            continue
        if c_anul and txt(r[c_anul]).upper() == "S":
            anuladas += 1
            continue
        out.append(dict(
            claves=[limpiar_id(r[c_id])],
            fecha=fecha_ddmmaaaa(r.get(col(df, "Fecha Transacción"))),
            afiliado_numero=txt(r.get(col(df, "Credencial Socio"))),
            afiliado_nombre=txt(r.get(col(df, "Apellido y Nombre Socio"))),
            cod=txt(r.get(col(df, "Practi. Presta"))),
            desc=txt(r.get(col(df, "Descripción Práctica"))),
            cant=num(r.get(col(df, "Cant. Tratamientos")), 1) or 1,
            importe=None, prof_nombre="", prof_mp="",
            copago=num(r.get(col(df, "Copago", "Coseguro"))),
        ))
    return out, anuladas


def _parse_sancor(df):
    c_id = col(df, "NRO ORDEN")
    if not c_id:
        raise ValueError("El archivo de SANCOR no tiene la columna 'NRO ORDEN'.")
    out = []
    for _, r in df.iterrows():
        if not limpiar_id(r[c_id]):
            continue  # fila TOTAL
        cant = num(r.get(col(df, "CANT.", "CANT")), 1) or 1
        out.append(dict(
            claves=[limpiar_id(r[c_id])],
            fecha=fecha_ddmmaaaa(r.get(col(df, "FECHA ORDEN"))),
            afiliado_numero=txt(r.get(col(df, "NRO AFILIADO ORIGEN", "NRO AFILIADO"))),
            afiliado_nombre=txt(r.get(col(df, "APELLIDO Y NOMBRE"))),
            cod=txt(r.get(col(df, "CÓDIGO", "CODIGO", parcial=False))),
            desc=txt(r.get(col(df, "DESCRIPCIÓN", "DESCRIPCION", parcial=False))),
            cant=cant, importe=num(r.get(col(df, "IMPORTE")), 0),
            prof_nombre=txt(r.get(col(df, "DESC. PRESTADOR EFECTOR"))),
            prof_mp=limpiar_id(r.get(col(df, "MAT. PRESTADOR EFECTOR"))),
        ))
    return out, 0


def _parse_avalian(df):
    c_id = col(df, "tranxml_id")
    if not c_id:
        raise ValueError("El archivo de AVALIAN no tiene la columna 'tranxml_id'.")
    out = []
    for _, r in df.iterrows():
        if not limpiar_id(r[c_id]):
            continue
        out.append(dict(
            claves=[limpiar_id(r[c_id]), limpiar_id(r.get("id_autorizacion_previa"))],
            fecha=fecha_ddmmaaaa(r.get("fecha_operacion") or r.get("fecha")),
            afiliado_numero=txt(r.get("codigo_afiliado")),
            afiliado_nombre=(txt(r.get("apellido_afiliado")) + " " + txt(r.get("nombre_afiliado"))).strip(),
            cod=txt(r.get("nom_prestacion_pdh")),
            desc=txt(r.get("descripcion_prestacion")),
            cant=num(r.get("cantidad_prestacion"), 1) or 1,
            importe=num(r.get("valor_total"), 0),
            prof_nombre=txt(r.get("nombre_realizador")),
            prof_mp=limpiar_id(r.get("matri_realizador")),
        ))
    return out, 0


PARSERS = {
    "GALENO": (_parse_galeno, ["Id Transacción", "Id Transaccion"]),
    "SANCOR": (_parse_sancor, ["NRO ORDEN"]),
    "AVALIAN": (_parse_avalian, ["tranxml_id"]),
    "SWISS": (smg.parse_reporte, ["N° Transacción", "transacción_item", "Código de prestación"]),
}


def guardar_coseguros(os_key, filas, periodo=""):
    """Guarda el copago de cada transacción + práctica del archivo validado (se usa en Presentaciones)."""
    datos = [(os_key, f["claves"][0], f["cod"], f["copago"], periodo) for f in filas if "copago" in f]
    if not datos:
        return 0
    with db.tx() as c:
        c.executemany("INSERT INTO coseguros(os,nro,cod,copago,periodo) VALUES (?,?,?,?,?) "
                      "ON CONFLICT(os,nro,cod) DO UPDATE SET copago=excluded.copago, periodo=excluded.periodo", datos)
    return len(datos)


class ArchivoDuplicado(Exception):
    """El archivo trae transacciones que ya estaban cargadas: la importación se frena."""

    def __init__(self, mensaje, info):
        super().__init__(mensaje)
        self.info = info


def prefacturar(os_key, periodo, contenido, nombre, solo_nuevas=False, modo="evweb"):
    """Cruza el archivo validado con lo extraído de EVWEB por número de
    transacción, completa profesional desde el padrón y valoriza.

    Las líneas se acumulan con las que ya están en pre-facturación. Si el archivo trae
    transacciones ya cargadas, no se importa nada (salvo que se pida importar solo las nuevas)."""
    periodo = validar_periodo(periodo)
    # SWISS: cada transacción es una sola prestación y el código puede corregirse al valorizar,
    # así que la repetición se detecta por número de transacción.
    kd = (lambda n, c: (n, "")) if os_key == "SWISS" else (lambda n, c: (n, c))
    parser, claves = PARSERS[os_key]
    filas, anuladas = parser(leer_tabla(contenido, nombre, claves=claves))
    if not filas:
        raise ValueError("El archivo no tiene filas para procesar.")

    huella = hashlib.sha256(contenido).hexdigest()
    previa = db.q1("SELECT nombre, fecha FROM importaciones WHERE os=? AND hash=? ORDER BY id DESC", (os_key, huella))
    existentes = {}
    for r in db.q("SELECT nro_transaccion, cod_practica, estado FROM lineas WHERE os=?", (os_key,)):
        existentes[kd(r["nro_transaccion"], r["cod_practica"])] = r["estado"]
    repetidas = [f for f in filas if kd(f["claves"][0], f["cod"]) in existentes]
    if repetidas and not solo_nuevas:
        donde = {"prefact": "Pre-facturación", "facturacion": "Facturación", "template": "un template"}
        por_estado = {}
        for f in repetidas:
            e = donde[existentes[kd(f["claves"][0], f["cod"])]]
            por_estado[e] = por_estado.get(e, 0) + 1
        nuevas_n = len(filas) - len(repetidas)
        motivo = (f"Este archivo ya fue importado el {previa['fecha']}." if previa and not nuevas_n
                  else f"El archivo trae {len(repetidas)} transacción(es) que ya estaban cargadas.")
        raise ArchivoDuplicado(
            motivo + " No se importó nada.",
            {"duplicadas": len(repetidas), "nuevas": nuevas_n, "total": len(filas),
             "ya_importado": previa["fecha"] if previa else None, "donde": por_estado,
             "ejemplos": [f["claves"][0] for f in repetidas[:8]]})
    guardar_coseguros(os_key, filas, periodo)

    ev = {}
    for f in db.q("SELECT nro, profesional, cuenta FROM evweb_filas WHERE os=? AND nro<>''", (os_key,)):
        ev.setdefault(f["nro"], f)
    padron = Padron(os_key)
    grilla = Grilla(os_key, periodo)
    swiss = os_key == "SWISS"
    vz = smg.Valorizadores(os_key) if swiss else None
    cache_otros = {}
    por_grilla = swiss and modo == "grilla"       # SWISS: cruzar y valorizar según grilla, sin EVWEB
    ya = {kd(r["nro_transaccion"], r["cod_practica"]) for r in
          db.q("SELECT nro_transaccion, cod_practica FROM lineas WHERE os=?", (os_key,))}

    res = dict(total=len(filas), anuladas=anuladas, duplicadas=0, ok=0, sin_evweb=0, sin_padron=0,
               sin_valor=0, grilla_periodo=grilla.periodo)
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    nuevas, vistos = [], set()
    for f in filas:
        nro = f["claves"][0]
        k = kd(nro, f["cod"])
        if k in ya:
            res["duplicadas"] += 1
            continue
        # misma transacción+código repetida dentro del archivo: se conserva (puede ser cantidad real)
        vistos.add(k)
        e = None if por_grilla else next((ev[c] for c in f["claves"] if c and c in ev), None)
        prof, obs = None, []
        por_cuit = padron.por_cuit.get(f.get("prof_cuit", "")) if swiss and f.get("prof_cuit") else None
        if por_grilla:
            # Proceso del repositorio de SWISS: el profesional sale del CUIT del efector
            prof = por_cuit
            cruce = "GRILLA" if prof else "SIN PADRON"
            if not prof:
                obs.append(f"CUIT del efector {f.get('prof_cuit') or 'vacío'} no está en el padrón")
        elif e:
            if e["cuenta"]:
                prof = padron.por_cuenta.get(e["cuenta"].upper())
            prof = prof or padron.buscar_nombre(e["profesional"])
            cruce = "OK" if prof else "SIN PADRON"
            if not prof:
                obs.append(f"EVWEB: {e['profesional']} no está en el padrón")
        else:
            cruce = "SIN EVWEB"
            # ayuda: el archivo validado trae matrícula / nombre del efector
            prof = por_cuit or (padron.por_mp.get(f["prof_mp"]) if f["prof_mp"] else None)
            prof = prof or padron.buscar_nombre(f["prof_nombre"])
            obs.append("Transacción no encontrada en EVWEB"
                       + (" · profesional sugerido por el archivo validado" if prof else ""))
        res["ok" if cruce in ("OK", "GRILLA") else "sin_evweb" if cruce == "SIN EVWEB" else "sin_padron"] += 1

        cat = prof["categoria"] if prof else ""
        esp = prof["especialidad"] if prof else ""
        iva, os_codigo = None, None
        regla, per_valor = "", periodo
        # Código propuesto: el del archivo no se toca; se valoriza con el propuesto
        cod_val, desc_prop, motivo_cod = smg.codigo_propuesto(f["cod"], esp) if swiss else (f["cod"], "", "")
        if motivo_cod:
            obs.append(f"Código propuesto {cod_val}: {motivo_cod}")
        if swiss:
            # Valorización con las reglas del repositorio, sobre el mes de la transacción
            v, regla, per_valor, hay_base = vz.valor(f["fecha"], cod_val, cat, esp, periodo, desc_prop or f.get("desc", ""))
            iva, os_codigo = smg.iva_y_codigo(prof["resp_fiscal"] if prof else "", f.get("condicion_iva"))
            res["grilla_periodo"] = per_valor if hay_base else res.get("grilla_periodo")
            if not hay_base:
                obs.append(f"No hay grilla de valores cargada para {per_valor}")
        else:
            v = grilla.valor(f["cod"], cat)
        # «Otros» (valores cargados a mano) manda sobre la grilla: sirve para los códigos que la grilla
        # no trae y para corregir un valor de la grilla sin tocarla.
        ko = (_clave_cod(cod_val), per_valor if swiss else periodo, cat)
        if ko not in cache_otros:
            cache_otros[ko] = valor_otros(os_key, *ko)
        vo, vig = cache_otros[ko]
        if vo:
            if v and abs(v - vo) > 0.01:
                obs.append(f"Valor de «Otros» en lugar del de la grilla ({_ar(v)})")
            v, regla = vo, f"Otros (vigencia {vig})"
        # GALENO no informa importes: se valoriza con la grilla. SANCOR y AVALIAN
        # traen el importe validado por la obra social; la grilla queda de respaldo.
        v_arch = round(f["importe"] / f["cant"], 2) if f["importe"] else None
        if v and v_arch and abs(v - v_arch) > max(1, v_arch * 0.001):
            obs.append("El valor del archivo difiere del de la grilla")
        if f["importe"]:
            vu, origen = v_arch, "archivo validado"
        elif v:
            vu, origen = v, (f"Valores · {regla}" if regla.startswith("Otros") else
                             f"grilla {per_valor} · {regla}" if swiss else f"grilla {grilla.periodo}")
        else:
            vu, origen = 0.0, ""
            res["sin_valor"] += 1
            obs.append(("#REVISAR VALORES: " + (regla or "la prestación no está en la grilla")) if swiss else "Sin valor en grilla")
        nuevas.append((
            os_key, periodo, "prefact", nro, f["fecha"], f["afiliado_numero"], f["afiliado_nombre"],
            f["cod"], f["desc"], f["cant"],
            prof["cuenta"] if prof else "", padron.mp(prof) or (f["prof_mp"] if not prof else ""),
            prof["nombre"] if prof else (e["profesional"] if e else f["prof_nombre"]),
            prof["cuit"] if prof else "", esp, cat, vu, round(vu * f["cant"], 2), origen, cruce,
            " · ".join(obs), ahora, v_arch, v or None, iva, os_codigo,
            prof["resp_fiscal"] if prof else "", f.get("condicion_iva", ""), cod_val, desc_prop))
    with db.tx() as c:
        c.executemany(
            "INSERT INTO lineas(os,periodo,estado,nro_transaccion,fecha_prestacion,afiliado_numero,afiliado_nombre,"
            "cod_practica,descripcion,cantidad,cuenta,matricula,profesional,cuit,especialidad,categoria,valor_unit,"
            "total,origen_valor,cruce,observacion,creado,valor_archivo,valor_grilla,iva,os_codigo,resp_fiscal,cond_afiliado,"
            "cod_propuesto,desc_propuesta) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            nuevas)
        c.execute("INSERT INTO importaciones(os,hash,nombre,periodo,fecha,filas) VALUES (?,?,?,?,?,?)",
                  (os_key, huella, nombre, periodo, ahora, len(nuevas)))
    res["insertadas"] = len(nuevas)
    res["en_prefacturacion"] = db.scalar("SELECT COUNT(*) FROM lineas WHERE os=? AND estado='prefact'", (os_key,))
    return res


CAMPOS_EDITABLES = ["nro_transaccion", "fecha_prestacion", "afiliado_numero", "afiliado_nombre", "cod_practica",
                    "descripcion", "cantidad", "cuenta", "matricula", "profesional", "cuit", "especialidad",
                    "categoria", "valor_unit", "observacion", "periodo"]


def editar_linea(lid, cambios, autocompletar=False, ctx=None):
    """`ctx` es un diccionario que comparte padrón, grillas y valorizador entre muchas ediciones
    seguidas (edición masiva), para no volver a cargarlos en cada línea."""
    ctx = {} if ctx is None else ctx
    lin = db.q1("SELECT * FROM lineas WHERE id=?", (lid,))
    if not lin:
        raise ValueError("Línea inexistente.")
    if lin["estado"] == "template":
        raise ValueError("La línea ya está en un template; anulá el template para modificarla.")
    nuevo = dict(lin)
    for k in CAMPOS_EDITABLES:
        if k in cambios and cambios[k] is not None:
            nuevo[k] = num(cambios[k]) if k in ("cantidad", "valor_unit") else str(cambios[k]).strip()
    if "periodo" in cambios:
        nuevo["periodo"] = validar_periodo(nuevo["periodo"])
    incremento = num(cambios.get("incremento")) if cambios.get("incremento") not in (None, "") else 0
    if incremento and not (-100 < incremento <= 500):
        raise ValueError("El incremento debe ser un porcentaje entre -100 y 500.")
    if autocompletar:
        padron = ctx.get("padron") or ctx.setdefault("padron", Padron(lin["os"]))
        prof = None
        if nuevo["cuenta"] and nuevo["cuenta"] != lin["cuenta"]:
            prof = padron.por_cuenta.get(nuevo["cuenta"].upper())
        elif nuevo["matricula"] and nuevo["matricula"] != lin["matricula"]:
            prof = padron.por_mp.get(nuevo["matricula"])
        elif nuevo["cuenta"]:
            prof = padron.por_cuenta.get(nuevo["cuenta"].upper())
        if prof:
            nuevo.update(cuenta=prof["cuenta"], matricula=padron.mp(prof) or nuevo["matricula"],
                         profesional=prof["nombre"], cuit=prof["cuit"],
                         especialidad=prof["especialidad"], categoria=prof["categoria"],
                         resp_fiscal=prof["resp_fiscal"])
        elif nuevo["cuenta"] != lin["cuenta"] or nuevo["matricula"] != lin["matricula"]:
            raise ValueError("La cuenta / matrícula indicada no existe en el padrón de esta obra social.")
        cambio_cod = nuevo["cod_practica"] != lin["cod_practica"] or nuevo["categoria"] != lin["categoria"] \
            or nuevo["periodo"] != lin["periodo"]
        cambio_esp = lin["os"] == "SWISS" and nuevo["especialidad"] != lin["especialidad"]
        if nuevo["cod_practica"] != lin["cod_practica"] or cambio_esp or not lin.get("cod_propuesto"):
            # el código propuesto sigue al código de la línea y a la especialidad
            if lin["os"] == "SWISS":
                nuevo["cod_propuesto"], nuevo["desc_propuesta"], _ = smg.codigo_propuesto(nuevo["cod_practica"], nuevo["especialidad"])
            else:
                nuevo["cod_propuesto"], nuevo["desc_propuesta"] = nuevo["cod_practica"], ""
        cod_val = nuevo.get("cod_propuesto") or nuevo["cod_practica"]
        if cambio_cod or lin.get("valor_grilla") is None or cambio_esp:
            kg = ("grilla", nuevo["periodo"])
            g = ctx.get(kg) or ctx.setdefault(kg, Grilla(lin["os"], nuevo["periodo"]))
            if lin["os"] == "SWISS":
                v = (ctx.get("vz") or ctx.setdefault("vz", smg.Valorizadores("SWISS"))).valor(nuevo["fecha_prestacion"], cod_val, nuevo["categoria"],
                                                     nuevo["especialidad"], nuevo["periodo"],
                                                     nuevo.get("desc_propuesta") or nuevo.get("descripcion") or "")[0]
            else:
                v = g.valor(cod_val, nuevo["categoria"])
            v = valor_otros(lin["os"], cod_val, nuevo["periodo"], nuevo["categoria"])[0] or v
            nuevo["valor_grilla"] = v or None            # la columna Valor grilla sigue al código y la categoría
            if v and "valor_unit" not in cambios and (cambio_cod or not lin["valor_unit"]):
                nuevo["valor_unit"], nuevo["origen_valor"] = v, f"grilla {g.periodo}"
    if "valor_unit" in cambios and num(cambios["valor_unit"]) != lin["valor_unit"]:
        nuevo["origen_valor"] = "manual"
    if incremento:      # incremento (o descuento) porcentual sobre el valor unitario de esta línea
        base = nuevo["valor_unit"] or 0
        if not base:
            raise ValueError("La línea no tiene valor unitario: no se le puede aplicar un incremento.")
        nuevo["valor_unit"] = round(base * (1 + incremento / 100), 2)
        marca = f"{incremento:+g} % sobre {_ar(base)}"
        nuevo["origen_valor"] = ((nuevo["origen_valor"] or "manual").split(" · incremento")[0] + f" · incremento {incremento:+g} %")[:200]
        nuevo["observacion"] = " · ".join(x for x in (nuevo.get("observacion") or "", f"Incremento {marca}") if x)
    nuevo["total"] = round(nuevo["valor_unit"] * (nuevo["cantidad"] or 1), 2)
    if nuevo["cuenta"] and nuevo["profesional"] and lin["cruce"] != "OK":
        nuevo["cruce"] = "MANUAL"
    campos = CAMPOS_EDITABLES + ["total", "origen_valor", "cruce", "valor_grilla", "resp_fiscal", "cod_propuesto", "desc_propuesta"]
    with db.tx() as c:
        c.execute(f"UPDATE lineas SET {','.join(k + '=?' for k in campos)} WHERE id=?",
                  [nuevo[k] for k in campos] + [lid])
    final = db.q1("SELECT * FROM lineas WHERE id=?", (lid,))
    final["_cambios"] = {k: {"antes": lin[k], "despues": final[k]} for k in campos if lin[k] != final[k]}
    if incremento:
        final["_cambios"]["incremento_porcentual"] = incremento
    return final


def completar_valores_lineas():
    """Líneas cargadas antes de guardar por separado el valor del archivo y el de la grilla:
    se reconstruyen para que al procesar se pueda elegir la fuente."""
    with db.tx() as c:
        c.execute("UPDATE lineas SET valor_archivo=valor_unit WHERE valor_archivo IS NULL AND valor_unit>0 "
                  "AND origen_valor='archivo validado'")
        c.execute("UPDATE lineas SET valor_grilla=valor_unit WHERE valor_grilla IS NULL AND valor_unit>0 "
                  "AND origen_valor LIKE 'grilla%'")
    pend = db.q("SELECT id, os, periodo, cod_practica, categoria FROM lineas WHERE valor_grilla IS NULL "
                "AND estado IN ('prefact','facturacion')")
    grillas, cambios = {}, []
    for l in pend:
        if l["os"] == "SWISS":
            continue          # sus valores salen de reglas propias al pre-facturar o al modificar la línea
        k = (l["os"], l["periodo"])
        if k not in grillas:
            grillas[k] = Grilla(*k)
        v = grillas[k].valor(l["cod_practica"], l["categoria"])
        if v:
            cambios.append((v, l["id"]))
    if cambios:
        with db.tx() as c:
            c.executemany("UPDATE lineas SET valor_grilla=? WHERE id=?", cambios)
    return len(cambios)


class Revalorizador:
    """Vuelve a valorizar líneas con lo que está cargado ahora: categoría y especialidad del padrón,
    grilla de valores y «Otros». Se usa después de corregir el padrón o los valores."""

    def __init__(self, os_key):
        self.os, self.padron, self.grillas = os_key, Padron(os_key), {}
        self.vz = smg.Valorizadores(os_key) if os_key == "SWISS" else None

    def linea(self, lin):
        """Devuelve (línea nueva, cambios) o (None, motivo) si no se pudo valorizar."""
        nuevo = dict(lin)
        prof = (self.padron.por_cuit.get(re.sub(r"\D", "", lin["cuit"] or "")) if lin["cuit"] else None) \
            or (self.padron.por_cuenta.get((lin["cuenta"] or "").upper()) if lin["cuenta"] else None)
        if prof:
            nuevo.update(especialidad=prof["especialidad"], categoria=prof["categoria"], resp_fiscal=prof["resp_fiscal"])
        if self.vz:
            nuevo["cod_propuesto"], nuevo["desc_propuesta"], _ = smg.codigo_propuesto(lin["cod_practica"], nuevo["especialidad"])
            cod = nuevo["cod_propuesto"]
            v, regla, per, _ = self.vz.valor(lin["fecha_prestacion"], cod, nuevo["categoria"], nuevo["especialidad"],
                                             lin["periodo"], nuevo["desc_propuesta"] or lin["descripcion"] or "")
            origen = f"grilla {per} · {regla}"
        else:
            cod, per = lin.get("cod_propuesto") or lin["cod_practica"], lin["periodo"]
            if lin["periodo"] not in self.grillas:
                self.grillas[lin["periodo"]] = Grilla(self.os, lin["periodo"])
            g = self.grillas[lin["periodo"]]
            v, origen = g.valor(cod, nuevo["categoria"]), f"grilla {g.periodo}"
        vo, vig = valor_otros(self.os, cod, per, nuevo["categoria"])
        if vo:
            v, origen = vo, f"Valores · Otros (vigencia {vig})"
        if not v:
            return None, "sin valor en la grilla ni en Otros"
        nuevo.update(valor_unit=v, valor_grilla=v, origen_valor=origen, total=round(v * (lin["cantidad"] or 1), 2))
        campos = ("especialidad", "categoria", "resp_fiscal", "cod_propuesto", "desc_propuesta", "valor_unit",
                  "valor_grilla", "origen_valor", "total")
        return nuevo, {k: {"antes": lin[k], "despues": nuevo[k]} for k in campos if lin[k] != nuevo[k]}


def codigos_difieren(lin):
    """True si el código propuesto es distinto del que trae el archivo validado."""
    p = lin.get("cod_propuesto")
    return bool(p) and _clave_cod(p) != _clave_cod(lin.get("cod_practica"))


def aplicar_codigo(lin, codigo):
    """Al procesar se elige qué código queda: el del archivo o el propuesto. Devuelve (línea, cambió)."""
    if codigo != "propuesto" or not codigos_difieren(lin):
        return lin, False
    nuevo = dict(lin)
    nuevo["cod_practica"] = lin["cod_propuesto"]
    if lin.get("desc_propuesta"):
        nuevo["descripcion"] = lin["desc_propuesta"]
    return nuevo, True


def aplicar_fuente(lin, fuente):
    """Al procesar se elige qué valor queda: el del archivo validado o el de la grilla.
    Devuelve la línea con el valor elegido; si esa fuente no tiene valor para la línea, o el valor
    fue cargado a mano, la deja como está."""
    v = lin.get("valor_archivo") if fuente == "archivo" else lin.get("valor_grilla") if fuente == "grilla" else None
    if not v or v <= 0 or lin.get("origen_valor") == "manual":
        return lin, False
    nuevo = dict(lin)
    nuevo["valor_unit"] = v
    nuevo["total"] = round(v * (lin["cantidad"] or 1), 2)
    nuevo["origen_valor"] = "archivo validado" if fuente == "archivo" else "grilla"
    return nuevo, True


def reiniciar_prefacturacion(os_key):
    """Borra todas las líneas que están en pre-facturación de una obra social, para empezar de nuevo.
    No toca lo que ya está en Facturación ni en templates."""
    with db.tx() as c:
        info = dict(c.execute("SELECT COUNT(*) n, COALESCE(SUM(total),0) total FROM lineas WHERE os=? AND estado='prefact'",
                              (os_key,)).fetchone())
        c.execute("DELETE FROM lineas WHERE os=? AND estado='prefact'", (os_key,))
        # los archivos se pueden volver a importar
        c.execute("DELETE FROM importaciones WHERE os=?", (os_key,))
    return {"lineas": info["n"], "importe": round(info["total"], 2)}


def quitar_evweb(os_key):
    """Borra todo lo extraído de EVWEB para una obra social."""
    with db.tx() as c:
        n = c.execute("DELETE FROM evweb_filas WHERE os=?", (os_key,)).rowcount
        c.execute("DELETE FROM evweb_extracciones WHERE os=?", (os_key,))
    return {"filas": n}


def validar_para_procesar(lin):
    faltan = [n for n, k in (("cuenta", "cuenta"), ("profesional", "profesional"),
                             ("código de prestación", "cod_practica")) if not lin[k]]
    if not lin["valor_unit"] or lin["valor_unit"] <= 0:
        faltan.append("valor")
    return faltan


# ───────────────────────── templates ─────────────────────────

# Template de importación EVWEB: hoja 'ImportacionesEvweb', 22 columnas (igual al de SEROS).
COLS_TEMPLATE = ["matricula", "afiliado_numero", "afiliado_denominacion", "fecha_prestacion", "cod_practica",
                 "cantidad", "actuacion", "tipo_facturacion", "honorario", "1er_ayudante", "2do_ayudante", "gasto",
                 "modulo", "aparatologia", "id_anticipo", "iva", "numaut", "cuit", "fecha_presentacion",
                 "Coseguro", "ModalidadCoseguro", "nroAutorizacion"]


def fecha_presentacion(hoy=None):
    """Último día del mes anterior a la fecha de procesamiento."""
    hoy = hoy or date.today()
    y, m = (hoy.year, hoy.month - 1) if hoy.month > 1 else (hoy.year - 1, 12)
    return datetime(y, m, calendar.monthrange(y, m)[1])


def _fila_template(l, fpres):
    try:
        fp = datetime.strptime(l["fecha_prestacion"], "%d/%m/%Y")
    except Exception:
        fp = l["fecha_prestacion"]
    cod = l["cod_practica"] or ""
    cod = int(cod) if cod.isdigit() and not cod.startswith("0") else cod
    cant = l["cantidad"] or 1
    return [l["cuenta"], str(l["afiliado_numero"] or ""), (l["afiliado_nombre"] or "").upper(), fp, cod,
            int(cant) if cant == int(cant) else cant, 0, None, round(l["total"] or 0, 2), 0, 0, 0, 0, 0, None,
            int(l.get("iva") or 0),
            None, None, fpres, None, None, str(l["nro_transaccion"] or "") or None]


def generar_template(os_key, ids):
    if not ids:
        raise ValueError("No hay filas seleccionadas.")
    marcas = ",".join("?" * len(ids))
    lineas = db.q(f"SELECT * FROM lineas WHERE os=? AND estado='facturacion' AND id IN ({marcas}) ORDER BY id",
                  [os_key] + list(ids))
    if not lineas:
        raise ValueError("Las filas seleccionadas no están en Facturación.")
    periodos = {l["periodo"] for l in lineas}
    if len(periodos) > 1:
        raise ValueError("Las filas seleccionadas son de períodos distintos: " + ", ".join(sorted(periodos)))
    periodo = periodos.pop()
    malas = [l for l in lineas if validar_para_procesar(l) or not l["fecha_prestacion"] or not l["afiliado_numero"]]
    if malas:
        raise ValueError(f"{len(malas)} fila(s) sin cuenta, código, fecha, afiliado o valor (ej: transacción "
                         f"{malas[0]['nro_transaccion']}). Corregilas o rechazalas antes de generar el template.")
    wb = Workbook()
    ws = wb.active
    ws.title = "ImportacionesEvweb"
    ws.append(COLS_TEMPLATE)
    for c in ws[1]:
        c.font = Font(bold=True)
    fpres = fecha_presentacion()
    for l in lineas:
        ws.append(_fila_template(l, fpres))
    for fila in ws.iter_rows(min_row=2):
        for c, k in zip(fila, COLS_TEMPLATE):
            if k in ("fecha_prestacion", "fecha_presentacion") and isinstance(c.value, datetime):
                c.number_format = "dd/mm/yyyy hh:mm"
            elif k in ("matricula", "afiliado_numero", "afiliado_denominacion", "nroAutorizacion") and c.value is not None:
                c.number_format = "@"
    sin_formulas(ws)
    ws.auto_filter.ref = f"A1:V{max(1, ws.max_row)}"
    for letra, w in {"A": 10, "B": 14, "C": 30, "D": 17, "E": 12, "S": 17, "V": 16}.items():
        ws.column_dimensions[letra].width = w
    out = io.BytesIO()
    wb.save(out)
    with db.tx() as c:
        nn = (c.execute("SELECT COALESCE(MAX(nn),0) FROM templates WHERE periodo=?", (periodo,)).fetchone()[0]) + 1
        nombre = f"Template_facturacion_{periodo}_{nn:02d}"
        cur = c.execute(
            "INSERT INTO templates(os,periodo,nn,nombre,fecha,filas,total,contenido) VALUES (?,?,?,?,?,?,?,?)",
            (os_key, periodo, nn, nombre, datetime.now().strftime("%d/%m/%Y %H:%M"), len(lineas),
             round(sum(l["total"] or 0 for l in lineas), 2), out.getvalue()))
        tid = cur.lastrowid
        c.execute(f"UPDATE lineas SET estado='template', template_id=? WHERE id IN ({','.join('?' * len(lineas))})",
                  [tid] + [l["id"] for l in lineas])
    return {"id": tid, "nombre": nombre, "filas": len(lineas)}


# ───────────────────────── presentaciones ─────────────────────────

def _leer_export(contenido, nombre, factura=""):
    df = leer_tabla(contenido, nombre, claves=["cod_practica", "Matricula"])
    if not col(df, "Matricula", parcial=False) or not col(df, "cod_practica", parcial=False):
        raise ValueError("El archivo no parece ser un 'PrestacionesExport' (faltan columnas Matricula / cod_practica).")
    if factura:
        c_f = col(df, "NumeroFactura")
        if not c_f:
            raise ValueError("El archivo no tiene columna NumeroFactura para filtrar.")
        df = df[df[c_f].astype(str).str.strip() == factura.strip()]
        if df.empty:
            raise ValueError(f"No hay filas con N° de factura {factura}.")
    return df.reset_index(drop=True)


def _num_export(df):
    """Las columnas numéricas del export vuelven a ser números en el Excel de salida."""
    for c in ("cantidad", "actuacion", "Honorario", "1er_ayudante", "2do_ayudante", "gasto", "aparatologia", "IVA"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def convertir_sancor(contenido, nombre, factura=""):
    """Agrega la columna MP a continuación de Matricula, con la matrícula del padrón."""
    df = _leer_export(contenido, nombre, factura)
    padron = Padron("SANCOR")
    c_mat = col(df, "Matricula", parcial=False)
    c_cuit = col(df, "cuit", parcial=False)

    def mp(r):
        p = padron.por_cuenta.get(txt(r[c_mat]).upper())
        if not p and c_cuit:
            p = padron.por_cuit.get(re.sub(r"\D", "", txt(r[c_cuit])))
        return padron.mp(p)

    mps = df.apply(mp, axis=1)
    pos = list(df.columns).index(c_mat) + 1
    df.insert(pos, "MP", mps)
    sin = sorted({txt(v) for v in df.loc[df["MP"] == "", c_mat]})
    df = _num_export(df)
    return df_a_xlsx(df.fillna(""), "Prestaciones exportadas"), {"filas": len(df), "sin_mp": sin}


def convertir_galeno(contenido, nombre, factura="", validado=None):
    """PrestacionesExport → PlanillaPrestaciones_Galeno (modelo del portal).

    El importe (columna J) es el total del export menos el coseguro de esa transacción,
    tomado del archivo validado de Galeno (cruce por número de transacción)."""
    df = _leer_export(contenido, nombre, factura)
    padron = Padron("GALENO")
    if validado:      # archivo validado subido en el momento: actualiza los coseguros guardados
        filas_val, _ = _parse_galeno(leer_tabla(validado[0], validado[1], claves=PARSERS["GALENO"][1]))
        guardar_coseguros("GALENO", filas_val)
    k = lambda c: re.sub(r"[.\s-]", "", str(c or "")).upper().lstrip("0")  # noqa: E731
    cos = {}
    for f in db.q("SELECT nro, cod, copago FROM coseguros WHERE os='GALENO'"):
        cos.setdefault(f["nro"], {})[k(f["cod"])] = f["copago"]
    c_aut = col(df, "numaut", parcial=False)
    cods_export = {}  # transacción → códigos que trae el export
    if c_aut:
        for nro, cod in zip(df[c_aut].map(limpiar_id), df["cod_practica"].map(k)):
            cods_export.setdefault(nro, set()).add(cod)
    usado = {}        # transacción → códigos ya descontados
    wb = load_workbook(os.path.join(ASSETS, "PlanillaPrestaciones_Galeno.xlsx"))
    ws = wb.active
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row)
    sin, sin_esp, sin_cruce, excedidos = set(), set(), set(), []
    total_cos, filas_cos = 0.0, 0
    g = lambda r, c: txt(r.get(c))  # noqa: E731
    for _, r in df.iterrows():
        cuenta = g(r, "Matricula").upper()
        p = padron.por_cuenta.get(cuenta) or padron.por_cuit.get(re.sub(r"\D", "", g(r, "cuit")))
        mp = padron.mp(p)
        if not mp:
            sin.add(cuenta)
        if not (p and p["especialidad"]):
            sin_esp.add(cuenta)
        hon = num(r.get("Honorario")) + num(r.get("1er_ayudante")) + num(r.get("2do_ayudante"))
        gas = num(r.get("gasto")) + num(r.get("aparatologia"))
        hg = 2 if (hon and gas) else 1 if gas else 0
        # coseguro: el de la misma práctica; si ningún código de la transacción coincide con el
        # archivo validado, el coseguro completo de la transacción va en su primera fila
        nro, cod = limpiar_id(g(r, "numaut")), k(g(r, "cod_practica"))
        copago = 0.0
        if nro and nro in cos:
            pend = {c: v for c, v in cos[nro].items() if c not in usado.setdefault(nro, set())}
            if cod in pend:
                copago = pend[cod]
                usado[nro].add(cod)
            elif pend and not (cods_export.get(nro, set()) & set(cos[nro])):
                copago = sum(pend.values())
                usado[nro].update(pend)
        elif nro:
            sin_cruce.add(nro)
        importe = round(hon + gas - copago, 2)
        if importe < 0:
            excedidos.append(nro)
            importe = 0.0
        if copago:
            total_cos, filas_cos = total_cos + copago, filas_cos + 1
        f = datetime.strptime(fecha_ddmmaaaa(r.get("fecha_prestacion")), "%d/%m/%Y") \
            if re.fullmatch(r"\d{2}/\d{2}/\d{4}", fecha_ddmmaaaa(r.get("fecha_prestacion"))) else g(r, "fecha_prestacion")
        ent = lambda v: int(v) if str(v).isdigit() and not str(v).startswith("0") else v  # noqa: E731
        ws.append([
            121, f, None, None,
            re.sub(r"\D", "", g(r, "afiliado_numero"))[:10],
            g(r, "afiliado_denominacion"),
            ent(g(r, "cod_practica")),
            " ".join(g(r, "Descripcion_Practica").split()),
            int(num(r.get("cantidad"), 1) or 1),
            importe,
            ent(g(r, "numaut")),
            1, ent(mp) if mp else None, None, hg, None,
            (p["especialidad"].strip() if p and p["especialidad"] else None), None, None,
        ])
        fila = ws.max_row
        ws.cell(fila, 2).number_format = "dd/mm/yyyy;@"
        ws.cell(fila, 5).number_format = "@"
        ws.cell(fila, 10).number_format = "#,##0.00"
        for cidx in (1, 7, 9, 11, 12, 13, 15):
            ws.cell(fila, cidx).number_format = "General"
    sin_formulas(ws)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), {"filas": len(df), "sin_mp": sorted(s for s in sin if s),
                            "sin_especialidad": sorted(s for s in sin_esp if s),
                            "coseguro_total": round(total_cos, 2), "coseguro_filas": filas_cos,
                            "sin_cruce": len(sin_cruce), "sin_cruce_ej": sorted(sin_cruce)[:8],
                            "coseguro_excedido": excedidos[:20]}
