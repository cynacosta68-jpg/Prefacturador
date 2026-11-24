# Instructivo paso a paso

Recorrido completo de un período con capturas de pantalla, usando SANCOR como ejemplo. Los pasos son los mismos para AVALIAN y GALENO. Los nombres y números que se ven en las capturas son datos de demostración.

## 1. Ingresar a la aplicación

![ingreso](01_ingreso.png)

1. Escribí tu **usuario** y tu **contraseña**.
2. Presioná **Ingresar**.

Después de 5 contraseñas incorrectas, el usuario se bloquea 15 minutos.

## 2. Cambiar la contraseña en el primer ingreso

![cambio de contraseña](02_cambio_de_contrasena.png)

La primera vez, la aplicación te obliga a cambiar la contraseña inicial.

1. Escribí la **contraseña actual** (la que te dio el administrador).
2. Escribí la **nueva** dos veces: mínimo 10 caracteres, con letras y números.
3. **Guardar**.

## 3. Elegir la obra social

![inicio](03_inicio.png)

1. En la pantalla de inicio, hacé clic en la tarjeta de la obra social con la que vas a trabajar.
2. Aparece el menú con las ocho secciones. El botón **Volver** te trae de nuevo a esta pantalla.

Cada tarjeta muestra cuántas líneas tenés en pre-facturación, en facturación y cuántos templates.

## 4. Padrón: cargar la base de profesionales

![padrón](04_padron.png)

1. Entrá a **Padrón**.
2. Presioná **Importar base (.xlsx)** y elegí el Excel de profesionales de esa obra social.
3. Verificá que la lista muestre cuenta, profesional, CUIT, especialidad, categoría y matrícula.

Importar reemplaza todo el padrón de esa obra social. Hacelo solo con la base completa y actualizada.

## 5. Padrón: corregir un profesional

![editar profesional](05_padron_editar.png)

1. En la fila del profesional, presioná **Editar**.
2. Cambiá el dato que corresponda.
3. **Guardar**. Para sumar uno nuevo, usá **+ Agregar**.

## 6. Valores: subir la grilla

![subir grilla](06_valores_subir.png)

1. Entrá a **Valores**.
2. Escribí el **período de la grilla** con formato MMAAAA (octubre de 2026 es 102026).
3. En **Archivo de la grilla**, elegí el Excel tal como lo entrega la obra social, con todas sus solapas.
4. Presioná **Subir y extraer**.

## 7. Valores: revisar las prestaciones

![tabla de valores](07_valores_tabla.png)

1. Leé el aviso verde: indica cuántas prestaciones se unificaron y cuántas salieron de cada solapa.
2. En la pestaña **Valores** está cada prestación con su código, especialidad, cantidad de unidades, valor y tipo de valor (por unidad o fijo).
3. Usá los filtros de período, especialidad, tipo de valor y búsqueda.

## 8. Valores: cambiar un valor por unidad

![unidades](08_valores_unidades.png)

1. Pasá a la pestaña **Unidades**.
2. Escribí el valor nuevo en la casilla de la fila.
3. Presioná **Guardar** y confirmá. Se recalculan todas las prestaciones que usan esa unidad.

El botón **ver** muestra qué prestaciones dependen de esa unidad.

## 9. Bot EVWEB: extraer las prestaciones validadas

![bot evweb](09_bot_evweb.png)

1. Entrá a **Bot EVWEB**. Obra social, estado de auditoría y «facturadas» ya vienen fijos.
2. Elegí **Fecha de carga desde** y **hasta**. Debajo se muestran los tramos de 9 días.
3. Escribí tu **usuario y contraseña de EVWEB**. No se guardan.
4. Presioná **Iniciar extracción** y esperá el aviso verde de finalización.

Si ya tenés el Excel de EVWEB descargado, cargalo en el recuadro inferior con **Importar archivo**.

## 10. Datos extraídos EVWEB: consultar

![datos extraídos](10_datos_extraidos.png)

1. Entrá a **Datos extraídos EVWEB**. Es solo de consulta.
2. Filtrá por **fecha desde / hasta**, **cuenta - profesional**, **N° de transacción** o **texto libre**.
3. **Exportar Excel** descarga lo que estás viendo.

## 11. Datos extraídos EVWEB: ver el detalle de una fila

![detalle de la fila](11_datos_extraidos_detalle.png)

