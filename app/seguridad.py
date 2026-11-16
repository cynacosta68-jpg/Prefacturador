"""Usuarios, sesiones, auditoría y copias de seguridad."""
import gzip
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
from datetime import datetime

from . import db

SESSION_HOURS = float(os.environ.get("SESSION_HOURS", "12"))
IDLE_MINUTES = float(os.environ.get("IDLE_MINUTES", "60"))
BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "30"))
BACKUP_HOURS = float(os.environ.get("BACKUP_HOURS", "24"))
BACKUP_DIR = os.path.join(db.DATA_DIR, "backups")
MIN_CLAVE = 10


# ───────────────────────── claves ─────────────────────────

def hash_clave(clave: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(clave.encode(), salt=sal, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${sal.hex()}${h.hex()}"


def verificar_clave(clave: str, guardada: str) -> bool:
    try:
        _, sal, h = guardada.split("$")
        calc = hashlib.scrypt(clave.encode(), salt=bytes.fromhex(sal), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc.hex(), h)
    except Exception:
        return False


_FALSA = hash_clave(secrets.token_hex(8))   # para tardar lo mismo si el usuario no existe


def validar_clave_nueva(clave: str, usuario: str = ""):
    if len(clave or "") < MIN_CLAVE:
        raise ValueError(f"La contraseña debe tener al menos {MIN_CLAVE} caracteres.")
    if not (re.search(r"[A-Za-zÁ-ú]", clave) and re.search(r"\d", clave)):
        raise ValueError("La contraseña debe combinar letras y números.")
    if usuario and usuario.lower() in clave.lower():
        raise ValueError("La contraseña no puede contener el nombre de usuario.")


def ahora_txt():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sembrar_admin():
    """Primer arranque: crea el administrador con ADMIN_USER / ADMIN_PASSWORD."""
    if db.scalar("SELECT COUNT(*) FROM usuarios"):
        return
    usuario = os.environ.get("ADMIN_USER", "admin").strip().lower()
    clave = os.environ.get("ADMIN_PASSWORD", "")
    if len(clave) < MIN_CLAVE:
        print(f"[seguridad] ADMIN_PASSWORD falta o tiene menos de {MIN_CLAVE} caracteres: no se creó el administrador.")
        return
    with db.tx() as c:
        c.execute("INSERT INTO usuarios(usuario,nombre,rol,clave,creado) VALUES (?,?,?,?,?)",
                  (usuario, "Administrador", "admin", hash_clave(clave), ahora_txt()))
    auditar("sistema", "", "usuario.alta", entidad="usuario", entidad_id=usuario, detalle={"rol": "admin", "origen": "arranque"})


# ───────────────────────── auditoría ─────────────────────────

def auditar(usuario, ip, accion, os_key=None, entidad=None, entidad_id=None, detalle=None):
    with db.tx() as c:
        c.execute("INSERT INTO auditoria(fecha,usuario,ip,accion,os,entidad,entidad_id,detalle) VALUES (?,?,?,?,?,?,?,?)",
                  (ahora_txt(), usuario, ip, accion, os_key, entidad,
                   None if entidad_id is None else str(entidad_id)[:80],
                   json.dumps(detalle, ensure_ascii=False, default=str) if detalle else None))


# ───────────────────────── sesiones ─────────────────────────

def _h(token):
    return hashlib.sha256(token.encode()).hexdigest()


def ingresar(usuario, clave, ip):
    """Devuelve (token, fila_usuario) o lanza PermissionError con el motivo para mostrar."""
    usuario = (usuario or "").strip().lower()
    u = db.q1("SELECT * FROM usuarios WHERE usuario=?", (usuario,))
    t = time.time()
    if u and u["bloqueado_hasta"] and u["bloqueado_hasta"] > t:
        auditar(usuario, ip, "login.bloqueado")
        raise PermissionError("Usuario bloqueado por intentos fallidos. Probá de nuevo en 15 minutos.")
    ok = verificar_clave(clave or "", u["clave"] if u else _FALSA) and bool(u) and bool(u["activo"])
    if not ok:
        if u:
            fallos = u["fallos"] + 1
            with db.tx() as c:
                c.execute("UPDATE usuarios SET fallos=?, bloqueado_hasta=? WHERE id=?",
                          (0 if fallos >= 5 else fallos, t + 900 if fallos >= 5 else 0, u["id"]))
        auditar(usuario[:60], ip, "login.fallido", detalle={"existe": bool(u)})
        raise PermissionError("Usuario o contraseña incorrectos.")
    token = secrets.token_urlsafe(32)
    with db.tx() as c:
        c.execute("DELETE FROM sesiones WHERE creado < ?", (t - SESSION_HOURS * 3600,))
        c.execute("INSERT INTO sesiones(token,usuario,creado,visto,ip) VALUES (?,?,?,?,?)", (_h(token), usuario, t, t, ip))
        c.execute("UPDATE usuarios SET fallos=0, bloqueado_hasta=0, ultimo_ingreso=? WHERE id=?", (ahora_txt(), u["id"]))
    auditar(usuario, ip, "login.ok")
    return token, u


def sesion(token):
    if not token:
        return None
    s = db.q1("SELECT s.token, s.creado, s.visto, u.usuario, u.nombre, u.rol, u.debe_cambiar FROM sesiones s "
              "JOIN usuarios u ON u.usuario=s.usuario WHERE s.token=? AND u.activo=1", (_h(token),))
    t = time.time()
    if not s or t - s["creado"] > SESSION_HOURS * 3600 or t - s["visto"] > IDLE_MINUTES * 60:
        return None
    if t - s["visto"] > 60:
        with db.tx() as c:
            c.execute("UPDATE sesiones SET visto=? WHERE token=?", (t, s["token"]))
    return s


def cerrar(token=None, usuario=None):
    with db.tx() as c:
        if token:
            c.execute("DELETE FROM sesiones WHERE token=?", (_h(token),))
        if usuario:
            c.execute("DELETE FROM sesiones WHERE usuario=?", (usuario,))


# ───────────────────────── copias de seguridad ─────────────────────────

_RE_BACKUP = re.compile(r"^facturacion_\d{8}_\d{6}\.db\.gz$")
_bk_lock = threading.Lock()


def crear_backup():
    """Copia consistente de la base (API de backup de SQLite) comprimida en /data/backups."""
    with _bk_lock:
        os.makedirs(BACKUP_DIR, mode=0o700, exist_ok=True)
        nombre = f"facturacion_{datetime.now():%Y%m%d_%H%M%S}.db.gz"
        tmp = os.path.join(BACKUP_DIR, ".tmp.db")
        origen = sqlite3.connect(db.DB_PATH)
        destino = sqlite3.connect(tmp)
        try:
            origen.backup(destino)
            ok = destino.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            destino.close()
            origen.close()
        if ok != "ok":
            os.remove(tmp)
            raise RuntimeError(f"La copia no pasó la verificación de integridad: {ok}")
        ruta = os.path.join(BACKUP_DIR, nombre)
        with open(tmp, "rb") as f, gzip.open(ruta, "wb", compresslevel=6) as g:
            shutil.copyfileobj(f, g)
        os.remove(tmp)
        os.chmod(ruta, 0o600)
        for viejo in listar_backups()[BACKUP_KEEP:]:
            os.remove(os.path.join(BACKUP_DIR, viejo["nombre"]))
        return {"nombre": nombre, "bytes": os.path.getsize(ruta)}


def listar_backups():
    if not os.path.isdir(BACKUP_DIR):
        return []
    out = []
    for n in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if _RE_BACKUP.match(n):
            st = os.stat(os.path.join(BACKUP_DIR, n))
            out.append({"nombre": n, "bytes": st.st_size, "fecha": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M")})
    return out


def ruta_backup(nombre):
    if not _RE_BACKUP.match(nombre or ""):
        return None
    ruta = os.path.join(BACKUP_DIR, nombre)
    return ruta if os.path.isfile(ruta) else None


def _ciclo_backup():
    while True:
        try:
            lista = listar_backups()
            ultimo = os.stat(os.path.join(BACKUP_DIR, lista[0]["nombre"])).st_mtime if lista else 0
            if time.time() - ultimo > BACKUP_HOURS * 3600:
                r = crear_backup()
                auditar("sistema", "", "backup.automatico", entidad="backup", entidad_id=r["nombre"], detalle=r)
        except Exception as e:   # nunca tumba el servicio
            try:
                auditar("sistema", "", "backup.error", detalle={"error": str(e)})
            except Exception:
                pass
        try:
            from . import archivo
            archivo.automatico()
        except Exception as e:
            try:
                auditar("sistema", "", "archivo.error", detalle={"error": str(e)})
            except Exception:
                pass
        time.sleep(1800)


def iniciar_backups():
    threading.Thread(target=_ciclo_backup, daemon=True).start()
