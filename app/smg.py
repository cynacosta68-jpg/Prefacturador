"""SWISS MEDICAL: las prestaciones del Reporte de Liquidación no vienen valorizadas.

Este módulo trae el proceso del repositorio «Valoriacion_SMG»:

  1. Limpieza del reporte y eliminación de duplicados por N° de transacción.
  2. Datos del profesional por CUIT del efector (cuenta, especialidad, categoría),
     IVA del template y código de obra social (11062 si es Responsable Inscripto, 11060 si no).
  3. Valorización con la «Base de datos de valorización» (solapas Nomenclador, unidades y
     Valor Fijos), en este orden de prioridad:
        R_ESP  reglas por especialidad / código específico
        R0     Nomenclador Nacional (otorrino y dermatología, códigos que no empiezan con 4)
        R1     Nomenclador: coeficiente del cirujano × valor de la unidad del mes
        R2A    Valores fijos de Swiss Medical por código + categoría
        R2B    Valores fijos de Swiss Medical por código
        R3     Valores fijos de cualquier nomenclador por código + categoría
     Si ninguna regla da valor, la línea queda para revisar.
"""
import io
import re
import unicodedata

import pandas as pd

from . import db

CODIGOS = ("11062", "11060")           # el bot extrae primero 11062 (I.V.A.) y después 11060

DESC_CLINICA = "SMG MED Consulta clinica medica"
DESC_MEDICO = "SMG MED Consulta medica"
DESC_MEDGEN = "SMG MED consulta medica"
ESPECIALIDADES_CLINICA_42 = ("CLINICA MEDICA", "CARDIOLOGIA", "CIRUGIA GENERAL", "GASTROENTEROLOGIA")
CODIGOS_SMG_CON_ARANCEL = ("12100401", "220101")
CODIGOS_SMG_SIN_ARANCEL = ("18010303",)
# Códigos del reporte que se facturan con otro código (el que figura en la grilla)
ALIAS_CODIGOS = {"180101": "18010301", "290102": "29010203"}
# Códigos que la grilla trae en dos solapas con valores distintos: solapa cuyo valor es el que se factura
SOLAPA_PREFERIDA = {"29010230": "neurologia"}
CLINICOS_42 = ("clinica medica", "medicina interna", "geriatria")
# «Consulta médica en consultorio» (42010100) hecha por un especialista: se factura con el código de
# consulta de su especialidad (código, denominación).
CONSULTA_GENERICA = "42010100"
CONSULTA_POR_ESPECIALIDAD = {
    "CARDIOLOGIA": ("42011700", "Consulta Cardiología"),
    "CIRUGIA GENERAL": ("42010800", "Consulta Cirugía general"),
    "GASTROENTEROLOGIA": ("42012000", "Consulta Gastroenterología"),
    "HEMATOLOGIA": ("42012300", "Consulta Hematología"),
    "NEUROCIRUGIA": ("42010106", "Consulta Neurocirugía"),
    "ORTOPEDIA Y TRAUMATOLOGIA": ("42011200", "Consulta Traumatología"),
    "PEDIATRIA": ("42013200", "Consulta Pediatría"),
    "REUMATOLOGIA": ("42011201", "Consulta Reumatología"),
    "DERMATOLOGIA": ("42011300", "Consulta Dermatología"),
    "ENDOCRINOLOGIA": ("42011900", "Consulta Endocrinología"),
    "GINECOLOGIA": ("42012201", "Consulta Ginecología"),
    "TOCOGINECOLOGIA": ("42012201", "Consulta Ginecología"),
    "OBSTETRICIA": ("42012202", "Consulta Obstetricia"),
    "INFECTOLOGIA": ("42012301", "Consulta infectología"),
    "NEFROLOGIA": ("42011000", "Consulta Nefrología"),
    "NEUMONOLOGIA": ("42012800", "Consulta Neumonología"),
    "NEUROLOGIA": ("42012900", "Consulta Neurología"),
    "OFTALMOLOGIA": ("42013000", "Consulta Oftalmología"),
    "ONCOLOGIA": ("42013500", "Consulta Oncología"),
    "OTORRINOLARINGOLOGIA": ("42013100", "Consulta Otorrinolaringología"),
    "UROLOGIA": ("42013600", "Consulta Urología"),
}


