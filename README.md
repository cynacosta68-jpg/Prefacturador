# Facturación Obras Sociales · AVALIAN – SANCOR – GALENO

Un solo servicio (API + interfaz + bot de EVWEB) para pre-facturar, facturar y preparar las presentaciones.
Toma el bot y el cruce por número de transacción de `ProcesarGaleno` y el flujo de edición / template / deshacer de
`seros-facturacion-evweb`.

```
Padrón + Valores ─▶ Bot EVWEB ─▶ Datos extraídos (solo consulta)
                                      │ cruce por N° de transacción
Archivo validado ─▶ Pre-facturación ─▶ Facturación ─▶ Templates ─▶ Presentaciones
                        ▲ RECHAZAR ───────┘   ▲ DESHACER ──┘
```

Al ingresar se muestra la pantalla de inicio con las tres obras sociales (AVALIAN = 10067 A.C.A. SALUD,
SANCOR = 10117, GALENO = 10099). Al elegir una aparece el menú estándar, igual para todas, y el botón
**← Volver** regresa a la pantalla de inicio. Desde ahí el administrador entra también a Auditoría, Copias de
seguridad y Usuarios.

## Secciones

| Sección | Qué hace |
|---|---|
| **Padrón** | Base de profesionales por obra social. Importar reemplaza el padrón de esa obra social. Alta, edición, baja y exportación. |
| **Valores** | Se sube el Excel de la grilla (todas las solapas) indicando el período. Dos sub-secciones: **Valores** (prestaciones unificadas) y **Unidades** (valores por unidad editables). Ver «Grillas de valores». |
| **Bot EVWEB** | Extrae de EVWEB con obra social = la elegida, estado «APROBADO EN OBRA SOCIAL», facturadas «NO» y el rango de fechas de carga que elige el usuario, fragmentado en tramos de 9 días. Usuario y contraseña de EVWEB se piden en cada extracción y no se guardan. También admite importar un Excel de EVWEB bajado a mano. |
| **Datos extraídos EVWEB** | Todo lo extraído, solo consulta, exportable a Excel. Filtros: fecha de prestación desde / hasta, cuenta - profesional, N° de transacción y texto libre. Filas idénticas no se duplican. |
| **Pre-facturación** | Se sube el archivo de prestaciones validadas y el período; «Comenzar a prefacturar» cruza cada fila con EVWEB por número de transacción, completa cuenta / matrícula / CUIT / especialidad / categoría desde el padrón y valoriza. Cada línea se puede modificar, eliminar o **Procesar** (individual o masivo). |
| **Facturación** | Líneas procesadas. Se pueden modificar o **Rechazar** (vuelven a Pre-facturación). Vista de a 1500 filas o todas, selección y **Generar template**. |
| **Templates** | `Template_facturacion_<período>_<NN>` (ej. `Template_facturacion_112026_01`). Descargar o **Deshacer** (las líneas vuelven a Facturación). |
| **Presentaciones** | GALENO: convierte `PrestacionesExport` a la `PlanillaPrestaciones_Galeno` y descarga `Anexo de prestaciones_MMAAAA`. SANCOR: agrega la columna `MP` después de `Matricula`. AVALIAN: enlace al portal. Al descargar se abre el portal de la obra social. |

## Grillas de valores

Cada obra social entrega un Excel con una solapa por especialidad y cada solapa está armada distinto. Al subirlo,
todas las solapas se unifican en dos tablas:

**Prestaciones** — código (de la obra social y/o del prestador), descripción, especialidad, cantidad de unidades
(`N/A` si es valor fijo), valor y tipo de valor (`Fijo` / `Por unidad`).

**Valores por unidad** — tipo de unidad, valor, período y especialidad. Son los que se cambian: al modificar uno se
recalculan todas las prestaciones que lo usan (`unidades × valor de la unidad`).

Cómo se normaliza cada solapa:

- El **valor de la unidad** se toma del rótulo de la solapa o sección («Valor Unidad», «V. UNIDAD», «UQ», «UHP»,
  el número bajo la fecha de vigencia). Si la solapa no lo declara pero las filas traen unidades y valor, se deduce
  (valor ÷ unidades) y queda marcado como «deducida».
- Las **unidades** de cada prestación salen de su columna (UQ, Unidades), de la tabla de niveles o complejidades de
  la solapa, o de dividir el valor por el valor de la unidad cuando da un múltiplo exacto.
- Si la solapa tiene una columna por vigencia, se usa la del período indicado (o la última anterior).
- Categorías A/B/C y recertificados generan una fila por categoría, con su propia unidad.
- Los módulos por complejidad («Complejidad 3» seguido de la lista de prácticas) asignan a cada práctica el código,
  las unidades y el valor de su complejidad.
