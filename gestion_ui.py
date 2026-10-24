"""Controles de clasificación y gestión comercial para Streamlit."""

import streamlit as st

from database import fetch_all, get_connection
from gestion import ESTADOS, NUMERICOS, TRANSICIONES, guardar_repuesto


def campos_clasificacion(prefix, current=None):
    units = {row["id"]: row["nombre"] for row in fetch_all("SELECT id, nombre FROM unidades_medida ORDER BY nombre")}
    brands = {row["id"]: row["nombre"] for row in fetch_all("SELECT id, nombre FROM marcas_repuestos ORDER BY nombre")}
    cols = st.columns(3)
    unit_options, brand_options = [None, *units], [None, *brands]
    unit_id = cols[0].selectbox("Unidad", unit_options,
                               index=unit_options.index(current["unidad_id"]) if current else 0,
                               format_func=lambda value: units.get(value, "Sin asignar"), key=f"{prefix}_unidad")
    brand_id = cols[1].selectbox("Marca comercial", brand_options,
                                index=brand_options.index(current["marca_id"]) if current else 0,
                                format_func=lambda value: brands.get(value, "Sin asignar"), key=f"{prefix}_marca")
    categories = {row["id"]: row["nombre"] for row in fetch_all(
        "SELECT id, nombre FROM categorias_repuestos WHERE marca_id = ? ORDER BY nombre", (brand_id,)
    )}
    category_options = [None, *categories]
    current_category = current["categoria_id"] if current and current["categoria_id"] in categories else None
    category_id = cols[2].selectbox("Categoría", category_options,
                                   index=category_options.index(current_category), disabled=brand_id is None,
                                   format_func=lambda value: categories.get(value, "Sin asignar"),
                                   key=f"{prefix}_categoria_{brand_id}")
    st.caption("Las categorías disponibles corresponden a la marca seleccionada. Puede administrar las listas en Clasificación.")
    return dict(unidad=units.get(unit_id), nombre_marca=brands.get(brand_id), categoria=categories.get(category_id))


def campos_comerciales(current=None):
    closed = bool(current and current["estado_gestion"] == "en_sap")
    states = [current["estado_gestion"], *TRANSICIONES[current["estado_gestion"]]] if current else ["propuesto", "en_sap"]
    state = st.selectbox("Estado de gestión", states, format_func=ESTADOS.get, disabled=closed)
    st.caption("Precios unitarios en dólares estadounidenses (USD). Cantidades expresadas en la unidad del repuesto.")
    labels = ("Mínimo de compra", "Precio de compra (USD)", "Precio de venta (USD)", "Cantidad de compra")
    data = {"estado_gestion": state}
    cols = st.columns(2)
    for index, (field, label) in enumerate(zip(NUMERICOS, labels)):
        value = float(current[field]) if current and current[field] is not None else None
        data[field] = cols[index % 2].number_input(label, min_value=0.0001 if field == "minimo_compra" else 0.0,
                                                  value=value, step=0.01, format="%.4f", disabled=closed)
    if closed:
        st.info("Seguimiento comercial cerrado: la gestión de este repuesto continúa en SAP.")
    if data["minimo_compra"] is not None and data["cantidad_compra"] is not None and data["cantidad_compra"] < data["minimo_compra"]:
        st.warning("La cantidad de compra es menor que el mínimo indicado.")
    return data


def mostrar_gestion(current):
    st.subheader("Clasificación y gestión comercial")
    classification = campos_clasificacion(f"editar_{current['id']}", current)
    with st.form(f"gestion_{current['id']}"):
        commercial = campos_comerciales(current)
        save = st.form_submit_button("Guardar clasificación y gestión")
    if save:
        try:
            with get_connection() as connection:
                guardar_repuesto(connection, classification | commercial, current["id"])
            st.rerun()
        except Exception as error:
            st.error(f"No se guardaron los cambios: {error}")
    with st.expander("Historial de estados"):
        rows = fetch_all("SELECT estado_anterior, estado_nuevo, fecha_cambio FROM historial_estados WHERE repuesto_id = ? ORDER BY id", (current["id"],))
        st.dataframe([dict(anterior=ESTADOS.get(row["estado_anterior"], "Inicio"),
                           nuevo=ESTADOS[row["estado_nuevo"]], fecha=row["fecha_cambio"]) for row in rows],
                     hide_index=True, width="stretch")


def administrar_clasificacion():
    st.subheader("Unidades, marcas comerciales y categorías")
    tables = {"Unidades": "unidades_medida", "Marcas comerciales": "marcas_repuestos", "Categorías": "categorias_repuestos"}
    kind = st.selectbox("Lista a administrar", list(tables))
    table = tables[kind]
    brand_id = None
    if table == "categorias_repuestos":
        brands = {row["id"]: row["nombre"] for row in fetch_all("SELECT id, nombre FROM marcas_repuestos ORDER BY nombre")}
        if not brands:
            st.info("Primero agregue una marca comercial.")
            return
        brand_id = st.selectbox("Marca de las categorías", list(brands), format_func=brands.get)
    where = " WHERE marca_id = ?" if brand_id is not None else ""
    rows = fetch_all(f"SELECT id, nombre FROM {table}{where} ORDER BY nombre", (brand_id,) if where else ())
    st.dataframe([dict(row) for row in rows], hide_index=True, width="stretch")
    with st.form(f"alta_{table}_{brand_id}", clear_on_submit=True):
        name = st.text_input("Nombre nuevo")
        create = st.form_submit_button("Agregar")
    if create:
        try:
            if not name.strip():
                raise ValueError("El nombre no puede quedar vacío")
            with get_connection() as connection:
                if brand_id is None:
                    connection.execute(f"INSERT INTO {table} (nombre) VALUES (?)", (name.strip(),))
                else:
                    connection.execute(f"INSERT INTO {table} (marca_id, nombre) VALUES (?, ?)", (brand_id, name.strip()))
            st.rerun()
        except Exception as error:
            st.error(f"No se agregó el valor; revise si ya existe: {error}")
    if rows:
        options = {row["id"]: row["nombre"] for row in rows}
        selected = st.selectbox("Valor para editar", list(options), format_func=options.get, key=f"lista_{table}_{brand_id}")
        with st.form(f"editar_lista_{table}_{selected}"):
            new_name = st.text_input("Nombre", value=options[selected])
            save = st.form_submit_button("Guardar nombre")
        if save:
            try:
                if not new_name.strip():
                    raise ValueError("El nombre no puede quedar vacío")
                with get_connection() as connection:
                    connection.execute(f"UPDATE {table} SET nombre = ? WHERE id = ?", (new_name.strip(), selected))
                st.rerun()
            except Exception as error:
                st.error(f"No se guardó el nombre: {error}")
        confirm = st.checkbox("Confirmo que deseo eliminar este valor", key=f"confirmar_lista_{table}_{selected}")
        if st.button("Eliminar valor", disabled=not confirm):
            try:
                with get_connection() as connection:
                    connection.execute(f"DELETE FROM {table} WHERE id = ?", (selected,))
                st.rerun()
            except Exception:
                st.error("No se puede eliminar un valor utilizado por repuestos o categorías.")
