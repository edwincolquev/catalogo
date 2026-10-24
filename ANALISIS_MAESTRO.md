# Análisis del maestro e importación del catálogo

## Fuentes revisadas

- `maestro_catalogo v2.csv`: 2 filas de encabezado y 15 columnas, sin las columnas `part_oem_code.part_id` y `part_cross_references.part_id`. En la revisión actual contiene 31 filas de datos y 3 códigos de proveedor (`7277`, `GA-0300`, `DOP1130`). Varias filas del mismo código aportan OEM, referencias o aplicaciones distintas; las filas sin código continúan el bloque anterior.
- `DESCRIPCION REPUESTOS v1.xlsm`: la hoja `Datos` vincula código de proveedor, marca, modelo, cilindrada, motor y años. La hoja `Resumen` presenta la aplicación redactada en la columna N, códigos OEM en Q y medidas en R. El código VBA `ObtenerDescripcion`, aportado posteriormente, define la compactación implementada en `descriptions.py`.
- En el esquema previo, `parts.sap_code` era obligatorio y `parts.supplier_code` no era único. La migración local ahora permite SAP y descripción vacíos y aplica unicidad a los códigos de proveedor informados.

## Correspondencia del CSV con SQLite

Desde el 24 de octubre de 2026, SQLite usa tablas y campos en español. Se conservan los encabezados del CSV anterior como alias de importación. También se admiten directamente los nombres de destino indicados abajo; véase [DICCIONARIO_DATOS.md](DICCIONARIO_DATOS.md).

La ampliación de unidad, marca comercial, categoría, estado y valores comerciales se describe en [GESTION_COMERCIAL.md](GESTION_COMERCIAL.md). Los maestros anteriores pueden seguir usándose sin esas columnas.

| CSV anterior, fila 2 | Destino actual | Regla |
| --- | --- | --- |
| `parts.id` | `repuestos.id` | No importar; lo asigna SQLite. |
| `parts.supplier_code` | `repuestos.codigo_proveedor` | Identifica el repuesto y agrupa filas repetidas. |
| `parts.sap_code` | `repuestos.codigo_sap` | Completar cuando venga informado. |
| `parts.description`, `parts.measure` | `repuestos.descripcion`, `.medida` | Completar o actualizar según la política de conflictos. |
| `part_oem_code.part_id` (ausente en v2) | `codigos_oem.repuesto_id` | Se obtiene del repuesto identificado por el código de proveedor. |
| `part_oem_code.oem_code` | `codigos_oem.codigo_oem` | Añadir si no existe para el repuesto. |
| `part_cross_references.part_id` (ausente en v2) | `referencias_cruzadas.repuesto_id` | Se obtiene del repuesto identificado por el código de proveedor. |
| `part_cross_references.reference_type`, `.reference_code` | `referencias_cruzadas.tipo_referencia`, `.codigo_referencia` | Añadir el par tipo/código si no existe. El tipo es obligatorio cuando hay código. |
| `vehicle_brands.name` | `marcas_vehiculos.nombre` | Reutilizar o crear marca. |
| `vehicle_model.name` | `modelos_vehiculos.nombre` | Reutilizar o crear modelo dentro de la marca. |
| `engine_type.code`, `.description` | `tipos_motor.codigo`, `.descripcion` | Reutilizar o crear motor si hay código. |
| `applications.displacement`, `.year_from`, `.year_to` | `aplicaciones_repuestos.cilindrada`, `.anio_desde`, `.anio_hasta` | Crear la aplicación única del repuesto, marca, modelo, motor, cilindrada y años. |
| `applications.application_text` (opcional) | `aplicaciones_repuestos.texto_aplicacion` | Texto libre de aplicación, equivalente a la columna H del VBA; forma parte de la clave de deduplicación. |

El CSV del ejemplo no incluye marca comercial, `activo` ni las fechas. La marca comercial ahora se almacena en `marcas_repuestos` y se vincula por `repuestos.marca_id`; el encabezado `repuestos.nombre_marca` sigue aceptándose. `descripcion_larga` se genera a partir de los datos consolidados. La fila 1 del CSV agrupa visualmente columnas; la fila 2 define los nombres que debe leer el importador. Se admiten tanto los encabezados anteriores como los nombres actuales en español.

## Flujo de importación propuesto

1. Leer CSV/Excel como texto para preservar ceros iniciales y códigos alfanuméricos; detectar si hay una o dos filas de encabezado.
2. Normalizar espacios y mayúsculas para búsqueda, conservando el texto original para mostrarlo. Dentro de un bloque de `supplier_code`, propagar únicamente el contexto omitido de código de proveedor, marca y modelo; al cambiar de marca se reinicia el modelo anterior.
3. Agrupar por `supplier_code` y mostrar al usuario los valores existentes del repuesto junto con los valores propuestos. Una celda vacía significa que no se aporta un cambio; el último valor no vacío reemplaza el anterior.
4. Si proveedor y SAP identifican repuestos distintos, cancelar la confirmación completa. Marcar por separado datos incompletos que impiden crear una aplicación, conservando los datos válidos del repuesto.
5. Al confirmar, insertar un repuesto nuevo o completar campos informados del existente; añadir OEM, referencias y aplicaciones mediante sus claves naturales, sin duplicados.
6. Registrar filas, cambios, conflictos y errores en `filas_importacion`; confirmar en una transacción y regenerar `descripcion_larga` de cada repuesto modificado.
7. Permitir buscar y editar en Streamlit repuestos, OEM, referencias y aplicaciones; mostrar el origen de cada importación y la descripción generada.

## Datos del ejemplo que requieren revisión

- `GA-0300` tiene marcas y valores como `D-60` y `C-60` en la columna de motor, pero no tiene modelo. La relación de aplicación no puede completarse con seguridad.
- En `DOP1130`, varios valores de `engine_type.code` ya incluyen motores, años y texto de redacción, por ejemplo `2Y 3Y DEL 85 AL 88;`. No son códigos de motor atómicos.
- `TOYOTA:` contiene puntuación final; podría normalizarse a `TOYOTA` para evitar una marca duplicada.
- La última fila de `DOP1130` deja vacío `parts.supplier_code`, siguiendo el bloque anterior. La regla de continuidad debe ser explícita.

## Decisiones confirmadas y pendientes

1. Confirmado: `supplier_code` es único en todo el catálogo.
2. Confirmado: un valor nuevo no vacío reemplaza el anterior; vacío significa conservar.
3. Implementado: se muestra una descripción larga en varias líneas y un resumen de aplicaciones en una línea, siguiendo las reglas de `ObtenerDescripcion` del VBA aportado por el usuario.
4. Pendiente de limpieza manual: filas sin modelo y textos compuestos en la columna de motor. Se advierten y se omiten esas aplicaciones.
