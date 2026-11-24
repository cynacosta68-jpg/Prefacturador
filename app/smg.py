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
#
# La base de SWISS MEDICAL tiene dos partes que se consolidan en «Valores»:
#
#   · Valores fijos: reporte que sale del sistema (Nomenclador, Cod, Descripción, Arancel, Honorario,
#     Gasto, Aparatología, Ayudantía, Total prestación). Se sube cada mes indicando su vigencia.
#   · Valores por unidades: la tabla «Valor en unidades» (código → unidades del cirujano por tipo de
#     nomenclador) y la tabla «unidades» (valor de cada unidad, que se carga cada mes con su vigencia).
#     El valor de la prestación es unidades × valor de la unidad.

HOJA_FIJOS, HOJA_UNID = "Valor Fijos", "Valor en unidades"
HOJAS_BASE = (HOJA_FIJOS, HOJA_UNID)

# Especialidad del profesional → tipo de nomenclador de «Valor en unidades» que le corresponde
NOMENCLADOR_POR_ESPECIALIDAD = {
    "UROLOGIA": "NOMENCLADOR UROLOGICO", "GASTROENTEROLOGIA": "NOMENCLADOR GASTROENTEROLOGICO",
    "OTORRINOLARINGOLOGIA": "NOMENCLADOR ORL", "TOCOGINECOLOGIA": "NOMENCLADOR GINECOLOGICO",
    "GINECOLOGIA": "NOMENCLADOR GINECOLOGICO", "OBSTETRICIA": "NOMENCLADOR GINECOLOGICO",
    "HEMATOLOGIA": "NOMENCLADOR HEMATOLOGICO", "ORTOPEDIA Y TRAUMATOLOGIA": "NOMENCLADOR TRAUMATOLOGICO",
    "ONCOLOGIA INFANTIL": "NOMENCLADOR ONCOHEMATOLOGIA-PEDIATRICA", "CIRUGIA GENERAL": "NOMENCLADOR CIRUGIA GRAL",
    "CIRUGIA INFANTIL": "NOMENCLADOR CIRUGIA GRAL", "CIRUGIA DE CABEZA Y CUELLO": "NOMENCLADOR CIRUGIA GRAL",
}


def _texto(v):
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else " ".join(str(v).split())


def _hojas_base(libro):
    """Ubica en el libro las tres tablas de la base, por nombre de solapa o por sus columnas."""
    fij = nom = uni = None
    for nombre, df in libro.items():
        n, cols = sin_tilde(nombre), {sin_tilde(c) for c in df.columns}
        if n == "VALOR FIJOS" or ({"COD", "TOTAL PRESTACION"} <= cols) or ({"CODIGO", "TOTAL PRESTACION"} <= cols):
            fij = df if fij is None else fij
        elif n in ("VALOR EN UNIDADES", "NOMENCLADOR") or "CIRUJANO" in cols:
            nom = df if nom is None else nom
        elif n == "UNIDADES" or ({"TIPO DE UNIDAD", "VALOR"} <= cols) or ({"TIPO DE NOMENCLADOR", "VALOR"} <= cols):
            uni = df if uni is None else uni
    return fij, nom, uni


def es_base(contenido):
    """True si el Excel trae alguna de las tablas de la base de valorización (y no es la grilla por especialidad)."""
    try:
        engine = "openpyxl" if contenido[:2] == b"PK" else "xlrd"
        libro = pd.read_excel(io.BytesIO(contenido), sheet_name=None, engine=engine, nrows=3)
    except Exception:
        return False
    return any(x is not None for x in _hojas_base(libro))


def _variante(nombre_unidad):
    """Categoría a la que corresponde una unidad «variable» (Traumatologia Categoria B, Ginecologia Re Certificados…)."""
    n = sin_tilde(nombre_unidad)
    if "RE CERT" in n or "RECERT" in n:
        return "R"
    m = re.search(r"\b(?:CATEGORIA|CONSULTA)\s+([ABC])\b", n)
    return m.group(1) if m else ""


