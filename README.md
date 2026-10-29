# Catalogo inteligente de repuestos

Aplicación Streamlit para administrar repuestos, importar maestros y generar descripciones con Supabase/PostgreSQL o SQLite local. Las tablas y sus campos usan nombres en español. Incluye clasificación por unidad, marca comercial y categoría, y seguimiento desde Propuesto hasta En SAP, con precios en USD.

El esquema se consulta en [DIAGRAMA_ER.md](DIAGRAMA_ER.md) y la correspondencia de nombres anteriores y actuales en [DICCIONARIO_DATOS.md](DICCIONARIO_DATOS.md). Por ejemplo, `parts.supplier_code` pasó a `repuestos.codigo_proveedor` y `part_oem_codes.oem_code` a `codigos_oem.codigo_oem`.

Las etapas, campos de compra y venta y encabezados del maestro se describen en [GESTION_COMERCIAL.md](GESTION_COMERCIAL.md). En Streamlit, la pestaña Clasificación administra las listas y la pestaña Importar permite descargar la plantilla ampliada.

## Supabase/PostgreSQL

El proyecto `catalogo-m7` (`wvsysymabduywfgekyfh`) contiene una copia del catálogo SQLite con las 13 tablas en español. Se aplicaron `supabase/migrations/20261028000000_catalogo_actual.sql` y `supabase/migrations/20261028000001_catalogo_reglas.sql`. El esquema histórico en inglés está archivado en `supabase/archive/` y no debe aplicarse al catálogo actual.

La carga procede del respaldo `data/catalogo.pre_supabase_20261028.sqlite3`. Para comprobar que los datos remotos siguen coincidiendo con él, ejecute `python supabase/import_sqlite.py --verify`. `--apply` solo carga cuando las 13 tablas de destino están vacías. El token temporal se lee de `.env`, excluido de Git; no se guarda en las migraciones.

Las tablas remotas tienen RLS activo y todavía no hay políticas para las claves públicas de la API. Streamlit utiliza PostgreSQL cuando `DATABASE_URL` está definida en el entorno o en `.env`; las pruebas con una ruta SQLite explícita siguen usando SQLite. La cadena debe provenir de **Connect > Session pooler** en Supabase, con la contraseña codificada para URL y SSL activo. Sin `DATABASE_URL`, la aplicación usa `data/catalogo.sqlite3`.

La aplicación reutiliza hasta cinco conexiones PostgreSQL por proceso. Las lecturas de `fetch_all` usan autocommit para evitar un viaje de red adicional; las escrituras conservan transacciones con commit o rollback. Reinicie Streamlit después de cambiar `DATABASE_URL`.

## Aplicación local

La versión local usa SQLite y Streamlit para importar, revisar y administrar el catálogo.

1. Crear un entorno virtual: `python -m venv .venv`
2. Activarlo en PowerShell: `.venv\\Scripts\\Activate.ps1`
3. Instalar dependencias: `pip install -r requirements.txt`
4. Ejecutar: `streamlit run app.py`

Los archivos de datos se guardan en `data/catalogo.sqlite3`. También se acepta la plantilla sencilla [plantilla_importacion.csv](plantilla_importacion.csv), con una fila por repuesto. Varios OEM o referencias pueden separarse con coma, punto y coma o `|`. En **Importar**, los filtros de marca y estado permiten descargar el maestro con los repuestos coincidentes y sus OEM, referencias y aplicaciones; también se puede descargar la plantilla vacía.

## Maestro con dos encabezados

La aplicación reconoce [maestro_catalogo v2.csv](maestro_catalogo%20v2.csv): la primera fila agrupa tablas y la segunda contiene los nombres de campos. Las filas repetidas de `repuestos.codigo_proveedor` (o el encabezado anterior `parts.supplier_code`) consolidan un mismo repuesto. También se admiten repuestos identificados solo por código SAP. El código de proveedor es único en el catálogo; SAP y descripción pueden completarse después. Una celda vacía conserva el valor existente y una celda no vacía lo reemplaza. El CSV no necesita los identificadores de las relaciones: el importador localiza el repuesto por su código de proveedor o SAP. Los OEM y las referencias nuevos se agregan al mismo repuesto; los códigos ya existentes no se duplican. Para eliminar o corregir un OEM o referencia existente se usa la edición en Streamlit.

Los maestros existentes en inglés siguen siendo compatibles. Para nuevos maestros en español, use `REPUESTOS` en la primera fila y encabezados como `repuestos.codigo_proveedor`, `codigos_oem.codigo_oem`, `referencias_cruzadas.tipo_referencia` y `referencias_cruzadas.codigo_referencia` en la segunda. El diccionario incluye los demás campos.

Las aplicaciones incompletas o con texto compuesto en el campo motor aparecen como avisos y se omiten; los datos válidos del repuesto sí se cargan. La pantalla de Streamlit permite crear, editar y eliminar repuestos, OEM, referencias y aplicaciones, y muestra la descripción generada y la revisión previa de cada carga. La administración de un repuesto se abre al marcar una sola fila en la hoja de trabajo; con varias filas marcadas queda disponible la edición repetida y se oculta la administración individual. Consulte [ANALISIS_MAESTRO.md](ANALISIS_MAESTRO.md) para el mapeo y los casos del archivo de ejemplo.

Al abrir una base en inglés, se crea `data/catalogo.pre_traduccion_es.sqlite3` antes de traducir tablas y campos. Se conservan valores, identificadores, relaciones e historial; también pueden confirmarse cargas preparadas con la versión anterior. Si el respaldo ya existe, se crea otro con un sufijo. Reabrir la base traducida no repite la migración. Para trabajar con otra base, defina `CATALOGO_DB_PATH` antes de iniciar Streamlit.

Las migraciones previas de SAP opcional y texto de aplicación conservan sus respaldos `catalogo.pre_supplier_migration.sqlite3` y `catalogo.pre_application_text_migration.sqlite3` cuando corresponden.

La migración comercial crea `catalogo.pre_gestion_comercial.sqlite3`. Convierte la marca de texto libre en una relación con `marcas_repuestos` e inicializa el estado de los registros con código SAP en En SAP y los demás en Propuesto. Los nuevos importes y cantidades quedan vacíos.

Las reglas de gesti?n est?n implementadas tanto en SQLite como en las migraciones actuales de Supabase/PostgreSQL.

## Formato de aplicaciones y descripciones

El resumen de aplicaciones sigue la función VBA `ObtenerDescripcion`: recorre las aplicaciones en el orden de carga, elimina duplicados completos y omite marca, modelo y cilindrada cuando coinciden con la aplicación anterior. Motor y periodo se muestran en cada aplicación; los años usan dos dígitos (`DEL 88 AL 00`, `DESDE 01`, `HASTA 05`). Todos los textos se convierten a mayúsculas y las aplicaciones se separan con `; `.

**Descripción generada** reúne descripción, medida y códigos OEM. Las aplicaciones se presentan por separado en **Aplicaciones en formato de catálogo**.

El campo opcional `aplicaciones_repuestos.texto_aplicacion` conserva el texto libre de la columna H (`Aplicación`) del VBA. Puede editarse en Streamlit o importarse con ese encabezado; el anterior `applications.application_text` también se acepta.

## Siguiente fase

- Ajustar la politica RLS a roles de negocio en lugar de permisos amplios para todo usuario autenticado.
- Revisar y corregir las aplicaciones ambiguas del maestro antes de completarlas en la base.
- Crear funciones RPC o una API para Power Apps.
- Agregar datos maestros y pruebas automatizadas de importacion y descripcion larga.
