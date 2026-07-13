# Prueba de CRUD de categorías y unidades con Bruno

## Requisitos previos

- El backend debe estar corriendo en http://localhost:8000
- PostgreSQL debe estar activo
- Debe existir un usuario con credenciales válidas para obtener el token JWT

## Pasos para probar

1. Abre la colección de Bruno en la carpeta bruno.
2. Ejecuta primero la solicitud de login para obtener un token.
3. Copia el accessToken en la variable correspondiente del entorno local.
4. Prueba las solicitudes de categorías y unidades.

## Endpoints disponibles

### Categorías
- GET /api/categorias/
- POST /api/categorias/
- GET /api/categorias/{id}/
- PATCH /api/categorias/{id}/
- DELETE /api/categorias/{id}/

### Unidades
- GET /api/unidades/
- POST /api/unidades/
- GET /api/unidades/{id}/
- PATCH /api/unidades/{id}/
- DELETE /api/unidades/{id}/

## Variables útiles

En el entorno local puedes usar:
- baseUrl: http://localhost:8000
- accessToken: token JWT obtenido del login
- categoriaId: id de una categoría creada
- unidadId: id de una unidad creada

## Ejemplo de payload para crear una unidad

```json
{
  "nombre": "Kilogramo",
  "abreviatura": "kg",
  "estado": true
}
```

## Ejemplo de payload para crear una categoría

```json
{
  "nombre": "Frutas",
  "descripcion": "Productos frutales",
  "estado": true
}
```
