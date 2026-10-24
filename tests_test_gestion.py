from contextlib import closing
import sqlite3

import pandas as pd

from database import get_connection, initialize_database
from gestion import guardar_repuesto
from importer import confirm_batch, stage_dataframe
from tests_test_migration import _legacy_database


def test_management_migration_preserves_brand_and_initializes_states(tmp_path):
    path = tmp_path / "catalogo.sqlite3"
    _legacy_database(path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("UPDATE parts SET brand_name = 'FRASLE' WHERE id = 17")
        connection.execute("INSERT INTO parts (supplier_code, brand_name) VALUES ('P-002', 'FRASLE')")
        connection.commit()
    initialize_database(path)
    initialize_database(path)
    assert len(list(tmp_path.glob("*.pre_gestion_comercial*.sqlite3"))) == 1
    with get_connection(path) as connection:
        rows = connection.execute("SELECT nombre_marca, estado_gestion, precio_compra FROM vista_repuestos ORDER BY id").fetchall()
        assert [tuple(row) for row in rows] == [("FRASLE", "en_sap", None), ("FRASLE", "propuesto", None)]
        assert connection.execute("SELECT count(*) FROM marcas_repuestos").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM historial_estados").fetchone()[0] == 2
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_management_import_is_sparse_and_idempotent(tmp_path):
    path = tmp_path / "catalogo.sqlite3"
    initialize_database(path)
    data = pd.DataFrame([{
        "repuestos.codigo_proveedor": "N-001", "unidades_medida.nombre": "Metro",
        "marcas_repuestos.nombre": "FRASLE", "categorias_repuestos.nombre": "Frenos",
        "repuestos.minimo_compra": "10,5", "repuestos.precio_compra": "2,25",
        "repuestos.precio_venta": "3.75", "repuestos.cantidad_compra": "12.5",
    }])
    assert confirm_batch(stage_dataframe(data, "gestion.csv", db_path=path), db_path=path) == (1, 0)
    assert confirm_batch(stage_dataframe(data, "gestion.csv", db_path=path), db_path=path) == (0, 0)
    update = pd.DataFrame([{"codigo_proveedor": "N-001", "precio_compra": "0", "precio_venta": ""}])
    assert confirm_batch(stage_dataframe(update, "actualizar.csv", db_path=path), db_path=path) == (0, 1)
    with get_connection(path) as connection:
        row = connection.execute("SELECT * FROM vista_repuestos").fetchone()
        assert (row["unidad"], row["nombre_marca"], row["categoria"]) == ("Metro", "FRASLE", "Frenos")
        assert (row["minimo_compra"], row["precio_compra"], row["precio_venta"], row["cantidad_compra"]) == (10.5, 0, 3.75, 12.5)
        assert row["estado_gestion"] == "propuesto"
        assert connection.execute("SELECT count(*) FROM categorias_repuestos").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM historial_estados").fetchone()[0] == 1
    invalid = pd.DataFrame([{"codigo_proveedor": "INVALIDO", "precio_compra": "-2", "cantidad_compra": "nan"}])
    batch = stage_dataframe(invalid, "invalido.csv", db_path=path)
    with get_connection(path) as connection:
        assert connection.execute("SELECT filas_error FROM lotes_importacion WHERE id = ?", (batch,)).fetchone()[0] == 1
    assert confirm_batch(batch, db_path=path) == (0, 0)


def test_category_must_belong_to_brand(tmp_path):
    path = tmp_path / "catalogo.sqlite3"
    initialize_database(path)
    with get_connection(path) as connection:
        first, _ = guardar_repuesto(connection, dict(codigo_proveedor="A", nombre_marca="MARCA A", categoria="FRENOS"))
        second, _ = guardar_repuesto(connection, dict(codigo_proveedor="B", nombre_marca="MARCA B", categoria="FRENOS"))
        other_category = connection.execute("SELECT categoria_id FROM repuestos WHERE id = ?", (second,)).fetchone()[0]
        try:
            connection.execute("UPDATE repuestos SET categoria_id = ? WHERE id = ?", (other_category, first))
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Se permitió una categoría de otra marca")
        guardar_repuesto(connection, dict(nombre_marca="MARCA B"), first)
        assert connection.execute("SELECT categoria_id FROM repuestos WHERE id = ?", (first,)).fetchone()[0] is None
        assert connection.execute("SELECT count(*) FROM categorias_repuestos").fetchone()[0] == 2


def test_workflow_records_history_and_closes_at_sap(tmp_path):
    path = tmp_path / "catalogo.sqlite3"
    initialize_database(path)
    with get_connection(path) as connection:
        part_id, _ = guardar_repuesto(connection, dict(codigo_proveedor="A", precio_compra="12.5"))
    try:
        with get_connection(path) as connection:
            guardar_repuesto(connection, dict(estado_gestion="Aprobado"), part_id)
    except ValueError:
        pass
    else:
        raise AssertionError("Se omitieron etapas del proceso")
    for state in ("En cotización", "Pendiente de aprobación", "Aprobado", "Pedido"):
        with get_connection(path) as connection:
            guardar_repuesto(connection, dict(estado_gestion=state), part_id)
    try:
        with get_connection(path) as connection:
            guardar_repuesto(connection, dict(estado_gestion="En SAP"), part_id)
    except ValueError as error:
        assert "código SAP" in str(error)
    else:
        raise AssertionError("Se permitió cerrar sin código SAP")
    with get_connection(path) as connection:
        guardar_repuesto(connection, dict(estado_gestion="En SAP", codigo_sap="SAP-01"), part_id)
        assert guardar_repuesto(connection, dict(estado_gestion="En SAP"), part_id) == (part_id, False)
        assert connection.execute("SELECT count(*) FROM historial_estados").fetchone()[0] == 6
        guardar_repuesto(connection, dict(descripcion="Descripción técnica actualizada"), part_id)
    try:
        with get_connection(path) as connection:
            guardar_repuesto(connection, dict(precio_compra="20"), part_id)
    except ValueError as error:
        assert "cerrado" in str(error)
    else:
        raise AssertionError("Se modificó la gestión comercial cerrada")


def test_failed_workflow_import_rolls_back_whole_batch(tmp_path):
    path = tmp_path / "catalogo.sqlite3"
    initialize_database(path)
    with get_connection(path) as connection:
        guardar_repuesto(connection, dict(codigo_proveedor="A"))
        guardar_repuesto(connection, dict(codigo_proveedor="B"))
    data = pd.DataFrame([{"codigo_proveedor": "A", "estado_gestion": "En cotización"},
                         {"codigo_proveedor": "B", "estado_gestion": "Pedido"}])
    batch = stage_dataframe(data, "estados.csv", db_path=path)
    try:
        confirm_batch(batch, db_path=path)
    except ValueError:
        pass
    else:
        raise AssertionError("El lote debía rechazarse por una transición inválida")
    with get_connection(path) as connection:
        assert connection.execute("SELECT count(*) FROM historial_estados").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM repuestos WHERE estado_gestion = 'propuesto'").fetchone()[0] == 2
        assert connection.execute("SELECT estado FROM lotes_importacion WHERE id = ?", (batch,)).fetchone()[0] == "staged"
