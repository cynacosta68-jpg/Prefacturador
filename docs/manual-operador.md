# Manual del operador

## 1. Para qué sirve y cómo es el recorrido

La aplicación lleva las prestaciones de AVALIAN, SANCOR y GALENO desde lo validado por la obra social hasta el archivo que se presenta. El menú es el mismo para las tres; primero elegís la obra social y después trabajás sobre ella.

Un período completo se hace en este orden:

1. **Padrón**: verificá que la base de profesionales de la obra social esté cargada y al día.
2. **Valores**: subí la grilla de valores del período.
3. **Bot EVWEB**: extraé de EVWEB las prestaciones validadas del rango de fechas.
4. **Datos extraídos EVWEB**: consultá lo extraído (opcional, es solo lectura).
5. **Pre-facturación**: subí el archivo de prestaciones validadas; la aplicación lo cruza con EVWEB y arma las líneas. Corregí lo que haga falta y procesá.
6. **Facturación**: revisá las líneas procesadas, rechazá las que estén mal y generá el template.
7. **Templates**: descargá el template generado.
8. **Presentaciones**: convertí el archivo de facturación al formato que pide cada obra social y entrá a su portal.

Los pasos 1 y 2 se hacen una vez por período. Los pasos 3 a 8 se pueden repetir las veces que haga falta dentro del mismo período.

**Formato del período.** En toda la aplicación el período se escribe como MMAAAA, sin barras ni espacios: octubre de 2026 es `102026`.

## 2. Ingreso y qué puede hacer un operador

Cada persona entra con su propio usuario. Todo lo que hacés queda registrado a tu nombre, así que no compartas tu usuario ni uses el de otra persona.

**Primer ingreso.** El administrador te da un usuario y una contraseña inicial. Al entrar, la aplicación te obliga a cambiarla antes de continuar.

**Reglas de la contraseña.** Mínimo 10 caracteres, con letras y números, y sin incluir tu nombre de usuario. Podés cambiarla cuando quieras desde la pantalla de inicio, con el botón **Cambiar contraseña**.

**Bloqueos y cierres automáticos**

- Después de 5 contraseñas incorrectas seguidas, el usuario se bloquea 15 minutos.
- La sesión se cierra sola a los 60 minutos sin actividad y, como máximo, a las 12 horas. Si pasa, volvés a ingresar y seguís: lo guardado no se pierde.
- Al terminar, usá siempre el botón **Salir**.

**Qué puede hacer el operador**

| Módulo | Operador | Solo administrador |
| --- | --- | --- |
| Padrón, Valores, Bot EVWEB, Datos extraídos | Usa todo | |
| Pre-facturación, Facturación, Templates, Presentaciones | Usa todo | |
| Auditoría | No la ve | Consulta y exporta el registro |
| Copias de seguridad | No las ve | Crea y descarga copias |
| Archivo | No lo ve | Descarga lo archivado y archiva a mano |
| Usuarios | No los ve | Crea usuarios y restablece contraseñas |

Si olvidás la contraseña o tu usuario quedó bloqueado y no podés esperar, pedile al administrador que la restablezca.

## 3. Pantalla de inicio y navegación

Al ingresar ves tres tarjetas, una por obra social: **AVALIAN** (10067, A.C.A. Salud), **SANCOR** (10117) y **GALENO** (10099). Cada tarjeta muestra cuántas líneas tenés en pre-facturación, cuántas en facturación y cuántos templates.

Hacé clic en la obra social con la que vas a trabajar. A partir de ahí:

- **Barra superior**: las ocho secciones. La sección en la que estás aparece resaltada en azul. El número al lado de cada nombre indica cuántos registros hay.
- **Segunda fila**: el botón **Volver** y el nombre de la obra social elegida.
- **Volver** te lleva a la pantalla de inicio para cambiar de obra social. No borra nada.

Todo lo que hagas en las secciones afecta solo a la obra social elegida. Antes de subir un archivo, mirá el nombre en la segunda fila para confirmar que estás en la correcta.

**Elementos que se repiten en todas las pantallas**

- **Banda azul**: muestra los totales de lo que estás viendo y los botones que actúan sobre las filas seleccionadas.
- **Casillas de selección**: la de cada fila la marca; la del encabezado marca todas las visibles.
- **Ver de a 1500 filas / todas**: las tablas largas se muestran de a 1500 filas; con las flechas pasás de página.
- **Exportar Excel**: descarga lo que estás viendo, con los filtros aplicados.
- **Diálogos**: se cierran con Cancelar o con la tecla Escape.

