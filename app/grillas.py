"""Extracción y normalización de las grillas de valores.

Cada obra social entrega un Excel con una solapa por especialidad y cada solapa
tiene su propio armado. Todas se llevan a dos tablas:

  unidades  → los valores por unidad (los que cambian mes a mes):
              especialidad · tipo de unidad · valor · período
  valores   → una fila por prestación:
              código · descripción · especialidad · cantidad de unidades (N/A si
              es valor fijo) · valor · tipo de valor (fijo / por unidad)

El "factor de normalización" es el valor de la unidad de cada solapa o sección:
una prestación es "por unidad" cuando su valor es unidades × valor de la unidad.
Las unidades salen de una columna (UQ, Unidades), de la tabla de niveles o
complejidades de la solapa, o de dividir el valor por el valor de la unidad.
"""
import io
import re
import unicodedata
from collections import Counter

import pandas as pd

from . import db

HOJAS_GENERALES = {"grilla", "aranceles generales", "consultas y especialidades", "hoja1", "sheet1"}

_RE_NUM = re.compile(r"^-?\d+(\.\d+)?$")
_RE_FECHA = re.compile(r"^(\d{4})-(\d{2})-(\d{2})( 00:00:00)?$")
_RE_COD = re.compile(r"^\d[\d.]{2,}\.?\s?[A-Za-z]{0,3}\d?$")
_RE_COD_INICIO = re.compile(r"^(\d{5,8})\s+(\S.*)$")
_RE_GRUPO = re.compile(r"^(complejidad|nivel|grupo|modulo|módulo)\s*[\"“”']?\s*([0-9]{1,2}[a-z]?|[ivx]{1,4}|[a-d][0-9]?)\b", re.I)
_RE_CAT = re.compile(r"^(?:(?:total|valor|arancel|cat|categoria)\.?\s*)?([abc])$")
_RE_UNIDAD_GENERAL = re.compile(
    r"^(unidad|valor (de )?(la )?unidad|galeno|gastos?|otros gastos|hon ?y ga(s)?tos|nomenclador de .* valor)\b|\buq\b")
_ESPEC = re.compile(
    r"infectolog|nutrici|reumatolog|otorrino|\borl\b|cardio|imagen|resonanc|gastro|onco|hemato|neumono|neurolog|"
    r"fonoaud|neonat|oftalmo|dolor|anatom|traumato|ortoped|columna|\bmama\b|gineco|tocogine|urolog|urogine|cirug|"
    r"neurocir|pediatr|clinic|dermato|kinesio|psiq|psico|alerg|endocrin|nefro|diabet|laborator|bioquim|maxilo|"
    r"plastica|anestes|terapia|guardia|vascular|torax|flebo|procto|mastolog|obstet|genetic|consultas")
ROMANOS = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}


def norm(v):
    t = str(v or "").strip().lower()
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[.,:;()/\\_\-\"'°º*]+", " ", t).split())


