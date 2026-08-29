import tempfile
from pathlib import Path

import pandas as pd

from database import get_connection, initialize_database
from descriptions import refresh_long_description
from importer import confirm_batch, stage_dataframe


def test_import_and_description_generation():
    database_path = Path(tempfile.gettempdir()) / "catalogo_test.sqlite3"
    database_path.unlink(missing_ok=True)
    initialize_database(database_path)
    dataframe = pd.DataFrame([
        {"Codigo SAP": "SAP-001", "Descripcion": "Filtro aceite", "Medida": "10 mm", "OEM": "OEM-1, OEM-2"},
        {"Codigo SAP": "SAP-002", "Descripcion": ""},
    ])
    batch_id = stage_dataframe(dataframe, "test.xlsx", db_path=database_path)
    assert confirm_batch(batch_id, db_path=database_path) == (1, 0)
    with get_connection(database_path) as connection:
        part = connection.execute("SELECT id FROM parts WHERE sap_code = 'SAP-001'").fetchone()
        description = refresh_long_description(connection, part["id"])
        assert description == "Filtro aceite\n10 mm\n(OEM: OEM-1, OEM-2)"
        assert connection.execute("SELECT COUNT(*) FROM import_staging_rows WHERE status = 'error'").fetchone()[0] == 1


def test_import_reads_semicolon_csv(tmp_path):
    source_path = tmp_path / "repuestos.csv"
    source_path.write_text(
        "Codigo SAP;Descripcion;OEM\nSAP-003;Filtro aire;OEM-3\n",
        encoding="utf-8",
    )
    dataframe = read_source(source_path)
    assert list(dataframe.columns) == ["Codigo SAP", "Descripcion", "OEM"]
    assert dataframe.iloc[0]["Codigo SAP"] == "SAP-003"