## 4. Padrón

El padrón es la base de profesionales de la obra social. La aplicación lo usa para completar en cada línea la cuenta, la matrícula, el CUIT, la especialidad y la categoría. Si un profesional falta o tiene un dato mal, sus líneas salen incompletas.

**Qué muestra.** Una fila por profesional: Cuenta (por ejemplo C224), Profesional, CUIT, Especialidad, Categoría, Responsabilidad fiscal y Matrícula (MP).

**Buscar.** Escribí en la casilla Buscar parte del nombre, la cuenta, el CUIT o la matrícula.

**Agregar un profesional**

1. Botón **+ Agregar**.
2. Completá los datos. El nombre es obligatorio; cargá también cuenta, categoría y matrícula para que sus líneas salgan completas.
3. **Guardar**.

**Corregir un dato.** Botón **Editar** en la fila del profesional, cambiá lo necesario y **Guardar**. Desde ese mismo diálogo se puede **Eliminar**.

**Importar la base completa**

1. Botón **Importar base (.xlsx)** y elegí el Excel de profesionales de esa obra social.
2. La aplicación avisa que va a **reemplazar** todo el padrón de esa obra social. Confirmá solo si el archivo es la base completa y actualizada.

El reemplazo borra los cambios hechos a mano que no estén en el archivo. Para un cambio puntual, usá Editar o Agregar.

**Exportar.** **Exportar Excel** descarga el padrón actual; sirve como respaldo antes de importar.

**Caso especial de GALENO.** La base de Galeno no trae la matrícula provincial. Para el anexo de Galeno, la aplicación toma la matrícula del mismo CUIT en los padrones de SANCOR o AVALIAN. Si un profesional no está en ninguno, cargá su matrícula a mano con Editar.

## 5. Valores

En Valores se carga la grilla de cada obra social. La aplicación unifica todas las solapas del Excel en una sola tabla de prestaciones y separa los valores por unidad, que son los que cambian de un período a otro.

### Subir la grilla

1. Escribí el **período de la grilla** (MMAAAA).
2. En **Archivo de la grilla**, elegí el Excel tal como lo entrega la obra social, con todas sus solapas.
3. **Subir y extraer**.

Al terminar aparece un resumen: cuántas prestaciones se unificaron, cuántas son por unidad, cuántas de valor fijo y cuántas prestaciones salió de cada solapa. Si una solapa importante figura con muy pocas, avisá al administrador.

Subir de nuevo el mismo período reemplaza la grilla anterior de ese período. Si el archivo no es una grilla (por ejemplo, el padrón), la aplicación lo rechaza y no cambia nada.

### Pestaña Valores

Muestra todas las prestaciones del período elegido.

| Columna | Qué significa |
| --- | --- |
| Código | Código de la obra social y, después de la barra, el del prestador si es distinto |
| Descripción | Nombre de la prestación; en gris, el grupo o complejidad al que pertenece |
| Especialidad | Solapa o sección de la grilla de donde salió |
| Cat. | Categoría (A, B, C) o «Recert.» para recertificados |
| Cant. unidades | Unidades de la prestación; **N/A** si el valor es fijo |
| Valor | Valor fijo, o unidades × valor de la unidad |
| Tipo de valor | **Por unidad** o **Fijo** |
| Unidad | Qué unidad usa y cuánto vale |

Filtros: período, especialidad, tipo de valor y búsqueda por código o descripción.

En las prestaciones de valor fijo, el botón **Cambiar valor** permite corregir el importe. Las que son por unidad no se editan acá: se cambian desde la pestaña Unidades.

### Pestaña Unidades

Muestra los valores por unidad del período: especialidad, tipo de unidad, período, valor y cuántas prestaciones la usan.

Para cambiar un valor:

1. Escribí el valor nuevo en la casilla de la fila (con coma para los decimales).
2. **Guardar**. La aplicación te dice cuántas prestaciones se van a recalcular.
3. Confirmá. Todas las prestaciones que usan esa unidad pasan a valer unidades × el valor nuevo.