CONSULTAS_QUE_NO_SE_CAMBIAN = ("42011901",)      # consulta de médico nutricionista


def codigo_propuesto(cod, especialidad):
    """Código que propone la aplicación para la línea: (código, denominación, motivo).
    Si no hay nada que proponer devuelve el mismo código del archivo, sin denominación ni motivo.

    · Códigos que se facturan con otro (180101 → 18010301).
    · Consultas (4201…): si la especialidad del profesional tiene código de consulta propio y el
      archivo trae otro (la consulta genérica o la de otra especialidad), se propone el de su especialidad."""
    k = clave_cod(cod)
    if k in ALIAS_CODIGOS:
        return ALIAS_CODIGOS[k], "", "código equivalente en la grilla"
    if k.startswith("4201") and k not in CONSULTAS_QUE_NO_SE_CAMBIAN:
        propia = CONSULTA_POR_ESPECIALIDAD.get(sin_tilde(especialidad))
        if propia and propia[0] != k:
            return propia[0], propia[1], "consulta según la especialidad"
    return str(cod or "").strip(), "", ""
ESPECIALIDADES_R0 = ("OTORRINOLARINGOLOGIA", "DERMATOLOGIA")


def limpiar(x):
    """Igual que en el repositorio: sin decimales, sin espacios, en mayúsculas."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return str(x).split(".")[0].strip().upper()


def clave_cod(x):
    """Código para comparar: pandas leía los códigos como números y perdía los ceros de la izquierda."""
    c = limpiar(x)
    return c.lstrip("0") or c


def sin_tilde(s):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    t = unicodedata.normalize("NFKD", str(s).strip().upper())
    return "".join(c for c in t if not unicodedata.combining(c))


def _num(v):
    try:
        f = float(str(v).replace(",", ".")) if not isinstance(v, (int, float)) else float(v)
        return None if pd.isna(f) else f
    except Exception:
        return None


def _periodo(v):
    """Fecha o texto → MMAAAA."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    m = re.match(r"^(\d{4})-(\d{2})", s)
    if m:
        return m.group(2) + m.group(1)
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{int(m.group(2)):02d}{m.group(3)}"
    if re.fullmatch(r"(0[1-9]|1[0-2])\d{4}", s):
        return s
    f = pd.to_datetime(s, errors="coerce", dayfirst=True)
    return None if pd.isna(f) else f"{f.month:02d}{f.year}"


def _col(df, *nombres):
    normas = {sin_tilde(c).replace("_", " "): c for c in df.columns}
    for n in nombres:
        k = sin_tilde(n).replace("_", " ")
        if k in normas:
            return normas[k]
    return None


# ───────────────────────── base de valorización ─────────────────────────

