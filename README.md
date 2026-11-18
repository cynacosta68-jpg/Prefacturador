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
- Cada línea guarda el valor del archivo validado y el de la grilla (columnas «Total archivo» y «Valor grilla»; la
  segunda se resalta cuando difiere del total). Al **Procesar** se pregunta cuál tomar; las líneas sin valor en la
  fuente elegida, o con valor cargado a mano, conservan el que tienen.
- Una línea solo se puede **Procesar** si tiene cuenta, profesional, código y valor.
- Las líneas se acumulan entre archivos. Si un archivo trae transacciones + código ya cargados, la importación se
  frena completa (respuesta 409) y se informa cuántas son y dónde están; el operador puede elegir importar solo las
  nuevas. El mismo archivo se reconoce además por su huella (tabla `importaciones`).
- Modificar una línea afecta solo a esa línea: no toca el padrón ni otras líneas del mismo profesional.
- Al modificar cuenta o matrícula se completa el profesional desde el padrón; al cambiar código o categoría se toma el valor de la grilla (se puede desactivar en el diálogo).

**Template** — hoja `ImportacionesEvweb`, 22 columnas, el mismo formato que genera SEROS: `matricula` = cuenta,
`honorario` = total de la línea, `nroAutorizacion` = N° de transacción, `fecha_presentacion` = último día del mes
anterior a la fecha de generación, `cantidad` la de la línea y el resto fijo en 0 / vacío.

**Planilla GALENO** — tipo de facturación 121, N° de asociado con 10 dígitos sin barra, monto = honorario + ayudantes +
gasto + aparatología **menos el coseguro** de esa transacción (columna `Copago` del archivo validado, cruzado por
N° de transacción y práctica; se guarda al pre-facturar o se sube en Presentaciones), tipo de matrícula 1 (provincial), N° de matrícula = MP del padrón, especialidad = la del profesional en el padrón, honorarios/gastos 0-1-2.
La base de GALENO no trae MP: se toma la del mismo CUIT en los padrones de SANCOR / AVALIAN, o se carga en Padrón.

## SWISS MEDICAL (códigos 11060 y 11062)

El Reporte de Liquidación de Swiss Medical no trae importes, así que la pre-facturación lo valoriza.

- **Bot EVWEB**: extrae primero el código 11062 (I.V.A.) y después el 11060, y acumula ambos en «Datos extraídos».
- **Padrón**: el profesional se busca por el **CUIT del efector**. De ahí salen cuenta, especialidad, categoría,
  el IVA del template y el código de obra social (11062 si es Responsable Inscripto, 11060 si no).
- **Valores**: acepta la grilla de Swiss (Excel con una solapa por especialidad) o la base estructurada del
  proceso anterior (solapas Nomenclador, unidades y Valor Fijos).
- **Reporte**: se aceptan los dos formatos de encabezados (el anterior y el actual).
- **Valorización con la grilla**:
  - Prácticas: por código. Si la solapa tiene columnas Cirujano A / B / C se usa la categoría del profesional;
    si tiene valor para recertificados se usa cuando la categoría es R.
  - Consultas (códigos 42…): la grilla las lista por tipo y no por código. Reglas (contrastadas con la
    facturación emitida de octubre 2026): pediatras → Consulta PEDIATRA; «Consulta médica en consultorio»
    de clínica médica, medicina interna, geriatría, cardiología, cirugía general y gastroenterología →
    CONSULTA CLINICOS; reumatología, infectología y psiquiatría → su renglón; el resto (incluye Médico y
    Medicina General) → Consulta A / B / C especialistas según la categoría.
  - Categoría R: cobra el valor recertificado (también los especialistas, que no tienen renglón propio).
  - El código del reporte es el de Swiss (SMMP): manda esa columna de la grilla y no la del código del Colegio.
  - Si el código figura en dos solapas con valores distintos se toma el primero y queda anotado.
- **IVA**: el padrón tiene «Código de IVA», que sale siempre de la responsabilidad fiscal (Responsable
  Inscripto = 1, el resto = 0). La línea lleva IVA 1 solo si el profesional tiene código 1 y el afiliado es
  Gravado. En Pre-facturación y Facturación se puede filtrar por condición del profesional y del afiliado,
  «Seleccionar las filtradas» y «Asignar IVA» (1 = calcula IVA, 0 = no calcula IVA) en bloque.