def celda(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = " ".join(str(v).split())
    return "" if s.lower() in ("nan", "nat", "none") else s


def es_num(s):
    return bool(_RE_NUM.match(s))


def periodo_de_fecha(s):
    m = _RE_FECHA.match(s)
    if not m or not (2015 <= int(m.group(1)) <= 2040):
        return None
    a, mes, dia = m.group(1), int(m.group(2)), int(m.group(3))
    if dia != 1 and mes == 1 and dia <= 12:      # 01/09 leído como 9 de enero
        mes = dia
    return f"{mes:02d}{a}"


def clave_periodo(p):
    return (p[2:], p[:2])


def limpiar_codigo(s):
    """Excel convierte códigos como 03.08.01 en fechas: se reconstruyen."""
    s = (s or "").strip()
    m = _RE_FECHA.match(s)
    if m:
        yy, mm, dd = m.group(1)[2:], m.group(2), m.group(3)
        return f"{yy}.{mm}.{dd}" if int(yy) > 31 else f"{mm}.{dd}.{yy}"
    return "" if s in ("-", "S/N", "s/n", "no esta") else s


def parece_codigo(s):
    return bool(s) and (bool(_RE_FECHA.match(s)) and periodo_de_fecha(s) is None or bool(_RE_COD.match(s))
                        or bool(re.match(r"^\d{5,8}\s+RE\d$", s)))


# ───────────────────────── roles de columnas ─────────────────────────

def rol_de(texto):
    """Rol de una celda de encabezado, o None."""
    n = norm(texto)
    if not n or len(n) > 34 or es_num(texto):
        return None
    if re.match(r"^cod(igo|igos)?\b", n):
        if re.search(r"\bnn\b", n):
            return "otro"
        return "cod_pp" if re.search(r"prest|\bpp\b", n) else "cod"
    if n in ("avalian", "galeno", "sancor", "prestador"):
        return "otro"
    if n in ("descripcion", "concepto", "conceptos", "nomenclador", "especialidades", "practica", "practicas",
             "capitulo practica", "prestacion", "prestaciones", "prestacion cirujano", "prestaciones a valor fijo"):
        return "desc"
    m = re.match(r"^cirujano ([abc])$", n)
    if m:
        return "cat_" + m.group(1).upper()
    if n in ("calculo valor honorario", "honorarios cx certificados"):
        return "valor"
    if n == "honorarios cx re certificados":
        return "valor_R"                   # segunda columna de valor: profesionales recertificados
    if n == "u cir":
        return "unid"
    if n == "u ayu":
        return "otro"
    if re.match(r"^(nivel|niveles|complejidad|complejidades|comp|compl)$", n) or n.startswith("complejidad unidades"):
        return "nivel"
    m = re.match(r"^hon(orarios?)? cat ([abc])$", n)
    if m:
        return "cat_" + m.group(2).upper()
    if re.match(r"^ay(udantes?)? cat [abc]$", n):
        return "otro"
    if re.search(r"ayud", n):
        if re.match(r"^(n |cant(idad)? (de )?)?ayudantes?( \d+ ?%?)?$", n):
            return "ayud"
        return "otro"                      # valor / honorario / unidades del ayudante: no es el valor de la prestación
    if n in ("uq", "uhp", "unidades", "unidad", "cant unidades", "cantidad unidades", "u quirurgicas", "un qx",
             "unidades quirurgicas", "unidad cirujano", "unidades cirujano", "unid quir"):
        return "unid"
    if re.match(r"^(valor|valores|valor especialista|cirujano|honorario cirujano|honorarios cirujano|"
                r"honorarios profesional|hon cirujano|importe)$", n):
        return "valor"
    if n == "arancel":
        return "arancel"
    if n == "total":
        return "total"
    m = _RE_CAT.match(n)
    if m:
        return "cat_" + m.group(1).upper()
    return None


def _rotulo_unidad(texto):
    n = norm(texto)
    return bool(re.search(r"\b(valor|v) (de )?(la )?unid", n) or n in ("valor uq", "unidad", "uq")
                or n.startswith("unidad de practicas") or n.startswith("valor unidad"))


def nombre_unidad(rotulo, hoja):
    n = norm(rotulo)
    if "endosc" in n:
        return "Unidad endoscópica"
    if "quir" in n or "uq" in n.split() or "cirujano" in n:
        return "Unidad quirúrgica (UQ)"
    if "uhp" in n.split():
        return "Unidad UHP"
    if "practica" in n or "consulta" in n:
        return "Unidad de prácticas/consultas"
    return "Unidad"


# ───────────────────────── una solapa ─────────────────────────

class Hoja:
    def __init__(self, nombre, filas, periodo, general):
        self.nombre, self.filas, self.periodo, self.general = nombre, filas, periodo, general
        self.ncols = max((len(f) for f in filas), default=0)
        self.unidades, self.prest = [], []
        self.niveles = {}
        self.nivel_valor = {}      # complejidad → valor fijo (tablas "Complejidad 1 … $")
        self._periodos()

    # columnas con una fecha de vigencia arriba: se usa la del período pedido
    def _periodos(self):
        self.col_per, self.mascara, self.fila_fecha = None, set(), -1
        por_fila = {}
        for i, f in enumerate(self.filas[:14]):
            for j, v in enumerate(f):
                p = periodo_de_fecha(v)
                if p:
                    por_fila.setdefault(i, {})[j] = p
        if not por_fila:
            return
        # si hay varias filas con fechas (bloques), manda la que tiene más columnas
        i, cols = max(por_fila.items(), key=lambda kv: len(kv[1]))
        previas = [(clave_periodo(p), j) for j, p in cols.items() if clave_periodo(p) <= clave_periodo(self.periodo)]
        if not previas:
            previas = [(clave_periodo(p), j) for j, p in cols.items()]
        mejor = max(k for k, _ in previas)
        self.col_per = min(j for k, j in previas if k == mejor)
        self.fila_fecha = i
        self.mascara = {j for j in cols if j != self.col_per}
        # columnas "pareja" entre vigencias (cirujano | ayudante): se ignoran las que siguen a una vigencia vieja
        orden = sorted(cols)
        for a, b in zip(orden, orden[1:] + [self.ncols]):
            if a != self.col_per:
                self.mascara.update(range(a, b))

    def nums(self, f, excluir=()):
        return [(j, float(v)) for j, v in enumerate(f)
                if j not in self.mascara and j not in excluir and es_num(v) and float(v) != 0]

    def extraer(self):
        roles = {}            # rol -> columna
        cats = {}             # categoría -> columna
        modo_niveles = None   # (col_nivel, col_unid)
        activos = []          # unidades declaradas vigentes en la sección
        hubo_datos = False
        seccion, especialidad = "", ("" if self.general else self.nombre)
        nivel_actual, padre = None, None
        cat_bloque = None

        def declarar(rotulo, valor, fila, origen="declarada"):
            nonlocal activos, hubo_datos
            if valor <= 0:
                return
            if hubo_datos:
                activos, hubo_datos = [], False
            tipo = nombre_unidad(rotulo, self.nombre)
            cat = ""
            if re.search(r"\brec(ert\w*)?\b", norm(rotulo)):
                tipo, cat = tipo + " · recertificados", "R"
            elif "ayud" in norm(rotulo):
                tipo += " · ayudante"
            elif any(u["tipo"] == tipo and "ayud" not in u["tipo"] for u in activos):
                tipo += " · ayudante"      # segunda "unidad cirujano" de la misma sección: es la del ayudante
            u = dict(especialidad=especialidad or self.nombre, tipo=tipo, valor=valor, origen=origen,
                     hoja=self.nombre, fila=fila + 1, n=0, cat=cat)
            self.unidades.append(u)
            activos.append(u)

        for i, f in enumerate(self.filas):
            f = f + [""] * (self.ncols - len(f))
            textos = [(j, v) for j, v in enumerate(f) if v and v != "-" and not es_num(v) and not _RE_FECHA.match(v)]
            no_vacias = [(j, v) for j, v in enumerate(f) if v and j not in self.mascara and v not in ("0", "0.0", "-")]
            if not no_vacias:
                continue
            primero = norm(no_vacias[0][1])
            if primero in ("nota", "notas", "observaciones") or primero.startswith("vigencia"):
                continue

            # ── fila de categorías sueltas (A | B | C) bajo "Especialista" / "Ayudante"
            letras = [(j, v.upper()) for j, v in enumerate(f) if v.upper() in ("A", "B", "C")]
            if len(letras) >= 3 and len(textos) == len(letras):
                arriba = self.filas[i - 1] + [""] * self.ncols if i else []
                bloques, rot = [], ""
                for j, l in letras:
                    if arriba and arriba[j]:
                        rot = norm(arriba[j])
                    if l == "A":
                        bloques.append([rot, {}])
                    if bloques:
                        bloques[-1][1][l] = j
                esp = [b for b in bloques if "ayud" not in b[0] and len(b[1]) == 3]
                if esp:
                    cats = esp[-1][1]
                    cat_bloque = i
                    self.mascara = set(range(self.ncols)) - set(cats.values()) - {0, 1, 2}
                continue
            if cat_bloque is not None and i == cat_bloque + 1 and cats:
                vals = {c: float(f[j]) for c, j in cats.items() if es_num(f[j])}
                if len(vals) == len(cats) and all(v > 50 for v in vals.values()):
                    for c, v in vals.items():
                        declarar(f"unidad quirurgica", v, i)
                        self.unidades[-1]["tipo"] = f"Unidad quirúrgica (UQ) · categoría {c}"
                        self.unidades[-1]["cat"] = c
                    continue

            mcat = re.fullmatch(r"cat(egoria)? ([abc])", norm(textos[0][1])) if len(textos) == 1 else None
            if mcat:
                v = [x for _, x in self.nums(f) if x > 50]
                if v:
                    declarar("unidad", v[0], i)
                    self.unidades[-1]["tipo"] = f"Unidad · categoría {mcat.group(2).upper()}"
                    self.unidades[-1]["cat"] = mcat.group(2).upper()
                continue

            # ── valor de unidad con rótulo ("VALOR DE UNIDAD | 14067,01", "V. UNIDAD" con el número debajo)
            decl = False
            for j, v in textos:
                if _rotulo_unidad(v) and rol_de(v) != "unid":
                    der = [x for k, x in self.nums(f) if k > j and x > 50]
                    if not der and i + 1 < len(self.filas):
                        sig = self.filas[i + 1] + [""] * self.ncols
                        der = [float(sig[j])] if es_num(sig[j]) and float(sig[j]) > 50 else []
                    if der:
                        declarar(v, der[0], i)
                        decl = True
                    break
            if decl and not any(parece_codigo(v) for v in f[:2]) and len([r for _, v in textos if (r := rol_de(v))]) < 3:
                for j, v in textos:          # la misma fila puede titular columnas ("… | 12323,45 | Cód. Presta")
                    if rol_de(v) in ("cod", "cod_pp"):
                        roles[rol_de(v)] = j
                continue

            # ── encabezado: define qué es cada columna (puede repetirse por sección)
            enc = [(j, rol_de(v)) for j, v in textos if j not in self.mascara or rol_de(v)]
            enc = [(j, r) for j, r in enc if r]
            grandes = [x for _, x in self.nums(f) if x >= 1000]
            reales = [e for e in enc if e[1] != "otro"]
            if reales and (len(reales) >= 2 or (reales[0][1] in ("nivel", "unid") and len(textos) <= 3)
                           or len(enc) == len(textos)) and (len(grandes) <= 1 or len(enc) == len(textos)):
                nuevos = {}
                for j, r in enc:
                    if r.startswith("cat_"):
                        cats[r[4:]] = j
                    elif r == "cod" and "cod" in nuevos and "cod_pp" not in nuevos:
                        nuevos["cod_pp"] = j
                    elif r != "otro" and r not in nuevos:
                        nuevos[r] = j
                if self.col_per is not None and any(j == self.col_per and r in ("nivel", "unid", "cod", "cod_pp", "desc", "ayud")
                                                    for r, j in nuevos.items()):
                    self.col_per, self.mascara = None, set()     # la fecha era solo la vigencia, no una columna
                for r, j in nuevos.items():
                    for viejo in [k for k, c in roles.items() if c == j]:
                        del roles[viejo]
                    roles[r] = j
                if any(r.startswith("cat_") for _, r in enc):
                    roles.pop("valor", None), roles.pop("total", None)
                elif "valor" in nuevos or "total" in nuevos or "arancel" in nuevos:
                    cats = {} if cat_bloque is None else cats
                # número en la fila de encabezado = valor de la unidad de esa solapa
                cand = [(k, x) for k, x in self.nums(f) if x > 50]
                if self.col_per is not None:
                    cand = [(k, x) for k, x in cand if k == self.col_per]
                if cand and not decl:
                    rot = next((v for j, v in textos if rol_de(v) == "unid"), "unidad")
                    declarar(rot, cand[0][1], i)
                modo_niveles = None
                if "nivel" in nuevos and "unid" in nuevos and "desc" not in roles and "cod" not in nuevos:
                    modo_niveles = (nuevos["nivel"], nuevos["unid"])
                elif "nivel" in nuevos and "unid" in nuevos and "desc" not in nuevos and "cod" not in nuevos \
                        and not self.niveles:
                    modo_niveles = (nuevos["nivel"], nuevos["unid"])
                # un encabezado puede ser también título de sección ("0301 | OPERACION EN EL OIDO | NIVEL")
                tit = [v for j, v in textos if not rol_de(v) and not parece_codigo(v)]
                if tit and len(tit[0]) <= 90:
                    seccion = tit[0]
                padre, nivel_actual = None, None
                continue

            # ── número suelto debajo de la fecha de vigencia = valor de la unidad
            if self.col_per is not None and self.fila_fecha < i <= self.fila_fecha + 2 and len(no_vacias) == 1 \
                    and es_num(f[self.col_per]) and float(f[self.col_per]) > 50:
                declarar("unidad", float(f[self.col_per]), i)
                continue

            # ── tabla de niveles / complejidades → unidades
            if modo_niveles:
                cn, cu = modo_niveles
                nv = norm(f[cn]) if cn < len(f) else ""
                if re.fullmatch(r"\d{1,2}[a-z]?", nv) and es_num(f[cu]):
                    self.niveles[nv] = float(f[cu])
                    continue
                modo_niveles = None

            excl = {roles.get(k) for k in ("cod", "cod_pp", "nivel", "unid", "ayud")} - {None}

            # ── código y descripción
            cod = limpiar_codigo(f[roles["cod"]]) if "cod" in roles else ""
            cpp = limpiar_codigo(f[roles["cod_pp"]]) if "cod_pp" in roles else ""
            if "cod" not in roles:
                for j in (0, 1):
                    if j == roles.get("cod_pp"):
                        continue
                    if j < len(f) and parece_codigo(f[j]) and not (es_num(f[j]) and float(f[j]) < 1000):
                        cod = limpiar_codigo(f[j])
                        excl.add(j)
                        break
            elif cod and not parece_codigo(f[roles["cod"]]) and not re.match(r"^\d", cod):
                cod = ""
            if cpp and " " in cpp and len(cpp) > 12 and not parece_codigo(f[roles["cod_pp"]]):
                excl.discard(roles["cod_pp"])      # la columna titulada "Cod." trae en realidad la descripción
                cpp = ""
            desc_cands = [(j, v) for j, v in textos if j not in excl and j not in self.mascara
                          and limpiar_codigo(v) not in (cod, cpp) and not parece_codigo(v)
                          and norm(v) not in ("honorarios", "gastos", "honorarios y gastos", "horarios")]
            grupo_txt = next((v for _, v in desc_cands if _RE_GRUPO.match(norm(v))), None)
            if not grupo_txt and "nivel" in roles and _RE_GRUPO.match(norm(f[roles["nivel"]])):
                grupo_txt = f[roles["nivel"]]
            if "desc" in roles and f[roles["desc"]] and not es_num(f[roles["desc"]]):
                desc = f[roles["desc"]]
            else:
                otros = [v for _, v in desc_cands if v != grupo_txt and len(v) >= 3] or ([grupo_txt] if grupo_txt else [])
                desc = otros[0] if otros else ""      # la descripción es el primer texto de la fila
            m = _RE_COD_INICIO.match(desc)
            if m and not cod:
                cod, desc = m.group(1), m.group(2)
            re1 = re.match(r"^(\d{5,8})\s+RE\d$", cod)
            if re1:
                cod = re1.group(1)

            # ── nivel, unidades, ayudantes
            nivel = norm(f[roles["nivel"]]) if "nivel" in roles else ""
            mg = _RE_GRUPO.match(nivel)
            if mg:
                nivel = str(ROMANOS.get(mg.group(2).lower(), mg.group(2).lower()))
            unid = None
            if "unid" in roles and es_num(f[roles["unid"]]) and float(f[roles["unid"]]) > 0:
                unid = float(f[roles["unid"]])
            if unid is None:
                mu = next((re.fullmatch(r"(\d+(?:\.\d+)?) unidades?", norm(v).replace(" 0 ", " ")) for _, v in textos
                           if re.fullmatch(r"\d+(\.\d+)? unidades?", norm(v))), None)
                if mu:
                    unid = float(mu.group(1))
                    textos = [(j, v) for j, v in textos if not re.fullmatch(r"\d+(\.\d+)? unidades?", norm(v))]
            ayud = f[roles["ayud"]] if "ayud" in roles and es_num(f[roles["ayud"]]) and float(f[roles["ayud"]]) <= 6 else ""

            # ── valores
            nums = self.nums(f, excl)
            por_cat = {c: float(f[j]) for c, j in cats.items() if j < len(f) and es_num(f[j]) and float(f[j]) > 0}
            vg = None
            if not por_cat:
                if self.col_per is not None and not (roles.get("total") == self.col_per and "valor" in roles):
                    vg = float(f[self.col_per]) if es_num(f[self.col_per]) else None
                else:
                    for r in ("valor", "arancel", "total"):
                        if r in roles and es_num(f[roles[r]]):
                            vg = float(f[roles[r]])
                            break
                    if vg is None and not any(r in roles for r in ("valor", "arancel", "total")):
                        cand = [x for _, x in nums if x >= 50]
                        vg = cand[0] if cand else None
                if vg is not None and vg <= 0:
                    vg = None

            # ── títulos, grupos y renglones "hijos"
            solo_texto = not nums and not por_cat and unid is None
            g = _RE_GRUPO.match(norm(grupo_txt or desc))
            if solo_texto and not cod and not cpp:
                if g and (grupo_txt or desc) and len(norm(grupo_txt or desc)) <= 40 and not nivel:
                    n = g.group(2).lower()
                    nivel_actual = str(ROMANOS.get(n, n))
                    if desc == (grupo_txt or desc):
                        padre = None
                        continue
                titulo = len(textos) == 1 and len(desc) <= 90
                es_esp = titulo and self.general and bool(_ESPEC.search(norm(desc))) and (roles or self.prest or i > 3) \
                    and not norm(desc).startswith(("valor", "unidad"))
                nota = re.match(r"^(\*|\d+\)|son |los |las |se |el |la |en |cuando |valida |nota|incluye |no |para |"
                                r"cirugias incluidas|patologia multiple)", norm(desc) + " ") or desc.startswith("*")
                if padre and desc and len(desc) > 3 and not rol_de(desc) and not es_esp and not nota \
                        and not (titulo and self.general and desc == desc.upper() and len(desc) > 25):
                    for p in padre:
                        self.prest.append({**p, "descripcion": desc[:300], "grupo": p["grupo"] or p["descripcion"],
                                           "fila": i + 1})
                    continue
                if desc and len(textos) <= 2 and len(desc) <= 90 and not nota \
                        and not _RE_UNIDAD_GENERAL.search(norm(desc)):
                    seccion = desc
                    if es_esp:
                        limpio = re.sub(r"^(nomenclador( quirurgico)?( de( la)?)?|practicas?( en| de)?)\s+", "", desc.strip(), flags=re.I)
                        especialidad = (limpio or desc).strip(" :").capitalize()
                        # cada especialidad define sus unidades y niveles; código, descripción y valor se conservan
                        roles = {k: v for k, v in roles.items() if k not in ("unid", "nivel", "ayud")}
                        cats, activos, hubo_datos = {}, [], False
                        self.niveles = {}
                    padre, nivel_actual = None, None
                continue
            if not desc and not cod and not cpp:
                continue

            # ── renglones de la solapa general que en realidad son valores de unidad
            if re.match(r"^\d+\)", desc):
                continue
            if not self.general and not cod and not cpp and vg and unid is None and not nivel and len(nums) == 1:
                nd = norm(desc)
                ultima = self.unidades[-1] if self.unidades else None
                if nd.startswith(("unidad", "valor unidad", "valor de unidad")):
                    declarar(desc, vg, i)
                    continue
                if "recertif" in nd and ultima and ultima["fila"] == i and vg < ultima["valor"] * 1.6:
                    declarar("unidad recertificados", vg, i)
                    self.unidades[-1]["tipo"] = ultima["tipo"].split(" · ")[0] + " · recertificados"
                    continue
            if self.general and not cod and not cpp and vg and unid is None and not nivel \
                    and _RE_UNIDAD_GENERAL.search(norm(desc)) \
                    and "interconsulta" not in norm(desc):
                self.unidades.append(dict(especialidad="General", tipo=desc[:120],
                                          valor=vg, origen="general", hoja=self.nombre, fila=i + 1, n=0))
                continue

            if unid is None:
                nv = nivel or (nivel_actual if "nivel" not in roles or not f[roles["nivel"]] else "")
                if g and not nivel:
                    n = g.group(2).lower()
                    nv = str(ROMANOS.get(n, n))
                if nv and nv in self.niveles:
                    unid = self.niveles[nv]
            if g and vg and not cod and not cpp and unid is None and not por_cat:
                n = g.group(2).lower()
                self.nivel_valor[str(ROMANOS.get(n, n))] = vg
            grupo_nivel = ""
            if vg is None and unid is None and not por_cat:
                nv = nivel or nivel_actual or ""
                if nv in self.nivel_valor and (cod or cpp):
                    vg, grupo_nivel = self.nivel_valor[nv], f"Complejidad {nv}"
                else:
                    continue
            # con unidades pero sin valores, bajo unidades por categoría: una fila por categoría
            cats_act = [u for u in activos if u.get("cat") in ("A", "B", "C")]
            if unid is not None and vg is None and not por_cat and cats_act:
                por_cat = {u["cat"]: None for u in cats_act}

            cat = "R" if (re1 or re.search(r"\dR$", cod) or re.search(r"\dR$", cpp) or "recertif" in norm(desc)) else ""
            segundo = None
            if not por_cat and vg and self.col_per is not None and not any(r in roles for r in ("valor", "total", "unid")):
                resto = [x for j, x in nums if j > self.col_per and x >= 50]
                if resto and abs(resto[0] - vg) > 0.01:
                    segundo = resto[0]
            base = dict(especialidad=especialidad or self.nombre, seccion=seccion, codigo=cod, codigo_prestador=cpp,
                        descripcion=(desc or grupo_txt or "")[:300], categoria=cat, unidades=unid, ayudantes=ayud,
                        grupo=(grupo_txt if grupo_txt and grupo_txt != desc else "") or grupo_nivel, fila=i + 1,
                        hoja=self.nombre,
                        valor_grilla=vg, _activos=list(activos))
            nuevas = []
            if por_cat:
                for c, v in por_cat.items():
                    nuevas.append({**base, "categoria": c, "valor_grilla": v})
            else:
                nuevas.append(base)
                jr = roles.get("valor_R")
                if jr is not None and es_num(f[jr]) and float(f[jr]) > 0:
                    nuevas.append({**base, "categoria": "R", "valor_grilla": float(f[jr])})
                if segundo:
                    nuevas.append({**base, "valor_grilla": segundo, "_segundo": True})
            self.prest.extend(nuevas)
            hubo_datos = True
            padre = nuevas if (g or grupo_txt) else None
            if not (g or grupo_txt):
                padre = None

        self._resolver()

    # ── asigna a cada prestación su unidad y calcula el valor
    def _resolver(self):
        def cerca(a, b):
            return b and abs(a - b) <= max(0.02, abs(b) * 0.0005)

        # 1) con unidades y valor: la unidad declarada que cierre la cuenta
        sin_unidad, descartar = [], []
        for p in self.prest:
            act = [u for u in p.pop("_activos") if "ayudante" not in u["tipo"]]
            if p["categoria"] in ("A", "B", "C"):
                act = [u for u in act if u.get("cat") == p["categoria"]] or [u for u in act if not u.get("cat")]
            u, vg, ok = p["unidades"], p["valor_grilla"], None
            if u and vg:
                ok = next((x for x in act if cerca(u * x["valor"], vg)), None)
                if not ok and u < 10:     # "1.355" unidades: el punto era separador de miles
                    ok = next((x for x in act if cerca(u * 1000 * x["valor"], vg)), None)
                    if ok:
                        p["unidades"] = u = round(u * 1000, 3)
                if not ok:
                    p["_act"] = act
                    sin_unidad.append(p)
            elif u and not vg:
                ok = next((x for x in act if not x.get("cat") or x["cat"] == p["categoria"]), None)
            elif vg and act:
                # sin columna de unidades: se deducen solo si el valor es múltiplo exacto de la unidad
                for x in act:
                    n = vg / x["valor"]
                    if x["valor"] >= 100 and 0.5 <= n <= 3000 and abs(n - round(n * 2) / 2) <= n * 0.00002:
                        ok, p["unidades"] = x, round(n * 2) / 2
                        break
            if ok and ok.get("cat") == "R" and not p["categoria"]:
                p["categoria"] = "R"
            if p.pop("_segundo", False) and not ok:
                descartar.append(id(p))       # segunda columna que no es de ninguna unidad: no se sabe qué es
            p["_u"] = ok
        self.prest = [p for p in self.prest if id(p) not in descartar]
        sin_unidad = [p for p in sin_unidad if id(p) not in descartar]
        # 2) unidades y valor sin declaración que cierre: se infiere el valor de la unidad
        clave = lambda p: (round(p["valor_grilla"] / p["unidades"], 2),  # noqa: E731
                           p["categoria"] if p["categoria"] in ("A", "B", "C") else "")
        for (razon, cat), n in Counter(clave(p) for p in sin_unidad).items():
            if n < 4 or razon < 50:
                continue
            grupo = [p for p in sin_unidad if clave(p) == (razon, cat)]
            esp = Counter(p["especialidad"] for p in grupo).most_common(1)[0][0]
            # si la solapa declara una unidad casi igual, es esa misma con otro redondeo: conserva su nombre
            decl = next((x for x in grupo[0]["_act"] if abs(x["valor"] - razon) <= razon * 0.005), None)
            tipo = decl["tipo"] if decl else "Unidad" + (f" · categoría {cat}" if cat else "")
            if not decl and all(p["categoria"] == "R" for p in grupo):
                tipo += " · recertificados"
            nueva = dict(especialidad=esp, tipo=tipo, valor=razon, origen="deducida", hoja=self.nombre,
                         fila=grupo[0]["fila"], n=0, cat=cat)
            if decl and decl["n"] == 0:
                decl["_reemplazada"] = True
            self.unidades.append(nueva)
            for p in grupo:
                p["_u"] = nueva
        for p in sin_unidad:
            p.pop("_act", None)
        self.unidades = [u for u in self.unidades if not (u.get("_reemplazada") and u["n"] == 0)]
        principales = [u for u in self.unidades if u["origen"] != "general" and "ayudante" not in u["tipo"]
                       and not u.get("cat")]
        for p in self.prest:
            if not p["_u"] and p["unidades"] and not p["valor_grilla"] and len(principales) == 1 and not self.general:
                p["_u"] = principales[0]
            u = p["_u"]
            if u and p["unidades"]:
                p["tipo_valor"] = "unidad"
                p["valor"] = round(p["unidades"] * u["valor"], 2)
                u["n"] += 1
            else:
                p["tipo_valor"], p["_u"] = "fijo", None
                p["valor"] = round(p["valor_grilla"], 2) if p["valor_grilla"] else None
                if p["unidades"] and not p["valor"]:
                    p["tipo_valor"] = "unidad"      # tiene unidades pero la solapa no informa el valor de la unidad
                else:
                    p["unidades"] = None
        self.prest = [p for p in self.prest if p["valor"] or p["tipo_valor"] == "unidad"]
        for u in self.unidades:
            if u["tipo"] == "Unidad" and (self.niveles or re.search(r"\b(cx|cirug|cirujan|quir)", norm(self.nombre))):
                u["tipo"] = "Unidad quirúrgica (UQ)"
        # unidades declaradas que no usó nadie y repiten otra: fuera
        vistas = set()
        limpias = []
        for u in self.unidades:
            k = (u["especialidad"], u["tipo"], round(u["valor"], 2))
            if u["origen"] != "general" and u["n"] == 0 and k in vistas:
                continue
            vistas.add(k)
            limpias.append(u)
        self.unidades = limpias


# ───────────────────────── importación ─────────────────────────

def leer_libro(contenido, nombre):
    if nombre.lower().endswith((".csv", ".txt")):
        texto = contenido.decode("utf-8-sig", errors="replace")
        sep = ";" if texto.split("\n", 1)[0].count(";") >= texto.split("\n", 1)[0].count(",") else ","
        return {"GRILLA": pd.read_csv(io.StringIO(texto), sep=sep, header=None, dtype=str)}
    engine = "openpyxl" if contenido[:2] == b"PK" else "xlrd"
    return pd.read_excel(io.BytesIO(contenido), sheet_name=None, header=None, dtype=str, engine=engine)


def extraer(contenido, nombre, periodo):
    libro = leer_libro(contenido, nombre)
    hojas = []
    for nom, df in libro.items():
        nom = str(nom).strip()
        filas = [[celda(v) for v in fila] for fila in df.values.tolist()]
        h = Hoja(nom, filas, periodo, general=len(libro) == 1 or norm(nom) in HOJAS_GENERALES)
        h.extraer()
        hojas.append(h)
    return hojas


def importar(os_key, periodo, contenido, nombre):
    hojas = extraer(contenido, nombre, periodo)
    total = sum(len(h.prest) for h in hojas)
    con_codigo = sum(1 for h in hojas for p in h.prest if p["codigo"] or p["codigo_prestador"])
    if total < 5 or con_codigo < total * 0.15:
        raise ValueError("El archivo no parece una grilla de valores: casi no tiene prestaciones con código y valor. "
                         "Verificá que no sea el padrón de profesionales u otro archivo.")
    resumen = []
    with db.tx() as c:
        c.execute("DELETE FROM valores WHERE os=? AND periodo=?", (os_key, periodo))
        c.execute("DELETE FROM unidades WHERE os=? AND periodo=?", (os_key, periodo))
        for h in hojas:
            ids = {}
            for u in h.unidades:
                cur = c.execute(
                    "INSERT INTO unidades(os,periodo,especialidad,tipo_unidad,valor,origen,hoja,fila) VALUES (?,?,?,?,?,?,?,?)",
                    (os_key, periodo, u["especialidad"], u["tipo"], round(u["valor"], 4), u["origen"], u["hoja"], u["fila"]))
                ids[id(u)] = cur.lastrowid
            for p in h.prest:
                c.execute(
                    "INSERT INTO valores(os,periodo,especialidad,seccion,codigo,codigo_prestador,descripcion,categoria,"
                    "unidades,tipo_valor,unidad_id,valor,valor_grilla,ayudantes,grupo,hoja,fila) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (os_key, periodo, p["especialidad"], p["seccion"], p["codigo"], p["codigo_prestador"],
                     p["descripcion"], p["categoria"], p["unidades"], p["tipo_valor"],
                     ids.get(id(p["_u"])) if p["_u"] else None, p["valor"], p["valor_grilla"], str(p["ayudantes"] or ""),
                     p["grupo"], p["hoja"], p["fila"]))
            resumen.append({"hoja": h.nombre, "prestaciones": len(h.prest),
                            "por_unidad": sum(1 for p in h.prest if p["tipo_valor"] == "unidad"),
                            "fijas": sum(1 for p in h.prest if p["tipo_valor"] == "fijo"),
                            "unidades": len(h.unidades)})
    return {"filas": total, "periodo": periodo, "hojas": resumen,
            "unidades": sum(len(h.unidades) for h in hojas),
            "por_unidad": sum(r["por_unidad"] for r in resumen), "fijas": sum(r["fijas"] for r in resumen)}