def importar_base(os_key, contenido, nombre, vigencia=""):
    """Carga la base de valorización. El archivo puede traer las tres tablas juntas o una sola:
    el reporte de valores fijos, la tabla «unidades» o la tabla «Valor en unidades».
    `vigencia` (MMAAAA) se usa para las tablas que no traen su propia columna de período."""
    engine = "openpyxl" if contenido[:2] == b"PK" else "xlrd"
    libro = pd.read_excel(io.BytesIO(contenido), sheet_name=None, engine=engine)
    fij, nom, uni = _hojas_base(libro)
    if fij is None and nom is None and uni is None:
        raise ValueError("El archivo no tiene ninguna de las tablas de la base de valorización "
                         "(Valor Fijos, Valor en unidades, unidades).")
    vigencia = (vigencia or "").strip()
    if vigencia and not re.fullmatch(r"(0[1-9]|1[0-2])\d{4}", vigencia):
        raise ValueError("La vigencia debe tener formato MMAAAA (ej: 112026).")

    def falta_vigencia(tabla):
        raise ValueError(f"La tabla «{tabla}» no trae la columna de período: indicá la vigencia (MMAAAA) al subirla.")

    # ── valores fijos
    fijos = []
    if fij is not None:
        f_cod, f_ar, f_per = _col(fij, "Cod", "Código", "Codigo"), _col(fij, "Arancel"), _col(fij, "Periodo", "Período", "Vigencia")
        f_nom, f_desc = _col(fij, "Nomenclador"), _col(fij, "Descripción", "Descripcion")
        f_tot, f_hon = _col(fij, "Total prestación", "Total prestacion"), _col(fij, "Honorario")
        if f_cod is None or f_tot is None:
            raise ValueError("En los valores fijos faltan las columnas «Cod» y «Total prestación».")
        if f_per is None and not vigencia:
            falta_vigencia("Valor Fijos")
        for r in fij.itertuples(index=False):
            r = dict(zip(fij.columns, r))
            p, v, cod = (_periodo(r[f_per]) if f_per else vigencia), _num(r[f_tot]), limpiar(r[f_cod])
            if p and v is not None and cod:
                fijos.append((p, cod, limpiar(r[f_ar]) if f_ar else "", _texto(r[f_nom]) if f_nom else "",
                              _texto(r[f_desc]) if f_desc else "", round(v, 2), _num(r[f_hon]) if f_hon else None))
    # ── valores de las unidades
    unidades = []        # (periodo, nombre, nomenclador, categoría, valor)
    if uni is not None:
        u_nombre, u_tipo = _col(uni, "Tipo de unidad"), _col(uni, "Tipo de Nomenclador")
        u_per, u_val = _col(uni, "Vigencia", "Mes", "Periodo", "Período"), _col(uni, "Valor")
        if u_tipo is None or u_val is None:
            raise ValueError("En la tabla «unidades» faltan las columnas «Tipo de Nomenclador» y «Valor».")
        if u_per is None and not vigencia:
            falta_vigencia("unidades")
        base = {}        # por período: nomenclador de la última unidad no variable
        for r in uni.itertuples(index=False):
            r = dict(zip(uni.columns, r))
            p, v, tipo = (_periodo(r[u_per]) if u_per else vigencia), _num(r[u_val]), _texto(r[u_tipo])
            nombre_u = _texto(r[u_nombre]) if u_nombre else tipo
            if not (p and v and tipo):
                continue
            if sin_tilde(tipo).startswith("VARIABLE"):      # variante por categoría de la unidad anterior
                unidades.append((p, nombre_u, base.get(p, tipo), _variante(nombre_u) or "?", v))
            else:
                base[p] = tipo
                unidades.append((p, nombre_u, tipo, "", v))
    # ── unidades por prestación
    nomen = None
    if nom is not None:
        c_cod, c_tipo, c_cir = _col(nom, "Código", "Codigo"), _col(nom, "Tipo de nomenclador"), _col(nom, "Cirujano")
        c_desc = _col(nom, "Descripción de Práctica", "Descripción", "Descripcion", "Detalle", "Prestación")
        if c_cod is None or c_tipo is None or c_cir is None:
            raise ValueError("En «Valor en unidades» faltan las columnas «Código», «Tipo de nomenclador» y «Cirujano».")
        nomen = []
        for r in nom.itertuples(index=False):
            r = dict(zip(nom.columns, r))
            cod, cir = limpiar(r[c_cod]), _num(r[c_cir])
            if cod and re.match(r"^\d", cod) and cir:
                nomen.append((cod, _texto(r[c_tipo]), cir, _texto(r[c_desc]) if c_desc else ""))

    per_fijos = {f[0] for f in fijos}
    per_unid = {u[0] for u in unidades}
    if nomen is not None and not per_unid:        # se subió solo «Valor en unidades»: rige para la vigencia indicada
        if not vigencia:
            falta_vigencia("Valor en unidades")
        per_unid = {vigencia}
    orden = lambda p: (p[2:], p[:2])  # noqa: E731
    periodos = sorted(per_fijos | per_unid, key=orden)
    if not periodos:
        raise ValueError("El archivo no trae valores para ningún período.")

    marcas = ",".join("?" * len(HOJAS_BASE))
    n_unid_val = 0
    with db.tx() as c:
        for p in periodos:        # si el período tenía la grilla por especialidad, se reemplaza por la base
            c.execute(f"DELETE FROM valores WHERE os=? AND periodo=? AND hoja NOT IN ({marcas})", (os_key, p) + HOJAS_BASE)
            c.execute("DELETE FROM unidades WHERE os=? AND periodo=? AND hoja<>'unidades'", (os_key, p))
        for p in per_fijos:
            c.execute("DELETE FROM valores WHERE os=? AND periodo=? AND hoja=?", (os_key, p, HOJA_FIJOS))
        c.executemany(
            "INSERT INTO valores(os,periodo,especialidad,seccion,codigo,codigo_prestador,descripcion,categoria,unidades,"
            "tipo_valor,unidad_id,valor,valor_grilla,ayudantes,grupo,hoja,fila) VALUES (?,?,?,?,?,'',?,?,NULL,'fijo',NULL,?,?,'','',?,?)",
            [(os_key, p, nomc or "Valores fijos", nomc, cod, desc, cat, v, hon, HOJA_FIJOS, i)
             for i, (p, cod, cat, nomc, desc, v, hon) in enumerate(fijos, start=2)])
        for p in per_unid:
            # tabla de unidades por prestación: la del archivo o, si no vino, la última cargada
            tabla = nomen
            if tabla is None:
                ult = c.execute("SELECT periodo FROM valores WHERE os=? AND hoja=? ORDER BY substr(periodo,3)||substr(periodo,1,2) DESC LIMIT 1",
                                (os_key, HOJA_UNID)).fetchone()
                tabla = [] if not ult else [(r["codigo"], r["especialidad"], r["unidades"], r["descripcion"]) for r in c.execute(
                    "SELECT DISTINCT codigo, especialidad, unidades, descripcion FROM valores WHERE os=? AND periodo=? AND hoja=?",
                    (os_key, ult["periodo"], HOJA_UNID)).fetchall()]
            if any(u[0] == p for u in unidades):
                c.execute("DELETE FROM unidades WHERE os=? AND periodo=?", (os_key, p))
                for fila, (pp, nombre_u, tipo, cat, v) in enumerate(unidades, start=2):
                    if pp == p:
                        c.execute("INSERT INTO unidades(os,periodo,especialidad,tipo_unidad,valor,origen,hoja,fila,categoria) "
                                  "VALUES (?,?,?,?,?,?,?,?,?)", (os_key, p, tipo, nombre_u, v, "declarada", "unidades", fila, cat))
            us = {}
            for u in c.execute("SELECT * FROM unidades WHERE os=? AND periodo=? ORDER BY id", (os_key, p)).fetchall():
                us.setdefault(u["especialidad"], []).append(dict(u))
            c.execute("DELETE FROM valores WHERE os=? AND periodo=? AND hoja=?", (os_key, p, HOJA_UNID))
            filas = []
            for i, (cod, tipo, cir, desc) in enumerate(tabla, start=2):
                for u in us.get(tipo, []):
                    filas.append((os_key, p, tipo, cod, desc, u["categoria"] or "", cir, u["id"], round(cir * u["valor"], 2), HOJA_UNID, i))
            c.executemany(
                "INSERT INTO valores(os,periodo,especialidad,seccion,codigo,codigo_prestador,descripcion,categoria,unidades,"
                "tipo_valor,unidad_id,valor,valor_grilla,ayudantes,grupo,hoja,fila) VALUES (?,?,?,'',?,'',?,?,?,'unidad',?,?,NULL,'','',?,?)", filas)
            n_unid_val += len(filas)
    return {"filas": len(fijos) + n_unid_val, "periodo": periodos[-1], "periodos": periodos,
            "unidades": len(unidades), "por_unidad": n_unid_val, "fijas": len(fijos),
            "hojas": [h for h in (
                {"hoja": "Valores fijos", "prestaciones": len(fijos), "por_unidad": 0, "fijas": len(fijos), "unidades": 0} if fij is not None else None,
                {"hoja": "Valores por unidades", "prestaciones": n_unid_val, "por_unidad": n_unid_val, "fijas": 0, "unidades": 0} if n_unid_val else None,
                {"hoja": "Unidades", "prestaciones": 0, "por_unidad": 0, "fijas": 0, "unidades": len(unidades)} if uni is not None else None) if h]}


