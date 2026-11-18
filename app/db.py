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

-- Grillas normalizadas: valores por unidad (lo que cambia mes a mes) y prestaciones
CREATE TABLE IF NOT EXISTS unidades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    os TEXT NOT NULL, periodo TEXT NOT NULL,
    especialidad TEXT, tipo_unidad TEXT, valor REAL NOT NULL,
    origen TEXT, hoja TEXT, fila INTEGER
);
CREATE INDEX IF NOT EXISTS ix_uni ON unidades(os, periodo);
CREATE TABLE IF NOT EXISTS valores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    os TEXT NOT NULL, periodo TEXT NOT NULL,
    especialidad TEXT, seccion TEXT, codigo TEXT, codigo_prestador TEXT, descripcion TEXT,
    categoria TEXT, unidades REAL, tipo_valor TEXT NOT NULL DEFAULT 'fijo', unidad_id INTEGER,
    valor REAL, valor_grilla REAL, ayudantes TEXT, grupo TEXT, hoja TEXT, fila INTEGER
);
CREATE INDEX IF NOT EXISTS ix_val ON valores(os, periodo, codigo);
CREATE INDEX IF NOT EXISTS ix_val_u ON valores(unidad_id);

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
CREATE INDEX IF NOT EXISTS ix_lin_id ON lineas(os, estado, id);

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

-- Coseguros (copagos) informados en el archivo validado, por transacción y práctica
CREATE TABLE IF NOT EXISTS coseguros (
    os TEXT NOT NULL, nro TEXT NOT NULL, cod TEXT NOT NULL, copago REAL NOT NULL DEFAULT 0, periodo TEXT,
    PRIMARY KEY (os, nro, cod)
);

-- Archivos validados ya importados (para reconocer cuando se sube el mismo)
CREATE TABLE IF NOT EXISTS importaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    os TEXT NOT NULL, hash TEXT NOT NULL, nombre TEXT, periodo TEXT, fecha TEXT, filas INTEGER
);
CREATE INDEX IF NOT EXISTS ix_imp ON importaciones(os, hash);

-- Valores cargados a mano para prestaciones que la grilla no trae (solapa «Otros» de Valores)
CREATE TABLE IF NOT EXISTS otros_valores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    os TEXT NOT NULL, codigo TEXT NOT NULL, descripcion TEXT,
    vigencia TEXT NOT NULL,            -- MMAAAA desde el que rige el valor
    valor REAL, valor_r REAL           -- todas las categorías / categoría R
);
CREATE INDEX IF NOT EXISTS ix_otros ON otros_valores(os, codigo);

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
        # Versión anterior de las grillas (sin unidades): se descarta, hay que volver a subirlas
        cols = [r[1] for r in _conn.execute("PRAGMA table_info(valores)").fetchall()]
        if cols and "tipo_valor" not in cols:
            _conn.execute("DROP TABLE valores")
        _conn.executescript(SCHEMA)
        cols = [r[1] for r in _conn.execute("PRAGMA table_info(lineas)").fetchall()]
        for nueva in ("valor_archivo", "valor_grilla"):     # valor unitario según el archivo validado y según la grilla
            if nueva not in cols:
                _conn.execute(f"ALTER TABLE lineas ADD COLUMN {nueva} REAL")
        if "iva" not in cols:            # SWISS MEDICAL: IVA del template y código de obra social de la línea
            _conn.execute("ALTER TABLE lineas ADD COLUMN iva INTEGER")
            _conn.execute("ALTER TABLE lineas ADD COLUMN os_codigo TEXT")
        if "resp_fiscal" not in cols:    # condición del profesional y del afiliado, para filtrar y asignar IVA en bloque
            _conn.execute("ALTER TABLE lineas ADD COLUMN resp_fiscal TEXT")
            _conn.execute("ALTER TABLE lineas ADD COLUMN cond_afiliado TEXT")
            _conn.execute("UPDATE lineas SET resp_fiscal=(SELECT p.resp_fiscal FROM profesionales p WHERE p.os=lineas.os "
                          "AND p.cuit=lineas.cuit AND p.cuit<>'' LIMIT 1)")
        if "cod_propuesto" not in cols:  # código que propone la aplicación (según especialidad); el del archivo no se toca
            _conn.execute("ALTER TABLE lineas ADD COLUMN cod_propuesto TEXT")
            _conn.execute("ALTER TABLE lineas ADD COLUMN desc_propuesta TEXT")
            _conn.execute("UPDATE lineas SET cod_propuesto=cod_practica")
        cols = [r[1] for r in _conn.execute("PRAGMA table_info(profesionales)").fetchall()]
        if "codigo_iva" not in cols:     # código de IVA: depende de la responsabilidad fiscal (Responsable Inscripto = 1)
            _conn.execute("ALTER TABLE profesionales ADD COLUMN efector TEXT")
            _conn.execute("ALTER TABLE profesionales ADD COLUMN codigo_iva INTEGER")
            _conn.execute("UPDATE profesionales SET codigo_iva=CASE WHEN LOWER(TRIM(resp_fiscal))='responsable inscripto' THEN 1 ELSE 0 END")
        cols = [r[1] for r in _conn.execute("PRAGMA table_info(evweb_filas)").fetchall()]
        if "fecha" not in cols:      # fecha de la prestación (AAAA-MM-DD) para filtrar y archivar
            _conn.execute("ALTER TABLE evweb_filas ADD COLUMN fecha TEXT")
        _conn.execute("CREATE INDEX IF NOT EXISTS ix_ev_fecha ON evweb_filas(os, fecha)")
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
