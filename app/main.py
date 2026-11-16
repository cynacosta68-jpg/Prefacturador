"""API + interfaz. Un solo servicio (una sola réplica: el bot corre en un hilo)."""
import io
import os
import re
import threading
import time
import traceback
import uuid
from datetime import datetime, date
from urllib.parse import quote

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import db, logic, seguridad
from .seguridad import auditar
from .evweb_bot import ejecutar_extractor, generar_rangos_9_dias

COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() in ("1", "true", "si", "yes")
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "40"))
HEADLESS = os.environ.get("HEADLESS", "true").lower() in ("1", "true", "si", "yes")
LINKS = {
    "GALENO": os.environ.get("LINK_GALENO", "https://www.galeno.com.ar/"),
    "AVALIAN": os.environ.get("LINK_AVALIAN", "https://online.avalian.com/prestador/ingreso"),
    "SANCOR": os.environ.get("LINK_SANCOR", "https://autogestionprestadores.sancorsalud.com.ar/#/login"),
}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
STATIC = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="Facturación Obras Sociales", docs_url=None, redoc_url=None, openapi_url=None)
JOBS = {}
_bot_lock = threading.Lock()
_intentos = {}


@app.on_event("startup")
def _inicio():
    db.conn()
    seguridad.sembrar_admin()
    seguridad.iniciar_backups()


