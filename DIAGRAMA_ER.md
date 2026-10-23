# Diagrama entidad–relación de `catalogo.sqlite3`

Fuente: esquema real de `data/catalogo.sqlite3`, contrastado con `schema.sql`.
`PK` = clave primaria; `FK` = clave foránea. Un círculo en la relación indica participación opcional.

```mermaid
erDiagram
    parts {
        INTEGER id PK
        TEXT sap_code UK
        TEXT supplier_code
        TEXT description
        TEXT measure
        TEXT brand_name
        TEXT long_description
        INTEGER is_active
        TEXT created_at
        TEXT updated_at
    }
    part_oem_codes {
        INTEGER id PK
        INTEGER part_id FK
        TEXT oem_code
        TEXT created_at
    }
    part_cross_references {
        INTEGER id PK
        INTEGER part_id FK
        TEXT reference_type
        TEXT reference_code
        TEXT created_at
    }
    vehicle_brands {
        INTEGER id PK
        TEXT name UK
        TEXT created_at
    }
    vehicle_models {
        INTEGER id PK
        INTEGER brand_id FK
        TEXT name
        TEXT created_at
    }
    engine_types {
        INTEGER id PK
        TEXT code UK
        TEXT description
        TEXT created_at
    }
    part_applications {
        INTEGER id PK
        INTEGER part_id FK
        INTEGER brand_id FK
        INTEGER model_id FK
        INTEGER engine_type_id FK
        REAL displacement
        INTEGER year_from
        INTEGER year_to
        TEXT created_at
    }
    import_batches {
        INTEGER id PK
        TEXT file_name
        TEXT sheet_name
        TEXT status
        INTEGER total_rows
        INTEGER valid_rows
        INTEGER error_rows
        TEXT created_at
        TEXT processed_at
    }
    import_staging_rows {
        INTEGER id PK
        INTEGER batch_id FK
        INTEGER row_number
        TEXT raw_data
        TEXT normalized_data
        TEXT status
        TEXT errors
    }

    parts ||--o{ part_oem_codes : tiene
    parts ||--o{ part_cross_references : tiene
    parts ||--o{ part_applications : aplica_en
    vehicle_brands ||--o{ vehicle_models : agrupa
    vehicle_brands ||--o{ part_applications : marca
    vehicle_models ||--o{ part_applications : modelo
    engine_types |o--o{ part_applications : motor_opcional
    import_batches ||--o{ import_staging_rows : contiene
```

## Puntos para analizar

- `part_applications` enlaza un repuesto con marca, modelo y, opcionalmente, tipo de motor. `displacement` y los años acotan la aplicación.
- `brand_name` en `parts` es texto libre y no tiene clave foránea a `vehicle_brands`.
- Las claves foráneas de `part_applications.brand_id` y `model_id` son independientes: el esquema permite asociar una marca con un modelo de otra marca. Esto requiere validación adicional si se desea impedirlo.
- La restricción `UNIQUE` de SQLite en `part_applications` permite filas repetidas cuando alguna columna de la combinación es `NULL`. La migración de Supabase usa `coalesce(...)` para cubrir ese caso.
- `import_batches` e `import_staging_rows` forman un circuito separado de preparación de archivos. La migración PostgreSQL/Supabase actual contiene las siete tablas del catálogo, pero no estas dos tablas de importación.

## Estado de los datos locales

Al revisar la base local el 23 de octubre de 2026: `parts` 2 filas; `part_oem_codes` 1; `import_batches` 5; `import_staging_rows` 7. Las otras cinco tablas estaban vacías. Estos conteos cambian al usar la aplicación.
