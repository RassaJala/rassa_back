# Prueba de Pedidos con Bruno

## Requisitos previos

- El backend debe estar corriendo en `http://localhost:8000`
- PostgreSQL debe estar activo
- Debe existir al menos un pedido con cambios de estado registrados

## Pasos para probar

1. Abre la colección de Bruno en la carpeta `bruno/`.
2. Ejecuta primero la solicitud de login para obtener un token.
3. Copia el `accessToken` en la variable correspondiente del entorno.
4. Prueba las solicitudes de pedidos.

## Endpoints disponibles

### Listar pedidos

```
GET /api/pedidos/
```

Retorna pedidos del vendedor autenticado. Admin ve todos.
Filtro opcional: `?estado=pendiente`

### Detalle de pedido

```
GET /api/pedidos/{id}/
```

Retorna el pedido con detalles e historial embebido.

### Cambiar estado

```
PATCH /api/pedidos/{id}/status/
```

Body:

```json
{
  "nuevo_estado": "confirmado"
}
```

Estados válidos: `confirmado`, `en_preparacion`, `listo_para_retirar`, `entregado`, `cancelado`

Secuencia: pendiente → confirmado → en_preparacion → listo_para_retirar → entregado

Cancelación permitida desde: pendiente, confirmado, en_preparacion, listo_para_retirar.

### Historial de estados (endpoint dedicado)

```
GET /api/pedidos/{id}/historial/
```

Retorna solo el historial de cambios de estado del pedido. Útil para componentes de línea de tiempo en el frontend.

**Respuesta:**

```json
{
  "data": [
    {
      "id_historial": 1,
      "estado_anterior": null,
      "estado_nuevo": "pendiente",
      "cambiado_por_nombre": "Juan Perez",
      "creado_en": "2026-06-01T09:30:00-03:00"
    },
    {
      "id_historial": 2,
      "estado_anterior": "pendiente",
      "estado_nuevo": "confirmado",
      "cambiado_por_nombre": "Vendedor Universidad",
      "creado_en": "2026-06-01T10:00:00-03:00"
    }
  ]
}
```

## Variables útiles

| Variable    | Descripción               | Ejemplo   |
| ----------- | ------------------------- | --------- |
| `baseUrl`   | URL base del backend      | `http://localhost:8000` |
| `accessToken` | JWT token del login     | `eyJ0e...` |
| `pedidoId`  | ID del pedido a consultar | `1`       |

## Flujo recomendado de prueba

1. **Login** → copiar `accessToken`
2. **Listar pedidos** → verificar que retorna pedidos
3. **Detalle** → ver un pedido específico
4. **Cambiar estado** → avanzar el pedido en la secuencia
5. **Historial** → verificar que los cambios se registraron
6. **Historial de pedido inexistente** → debe retornar 404