@app.exception_handler(ValueError)
async def _valor(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.middleware("http")
async def _cabeceras(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = ("default-src 'self'; object-src 'none'; base-uri 'none'; "
                                               "form-action 'self'; frame-ancestors 'none'")
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    if COOKIE_SECURE:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ───────────────────────── sesión ─────────────────────────

def _ip(request: Request):
    return request.client.host if request.client else ""


def usuario_actual(request: Request):
    ses = seguridad.sesion(request.cookies.get("sesion", ""))
    if not ses:
        raise HTTPException(401, "Sesión vencida. Volvé a ingresar.")
    # CSRF: las operaciones que modifican exigen la cabecera que solo pone la interfaz
    if request.method not in ("GET", "HEAD") and request.headers.get("x-requested-with") != "app":
        raise HTTPException(403, "Solicitud no permitida.")
    libres = ("/api/me", "/api/mi-clave", "/api/logout")
    if ses["debe_cambiar"] and request.url.path not in libres:
        raise HTTPException(403, "Tenés que cambiar tu contraseña antes de continuar.")
    return {"usuario": ses["usuario"], "nombre": ses["nombre"], "rol": ses["rol"], "ip": _ip(request),
            "debe_cambiar": bool(ses["debe_cambiar"])}


def solo_admin(u=Depends(usuario_actual)):
    if u["rol"] != "admin":
        raise HTTPException(403, "Solo un administrador puede hacer esto.")
    return u


Auth = Depends(usuario_actual)
Admin = Depends(solo_admin)


def A(u, accion, os_key=None, entidad=None, entidad_id=None, **detalle):
    auditar(u["usuario"], u["ip"], accion, os_key, entidad, entidad_id, detalle or None)


@app.post("/api/login")
async def login(request: Request):
    datos = await request.json()
    ip, ahora = _ip(request), time.time()
    _intentos[ip] = [t for t in _intentos.get(ip, []) if ahora - t < 900]
    if len(_intentos[ip]) >= 10:
        raise HTTPException(429, "Demasiados intentos desde esta conexión. Esperá 15 minutos.")
    try:
        token, _ = seguridad.ingresar(str(datos.get("usuario", "")), str(datos.get("clave", "")), ip)
    except PermissionError as e:
        _intentos[ip].append(ahora)
        raise HTTPException(401, str(e))
    resp = JSONResponse({"ok": True})
    resp.set_cookie("sesion", token, httponly=True, secure=COOKIE_SECURE, samesite="strict",
                    max_age=int(seguridad.SESSION_HOURS * 3600), path="/")
    return resp


@app.post("/api/logout")
def logout(request: Request):
    tok = request.cookies.get("sesion", "")
    ses = seguridad.sesion(tok)
    if ses:
        auditar(ses["usuario"], _ip(request), "logout")
    seguridad.cerrar(token=tok)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("sesion", path="/")
    return resp


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/me")
def me(u=Auth):
    return {"usuario": u["usuario"], "nombre": u["nombre"], "rol": u["rol"], "debe_cambiar": u["debe_cambiar"],
            "obras": logic.OBRAS, "links": LINKS, "inactividad_min": seguridad.IDLE_MINUTES,
            "resumen": {k: _resumen(k) for k in logic.OBRAS}}


@app.post("/api/mi-clave")
async def mi_clave(request: Request, u=Auth):
    d = await request.json()
    fila = db.q1("SELECT * FROM usuarios WHERE usuario=?", (u["usuario"],))
    if not seguridad.verificar_clave(str(d.get("actual", "")), fila["clave"]):
        A(u, "clave.cambio_fallido")
        raise ValueError("La contraseña actual no es correcta.")
    seguridad.validar_clave_nueva(str(d.get("nueva", "")), u["usuario"])
    with db.tx() as c:
        c.execute("UPDATE usuarios SET clave=?, debe_cambiar=0 WHERE id=?", (seguridad.hash_clave(d["nueva"]), fila["id"]))
    A(u, "clave.cambio")
    return {"ok": True}


# ───────────────────────── usuarios (solo administrador) ─────────────────────────

@app.get("/api/usuarios")
def usuarios(u=Admin):
    return {"filas": db.q("SELECT id,usuario,nombre,rol,activo,creado,ultimo_ingreso,debe_cambiar FROM usuarios ORDER BY usuario")}


@app.post("/api/usuarios")
async def usuario_alta(request: Request, u=Admin):
    d = await request.json()
    usuario = str(d.get("usuario", "")).strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,40}", usuario):
        raise ValueError("El usuario debe tener 3 a 40 caracteres: letras, números, punto o guion.")
    rol = d.get("rol") if d.get("rol") in ("admin", "operador") else "operador"
    seguridad.validar_clave_nueva(str(d.get("clave", "")), usuario)
    if db.q1("SELECT 1 x FROM usuarios WHERE usuario=?", (usuario,)):
        raise ValueError("Ya existe un usuario con ese nombre.")
    with db.tx() as c:
        c.execute("INSERT INTO usuarios(usuario,nombre,rol,clave,debe_cambiar,creado) VALUES (?,?,?,?,1,?)",
                  (usuario, str(d.get("nombre", "")).strip()[:80], rol, seguridad.hash_clave(d["clave"]), seguridad.ahora_txt()))
    A(u, "usuario.alta", entidad="usuario", entidad_id=usuario, rol=rol)
    return {"ok": True}


@app.put("/api/usuarios/{uid}")
async def usuario_editar(uid: int, request: Request, u=Admin):
    d = await request.json()
    fila = db.q1("SELECT * FROM usuarios WHERE id=?", (uid,))
    if not fila:
        raise HTTPException(404, "Usuario inexistente.")
    rol = d.get("rol", fila["rol"]) if d.get("rol") in ("admin", "operador") else fila["rol"]
    activo = 1 if d.get("activo", bool(fila["activo"])) else 0
    if fila["usuario"] == u["usuario"] and (not activo or rol != "admin"):
        raise ValueError("No podés quitarte a vos mismo el acceso de administrador.")
    cambios = {}
    with db.tx() as c:
        if rol != fila["rol"] or activo != fila["activo"] or d.get("nombre", fila["nombre"]) != fila["nombre"]:
            c.execute("UPDATE usuarios SET rol=?, activo=?, nombre=? WHERE id=?",
                      (rol, activo, str(d.get("nombre", fila["nombre"]) or "")[:80], uid))
            cambios.update(rol=rol, activo=bool(activo))
        if d.get("clave"):
            seguridad.validar_clave_nueva(str(d["clave"]), fila["usuario"])
            c.execute("UPDATE usuarios SET clave=?, debe_cambiar=1, fallos=0, bloqueado_hasta=0 WHERE id=?",
                      (seguridad.hash_clave(d["clave"]), uid))
            cambios["clave"] = "restablecida"
    if not activo or d.get("clave"):
        seguridad.cerrar(usuario=fila["usuario"])   # cierra sus sesiones abiertas
    A(u, "usuario.modificacion", entidad="usuario", entidad_id=fila["usuario"], **cambios)
    return {"ok": True}


# ───────────────────────── auditoría y copias (solo administrador) ─────────────────────────

def _auditoria(q="", usuario="", accion="", desde="", hasta=""):
    sql, par = "SELECT * FROM auditoria WHERE 1=1", []
    for campo, val, op in (("usuario", usuario, "="), ("fecha", desde, ">="), ("fecha", hasta and hasta + " 23:59:59", "<=")):
        if val:
            sql += f" AND {campo} {op} ?"
            par.append(val)
    if accion:
        sql += " AND accion LIKE ?"
        par.append(accion + "%")
    filas = db.q(sql + " ORDER BY id DESC", par)
    if q:
        b = logic.norm(q)
        filas = [f for f in filas if b in logic.norm(" ".join(str(v or "") for v in f.values()))]
    return filas


@app.get("/api/auditoria")
def auditoria(q: str = "", usuario: str = "", accion: str = "", desde: str = "", hasta: str = "",
              limite: int = 500, inicio: int = 0, u=Admin):
    filas = _auditoria(q, usuario, accion, desde, hasta)
    return {"total": len(filas), "filas": filas[inicio:inicio + limite],
            "usuarios": [r["usuario"] for r in db.q("SELECT DISTINCT usuario FROM auditoria ORDER BY 1")],
            "acciones": sorted({r["accion"].split(".")[0] for r in db.q("SELECT DISTINCT accion FROM auditoria")})}


@app.get("/api/auditoria/exportar")
def auditoria_exportar(q: str = "", usuario: str = "", accion: str = "", desde: str = "", hasta: str = "", u=Admin):
    filas = _auditoria(q, usuario, accion, desde, hasta)
    A(u, "auditoria.exportar", filas=len(filas))
    df = pd.DataFrame(filas, columns=["id", "fecha", "usuario", "ip", "accion", "os", "entidad", "entidad_id", "detalle"])
    return _descarga(logic.df_a_xlsx(df, "Auditoria"), f"Auditoria_{date.today():%Y%m%d}.xlsx")


@app.get("/api/backups")
def backups(u=Admin):
    return {"filas": seguridad.listar_backups(), "conservar": seguridad.BACKUP_KEEP, "cada_horas": seguridad.BACKUP_HOURS}


@app.post("/api/backups")
def backup_crear(u=Admin):
    r = seguridad.crear_backup()
    A(u, "backup.manual", entidad="backup", entidad_id=r["nombre"], bytes=r["bytes"])
    return r


@app.get("/api/backups/{nombre}")
def backup_descargar(nombre: str, u=Admin):
    ruta = seguridad.ruta_backup(nombre)
    if not ruta:
        raise HTTPException(404, "Copia inexistente.")
    A(u, "backup.descarga", entidad="backup", entidad_id=nombre)
    return FileResponse(ruta, media_type="application/gzip", filename=nombre, headers={"Cache-Control": "no-store"})


# ───────────────────────── utilidades ─────────────────────────

def _os(os_key):
    os_key = (os_key or "").upper()
    if os_key not in logic.OBRAS:
        raise HTTPException(400, "Obra social inválida.")
    return os_key


async def _leer(archivo: UploadFile):
    datos = await archivo.read()
    if not datos:
        raise HTTPException(400, "El archivo está vacío.")
    if len(datos) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"El archivo supera {MAX_UPLOAD_MB} MB.")
    return datos, archivo.filename or "archivo.xlsx"


