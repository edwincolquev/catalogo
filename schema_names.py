"""Correspondencia del esquema anterior y los nombres en español."""

TABLE_RENAMES = {
    "parts": "repuestos",
    "part_oem_codes": "codigos_oem",
    "part_cross_references": "referencias_cruzadas",
    "vehicle_brands": "marcas_vehiculos",
    "vehicle_models": "modelos_vehiculos",
    "engine_types": "tipos_motor",
    "part_applications": "aplicaciones_repuestos",
    "import_batches": "lotes_importacion",
    "import_staging_rows": "filas_importacion",
}

COLUMN_RENAMES = {
    "sap_code": "codigo_sap",
    "supplier_code": "codigo_proveedor",
    "description": "descripcion",
    "measure": "medida",
    "brand_name": "nombre_marca",
    "long_description": "descripcion_larga",
    "is_active": "activo",
    "created_at": "fecha_creacion",
    "updated_at": "fecha_actualizacion",
    "part_id": "repuesto_id",
    "oem_code": "codigo_oem",
    "reference_type": "tipo_referencia",
    "reference_code": "codigo_referencia",
    "name": "nombre",
    "brand_id": "marca_id",
    "code": "codigo",
    "model_id": "modelo_id",
    "engine_type_id": "tipo_motor_id",
    "displacement": "cilindrada",
    "year_from": "anio_desde",
    "year_to": "anio_hasta",
    "application_text": "texto_aplicacion",
    "file_name": "nombre_archivo",
    "sheet_name": "nombre_hoja",
    "status": "estado",
    "total_rows": "total_filas",
    "valid_rows": "filas_validas",
    "error_rows": "filas_error",
    "processed_at": "fecha_procesamiento",
    "batch_id": "lote_id",
    "row_number": "numero_fila",
    "raw_data": "datos_originales",
    "normalized_data": "datos_normalizados",
    "errors": "errores",
}

IMPORT_KEY_RENAMES = {
    **COLUMN_RENAMES,
    "vehicle_brand": "marca_vehiculo",
    "vehicle_model": "modelo_vehiculo",
    "engine_code": "codigo_motor",
    "engine_description": "descripcion_motor",
    "model_name": "nombre_modelo",
}


def normalize_import_data(data: dict) -> dict:
    """Permite confirmar y revisar cargas preparadas antes de la traducción.

    El JSON histórico se conserva tal como fue guardado; solo se adaptan sus
    claves al leerlo. Los valores y los encabezados originales no se modifican.
    """
    return {IMPORT_KEY_RENAMES.get(key, key): value for key, value in data.items()}
