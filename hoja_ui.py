"""Hoja editable con selección y repetición de celdas en Streamlit."""

from copy import deepcopy

import pandas as pd
import streamlit as st

from database import fetch_all
from gestion import ESTADOS, NUMERICOS
from hoja_trabajo import (
    CAMPOS_EDITABLES, aplicar_edicion, cambios_hoja, filas_para_editor,
    guardar_cambios_hoja, valor_celda,
)

STATE_KEY = "hoja_trabajo"
LABELS = {
    "codigo_proveedor": "Código proveedor", "codigo_sap": "Código SAP", "descripcion": "Descripción",
    "medida": "Medida", "nombre_marca": "Marca comercial", "unidad": "Unidad", "categoria": "Categoría",
    "estado_gestion": "Estado", "minimo_compra": "Mínimo compra", "precio_compra": "Compra (USD)",
    "precio_venta": "Venta (USD)", "cantidad_compra": "Cantidad compra", "activo": "Activo",
}


def hay_cambios_hoja():
    state = st.session_state.get(STATE_KEY)
    return bool(state and cambios_hoja(state["originales"], state["borrador"]))


def _renovar_editor(state):
    version = st.session_state.get("hoja_version", 0) + 1
    st.session_state["hoja_version"] = version
    state["editor_key"] = f"hoja_editor_{version}"
    state["entrada"] = deepcopy(state["borrador"])


def _seleccionar_todas():
    selected = st.session_state["hoja_seleccionar_todas"]
    state = st.session_state[STATE_KEY]
    for row in state["borrador"]:
        row["seleccionar"] = selected
    _renovar_editor(state)


def _al_editar(editor_key):
    state = st.session_state[STATE_KEY]
    if editor_key != state["editor_key"]:
        return
    proposal = deepcopy(state["entrada"])
    edits = st.session_state[editor_key]["edited_rows"]
    for position, changes in edits.items():
        if 0 <= int(position) < len(proposal):
            for field, value in changes.items():
                if field in (*CAMPOS_EDITABLES, "seleccionar"):
                    proposal[int(position)][field] = valor_celda(value)
    draft, notices = aplicar_edicion(state["borrador"], proposal, repetir=True)
    state["borrador"] = draft
    state["avisos"] = notices
    if draft != proposal:
        _renovar_editor(state)