def importar_base(os_key, contenido, nombre):
    """Carga la «Base de datos de valorización» en las tablas de valores y unidades.
    Cada mes de la base queda como un período; se reemplazan los períodos que trae el archivo."""
    engine = "openpyxl" if contenido[:2] == b"PK" else "xlrd"
    libro = pd.read_excel(io.BytesIO(contenido), sheet_name=None, engine=engine)
    hojas = {sin_tilde(k): v for k, v in libro.items()}
    faltan = [n for n in ("NOMENCLADOR", "UNIDADES", "VALOR FIJOS") if n not in hojas]
    if faltan:
        raise ValueError("La base de valorización de SWISS MEDICAL debe tener las solapas Nomenclador, unidades y "
                         "Valor Fijos. Faltan: " + ", ".join(faltan) + ".")
    nom, uni, fij = hojas["NOMENCLADOR"], hojas["UNIDADES"], hojas["VALOR FIJOS"]
    c_cod, c_tipo, c_cir = _col(nom, "Código", "Codigo"), _col(nom, "Tipo de nomenclador"), _col(nom, "Cirujano")
    u_tipo, u_mes, u_val = _col(uni, "Tipo de Nomenclador"), _col(uni, "Mes"), _col(uni, "Valor")
    f_cod, f_ar, f_per = _col(fij, "Cod", "Código", "Codigo"), _col(fij, "Arancel"), _col(fij, "Periodo", "Período")
    f_nom, f_desc, f_tot = _col(fij, "Nomenclador"), _col(fij, "Descripción", "Descripcion"), _col(fij, "Total prestación", "Total prestacion")
    for etiqueta, c in (("Nomenclador: Código", c_cod), ("Nomenclador: Tipo de nomenclador", c_tipo),
                        ("Nomenclador: Cirujano", c_cir), ("unidades: Tipo de Nomenclador", u_tipo),
                        ("unidades: Mes", u_mes), ("unidades: Valor", u_val), ("Valor Fijos: Cod", f_cod),
                        ("Valor Fijos: Periodo", f_per), ("Valor Fijos: Total prestación", f_tot)):
        if c is None:
            raise ValueError(f"En la base de valorización falta la columna «{etiqueta}».")
    c_desc = _col(nom, "Descripción", "Descripcion", "Detalle", "Prestación")

    unidades = []        # (periodo, tipo, valor)
    for _, r in uni.iterrows():
        p, v, t = _periodo(r[u_mes]), _num(r[u_val]), str(r[u_tipo]).strip() if not pd.isna(r[u_tipo]) else ""
        if p and v and t:
            unidades.append((p, t, v))
    fijos = []
    for _, r in fij.iterrows():
        p, v, cod = _periodo(r[f_per]), _num(r[f_tot]), limpiar(r[f_cod])
        if p and v is not None and cod:
            fijos.append(dict(periodo=p, codigo=cod, categoria=limpiar(r[f_ar]) if f_ar else "",
                              nomenclador="" if not f_nom or pd.isna(r[f_nom]) else str(r[f_nom]).strip(),
                              descripcion="" if not f_desc or pd.isna(r[f_desc]) else str(r[f_desc]).strip(), valor=v))
    nomen = []
    for _, r in nom.iterrows():
        cod, cir = limpiar(r[c_cod]), _num(r[c_cir])
        if cod and cir is not None:
            nomen.append(dict(codigo=cod, tipo=str(r[c_tipo]).strip() if not pd.isna(r[c_tipo]) else "", cirujano=cir,
                              descripcion="" if not c_desc or pd.isna(r[c_desc]) else str(r[c_desc]).strip()))
    periodos = sorted({p for p, _, _ in unidades} | {f["periodo"] for f in fijos}, key=lambda p: (p[2:], p[:2]))
    if not periodos:
        raise ValueError("La base de valorización no tiene períodos con valores (columnas Mes / Periodo).")

    with db.tx() as c:
        for p in periodos:
            c.execute("DELETE FROM valores WHERE os=? AND periodo=?", (os_key, p))
            c.execute("DELETE FROM unidades WHERE os=? AND periodo=?", (os_key, p))
        ids = {}
        for fila, (p, t, v) in enumerate(unidades, start=2):
            if (p, t) in ids:
                continue
            cur = c.execute("INSERT INTO unidades(os,periodo,especialidad,tipo_unidad,valor,origen,hoja,fila) "
                            "VALUES (?,?,?,?,?,?,?,?)", (os_key, p, t, "Unidad · " + t, v, "declarada", "unidades", fila))
            ids[(p, t)] = (cur.lastrowid, v)
        n_nom = 0
        for (p, t), (uid, v) in ids.items():
            for fila, n in enumerate(nomen, start=2):
                if n["tipo"] != t:
                    continue
                c.execute("INSERT INTO valores(os,periodo,especialidad,seccion,codigo,codigo_prestador,descripcion,categoria,"
                          "unidades,tipo_valor,unidad_id,valor,valor_grilla,ayudantes,grupo,hoja,fila) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (os_key, p, t, "Nomenclador", n["codigo"], "", n["descripcion"], "", n["cirujano"], "unidad",
                           uid, round(n["cirujano"] * v, 2), None, "", "", "Nomenclador", fila))
                n_nom += 1
        for fila, f in enumerate(fijos, start=2):
            c.execute("INSERT INTO valores(os,periodo,especialidad,seccion,codigo,codigo_prestador,descripcion,categoria,"
                      "unidades,tipo_valor,unidad_id,valor,valor_grilla,ayudantes,grupo,hoja,fila) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (os_key, f["periodo"], f["nomenclador"] or "Valores fijos", f["nomenclador"], f["codigo"], "",
                       f["descripcion"], f["categoria"], None, "fijo", None, round(f["valor"], 2), f["valor"], "", "",
                       "Valor Fijos", fila))
    return {"filas": n_nom + len(fijos), "periodo": periodos[-1], "periodos": periodos, "unidades": len(ids),
            "por_unidad": n_nom, "fijas": len(fijos),
            "hojas": [{"hoja": "Nomenclador", "prestaciones": n_nom, "por_unidad": n_nom, "fijas": 0, "unidades": 0},
                      {"hoja": "unidades", "prestaciones": 0, "por_unidad": 0, "fijas": 0, "unidades": len(ids)},
                      {"hoja": "Valor Fijos", "prestaciones": len(fijos), "por_unidad": 0, "fijas": len(fijos), "unidades": 0}]}


