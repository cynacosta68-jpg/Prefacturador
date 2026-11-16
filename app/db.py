"""Acceso a la base SQLite (persistida en el volumen /data)."""
import os
import sqlite3
import threading
from contextlib import contextmanager

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "facturacion.db")

_lock = threading.RLock()
_conn = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS profesionales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    os TEXT NOT NULL,
    cuenta TEXT, nombre TEXT, cuit TEXT, especialidad TEXT,
    categoria TEXT, resp_fiscal TEXT, matricula TEXT,
    nombre_norm TEXT
);
CREATE INDEX IF NOT EXISTS ix_prof_os ON profesionales(os);

CREATE TABLE IF NOT EXISTS valores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    os TEXT NOT NULL, periodo TEXT NOT NULL,
    especialidad TEXT, codigo TEXT, codigo_prestador TEXT, descripcion TEXT,
    categoria TEXT, valor REAL, fila INTEGER
);
CREATE INDEX IF NOT EXISTS ix_val ON valores(os, periodo, codigo);

CREATE TABLE IF NOT EXISTS evweb_extracciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    os TEXT NOT NULL, origen TEXT, desde TEXT, hasta TEXT,
    fecha TEXT, filas INTEGER, nuevas INTEGER
);
CREATE TABLE IF NOT EXISTS evweb_filas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    extraccion_id INTEGER, os TEXT NOT NULL,
    nro TEXT, profesional TEXT, cuenta TEXT,
    data TEXT, hash TEXT,
    UNIQUE(os, hash)
);
CREATE INDEX IF NOT EXISTS ix_ev ON evweb_filas(os, nro);

CREATE TABLE IF NOT EXISTS lineas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    os TEXT NOT NULL, periodo TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'prefact',
    nro_transaccion TEXT, fecha_prestacion TEXT,
    afiliado_numero TEXT, afiliado_nombre TEXT,
    cod_practica TEXT, descripcion TEXT, cantidad REAL DEFAULT 1,
    cuenta TEXT, matricula TEXT, profesional TEXT, cuit TEXT,
    especialidad TEXT, categoria TEXT,
    valor_unit REAL DEFAULT 0, total REAL DEFAULT 0,
    origen_valor TEXT, cruce TEXT, observacion TEXT,
    template_id INTEGER, creado TEXT
);
CREATE INDEX IF NOT EXISTS ix_lin ON lineas(os, estado, periodo);

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT UNIQUE NOT NULL, nombre TEXT, rol TEXT NOT NULL DEFAULT 'operador',
    clave TEXT NOT NULL, activo INTEGER NOT NULL DEFAULT 1,
    fallos INTEGER NOT NULL DEFAULT 0, bloqueado_hasta REAL DEFAULT 0,
    debe_cambiar INTEGER NOT NULL DEFAULT 0, creado TEXT, ultimo_ingreso TEXT
);
CREATE TABLE IF NOT EXISTS sesiones (
    token TEXT PRIMARY KEY, usuario TEXT NOT NULL, creado REAL, visto REAL, ip TEXT
);
-- Auditoría: solo se agregan filas; los disparadores impiden modificarla o borrarla.
CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL, usuario TEXT, ip TEXT, accion TEXT NOT NULL,
    os TEXT, entidad TEXT, entidad_id TEXT, detalle TEXT
);
CREATE INDEX IF NOT EXISTS ix_aud ON auditoria(fecha);
CREATE TRIGGER IF NOT EXISTS aud_no_update BEFORE UPDATE ON auditoria
BEGIN SELECT RAISE(ABORT, 'La auditoria no se puede modificar'); END;
CREATE TRIGGER IF NOT EXISTS aud_no_delete BEFORE DELETE ON auditoria
BEGIN SELECT RAISE(ABORT, 'La auditoria no se puede borrar'); END;

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    os TEXT NOT NULL, periodo TEXT NOT NULL, nn INTEGER,
    nombre TEXT, fecha TEXT, filas INTEGER, total REAL,
    contenido BLOB
);
"""


def conn():
    global _conn
    if _conn is None:
        os.makedirs(DATA_DIR, mode=0o700, exist_ok=True)
        if not os.path.exists(DB_PATH):
            os.close(os.open(DB_PATH, os.O_CREAT | os.O_WRONLY, 0o600))   # solo el usuario del servicio
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None, timeout=30)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA secure_delete=ON")
        _conn.executescript(SCHEMA)
    return _conn


@contextmanager
def tx():
    """Transacción serializada (los jobs del bot escriben desde otros threads)."""
    with _lock:
        c = conn()
        c.execute("BEGIN")
        try:
            yield c
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise


def q(sql, params=()):
    with _lock:
        return [dict(r) for r in conn().execute(sql, params).fetchall()]


def q1(sql, params=()):
    r = q(sql, params)
    return r[0] if r else None


def scalar(sql, params=()):
    with _lock:
        r = conn().execute(sql, params).fetchone()
        return r[0] if r else None
