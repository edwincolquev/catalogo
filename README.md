# Catalogo inteligente de repuestos

Aplicación local SQLite/Streamlit para administrar repuestos, importar maestros y generar descripciones. Las tablas y sus campos usan nombres en español. Incluye clasificación por unidad, marca comercial y categoría, y seguimiento desde Propuesto hasta En SAP, con precios en USD.

El esquema se consulta en [DIAGRAMA_ER.md](DIAGRAMA_ER.md) y la correspondencia de nombres anteriores y actuales en [DICCIONARIO_DATOS.md](DICCIONARIO_DATOS.md). Por ejemplo, `parts.supplier_code` pasó a `repuestos.codigo_proveedor` y `part_oem_codes.oem_code` a `codigos_oem.codigo_oem`.

Las etapas, campos de compra y venta y encabezados del maestro se describen en [GESTION_COMERCIAL.md](GESTION_COMERCIAL.md). En Streamlit, la pestaña Clasificación administra las listas y la pestaña Importar permite descargar la plantilla ampliada.

## Referencia histórica de Supabase/PostgreSQL

La migración remota inicial conserva sus nombres en inglés. Las instrucciones y el ejemplo SQL de esta sección corresponden a esa versión; la aplicación local utiliza `schema.sql` y `schema_gestion.sql`.

- Tablas para repuestos, OEM, equivalencias, marcas, modelos, motores y aplicaciones.
- Restricciones de unicidad para SAP, OEM, equivalencias y aplicaciones.
- Indices trigram para busquedas por SAP, codigo OEM y descripcion.
- Funcion `public.generate_long_description(part_id)`.
- Regeneracion automatica de `long_description` al cambiar el repuesto o sus relaciones.
- RLS habilitado para que usuarios autenticados consulten y administren el catalogo.

## Ejecucion en Supabase

1. Crear o seleccionar un proyecto Supabase.
2. Confirmar el `project_ref` del proyecto y el entorno objetivo.
3. Ejecutar `supabase/migrations/20260820000000_initial_catalog.sql` desde el SQL Editor, Supabase CLI o el MCP de Supabase conectado al proyecto.
4. Ejecutar una prueba con un repuesto, una marca, un modelo, un OEM y una aplicacion.
5. Verificar que `parts.long_description` se actualiza automaticamente.

No se incluyen credenciales, claves ni un `project_ref` porque aun no estan disponibles en este workspace. El MCP tampoco aparece configurado entre las herramientas disponibles en esta sesion; por eso la migracion queda preparada para ejecutarse cuando se habilite el conector.

## Prueba de humo

```sql
insert into public.parts (sap_code, description, measure)
values ('CPL-7277', 'MANGUERA DE REFRIGERACION', '12X12X220')
returning id, long_description;

select public.generate_long_description(id)
from public.parts
where sap_code = 'CPL-7277';
```

## Aplicación local

La versión local usa SQLite y Streamlit para importar, revisar y administrar el catálogo.

1. Crear un entorno virtual: `python -m venv .venv`
2. Activarlo en PowerShell: `.venv\\Scripts\\Activate.ps1`
3. Instalar dependencias: `pip install -r requirements.txt`
4. Ejecutar: `streamlit run app.py`

Los archivos de datos se guardan en `data/catalogo.sqlite3`. También se acepta la plantilla sencilla [plantilla_importacion.csv](plantilla_importacion.csv), con una fila por repuesto. Varios OEM o referencias pueden separarse con coma, punto y coma o `|`.

## Maestro con dos encabezados

La aplicación reconoce [maestro_catalogo v2.csv](maestro_catalogo%20v2.csv): la primera fila agrupa tablas y la segunda contiene los nombres de campos. Las filas repetidas de `repuestos.codigo_proveedor` (o el encabezado anterior `parts.supplier_code`) consolidan un mismo repuesto. El código de proveedor es único en el catálogo; SAP y descripción pueden completarse después. Una celda vacía conserva el valor existente y una celda no vacía lo reemplaza. El CSV no necesita los identificadores de las relaciones: el importador los obtiene desde el código de proveedor. Los OEM y las referencias nuevos se agregan al mismo repuesto; los códigos ya existentes no se duplican. Para eliminar o corregir un OEM o referencia existente se usa la edición en Streamlit.

Los maestros existentes en inglés siguen siendo compatibles. Para nuevos maestros en español, use `REPUESTOS` en la primera fila y encabezados como `repuestos.codigo_proveedor`, `codigos_oem.codigo_oem`, `referencias_cruzadas.tipo_referencia` y `referencias_cruzadas.codigo_referencia` en la segunda. El diccionario incluye los demás campos.

Las aplicaciones incompletas o con texto compuesto en el campo motor aparecen como avisos y se omiten; los datos válidos del repuesto sí se cargan. La pantalla de Streamlit permite crear, editar y eliminar repuestos, OEM, referencias y aplicaciones, y muestra la descripción generada y la revisión previa de cada carga. Consulte [ANALISIS_MAESTRO.md](ANALISIS_MAESTRO.md) para el mapeo y los casos del archivo de ejemplo.

Al abrir una base en inglés, se crea `data/catalogo.pre_traduccion_es.sqlite3` antes de traducir tablas y campos. Se conservan valores, identificadores, relaciones e historial; también pueden confirmarse cargas preparadas con la versión anterior. Si el respaldo ya existe, se crea otro con un sufijo. Reabrir la base traducida no repite la migración. Para trabajar con otra base, defina `CATALOGO_DB_PATH` antes de iniciar Streamlit.

Las migraciones previas de SAP opcional y texto de aplicación conservan sus respaldos `catalogo.pre_supplier_migration.sqlite3` y `catalogo.pre_application_text_migration.sqlite3` cuando corresponden.

La migración comercial crea `catalogo.pre_gestion_comercial.sqlite3`. Convierte la marca de texto libre en una relación con `marcas_repuestos` e inicializa el estado de los registros con código SAP en En SAP y los demás en Propuesto. Los nuevos importes y cantidades quedan vacíos.

Estas reglas están implementadas en SQLite. La migración Supabase/PostgreSQL incluida en el repositorio todavía corresponde al modelo inicial y deberá alinearse antes de sincronizar ambos entornos.

## Formato de aplicaciones y descripciones

El resumen de aplicaciones sigue la función VBA `ObtenerDescripcion`: recorre las aplicaciones en el orden de carga, elimina duplicados completos y omite marca, modelo y cilindrada cuando coinciden con la aplicación anterior. Motor y periodo se muestran en cada aplicación; los años usan dos dígitos (`DEL 88 AL 00`, `DESDE 01`, `HASTA 05`). Todos los textos se convierten a mayúsculas y las aplicaciones se separan con `; `.

El campo opcional `aplicaciones_repuestos.texto_aplicacion` conserva el texto libre de la columna H (`Aplicación`) del VBA. Puede editarse en Streamlit o importarse con ese encabezado; el anterior `applications.application_text` también se acepta.

## Siguiente fase

- Ajustar la politica RLS a roles de negocio en lugar de permisos amplios para todo usuario autenticado.
- Revisar y corregir las aplicaciones ambiguas del maestro antes de completarlas en la base.
- Crear funciones RPC o una API para Power Apps.
- Agregar datos maestros y pruebas automatizadas de importacion y descripcion larga.
