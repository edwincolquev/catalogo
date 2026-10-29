from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

from database import execute, fetch_all, get_connection, initialize_database, using_postgres
from descriptions import generate_application_summary, generate_long_description, refresh_long_description
from importer import confirm_batch, plantilla_maestro_bytes, read_source, save_application, stage_dataframe
from schema_names import normalize_import_data
from gestion import CAMPOS_GESTION, ESTADOS, guardar_repuesto
from gestion_ui import administrar_clasificacion, campos_clasificacion, campos_comerciales, mostrar_gestion
from hoja_ui import hay_cambios_hoja, mostrar_hoja


st.set_page_config(page_title="Catálogo de repuestos", page_icon="+", layout="wide")
initialize_database()
st.title("Catálogo de repuestos")
st.caption("Repuestos, aplicaciones, importación y descripciones · Base: " +
           ("Supabase" if using_postgres() else "SQLite local"))

counts = fetch_all("""SELECT
    (SELECT COUNT(*) FROM repuestos) AS repuestos,
    (SELECT COUNT(*) FROM aplicaciones_repuestos) AS applications,
    (SELECT COUNT(*) FROM lotes_importacion) AS batches""")[0]
columns = st.columns(3)
columns[0].metric("Repuestos", counts["repuestos"])
columns[1].metric("Aplicaciones", counts["applications"])
columns[2].metric("Cargas", counts["batches"])

catalog_tab, import_tab, batches_tab, classification_tab = st.tabs(["Catálogo", "Importar", "Cargas", "Clasificación"])