def _descarga(contenido: bytes, nombre: str, extra=None):
    h = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}"}
    h.update(extra or {})
    return Response(contenido, media_type=XLSX, headers=h)


def _resumen(os_key):
    r = {e: 0 for e in ("prefact", "facturacion", "template")}
    for f in db.q("SELECT estado, COUNT(*) n FROM lineas WHERE os=? GROUP BY estado", (os_key,)):
        r[f["estado"]] = f["n"]
    r["padron"] = db.scalar("SELECT COUNT(*) FROM profesionales WHERE os=?", (os_key,))
    r["valores"] = db.scalar("SELECT COUNT(*) FROM valores WHERE os=?", (os_key,))
    r["evweb"] = db.scalar("SELECT COUNT(*) FROM evweb_filas WHERE os=?", (os_key,))
    r["templates"] = db.scalar("SELECT COUNT(*) FROM templates WHERE os=?", (os_key,))
    return r


@app.get("/api/resumen")
def resumen(os: str, u=Auth):
    return _resumen(_os(os))


# ───────────────────────── padrón ─────────────────────────

@app.get("/api/padron")
def padron(os: str, q: str = "", u=Auth):
    filas = db.q("SELECT id,cuenta,nombre,cuit,especialidad,categoria,resp_fiscal,matricula FROM profesionales "
                 "WHERE os=? ORDER BY nombre", (_os(os),))
    if q:
        b = logic.norm(q)
        filas = [f for f in filas if b in logic.norm(" ".join(str(v or "") for v in f.values()))]
    return {"filas": filas}