def cambiar_unidad(uid, valor):
    """Cambia el valor de una unidad y recalcula todas las prestaciones que dependen de ella."""
    u = db.q1("SELECT * FROM unidades WHERE id=?", (uid,))
    if not u:
        raise ValueError("Unidad inexistente.")
    if valor <= 0:
        raise ValueError("El valor de la unidad debe ser mayor que cero.")
    with db.tx() as c:
        c.execute("UPDATE unidades SET valor=?, origen=CASE WHEN origen='general' THEN origen ELSE 'modificada' END WHERE id=?",
                  (valor, uid))
        n = c.execute("UPDATE valores SET valor=ROUND(unidades*?,2) WHERE unidad_id=? AND tipo_valor='unidad'",
                      (valor, uid)).rowcount
    return {"antes": u["valor"], "despues": valor, "recalculadas": n, "unidad": u}


def copiar_periodo(os_key, origen, destino):
    """Arma un período nuevo a partir de otro: después solo se cambian los valores de unidad."""
    if db.scalar("SELECT COUNT(*) FROM valores WHERE os=? AND periodo=?", (os_key, destino)):
        raise ValueError(f"Ya hay una grilla cargada para {destino}. Eliminala antes de copiar.")
    us = db.q("SELECT * FROM unidades WHERE os=? AND periodo=?", (os_key, origen))
    if not us and not db.scalar("SELECT COUNT(*) FROM valores WHERE os=? AND periodo=?", (os_key, origen)):
        raise ValueError(f"No hay grilla cargada para {origen}.")
    with db.tx() as c:
        mapa = {}
        for u in us:
            cur = c.execute(
                "INSERT INTO unidades(os,periodo,especialidad,tipo_unidad,valor,origen,hoja,fila) VALUES (?,?,?,?,?,?,?,?)",
                (os_key, destino, u["especialidad"], u["tipo_unidad"], u["valor"], u["origen"], u["hoja"], u["fila"]))
            mapa[u["id"]] = cur.lastrowid
        n = 0
        for v in c.execute("SELECT * FROM valores WHERE os=? AND periodo=? ORDER BY id", (os_key, origen)).fetchall():
            v = dict(v)
            c.execute(
                "INSERT INTO valores(os,periodo,especialidad,seccion,codigo,codigo_prestador,descripcion,categoria,"
                "unidades,tipo_valor,unidad_id,valor,valor_grilla,ayudantes,grupo,hoja,fila) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (os_key, destino, v["especialidad"], v["seccion"], v["codigo"], v["codigo_prestador"], v["descripcion"],
                 v["categoria"], v["unidades"], v["tipo_valor"], mapa.get(v["unidad_id"]), v["valor"], v["valor_grilla"],
                 v["ayudantes"], v["grupo"], v["hoja"], v["fila"]))
            n += 1
    return {"prestaciones": n, "unidades": len(us)}