- En los nomencladores quirúrgicos el valor es el **honorario del cirujano**; la cantidad de ayudantes queda como dato.
- Lo que no tiene valor numérico («por presupuesto», «no convenido») no se carga.

Para un mes nuevo sin Excel nuevo: **Nuevo período a partir de…** copia la grilla y solo hay que cambiar los valores
por unidad. Si el archivo subido no es una grilla (por ejemplo, el padrón), se rechaza.

Límites conocidos: las grillas son planillas armadas a mano; conviene revisar el resumen por solapa que se muestra
al subir y, ante un valor raro, las columnas Solapa y Fila del Excel exportado indican de dónde salió.

## Reglas implementadas

**Cruce (pre-facturación)**

| Obra social | N° de transacción del archivo validado | Importe |
|---|---|---|
| GALENO | `Id Transacción` (las filas con `Anulada = S` se omiten) | de la grilla, por `Practi. Presta` |
| SANCOR | `NRO ORDEN` | `IMPORTE` del archivo (la grilla queda de respaldo) |
| AVALIAN | `tranxml_id`; si no está en EVWEB, `id_autorizacion_previa` | `valor_total` del archivo (grilla de respaldo) |

- En EVWEB la columna de transacción y la del profesional se detectan por nombre (`nroAutorizacion`, `Prescriptor`/`Efector`…), igual que en el bot de Galeno. El profesional se busca en el padrón por cuenta o por nombre (exacto → contenido → por palabras).
- Estados de cruce: `OK`, `SIN EVWEB` (la transacción no está en lo extraído), `SIN PADRON` (el profesional de EVWEB no está en el padrón), `MANUAL` (corregida a mano).
- Una línea solo se puede **Procesar** si tiene cuenta, profesional, código y valor.
- Volver a subir el mismo archivo no duplica: se omiten las transacciones + código ya cargados.
- Al modificar cuenta o matrícula se completa el profesional desde el padrón; al cambiar código o categoría se toma el valor de la grilla (se puede desactivar en el diálogo).

**Template** — hoja `ImportacionesEvweb`, 22 columnas, el mismo formato que genera SEROS: `matricula` = cuenta,
`honorario` = total de la línea, `nroAutorizacion` = N° de transacción, `fecha_presentacion` = último día del mes
anterior a la fecha de generación, `cantidad` la de la línea y el resto fijo en 0 / vacío.

**Planilla GALENO** — tipo de facturación 121, N° de asociado con 10 dígitos sin barra, monto = honorario + ayudantes +
gasto + aparatología **menos el coseguro** de esa transacción (columna `Copago` del archivo validado, cruzado por
N° de transacción y práctica; se guarda al pre-facturar o se sube en Presentaciones), tipo de matrícula 1 (provincial), N° de matrícula = MP del padrón, especialidad = la del profesional en el padrón, honorarios/gastos 0-1-2.
La base de GALENO no trae MP: se toma la del mismo CUIT en los padrones de SANCOR / AVALIAN, o se carga en Padrón.

## Auditoría

Cada acción queda registrada con fecha, usuario, IP, obra social y detalle: ingresos (correctos, fallidos y
bloqueos), importaciones de padrón y grillas, extracciones de EVWEB, pre-facturaciones, cada modificación de línea
(valor anterior y nuevo), procesar / rechazar / eliminar (las líneas eliminadas se guardan completas), templates
generados, descargados y deshechos, conversiones de presentaciones, toda exportación o descarga de datos, altas y
cambios de usuarios, y copias de seguridad.

El registro es de **solo agregado**: la base rechaza cualquier modificación o borrado de la auditoría (disparadores),
y la aplicación no tiene ninguna función para hacerlo. Se consulta y exporta desde *Inicio → Auditoría* (solo
administradores).

## Copias de seguridad

- Automática cada 24 h (`BACKUP_HOURS`), conservando las últimas 30 (`BACKUP_KEEP`), en `/data/backups`. Cada copia
  se toma con la API de backup de SQLite (consistente aunque se esté trabajando) y se verifica su integridad.
- *Inicio → Copias de seguridad*: crear una copia en el momento y descargarlas (solo administradores; queda auditado).
- **Las copias están en el mismo servidor.** Descargar una periódicamente y guardarla fuera del servidor, en un lugar
  con acceso restringido: contiene los datos personales y los usuarios (las contraseñas, solo como hash).
- Restaurar: detener el servicio en Easypanel, descomprimir la copia y dejarla como `/data/facturacion.db`
  (borrar `facturacion.db-wal` y `facturacion.db-shm` si existen), y volver a iniciar.

## Archivo mensual