@app.post("/api/padron/importar")
async def padron_importar(os: str = Form(...), archivo: UploadFile = File(...), u=Auth):
    datos, nombre = await _leer(archivo)
    n = logic.importar_padron(_os(os), datos, nombre)
    A(u, "padron.importar", _os(os), "padron", archivo=nombre, profesionales=n)
    return {"importados": n}


@app.put("/api/padron/{pid}")
async def padron_editar(pid: int, request: Request, u=Auth):
    d = await request.json()
    campos = ["cuenta", "nombre", "cuit", "especialidad", "categoria", "resp_fiscal", "matricula"]
    vals = {k: str(d.get(k, "") or "").strip() for k in campos}
    if not vals["nombre"]:
        raise ValueError("El nombre es obligatorio.")
    antes = db.q1("SELECT * FROM profesionales WHERE id=?", (pid,))
    if not antes:
        raise HTTPException(404, "Profesional inexistente.")
    with db.tx() as c:
        c.execute(f"UPDATE profesionales SET {','.join(k + '=?' for k in campos)}, nombre_norm=? WHERE id=?",
                  [vals[k] for k in campos] + [logic.norm(vals["nombre"]), pid])
    A(u, "padron.modificar", antes["os"], "profesional", pid, profesional=vals["nombre"],
      cambios={k: {"antes": antes[k], "despues": vals[k]} for k in campos if (antes[k] or "") != vals[k]})
    return {"ok": True}


@app.post("/api/padron")
async def padron_alta(request: Request, u=Auth):
    d = await request.json()
    os_key = _os(d.get("os"))
    campos = ["cuenta", "nombre", "cuit", "especialidad", "categoria", "resp_fiscal", "matricula"]
    vals = {k: str(d.get(k, "") or "").strip() for k in campos}
    if not vals["nombre"]:
        raise ValueError("El nombre es obligatorio.")
    with db.tx() as c:
        c.execute(f"INSERT INTO profesionales(os,{','.join(campos)},nombre_norm) VALUES (?,?,?,?,?,?,?,?,?)",
                  [os_key] + [vals[k] for k in campos] + [logic.norm(vals["nombre"])])
    A(u, "padron.alta", os_key, "profesional", None, **vals)
    return {"ok": True}


@app.delete("/api/padron/{pid}")
def padron_baja(pid: int, u=Auth):
    antes = db.q1("SELECT * FROM profesionales WHERE id=?", (pid,))
    if not antes:
        raise HTTPException(404, "Profesional inexistente.")
    with db.tx() as c:
        c.execute("DELETE FROM profesionales WHERE id=?", (pid,))
    antes.pop("nombre_norm", None)
    A(u, "padron.baja", antes["os"], "profesional", pid, **{k: v for k, v in antes.items() if k not in ("id", "os")})
    return {"ok": True}


@app.get("/api/padron/exportar")
def padron_exportar(os: str, u=Auth):
    df = pd.DataFrame(db.q(
        "SELECT cuenta Cuenta,nombre Profesional,cuit CUIT,especialidad Especialidad,categoria Categoria,"
        "resp_fiscal 'Responsabilidad fiscal',matricula Matricula FROM profesionales WHERE os=? ORDER BY nombre",
        (_os(os),)))
    A(u, "padron.exportar", _os(os), "padron", filas=len(df))
    return _descarga(logic.df_a_xlsx(df, "Padron"), f"Padron_{_os(os)}.xlsx")


# ───────────────────────── valores ─────────────────────────

@app.get("/api/valores/meta")
def valores_meta(os: str, u=Auth):
    os_key = _os(os)
    pers = [r["periodo"] for r in db.q("SELECT DISTINCT periodo FROM valores WHERE os=?", (os_key,))]
    pers.sort(key=lambda p: (p[2:], p[:2]), reverse=True)
    esp = {p: [r["especialidad"] for r in db.q(
        "SELECT DISTINCT especialidad FROM valores WHERE os=? AND periodo=? ORDER BY id", (os_key, p))] for p in pers}
    return {"periodos": pers, "especialidades": esp}