def mostrar_hoja(rows, scope, total):
    rows = [dict(row) for row in rows]
    state = st.session_state.get(STATE_KEY)
    if state is None or (state["scope"] != scope and not hay_cambios_hoja()):
        state = dict(scope=scope, originales=rows, borrador=filas_para_editor(rows), avisos=[])
        st.session_state[STATE_KEY] = state
        _renovar_editor(state)
    elif not hay_cambios_hoja() and state["originales"] != rows:
        selected = {row["id"] for row in state["borrador"] if row["seleccionar"]}
        state["originales"] = rows
        state["borrador"] = filas_para_editor(rows, selected)
        _renovar_editor(state)
    flash = st.session_state.pop("hoja_mensaje", None)
    if flash:
        st.success(flash)
    st.subheader("Hoja de trabajo")
    st.caption(f"{len(state['borrador'])} de {total} repuestos mostrados con estos filtros.")
    if not state["borrador"]:
        st.info("No hay repuestos para los filtros elegidos.")
        return []
    selected_count = sum(bool(row["seleccionar"]) for row in state["borrador"])
    st.session_state["hoja_seleccionar_todas"] = selected_count == len(state["borrador"])
    select_column, _ = st.columns([1, 11], gap="small")
    select_column.checkbox(
        "Seleccionar todas las filas mostradas",
        key="hoja_seleccionar_todas",
        label_visibility="collapsed",
        help="Marcar o quitar la selección de todas las filas mostradas",
        on_change=_seleccionar_todas,
    )
    data = pd.DataFrame(state["entrada"])
    for field in NUMERICOS:
        data[field] = pd.to_numeric(data[field], errors="raise").astype(float)
    for field in CAMPOS_EDITABLES:
        if field not in (*NUMERICOS, "activo"):
            data[field] = data[field].astype("string")
    data["activo"] = data["activo"].astype(bool)
    data["seleccionar"] = data["seleccionar"].astype(bool)
    data.index = data["id"].tolist()
    config = {field: st.column_config.TextColumn(label) for field, label in LABELS.items()}
    config["codigo_proveedor"] = st.column_config.TextColumn("Código proveedor", required=True)
    config["seleccionar"] = st.column_config.CheckboxColumn(" ", default=False, pinned=True, width="small")
    config["id"] = st.column_config.NumberColumn("ID", disabled=True)
    config["activo"] = st.column_config.CheckboxColumn("Activo")
    config["estado_gestion"] = st.column_config.SelectboxColumn("Estado", options=list(ESTADOS.values()), required=True, width="medium")
    config["fecha_actualizacion"] = st.column_config.TextColumn("Actualizado", disabled=True)
    for field in NUMERICOS:
        config[field] = st.column_config.NumberColumn(LABELS[field], min_value=0.0001 if field == "minimo_compra" else 0.0, format="%.4f")
    for field, table in (("unidad", "unidades_medida"), ("nombre_marca", "marcas_repuestos"), ("categoria", "categorias_repuestos")):
        options = {row["nombre"] for row in fetch_all(f"SELECT nombre FROM {table}")}
        options.update(row[field] for row in state["borrador"] if row[field])
        config[field] = st.column_config.SelectboxColumn(LABELS[field], options=sorted(options), width="medium")
    disabled = ["id", "fecha_actualizacion", "_index"]
    if all(row["estado_gestion"] == "en_sap" for row in state["originales"]):
        disabled += ["estado_gestion", *NUMERICOS]
    st.data_editor(data, hide_index=True, width="stretch", height=min(580, 38 + 35 * len(data)),
                   num_rows="fixed", column_config=config, disabled=disabled, key=state["editor_key"],
                   on_change=_al_editar, args=(state["editor_key"],))
    st.caption(f"{selected_count} filas seleccionadas. Edite una celda de una fila marcada para copiar su valor a las demás marcadas. Los códigos proveedor y SAP se editan individualmente.")
    for notice in state["avisos"]:
        st.warning(notice)
    st.caption("Las categorías deben pertenecer a la marca de cada fila. Al cambiar la marca se limpia su categoría. Los artículos En SAP tienen cerrados sus precios, cantidades y estado.")
    changes = cambios_hoja(state["originales"], state["borrador"])
    st.caption(f"{len(changes)} repuestos con cambios pendientes. Guarde o descarte para volver a cambiar los filtros.")
    if changes:
        originals = {row["id"]: row for row in state["originales"]}
        with st.expander("Revisar cambios pendientes"):
            review = []
            for part_id, fields in changes.items():
                for field, value in fields.items():
                    previous = originals[part_id][field]
                    if field == "estado_gestion":
                        previous = ESTADOS[previous]
                    review.append(dict(codigo_proveedor=originals[part_id]["codigo_proveedor"], campo=LABELS[field],
                                       anterior="" if previous is None else str(previous), nuevo="" if value is None else str(value)))
            st.dataframe(review, hide_index=True, width="stretch")
    save, discard = st.columns(2)
    if save.button("Guardar cambios de la hoja", type="primary", disabled=not changes):
        try:
            count = guardar_cambios_hoja(state["originales"], changes)
            st.session_state.pop(STATE_KEY)
            st.session_state["hoja_mensaje"] = f"Hoja guardada: {count} repuestos actualizados."
            st.rerun()
        except Exception as error:
            st.error(f"No se guardó ninguna fila: {error}")
    if discard.button("Descartar cambios de la hoja", disabled=not changes):
        st.session_state.pop(STATE_KEY)
        st.rerun()
    return [row["id"] for row in state["borrador"] if row["seleccionar"]]
