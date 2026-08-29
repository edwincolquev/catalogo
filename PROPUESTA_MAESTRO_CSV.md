# Propuesta de maestro CSV

## 1. Llave del repuesto

La llave funcional sera `supplier_code` (codigo del proveedor). Debe ser obligatorio, unico y no depender de que exista todavia un codigo SAP.

`Sap_code` sera opcional y podra completarse o actualizarse en una carga posterior. No debe ser la llave principal del repuesto.

La plantilla operativa es [maestro_catalogo.csv](maestro_catalogo.csv).

## 2. Una fila por repuesto

El archivo maestro usa una fila por `supplier_code` y estas columnas:

| Columna | Obligatoria | Destino | Regla |
| --- | --- | --- | --- |
| `supplier_code` | Si | `parts.supplier_code` | Identificador unico del repuesto. |
| `sap_code` | No | `parts.sap_code` | Puede quedar vacio y completarse despues. |
| `description` | No | `parts.description` | Se puede completar en otra carga, pero la aplicacion debe permitirlo. |
| `measure` | No | `parts.measure` | Texto libre normalizado. |
| `brand_name` | No | `parts.brand_name` | Marca comercial del repuesto. |
| `oem_codes` | No | `part_oem_codes` | Varios codigos separados por `|`. |
| `reference_codes` | No | `part_cross_references` | Varios codigos separados por `|`. |
| `applications` | No | Tablas de vehiculos y aplicaciones | Una o varias aplicaciones codificadas segun la regla siguiente. |

El CSV usa `;` como separador porque es el formato que normalmente genera Excel en configuracion regional espanola.

## 3. Aplicaciones en una sola celda

Cada aplicacion se representa con seis valores separados por `|` y varias aplicaciones se separan con `||`:

`marca | modelo | motor | cilindrada | anio_desde | anio_hasta`

Ejemplo de valor para `applications`:

`TOYOTA|HILUX|2GD-FTV|2.4|2016|2020||TOYOTA|FORTUNER|1GD-FTV|2.8|2017|2020`

Reglas:

- La posicion de cada valor es fija.
- `marca` y `modelo` son obligatorios cuando existe una aplicacion.
- `motor`, `cilindrada`, `anio_desde` y `anio_hasta` pueden quedar vacios.
- La cilindrada debe ser numerica y mayor que cero.
- Los anios deben estar entre 1886 y 2200.
- `anio_desde` no puede ser mayor que `anio_hasta`.
- No usar `|` ni `||` dentro de los nombres o codigos.
- Si las aplicaciones llegan a ser muy complejas, conviene pasar a un segundo archivo normalizado de aplicaciones; no se debe forzar toda la complejidad dentro de una celda.

## 4. Flujo propuesto de carga

1. Leer el CSV y detectar el separador.
2. Validar que exista `supplier_code` y que no este vacio.
3. Agrupar filas por `supplier_code`. Se aceptan varias filas del mismo repuesto para facilitar cargas provenientes de distintas fuentes.
4. Consolidar los campos multivalor mediante union sin duplicados.
5. Si las filas repetidas traen valores diferentes para `sap_code`, `description`, `measure` o `brand_name`, marcar el grupo como conflicto y no confirmarlo automaticamente.
6. Buscar el repuesto por `supplier_code`, ignorando mayusculas y espacios externos.
7. Crear el repuesto si no existe; actualizar solo los campos informados si ya existe.
8. Mantener `sap_code` opcional. Si llega vacio, no borrar un SAP existente.
9. Crear marcas de vehiculo, modelos y motores una sola vez usando sus claves naturales.
10. Crear OEM y referencias una sola vez por repuesto; los repetidos se ignoran.
11. Crear la aplicacion usando la combinacion completa de repuesto, marca, modelo, motor, cilindrada y rango de anios; los repetidos se ignoran.
12. Registrar toda la operacion en staging para revisar filas validas, advertencias y errores antes de confirmar.
13. Regenerar `long_description` despues de confirmar cada repuesto afectado.

## 5. Cambios necesarios antes de implementar

El esquema actual no soporta directamente esta regla porque:

- `parts.sap_code` es `NOT NULL` y tiene un indice unico.
- `parts.supplier_code` permite nulos y no tiene indice unico.
- La pantalla de alta exige SAP.
- El importador actual inserta solamente `parts`, OEM y referencias; no carga marcas, modelos, motores ni aplicaciones.
- La prueba existente debe importar `read_source` antes de usarlo.

La implementacion deberia incluir, en una migracion controlada:

- Hacer `supplier_code` obligatorio para nuevos repuestos.
- Crear una unicidad sobre `upper(trim(supplier_code))`.
- Permitir `sap_code` nulo y conservar unicidad solo cuando tenga valor.
- Cambiar el alta manual para exigir `supplier_code`, no SAP.
- Agregar el parser de `oem_codes`, `reference_codes` y `applications`.
- Usar actualizacion parcial: celdas vacias no deben borrar informacion existente.
- Agregar un reporte de conflictos para filas con el mismo `supplier_code` y valores contradictorios.

## 6. Criterios de aprobacion

Antes de programar, confirmar:

- Que `supplier_code` identifica univocamente al repuesto en todo el negocio.
- Que una fila del maestro representa un unico repuesto.
- Que `|` y `||` quedan reservados para separar datos multivalor.
- Que una celda vacia significa "no actualizar", no borrar.
- Que el SAP puede quedar vacio.
- Que las aplicaciones se cargaran con el formato de seis posiciones.
- Que los registros actuales seran revisados antes de cambiar las restricciones de la base.