# ───────────────────────── valorización ─────────────────────────

class Valorizador:
    """Aplica las reglas del repositorio para un período (el mes de la transacción)."""

    def __init__(self, os_key, periodo):
        self.periodo = periodo
        filas = db.q("SELECT * FROM valores WHERE os=? AND periodo=? AND valor IS NOT NULL ORDER BY id", (os_key, periodo))
        self.fijos = [f for f in filas if f["hoja"] == "Valor Fijos"]
        self.nomen = {}
        for f in filas:
            if f["hoja"] == "Nomenclador":
                self.nomen.setdefault(clave_cod(f["codigo"]), f["valor"])
        for f in self.fijos:
            f["_k"] = clave_cod(f["codigo"])
            f["_cat"] = limpiar(f["categoria"])
            f["_nom"] = sin_tilde(f["seccion"])
        self.hay = bool(filas)

    def _fijo(self, cond):
        return next((f["valor"] for f in self.fijos if cond(f)), None)

    def valor(self, cod, categoria, especialidad):
        """Devuelve (valor, regla) o (None, '')."""
        k, cat, esp = clave_cod(cod), limpiar(categoria), sin_tilde(especialidad)
        smg = lambda f: str(f["descripcion"] or "").startswith("SMG")  # noqa: E731

        # R_ESP · reglas por especialidad / código específico
        v = None
        if k in CODIGOS_SMG_SIN_ARANCEL:
            v = self._fijo(lambda f: f["_k"] == k and smg(f))
        elif k in CODIGOS_SMG_CON_ARANCEL:
            v = self._fijo(lambda f: f["_k"] == k and f["_cat"] == cat and smg(f))
        elif k == "42010100" and esp in ESPECIALIDADES_CLINICA_42:
            v = self._fijo(lambda f: f["_k"] == k and f["descripcion"] == DESC_CLINICA and f["_cat"] == cat)
        elif k == "42010100" and esp == "MEDICO":
            v = self._fijo(lambda f: f["_k"] == k and f["descripcion"] == DESC_MEDICO and f["_cat"] == cat)
        elif k == "42010100" and esp == "MEDICINA GENERAL Y/O FAMILIAR":
            efectivo = "C" if cat == "R" else cat
            v = self._fijo(lambda f: f["_k"] == k and f["descripcion"] == DESC_MEDGEN and f["_cat"] == efectivo)
        elif esp == "DIAGNOSTICO POR IMAGENES":
            v = self._fijo(lambda f: f["_k"] == k and not f["seccion"])
        if v is not None:
            return v, "regla especial"

        # R0 · Nomenclador Nacional
        if esp in ESPECIALIDADES_R0 and not k.startswith("4"):
            v = self._fijo(lambda f: f["_k"] == k and "NOMENCLADOR NACIONAL" in f["_nom"])
            if v is not None:
                return v, "nomenclador nacional"
        # R1 · nomenclador × unidad
        if k in self.nomen:
            return self.nomen[k], "nomenclador × unidad"
        # R2 · valores fijos de Swiss Medical
        sm = lambda f: not f["seccion"] or "SWISS MEDICAL" in f["_nom"]  # noqa: E731
        v = self._fijo(lambda f: f["_k"] == k and f["_cat"] == cat and sm(f))
        if v is not None:
            return v, "valor fijo SMG (código + categoría)"
        v = self._fijo(lambda f: f["_k"] == k and sm(f))
        if v is not None:
            return v, "valor fijo SMG (código)"
        # R3 · valores fijos sin filtro de nomenclador
        v = self._fijo(lambda f: f["_k"] == k and f["_cat"] == cat)
        if v is not None:
            return v, "valor fijo (código + categoría)"
        return None, ""


