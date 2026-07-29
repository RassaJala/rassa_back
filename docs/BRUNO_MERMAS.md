# Prueba de Mermas con Bruno

## Requisitos previos

- El backend debe estar corriendo en `http://localhost:8000`
- PostgreSQL debe estar activo
- Deben existir productos semanales y decisiones de merma registradas

## Pasos para probar

1. Abre la colección de Bruno en la carpeta `bruno/`.
2. Ejecuta primero la solicitud de login para obtener un token.
3. Copia el `accessToken` en la variable correspondiente del entorno.
4. Prueba las solicitudes de mermas.

## Endpoints disponibles

### Listar mermas

```
GET /api/mermas/
```

Retorna mermas paginadas con información del producto y decisión.
Filtro opcional: `?incluir_inactivos=true`

### Registrar merma

```
POST /api/mermas/
```

Body:

```json
{
  "fk_producto_semanal": 1,
  "cantidad": 5,
  "motivo": "Producto dañado durante transporte",
  "comentarios": "Se detectó al llegar al almacén",
  "fk_decision": 1
}
```

### Detalle de merma

```
GET /api/mermas/{id}/
```

### Resumen de mermas (nuevo)

```
GET /api/mermas/resumen/
```

Retorna datos agregados de mermas agrupados por período, producto y decisión.
Solo accesible por Administradores.

**Query params opcionales:**

| Parámetro | Tipo | Descripción | Ejemplo |
|-----------|------|-------------|---------|
| `fecha_desde` | string (YYYY-MM-DD) | Fecha inicio del filtro | `2026-07-01` |
| `fecha_hasta` | string (YYYY-MM-DD) | Fecha fin del filtro | `2026-07-31` |
| `producto_id` | int | ID del producto a filtrar | `1` |
| `agrupar_por` | string (`mes` o `semana`) | Período de agrupación | `semana` |

**Respuesta:**

```json
{
  "ok": true,
  "data": {
    "agrupacion": "mes",
    "total_general": 23,
    "producto_mas_afectado": {
      "nombre": "Manzana",
      "total": 15
    },
    "detalle": [
      {
        "periodo": "2026-07-01T00:00:00-03:00",
        "producto_nombre": "Manzana",
        "producto_id": 1,
        "decision_nombre": "Donar",
        "decision_id": 1,
        "total_cantidad": 10,
        "total_mermas": 1
      }
    ]
  }
}
```

**Ejemplos de uso:**

```
# Resumen por mes (default)
GET /api/mermas/resumen/

# Resumen por semana
GET /api/mermas/resumen/?agrupar_por=semana

# Filtrar por rango de fechas
GET /api/mermas/resumen/?fecha_desde=2026-07-01&fecha_hasta=2026-07-31

# Filtrar por producto
GET /api/mermas/resumen/?producto_id=1

# Combinar filtros
GET /api/mermas/resumen/?fecha_desde=2026-07-01&fecha_hasta=2026-07-31&agrupar_por=semana&producto_id=1
```

### Gestionar decisiones de merma

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/decisiones-merma/` | GET | Listar decisiones |
| `/api/decisiones-merma/` | POST | Crear decisión |
| `/api/decisiones-merma/{id}/` | GET | Detalle |
| `/api/decisiones-merma/{id}/` | PATCH | Editar |
| `/api/decisiones-merma/{id}/` | DELETE | Desactivar (soft-delete) |

## Variables útiles

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `baseUrl` | URL base del backend | `http://localhost:8000` |
| `accessToken` | JWT token del login | `eyJ0e...` |
| `mermaId` | ID de la merma a consultar | `1` |

## Flujo recomendado de prueba

1. **Login** → copiar `accessToken`
2. **Listar decisiones** → verificar que existen decisiones
3. **Listar mermas** → verificar que retorna mermas
4. **Detalle de merma** → ver una merma específica
5. **Resumen sin filtros** → verificar agregación por mes
6. **Resumen con filtros** → probar filtros de fecha y producto
7. **Resumen por semana** → verificar agrupación semanal
8. **Registrar merma** → crear una nueva merma y verificar que descuenta stock