1. Hacé **doble clic** sobre una fila.
2. Se abre el detalle con todos los campos de esa fila.
3. Cerralo con **Cerrar** o con la tecla Escape.

## 12. Pre-facturación: subir el archivo validado

![subir archivo validado](12_prefacturacion_subir.png)

1. Entrá a **Pre-facturación**.
2. En **Archivo de prestaciones validadas**, elegí el archivo de la obra social.
3. Escribí el **período de pre-facturación** (MMAAAA).
4. Presioná **Comenzar a prefacturar**.

## 13. Pre-facturación: leer el resultado del cruce

![resultado del cruce](13_prefacturacion_resultado.png)

1. El aviso resume cuántas líneas se incorporaron y cuántas quedaron con cruce OK, sin EVWEB, sin padrón o sin valor.
2. La banda azul muestra cuántas están **listas para procesar** y cuántas hay **a revisar**.
3. La columna **Cruce** de cada línea indica su estado.

## 14. Pre-facturación: encontrar las líneas a revisar

![líneas sin evweb](14_prefacturacion_sin_evweb.png)

1. En el filtro **Cruce**, elegí «SIN EVWEB» o «SIN PADRON».
2. Quedan en pantalla solo las líneas que necesitan corrección.

## 15. Pre-facturación: modificar una línea

![modificar línea](15_prefacturacion_modificar.png)

1. Presioná **Modificar** en la fila.
2. Escribí la **cuenta** del profesional: el nombre, CUIT, especialidad y categoría se completan desde el padrón.
3. Podés cambiar también código, cantidad, valor unitario o cualquier otro campo.
4. **Guardar**.

## 16. Pre-facturación: comparar archivo y grilla

![valores de archivo y grilla](16_prefacturacion_valores.png)

1. Desplazá la tabla hacia la derecha.
2. Compará **Total**, **Total archivo** y **Valor grilla** de cada línea.
3. Cuando el valor de la grilla difiere del total, aparece resaltado en amarillo.

## 17. Pre-facturación: procesar y elegir el valor

![archivo o grilla](17_procesar_archivo_o_grilla.png)

1. Marcá las líneas (la casilla del encabezado marca todas las visibles).
2. Presioná **Procesar seleccionadas**.
3. Elegí qué valor total tomar: **del archivo** o **de la grilla**. El cuadro muestra cuánto suma cada opción.

## 18. Pre-facturación: revisar las omitidas

![líneas omitidas](18_procesar_resultado.png)

1. Las líneas completas pasan a Facturación.
2. Si alguna no se pudo procesar, la aplicación lista cuál es y qué le falta.
3. Corregila con **Modificar** y volvé a procesarla.

## 19. Facturación: revisar

![facturación](19_facturacion.png)

1. Entrá a **Facturación**.
2. Revisá las líneas. Podés **Modificar** cualquiera.
3. Si una no debe facturarse todavía, **Rechazar** la devuelve a Pre-facturación.

## 20. Facturación: generar el template

![confirmar template](20_facturacion_confirmar.png)

1. Filtrá por el período y marcá las líneas.
2. Presioná **Generar template**.
3. Confirmá.

Todas las líneas de un template deben ser del mismo período.

## 21. Template generado

![template generado](21_template_generado.png)

1. La aplicación informa el nombre del template y la cantidad de filas.
2. Podés **Descargar** en el momento o **Ir a Templates**.

## 22. Templates: descargar o deshacer

![templates](22_templates.png)

1. En **Templates** están todos los generados, con período, fecha, filas e importe.
2. **Descargar** baja el Excel para importar en EVWEB.
3. **Deshacer** elimina el template y devuelve sus líneas a Facturación.

## 23. Presentaciones: convertir y presentar

![presentaciones](23_presentaciones.png)

1. Entrá a **Presentaciones**.
2. Elegí el archivo **PrestacionesExport** y escribí el **período**.
3. Presioná **Iniciar conversor** y leé los avisos.
4. Presioná **Descargar**: baja el archivo convertido y se abre el portal de la obra social.

En GALENO se genera el Anexo de prestaciones y se descuentan los coseguros. En SANCOR se agrega la columna MP. AVALIAN solo muestra el enlace al portal.

## 24. Terminar

![inicio con totales](24_inicio_con_totales.png)

1. Con **Volver** regresás a la pantalla de inicio, que muestra cómo quedó cada obra social.
2. Al terminar, presioná siempre **Salir**.
