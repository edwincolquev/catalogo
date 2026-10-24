CREATE TABLE IF NOT EXISTS unidades_medida (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL CHECK (trim(nombre) <> '')
);
CREATE UNIQUE INDEX IF NOT EXISTS unidades_medida_nombre_unico ON unidades_medida (upper(trim(nombre)));

CREATE TABLE IF NOT EXISTS marcas_repuestos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL CHECK (trim(nombre) <> '')
);
CREATE UNIQUE INDEX IF NOT EXISTS marcas_repuestos_nombre_unico ON marcas_repuestos (upper(trim(nombre)));

CREATE TABLE IF NOT EXISTS categorias_repuestos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marca_id INTEGER NOT NULL REFERENCES marcas_repuestos(id) ON DELETE RESTRICT,
    nombre TEXT NOT NULL CHECK (trim(nombre) <> '')
);
CREATE UNIQUE INDEX IF NOT EXISTS categorias_repuestos_marca_nombre_unico ON categorias_repuestos (marca_id, upper(trim(nombre)));

CREATE TABLE IF NOT EXISTS historial_estados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repuesto_id INTEGER NOT NULL REFERENCES repuestos(id) ON DELETE CASCADE,
    estado_anterior TEXT,
    estado_nuevo TEXT NOT NULL,
    fecha_cambio TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS historial_estados_repuesto ON historial_estados (repuesto_id, id);
CREATE INDEX IF NOT EXISTS repuestos_estado_gestion ON repuestos (estado_gestion);

CREATE VIEW IF NOT EXISTS vista_repuestos AS
SELECT r.id, r.codigo_proveedor, r.codigo_sap, r.descripcion, r.medida,
       r.descripcion_larga, r.activo, r.fecha_creacion, r.fecha_actualizacion,
       r.unidad_id, r.marca_id, r.categoria_id, r.estado_gestion,
       r.minimo_compra, r.precio_compra, r.precio_venta, r.cantidad_compra,
       u.nombre AS unidad, m.nombre AS nombre_marca, c.nombre AS categoria
FROM repuestos r
LEFT JOIN unidades_medida u ON u.id = r.unidad_id
LEFT JOIN marcas_repuestos m ON m.id = r.marca_id
LEFT JOIN categorias_repuestos c ON c.id = r.categoria_id;

CREATE TRIGGER IF NOT EXISTS repuestos_categoria_insertar
BEFORE INSERT ON repuestos
WHEN NEW.categoria_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM categorias_repuestos WHERE id = NEW.categoria_id AND marca_id = NEW.marca_id
)
BEGIN
    SELECT RAISE(ABORT, 'La categoria debe pertenecer a la marca del repuesto');
END;

CREATE TRIGGER IF NOT EXISTS repuestos_categoria_actualizar
BEFORE UPDATE OF marca_id, categoria_id ON repuestos
WHEN NEW.categoria_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM categorias_repuestos WHERE id = NEW.categoria_id AND marca_id = NEW.marca_id
)
BEGIN
    SELECT RAISE(ABORT, 'La categoria debe pertenecer a la marca del repuesto');
END;

CREATE TRIGGER IF NOT EXISTS categorias_marca_actualizar
BEFORE UPDATE OF marca_id ON categorias_repuestos
WHEN NEW.marca_id <> OLD.marca_id AND EXISTS (SELECT 1 FROM repuestos WHERE categoria_id = OLD.id)
BEGIN
    SELECT RAISE(ABORT, 'No puede cambiarse la marca de una categoria en uso');
END;

CREATE TRIGGER IF NOT EXISTS repuestos_estado_inicial
BEFORE INSERT ON repuestos
WHEN NEW.estado_gestion NOT IN ('propuesto', 'en_sap')
BEGIN
    SELECT RAISE(ABORT, 'El estado inicial debe ser Propuesto o En SAP');
END;

CREATE TRIGGER IF NOT EXISTS repuestos_transicion_estado
BEFORE UPDATE OF estado_gestion ON repuestos
WHEN NEW.estado_gestion <> OLD.estado_gestion AND NOT (
    (OLD.estado_gestion = 'propuesto' AND NEW.estado_gestion IN ('en_cotizacion', 'rechazado')) OR
    (OLD.estado_gestion = 'en_cotizacion' AND NEW.estado_gestion IN ('pendiente_aprobacion', 'rechazado')) OR
    (OLD.estado_gestion = 'pendiente_aprobacion' AND NEW.estado_gestion IN ('aprobado', 'rechazado')) OR
    (OLD.estado_gestion = 'aprobado' AND NEW.estado_gestion IN ('pedido', 'rechazado')) OR
    (OLD.estado_gestion = 'pedido' AND NEW.estado_gestion IN ('en_sap', 'rechazado'))
)
BEGIN
    SELECT RAISE(ABORT, 'Transicion de estado no permitida');
END;

CREATE TRIGGER IF NOT EXISTS repuestos_comercial_cerrado
BEFORE UPDATE OF minimo_compra, precio_compra, precio_venta, cantidad_compra ON repuestos
WHEN OLD.estado_gestion = 'en_sap' AND (
    NEW.minimo_compra IS NOT OLD.minimo_compra OR NEW.precio_compra IS NOT OLD.precio_compra OR
    NEW.precio_venta IS NOT OLD.precio_venta OR NEW.cantidad_compra IS NOT OLD.cantidad_compra
)
BEGIN
    SELECT RAISE(ABORT, 'El seguimiento comercial esta cerrado en SAP');
END;

CREATE TRIGGER IF NOT EXISTS repuestos_historial_inicial
AFTER INSERT ON repuestos
BEGIN
    INSERT INTO historial_estados (repuesto_id, estado_nuevo) VALUES (NEW.id, NEW.estado_gestion);
END;

CREATE TRIGGER IF NOT EXISTS repuestos_historial_cambio
AFTER UPDATE OF estado_gestion ON repuestos
WHEN NEW.estado_gestion <> OLD.estado_gestion
BEGIN
    INSERT INTO historial_estados (repuesto_id, estado_anterior, estado_nuevo)
    VALUES (NEW.id, OLD.estado_gestion, NEW.estado_gestion);
END;
