# API de Categorías y Unidades

## Endpoints

### Categorías
- `GET /api/categorias/`
- `POST /api/categorias/`
- `GET /api/categorias/{pk}/`
- `PATCH /api/categorias/{pk}/`
- `PUT /api/categorias/{pk}/`
- `DELETE /api/categorias/{pk}/`

### Unidades
- `GET /api/unidades/`
- `POST /api/unidades/`
- `GET /api/unidades/{pk}/`
- `PATCH /api/unidades/{pk}/`
- `PUT /api/unidades/{pk}/`
- `DELETE /api/unidades/{pk}/`

---

## Modelo `Unidad`

Campos disponibles:
- `id_unidad` (AutoField, solo lectura)
- `tipo` (nombre de la unidad)
- `abreviatura` (ej: `kg`, `pz`, `mnj`, `lt`)
- `creado_en` (solo lectura)
- `estado` (booleano)

La semilla de datos carga estas unidades:
- `Kilogramo` / `kg`
- `Pieza` / `pz`
- `Manojo` / `mnj`
- `Litro` / `lt`
- `Docena` / `dz`

---

## Campos expuestos

### Categorías
- `id_categoria`
- `nombre`
- `descripcion`
- `creado_en`
- `estado`

### Unidades
- `id_unidad`
- `tipo`
- `abreviatura`
- `creado_en`
- `estado`

---

## Comportamiento CRUD

### Listar

`GET /api/categorias/`
`GET /api/unidades/`

La respuesta es paginada y tiene esta forma:

```json
{
  "count": 6,
  "next": null,
  "previous": null,
  "results": [
    {
      "id_categoria": 1,
      "nombre": "Verduras",
      "descripcion": "Verduras frescas del campo",
      "creado_en": "2026-07-07T00:03:16.203887-03:00",
      "estado": true
    }
  ]
}
```

### Crear

#### Categoría
`POST /api/categorias/`

Ejemplo:

```json
{
  "nombre": "Semillas",
  "descripcion": "Semillas y plantines",
  "estado": true
}
```

#### Unidad
`POST /api/unidades/`

Ejemplo:

```json
{
  "tipo": "Caja",
  "abreviatura": "cja",
  "estado": true
}
```

### Obtener uno

`GET /api/categorias/{pk}/`
`GET /api/unidades/{pk}/`

Devuelve el objeto completo con `creado_en` y `estado`.

### Actualizar

`PATCH /api/categorias/{pk}/`
`PATCH /api/unidades/{pk}/`

Ejemplo parcial:

```json
{
  "descripcion": "Nueva descripción"
}
```

También se admite `PUT` completo.

### Eliminar / desactivar

`DELETE /api/categorias/{pk}/`
`DELETE /api/unidades/{pk}/`

En lugar de eliminar físicamente el registro, el backend marca `estado=false`.

---

## Filtros de estado

- `GET /api/categorias/?estado=true`
- `GET /api/unidades/?estado=true`
- `GET /api/categorias/?estado=false`
- `GET /api/unidades/?estado=false`
- `GET /api/categorias/?estado=all`
- `GET /api/unidades/?estado=all`

---

## Notas

- La API usa `DefaultRouter` de DRF.
- `id_categoria`, `id_unidad` y `creado_en` son solo lectura.
- `DELETE` se comporta como desactivación lógica.
- La validación de DRF revisa que los campos requeridos estén presentes.