with catalog_tab:
    pending_sheet = hay_cambios_hoja()
    brands = {row["id"]: row["nombre"] for row in fetch_all("SELECT id, nombre FROM marcas_repuestos ORDER BY nombre")}
    filter_cols = st.columns([2, 2, 1])
    brand_filter = filter_cols[0].selectbox("Filtrar por MARCA", [None, -1, *brands],
                                           format_func=lambda value: "Todas las marcas" if value is None else (
                                               "Sin marca" if value == -1 else brands[value]),
                                           disabled=pending_sheet, key="filtro_marca")
    state_filter = filter_cols[1].selectbox("Filtrar por estado", [None, *ESTADOS],
                                           format_func=lambda value: ESTADOS.get(value, "Todos"), disabled=pending_sheet)
    row_limit = filter_cols[2].selectbox("Filas a mostrar", [200, 500, 1000, None],
                                        format_func=lambda value: "Todas" if value is None else str(value), disabled=pending_sheet)
    search = st.text_input("Buscar por proveedor, SAP o descripción", disabled=pending_sheet)
    params = ()
    conditions = []
    if brand_filter == -1:
        conditions.append("marca_id IS NULL")
    elif brand_filter is not None:
        conditions.append("marca_id = ?")
        params += (brand_filter,)
    if search.strip():
        conditions.append("""(upper(codigo_proveedor) LIKE upper(?) OR upper(codigo_sap) LIKE upper(?)
                   OR upper(descripcion) LIKE upper(?))""")
        term = f"%{search.strip()}%"
        params += (term, term, term)
    if state_filter:
        conditions.append("estado_gestion = ?")
        params += (state_filter,)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    total = fetch_all("SELECT COUNT(*) FROM vista_repuestos" + where, params)[0][0]
    sql = "SELECT * FROM vista_repuestos" + where + " ORDER BY fecha_actualizacion DESC, id DESC"
    if row_limit is not None:
        sql += " LIMIT ?"
        params += (row_limit,)
    repuestos = fetch_all(sql, params)
    seleccionados = mostrar_hoja(repuestos, (brand_filter, state_filter, search, row_limit), total)

    with st.expander("Nuevo repuesto"):
        new_classification = campos_clasificacion("nuevo")
        with st.form("create_part", clear_on_submit=True):
            supplier = st.text_input("Código proveedor *")
            sap = st.text_input("Código SAP")
            descripcion = st.text_input("Descripción")
            medida = st.text_input("Medida")
            new_commercial = campos_comerciales()
            create = st.form_submit_button("Crear repuesto", type="primary")
        if create:
            if not supplier.strip():
                st.error("El código de proveedor es obligatorio.")
            else:
                try:
                    with get_connection() as connection:
                        created_id, _ = guardar_repuesto(
                            connection, dict(codigo_proveedor=supplier, codigo_sap=sap, descripcion=descripcion, medida=medida)
                            | new_classification | new_commercial,
                        )
                        refresh_long_description(connection, created_id)
                    st.success("Repuesto creado.")
                    st.rerun()
                except Exception as error:
                    st.error(f"No fue posible crear el repuesto: {error}")

    if repuestos and not seleccionados:
        st.info("Seleccione una fila de la hoja de trabajo para administrar ese repuesto.")
    elif len(seleccionados) > 1:
        st.info("Hay varias filas seleccionadas. Deje solo una para administrar un repuesto.")
    if len(seleccionados) == 1:
        repuesto_id = seleccionados[0]
        part = fetch_all("SELECT * FROM vista_repuestos WHERE id = ?", (repuesto_id,))[0]
        st.subheader(f"Administrar repuesto: {part['codigo_proveedor'] or part['codigo_sap'] or repuesto_id}")
        with st.form(f"edit_part_{repuesto_id}"):
            cols = st.columns(2)
            supplier_edit = cols[0].text_input("Código proveedor *", value=part["codigo_proveedor"] or "")
            sap_edit = cols[1].text_input("Código SAP", value=part["codigo_sap"] or "")
            description_edit = st.text_input("Descripción", value=part["descripcion"] or "")
            measure_edit = st.text_input("Medida", value=part["medida"] or "")
            active_edit = st.checkbox("Activo", value=bool(part["activo"]))
            save_part = st.form_submit_button("Guardar cambios", type="primary")
        if save_part:
            if not supplier_edit.strip():
                st.error("El código de proveedor es obligatorio.")
            else:
                try:
                    with get_connection() as connection:
                        guardar_repuesto(connection, dict(codigo_proveedor=supplier_edit, codigo_sap=sap_edit,
                                                         descripcion=description_edit, medida=measure_edit,
                                                         activo=active_edit), repuesto_id)
                        refresh_long_description(connection, repuesto_id)
                    st.success("Repuesto actualizado.")
                    st.rerun()
                except Exception as error:
                    st.error(f"No fue posible actualizar: {error}")

        mostrar_gestion(part)
        with get_connection(autocommit=True) as connection:
            descripcion_generada = generate_long_description(connection, repuesto_id)
            application_summary = generate_application_summary(connection, repuesto_id)
        st.text_area("Descripción generada", value=descripcion_generada, height=140, disabled=True)
        st.text_area("Aplicaciones en formato de catálogo", value=application_summary, height=90, disabled=True)

        left, right = st.columns(2)
        with left:
            st.subheader("Códigos OEM")
            oems = fetch_all("SELECT id, codigo_oem FROM codigos_oem WHERE repuesto_id = ? ORDER BY codigo_oem", (repuesto_id,))
            st.dataframe([dict(row) for row in oems], hide_index=True, width="stretch")
            with st.form(f"oem_add_{repuesto_id}", clear_on_submit=True):
                oem_value = st.text_input("Nuevo OEM")
                add_oem = st.form_submit_button("Añadir OEM")
            if add_oem and oem_value.strip():
                try:
                    with get_connection() as connection:
                        exists = connection.execute(
                            "SELECT 1 FROM codigos_oem WHERE repuesto_id = ? AND upper(trim(codigo_oem)) = upper(trim(?))",
                            (repuesto_id, oem_value),
                        ).fetchone()
                        if not exists:
                            connection.execute("INSERT INTO codigos_oem (repuesto_id, codigo_oem) VALUES (?, ?)",
                                               (repuesto_id, oem_value.strip()))
                            refresh_long_description(connection, repuesto_id)
                    st.rerun()
                except Exception as error:
                    st.error(str(error))
            if oems:
                oem_delete = st.selectbox("OEM para eliminar", [row["id"] for row in oems],
                                          format_func=lambda value: next(row["codigo_oem"] for row in oems if row["id"] == value))
                current_oem = next(row["codigo_oem"] for row in oems if row["id"] == oem_delete)
                with st.form(f"oem_edit_{repuesto_id}_{oem_delete}"):
                    oem_edit = st.text_input("Editar código OEM", value=current_oem)
                    save_oem = st.form_submit_button("Guardar OEM")
                if save_oem:
                    if not oem_edit.strip():
                        st.error("El código OEM no puede quedar vacío.")
                    else:
                        try:
                            with get_connection() as connection:
                                duplicate = connection.execute(
                                    """SELECT 1 FROM codigos_oem WHERE repuesto_id = ? AND id <> ?
                                       AND upper(trim(codigo_oem)) = upper(trim(?))""",
                                    (repuesto_id, oem_delete, oem_edit),
                                ).fetchone()
                                if duplicate:
                                    raise ValueError("Este OEM ya existe para el repuesto")
                                connection.execute("UPDATE codigos_oem SET codigo_oem = ? WHERE id = ? AND repuesto_id = ?",
                                                   (oem_edit.strip(), oem_delete, repuesto_id))
                                refresh_long_description(connection, repuesto_id)
                            st.rerun()
                        except Exception as error:
                            st.error(str(error))
                if st.button("Eliminar OEM"):
                    with get_connection() as connection:
                        connection.execute("DELETE FROM codigos_oem WHERE id = ? AND repuesto_id = ?", (oem_delete, repuesto_id))
                        refresh_long_description(connection, repuesto_id)
                    st.rerun()

        with right:
            st.subheader("Referencias cruzadas")
            refs = fetch_all("""SELECT id, tipo_referencia, codigo_referencia FROM referencias_cruzadas
                                WHERE repuesto_id = ? ORDER BY tipo_referencia, codigo_referencia""", (repuesto_id,))
            st.dataframe([dict(row) for row in refs], hide_index=True, width="stretch")
            with st.form(f"ref_add_{repuesto_id}", clear_on_submit=True):
                ref_type = st.text_input("Tipo de referencia")
                ref_code = st.text_input("Código de referencia")
                add_ref = st.form_submit_button("Añadir referencia")
            if add_ref:
                if not ref_type.strip() or not ref_code.strip():
                    st.error("Tipo y código son obligatorios.")
                else:
                    with get_connection() as connection:
                        exists = connection.execute(
                            """SELECT 1 FROM referencias_cruzadas WHERE repuesto_id = ?
                               AND upper(trim(tipo_referencia)) = upper(trim(?))
                               AND upper(trim(codigo_referencia)) = upper(trim(?))""",
                            (repuesto_id, ref_type, ref_code),
                        ).fetchone()
                        if not exists:
                            connection.execute(
                                "INSERT INTO referencias_cruzadas (repuesto_id, tipo_referencia, codigo_referencia) VALUES (?, ?, ?)",
                                (repuesto_id, ref_type.strip(), ref_code.strip()),
                            )
                    st.rerun()
            if refs:
                ref_delete = st.selectbox("Referencia para eliminar", [row["id"] for row in refs],
                                          format_func=lambda value: next(
                                              f"{row['tipo_referencia']}: {row['codigo_referencia']}"
                                              for row in refs if row["id"] == value))
                current_ref = next(row for row in refs if row["id"] == ref_delete)
                with st.form(f"ref_edit_{repuesto_id}_{ref_delete}"):
                    ref_type_edit = st.text_input("Editar tipo", value=current_ref["tipo_referencia"])
                    ref_code_edit = st.text_input("Editar código", value=current_ref["codigo_referencia"])
                    save_ref = st.form_submit_button("Guardar referencia")
                if save_ref:
                    if not ref_type_edit.strip() or not ref_code_edit.strip():
                        st.error("Tipo y código son obligatorios.")
                    else:
                        try:
                            with get_connection() as connection:
                                duplicate = connection.execute(
                                    """SELECT 1 FROM referencias_cruzadas WHERE repuesto_id = ? AND id <> ?
                                       AND upper(trim(tipo_referencia)) = upper(trim(?))
                                       AND upper(trim(codigo_referencia)) = upper(trim(?))""",
                                    (repuesto_id, ref_delete, ref_type_edit, ref_code_edit),
                                ).fetchone()
                                if duplicate:
                                    raise ValueError("Esta referencia ya existe para el repuesto")
                                connection.execute(
                                    """UPDATE referencias_cruzadas SET tipo_referencia = ?, codigo_referencia = ?
                                       WHERE id = ? AND repuesto_id = ?""",
                                    (ref_type_edit.strip(), ref_code_edit.strip(), ref_delete, repuesto_id),
                                )
                            st.rerun()
                        except Exception as error:
                            st.error(str(error))
                if st.button("Eliminar referencia"):
                    execute("DELETE FROM referencias_cruzadas WHERE id = ? AND repuesto_id = ?", (ref_delete, repuesto_id))
                    st.rerun()

        st.subheader("Aplicaciones")
        applications = fetch_all(
            """SELECT a.id, b.nombre AS marca_vehiculo, m.nombre AS modelo_vehiculo, e.codigo AS codigo_motor,
                      e.descripcion AS descripcion_motor, a.cilindrada, a.anio_desde, a.anio_hasta,
                      a.texto_aplicacion
               FROM aplicaciones_repuestos a
               JOIN marcas_vehiculos b ON b.id = a.marca_id
               JOIN modelos_vehiculos m ON m.id = a.modelo_id
               LEFT JOIN tipos_motor e ON e.id = a.tipo_motor_id
               WHERE a.repuesto_id = ? ORDER BY b.nombre, m.nombre, a.anio_desde""", (repuesto_id,),
        )
        st.dataframe([dict(row) for row in applications], hide_index=True, width="stretch")
        app_by_id = {row["id"]: row for row in applications}
        app_choice = st.selectbox("Aplicación para editar", [0, *app_by_id],
                                  format_func=lambda value: "Nueva aplicación" if value == 0 else
                                  f"{app_by_id[value]['marca_vehiculo']} · {app_by_id[value]['modelo_vehiculo']} · #{value}")
        selected = app_by_id.get(app_choice)
        with st.form(f"application_{repuesto_id}_{app_choice}"):
            cols = st.columns(2)
            marca_vehiculo = cols[0].text_input("Marca vehículo *", value=selected["marca_vehiculo"] if selected else "")
            modelo_vehiculo = cols[1].text_input("Modelo *", value=selected["modelo_vehiculo"] if selected else "")
            codigo_motor = cols[0].text_input("Código motor", value=(selected["codigo_motor"] or "") if selected else "")
            descripcion_motor = cols[1].text_input("Descripción motor", value=(selected["descripcion_motor"] or "") if selected else "")
            cilindrada = cols[0].text_input("Cilindrada", value=str(selected["cilindrada"] or "") if selected else "")
            anio_desde = cols[1].text_input("Año desde", value=str(selected["anio_desde"] or "") if selected else "")
            anio_hasta = cols[0].text_input("Año hasta", value=str(selected["anio_hasta"] or "") if selected else "")
            texto_aplicacion = st.text_input("Aplicación (texto adicional)", value=(selected["texto_aplicacion"] or "") if selected else "")
            save_app = st.form_submit_button("Guardar aplicación")
        if save_app:
            data = dict(marca_vehiculo=marca_vehiculo.strip(), modelo_vehiculo=modelo_vehiculo.strip(),
                        codigo_motor=codigo_motor.strip(), descripcion_motor=descripcion_motor.strip(),
                        cilindrada=cilindrada.strip(), anio_desde=anio_desde.strip(), anio_hasta=anio_hasta.strip(),
                        texto_aplicacion=texto_aplicacion.strip())
            try:
                with get_connection() as connection:
                    saved = save_application(connection, repuesto_id, data, app_choice or None)
                    if saved:
                        refresh_long_description(connection, repuesto_id)
                if not saved:
                    st.info("La aplicación ya existe.")
                else:
                    st.success("Aplicación guardada.")
                    st.rerun()
            except Exception as error:
                st.error(f"No fue posible guardar la aplicación: {error}")
        if app_choice and st.button("Eliminar aplicación"):
            with get_connection() as connection:
                connection.execute("DELETE FROM aplicaciones_repuestos WHERE id = ? AND repuesto_id = ?", (app_choice, repuesto_id))
                refresh_long_description(connection, repuesto_id)
            st.rerun()

        st.divider()
        confirm_delete = st.checkbox("Confirmo que deseo eliminar este repuesto y sus datos asociados")
        if st.button("Eliminar repuesto", disabled=not confirm_delete):
            execute("DELETE FROM repuestos WHERE id = ?", (repuesto_id,))
            st.rerun()

