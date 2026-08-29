from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from database import DEFAULT_DB_PATH, execute, fetch_all, get_connection, initialize_database
from descriptions import refresh_long_description
from importer import confirm_batch, read_source, stage_dataframe

st.set_page_config(page_title="Catálogo de repuestos", page_icon="+", layout="wide")
initialize_database()

st.title("Catálogo de repuestos")
st.caption("Centralización, calidad de datos y descripción automática")

parts_count = fetch_all("SELECT COUNT(*) AS total FROM parts")[0]["total"]
active_count = fetch_all("SELECT COUNT(*) AS total FROM parts WHERE is_active = 1")[0]["total"]
applications_count = fetch_all("SELECT COUNT(*) AS total FROM part_applications")[0]["total"]
batches_count = fetch_all("SELECT COUNT(*) AS total FROM import_batches")[0]["total"]
metrics = st.columns(4)
metrics[0].metric("Repuestos", parts_count)
metrics[1].metric("Activos", active_count)
metrics[2].metric("Aplicaciones", applications_count)
metrics[3].metric("Cargas", batches_count)

search = st.text_input("Buscar por código SAP o descripción")
query = "SELECT id, sap_code, supplier_code, description, measure, brand_name, is_active, updated_at FROM parts"
parameters: tuple[str, ...] = ()
if search.strip():
    query += " WHERE upper(sap_code) LIKE upper(?) OR upper(description) LIKE upper(?)"
    term = f"%{search.strip()}%"
    parameters = (term, term)
query += " ORDER BY updated_at DESC, id DESC LIMIT 200"
parts = fetch_all(query, parameters)

left, right = st.columns([1.5, 1])
with left:
    st.subheader("Catálogo")
    st.dataframe([dict(row) for row in parts], use_container_width=True, hide_index=True)
with right:
    st.subheader("Nuevo repuesto")
    with st.form("new_part", clear_on_submit=True):
        sap_code = st.text_input("Código SAP *")
        description = st.text_input("Descripción *")
        measure = st.text_input("Medida")
        supplier_code = st.text_input("Código proveedor")
        brand_name = st.text_input("Marca del repuesto")
        submitted = st.form_submit_button("Guardar repuesto", type="primary")
    if submitted:
        if not sap_code.strip() or not description.strip():
            st.error("Código SAP y descripción son obligatorios.")
        else:
            try:
                execute(
                    "INSERT INTO parts (sap_code, description, measure, supplier_code, brand_name) VALUES (?, ?, ?, ?, ?)",
                    (sap_code.strip(), description.strip(), measure.strip() or None, supplier_code.strip() or None, brand_name.strip() or None),
                )
                with get_connection() as connection:
                    part = connection.execute("SELECT id FROM parts WHERE upper(sap_code) = upper(?)", (sap_code.strip(),)).fetchone()
                    refresh_long_description(connection, part["id"])
                st.success("Repuesto guardado.")
                st.rerun()
            except Exception as error:
                st.error(f"No fue posible guardar el repuesto: {error}")

st.divider()
st.subheader("Importación ELT")
source_file = st.file_uploader("Cargar archivo CSV o Excel", type=["csv", "xlsx", "xls"])
if source_file:
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(source_file.name).suffix) as temporary:
        temporary.write(source_file.getvalue())
        temporary_path = temporary.name
    try:
        dataframe = read_source(temporary_path)
        st.write(f"Vista previa: {len(dataframe)} filas")
        st.dataframe(dataframe.head(20), use_container_width=True, hide_index=True)
        if st.button("Enviar a staging", type="primary"):
            batch_id = stage_dataframe(dataframe, source_file.name)
            st.session_state["last_batch_id"] = batch_id
            st.success(f"Carga {batch_id} preparada para revisión.")
    except Exception as error:
        st.error(f"No fue posible leer el archivo: {error}")

last_batch_id = st.session_state.get("last_batch_id")
if last_batch_id:
    batch = fetch_all("SELECT * FROM import_batches WHERE id = ?", (last_batch_id,))[0]
    st.info(f"Carga {last_batch_id}: {batch['valid_rows']} filas válidas y {batch['error_rows']} con errores.")
    staged_rows = fetch_all("SELECT row_number, status, errors, normalized_data FROM import_staging_rows WHERE batch_id = ? ORDER BY row_number", (last_batch_id,))
    st.dataframe([dict(row) for row in staged_rows], use_container_width=True, hide_index=True)
    if batch["status"] == "staged" and st.button("Confirmar filas válidas", type="primary"):
        inserted, skipped = confirm_batch(last_batch_id)
        st.success(f"Importación confirmada: {inserted} insertados, {skipped} omitidos por duplicidad.")
        st.rerun()

st.divider()
st.subheader("Cargas recientes")
batches = fetch_all("SELECT id, file_name, status, total_rows, valid_rows, error_rows, created_at FROM import_batches ORDER BY id DESC LIMIT 20")
st.dataframe([dict(row) for row in batches], use_container_width=True, hide_index=True)
