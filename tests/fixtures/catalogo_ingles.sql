PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sap_code TEXT,
    supplier_code TEXT,
    description TEXT,
    measure TEXT,
    brand_name TEXT,
    long_description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS parts_sap_code_unique ON parts (upper(trim(sap_code))) WHERE sap_code IS NOT NULL AND trim(sap_code) <> '';
CREATE UNIQUE INDEX IF NOT EXISTS parts_supplier_code_unique ON parts (upper(trim(supplier_code))) WHERE supplier_code IS NOT NULL AND trim(supplier_code) <> '';
CREATE INDEX IF NOT EXISTS parts_description_index ON parts (description);

CREATE TABLE IF NOT EXISTS part_oem_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    oem_code TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (part_id, oem_code COLLATE NOCASE)
);

CREATE TABLE IF NOT EXISTS part_cross_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    reference_type TEXT NOT NULL,
    reference_code TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (part_id, reference_type COLLATE NOCASE, reference_code COLLATE NOCASE)
);

CREATE TABLE IF NOT EXISTS vehicle_brands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vehicle_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL REFERENCES vehicle_brands(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (brand_id, name COLLATE NOCASE)
);

CREATE TABLE IF NOT EXISTS engine_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS part_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    brand_id INTEGER NOT NULL REFERENCES vehicle_brands(id) ON DELETE RESTRICT,
    model_id INTEGER NOT NULL REFERENCES vehicle_models(id) ON DELETE RESTRICT,
    engine_type_id INTEGER REFERENCES engine_types(id) ON DELETE RESTRICT,
    displacement REAL CHECK (displacement IS NULL OR displacement > 0),
    year_from INTEGER CHECK (year_from IS NULL OR year_from BETWEEN 1886 AND 2200),
    year_to INTEGER CHECK (year_to IS NULL OR year_to BETWEEN 1886 AND 2200),
    application_text TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (year_from IS NULL OR year_to IS NULL OR year_from <= year_to)
);
CREATE INDEX IF NOT EXISTS part_applications_vehicle_lookup ON part_applications (brand_id, model_id, year_from, year_to);
CREATE UNIQUE INDEX IF NOT EXISTS part_applications_unique ON part_applications (
    part_id, brand_id, model_id, coalesce(engine_type_id, 0), coalesce(displacement, 0),
    coalesce(year_from, 0), coalesce(year_to, 0), upper(trim(coalesce(application_text, '')))
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    sheet_name TEXT,
    status TEXT NOT NULL DEFAULT 'staged' CHECK (status IN ('staged', 'confirmed', 'rejected')),
    total_rows INTEGER NOT NULL DEFAULT 0,
    valid_rows INTEGER NOT NULL DEFAULT 0,
    error_rows INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS import_staging_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL,
    raw_data TEXT NOT NULL,
    normalized_data TEXT,
    status TEXT NOT NULL CHECK (status IN ('valid', 'error')),
    errors TEXT,
    UNIQUE (batch_id, row_number)
);
