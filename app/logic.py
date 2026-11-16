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

from . import db, grillas

OBRAS = {
    "AVALIAN": {"codigo": "10067", "nombre": "10067 - A.C.A. SALUD (AVALIAN)"},
    "SANCOR": {"codigo": "10117", "nombre": "10117 - ASOCIACION MUTUAL SANCOR"},
    "GALENO": {"codigo": "10099", "nombre": "10099 - GALENO Argentina S.A. AZUL/BLANCO/ORO/PLATA"},
}

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

def importar_padron(os_key, contenido, nombre, reemplazar=True):
    df = leer_tabla(contenido, nombre, claves=["Profesional", "Nombre", "CUIT"])
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
    filas = []
    for _, r in df.iterrows():
        nom = txt(r[c_nombre])
        if not nom:
            continue
        filas.append((
            os_key,
            txt(r[c_cuenta]) if c_cuenta else "",
            nom,
            limpiar_id(r[c_cuit]) if c_cuit else "",
            txt(r[c_esp]) if c_esp else "",
            txt(r[c_cat]) if c_cat else "",
            txt(r[c_rf]) if c_rf else "",
            limpiar_id(r[c_mp]) if c_mp else "",
            norm(nom),
        ))
    with db.tx() as c:
        if reemplazar:
            c.execute("DELETE FROM profesionales WHERE os=?", (os_key,))
        c.executemany(
            "INSERT INTO profesionales(os,cuenta,nombre,cuit,especialidad,categoria,resp_fiscal,matricula,nombre_norm)"
            " VALUES (?,?,?,?,?,?,?,?,?)", filas)
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
    return grillas.importar(os_key, validar_periodo(periodo), contenido, nombre)


Grilla = grillas.Grilla


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
            cur = c.execute(
                "INSERT OR IGNORE INTO evweb_filas(extraccion_id,os,nro,profesional,cuenta,data,hash) VALUES (?,?,?,?,?,?,?)",
                (eid, os_key, limpiar_id(r[c_aut]), txt(r[c_prof]), txt(r[c_cta]) if c_cta else "", js, h))
            nuevas += cur.rowcount
        c.execute("UPDATE evweb_extracciones SET nuevas=? WHERE id=?", (nuevas, eid))
    return {"filas": len(df), "nuevas": nuevas, "col_autorizacion": c_aut, "col_profesional": c_prof}


def evweb_df(os_key, busqueda=""):
    filas = db.q("SELECT data FROM evweb_filas WHERE os=? ORDER BY id", (os_key,))
    regs = [json.loads(f["data"]) for f in filas]
    if busqueda:
        b = norm(busqueda)
        regs = [r for r in regs if b in norm(" ".join(r.values()))]
    return pd.DataFrame(regs)


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
}


