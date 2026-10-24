# Diccionario de datos del catálogo

Esquema SQLite en español desde el 24 de octubre de 2026. Incluye trece tablas y la vista `vista_repuestos`. Los nombres técnicos usan minúsculas, guiones bajos y letras sin tilde; por ejemplo, `anio_desde`.

| Tabla anterior | Tabla actual | Contenido |
| --- | --- | --- |
| `parts` | `repuestos` | Datos principales y descripción generada de cada repuesto. |
| `part_oem_codes` | `codigos_oem` | Códigos originales asociados a cada repuesto. |
| `part_cross_references` | `referencias_cruzadas` | Equivalencias por tipo y código de referencia. |
| `vehicle_brands` | `marcas_vehiculos` | Marcas de los vehículos. |
| `vehicle_models` | `modelos_vehiculos` | Modelos de vehículos, vinculados a una marca. |
| `engine_types` | `tipos_motor` | Códigos y descripciones de los motores. |
| `part_applications` | `aplicaciones_repuestos` | Vehículos y motores compatibles con cada repuesto, con cilindrada, años y texto adicional. |
| `import_batches` | `lotes_importacion` | Historial de archivos cargados y su estado de procesamiento. |
| `import_staging_rows` | `filas_importacion` | Detalle, validaciones y datos originales de cada fila importada. |
| Nueva | `unidades_medida` | Unidades como Pieza, Juego o Metro. |
| Nueva | `marcas_repuestos` | Marcas comerciales de los repuestos. |
| Nueva | `categorias_repuestos` | Categorías dentro de cada marca comercial. |
| Nueva | `historial_estados` | Estado inicial y cambios del seguimiento comercial. |

## Campos por tabla

### `repuestos`

| Campo anterior | Campo actual | Tipo | Relación |
| --- | --- | --- | --- |
| `id` | `id` | INTEGER | Clave primaria |
| `sap_code` | `codigo_sap` | TEXT |  |
| `supplier_code` | `codigo_proveedor` | TEXT |  |
| `description` | `descripcion` | TEXT |  |
| `measure` | `medida` | TEXT |  |
| `brand_name` / `nombre_marca` | `marca_id` | INTEGER | `marcas_repuestos.id`; nombre disponible en `vista_repuestos.nombre_marca`. |
| Nuevo | `unidad_id` | INTEGER | `unidades_medida.id` |
| Nuevo | `categoria_id` | INTEGER | `categorias_repuestos.id`; debe corresponder a `marca_id`. |
| Nuevo | `estado_gestion` | TEXT | Etapa comercial, desde `propuesto` hasta `en_sap` o `rechazado`. |
| Nuevo | `minimo_compra` | REAL | Cantidad mínima mayor que cero, opcional. |
| Nuevo | `precio_compra` | REAL | Precio unitario en USD, opcional y no negativo. |
| Nuevo | `precio_venta` | REAL | Precio unitario en USD, opcional y no negativo. |
| Nuevo | `cantidad_compra` | REAL | Cantidad prevista, opcional y no negativa. |
| `long_description` | `descripcion_larga` | TEXT |  |
| `is_active` | `activo` | INTEGER |  |
| `created_at` | `fecha_creacion` | TEXT |  |
| `updated_at` | `fecha_actualizacion` | TEXT |  |

### `codigos_oem`

| Campo anterior | Campo actual | Tipo | Relación |
| --- | --- | --- | --- |
| `id` | `id` | INTEGER | Clave primaria |
| `part_id` | `repuesto_id` | INTEGER | `repuestos.id` |
| `oem_code` | `codigo_oem` | TEXT |  |
| `created_at` | `fecha_creacion` | TEXT |  |

### `referencias_cruzadas`

| Campo anterior | Campo actual | Tipo | Relación |
| --- | --- | --- | --- |
| `id` | `id` | INTEGER | Clave primaria |
| `part_id` | `repuesto_id` | INTEGER | `repuestos.id` |
| `reference_type` | `tipo_referencia` | TEXT |  |
| `reference_code` | `codigo_referencia` | TEXT |  |
| `created_at` | `fecha_creacion` | TEXT |  |

### `marcas_vehiculos`

| Campo anterior | Campo actual | Tipo | Relación |
| --- | --- | --- | --- |
| `id` | `id` | INTEGER | Clave primaria |
| `name` | `nombre` | TEXT |  |
| `created_at` | `fecha_creacion` | TEXT |  |

### `modelos_vehiculos`

| Campo anterior | Campo actual | Tipo | Relación |
| --- | --- | --- | --- |
| `id` | `id` | INTEGER | Clave primaria |
| `brand_id` | `marca_id` | INTEGER | `marcas_vehiculos.id` |
| `name` | `nombre` | TEXT |  |
| `created_at` | `fecha_creacion` | TEXT |  |

### `tipos_motor`

| Campo anterior | Campo actual | Tipo | Relación |
| --- | --- | --- | --- |
| `id` | `id` | INTEGER | Clave primaria |
| `code` | `codigo` | TEXT |  |
| `description` | `descripcion` | TEXT |  |
| `created_at` | `fecha_creacion` | TEXT |  |