El botón **ver** de cada fila te lleva a la pestaña Valores mostrando solo las prestaciones de esa unidad. Para volver a ver todas, usá **Quitar filtro de unidad**.

En la columna Origen: «Declarada en la grilla» es el valor escrito en el Excel; «Deducida de la grilla» se calculó a partir de las filas; «Listado general» es de referencia y no recalcula prestaciones.

### Período nuevo sin Excel nuevo

Si la obra social solo actualiza los valores de unidad:

1. Botón **Nuevo período a partir de** (el período que estás viendo).
2. Escribí el período nuevo y **Crear período**.
3. En el período nuevo, andá a Unidades y cambiá los valores que correspondan.

**Eliminar período** borra la grilla y las unidades del período que estás viendo. No afecta a las líneas ya pre-facturadas.

## 6. Bot EVWEB

El bot entra a EVWEB con tus credenciales y descarga las prestaciones validadas de la obra social elegida. Lo extraído queda guardado en Datos extraídos EVWEB y es lo que después se cruza en Pre-facturación.

**Parámetros fijos.** El bot ya sabe qué buscar; no hay que elegirlos:

- Obra social: la que elegiste al entrar (10067, 10117 o 10099).
- Estado de auditoría: APROBADO EN OBRA SOCIAL.
- Facturadas: NO.

**Lo que elegís vos:** fecha de carga desde y fecha de carga hasta.

### Hacer una extracción

1. Elegí **Fecha de carga desde** y **Fecha de carga hasta**. Debajo se muestran los tramos: el rango se divide en tramos de 9 días, porque EVWEB no devuelve bien rangos largos.
2. Escribí tu **usuario y contraseña de EVWEB**. Se usan solo para esa extracción y no se guardan.
3. **Iniciar extracción**.
4. Seguí el avance en pantalla: una barra de progreso y un registro que indica en qué tramo va. Podés pasar a otra sección; el bot sigue trabajando.
5. Al terminar, un aviso verde indica cuántas filas se descargaron y cuántas son nuevas. El enlace **Ver datos extraídos** te lleva a consultarlas.

Un mes completo son cuatro tramos y tarda varios minutos. Solo puede correr una extracción a la vez en toda la aplicación: si otra persona está extrayendo, esperá a que termine.

### Cómo leer el resultado

- **Filas nuevas menor que filas descargadas**: es normal si repetiste un rango. Las filas idénticas no se duplican.
- **Aviso amarillo «sin registros» en un tramo**: EVWEB no tenía prestaciones aprobadas en esas fechas.
- **Aviso rojo de error**: el mensaje dice en qué paso falló. Lo descargado hasta ese momento queda guardado. Los más comunes están en la sección 13.

### Si ya tenés el Excel de EVWEB

Si descargaste a mano el «Exportar prácticas Excel» de EVWEB, subílo en el recuadro inferior con **Importar archivo**. Queda guardado igual que si lo hubiera traído el bot.

## 7. Datos extraídos EVWEB

Esta sección muestra todo lo extraído de EVWEB para la obra social elegida. Es **solo de consulta**: no se puede modificar ni borrar nada desde acá.

**Filtros.** Se combinan entre sí:

| Filtro | Cómo se usa |
| --- | --- |
| Fecha desde / Fecha hasta | Limita por fecha de la prestación |
| Cuenta - profesional | Elegí de la lista o escribí parte de la cuenta o del nombre, por ejemplo «C224 - ABOUZED, Roberto Alfredo» |
| N° de transacción | Escribí el número completo o una parte |
| Texto libre | Busca en todas las columnas: afiliado, código, prestación |

**Limpiar filtros** los quita todos de una vez.

**Ver el detalle de una fila.** Hacé doble clic sobre cualquier fila y se abre un cuadro con todos sus campos, cada uno con su valor completo, sin los recortes de la tabla. Los campos vacíos no se listan. También se abre con la tecla Enter cuando la fila está seleccionada con el teclado. Se cierra con **Cerrar** o con Escape. Es solo de lectura.

**Exportar Excel** descarga las filas que estás viendo, con los filtros aplicados.

Debajo de la tabla se indica cuántas filas hay en vista, de qué fechas, y las últimas extracciones realizadas.

**Por qué pueden faltar datos viejos.** El día 25 de cada mes la aplicación archiva el período ya presentado y lo quita de esta vista (ver sección 12). Si necesitás consultar algo archivado, pedile el archivo al administrador.

