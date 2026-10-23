from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

from database import execute, fetch_all, get_connection, initialize_database
from descriptions import generate_application_summary, refresh_long_description
from importer import confirm_batch, read_source, save_application, stage_dataframe


st.set_page_config(page_title="Catálogo de repuestos", page_icon="+", layout="wide")
initialize_database()
st.title("Catálogo de repuestos")
st.caption("Repuestos, aplicaciones, importación y descripciones")

counts = fetch_all("""SELECT
    (SELECT COUNT(*) FROM parts) AS parts,
    (SELECT COUNT(*) FROM part_applications) AS applications,
    (SELECT COUNT(*) FROM import_batches) AS batches""")[0]
columns = st.columns(3)
columns[0].metric("Repuestos", counts["parts"])
columns[1].metric("Aplicaciones", counts["applications"])
columns[2].metric("Cargas", counts["batches"])

catalog_tab, import_tab, batches_tab = st.tabs(["Catálogo", "Importar", "Cargas"])

with catalog_tab:
    search = st.text_input("Buscar por proveedor, SAP o descripción")
    sql = """SELECT id, supplier_code, sap_code, description, measure, brand_name,
                    is_active, updated_at FROM parts"""
    params = ()
    if search.strip():
        sql += """ WHERE upper(supplier_code) LIKE upper(?) OR upper(sap_code) LIKE upper(?)
                   OR upper(description) LIKE upper(?)"""
        term = f"%{search.strip()}%"
        params = (term, term, term)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT 200"
    parts = fetch_all(sql, params)
    st.dataframe([dict(part) for part in parts], width="stretch", hide_index=True)

    with st.expander("Nuevo repuesto"):
        with st.form("create_part", clear_on_submit=True):
            supplier = st.text_input("Código proveedor *")
            sap = st.text_input("Código SAP")
            description = st.text_input("Descripción")
            measure = st.text_input("Medida")
            brand = st.text_input("Marca comercial")
            create = st.form_submit_button("Crear repuesto", type="primary")
        if create:
            if not supplier.strip():
                st.error("El código de proveedor es obligatorio.")
            else:
                try:
                    with get_connection() as connection:
                        cursor = connection.execute(
                            """INSERT INTO parts (supplier_code, sap_code, description, measure, brand_name)
                               VALUES (?, ?, ?, ?, ?)""",
                            (supplier.strip(), sap.strip() or None, description.strip() or None,
                             measure.strip() or None, brand.strip() or None),
                        )
                        refresh_long_description(connection, int(cursor.lastrowid))
                    st.success("Repuesto creado.")
                    st.rerun()
                except Exception as error:
                    st.error(f"No fue posible crear el repuesto: {error}")

    if parts:
        choices = {part["id"]: f"{part['supplier_code'] or 'Sin proveedor'} · {part['sap_code'] or 'Sin SAP'} · {part['description'] or ''}" for part in parts}
        part_id = st.selectbox("Seleccionar repuesto para administrar", list(choices), format_func=choices.get)
        part = fetch_all("SELECT * FROM parts WHERE id = ?", (part_id,))[0]
        with st.form(f"edit_part_{part_id}"):
            cols = st.columns(2)
            supplier_edit = cols[0].text_input("Código proveedor *", value=part["supplier_code"] or "")
            sap_edit = cols[1].text_input("Código SAP", value=part["sap_code"] or "")
            description_edit = st.text_input("Descripción", value=part["description"] or "")
            measure_edit = st.text_input("Medida", value=part["measure"] or "")
            brand_edit = st.text_input("Marca comercial", value=part["brand_name"] or "")
            active_edit = st.checkbox("Activo", value=bool(part["is_active"]))
            save_part = st.form_submit_button("Guardar cambios", type="primary")
        if save_part:
            if not supplier_edit.strip():
                st.error("El código de proveedor es obligatorio.")
            else:
                try:
                    with get_connection() as connection:
                        connection.execute(
                            """UPDATE parts SET supplier_code = ?, sap_code = ?, description = ?,
                               measure = ?, brand_name = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
                               WHERE id = ?""",
                            (supplier_edit.strip(), sap_edit.strip() or None, description_edit.strip() or None,
                             measure_edit.strip() or None, brand_edit.strip() or None, int(active_edit), part_id),
                        )
                        refresh_long_description(connection, part_id)
                    st.success("Repuesto actualizado.")
                    st.rerun()
                except Exception as error:
                    st.error(f"No fue posible actualizar: {error}")

        with get_connection() as connection:
            application_summary = generate_application_summary(connection, part_id)
        st.text_area("Descripción generada", value=part["long_description"] or "", height=140, disabled=True)
        st.text_area("Aplicaciones en formato de catálogo", value=application_summary, height=90, disabled=True)

        left, right = st.columns(2)
        with left:
            st.subheader("Códigos OEM")
            oems = fetch_all("SELECT id, oem_code FROM part_oem_codes WHERE part_id = ? ORDER BY oem_code", (part_id,))
            st.dataframe([dict(row) for row in oems], hide_index=True, width="stretch")
            with st.form(f"oem_add_{part_id}", clear_on_submit=True):
                oem_value = st.text_input("Nuevo OEM")
                add_oem = st.form_submit_button("Añadir OEM")
            if add_oem and oem_value.strip():
                try:
                    with get_connection() as connection:
                        exists = connection.execute(
                            "SELECT 1 FROM part_oem_codes WHERE part_id = ? AND upper(trim(oem_code)) = upper(trim(?))",
                            (part_id, oem_value),
                        ).fetchone()
                        if not exists:
                            connection.execute("INSERT INTO part_oem_codes (part_id, oem_code) VALUES (?, ?)",
                                               (part_id, oem_value.strip()))
                            refresh_long_description(connection, part_id)
                    st.rerun()
                except Exception as error:
                    st.error(str(error))
            if oems:
                oem_delete = st.selectbox("OEM para eliminar", [row["id"] for row in oems],
                                          format_func=lambda value: next(row["oem_code"] for row in oems if row["id"] == value))
                current_oem = next(row["oem_code"] for row in oems if row["id"] == oem_delete)
                with st.form(f"oem_edit_{part_id}_{oem_delete}"):
                    oem_edit = st.text_input("Editar código OEM", value=current_oem)
                    save_oem = st.form_submit_button("Guardar OEM")
                if save_oem:
                    if not oem_edit.strip():
                        st.error("El código OEM no puede quedar vacío.")
                    else:
                        try:
                            with get_connection() as connection:
                                duplicate = connection.execute(
                                    """SELECT 1 FROM part_oem_codes WHERE part_id = ? AND id <> ?
                                       AND upper(trim(oem_code)) = upper(trim(?))""",
                                    (part_id, oem_delete, oem_edit),
                                ).fetchone()
                                if duplicate:
                                    raise ValueError("Este OEM ya existe para el repuesto")
                                connection.execute("UPDATE part_oem_codes SET oem_code = ? WHERE id = ? AND part_id = ?",
                                                   (oem_edit.strip(), oem_delete, part_id))
                                refresh_long_description(connection, part_id)
                            st.rerun()
                        except Exception as error:
                            st.error(str(error))
                if st.button("Eliminar OEM"):
                    with get_connection() as connection:
                        connection.execute("DELETE FROM part_oem_codes WHERE id = ? AND part_id = ?", (oem_delete, part_id))
                        refresh_long_description(connection, part_id)
                    st.rerun()

        with right:
            st.subheader("Referencias cruzadas")
            refs = fetch_all("""SELECT id, reference_type, reference_code FROM part_cross_references
                                WHERE part_id = ? ORDER BY reference_type, reference_code""", (part_id,))
            st.dataframe([dict(row) for row in refs], hide_index=True, width="stretch")
            with st.form(f"ref_add_{part_id}", clear_on_submit=True):
                ref_type = st.text_input("Tipo de referencia")
                ref_code = st.text_input("Código de referencia")
                add_ref = st.form_submit_button("Añadir referencia")
            if add_ref:
                if not ref_type.strip() or not ref_code.strip():
                    st.error("Tipo y código son obligatorios.")
                else:
                    with get_connection() as connection:
                        exists = connection.execute(
                            """SELECT 1 FROM part_cross_references WHERE part_id = ?
                               AND upper(trim(reference_type)) = upper(trim(?))
                               AND upper(trim(reference_code)) = upper(trim(?))""",
                            (part_id, ref_type, ref_code),
                        ).fetchone()
                        if not exists:
                            connection.execute(
                                "INSERT INTO part_cross_references (part_id, reference_type, reference_code) VALUES (?, ?, ?)",
                                (part_id, ref_type.strip(), ref_code.strip()),
                            )
                    st.rerun()
            if refs:
                ref_delete = st.selectbox("Referencia para eliminar", [row["id"] for row in refs],
                                          format_func=lambda value: next(
                                              f"{row['reference_type']}: {row['reference_code']}"
                                              for row in refs if row["id"] == value))
                current_ref = next(row for row in refs if row["id"] == ref_delete)
                with st.form(f"ref_edit_{part_id}_{ref_delete}"):
                    ref_type_edit = st.text_input("Editar tipo", value=current_ref["reference_type"])
                    ref_code_edit = st.text_input("Editar código", value=current_ref["reference_code"])
                    save_ref = st.form_submit_button("Guardar referencia")
                if save_ref:
                    if not ref_type_edit.strip() or not ref_code_edit.strip():
                        st.error("Tipo y código son obligatorios.")
                    else:
                        try:
                            with get_connection() as connection:
                                duplicate = connection.execute(
                                    """SELECT 1 FROM part_cross_references WHERE part_id = ? AND id <> ?
                                       AND upper(trim(reference_type)) = upper(trim(?))
                                       AND upper(trim(reference_code)) = upper(trim(?))""",
                                    (part_id, ref_delete, ref_type_edit, ref_code_edit),
                                ).fetchone()
                                if duplicate:
                                    raise ValueError("Esta referencia ya existe para el repuesto")
                                connection.execute(
                                    """UPDATE part_cross_references SET reference_type = ?, reference_code = ?
                                       WHERE id = ? AND part_id = ?""",
                                    (ref_type_edit.strip(), ref_code_edit.strip(), ref_delete, part_id),
                                )
                            st.rerun()
                        except Exception as error:
                            st.error(str(error))
                if st.button("Eliminar referencia"):
                    execute("DELETE FROM part_cross_references WHERE id = ? AND part_id = ?", (ref_delete, part_id))
                    st.rerun()

        st.subheader("Aplicaciones")
        applications = fetch_all(
            """SELECT a.id, b.name AS vehicle_brand, m.name AS vehicle_model, e.code AS engine_code,
                      e.description AS engine_description, a.displacement, a.year_from, a.year_to,
                      a.application_text
               FROM part_applications a
               JOIN vehicle_brands b ON b.id = a.brand_id
               JOIN vehicle_models m ON m.id = a.model_id
               LEFT JOIN engine_types e ON e.id = a.engine_type_id
               WHERE a.part_id = ? ORDER BY b.name, m.name, a.year_from""", (part_id,),
        )
        st.dataframe([dict(row) for row in applications], hide_index=True, width="stretch")
        app_by_id = {row["id"]: row for row in applications}
        app_choice = st.selectbox("Aplicación para editar", [0, *app_by_id],
                                  format_func=lambda value: "Nueva aplicación" if value == 0 else
                                  f"{app_by_id[value]['vehicle_brand']} · {app_by_id[value]['vehicle_model']} · #{value}")
        selected = app_by_id.get(app_choice)
        with st.form(f"application_{part_id}_{app_choice}"):
            cols = st.columns(2)
            vehicle_brand = cols[0].text_input("Marca vehículo *", value=selected["vehicle_brand"] if selected else "")
            vehicle_model = cols[1].text_input("Modelo *", value=selected["vehicle_model"] if selected else "")
            engine_code = cols[0].text_input("Código motor", value=(selected["engine_code"] or "") if selected else "")
            engine_description = cols[1].text_input("Descripción motor", value=(selected["engine_description"] or "") if selected else "")
            displacement = cols[0].text_input("Cilindrada", value=str(selected["displacement"] or "") if selected else "")
            year_from = cols[1].text_input("Año desde", value=str(selected["year_from"] or "") if selected else "")
            year_to = cols[0].text_input("Año hasta", value=str(selected["year_to"] or "") if selected else "")
            application_text = st.text_input("Aplicación (texto adicional)", value=(selected["application_text"] or "") if selected else "")
            save_app = st.form_submit_button("Guardar aplicación")
        if save_app:
            data = dict(vehicle_brand=vehicle_brand.strip(), vehicle_model=vehicle_model.strip(),
                        engine_code=engine_code.strip(), engine_description=engine_description.strip(),
                        displacement=displacement.strip(), year_from=year_from.strip(), year_to=year_to.strip(),
                        application_text=application_text.strip())
            try:
                with get_connection() as connection:
                    saved = save_application(connection, part_id, data, app_choice or None)
                    if saved:
                        refresh_long_description(connection, part_id)
                if not saved:
                    st.info("La aplicación ya existe.")
                else:
                    st.success("Aplicación guardada.")
                    st.rerun()
            except Exception as error:
                st.error(f"No fue posible guardar la aplicación: {error}")
        if app_choice and st.button("Eliminar aplicación"):
            with get_connection() as connection:
                connection.execute("DELETE FROM part_applications WHERE id = ? AND part_id = ?", (app_choice, part_id))
                refresh_long_description(connection, part_id)
            st.rerun()

        st.divider()
        confirm_delete = st.checkbox("Confirmo que deseo eliminar este repuesto y sus datos asociados")
        if st.button("Eliminar repuesto", disabled=not confirm_delete):
            execute("DELETE FROM parts WHERE id = ?", (part_id,))
            st.rerun()

