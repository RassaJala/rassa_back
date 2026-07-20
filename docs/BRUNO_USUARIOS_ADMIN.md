# Prueba de GestiÃ³n de Usuarios (Admin) con Bruno

## Requisitos previos

- El backend debe estar corriendo en `http://localhost:8000`
- PostgreSQL debe estar activo
- Debe existir un usuario con rol **Administrador** (ver `USUARIOS_PRUEBA.md`)

## Credenciales de Admin

```json
{
  "email": "admin@rassa.com",
  "password": "admin123"
}
```

## Pasos para probar

1. Abre la colecciÃ³n de Bruno en la carpeta `bruno/`.
2. Selecciona el entorno **local** en Bruno (esquina superior derecha).
3. Ejecuta la solicitud **Login** (`auth/login.bru`) para obtener el token.
4. Copia el `accessToken` del response y pÃ©galo en la variable `accessToken` del entorno local.
5. Ve a la carpeta `usuarios_admin/` y ejecuta las solicitudes en orden.

## Endpoints disponibles

### Listar todos los usuarios

```
GET /api/admin/usuarios/
```

Sin parÃ¡metros retorna todos los usuarios. Respuesta:

```json
{
  "data": [
    {
      "id_usuario": 1,
      "email": "juan.perez@email.com",
      "telefono": "4611234567",
      "role": "farmer",
      "nombre": "Juan",
      "apellido_paterno": "PÃ©rez",
      "apellido_materno": "GarcÃ­a",
      "fecha_nacimiento": "1985-03-15",
      "genero": "M",
      "direccion": "Av. Principal 123",
      "localidad": 1,
      "localidad_nombre": "Centro",
      "estado": true,
      "creado_en": "2026-07-01T10:00:00Z"
    }
  ]
}
```

### Buscar por nombre o correo

```
GET /api/admin/usuarios/?search=juan
```

Busca en: `nombre`, `apellido_paterno`, `apellido_materno`, `correo` (case-insensitive).

### Filtrar por rol

```
GET /api/admin/usuarios/?rol=Cliente
```

Valores vÃ¡lidos (en espaÃ±ol, tal como estÃ¡n en la BD): `Admin`, `Agricultor`, `Vendedor`, `Cliente`

> **Nota**: El filtro usa `icontains` (case-insensitive), asÃ­ que `cliente`, `CLIENTE`, etc. tambiÃ©n funcionan.

### Filtrar por estado

```
GET /api/admin/usuarios/?estado=true
GET /api/admin/usuarios/?estado=false
```

### Combinar filtros

```
GET /api/admin/usuarios/?search=maria&rol=Agricultor&estado=true
```

### Ver detalle de usuario

```
GET /api/admin/usuarios/{id}/
```

### Editar usuario

```
PATCH /api/admin/usuarios/{id}/
```

Campos editables (todos opcionales):

```json
{
  "telefono": "4619999999",
  "nombre": "Juan",
  "apellido_paterno": "PÃ©rez",
  "apellido_materno": "GarcÃ­a",
  "fecha_nacimiento": "1985-03-15",
  "sexo": "M",
  "domicilio": "Av. Principal 123",
  "fk_localidad": 1,
  "role": "farmer"
}
```

Valores de `role`: `buyer` (Cliente), `farmer` (Agricultor), `admin` (Admin), `seller` (Vendedor)

### Activar/Desactivar usuario

```
PATCH /api/admin/usuarios/{id}/toggle-estado/
```

Sin body. Retorna el usuario con el estado invertido.

**ValidaciÃ³n**: Si el admin intenta desactivarse a sÃ­ mismo, retorna:

```json
{
  "detail": "No puedes desactivar tu propia cuenta de administrador."
}
```

## Variables del entorno local

| Variable          | DescripciÃ³n                          | Ejemplo              |
| ----------------- | ------------------------------------ | -------------------- |
| `baseUrl`         | URL base del backend                 | `http://localhost:8000` |
| `accessToken`     JWT token del login             | `eyJ0eXAiOiJKV1...` |
| `usuariosAdminId` | ID del usuario a gestionar          | `1`                  |
| `searchTerm`      | TÃ©rmino de bÃºsqueda                  | `admin`              |
| `rolFilter`       | Filtro por nombre de rol (en espaÃ±ol) | `Cliente`            |
| `estadoFilter`    | Filtro por estado (`true`/`false`)   | `true`               |

## Flujo recomendado de prueba

1. **Login** â†’ copiar `accessToken`
2. **Listar usuarios** â†’ verificar que retorna todos los usuarios
3. **Detalle** â†’ ver un usuario especÃ­fico (cambiar `usuariosAdminId`)
4. **Editar** â†’ modificar telÃ©fono o nombre
5. **Cambiar rol** â†’ cambiar un Cliente a Vendedor
6. **Toggle estado** â†’ desactivar un usuario
7. **Listar con filtro estado=false** â†’ verificar que el usuario desactivado aparece
8. **Toggle estado** â†’ reactivar el usuario
9. **Intentar desactivarse a sÃ­ mismo** â†’ debe retornar error 400

## Notas importantes

- Todos los endpoints requieren rol **Administrador**. Si usas credenciales de otro rol, recibirÃ¡s `403 Forbidden`.
- El toggle de estado es una operaciÃ³n idempotente: cada llamada invierte el estado actual.
- La bÃºsqueda es case-insensitive y busca coincidencias parciales ( LIKE %term% ).