## 8. Pre-facturación

Pre-facturación cruza el archivo de prestaciones validadas de la obra social con lo extraído de EVWEB, por número de transacción, y arma una línea por prestación con su profesional y su valor. Acá se corrige todo lo que haga falta antes de facturar.

**Antes de empezar**, confirmá que para esa obra social estén cargados el padrón, la grilla del período y la extracción de EVWEB de las fechas correspondientes. Si falta la extracción, todas las líneas salen «SIN EVWEB».

### Comenzar a prefacturar

1. En **Archivo de prestaciones validadas**, elegí el archivo de la obra social.
2. Escribí el **período de pre-facturación** (MMAAAA).
3. **Comenzar a prefacturar**.

Cada obra social tiene su propio archivo:

| Obra social | Archivo | Número de transacción | De dónde sale el valor |
| --- | --- | --- | --- |
| GALENO | Excel de conectividad | Id Transacción | De la grilla, por código y categoría |
| SANCOR | Excel de preliquidación | NRO ORDEN | Del importe del archivo |
| AVALIAN | Archivo CSV | tranxml_id | Del valor total del archivo |

Al terminar, un aviso resume: líneas incorporadas, cruce OK, sin EVWEB, sin padrón, sin valor, omitidas por estar ya cargadas y, en Galeno, omitidas por anuladas.

**Las líneas se acumulan.** Cada archivo nuevo suma sus líneas a las que ya están en pre-facturación; lo que no procesaste queda ahí hasta que lo proceses o lo elimines.

**Archivo repetido.** Si subís un archivo que trae transacciones ya cargadas, la importación se frena y no se importa nada. Un cuadro indica cuántas filas están repetidas, dónde están (Pre-facturación, Facturación o un template) y algunos números de ejemplo. Si es el mismo archivo, cerrá el cuadro. Si es un archivo distinto que se superpone con uno anterior, podés elegir **Importar solo las nuevas**.

**Las modificaciones valen solo para esa fila.** Cambiar la cuenta, el valor o cualquier otro dato de una línea no modifica el padrón ni las demás líneas, aunque sean del mismo profesional.

### La columna Cruce

| Estado | Qué significa | Qué hacer |
| --- | --- | --- |
| OK | La transacción está en EVWEB y el profesional está en el padrón | Revisar y procesar |
| SIN EVWEB | La transacción no está en lo extraído | Extraer el rango de fechas que falta, o completar el profesional a mano |
| SIN PADRON | EVWEB trae un profesional que no está en el padrón | Agregarlo en Padrón, o corregir la cuenta en la línea |
| MANUAL | La línea fue completada a mano | Revisar y procesar |

La columna Observación explica el motivo en cada línea. La columna Origen valor dice si el valor salió de la grilla, del archivo validado o si fue cargado a mano.

### Buscar líneas

Filtros disponibles: Período, Cruce, Cuenta - profesional, N° de transacción y Texto libre. Para trabajar las que tienen problemas, filtrá Cruce por «SIN EVWEB» o «SIN PADRON».

### Modificar una línea

1. Botón **Modificar** en la fila.
2. Cambiá lo necesario: transacción, fecha, período, afiliado, código de prestación, descripción, cantidad, valor unitario, cuenta, matrícula, profesional, CUIT, especialidad, categoría u observación.
3. **Guardar**.

Con la casilla de autocompletar tildada (viene así):

- Si cambiás la **cuenta** o la **matrícula**, la aplicación trae del padrón el profesional, CUIT, especialidad y categoría. Si la cuenta no existe en el padrón, avisa y no guarda.
- Si cambiás el **código** o la **categoría**, toma el valor de la grilla.
- Si escribís vos el **valor unitario**, se respeta el tuyo.

El total siempre es valor unitario × cantidad.

### Modificar varias a la vez

Marcá las líneas, **Modificar seleccionadas**, completá solo los campos que querés cambiar y **Aplicar**. Lo que dejés vacío no se toca.

### Eliminar

**Eliminar** en la fila, o **Eliminar seleccionadas** para varias. Pide confirmación. Una línea eliminada no se recupera desde la pantalla; queda registrada completa en la auditoría.

### Procesar

Procesar envía la línea a Facturación. Se hace con **Procesar** en la fila o con **Procesar seleccionadas**.