def _valores(os_key, periodo, especialidad, q):
    sql, par = "SELECT * FROM valores WHERE os=? AND periodo=?", [os_key, periodo]
    if especialidad:
        sql += " AND especialidad=?"
        par.append(especialidad)
    filas = db.q(sql + " ORDER BY id", par)
    if q:
        b = logic.norm(q)
        filas = [f for f in filas if b in logic.norm(f"{f['codigo']} {f['codigo_prestador']} {f['descripcion']}")]
    return filas


@app.get("/api/valores")
def valores(os: str, periodo: str, especialidad: str = "", q: str = "", u=Auth):
    filas = _valores(_os(os), periodo, especialidad, q)
    return {"total": len(filas), "filas": filas[:3000]}


@app.post("/api/valores/importar")
async def valores_importar(os: str = Form(...), periodo: str = Form(...), archivo: UploadFile = File(...), u=Auth):
    datos, nombre = await _leer(archivo)
    r = logic.importar_grilla(_os(os), periodo, datos, nombre)
    A(u, "valores.importar", _os(os), "grilla", r["periodo"], archivo=nombre, filas=r["filas"])
    return r


@app.delete("/api/valores")
def valores_borrar(os: str, periodo: str, u=Auth):
    with db.tx() as c:
        n = c.execute("DELETE FROM valores WHERE os=? AND periodo=?", (_os(os), periodo)).rowcount
    A(u, "valores.eliminar", _os(os), "grilla", periodo, filas=n)
    return {"ok": True}


@app.get("/api/valores/exportar")
def valores_exportar(os: str, periodo: str, especialidad: str = "", q: str = "", u=Auth):
    filas = _valores(_os(os), periodo, especialidad, q)
    df = pd.DataFrame([{"Especialidad": f["especialidad"], "Código OS": f["codigo"],
                        "Código prestador": f["codigo_prestador"], "Descripción": f["descripcion"],
                        "Categoría": f["categoria"], "Valor": f["valor"], "Fila grilla": f["fila"]} for f in filas])
    A(u, "valores.exportar", _os(os), "grilla", periodo, filas=len(filas))
    return _descarga(logic.df_a_xlsx(df, "Valores"), f"Valores_{_os(os)}_{periodo}.xlsx")


# ───────────────────────── EVWEB ─────────────────────────

def _run_bot(jid, os_key, usuario, clave, desde: date, hasta: date, quien):
    job = JOBS[jid]

    def prog(texto, pct):
        job["progreso"] = (texto, float(pct))
        job["log"].append(f"{datetime.now():%H:%M:%S} {texto}")

    try:
        with _bot_lock:   # una sola sesión de EVWEB a la vez
            rangos = generar_rangos_9_dias(desde, hasta)
            res = ejecutar_extractor(usuario, clave, logic.OBRAS[os_key]["codigo"], rangos, prog, HEADLESS)
        job["avisos"] = res.get("avisos", [])
        guard = {"filas": 0, "nuevas": 0}
        if res["excels"]:
            prog("Guardando datos extraídos…", 0.92)
            guard = logic.guardar_evweb(os_key, res["excels"], "bot", f"{desde:%d/%m/%Y}", f"{hasta:%d/%m/%Y}")
        job["resultado"] = {**guard, "tramos": len(rangos), "descargados": len(res["excels"])}
        auditar(quien["usuario"], quien["ip"], "evweb.extraccion_fin", os_key, "evweb", None,
                {"desde": f"{desde:%d/%m/%Y}", "hasta": f"{hasta:%d/%m/%Y}", **job["resultado"],
                 "error": res.get("error"), "avisos": job["avisos"]})
        if res.get("error"):
            job["error"] = res["error"] + (f" (se guardaron {guard['filas']} filas de los tramos ya descargados)"
                                           if guard["filas"] else "")
            job["estado"] = "error"
        else:
            job["estado"] = "listo"
            prog("Extracción finalizada", 1.0)
    except Exception as e:
        job["error"] = f"{e}"
        job["log"].append(traceback.format_exc())
        auditar(quien["usuario"], quien["ip"], "evweb.extraccion_error", os_key, "evweb", None, {"error": str(e)})
        job["estado"] = "error"


