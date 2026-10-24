import csv
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from database import get_connection, initialize_database
from descriptions import generate_application_summary
from importer import confirm_batch, read_source, stage_dataframe
from schema_names import COLUMN_RENAMES, TABLE_RENAMES


LEGACY_SCHEMA = Path(__file__).parent / "tests" / "fixtures" / "catalogo_ingles.sql"


def _legacy_database(path):
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(LEGACY_SCHEMA.read_text(encoding="utf-8"))
        connection.execute("INSERT INTO parts (id, supplier_code, sap_code, description) VALUES (17, 'P-001', 'SAP-001', 'Original')")
        connection.execute("INSERT INTO part_oem_codes (id, part_id, oem_code) VALUES (11, 17, 'OEM-01')")
        connection.execute("INSERT INTO part_cross_references (id, part_id, reference_type, reference_code) VALUES (12, 17, 'CRUCE', 'REF-01')")
        connection.execute("INSERT INTO vehicle_brands (id, name) VALUES (4, 'TOYOTA')")
        connection.execute("INSERT INTO vehicle_models (id, brand_id, name) VALUES (8, 4, 'HILUX')")
        connection.execute("INSERT INTO engine_types (id, code, description) VALUES (6, '2L', 'Diesel')")
        connection.execute("""INSERT INTO part_applications
            (id, part_id, brand_id, model_id, engine_type_id, displacement, year_from, year_to, application_text)
            VALUES (21, 17, 4, 8, 6, 2.4, 1990, 1995, 'PICKUP')""")
        connection.execute("INSERT INTO import_batches (id, file_name, total_rows, valid_rows) VALUES (3, 'anterior.csv', 1, 1)")
        data = dict(supplier_code="P-001", description="Actualizada", oem_code="OEM-02",
                    reference_type="CRUCE", reference_code="REF-02", vehicle_brand="TOYOTA",
                    vehicle_model="HILUX", engine_code="2L", displacement="2,4",
                    year_from="1990", year_to="1995", application_text="4X4",
                    has_application_data=True, application_warnings=[])
        connection.execute("""INSERT INTO import_staging_rows
            (id, batch_id, row_number, raw_data, normalized_data, status)
            VALUES (31, 3, 3, ?, ?, 'valid')""",
                           (json.dumps({"parts.supplier_code": "P-001"}), json.dumps(data)))
        connection.commit()


def test_migration_preserves_every_value_and_pending_import(tmp_path):
    path = tmp_path / "catalogo.sqlite3"
    _legacy_database(path)
    with closing(sqlite3.connect(path)) as connection:
        before = {table: connection.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall()
                  for table in TABLE_RENAMES}
        old_columns = {table: [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
                       for table in TABLE_RENAMES}
    initialize_database(path)
    initialize_database(path)
    assert len(list(tmp_path.glob("*.pre_traduccion_es*.sqlite3"))) == 1
    with closing(sqlite3.connect(path)) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert not tables & TABLE_RENAMES.keys()
        for old, new in TABLE_RENAMES.items():
            target = "vista_repuestos" if old == "parts" else new
            fields = [COLUMN_RENAMES.get(column, column) for column in old_columns[old]]
            projection = ", ".join(f'"{field}"' for field in fields)
            assert connection.execute(f'SELECT {projection} FROM "{target}" ORDER BY id').fetchall() == before[old]
            assert set(fields) <= {row[1] for row in connection.execute(f'PRAGMA table_info("{target}")')}
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    with closing(sqlite3.connect(tmp_path / "catalogo.pre_traduccion_es.sqlite3")) as backup:
        for table in TABLE_RENAMES:
            assert backup.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall() == before[table]
    assert confirm_batch(3, db_path=path) == (0, 1)
    with get_connection(path) as connection:
        assert connection.execute("SELECT descripcion FROM repuestos WHERE id = 17").fetchone()[0] == "Actualizada"
        for table in ("codigos_oem", "referencias_cruzadas", "aplicaciones_repuestos"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table} WHERE repuesto_id = 17").fetchone()[0] == 2
        assert generate_application_summary(connection, 17) == "TOYOTA: HILUX 2,4 2L DEL 90 AL 95 PICKUP; 2L DEL 90 AL 95 4X4"
        # La secuencia y las eliminaciones en cascada también deben conservarse.
        new_id = connection.execute("INSERT INTO repuestos (codigo_proveedor) VALUES ('P-002')").lastrowid
        assert new_id > 17
        connection.execute("DELETE FROM repuestos WHERE id = 17")
        for table in ("codigos_oem", "referencias_cruzadas", "aplicaciones_repuestos"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_migration_rolls_back_on_conflicting_column(tmp_path):
    path = tmp_path / "conflicto.sqlite3"
    _legacy_database(path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("ALTER TABLE parts ADD COLUMN descripcion TEXT")
        before = connection.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()
    try:
        initialize_database(path)
    except ValueError as error:
        assert "description y descripcion" in str(error)
    else:
        raise AssertionError("La migración debía rechazar los nombres en conflicto")
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall() == before
        assert connection.execute("SELECT description FROM parts WHERE id = 17").fetchone()[0] == "Original"


def test_spanish_master_is_idempotent(tmp_path):
    path = tmp_path / "catalogo.sqlite3"
    initialize_database(path)
    source = tmp_path / "maestro_es.csv"
    with source.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(["REPUESTOS", "", "CODIGOS_OEM", "REFERENCIAS_CRUZADAS", "", "MARCAS_VEHICULOS",
                         "MODELOS_VEHICULOS", "TIPOS_MOTOR", "APLICACIONES_REPUESTOS", "", "", ""])
        writer.writerow(["repuestos.codigo_proveedor", "repuestos.descripcion", "codigos_oem.codigo_oem",
                         "referencias_cruzadas.tipo_referencia", "referencias_cruzadas.codigo_referencia",
                         "marcas_vehiculos.nombre", "modelos_vehiculos.nombre", "tipos_motor.codigo",
                         "aplicaciones_repuestos.cilindrada", "aplicaciones_repuestos.anio_desde",
                         "aplicaciones_repuestos.anio_hasta", "aplicaciones_repuestos.texto_aplicacion"])
        writer.writerow(["001", "MANGUERA", "OEM-1", "CRUCE", "REF-1", "TOYOTA", "HILUX", "2L", "2,4", "1990", "1995", "PICKUP"])
        writer.writerow(["001", "", "OEM-1", "cruce", "ref-1", "", "", "", "", "", "", ""])
    master = read_source(source)
    assert master.attrs["master_format"]
    assert confirm_batch(stage_dataframe(master, source.name, db_path=path), db_path=path) == (1, 0)
    assert confirm_batch(stage_dataframe(master, source.name, db_path=path), db_path=path) == (0, 0)
    with get_connection(path) as connection:
        repuesto_id = connection.execute("SELECT id FROM repuestos WHERE codigo_proveedor = '001'").fetchone()[0]
        assert generate_application_summary(connection, repuesto_id) == "TOYOTA: HILUX 2,4 2L DEL 90 AL 95 PICKUP"
        assert connection.execute("SELECT COUNT(*) FROM codigos_oem").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM referencias_cruzadas").fetchone()[0] == 1