Una línea solo se procesa si tiene **cuenta, profesional, código de prestación y valor**. Si procesás varias y algunas no cumplen, la aplicación procesa las que sí y muestra la lista de las omitidas con lo que le falta a cada una.

En la banda azul, «Listas para procesar» y «A revisar» te dicen cuántas hay de cada tipo.

**Archivo o grilla.** Cada línea muestra dos importes para comparar: **Total archivo** (lo que informa el archivo validado) y **Valor grilla** (lo que resulta de la grilla de valores). Cuando el de la grilla difiere del total de la línea, aparece resaltado en amarillo.

Al presionar Procesar, la aplicación pregunta qué valor total tomar:

- **Valor total del archivo**: la línea queda con el importe del archivo validado.
- **Valor total de la grilla**: la línea queda con el importe de la grilla.
- **Valor actual de la línea**: la línea se procesa con el total que muestra en ese momento, sin cambiarlo. Usala cuando ya corregiste el valor a mano.

El diálogo muestra cuánto suma cada opción para las líneas seleccionadas que están en pantalla. Las líneas que no tienen valor en la fuente elegida, y las que tienen un valor cargado a mano, conservan el valor que muestran. GALENO no trae importes en su archivo, así que ahí solo está disponible la grilla.

## 9. Facturación

Facturación muestra las líneas que ya procesaste. Acá se hace la última revisión y se genera el template.

**Revisar.** Usá los mismos filtros que en Pre-facturación: Período, Cuenta - profesional, N° de transacción y Texto libre. La banda azul muestra la cantidad de líneas y el importe total de lo filtrado.

**Modificar.** Funciona igual que en Pre-facturación: **Modificar** en la fila o **Modificar seleccionadas** para varias.

**Rechazar.** Si una línea no debe facturarse todavía, **Rechazar** la devuelve a Pre-facturación. No se pierde: queda ahí para corregirla y volver a procesarla. **Rechazar seleccionadas** hace lo mismo con varias.

### Generar el template

1. Filtrá por el **período** que vas a facturar.
2. Elegí cómo ver las líneas: **de a 1500 filas** o **todas**.
3. Marcá las líneas. La casilla del encabezado marca todas las que están en pantalla.
4. **Generar template** y confirmá.
5. En el aviso final podés descargarlo en el momento o ir a Templates.

Cosas a tener en cuenta:

- Todas las líneas de un template deben ser del **mismo período**. Si mezclás períodos, la aplicación no lo genera y te avisa.
- Se genera **un solo template** con todas las líneas seleccionadas, sin tope de cantidad. La casilla del encabezado (o «Seleccionar las filtradas») marca todas las líneas que cumplen el filtro, no solo las de la página.
- Si alguna línea seleccionada no tiene cuenta, código, fecha, afiliado o valor, el template no se genera: corregila o rechazala.
- Las líneas incluidas en un template salen de Facturación y ya no se pueden modificar, salvo que deshagas el template.

## 10. Templates

Acá quedan los templates generados para la obra social elegida, del más nuevo al más viejo. Cada uno muestra su nombre, período, fecha de generación, cantidad de filas e importe.

**Nombre.** `Template_facturacion_` + período + número de orden. El segundo template de noviembre de 2026 es `Template_facturacion_112026_02`.

**Descargar.** Baja el Excel listo para importar en EVWEB. Es el formato «ImportacionesEvweb» de 22 columnas: la columna matrícula lleva la cuenta del profesional, honorario lleva el total de la línea y nroAutorizacion lleva el número de transacción.

**Deshacer.** Si el template salió mal, **Deshacer** lo elimina y devuelve todas sus líneas a Facturación, donde podés corregirlas y generar uno nuevo. Hacelo antes de importar el template en EVWEB.

Un template cuyas líneas ya fueron archivadas (ver sección 12) se puede descargar, pero no deshacer.

## 11. Presentaciones

Presentaciones prepara el archivo que se sube al portal de cada obra social. Parte del archivo de facturación **PrestacionesExport**, que se obtiene de EVWEB después de facturar. Lo que ves cambia según la obra social elegida.

### GALENO

Convierte el PrestacionesExport al formato de la planilla de prestaciones de Galeno.