def prefacturar(os_key, periodo, contenido, nombre):
    """Cruza el archivo validado con lo extraído de EVWEB por número de
    transacción, completa profesional desde el padrón y valoriza."""
    periodo = validar_periodo(periodo)
    parser, claves = PARSERS[os_key]
    filas, anuladas = parser(leer_tabla(contenido, nombre, claves=claves))
    if not filas:
        raise ValueError("El archivo no tiene filas para procesar.")

    ev = {}
    for f in db.q("SELECT nro, profesional, cuenta FROM evweb_filas WHERE os=? AND nro<>''", (os_key,)):
        ev.setdefault(f["nro"], f)
    padron = Padron(os_key)
    grilla = Grilla(os_key, periodo)
    ya = {(r["nro_transaccion"], r["cod_practica"]) for r in
          db.q("SELECT nro_transaccion, cod_practica FROM lineas WHERE os=?", (os_key,))}

    res = dict(total=len(filas), anuladas=anuladas, duplicadas=0, ok=0, sin_evweb=0, sin_padron=0,
               sin_valor=0, grilla_periodo=grilla.periodo)
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    nuevas, vistos = [], set()
    for f in filas:
        nro = f["claves"][0]
        k = (nro, f["cod"])
        if k in ya:
            res["duplicadas"] += 1
            continue
        # misma transacción+código repetida dentro del archivo: se conserva (puede ser cantidad real)
        vistos.add(k)
        e = next((ev[c] for c in f["claves"] if c and c in ev), None)
        prof, obs = None, []
        if e:
            if e["cuenta"]:
                prof = padron.por_cuenta.get(e["cuenta"].upper())
            prof = prof or padron.buscar_nombre(e["profesional"])
            cruce = "OK" if prof else "SIN PADRON"
            if not prof:
                obs.append(f"EVWEB: {e['profesional']} no está en el padrón")
        else:
            cruce = "SIN EVWEB"
            # ayuda: el archivo validado trae matrícula / nombre del efector
            prof = padron.por_mp.get(f["prof_mp"]) if f["prof_mp"] else None
            prof = prof or padron.buscar_nombre(f["prof_nombre"])
            obs.append("Transacción no encontrada en EVWEB"
                       + (" · profesional sugerido por el archivo validado" if prof else ""))
        res["ok" if cruce == "OK" else "sin_evweb" if cruce == "SIN EVWEB" else "sin_padron"] += 1

        cat = prof["categoria"] if prof else ""
        esp = prof["especialidad"] if prof else ""
        v = grilla.valor(f["cod"], cat)
        # GALENO no informa importes: se valoriza con la grilla. SANCOR y AVALIAN
        # traen el importe validado por la obra social; la grilla queda de respaldo.
        if f["importe"]:
            vu, origen = round(f["importe"] / f["cant"], 2), "archivo validado"
        elif v:
            vu, origen = v, f"grilla {grilla.periodo}"
        else:
            vu, origen = 0.0, ""
            res["sin_valor"] += 1
            obs.append("Sin valor en grilla")
        nuevas.append((
            os_key, periodo, "prefact", nro, f["fecha"], f["afiliado_numero"], f["afiliado_nombre"],
            f["cod"], f["desc"], f["cant"],
            prof["cuenta"] if prof else "", padron.mp(prof) or (f["prof_mp"] if not prof else ""),
            prof["nombre"] if prof else (e["profesional"] if e else f["prof_nombre"]),
            prof["cuit"] if prof else "", esp, cat, vu, round(vu * f["cant"], 2), origen, cruce,
            " · ".join(obs), ahora))
    with db.tx() as c:
        c.executemany(
            "INSERT INTO lineas(os,periodo,estado,nro_transaccion,fecha_prestacion,afiliado_numero,afiliado_nombre,"
            "cod_practica,descripcion,cantidad,cuenta,matricula,profesional,cuit,especialidad,categoria,valor_unit,"
            "total,origen_valor,cruce,observacion,creado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            nuevas)
    res["insertadas"] = len(nuevas)
    return res


CAMPOS_EDITABLES = ["nro_transaccion", "fecha_prestacion", "afiliado_numero", "afiliado_nombre", "cod_practica",
                    "descripcion", "cantidad", "cuenta", "matricula", "profesional", "cuit", "especialidad",
                    "categoria", "valor_unit", "observacion", "periodo"]


def editar_linea(lid, cambios, autocompletar=False):
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
    if autocompletar:
        padron = Padron(lin["os"])
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
                         especialidad=prof["especialidad"], categoria=prof["categoria"])
        elif nuevo["cuenta"] != lin["cuenta"] or nuevo["matricula"] != lin["matricula"]:
            raise ValueError("La cuenta / matrícula indicada no existe en el padrón de esta obra social.")
        cambio_cod = nuevo["cod_practica"] != lin["cod_practica"] or nuevo["categoria"] != lin["categoria"]
        if "valor_unit" not in cambios and (cambio_cod or not lin["valor_unit"]):
            g = Grilla(lin["os"], nuevo["periodo"])
            v = g.valor(nuevo["cod_practica"], nuevo["categoria"])
            if v:
                nuevo["valor_unit"], nuevo["origen_valor"] = v, f"grilla {g.periodo}"
    if "valor_unit" in cambios and num(cambios["valor_unit"]) != lin["valor_unit"]:
        nuevo["origen_valor"] = "manual"
    nuevo["total"] = round(nuevo["valor_unit"] * (nuevo["cantidad"] or 1), 2)
    if nuevo["cuenta"] and nuevo["profesional"] and lin["cruce"] != "OK":
        nuevo["cruce"] = "MANUAL"
    campos = CAMPOS_EDITABLES + ["total", "origen_valor", "cruce"]
    with db.tx() as c:
        c.execute(f"UPDATE lineas SET {','.join(k + '=?' for k in campos)} WHERE id=?",
                  [nuevo[k] for k in campos] + [lid])
    final = db.q1("SELECT * FROM lineas WHERE id=?", (lid,))
    final["_cambios"] = {k: {"antes": lin[k], "despues": final[k]} for k in campos if lin[k] != final[k]}
    return final


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
            int(cant) if cant == int(cant) else cant, 0, None, round(l["total"] or 0, 2), 0, 0, 0, 0, 0, None, 0,
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


def convertir_galeno(contenido, nombre, factura=""):
    """PrestacionesExport → PlanillaPrestaciones_Galeno (modelo del portal)."""
    df = _leer_export(contenido, nombre, factura)
    padron = Padron("GALENO")
    wb = load_workbook(os.path.join(ASSETS, "PlanillaPrestaciones_Galeno.xlsx"))
    ws = wb.active
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row)
    sin = set()
    g = lambda r, c: txt(r.get(c))  # noqa: E731
    for _, r in df.iterrows():
        cuenta = g(r, "Matricula").upper()
        p = padron.por_cuenta.get(cuenta) or padron.por_cuit.get(re.sub(r"\D", "", g(r, "cuit")))
        mp = padron.mp(p)
        if not mp:
            sin.add(cuenta)
        hon = num(r.get("Honorario")) + num(r.get("1er_ayudante")) + num(r.get("2do_ayudante"))
        gas = num(r.get("gasto")) + num(r.get("aparatologia"))
        hg = 2 if (hon and gas) else 1 if gas else 0
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
            round(hon + gas, 2),
            ent(g(r, "numaut")),
            1, ent(mp) if mp else None, None, hg, None, None, None, None,
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
    return out.getvalue(), {"filas": len(df), "sin_mp": sorted(s for s in sin if s)}
