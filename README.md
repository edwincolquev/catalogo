# Catalogo inteligente de repuestos

Primera fase: modelo relacional para Supabase/PostgreSQL y aplicación local SQLite/Streamlit.

## Incluido

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

La primera versión incluye SQLite, carga de CSV/Excel a staging, validación de filas, confirmación de registros válidos, gestión básica de repuestos y generación de descripción larga.

1. Crear un entorno virtual: `python -m venv .venv`
2. Activarlo en PowerShell: `.venv\\Scripts\\Activate.ps1`
3. Instalar dependencias: `pip install -r requirements.txt`
4. Ejecutar: `streamlit run app.py`

Los archivos de datos se guardan en `data/catalogo.sqlite3`. Para comenzar, use la plantilla [plantilla_importacion.csv](plantilla_importacion.csv) y complete una fila por repuesto. Las columnas reconocidas incluyen `Codigo SAP`, `Descripcion`, `Medida`, `OEM`, `Referencia`, `Codigo proveedor` y `Marca`. `Codigo SAP` y `Descripcion` son obligatorios; varios valores de `OEM` o `Referencia` pueden separarse con coma, punto y coma o `|`.

## Siguiente fase

- Ajustar la politica RLS a roles de negocio en lugar de permisos amplios para todo usuario autenticado.
- Definir el formato real de los Excel y crear `import_batches` y tablas de staging.
- Crear funciones RPC o una API para Power Apps.
- Agregar datos maestros y pruebas automatizadas de importacion y descripcion larga.
