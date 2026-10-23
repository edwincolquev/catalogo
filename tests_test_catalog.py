import csv
import pandas as pd

from database import get_connection, initialize_database
from descriptions import format_application_rows, generate_application_summary, refresh_long_description
from importer import confirm_batch, read_source, stage_dataframe


def test_import_and_description_generation(tmp_path):
    database_path = tmp_path / "catalogo_test.sqlite3"
    initialize_database(database_path)
    dataframe = pd.DataFrame([
        {"Codigo SAP": "SAP-001", "Descripcion": "Filtro aceite", "Medida": "10 mm", "OEM": "OEM-1, OEM-2"},
        {"Codigo SAP": "SAP-002", "Descripcion": ""},
    ])
    batch_id = stage_dataframe(dataframe, "test.xlsx", db_path=database_path)
    assert confirm_batch(batch_id, db_path=database_path) == (2, 0)
    with get_connection(database_path) as connection:
        part = connection.execute("SELECT id FROM parts WHERE sap_code = 'SAP-001'").fetchone()
        description = refresh_long_description(connection, part["id"])
        assert description == "Filtro aceite\n10 mm\n(OEM: OEM-1, OEM-2)"
        assert connection.execute("SELECT COUNT(*) FROM import_staging_rows WHERE status = 'error'").fetchone()[0] == 0
        assert connection.execute("SELECT description FROM parts WHERE sap_code = 'SAP-002'").fetchone()[0] is None


def test_import_reads_semicolon_csv(tmp_path):
    source_path = tmp_path / "repuestos.csv"
    source_path.write_text(
        "Codigo SAP;Descripcion;OEM\nSAP-003;Filtro aire;OEM-3\n",
        encoding="utf-8",
    )
    dataframe = read_source(source_path)
    assert list(dataframe.columns) == ["Codigo SAP", "Descripcion", "OEM"]
    assert dataframe.iloc[0]["Codigo SAP"] == "SAP-003"


def test_master_is_idempotent_and_updates_only_informed_fields(tmp_path):
    database_path = tmp_path / "catalogo.sqlite3"
    initialize_database(database_path)
    source_path = tmp_path / "maestro.csv"
    with source_path.open("w", encoding="utf-8", newline="") as source:
        writer = csv.writer(source, delimiter=";")
        writer.writerow(["PARTS", "", "", "", "PART_OEM_CODE", "VEHICLE_BRANDS", "VEHICLE_MODELS", "ENGINE_TYPES", "PART_APPLICATIONS", "", ""])
        writer.writerow(["parts.supplier_code", "parts.sap_code", "parts.description", "parts.measure",
                         "part_oem_code.oem_code", "vehicle_brands.name", "vehicle_model.name",
                         "engine_type.code", "applications.displacement", "applications.year_from",
                         "applications.year_to"])
        writer.writerow(["7277", "CPL-7277", "MANGUERA", "12X12X220", "OEM-1", "TOYOTA", "HILUX", "2L", "2,4", "1990", "1995"])
        writer.writerow(["7277", "", "", "", "", "", "PICKUP", "3L", "2,8", "1996", "2000"])
        writer.writerow(["GA-0300", "CTL-GA-0300", "GUARDAPOLVO", "", "", "CHEVROLET", "", "D-60", "", "1964", "1971"])
    master = read_source(source_path)
    assert master.attrs["first_data_row"] == 3
    batch_id = stage_dataframe(master, "maestro.csv", db_path=database_path)
    with get_connection(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM import_staging_rows WHERE batch_id = ? AND errors LIKE '%Aviso:%'",
            (batch_id,),
        ).fetchone()[0] == 1
    assert confirm_batch(batch_id, db_path=database_path) == (2, 0)
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM part_applications").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM parts").fetchone()[0] == 2
    batch_id = stage_dataframe(master, "maestro.csv", db_path=database_path)
    assert confirm_batch(batch_id, db_path=database_path) == (0, 0)
    update = pd.DataFrame([{
        "Codigo proveedor": "7277", "Descripcion": "MANGUERA ACTUALIZADA", "OEM": "OEM-1|OEM-NUEVO",
    }])
    batch_id = stage_dataframe(update, "update.csv", db_path=database_path)
    assert confirm_batch(batch_id, db_path=database_path) == (0, 1)
    with get_connection(database_path) as connection:
        part = connection.execute("SELECT * FROM parts WHERE supplier_code = '7277'").fetchone()
        assert part["description"] == "MANGUERA ACTUALIZADA"
        assert part["sap_code"] == "CPL-7277"
        assert connection.execute(
            "SELECT COUNT(*) FROM part_oem_codes WHERE part_id = ?", (part["id"],)
        ).fetchone()[0] == 2