1. En **Archivo «PrestacionesExport»**, elegí el archivo.
2. Escribí el **período** (MMAAAA).
3. Si el export trae facturas de varias obras sociales, escribí el **N° de factura** de Galeno para convertir solo esas filas.
4. En **Archivo validado de Galeno**, subí el archivo validado del período solo si no lo cargaste antes en Pre-facturación. De ahí salen los coseguros.
5. **Iniciar conversor**.
6. Leé los avisos (abajo) y, si está todo bien, **Descargar Anexo de prestaciones**. Se descarga `Anexo de prestaciones_MMAAAA.xlsx` y se abre el portal de Galeno en otra pestaña.

Qué lleva el anexo:

| Columna | Contenido |
| --- | --- |
| Tipo de facturación | 121 (ambulatorio) |
| N° de asociado | Los 10 primeros dígitos, sin barra |
| Importe (columna J) | Total de la fila **menos el coseguro** de esa transacción |
| N° de autorización | Número de transacción |
| Tipo de matrícula | 1 (provincial) |
| N° de matrícula | Matrícula del profesional según el padrón |
| Especialidad | Especialidad del profesional según el padrón |

El coseguro se toma de la columna Copago del archivo validado de Galeno y se cruza por número de transacción.

Avisos después de convertir:

- **Verde**: cantidad de filas convertidas.
- **Azul**: total de coseguros descontados y en cuántas filas. Compará ese total con el del archivo validado.
- **Amarillo, transacciones que no están en el archivo validado**: en esas filas no se descontó coseguro. Subí el archivo validado del período correcto y volvé a convertir.
- **Amarillo, cuentas sin matrícula o sin especialidad**: cargalas en Padrón y volvé a convertir.
- **Rojo, el coseguro supera al importe**: esas filas quedaron en 0. Revisalas antes de presentar.

Portal: webapp.galeno.com.ar/prestadores-liq-web

### SANCOR

Agrega al PrestacionesExport la columna **MP**, con la matrícula del profesional tomada del padrón, a continuación de la columna Matricula.

1. Elegí el **Archivo «PrestacionesExport»**, el **período** y, si hace falta, el **N° de factura** de Sancor.
2. **Iniciar conversor**.
3. Si aparece el aviso de cuentas sin matrícula, cargalas en Padrón y volvé a convertir.
4. **Descargar archivo convertido**. Se abre el portal de Sancor en otra pestaña.

Portal: autogestionprestadores.sancorsalud.com.ar

### AVALIAN

No requiere conversión. La sección muestra el enlace al portal y el botón **Ir a AVALIAN**.

Portal: online.avalian.com/prestador/ingreso

## 11 bis. SWISS MEDICAL (códigos 11060 y 11062)

El Reporte de Liquidación de Swiss Medical no trae importes, así que la pre-facturación lo valoriza.

- **Bot EVWEB**: extrae primero el código 11062 (I.V.A.) y después el 11060, y acumula ambos en «Datos extraídos».
- **Padrón**: el profesional se busca por el **CUIT del efector**; si ese CUIT no está, por el **código de efector**
  (columna «Efector» del padrón = «Código de Prestador Efector» del reporte), que es como se asignan los
  profesionales que facturan a través de una sociedad. De ahí salen cuenta, especialidad, categoría,
  el IVA del template y el código de obra social (11062 si es Responsable Inscripto, 11060 si no).
- **Valores**: la base de valorización de SWISS tiene dos partes, que quedan consolidadas en la solapa «Valores»:
  - **Valores fijos**: el reporte que sale del sistema (Nomenclador, Cod, Descripción, Arancel, Honorario, Gasto,
    Total prestación). Se sube cada mes indicando la **vigencia** (MMAAAA); reemplaza los valores fijos de ese período.
  - **Valores por unidades**: la tabla «Valor en unidades» (unidades del cirujano por código y tipo de nomenclador)
    y la tabla «unidades» (valor de cada unidad, que se carga cada mes con su vigencia, por archivo o editándola en
    la solapa «Unidades»). El valor es unidades × valor de la unidad; se recalcula al cambiar una unidad o con
    «Actualizar valores por unidades». «Nuevo período a partir de…» copia un período para cargarle los valores nuevos.
  - Se acepta también el Excel con las tres tablas juntas y varios períodos. Si el archivo trae su columna de
    período, manda esa; si no, la vigencia indicada al subir.
  - Si un período no tiene base cargada, se usa la grilla por especialidad (una solapa por especialidad).