@app.post("/api/evweb/extraer")
async def evweb_extraer(request: Request, u=Auth):
    d = await request.json()
    os_key = _os(d.get("os"))
    try:
        desde = datetime.strptime(d.get("desde", ""), "%Y-%m-%d").date()
        hasta = datetime.strptime(d.get("hasta", ""), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Indicá fecha de carga desde y hasta.")
    if hasta < desde:
        raise ValueError("La fecha 'hasta' debe ser posterior a 'desde'.")
    if (hasta - desde).days > 370:
        raise ValueError("El rango máximo es de un año.")
    if not d.get("usuario") or not d.get("clave"):
        raise ValueError("Ingresá usuario y contraseña de EVWEB.")
    if any(j["estado"] == "corriendo" for j in JOBS.values()):
        raise ValueError("Ya hay una extracción en curso. Esperá a que termine.")
    jid = uuid.uuid4().hex
    JOBS[jid] = {"id": jid, "os": os_key, "estado": "corriendo", "progreso": ("Iniciando…", 0.02), "log": [],
                 "avisos": [], "error": None, "resultado": None,
                 "tramos": generar_rangos_9_dias(desde, hasta)}
    A(u, "evweb.extraccion_inicio", os_key, "evweb", None, desde=f"{desde:%d/%m/%Y}", hasta=f"{hasta:%d/%m/%Y}",
      usuario_evweb=d["usuario"], tramos=len(JOBS[jid]["tramos"]))
    threading.Thread(target=_run_bot, args=(jid, os_key, d["usuario"], d["clave"], desde, hasta, u), daemon=True).start()
    return {"job": jid}


@app.get("/api/evweb/tramos")
def evweb_tramos(desde: str, hasta: str, u=Auth):
    try:
        a, b = datetime.strptime(desde, "%Y-%m-%d").date(), datetime.strptime(hasta, "%Y-%m-%d").date()
    except ValueError:
        return {"tramos": []}
    return {"tramos": generar_rangos_9_dias(a, b) if b >= a and (b - a).days <= 370 else []}


@app.get("/api/evweb/job")
def evweb_job(id: str = "", os: str = "", u=Auth):
    job = JOBS.get(id) if id else next((j for j in reversed(list(JOBS.values())) if j["estado"] == "corriendo"), None)
    if not job:
        return {"job": None}
    return {"job": {k: job[k] for k in ("id", "os", "estado", "progreso", "avisos", "error", "resultado", "tramos")}
            | {"log": job["log"][-40:]}}


@app.post("/api/evweb/importar")
async def evweb_importar(os: str = Form(...), archivo: UploadFile = File(...), u=Auth):
    datos, nombre = await _leer(archivo)
    df = logic.leer_tabla(datos, nombre)
    r = logic.guardar_evweb(_os(os), [df], f"archivo: {nombre}")
    A(u, "evweb.importar", _os(os), "evweb", None, archivo=nombre, filas=r["filas"], nuevas=r["nuevas"])
    return r


@app.get("/api/evweb")
def evweb(os: str, q: str = "", limite: int = 1500, desde: int = 0, u=Auth):
    os_key = _os(os)
    df = logic.evweb_df(os_key, q)
    ext = db.q("SELECT * FROM evweb_extracciones WHERE os=? ORDER BY id DESC LIMIT 30", (os_key,))
    tramo = df.iloc[desde:desde + limite] if limite > 0 else df
    return {"total": len(df), "columnas": list(df.columns), "filas": tramo.fillna("").to_dict("records"),
            "extracciones": ext}


@app.get("/api/evweb/exportar")
def evweb_exportar(os: str, q: str = "", u=Auth):
    df = logic.evweb_df(_os(os), q)
    A(u, "evweb.exportar", _os(os), "evweb", None, filas=len(df), filtro=q)
    return _descarga(logic.df_a_xlsx(df, "EVWEB"), f"Datos_extraidos_evweb_{_os(os)}_{date.today():%Y%m%d}.xlsx")


# ───────────────────────── pre-facturación / facturación ─────────────────────────

@app.post("/api/prefacturar")
async def prefacturar(os: str = Form(...), periodo: str = Form(...), archivo: UploadFile = File(...), u=Auth):
    datos, nombre = await _leer(archivo)
    r = logic.prefacturar(_os(os), periodo, datos, nombre)
    A(u, "prefacturacion.iniciar", _os(os), "prefacturacion", periodo, archivo=nombre, **r)
    return r


def _lineas(os_key, estado, periodo="", q="", cruce=""):
    sql, par = "SELECT * FROM lineas WHERE os=? AND estado=?", [os_key, estado]
    if periodo:
        sql += " AND periodo=?"
        par.append(periodo)
    if cruce:
        sql += " AND cruce=?"
        par.append(cruce)
    filas = db.q(sql + " ORDER BY id", par)
    if q:
        b = logic.norm(q)
        filas = [f for f in filas if b in logic.norm(" ".join(str(f[k] or "") for k in (
            "nro_transaccion", "afiliado_numero", "afiliado_nombre", "cod_practica", "descripcion", "cuenta",
            "matricula", "profesional", "especialidad", "observacion")))]
    return filas


@app.get("/api/lineas")
def lineas(os: str, estado: str, periodo: str = "", q: str = "", cruce: str = "", limite: int = 1500,
           desde: int = 0, u=Auth):
    os_key = _os(os)
    if estado not in ("prefact", "facturacion", "template"):
        raise HTTPException(400, "Estado inválido.")
    filas = _lineas(os_key, estado, periodo, q, cruce)
    pers = [r["periodo"] for r in db.q("SELECT DISTINCT periodo FROM lineas WHERE os=? AND estado=?", (os_key, estado))]
    tramo = filas[desde:desde + limite] if limite > 0 else filas
    return {"total": len(filas), "importe": round(sum(f["total"] or 0 for f in filas), 2),
            "listas": sum(1 for f in filas if not logic.validar_para_procesar(f)),
            "periodos": sorted(pers, key=lambda p: (p[2:], p[:2]), reverse=True), "filas": tramo}


@app.get("/api/lineas/exportar")
def lineas_exportar(os: str, estado: str, periodo: str = "", q: str = "", cruce: str = "", u=Auth):
    filas = _lineas(_os(os), estado, periodo, q, cruce)
    cols = ["periodo", "nro_transaccion", "fecha_prestacion", "afiliado_numero", "afiliado_nombre", "cod_practica",
            "descripcion", "cantidad", "cuenta", "matricula", "profesional", "cuit", "especialidad", "categoria",
            "valor_unit", "total", "origen_valor", "cruce", "observacion"]
    df = pd.DataFrame([{k: f[k] for k in cols} for f in filas], columns=cols)
    nombre = {"prefact": "Prefacturacion", "facturacion": "Facturacion", "template": "Emitidas"}[estado]
    A(u, "lineas.exportar", _os(os), nombre.lower(), periodo or None, filas=len(filas))
    return _descarga(logic.df_a_xlsx(df, nombre), f"{nombre}_{_os(os)}_{periodo or 'todos'}.xlsx")


@app.put("/api/lineas/{lid}")
async def linea_editar(lid: int, request: Request, u=Auth):
    d = await request.json()
    r = logic.editar_linea(lid, d.get("cambios", {}), bool(d.get("autocompletar")))
    A(u, "linea.modificar", r["os"], "linea", lid, transaccion=r["nro_transaccion"], etapa=r["estado"], cambios=r.pop("_cambios"))
    return r


@app.post("/api/lineas/accion")
async def lineas_accion(request: Request, u=Auth):
    d = await request.json()
    os_key, accion = _os(d.get("os")), d.get("accion")
    ids = [int(i) for i in d.get("ids", [])]
    if not ids:
        raise ValueError("No hay filas seleccionadas.")
    if accion not in ("procesar", "rechazar", "eliminar", "editar"):
        raise HTTPException(400, "Acción inválida.")
    hechas, omitidas, afectadas = 0, [], []
    with db.tx() as c:
        for bloque in (ids[i:i + 500] for i in range(0, len(ids), 500)):
            marcas = ",".join("?" * len(bloque))
            filas = [dict(r) for r in c.execute(
                f"SELECT * FROM lineas WHERE os=? AND id IN ({marcas})", [os_key] + bloque).fetchall()]
            for f in filas:
                if accion == "procesar" and f["estado"] == "prefact":
                    faltan = logic.validar_para_procesar(f)
                    if faltan:
                        omitidas.append({"id": f["id"], "nro": f["nro_transaccion"], "faltan": faltan})
                        continue
                    c.execute("UPDATE lineas SET estado='facturacion' WHERE id=?", (f["id"],))
                elif accion == "rechazar" and f["estado"] == "facturacion":
                    c.execute("UPDATE lineas SET estado='prefact' WHERE id=?", (f["id"],))
                elif accion == "eliminar" and f["estado"] in ("prefact", "facturacion"):
                    c.execute("DELETE FROM lineas WHERE id=?", (f["id"],))
                elif accion == "editar" and f["estado"] in ("prefact", "facturacion"):
                    pass
                else:
                    continue
                hechas += 1
                if accion == "eliminar":   # se conserva la línea completa en la auditoría
                    afectadas.append({k: f[k] for k in f if k not in ("creado", "template_id") and f[k] not in (None, "")})
                else:
                    afectadas.append({"id": f["id"], "transaccion": f["nro_transaccion"], "cod": f["cod_practica"]})
    if accion == "editar":   # edición masiva: mismos cambios a todas las seleccionadas
        hechas = 0
        for i in ids:
            try:
                r = logic.editar_linea(i, d.get("cambios", {}), True)
                hechas += 1
                afectadas.append({"id": i, "transaccion": r["nro_transaccion"], "cambios": r["_cambios"]})
            except ValueError as e:
                omitidas.append({"id": i, "nro": "", "faltan": [str(e)]})
    for i in range(0, len(afectadas), 500):   # registros de hasta 500 líneas cada uno
        A(u, {"procesar": "lineas.procesar", "rechazar": "lineas.rechazar", "eliminar": "lineas.eliminar",
              "editar": "lineas.modificar_masivo"}[accion], os_key, "linea", None,
          cantidad=len(afectadas), parte=i // 500 + 1, lineas=afectadas[i:i + 500])
    return {"hechas": hechas, "omitidas": omitidas[:50], "n_omitidas": len(omitidas)}


# ───────────────────────── templates ─────────────────────────

@app.post("/api/templates")
async def template_generar(request: Request, u=Auth):
    d = await request.json()
    r = logic.generar_template(_os(d.get("os")), [int(i) for i in d.get("ids", [])])
    A(u, "template.generar", _os(d.get("os")), "template", r["id"], **r)
    return r


@app.get("/api/templates")
def templates(os: str, u=Auth):
    return {"filas": db.q("SELECT id,os,periodo,nn,nombre,fecha,filas,total FROM templates WHERE os=? ORDER BY id DESC",
                          (_os(os),))}


@app.get("/api/templates/{tid}/descargar")
def template_descargar(tid: int, u=Auth):
    t = db.q1("SELECT os, nombre, contenido FROM templates WHERE id=?", (tid,))
    if not t:
        raise HTTPException(404, "Template inexistente.")
    A(u, "template.descargar", t["os"], "template", tid, nombre=t["nombre"])
    return _descarga(t["contenido"], t["nombre"] + ".xlsx")


@app.delete("/api/templates/{tid}")
def template_deshacer(tid: int, u=Auth):
    """DESHACER: las líneas vuelven a Facturación y el template se elimina."""
    t = db.q1("SELECT os, nombre, filas, total FROM templates WHERE id=?", (tid,))
    if not t:
        raise HTTPException(404, "Template inexistente.")
    with db.tx() as c:
        c.execute("UPDATE lineas SET estado='facturacion', template_id=NULL WHERE template_id=?", (tid,))
        c.execute("DELETE FROM templates WHERE id=?", (tid,))
    A(u, "template.deshacer", t["os"], "template", tid, **{k: t[k] for k in ("nombre", "filas", "total")})
    return {"ok": True}


# ───────────────────────── presentaciones ─────────────────────────

@app.post("/api/presentaciones/{os}")
async def presentacion(os: str, periodo: str = Form(...), factura: str = Form(""),
                       archivo: UploadFile = File(...), u=Auth):
    os_key = _os(os)
    periodo = logic.validar_periodo(periodo)
    datos, nombre = await _leer(archivo)
    if os_key == "GALENO":
        salida, info = logic.convertir_galeno(datos, nombre, factura)
        archivo_out = f"Anexo de prestaciones_{periodo}.xlsx"
    elif os_key == "SANCOR":
        salida, info = logic.convertir_sancor(datos, nombre, factura)
        archivo_out = f"PrestacionesExport_SANCOR_{periodo}.xlsx"
    else:
        raise HTTPException(400, "AVALIAN no requiere conversión.")
    A(u, "presentacion.convertir", os_key, "presentacion", periodo, archivo=nombre, salida=archivo_out,
      factura=factura, filas=info["filas"], cuentas_sin_mp=info["sin_mp"])
    return _descarga(salida, archivo_out, {"X-Filas": str(info["filas"]),
                                           "X-Sin-MP": quote(", ".join(info["sin_mp"][:60])),
                                           "X-Sin-MP-N": str(len(info["sin_mp"]))})


# ───────────────────────── interfaz ─────────────────────────

app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"), headers={"Cache-Control": "no-cache"})