def recalcular_unidades(os_key, periodo):
    """«Actualizar valores por unidades»: valor = unidades × valor de la unidad, para todo el período."""
    with db.tx() as c:
        n = c.execute("UPDATE valores SET valor=ROUND(unidades*(SELECT u.valor FROM unidades u WHERE u.id=valores.unidad_id),2) "
                      "WHERE os=? AND periodo=? AND tipo_valor='unidad' AND unidad_id IS NOT NULL", (os_key, periodo)).rowcount
    return {"recalculadas": n}


# ───────────────────────── valorización ─────────────────────────

class Valorizador:
    """Valoriza con la base de un período (el mes de la prestación; si no está, el anterior más cercano).

    Reglas, contrastadas con la facturación emitida de octubre 2026:
      1. Valores por unidades: si el código está en «Valor en unidades» bajo el nomenclador de la
         especialidad del profesional → unidades × valor de la unidad (con la variante de su categoría:
         Traumatología A / B / C, Ginecología recertificados para R).
      2. Valores fijos del código, en este orden: categoría del profesional con descripción «SMG» →
         valor fijo sin categoría (VF) → categoría del profesional → C si es R y no hay fila R.
         · «Consulta médica en consultorio» (42010100): «consulta clínica médica» para clínica médica,
           medicina interna y geriatría; «consulta médica» para el resto.
         · Radiología (capítulo 34): se factura el honorario, sin el gasto."""

    def __init__(self, os_key, periodo):
        clave = lambda p: (p[2:], p[:2])  # noqa: E731
        marcas = ",".join("?" * len(HOJAS_BASE))
        pers = [r["periodo"] for r in db.q(f"SELECT DISTINCT periodo FROM valores WHERE os=? AND hoja IN ({marcas})",
                                           (os_key,) + HOJAS_BASE)]
        previos = sorted((p for p in pers if clave(p) <= clave(periodo)), key=clave) if periodo else []
        self.periodo = previos[-1] if previos else None
        self.fijos, self.unid = {}, {}
        if self.periodo:
            for f in db.q(f"SELECT * FROM valores WHERE os=? AND periodo=? AND hoja IN ({marcas}) AND valor>0 ORDER BY id",
                          (os_key, self.periodo) + HOJAS_BASE):
                f["_smg"] = str(f["descripcion"] or "").startswith("SMG")
                (self.fijos if f["hoja"] == HOJA_FIJOS else self.unid).setdefault(clave_cod(f["codigo"]), []).append(f)
        self.hay = bool(self.fijos or self.unid)

    def valor(self, cod, categoria, especialidad, desc=""):
        """Devuelve (valor, regla) o (None, motivo)."""
        k, cat, esp = clave_cod(cod), limpiar(categoria), sin_tilde(especialidad)
        # 1 · por unidades, con el nomenclador de la especialidad
        nomen = NOMENCLADOR_POR_ESPECIALIDAD.get(esp)
        filas = [f for f in self.unid.get(k, []) if f["especialidad"] == nomen] if nomen else []
        if filas:
            cats = {f["categoria"] for f in filas}
            efectiva = cat if cat in cats else ("C" if cat == "R" and "C" in cats else "")
            f = next((x for x in filas if x["categoria"] == efectiva), None)
            if f:
                return f["valor"], f"por unidades · {f['especialidad'].replace('NOMENCLADOR ', '').capitalize()}" + (f" · categoría {efectiva}" if efectiva else "")
        # 2 · valores fijos
        g = self.fijos.get(k)
        if not g:
            return None, ("la prestación no está en la base de valores" if self.hay else "")
        if k == CONSULTA_GENERICA:
            clinica = any(x in esp.lower() for x in CLINICOS_42)
            q = [f for f in g if ("clinica" in sin_tilde(f["descripcion"]).lower()) == clinica and f["_smg"]]
            f = next((x for x in q if x["categoria"] == cat), None) or (next((x for x in q if x["categoria"] == "C"), None) if cat == "R" else None)
            if f:
                return f["valor"], "valor fijo · " + ("consulta clínica médica" if clinica else "consulta médica")
        if len(k) == 6 and k.startswith("34"):
            f = next((x for x in g if x["categoria"] == cat and (x["valor_grilla"] or 0) > 0), None)
            if f:
                return f["valor_grilla"], "valor fijo · honorario (radiología)"
        for cond, nombre in ((lambda x: x["categoria"] == cat and x["_smg"], "categoría"),
                             (lambda x: x["categoria"] == "VF" and x["_smg"], "sin categoría"),
                             (lambda x: x["categoria"] == "VF", "sin categoría"),
                             (lambda x: x["categoria"] == cat, "categoría"),
                             (lambda x: cat == "R" and x["categoria"] == "C", "categoría C (no hay valor para R)")):
            f = next((x for x in g if cond(x)), None)
            if f:
                return f["valor"], "valor fijo · " + nombre
        if cat not in ("A", "B", "C", "R"):
            return None, "falta la categoría del profesional"
        return None, "la prestación no tiene valor para la categoría del profesional"


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
    """Un valorizador por período, creado a demanda. Si hay base de valorización cargada (valores fijos y
    valores por unidades) se usa esa; si no, la grilla de valores por especialidad."""

    def __init__(self, os_key):
        self.os, self.cache = os_key, {}

    def valor(self, fecha_ddmmaaaa, cod, categoria, especialidad, periodo_por_defecto="", desc=""):
        p = _periodo(fecha_ddmmaaaa) or periodo_por_defecto
        if p not in self.cache:
            vz = Valorizador(self.os, p)
            self.cache[p] = vz if vz.hay else ValorizadorGrilla(self.os, p)
        vz = self.cache[p]
        v, regla = vz.valor(cod, categoria, especialidad, desc)
        return v, regla, (vz.periodo or p), vz.hay


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
    c_efe = _col(df, "Código de Prestador Efector") or ("efector" if "efector" in df.columns else None)
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
            prof_efector=limpiar_id(r[c_efe]) if c_efe else "",
            prof_cuit=re.sub(r"\D", "", txt(r[c_cuit]).split(".")[0]), condicion_iva=txt(r[c_iva]) if c_iva else "",
            copago=num(r[c_cop]) if c_cop else 0.0))
    return out, repetidas


def iva_y_codigo(resp_fiscal, condicion_iva):
    """IVA del template (0 / 1) y código de obra social, como en el repositorio."""
    rf = str(resp_fiscal or "").strip()
    # IVA = 1 solo si el profesional es Responsable Inscripto (código de IVA 1) y el afiliado es Gravado
    iva = 1 if (rf.lower() == "responsable inscripto" and str(condicion_iva or "").strip().lower() != "exento") else 0
    return iva, ("11062" if rf == "Responsable Inscripto" else "11060")