El período de un mes se presenta hasta el día 15 del mes siguiente; por eso, el **día 20** de cada mes (`ARCHIVE_DAY`)
la aplicación archiva sola el período anterior y todo lo más viejo: octubre se archiva el 20 de noviembre.

- Se archivan los **datos extraídos de EVWEB** (por fecha de prestación) y las **líneas ya emitidas en templates**.
  Lo que sigue pendiente en Pre-facturación o Facturación no se toca; los templates siguen descargables.
- Cada archivo es un Excel (`Archivo_<OS>_hasta_<período>_<fecha>.xlsx`) en `/data/archivo`, con una hoja por tipo de
  dato. Antes de quitar nada se hace una copia de seguridad completa y se verifica que el Excel quedó escrito.
- *Inicio → Archivo* (solo administradores): lista y descarga de archivos, y «Archivar ahora» para hacerlo a mano.
- Los archivos quedan en el mismo servidor: descargarlos y guardarlos fuera. Para volver a consultar datos
  archivados se abre el Excel; no se reincorporan a la aplicación.

## Seguridad de la información (Ley 25.326)

- **Un usuario por persona**, con roles administrador / operador. Contraseñas con scrypt (nunca en texto), mínimo 10
  caracteres con letras y números, cambio obligatorio en el primer ingreso y tras un restablecimiento.
- Bloqueo de 15 minutos tras 5 intentos fallidos y límite de intentos por IP.
- Sesiones guardadas en el servidor (solo su hash), revocables: se cierran a los 60 minutos de inactividad
  (`IDLE_MINUTES`), a las 12 h (`SESSION_HOURS`), y al desactivar al usuario o restablecer su clave.
  Cookie `HttpOnly + Secure + SameSite=Strict`; protección CSRF por cabecera.
- Cabeceras estrictas: CSP sin scripts ni estilos inline, `frame-ancestors 'none'`, HSTS, `no-store` en los datos.
- Los Excel que se descargan no contienen fórmulas provenientes de datos externos.
- Los padrones, grillas, archivos validados y templates **no se suben a GitHub** (`.gitignore`); viven en `/data`,
  con la base accesible solo para el usuario del servicio, que corre sin privilegios de root.
- Las credenciales de EVWEB no se almacenan (sí queda auditado qué usuario de EVWEB se usó).
- La base no está cifrada en disco: el cifrado en reposo depende del disco del servidor OVH. Usar siempre HTTPS
  (dominio de Easypanel con certificado) y no exponer el puerto 8000 directamente.

## Despliegue en Easypanel (servidor OVH, repo en GitHub)

1. **GitHub**: crear un repositorio **privado** vacío y subir este código:
   ```bash
   git remote add origin git@github.com:<usuario>/<repositorio>.git
   git push -u origin main
   ```
2. **Easypanel → proyecto → + Service → App**.
   - *Source*: GitHub → repositorio → rama `main` → *Build*: **Dockerfile**.
   - *Environment* (ver `.env.example`):
     ```
     ADMIN_USER=admin
     ADMIN_PASSWORD=<mínimo 10 caracteres; solo crea el administrador en el primer arranque>
     COOKIE_SECURE=true
     TZ=America/Argentina/Buenos_Aires
     ```
   - *Mounts*: **Volume** → nombre `datos` → *Mount path* `/data`. Sin este volumen los datos se pierden en cada despliegue.
   - *Domains*: dominio con HTTPS → puerto **8000**.
   - *Resources*: al menos 1 GB de RAM (Chromium). **Una sola réplica.**
3. *Deploy*. Salud: `https://<dominio>/api/health`. Activar *Auto Deploy* para redesplegar con cada `git push`.
4. Primer uso: ingresar con el administrador, crear un usuario para cada persona (*Inicio → Usuarios*), y en cada
   obra social **Padrón → Importar base** y **Valores → Subir grilla**.
5. Descargar periódicamente una copia desde *Inicio → Copias de seguridad* y guardarla fuera del servidor.

Prueba local: `docker compose up --build` → http://localhost:8000 (usuario `admin`, clave la del `docker-compose.yml`).

## Desarrollo

```bash
pip install -r requirements.txt
DATA_DIR=./data ADMIN_PASSWORD=prueba12345 COOKIE_SECURE=false uvicorn app.main:app --reload
```

Estructura: `app/evweb_bot.py` (Playwright), `app/grillas.py` (normalización de grillas), `app/logic.py` (lectura de archivos, cruce, template,
conversores), `app/main.py` (API), `app/seguridad.py` (usuarios, sesiones, auditoría, copias), `app/db.py` (SQLite), `app/static` (interfaz sin build),
`assets/PlanillaPrestaciones_Galeno.xlsx` (modelo vacío del portal de Galeno).