- **ARCA (vía Arcanum)**: «Padrón → Actualizar condición desde ARCA» consulta en ARCA la Constancia de
  Inscripción de cada profesional (por CUIT), y actualiza la responsabilidad fiscal y el código de IVA de los
  que cambiaron. Hace copia de seguridad antes, corre en segundo plano y al terminar muestra los cambios, los
  CUIT sin dato y los que no se pudieron consultar. No da de alta ni de baja profesionales. En el formulario
  de cada profesional hay un botón «Consultar ARCA» para un solo CUIT. Usa el mismo Arcanum que el Portal de
  Cuentas a Pagar: variables `ARCANUM_URL` (en el mismo proyecto de Easypanel, `http://arcanum:8094`),
  `ARCANUM_API_KEY` y `ARCANUM_CUIT` (CUIT del certificado cargado en Arcanum).
- **Otros (Valores → solapa «Otros»)**: valores cargados a mano, que **mandan sobre la grilla**: sirven para
  prestaciones que la grilla no trae y para corregir un valor sin tocar la grilla. Cada
  fila tiene código, descripción, vigencia desde (MMAAAA), valor para todas las categorías y valor para la
  categoría R (vacío = igual al general). La pre-facturación usa la vigencia más reciente que no supere el mes de la prestación; si el código
  no está en «Otros», usa la grilla. Cuando reemplaza un valor de la grilla, la línea lo deja anotado. Para un valor nuevo se agrega otra fila con la nueva
  vigencia. Se puede agregar, editar, importar y exportar en Excel (columnas Código, Descripción, Vigencia,
  Valor, Valor R). Vale para todas las obras sociales.
- **Código 29010230** (Polisomnografía sin CPAP): figura en dos solapas; se usa el valor de Neurología.
- **Código propuesto** (SWISS): la línea conserva el código del archivo validado («Cód. archivo») y al lado muestra
  el «Cód. propuesto» por la aplicación, con la leyenda «Difieren cód.» o «Coinciden códigos» (se puede filtrar
  por esa leyenda). Se propone otro código cuando el archivo trae una consulta (4201…) que no es la de la
  especialidad del profesional —la genérica 42010100 o la de otra especialidad— y esa especialidad tiene código
  propio; y para los códigos que se facturan con otro (180101 → 18010301, 290102 → 29010203). El valor se
  calcula siempre con el código propuesto. Al **Procesar**, si alguna línea difiere, se pregunta si queda el
  código del archivo o el propuesto. La consulta de Pediatría hecha por una especialidad infantil se valoriza
  como consulta de pediatra.
- **Revalorizar seleccionadas** (Pre-facturación y Facturación): con las líneas elegidas —o todas las filtradas—
  se puede (a) volver a valorizar con lo cargado ahora (categoría y especialidad del padrón, grilla y «Otros»),
  útil después de corregir el padrón o los valores; (b) asignar un mismo valor unitario a todas; o (c) aplicar
  un incremento % sobre el valor de cada una. Informa cuántas cambiaron y el importe antes y después.
- **Muchas filas**: las tablas se muestran de a 200, 500 (por defecto) o 1.500 filas; «todas» solo aparece si hay
  hasta 2.000. La casilla de la cabecera y «Seleccionar las filtradas» seleccionan todas las líneas que cumplen
  el filtro, también las de otras páginas, y las acciones masivas actúan sobre todas ellas. La base de datos
  cuenta, suma y pagina, y las respuestas viajan comprimidas.
- **Filtro «Valor unitario»**: Todos / Sin valor / Con valor.
- **Incremento %**: al modificar una línea (o varias a la vez) en Pre-facturación o Facturación se puede indicar
  un porcentaje sobre el valor unitario (negativo = descuento). Queda anotado en el origen del valor, en la
  observación de la línea y en la auditoría.
- **Pre-facturación**: «Cruzar y valorizar según grilla» (sin EVWEB), «Cruzar y validar según EVWEB» y «Reiniciar».
- **Datos extraídos EVWEB** (todas las obras sociales): botón «Quitar datos EVWEB»; si no se usa, el archivo
  del día 20 los retira solo.

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
