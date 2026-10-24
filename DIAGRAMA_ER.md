# Diagrama entidad–relación de `catalogo.sqlite3`

Fuente: esquema de `data/catalogo.sqlite3`, definido por `schema.sql` y `schema_gestion.sql`.
`PK` = clave primaria; `FK` = clave foránea. Un círculo en la relación indica participación opcional.

```mermaid
erDiagram
    repuestos {
        INTEGER id PK
        TEXT codigo_sap UK
        TEXT codigo_proveedor UK
        TEXT descripcion
        TEXT medida
        INTEGER unidad_id FK
        INTEGER marca_id FK
        INTEGER categoria_id FK
        TEXT estado_gestion
        REAL minimo_compra
        REAL precio_compra
        REAL precio_venta
        REAL cantidad_compra
        TEXT descripcion_larga
        INTEGER activo
        TEXT fecha_creacion
        TEXT fecha_actualizacion
    }
    codigos_oem {
        INTEGER id PK
        INTEGER repuesto_id FK
        TEXT codigo_oem
        TEXT fecha_creacion
    }
    referencias_cruzadas {
        INTEGER id PK
        INTEGER repuesto_id FK
        TEXT tipo_referencia
        TEXT codigo_referencia
        TEXT fecha_creacion
    }
    marcas_vehiculos {
        INTEGER id PK
        TEXT nombre UK
        TEXT fecha_creacion
    }
    modelos_vehiculos {
        INTEGER id PK
        INTEGER marca_id FK
        TEXT nombre
        TEXT fecha_creacion
    }
    tipos_motor {
        INTEGER id PK
        TEXT codigo UK
        TEXT descripcion
        TEXT fecha_creacion
    }
    aplicaciones_repuestos {
        INTEGER id PK
        INTEGER repuesto_id FK
        INTEGER marca_id FK
        INTEGER modelo_id FK
        INTEGER tipo_motor_id FK
        REAL cilindrada
        INTEGER anio_desde
        INTEGER anio_hasta
        TEXT texto_aplicacion
        TEXT fecha_creacion
    }
    lotes_importacion {
        INTEGER id PK
        TEXT nombre_archivo
        TEXT nombre_hoja
        TEXT estado
        INTEGER total_filas
        INTEGER filas_validas
        INTEGER filas_error
        TEXT fecha_creacion
        TEXT fecha_procesamiento
    }
    filas_importacion {
        INTEGER id PK
        INTEGER lote_id FK
        INTEGER numero_fila
        TEXT datos_originales
        TEXT datos_normalizados
        TEXT estado
        TEXT errores
    }

    unidades_medida {
        INTEGER id PK
        TEXT nombre UK
    }
    marcas_repuestos {
        INTEGER id PK
        TEXT nombre UK
    }
    categorias_repuestos {
        INTEGER id PK
        INTEGER marca_id FK
        TEXT nombre
    }
    historial_estados {
        INTEGER id PK
        INTEGER repuesto_id FK
        TEXT estado_anterior
        TEXT estado_nuevo
        TEXT fecha_cambio
    }

    unidades_medida |o--o{ repuestos : unidad
    marcas_repuestos |o--o{ repuestos : marca_comercial
    marcas_repuestos ||--o{ categorias_repuestos : define
    categorias_repuestos |o--o{ repuestos : clasifica
    repuestos ||--o{ historial_estados : recorre
    repuestos ||--o{ codigos_oem : tiene
    repuestos ||--o{ referencias_cruzadas : tiene
    repuestos ||--o{ aplicaciones_repuestos : aplica_en
    marcas_vehiculos ||--o{ modelos_vehiculos : agrupa
    marcas_vehiculos ||--o{ aplicaciones_repuestos : marca
    modelos_vehiculos ||--o{ aplicaciones_repuestos : modelo
    tipos_motor |o--o{ aplicaciones_repuestos : motor_opcional
    lotes_importacion ||--o{ filas_importacion : contiene
```

## Puntos para analizar

- `aplicaciones_repuestos` enlaza un repuesto con marca, modelo y, opcionalmente, tipo de motor. `cilindrada` y los años acotan la aplicación.
- `repuestos.marca_id` referencia la marca comercial en `marcas_repuestos`. Cada categoría pertenece a una marca comercial; se valida que coincida con la del repuesto. Las marcas de vehículos se mantienen en `marcas_vehiculos`.
- Las claves foráneas de `aplicaciones_repuestos.marca_id` y `modelo_id` son independientes: el esquema permite asociar una marca con un modelo de otra marca. Esto requiere validación adicional si se desea impedirlo.
- El índice único de `aplicaciones_repuestos` usa `coalesce(...)` y normaliza `texto_aplicacion` para evitar duplicados incluso cuando hay campos vacíos.
- `lotes_importacion` e `filas_importacion` forman un circuito separado de preparación de archivos. La migración PostgreSQL/Supabase actual contiene las siete tablas del catálogo, pero no estas dos tablas de importación.

## Nombres y compatibilidad

Las nueve tablas originales se tradujeron al español el 24 de octubre de 2026. La ampliación comercial agrega cuatro tablas y `vista_repuestos`, que muestra unidad, marca y categoría por nombre. Consulte [DICCIONARIO_DATOS.md](DICCIONARIO_DATOS.md) y [GESTION_COMERCIAL.md](GESTION_COMERCIAL.md) para los campos, etapas y reglas de importación.