### `aplicaciones_repuestos`

| Campo anterior | Campo actual | Tipo | Relación |
| --- | --- | --- | --- |
| `id` | `id` | INTEGER | Clave primaria |
| `part_id` | `repuesto_id` | INTEGER | `repuestos.id` |
| `brand_id` | `marca_id` | INTEGER | `marcas_vehiculos.id` |
| `model_id` | `modelo_id` | INTEGER | `modelos_vehiculos.id` |
| `engine_type_id` | `tipo_motor_id` | INTEGER | `tipos_motor.id` |
| `displacement` | `cilindrada` | REAL |  |
| `year_from` | `anio_desde` | INTEGER |  |
| `year_to` | `anio_hasta` | INTEGER |  |
| `application_text` | `texto_aplicacion` | TEXT |  |
| `created_at` | `fecha_creacion` | TEXT |  |

### `lotes_importacion`

| Campo anterior | Campo actual | Tipo | Relación |
| --- | --- | --- | --- |
| `id` | `id` | INTEGER | Clave primaria |
| `file_name` | `nombre_archivo` | TEXT |  |
| `sheet_name` | `nombre_hoja` | TEXT |  |
| `status` | `estado` | TEXT |  |
| `total_rows` | `total_filas` | INTEGER |  |
| `valid_rows` | `filas_validas` | INTEGER |  |
| `error_rows` | `filas_error` | INTEGER |  |
| `created_at` | `fecha_creacion` | TEXT |  |
| `processed_at` | `fecha_procesamiento` | TEXT |  |

### `filas_importacion`

| Campo anterior | Campo actual | Tipo | Relación |
| --- | --- | --- | --- |
| `id` | `id` | INTEGER | Clave primaria |
| `batch_id` | `lote_id` | INTEGER | `lotes_importacion.id` |
| `row_number` | `numero_fila` | INTEGER |  |
| `raw_data` | `datos_originales` | TEXT |  |
| `normalized_data` | `datos_normalizados` | TEXT |  |
| `status` | `estado` | TEXT |  |
| `errors` | `errores` | TEXT |  |

### Catálogos de clasificación e historial

| Tabla | Campos | Reglas |
| --- | --- | --- |
| `unidades_medida` | `id`, `nombre` | Nombre único, ignorando mayúsculas y espacios externos. |
| `marcas_repuestos` | `id`, `nombre` | Marca comercial única; independiente de `marcas_vehiculos`. |
| `categorias_repuestos` | `id`, `marca_id`, `nombre` | `marca_id` apunta a `marcas_repuestos.id`; nombre único dentro de esa marca. |
| `historial_estados` | `id`, `repuesto_id`, `estado_anterior`, `estado_nuevo`, `fecha_cambio` | `repuesto_id` apunta a `repuestos.id`. El primer registro no tiene estado anterior. |

`vista_repuestos` reúne los campos del repuesto y los nombres `unidad`, `nombre_marca` y `categoria`. Es una vista de consulta; los cambios se guardan en las tablas correspondientes. Consulte [GESTION_COMERCIAL.md](GESTION_COMERCIAL.md) para las etapas, el cierre en SAP y la plantilla de importación.

## Importación y conservación de datos

- `repuestos.codigo_proveedor` identifica un repuesto en todo el catálogo. Los encabezados anteriores, como `parts.supplier_code`, siguen aceptándose.
- Un maestro en español puede usar `REPUESTOS` en la primera fila y nombres como `repuestos.codigo_proveedor`, `codigos_oem.codigo_oem` o `aplicaciones_repuestos.anio_desde` en la segunda. La primera fila también admite el encabezado anterior `PARTS`.
- No se requieren los campos `repuesto_id` en el CSV: se resuelven a partir del código de proveedor. Se conservan las reglas para no duplicar OEM, referencias ni aplicaciones.
- Los campos informados actualizan el repuesto; las celdas vacías conservan el valor guardado. Los OEM y las referencias nuevos se agregan.
- Las cargas preparadas con la versión anterior se pueden revisar y confirmar. Su JSON histórico se conserva y se interpreta al leerlo.
- Los valores de estado conservan sus códigos: `staged` (preparada), `confirmed` (confirmada), `rejected` (rechazada), `valid` (fila válida) y `error` (fila con error). Se tradujeron los nombres del esquema, sin reescribir los datos históricos.
- `sqlite_sequence` es una tabla interna de SQLite para los identificadores automáticos.

## Respaldo y migración

Al abrir una base con el esquema anterior, `initialize_database` genera un respaldo mediante la API de SQLite en `data/catalogo.pre_traduccion_es.sqlite3` (con sufijo adicional si ya existe). Después renombra tablas, campos e índices dentro de una transacción y verifica la integridad y las claves foráneas. Reabrir una base traducida no repite el cambio ni genera otro respaldo.

El respaldo corresponde al esquema en inglés y debe usarse con la versión anterior del programa si se necesita volver a ese estado. Con el programa actual, una base en inglés vuelve a migrarse al inicializarse.

La migración histórica de Supabase/PostgreSQL se conserva en inglés y no se ha aplicado esta traducción a una base remota.
