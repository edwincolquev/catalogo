from copy import deepcopy

from database import get_connection, initialize_database
from gestion import guardar_repuesto
from hoja_trabajo import aplicar_edicion, cambios_hoja, filas_para_editor, guardar_cambios_hoja


def _datos(tmp_path):
    path = tmp_path / "hoja.sqlite3"
    initialize_database(path)
    with get_connection(path) as connection:
        for code, brand in (("P-1", "MARCA A"), ("P-2", "MARCA A"), ("P-3", "MARCA B")):
            guardar_repuesto(connection, dict(codigo_proveedor=code, nombre_marca=brand,
                                             categoria="FRENOS", precio_compra=2, descripcion="Inicial"))
        rows = [dict(row) for row in connection.execute("SELECT * FROM vista_repuestos ORDER BY id DESC")]
    return path, rows


def test_repetition_changes_only_selected_rows_and_not_unique_codes(tmp_path):
    _, rows = _datos(tmp_path)
    draft = filas_para_editor(rows, [rows[0]["id"], rows[2]["id"]])
    proposal = deepcopy(draft)
    proposal[2]["precio_compra"] = 3.75
    proposal[2]["codigo_sap"] = "SAP-INDIVIDUAL"
    result, _ = aplicar_edicion(draft, proposal, repetir=True)
    assert [row["precio_compra"] for row in result] == [3.75, 2, 3.75]
    assert result[0]["codigo_sap"] is None
    assert result[2]["codigo_sap"] == "SAP-INDIVIDUAL"
    # Marcar otra fila después no debe volver a propagar la edición anterior.
    selected_more = deepcopy(result)
    selected_more[1]["seleccionar"] = True
    result, _ = aplicar_edicion(result, selected_more, repetir=True)
    assert result[1]["precio_compra"] == 2


def test_brand_changes_reset_only_categories_of_changed_brands(tmp_path):
    _, rows = _datos(tmp_path)
    draft = filas_para_editor(rows, [row["id"] for row in rows])
    proposal = deepcopy(draft)
    proposal[2]["nombre_marca"] = "MARCA B"
    result, _ = aplicar_edicion(draft, proposal, repetir=True)
    assert [row["nombre_marca"] for row in result] == ["MARCA B"] * 3
    assert [row["categoria"] for row in result] == ["FRENOS", None, None]


def test_pasting_different_values_does_not_overwrite_other_selected_rows(tmp_path):
    _, rows = _datos(tmp_path)
    draft = filas_para_editor(rows, [row["id"] for row in rows])
    proposal = deepcopy(draft)
    proposal[0]["precio_compra"], proposal[1]["precio_compra"] = 8, 9
    result, notices = aplicar_edicion(draft, proposal, repetir=True)
    assert [row["precio_compra"] for row in result] == [8, 9, 2]
    assert len(notices) == 1


def test_sheet_saves_zero_blanks_and_regenerates_description(tmp_path):
    path, rows = _datos(tmp_path)
    edited = filas_para_editor(rows)
    edited[0]["precio_compra"] = 0
    edited[0]["descripcion"] = "Modificada"
    edited[1]["precio_compra"] = None
    changes = cambios_hoja(rows, edited)
    assert guardar_cambios_hoja(rows, changes, path) == 2
    with get_connection(path) as connection:
        row = connection.execute("SELECT * FROM repuestos WHERE id = ?", (rows[0]["id"],)).fetchone()
        assert row["precio_compra"] == 0
        assert row["descripcion_larga"] == "Modificada"
        assert connection.execute("SELECT precio_compra FROM repuestos WHERE id = ?", (rows[1]["id"],)).fetchone()[0] is None
        assert connection.execute("SELECT precio_compra FROM repuestos WHERE id = ?", (rows[2]["id"],)).fetchone()[0] == 2


def test_invalid_bulk_state_rolls_back_prices_and_history(tmp_path):
    path, rows = _datos(tmp_path)
    changes = {
        rows[0]["id"]: dict(precio_compra=10, estado_gestion="En cotización"),
        rows[1]["id"]: dict(estado_gestion="Pedido"),
    }
    try:
        guardar_cambios_hoja(rows, changes, path)
    except ValueError as error:
        assert rows[1]["codigo_proveedor"] in str(error)
    else:
        raise AssertionError("Se guardó un cambio de estado inválido")
    with get_connection(path) as connection:
        assert connection.execute("SELECT count(*) FROM historial_estados").fetchone()[0] == 3
        assert connection.execute("SELECT count(*) FROM repuestos WHERE precio_compra = 2 AND estado_gestion = 'propuesto'").fetchone()[0] == 3


def test_sheet_detects_stale_rows_and_rejects_unshown_ids(tmp_path):
    path, rows = _datos(tmp_path)
    with get_connection(path) as connection:
        guardar_repuesto(connection, dict(precio_compra=7), rows[1]["id"])
    try:
        guardar_cambios_hoja(rows, {rows[0]["id"]: {"precio_compra": 10}, rows[1]["id"]: {"precio_compra": 12}}, path)
    except ValueError as error:
        assert "cambiaron" in str(error)
    else:
        raise AssertionError("Se sobrescribió un cambio realizado en otra sesión")
    with get_connection(path) as connection:
        assert connection.execute("SELECT precio_compra FROM repuestos WHERE id = ?", (rows[0]["id"],)).fetchone()[0] == 2
        assert connection.execute("SELECT precio_compra FROM repuestos WHERE id = ?", (rows[1]["id"],)).fetchone()[0] == 7
    try:
        guardar_cambios_hoja(rows[:1], {rows[2]["id"]: {"precio_compra": 20}}, path)
    except ValueError as error:
        assert "mostradas" in str(error)
    else:
        raise AssertionError("Se modificó una fila fuera de la hoja")


def test_sheet_keeps_sap_closed_and_rejects_wrong_category(tmp_path):
    path, rows = _datos(tmp_path)
    with get_connection(path) as connection:
        sap_id, _ = guardar_repuesto(connection, dict(codigo_proveedor="SAP", codigo_sap="SAP-1", precio_compra=5))
        sap_row = dict(connection.execute("SELECT * FROM vista_repuestos WHERE id = ?", (sap_id,)).fetchone())
        other_brand = connection.execute("INSERT INTO marcas_repuestos (nombre) VALUES ('OTRA')").lastrowid
        connection.execute("INSERT INTO categorias_repuestos (marca_id, nombre) VALUES (?, 'EXCLUSIVA')", (other_brand,))
    for originals, changes, message in (
        ([sap_row], {sap_id: {"precio_compra": 10}}, "cerrado"),
        (rows, {rows[0]["id"]: {"categoria": "EXCLUSIVA"}}, "no pertenece"),
        (rows, {rows[0]["id"]: {"codigo_proveedor": ""}}, "vacío"),
        (rows, {rows[0]["id"]: {"id": 1000}}, "no editables"),
    ):
        try:
            guardar_cambios_hoja(originals, changes, path)
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError("La validación debía impedir guardar el cambio")