with import_tab:
    st.subheader("Importar maestro CSV o Excel")
    st.caption("Un código de proveedor repetido añade datos al mismo repuesto. Los valores nuevos reemplazan los existentes; las celdas vacías los conservan.")
    source_file = st.file_uploader("Archivo maestro", type=["csv", "xlsx", "xls"])
    if source_file:
        try:
            with tempfile.TemporaryDirectory() as folder:
                source_path = Path(folder) / Path(source_file.name).name
                source_path.write_bytes(source_file.getvalue())
                dataframe = read_source(source_path)
            st.write(f"{len(dataframe)} filas detectadas")
            st.dataframe(dataframe.head(20), width="stretch", hide_index=True)
            if st.button("Preparar carga", type="primary"):
                batch_id = stage_dataframe(dataframe, source_file.name)
                st.session_state["last_batch_id"] = batch_id
                st.rerun()
        except Exception as error:
            st.error(f"No fue posible leer o preparar el archivo: {error}")
    batch_id = st.session_state.get("last_batch_id")
    if batch_id:
        batch = fetch_all("SELECT * FROM import_batches WHERE id = ?", (batch_id,))[0]
        st.info(f"Carga {batch_id}: {batch['valid_rows']} filas válidas y {batch['error_rows']} con errores.")
        staged = fetch_all(
            "SELECT row_number, status, errors, normalized_data FROM import_staging_rows WHERE batch_id = ? ORDER BY row_number",
            (batch_id,),
        )
        warning_count = sum(bool(row["errors"] and "Aviso:" in row["errors"]) for row in staged)
        if warning_count:
            st.warning(f"{warning_count} filas tienen avisos: sus aplicaciones se omitirán; los demás datos válidos sí se cargarán.")
        review = []
        for row in staged:
            data = json.loads(row["normalized_data"])
            supplier = data.get("supplier_code")
            current = fetch_all(
                "SELECT supplier_code, sap_code, description, measure FROM parts WHERE upper(trim(supplier_code)) = upper(trim(?))",
                (supplier,),
            ) if supplier else []
            review.append(dict(fila=row["row_number"], estado=row["status"], avisos=row["errors"],
                               proveedor=supplier, sap_nuevo=data.get("sap_code"),
                               descripcion_nueva=data.get("description"),
                               existente=dict(current[0]) if current else None,
                               marca=data.get("vehicle_brand"), modelo=data.get("vehicle_model"),
                               motor=data.get("engine_code"), aplicacion=data.get("application_text")))
        st.dataframe(review, width="stretch", hide_index=True)
        if batch["status"] == "staged" and st.button("Confirmar filas válidas", type="primary"):
            try:
                inserted, updated = confirm_batch(batch_id)
                st.success(f"Confirmado: {inserted} repuestos nuevos y {updated} existentes actualizados.")
                st.rerun()
            except Exception as error:
                st.error(f"No se confirmó la carga; no se guardaron cambios: {error}")

with batches_tab:
    batches = fetch_all(
        """SELECT id, file_name, status, total_rows, valid_rows, error_rows, created_at, processed_at
           FROM import_batches ORDER BY id DESC LIMIT 50"""
    )
    st.dataframe([dict(row) for row in batches], width="stretch", hide_index=True)