def test_oem_only_continuation_does_not_create_application(tmp_path):
    database_path = tmp_path / "catalogo.sqlite3"
    initialize_database(database_path)
    rows = pd.DataFrame([
        {"parts.supplier_code": "PROV-1", "vehicle_brands.name": "TOYOTA", "vehicle_model.name": "HILUX"},
        {"parts.supplier_code": "PROV-1", "part_oem_code.oem_code": "OEM-1"},
    ]).fillna("")
    rows.attrs["master_format"] = True
    rows.attrs["first_data_row"] = 3
    batch_id = stage_dataframe(rows, "maestro.csv", db_path=database_path)
    assert confirm_batch(batch_id, db_path=database_path) == (1, 0)
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM part_applications").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM part_oem_codes").fetchone()[0] == 1


def test_vba_application_compaction():
    def application(brand, model, displacement, engine, start, end, text=""):
        return dict(brand_name=brand, model_name=model, displacement=displacement,
                    engine_code=engine, year_from=start, year_to=end, application_text=text)

    rows = [
        application("Honda", "Civic", 1.6, "D16", 1988, 2000, "Sedan"),
        application("HONDA", "CIVIC", 1.6, "D16", 1988, 2000, "SEDAN"),
        application("Honda", "Civic", 1.6, "D16", 1988, 2000, "Hatchback"),
        application("Honda", "Civic", 1.6, "B16", 1990, 1992, "Coupe"),
        application("Honda", "Accord", 1.6, "F20", 1994, None),
        application("Toyota", "Hilux", 2.4, "2L", None, 2005),
        application("Honda", "Civic", 1.6, "D17", 2001, 2006),
    ]
    assert format_application_rows(rows) == (
        "HONDA: CIVIC 1,6 D16 DEL 88 AL 00 SEDAN; "
        "D16 DEL 88 AL 00 HATCHBACK; B16 DEL 90 AL 92 COUPE; "
        "ACCORD 1,6 F20 DESDE 94; TOYOTA: HILUX 2,4 2L HASTA 05; "
        "HONDA: CIVIC 1,6 D17 DEL 01 AL 06"
    )


def test_application_text_is_imported_and_part_of_duplicate_key(tmp_path):
    database_path = tmp_path / "catalogo.sqlite3"
    initialize_database(database_path)
    rows = pd.DataFrame([
        {"parts.supplier_code": "P-1", "vehicle_brands.name": "TOYOTA",
         "vehicle_model.name": "HILUX", "engine_type.code": "2L",
         "applications.year_from": "1990", "applications.year_to": "1995",
         "applications.application_text": "PICKUP"},
        {"parts.supplier_code": "P-1", "vehicle_brands.name": "TOYOTA",
         "vehicle_model.name": "HILUX", "engine_type.code": "2L",
         "applications.year_from": "1990", "applications.year_to": "1995",
         "applications.application_text": "4X4"},
    ]).fillna("")
    batch_id = stage_dataframe(rows, "applications.csv", db_path=database_path)
    assert confirm_batch(batch_id, db_path=database_path) == (1, 0)
    batch_id = stage_dataframe(rows, "applications.csv", db_path=database_path)
    assert confirm_batch(batch_id, db_path=database_path) == (0, 0)
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM part_applications").fetchone()[0] == 2
        part_id = connection.execute("SELECT id FROM parts WHERE supplier_code = 'P-1'").fetchone()[0]
        assert generate_application_summary(connection, part_id) == (
            "TOYOTA: HILUX 2L DEL 90 AL 95 PICKUP; 2L DEL 90 AL 95 4X4"
        )