class ValorizadorGrilla:
    """Valoriza con la grilla de valores de Swiss Medical (el Excel con una solapa por especialidad).

    · Prácticas: por código. Si la solapa tiene columnas por categoría (Cirujano A / B / C) se usa la del
      profesional; si tiene valor para recertificados, se usa cuando la categoría es R.
    · Consultas (códigos 42…): la grilla no las lista por código sino por tipo de consulta, así que se
      eligen por la denominación de la prestación, la especialidad y la categoría del profesional."""

    def __init__(self, os_key, periodo):
        from .grillas import Grilla
        self.g = Grilla(os_key, periodo)
        self.periodo = self.g.periodo
        self.hay = bool(self.periodo)
        self.consultas = {}
        if self.hay:
            for f in db.q("SELECT descripcion, valor FROM valores WHERE os=? AND periodo=? AND valor>0 "
                          "AND COALESCE(codigo,'')='' AND COALESCE(codigo_prestador,'')='' ORDER BY id",
                          (os_key, self.periodo)):
                n = " ".join(sin_tilde(f["descripcion"]).lower().split())
                if n.startswith("consulta"):
                    self.consultas.setdefault(n, (f["valor"], f["descripcion"]))

    def _consulta(self, *palabras, sin=()):
        for n, (v, d) in self.consultas.items():
            if all(p in n for p in palabras) and not any(x in n for x in sin):
                return v, "consulta · " + " ".join(d.split())
        return None, ""

    def valor(self, cod, categoria, especialidad, desc=""):
        cat = limpiar(categoria)
        cand = self.g.idx.get(self.g._k(cod)) if self.hay else None
        if cand:
            # El reporte trae el código de Swiss (SMMP): manda la columna de código de la grilla. El código
            # del Colegio solo se usa si no hay ninguna fila con ese código de Swiss.
            k = self.g._k(cod)
            propios = [f for f in cand if self.g._k(f["codigo"]) == k]
            cand = propios or cand
            pref = SOLAPA_PREFERIDA.get(clave_cod(cod))
            if pref:
                cand = [f for f in cand if sin_tilde(f["hoja"]).lower() == pref] or cand
        if cand:
            v, regla = self._por_codigo(cand, cat)
            if v:       # el mismo código puede estar en dos solapas con valores distintos: se avisa
                elegida = regla.split(" · ")[0]
                otros = {f["hoja"] for f in cand if f["hoja"] != elegida and abs(f["valor"] - v) > 1
                         and f["categoria"] in ("", "R" if cat == "R" else "")}
                if otros:
                    regla += " · código también en " + ", ".join(sorted(otros)) + " con otro valor"
            return v, regla
        return self._consultas(cod, cat, especialidad, desc)

    def _por_codigo(self, cand, cat):
        if True:
            cats = {f["categoria"] for f in cand}
            if cats & {"A", "B", "C"}:
                efectiva = "C" if cat == "R" else cat          # tabla A / B / C sin columna R: se toma C
                f = next((x for x in cand if x["categoria"] == efectiva), None)
                if not f:
                    return None, "falta la categoría del profesional"
                return f["valor"], f"{f['hoja']} · categoría {efectiva}" + (" (profesional R)" if cat == "R" else "")
            if "R" in cats:
                f = next((x for x in cand if (x["categoria"] == "R") == (cat == "R")), cand[0])
                return f["valor"], f["hoja"] + (" · recertificados" if f["categoria"] == "R" else "")
            return cand[0]["valor"], cand[0]["hoja"]

    def _consultas(self, cod, cat, especialidad, desc):
        """Reglas tomadas de la facturación emitida de octubre 2026:
        · pediatras → Consulta PEDIATRA (R: recertificado)
        · «Consulta médica en consultorio» de clínica médica y afines → CONSULTA CLINICOS (R: recertificados)
        · reumatología, infectología y psiquiatría → su renglón
        · el resto (incluye Médico y Medicina General) → Consulta A / B / C especialistas
        · categoría R sin renglón propio → valor recertificado"""
        if not self.hay or not clave_cod(cod).startswith("42"):
            return None, ""
        nd = sin_tilde(desc).lower()
        ne = sin_tilde(especialidad).lower()
        rec = cat == "R"
        # Pediatras, y consulta de Pediatría hecha por una especialidad infantil (oncología infantil, etc.)
        if "pediatr" in ne or "neonatolog" in ne or ("pediatr" in nd and (not ne or "infantil" in ne)):
            v, r = self._consulta("pediatra", "recertif") if rec else self._consulta("pediatra", sin=("recertif",))
            if v:
                return v, r
        generica = "consulta medica" in nd or not nd
        if generica and any(x in ne for x in CLINICOS_42):
            v, r = self._consulta("clinicos", "recertif") if rec else self._consulta("clinicos", sin=("recertif",))
            if v:
                return v, r
        for clave in ("reumatolog", "infectolog", "psiquiatr"):
            if clave in ne or (clave in nd and not rec):
                v, r = self._consulta(clave)
                if v and not rec:
                    return v, r
        if rec:
            v, r = self._consulta("recertif")
            if v:
                return v, "consulta · valor recertificado (profesional R)"
        if cat not in ("A", "B", "C"):
            return None, "falta la categoría del profesional"
        return self._consulta(f"consulta {cat.lower()} especialistas")


