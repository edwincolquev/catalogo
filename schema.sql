PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS repuestos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_sap TEXT,
    codigo_proveedor TEXT,
    descripcion TEXT,
    medida TEXT,
    unidad_id INTEGER REFERENCES unidades_medida(id) ON DELETE RESTRICT,
    marca_id INTEGER REFERENCES marcas_repuestos(id) ON DELETE RESTRICT,
    categoria_id INTEGER REFERENCES categorias_repuestos(id) ON DELETE RESTRICT,
    estado_gestion TEXT NOT NULL DEFAULT 'propuesto'
        CHECK (estado_gestion IN ('propuesto', 'en_cotizacion', 'pendiente_aprobacion', 'aprobado', 'rechazado', 'pedido', 'en_sap'))
        CHECK (estado_gestion <> 'en_sap' OR trim(coalesce(codigo_sap, '')) <> ''),
    minimo_compra REAL CHECK (minimo_compra IS NULL OR minimo_compra > 0),
    precio_compra REAL CHECK (precio_compra IS NULL OR precio_compra >= 0),
    precio_venta REAL CHECK (precio_venta IS NULL OR precio_venta >= 0),
    cantidad_compra REAL CHECK (cantidad_compra IS NULL OR cantidad_compra >= 0),
    descripcion_larga TEXT,
    activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS repuestos_codigo_sap_unico ON repuestos (upper(trim(codigo_sap))) WHERE codigo_sap IS NOT NULL AND trim(codigo_sap) <> '';
CREATE UNIQUE INDEX IF NOT EXISTS repuestos_codigo_proveedor_unico ON repuestos (upper(trim(codigo_proveedor))) WHERE codigo_proveedor IS NOT NULL AND trim(codigo_proveedor) <> '';
CREATE INDEX IF NOT EXISTS repuestos_descripcion_indice ON repuestos (descripcion);

CREATE TABLE IF NOT EXISTS codigos_oem (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repuesto_id INTEGER NOT NULL REFERENCES repuestos(id) ON DELETE CASCADE,
    codigo_oem TEXT NOT NULL,
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (repuesto_id, codigo_oem COLLATE NOCASE)
);

CREATE TABLE IF NOT EXISTS referencias_cruzadas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repuesto_id INTEGER NOT NULL REFERENCES repuestos(id) ON DELETE CASCADE,
    tipo_referencia TEXT NOT NULL,
    codigo_referencia TEXT NOT NULL,
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (repuesto_id, tipo_referencia COLLATE NOCASE, codigo_referencia COLLATE NOCASE)
);

CREATE TABLE IF NOT EXISTS marcas_vehiculos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE COLLATE NOCASE,
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS modelos_vehiculos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marca_id INTEGER NOT NULL REFERENCES marcas_vehiculos(id) ON DELETE RESTRICT,
    nombre TEXT NOT NULL,
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (marca_id, nombre COLLATE NOCASE)
);

CREATE TABLE IF NOT EXISTS tipos_motor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE COLLATE NOCASE,
    descripcion TEXT,
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aplicaciones_repuestos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repuesto_id INTEGER NOT NULL REFERENCES repuestos(id) ON DELETE CASCADE,
    marca_id INTEGER NOT NULL REFERENCES marcas_vehiculos(id) ON DELETE RESTRICT,
    modelo_id INTEGER NOT NULL REFERENCES modelos_vehiculos(id) ON DELETE RESTRICT,
    tipo_motor_id INTEGER REFERENCES tipos_motor(id) ON DELETE RESTRICT,
    cilindrada REAL CHECK (cilindrada IS NULL OR cilindrada > 0),
    anio_desde INTEGER CHECK (anio_desde IS NULL OR anio_desde BETWEEN 1886 AND 2200),
    anio_hasta INTEGER CHECK (anio_hasta IS NULL OR anio_hasta BETWEEN 1886 AND 2200),
    texto_aplicacion TEXT,
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (anio_desde IS NULL OR anio_hasta IS NULL OR anio_desde <= anio_hasta)
);
CREATE INDEX IF NOT EXISTS aplicaciones_repuestos_busqueda_vehiculo ON aplicaciones_repuestos (marca_id, modelo_id, anio_desde, anio_hasta);
CREATE UNIQUE INDEX IF NOT EXISTS aplicaciones_repuestos_unicas ON aplicaciones_repuestos (
    repuesto_id, marca_id, modelo_id, coalesce(tipo_motor_id, 0), coalesce(cilindrada, 0),
    coalesce(anio_desde, 0), coalesce(anio_hasta, 0), upper(trim(coalesce(texto_aplicacion, '')))
);

CREATE TABLE IF NOT EXISTS lotes_importacion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_archivo TEXT NOT NULL,
    nombre_hoja TEXT,
    estado TEXT NOT NULL DEFAULT 'staged' CHECK (estado IN ('staged', 'confirmed', 'rejected')),
    total_filas INTEGER NOT NULL DEFAULT 0,
    filas_validas INTEGER NOT NULL DEFAULT 0,
    filas_error INTEGER NOT NULL DEFAULT 0,
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_procesamiento TEXT
);

CREATE TABLE IF NOT EXISTS filas_importacion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id INTEGER NOT NULL REFERENCES lotes_importacion(id) ON DELETE CASCADE,
    numero_fila INTEGER NOT NULL,
    datos_originales TEXT NOT NULL,
    datos_normalizados TEXT,
    estado TEXT NOT NULL CHECK (estado IN ('valid', 'error')),
    errores TEXT,
    UNIQUE (lote_id, numero_fila)
);