class Grilla:
    """Búsqueda del valor de una prestación por código (de la obra social o del prestador)."""

    def __init__(self, os_key, periodo):
        self.os = os_key
        periodos = [r["periodo"] for r in db.q("SELECT DISTINCT periodo FROM valores WHERE os=?", (os_key,))]
        previos = sorted([p for p in periodos if clave_periodo(p) <= clave_periodo(periodo)], key=clave_periodo)
        self.periodo = previos[-1] if previos else None
        self.idx = {}
        if self.periodo:
            for f in db.q("SELECT * FROM valores WHERE os=? AND periodo=? AND valor>0 ORDER BY id", (os_key, self.periodo)):
                for cod in (f["codigo"], f["codigo_prestador"]):
                    if cod:
                        self.idx.setdefault(self._k(cod), []).append(f)

    @staticmethod
    def _k(cod):
        c = re.sub(r"[.\s/-]", "", str(cod or "")).upper()
        return c.lstrip("0") or c

    def buscar(self, cod, categoria=""):
        claves = [self._k(cod)]
        if self.os == "AVALIAN" and str(cod).startswith("02") and len(str(cod)) == 8:
            claves.append(self._k(str(cod)[2:]))      # 02420101 → 420101
        cand = next((self.idx[k] for k in claves if k and k in self.idx), None)
        if not cand:
            return None
        cat = (categoria or "").strip().upper()
        exacta = [f for f in cand if f["categoria"] == cat and cat]
        if exacta:
            return exacta[0]
        pref = [f for f in cand if (f["categoria"] == "R") == (cat == "R")]
        return (pref or cand)[0]

    def valor(self, cod, categoria=""):
        f = self.buscar(cod, categoria)
        return f["valor"] if f else None
