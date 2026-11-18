"""Consulta de la condición fiscal de los profesionales en ARCA, a través de Arcanum.

Arcanum es el gateway de ARCA que ya usa el Portal de Cuentas a Pagar. Se consulta igual que ahí:

    GET {ARCANUM_URL}/api/padron/a5/{cuit}?cuit={ARCANUM_CUIT}      cabecera X-API-Key: {ARCANUM_API_KEY}

y responde { ok, alcance, cuit, datos }, donde «datos» es la Constancia de Inscripción (a5): datosGenerales,
datosMonotributo o datosRegimenGeneral. Variables de entorno (las mismas que en el portal):

  ARCANUM_URL      dirección de Arcanum. En el mismo proyecto de Easypanel: http://arcanum:8094
  ARCANUM_API_KEY  la clave configurada en Arcanum
  ARCANUM_CUIT     CUIT del certificado cargado en Arcanum (el representante que hace la consulta)
"""
import json
import os
import re
import urllib.error
import urllib.request


class ArcaError(ValueError):
    def __init__(self, mensaje, estado=None):
        super().__init__(mensaje)
        self.estado = estado


def _cfg():
    return (os.environ.get("ARCANUM_URL", "").strip().rstrip("/"), os.environ.get("ARCANUM_API_KEY", "").strip(),
            re.sub(r"\D", "", os.environ.get("ARCANUM_CUIT", "") or os.environ.get("EMPRESA_CUIT", "")))


def configurado():
    return all(_cfg())


def _lista(x):
    return x if isinstance(x, list) else ([x] if x else [])


def condicion_fiscal(datos):
    """Responsabilidad fiscal como la usa el padrón: Monotributo, Responsable Inscripto o Exento.
    Devuelve '' si la constancia no alcanza para decidir (no se toca lo cargado)."""
    if datos.get("datosMonotributo"):
        return "Monotributo"
    rg = datos.get("datosRegimenGeneral")
    if rg:
        ids, descs = set(), set()
        for i in _lista(rg.get("impuesto")):
            if isinstance(i, dict):
                ids.add(str(i.get("idImpuesto", "")).strip())
                descs.add(str(i.get("descripcionImpuesto", "")).strip().upper())
        # 30 = IVA (inscripto) · 32 = IVA exento. «IVA EXENTO» también contiene «IVA»: se mira el nombre completo.
        if "30" in ids or "IVA" in descs:
            return "Responsable Inscripto"
        if "32" in ids or "IVA EXENTO" in descs:
            return "Exento"
    return ""


def consultar(cuit):
    """Datos del contribuyente según ARCA. Lanza ArcaError si no se puede consultar."""
    url, clave, rep = _cfg()
    if not (url and clave and rep):
        raise ArcaError("La conexión con ARCA no está configurada. El administrador debe cargar ARCANUM_URL, "
                        "ARCANUM_API_KEY y ARCANUM_CUIT en las variables de entorno del servicio.")
    cuit = re.sub(r"\D", "", str(cuit or ""))
    if len(cuit) != 11:
        raise ArcaError("CUIT inválido: debe tener 11 dígitos.")
    if not re.match(r"^https?://", url):
        raise ArcaError("ARCANUM_URL debe empezar con http:// o https://.")
    pedido = urllib.request.Request(f"{url}/api/padron/a5/{cuit}?cuit={rep}", headers={"X-API-Key": clave})
    try:
        with urllib.request.urlopen(pedido, timeout=15) as r:
            data = json.loads(r.read(2_000_000).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ArcaError("CUIT no encontrado en ARCA.", 404) from None
        if e.code in (401, 403):
            raise ArcaError("Arcanum rechazó la clave (ARCANUM_API_KEY).", e.code) from None
        raise ArcaError(f"Arcanum respondió con error {e.code}.", e.code) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ArcaError("No se pudo conectar con Arcanum. Verificá que esté corriendo y la dirección ARCANUM_URL.") from None
    except ValueError:
        raise ArcaError("Arcanum devolvió una respuesta que no se pudo leer.") from None
    raiz = (data.get("datos") or data.get("persona") or data) if isinstance(data, dict) else {}
    if not isinstance(raiz, dict):
        raiz = {}
    g = raiz.get("datosGenerales") or {}
    nombre = g.get("razonSocial") or ", ".join(x for x in (g.get("apellido"), g.get("nombre")) if x)
    error = raiz.get("errorConstancia") or {}
    motivo = "; ".join(str(x) for x in _lista(error.get("error"))) if isinstance(error, dict) else ""
    mono = raiz.get("datosMonotributo") or {}
    cat = mono.get("categoriaMonotributo") if isinstance(mono, dict) else None
    if isinstance(cat, dict):
        cat = cat.get("descripcionCategoria") or cat.get("idCategoria")
    return {"cuit": cuit, "resp_fiscal": condicion_fiscal(raiz), "razon_social": nombre or "",
            "estado": str(g.get("estadoClave") or ""), "categoria_monotributo": str(cat or "").split(" ")[0],
            "observacion": motivo[:300]}