- **Cómo se valoriza con la base** (contrastado con la facturación emitida de octubre 2026):
  1. Por unidades, si el código está en «Valor en unidades» bajo el nomenclador de la especialidad del profesional
     (con la unidad de su categoría: Traumatología A / B / C, Ginecología recertificados para R).
  2. Valores fijos del código: fila de la categoría del profesional con descripción «SMG» → valor fijo sin
     categoría (VF) → fila de la categoría → fila C si el profesional es R y no hay fila R. La «Consulta médica
     en consultorio» usa «consulta clínica médica» para clínica médica, medicina interna y geriatría, y «consulta
     médica» para el resto. En radiología (capítulo 34) se factura el honorario, sin el gasto.
  3. Lo cargado en «Otros» manda sobre todo lo anterior.
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
  Cada fila puede llevar una **especialidad**: ese valor rige solo para los profesionales de esa especialidad y
  manda sobre la fila general del mismo código (por ejemplo, 18010318 vale distinto para Imágenes que para
  Cardiología). La columna «Especialidad» del Excel es opcional.
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
  se puede (a) revalorizar automáticamente **según grilla** (categoría y especialidad del padrón, grilla y «Otros»,
  útil después de corregir el padrón o los valores) o **según EVWEB** (además vuelve a buscar cada transacción en
  los datos extraídos de EVWEB, toma de ahí el profesional y actualiza el cruce); (b) asignar un mismo valor unitario a todas; o (c) aplicar
  un incremento % sobre el valor de cada una. Informa cuántas cambiaron y el importe antes y después.
- **Muchas filas**: las tablas se muestran de a 200, 500 (por defecto) o 1.500 filas; «todas» solo aparece si hay
  hasta 2.000. La casilla de la cabecera y «Seleccionar las filtradas» seleccionan todas las líneas que cumplen
  el filtro, también las de otras páginas, y las acciones masivas actúan sobre todas ellas. La base de datos
  cuenta, suma y pagina, y las respuestas viajan comprimidas.
- **Filtro «Valor unitario»**: Todos / Sin valor / Con valor.
- **Borrar valores en bloque**: en Valores, tanto en la solapa «Valores» (prestaciones de la grilla) como en «Otros»,
  se tildan las filas —o la casilla de la cabecera para todas las de la página— y «Eliminar seleccionadas».
  Pide confirmación y deja en la auditoría lo que se borró.
- **Presentaciones (SWISS)**: conversor del «PrestacionesExport»: agrega la columna **MP** (matrícula del padrón) al
  lado de Matricula, igual que SANCOR, y la columna **Total** a continuación de IVA = Honorarios + IVA − Coseguro
  (el IVA es el 10,5 % del honorario cuando la columna IVA vale 1). El coseguro es la columna Copago del reporte de
  liquidación, cruzada por número de transacción: se toma del reporte cargado en Pre-facturación o del que se
  suba en el momento. Informa honorarios, coseguros descontados, filas con IVA y total; avisa las transacciones
  sin cruce y las que tienen un coseguro mayor al honorario (quedan en 0 para revisar).
- **Templates**: un solo template con todas las líneas seleccionadas, sin dividir por cantidad de filas.
- **Orden de las columnas**: en Pre-facturación, Facturación y Emitidas se puede arrastrar el encabezado de una columna
  hasta otro lugar; el orden queda guardado en ese navegador y «Restablecer columnas» vuelve al original.
- **Incremento %**: al modificar una línea (o varias a la vez) en Pre-facturación o Facturación se puede indicar
  un porcentaje sobre el valor unitario (negativo = descuento). Queda anotado en el origen del valor, en la
  observación de la línea y en la auditoría.
- **Pre-facturación**: «Cruzar y valorizar según grilla» (sin EVWEB), «Cruzar y validar según EVWEB» y «Reiniciar».
- **Datos extraídos EVWEB** (todas las obras sociales): botón «Quitar datos EVWEB»; si no se usa, el archivo
  del día 25 los retira solo.

## 12. Archivo mensual, auditoría y cuidado de los datos

### Archivo del día 25

El período de un mes se presenta hasta el día 15 del mes siguiente. Por eso, el **día 25 de cada mes** la aplicación archiva sola el período anterior y todo lo más viejo: octubre se archiva el 25 de noviembre.

