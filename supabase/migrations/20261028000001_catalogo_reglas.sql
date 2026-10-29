-- Reglas de gestión equivalentes a los triggers de schema_gestion.sql.
-- Se aplican después de la carga inicial para preservar el historial original.

create function public.validar_categoria_repuesto()
returns trigger language plpgsql set search_path = '' as $$
begin
    if new.categoria_id is not null and not exists (
        select 1 from public.categorias_repuestos c
        where c.id = new.categoria_id and c.marca_id = new.marca_id
    ) then
        raise exception 'La categoria debe pertenecer a la marca del repuesto';
    end if;
    return new;
end;
$$;

create trigger repuestos_categoria_insertar
before insert or update of marca_id, categoria_id on public.repuestos
for each row execute function public.validar_categoria_repuesto();

create function public.validar_marca_categoria()
returns trigger language plpgsql set search_path = '' as $$
begin
    if new.marca_id is distinct from old.marca_id and exists (
        select 1 from public.repuestos r where r.categoria_id = old.id
    ) then
        raise exception 'No puede cambiarse la marca de una categoria en uso';
    end if;
    return new;
end;
$$;

create trigger categorias_marca_actualizar
before update of marca_id on public.categorias_repuestos
for each row execute function public.validar_marca_categoria();

create function public.validar_estado_repuesto()
returns trigger language plpgsql set search_path = '' as $$
begin
    if tg_op = 'INSERT' then
        if new.estado_gestion not in ('propuesto', 'en_sap') then
            raise exception 'El estado inicial debe ser Propuesto o En SAP';
        end if;
    elsif new.estado_gestion is distinct from old.estado_gestion and not (
        (old.estado_gestion = 'propuesto' and new.estado_gestion in ('en_cotizacion', 'rechazado')) or
        (old.estado_gestion = 'en_cotizacion' and new.estado_gestion in ('pendiente_aprobacion', 'rechazado')) or
        (old.estado_gestion = 'pendiente_aprobacion' and new.estado_gestion in ('aprobado', 'rechazado')) or
        (old.estado_gestion = 'aprobado' and new.estado_gestion in ('pedido', 'rechazado')) or
        (old.estado_gestion = 'pedido' and new.estado_gestion in ('en_sap', 'rechazado'))
    ) then
        raise exception 'Transicion de estado no permitida';
    end if;
    return new;
end;
$$;

create trigger repuestos_estado_insertar
before insert on public.repuestos
for each row execute function public.validar_estado_repuesto();

create trigger repuestos_estado_actualizar
before update of estado_gestion on public.repuestos
for each row execute function public.validar_estado_repuesto();

create function public.validar_comercial_repuesto()
returns trigger language plpgsql set search_path = '' as $$
begin
    if old.estado_gestion = 'en_sap' and (
        new.minimo_compra is distinct from old.minimo_compra or
        new.precio_compra is distinct from old.precio_compra or
        new.precio_venta is distinct from old.precio_venta or
        new.cantidad_compra is distinct from old.cantidad_compra
    ) then
        raise exception 'El seguimiento comercial esta cerrado en SAP';
    end if;
    return new;
end;
$$;

create trigger repuestos_comercial_cerrado
before update of minimo_compra, precio_compra, precio_venta, cantidad_compra on public.repuestos
for each row execute function public.validar_comercial_repuesto();

create function public.registrar_historial_repuesto()
returns trigger language plpgsql set search_path = '' as $$
begin
    if tg_op = 'INSERT' then
        insert into public.historial_estados (repuesto_id, estado_nuevo)
        values (new.id, new.estado_gestion);
    elsif new.estado_gestion is distinct from old.estado_gestion then
        insert into public.historial_estados (repuesto_id, estado_anterior, estado_nuevo)
        values (new.id, old.estado_gestion, new.estado_gestion);
    end if;
    return new;
end;
$$;

create trigger repuestos_historial_inicial
after insert on public.repuestos
for each row execute function public.registrar_historial_repuesto();

create trigger repuestos_historial_cambio
after update of estado_gestion on public.repuestos
for each row execute function public.registrar_historial_repuesto();
