# Análisis del maestro e importación del catálogo

## Fuentes revisadas

- `maestro_catalogo.csv`: 2 filas de encabezado y 17 columnas. En la revisión actual contiene 31 filas de datos y 3 códigos de proveedor (`7277`, `GA-0300`, `DOP1130`). Varias filas del mismo código aportan aplicaciones distintas; las filas sin código continúan el bloque anterior.
- `DESCRIPCION REPUESTOS v1.xlsm`: la hoja `Datos` vincula código de proveedor, marca, modelo, cilindrada, motor y años. La hoja `Resumen` presenta la aplicación redactada en la columna N, códigos OEM en Q y medidas en R. El código VBA `ObtenerDescripcion`, aportado posteriormente, define la compactación implementada en `descriptions.py`.
- En el esquema previo, `parts.sap_code` era obligatorio y `parts.supplier_code` no era único. La migración local ahora permite SAP y descripción vacíos y aplica unicidad a los códigos de proveedor informados.

## Correspondencia del CSV con SQLite

| CSV, fila 2 | Destino | Regla propuesta |
| --- | --- | --- |
| `parts.id` | `parts.id` | No importar; lo asigna SQLite. |
| `parts.supplier_code` | `parts.supplier_code` | Identifica el repuesto y agrupa filas repetidas. |
| `parts.sap_code` | `parts.sap_code` | Completar cuando venga informado. |
| `parts.description`, `parts.measure` | `parts` | Completar o actualizar según la política de conflictos. |
| `part_oem_code.part_id` | `part_oem_codes.part_id` | No importar; se obtiene del repuesto identificado. |
| `part_oem_code.oem_code` | `part_oem_codes.oem_code` | Añadir si no existe para el repuesto. |
| `part_cross_references.part_id` | `part_cross_references.part_id` | No importar; se obtiene del repuesto identificado. |
| `part_cross_references.reference_type`, `.reference_code` | `part_cross_references` | Añadir el par tipo/código si no existe. El tipo es obligatorio cuando hay código. |
| `vehicle_brands.name` | `vehicle_brands.name` | Reutilizar o crear marca. |
| `vehicle_model.name` | `vehicle_models.name` | Reutilizar o crear modelo dentro de la marca. |
| `engine_type.code`, `.description` | `engine_types` | Reutilizar o crear motor si hay código. |
| `applications.displacement`, `.year_from`, `.year_to` | `part_applications` | Crear la aplicación única del repuesto, marca, modelo, motor, cilindrada y años. |
| `applications.application_text` (opcional) | `part_applications.application_text` | Texto libre de aplicación, equivalente a la columna H del VBA; forma parte de la clave de deduplicación. |

El CSV no incluye `parts.brand_name`, `is_active` ni las fechas. `long_description` debe generarse a partir de los datos consolidados. La fila 1 del CSV agrupa visualmente columnas; la fila 2 define los nombres reales que debe leer el importador. Las variantes de nombres singulares y los errores ortográficos del encabezado deben reconocerse por alias explícitos, sin cambiar el archivo original.

## Flujo de importación propuesto

1. Leer CSV/Excel como texto para preservar ceros iniciales y códigos alfanuméricos; detectar si hay una o dos filas de encabezado.
2. Normalizar espacios y mayúsculas para búsqueda, conservando el texto original para mostrarlo. Dentro de un bloque de `supplier_code`, propagar únicamente el contexto omitido de código de proveedor, marca y modelo; al cambiar de marca se reinicia el modelo anterior.
3. Agrupar por `supplier_code` y mostrar al usuario los valores existentes del repuesto junto con los valores propuestos. Una celda vacía significa que no se aporta un cambio; el último valor no vacío reemplaza el anterior.
4. Si proveedor y SAP identifican repuestos distintos, cancelar la confirmación completa. Marcar por separado datos incompletos que impiden crear una aplicación, conservando los datos válidos del repuesto.
5. Al confirmar, insertar un repuesto nuevo o completar campos informados del existente; añadir OEM, referencias y aplicaciones mediante sus claves naturales, sin duplicados.
6. Registrar filas, cambios, conflictos y errores en staging; confirmar en una transacción y regenerar `long_description` de cada repuesto modificado.
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
