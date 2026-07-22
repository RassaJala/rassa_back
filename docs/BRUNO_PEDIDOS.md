# Prueba de Historial de Pedidos con Bruno

## Requisitos previos

- El backend debe estar corriendo en `http://localhost:8000`
- PostgreSQL debe estar activo
- Debe existir al menos un pedido con cambios de estado registrados

## Datos de prueba

El seed incluye 23 registros de historial para los pedidos de prueba.
Los pedidos van del ID 1 al 12.

## Pasos para probar

1. Abre la colecciÃ³n de Bruno en la carpeta `bruno/`.
2. Selecciona el entorno **local** en Bruno (esquina superior derecha).
3. Ejecuta la solicitud **Login** (`auth/login.bru`) para obtener el token.
4. Copia el `accessToken` del response y pÃ©galo en la variable `accessToken` del entorno local.
5. Ve a la carpeta `pedidos/` y ejecuta la solicitud **Pedido - Historial de estados**.
6. Cambia el valor de `pedidoId` en `vars:pre-request` para probar con otros pedidos.

## Endpoint disponible

### Historial de estados de un pedido

```
GET /api/pedidos/{id}/historial/
```

Retorna todos los cambios de estado registrados para un pedido especÃ­fico, ordenados cronolÃ³gicamente.

**ParÃ¡metros:**

| ParÃ¡metro | Tipo   | Requerido | DescripciÃ³n               |
| --------- | ------ | --------- | ------------------------- |
| `id`      | int    | SÃ­        | ID del pedido (en la URL) |

**Respuesta exitosa (200):**

```json
{
  "data": [
    {
      "id_historial": 1,
      "fk_pedido": 1,
      "fk_estado_anterior": null,
      "estado_anterior_nombre": null,
      "fk_estado_nuevo": 1,
      "estado_nuevo_nombre": "Pendiente",
      "fk_cambiado_por": null,
      "cambiado_por_nombre": null,
      "creado_en": "2026-06-01T09:30:00-03:00"
    },
    {
      "id_historial": 2,
      "fk_pedido": 1,
      "fk_estado_anterior": 1,
      "estado_anterior_nombre": "Pendiente",
      "fk_estado_nuevo": 2,
      "estado_nuevo_nombre": "Confirmado",
      "fk_cambiado_por": 3,
      "cambiado_por_nombre": "Carlos Vendedor",
      "creado_en": "2026-06-01T10:00:00-03:00"
    }
  ]
}
```

**Errores posibles:**

| CÃ³digo | DescripciÃ³n               |
| ------ | ------------------------- |
| 401    | Token no vÃ¡lido o expirado |
| 404    | Pedido no encontrado       |

## Variables del entorno local

| Variable    | DescripciÃ³n                  | Ejemplo              |
| ----------- | ---------------------------- | -------------------- |
| `baseUrl`   | URL base del backend         | `http://localhost:8000` |
| `accessToken` | JWT token del login        | `eyJ0eXAiOiJKV1...` |
| `pedidoId`  | ID del pedido a consultar    | `1`                  |

## Flujo recomendado de prueba

1. **Login** â†’ copiar `accessToken`
2. **Historial pedido 1** â†’ verificar que retorna los registros del seed
3. **Cambiar `pedidoId` a 5** â†’ probar con otro pedido
4. **Cambiar `pedidoId` a 999** â†’ debe retornar 404
5. **Probar sin token** â†’ debe retornar 401

## Notas importantes

- El endpoint es de **solo lectura** (GET).
- Requiere autenticaciÃ³n JWT.
- El historial se genera automÃ¡ticamente cuando cambia el estado de un pedido (via signal).
- El campo `cambiado_por_nombre` puede ser `null` si el cambio fue registrado sin usuario asociado (ej: seed data).