class Valorizadores:
    """Un valorizador por período, creado a demanda. Si el período tiene la base estructurada del
    repositorio (Nomenclador / unidades / Valor Fijos) se usan sus reglas; si no, la grilla de valores."""

    def __init__(self, os_key):
        self.os, self.cache = os_key, {}

    def valor(self, fecha_ddmmaaaa, cod, categoria, especialidad, periodo_por_defecto="", desc=""):
        p = _periodo(fecha_ddmmaaaa) or periodo_por_defecto
        if p not in self.cache:
            vz = Valorizador(self.os, p)
            if not vz.fijos and not vz.nomen:
                vz = ValorizadorGrilla(self.os, p)
            self.cache[p] = vz
        vz = self.cache[p]
        if isinstance(vz, ValorizadorGrilla):
            v, regla = vz.valor(cod, categoria, especialidad, desc)
        else:
            v, regla = vz.valor(cod, categoria, especialidad)
        return v, regla, (vz.periodo or p), vz.hay


def es_base(contenido):
    """True si el Excel es la base estructurada del repositorio (y no la grilla por especialidad)."""
    try:
        engine = "openpyxl" if contenido[:2] == b"PK" else "xlrd"
        nombres = {sin_tilde(n) for n in pd.ExcelFile(io.BytesIO(contenido), engine=engine).sheet_names}
    except Exception:
        return False
    return {"NOMENCLADOR", "UNIDADES", "VALOR FIJOS"} <= nombres