with import_tab:
    st.subheader("Importar maestro CSV o Excel")
    export_cols = st.columns(2)
    export_brand = export_cols[0].selectbox(
        "Filtrar por MARCA", [None, -1, *brands],
        format_func=lambda value: "Todas las marcas" if value is None else (
            "Sin marca" if value == -1 else brands[value]
        ), key="export_filtro_marca",
    )
    export_state = export_cols[1].selectbox(
        "Filtrar por estado", [None, *ESTADOS],
        format_func=lambda value: ESTADOS.get(value, "Todos"), key="export_filtro_estado",
    )
    download_cols = st.columns(2)
    download_cols[0].download_button(
        "Descargar plantilla con clasificación y gestión",
        data=plantilla_maestro_bytes(incluir_datos=True, marca_id=export_brand, estado=export_state),
        file_name="plantilla_maestro_filtrada.csv", mime="text/csv",
    )
    download_cols[1].download_button(
        "Descargar plantilla vacía", data=plantilla_maestro_bytes(),
        file_name="plantilla_maestro_gestion.csv", mime="text/csv",
    )
    st.caption("La plantilla con datos incluye únicamente los repuestos que coinciden con ambos filtros.")
    st.caption("Los precios de compra y venta de la plantilla están expresados en USD.")
    st.caption("Un código de proveedor repetido añade datos al mismo repuesto. Los campos informados del repuesto se actualizan; los OEM y las referencias nuevos se añaden sin duplicados.")
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
                lote_id = stage_dataframe(dataframe, source_file.name)
                st.session_state["last_batch_id"] = lote_id
                st.rerun()
        except Exception as error:
            st.error(f"No fue posible leer o preparar el archivo: {error}")
    lote_id = st.session_state.get("last_batch_id")
    if lote_id:
        batch = fetch_all("SELECT * FROM lotes_importacion WHERE id = ?", (lote_id,))[0]
        st.info(f"Carga {lote_id}: {batch['filas_validas']} filas válidas y {batch['filas_error']} con errores.")
        staged = fetch_all(
            "SELECT numero_fila, estado, errores, datos_normalizados FROM filas_importacion WHERE lote_id = ? ORDER BY numero_fila",
            (lote_id,),
        )
        warning_count = sum(bool(row["errores"] and "Aviso:" in row["errores"]) for row in staged)
        if warning_count:
            st.warning(f"{warning_count} filas tienen avisos: sus aplicaciones se omitirán; los demás datos válidos sí se cargarán.")
        review = []
        existing_by_supplier = {}
        for row in staged:
            data = normalize_import_data(json.loads(row["datos_normalizados"]))
            supplier = data.get("codigo_proveedor")
            supplier_key = supplier.strip().upper() if supplier else ""
            if supplier_key and supplier_key not in existing_by_supplier:
                current = fetch_all(
                    "SELECT * FROM vista_repuestos WHERE upper(trim(codigo_proveedor)) = ?",
                    (supplier_key,),
                )
                if current:
                    repuesto_id = current[0]["id"]
                    oem_codes = fetch_all(
                        "SELECT codigo_oem FROM codigos_oem WHERE repuesto_id = ? ORDER BY upper(codigo_oem)",
                        (repuesto_id,),
                    )
                    references = fetch_all(
                        "SELECT tipo_referencia, codigo_referencia FROM referencias_cruzadas WHERE repuesto_id = ? ORDER BY upper(tipo_referencia), upper(codigo_referencia)",
                        (repuesto_id,),
                    )
                    existing_by_supplier[supplier_key] = (
                        {key: current[0][key] for key in ("codigo_proveedor", "codigo_sap", "descripcion", "medida", *CAMPOS_GESTION)},
                        ", ".join(item["codigo_oem"] for item in oem_codes),
                        ", ".join(f"{item['tipo_referencia']}: {item['codigo_referencia']}" for item in references),
                    )
                else:
                    existing_by_supplier[supplier_key] = (None, "", "")
            existing, existing_oem, existing_references = existing_by_supplier.get(supplier_key, (None, "", ""))
            review.append(dict(fila=row["numero_fila"], estado=row["estado"], avisos=row["errores"],
                               proveedor=supplier, sap_nuevo=data.get("codigo_sap"),
                               descripcion_nueva=data.get("descripcion"),
                               existente=existing,
                               oem_nuevo=data.get("codigo_oem"), oem_existentes=existing_oem,
                               referencia_nueva=(f"{data.get('tipo_referencia')}: {data.get('codigo_referencia')}"
                                                  if data.get("codigo_referencia") else None),
                               referencias_existentes=existing_references,
                               marca=data.get("marca_vehiculo"), modelo=data.get("modelo_vehiculo"),
                               motor=data.get("codigo_motor"), aplicacion=data.get("texto_aplicacion"),
                               **{field + "_nuevo": data.get(field) for field in CAMPOS_GESTION}))
        st.dataframe(review, width="stretch", hide_index=True)
        if batch["estado"] == "staged" and st.button("Confirmar filas válidas", type="primary"):
            try:
                inserted, updated = confirm_batch(lote_id)
                st.success(f"Confirmado: {inserted} repuestos nuevos y {updated} existentes actualizados.")
                st.rerun()
            except Exception as error:
                st.error(f"No se confirmó la carga; no se guardaron cambios: {error}")

with batches_tab:
    batches = fetch_all(
        """SELECT id, nombre_archivo, estado, total_filas, filas_validas, filas_error, fecha_creacion, fecha_procesamiento
           FROM lotes_importacion ORDER BY id DESC LIMIT 50"""
    )
    st.dataframe([dict(row) for row in batches], width="stretch", hide_index=True)

with classification_tab:
    administrar_clasificacion()