| Se archiva y sale de la vista | No se toca |
| --- | --- |
| Los datos extraídos de EVWEB de ese período | Las líneas que siguen en Pre-facturación |
| Las líneas ya incluidas en templates | Las líneas que siguen en Facturación |
| | Los templates, que siguen descargables |
| | El padrón y las grillas de valores |

Qué implica para tu trabajo:

- Terminá de procesar, generar los templates y presentar el período **antes del día 25**.
- Después del 20, los datos de EVWEB de ese período ya no están para cruzar. Si te queda una pre-facturación atrasada, las líneas saldrán «SIN EVWEB» y habrá que extraer de nuevo ese rango.
- Lo archivado no se borra: queda en un Excel que el administrador puede descargar.

### Auditoría

Cada acción queda registrada con fecha, hora, usuario y detalle: ingresos, importaciones, extracciones, cada modificación de línea con el valor anterior y el nuevo, líneas procesadas, rechazadas y eliminadas, templates, conversiones y toda descarga o exportación. El registro no se puede modificar ni borrar. Solo el administrador lo consulta.

### Cuidado de los datos

La aplicación maneja datos personales y de salud de afiliados y profesionales.

- No compartas tu usuario ni tu contraseña.
- Usá **Salir** al terminar y no dejes la sesión abierta en una computadora compartida.
- Los Excel que descargás contienen datos personales: guardalos solo donde corresponda y borralos cuando ya no los necesites.
- No envíes esos archivos por canales no autorizados.

## 13. Problemas frecuentes

| Qué pasa | Causa probable | Qué hacer |
| --- | --- | --- |
| «Sesión vencida. Volvé a ingresar» | Pasaron 60 minutos sin actividad | Ingresá de nuevo; lo guardado no se pierde |
| «Usuario bloqueado por intentos fallidos» | 5 contraseñas incorrectas | Esperá 15 minutos o pedí al administrador que la restablezca |
| «El período debe tener formato MMAAAA» | Período mal escrito | Escribilo con 6 dígitos, por ejemplo 102026 |
| «El archivo no parece una grilla de valores» | Subiste otro archivo en Valores (por ejemplo, el padrón) | Subí el Excel de la grilla; el padrón va en Padrón |
| Bot: «Login fallido» | Usuario o contraseña de EVWEB incorrectos | Verificá las credenciales entrando a EVWEB a mano |
| Bot: «no apareció el menú Facturación» | EVWEB lento o con cambios | Reintentá en unos minutos; si se repite, avisá al administrador |
| «Ya hay una extracción en curso» | Otra persona está usando el bot | Esperá a que termine |
| El bot termina con «sin registros» | No hay prestaciones aprobadas y no facturadas en esas fechas | Revisá el rango de fechas |
| Todas las líneas salen «SIN EVWEB» | Falta la extracción de ese rango, o ya fue archivada | Hacé la extracción y volvé a subir el archivo validado |
| Líneas «SIN PADRON» | El profesional no está en el padrón de esa obra social | Agregalo en Padrón, o corregí la cuenta en la línea |
| «Sin valor» en líneas de Galeno | Falta la grilla del período, o el código no está en la grilla | Subí la grilla, o cargá el valor unitario a mano |
| No deja procesar una línea | Le falta cuenta, profesional, código o valor | Modificala y completá lo que indica el aviso |
| «La cuenta / matrícula indicada no existe en el padrón» | Escribiste una cuenta que no está cargada | Verificá la cuenta, o agregá al profesional en Padrón |
| «Las filas seleccionadas son de períodos distintos» | Marcaste líneas de más de un período | Filtrá por período antes de seleccionar |
| El template no se genera por filas incompletas | Alguna línea no tiene cuenta, código, fecha, afiliado o valor | Corregila o rechazala |
| Presentaciones: «no parece ser un PrestacionesExport» | Subiste otro archivo | Subí el export de facturación de EVWEB |
| Anexo de Galeno sin coseguros descontados | El archivo validado cargado es de otro período | Subí el archivo validado del período del export y volvé a convertir |
| «Las líneas de este template ya fueron archivadas» | Pasó el día 25 | No se puede deshacer; consultá al administrador |

Si el problema no figura acá, anotá el mensaje exacto, la obra social y lo que estabas haciendo, y avisá al administrador. Con la hora aproximada puede ubicar la acción en la auditoría.