# ───────────────────────── reporte de liquidación ─────────────────────────

def parse_reporte(df):
    """Reporte de Liquidación de Swiss Medical (encabezados nuevos o los del repositorio)."""
    c_tx = _col(df, "N° Transacción", "Nº Transacción", "transacción_item", "transaccion_item")
    if not c_tx:
        raise ValueError("El archivo de SWISS MEDICAL no tiene la columna «N° Transacción».")
    c = lambda *n: _col(df, *n)  # noqa: E731
    c_ticket, c_aut = c("N° Ticket", "transacción_ticket"), c("Número de autorización", "autorización")
    c_falta, c_fprest = c("Fecha Alta Transacción", "fecha_transaccion"), c("Fecha Prestación", "fecha_prestacion")
    c_cred, c_afil = c("Credencial", "credencial"), c("Afiliado Nombre y Apellido", "afiliado")
    c_iva, c_cod = c("Condición IVA socio", "condición_iva"), c("Código de prestación", "prestación")
    c_desc, c_cant = c("Prestación Denominación", "prestación_denominación", "denominación"), c("Cantidad", "cantidad")
    c_cop, c_cuit = c("Copago", "copago"), c("Cuit Efector", "efector_cuit")
    c_mat, c_nom = c("Matricula Efector", "efector_matricula"), c("Efector Razón Social", "efector_razón_social")
    if not c_cod or not c_cuit:
        raise ValueError("El archivo de SWISS MEDICAL no tiene las columnas «Código de prestación» y «Cuit Efector».")
    from .logic import fecha_ddmmaaaa, limpiar_id, num, txt
    out, vistos, repetidas = [], set(), 0
    for _, r in df.iterrows():
        nro = limpiar_id(r[c_tx])
        if not nro:
            continue
        if nro in vistos:              # el repositorio elimina duplicados por transacción_item
            repetidas += 1
            continue
        vistos.add(nro)
        # La fecha de la prestación define el mes de valorización. «Fecha Alta Transacción» viene vacía («-»)
        # o en formato mes/día/año, así que solo se usa si falta la de prestación.
        fecha = fecha_ddmmaaaa(r[c_fprest]) if c_fprest else ""
        if not re.match(r"\d{2}/\d{2}/\d{4}", fecha):
            fecha = fecha_ddmmaaaa(r[c_falta]) if c_falta else ""
        aut = re.sub(r"\D", "", txt(r[c_aut])) if c_aut else ""
        out.append(dict(
            claves=[nro] + [x for x in ((limpiar_id(r[c_ticket]) if c_ticket else ""), aut) if x and x != nro],
            fecha=fecha, afiliado_numero=txt(r[c_cred]) if c_cred else "", afiliado_nombre=txt(r[c_afil]) if c_afil else "",
            cod=txt(r[c_cod]), desc=txt(r[c_desc]) if c_desc else "", cant=num(r[c_cant], 1) if c_cant else 1,
            importe=None, prof_nombre=txt(r[c_nom]) if c_nom else "", prof_mp=txt(r[c_mat]) if c_mat else "",
            prof_cuit=re.sub(r"\D", "", txt(r[c_cuit]).split(".")[0]), condicion_iva=txt(r[c_iva]) if c_iva else "",
            copago=num(r[c_cop]) if c_cop else 0.0))
    return out, repetidas


def iva_y_codigo(resp_fiscal, condicion_iva):
    """IVA del template (0 / 1) y código de obra social, como en el repositorio."""
    rf = str(resp_fiscal or "").strip()
    # IVA = 1 solo si el profesional es Responsable Inscripto (código de IVA 1) y el afiliado es Gravado
    iva = 1 if (rf.lower() == "responsable inscripto" and str(condicion_iva or "").strip().lower() != "exento") else 0
    return iva, ("11062" if rf == "Responsable Inscripto" else "11060")
