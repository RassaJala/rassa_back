# RASSA JALA - Plan de Arquitectura Django

**Documento de Estrategia para el Desarrollo de Módulos**

_Versión: 3.0_
_Fecha: 03/07/26_

---

## 1. Estado Actual del Proyecto

### 1.1 Estructura Django Configurada

```
back/
├── rassa/                              ← App principal (Django AppConfig)
│   ├── apps.py                         ← RassaConfig
│   ├── models.py                       ← 32 modelos del dominio
│   ├── urls.py                         ← Router principal (JWT auth)
│   ├── settings.py                     ← Configuración del proyecto
│   │
│   ├── auth_views.py                   ← CustomTokenObtainPairView (login JWT)
│   ├── auth_serializers.py             ← CustomTokenObtainPairSerializer
│   │
│   ├── permissions/                    ← Módulo de permisos RBAC
│   │   ├── __init__.py
│   │   └── role_permissions.py         ← 8 clases de permiso por rol
│   │
│   ├── migrations/                     ← 6 migraciones Django
│   │
│   ├── tests/                          ← Tests unitarios
│   │   ├── __init__.py
│   │   ├── test_auth_views.py
│   │   ├── test_auth_serializers.py
│   │   └── test_role_permissions.py
│   │
│   └── management/
│       └── commands/
│           └── seed_rassa_data.py      ← Seeders (32 tablas, 12 usuarios)
│
├── db/
│   └── archive/                        ← rassa_jala.sql (original)
│
├── docs/
│   ├── ARQUITECTURA_MODULOS.md         ← Este documento
│   └── USUARIOS_PRUEBA.md              ← Usuarios y catálogos de prueba
│
├── setup.sh                            ← Setup interactivo (Linux/macOS/Git Bash)
├── setup.ps1                           ← Setup interactivo (PowerShell)
├── .pylintrc                           ← Configuración pylint + django
├── pyproject.toml                      ← Dependencias uv
├── requirements.txt                    ← Dependencias pip
├── requirements-dev.txt                ← Dependencias de desarrollo
├── .env.template                       ← Template de variables de entorno
└── .env                                ← Variables de entorno (no versionado)
```

### 1.2 Modelos Implementados (32)

| Modelo                | Estado | Módulo Doc       | on_delete                                  |
| --------------------- | ------ | ---------------- | ------------------------------------------ |
| Rol                   | ✓      | M3 - Usuarios    | PROTECT                                    |
| CategoriaProducto     | ✓      | M1 - Catálogo    | —                                          |
| Unidad                | ✓      | M1 - Catálogo    | —                                          |
| EstadoPedido          | ✓      | M5 - Pedidos     | —                                          |
| DecisionMerma         | ✓      | M7 - Mermas      | —                                          |
| Municipio             | ✓      | M1 - Catálogo    | —                                          |
| Localidad             | ✓      | M1 - Catálogo    | CASCADE→Municipio                          |
| Persona               | ✓      | M3 - Usuarios    | SET_NULL→Localidad                         |
| Usuario               | ✓      | M3 - Usuarios    | SET_NULL→User, PROTECT→Rol                 |
| Familia               | ✓      | M4 - Familias    | SET_NULL→Usuario                           |
| FamiliaUsuario        | ✓      | M4 - Familias    | CASCADE                                    |
| LimiteCliente         | ✓      | M4 - Familias    | CASCADE                                    |
| Producto              | ✓      | M1 - Catálogo    | CASCADE→Categoria                          |
| PublicacionSemanal    | ✓      | M2 - Publicación | SET_NULL→Usuario                           |
| ProductoSemanal       | ✓      | M2 - Publicación | PROTECT→Unidad                             |
| PedidoCabecera        | ✓      | M5 - Pedidos     | SET_NULL→Usuario, PROTECT→EstadoPedido     |
| DetallePedido         | ✓      | M5 - Pedidos     | CASCADE                                    |
| TipoPago              | ✓      | M6 - Pagos       | —                                          |
| Pago                  | ✓      | M6 - Pagos       | SET_NULL→Pedido, PROTECT→TipoPago          |
| Merma                 | ✓      | M7 - Mermas      | SET_NULL→ProductoSemanal, PROTECT→Decision |
| Corte                 | ✓      | M6 - Pagos       | —                                          |
| Log                   | ✓      | M8 - Logs        | SET_NULL→Usuario                           |
| Conversacion          | ✓      | M9 - Chat        | —                                          |
| Integrante            | ✓      | M9 - Chat        | CASCADE                                    |
| Mensaje               | ✓      | M9 - Chat        | SET_NULL→Usuario, CASCADE→Conversacion     |
| Documento             | ✓      | M9 - Chat        | SET_NULL→Usuario                           |
| MensajeDocumento      | ✓      | M9 - Chat        | CASCADE                                    |
| ProductoImagen        | ✓      | M2 - Publicación | CASCADE→Producto                           |
| Recoleccion           | ✓      | M5 - Pedidos     | SET_NULL→Usuario                           |
| HistorialEstadoPedido | ✓      | M5 - Pedidos     | SET_NULL→Pedido/Usuario, PROTECT→Estado    |
| Recibo                | ✓      | M6 - Pagos       | SET_NULL→Pago/Pedido                       |
| Liquidacion           | ✓      | M6 - Pagos       | SET_NULL→Usuario                           |

### 1.3 Política de on_delete

| Política | Cantidad | Uso                                                           |
| -------- | -------- | ------------------------------------------------------------- |
| CASCADE  | 16       | Relación padre-hijo directa (hijo no tiene sentido sin padre) |
| SET_NULL | 19       | Preservar traza de auditoría e historial (fk nullable)        |
| PROTECT  | 6        | Catálogos compartidos no eliminables si tienen registros      |

### 1.4 Endpoints Actuales

| Endpoint              | Método | Descripción             | Autenticación |
| --------------------- | ------ | ----------------------- | ------------- |
| `/admin/`             | GET    | Panel de administración | Admin         |
| `/api/token/`         | POST   | Login JWT               | No            |
| `/api/token/refresh/` | POST   | Renovar access token    | No            |

### 1.5 Permisos RBAC Implementados

| Permiso               | Descripción         | Uso                | Tests   |
| --------------------- | ------------------- | ------------------ | ------- |
| `IsAdmin`             | Solo Administrador  | CRUD completo      | 5 tests |
| `IsAgricultor`        | Solo Agricultor     | Publicar productos | 3 tests |
| `IsVendedor`          | Solo Vendedor       | Gestionar pedidos  | 3 tests |
| `IsCliente`           | Solo Cliente        | Ver catálogo       | 2 tests |
| `IsAdminOrAgricultor` | Admin o Agricultor  | Gestión productos  | 4 tests |
| `IsAdminOrVendedor`   | Admin o Vendedor    | Gestión ventas     | 4 tests |
| `IsOwnerOrAdmin`      | Propietario o Admin | Perfil propio      | 6 tests |

**Total: 27 tests de permisos RBAC** (`rassa/tests/test_role_permissions.py`)

### 1.6 Roles del Sistema

| Backend (`roles.nombre_rol`) | Frontend (`user.role`) |
| ---------------------------- | ---------------------- |
| Administrador                | `"Administrador"`      |
| Vendedor                     | `"Vendedor"`           |
| Agricultor                   | `"Agricultor"`         |
| Cliente                      | `"Cliente"`            |

### 1.7 Migraciones

| Migración                          | Descripción                                       |
| ---------------------------------- | ------------------------------------------------- |
| `0001_initial`                     | 32 modelos Django, 42 tablas                      |
| `0002_remove_usuario_contrasenia`  | Eliminar campo `contrasenia` de `Usuario`         |
| `0003_log_fk_usuario_set_null`     | `Log.fk_usuario`: CASCADE → SET_NULL              |
| `0004_usuario_add_fk_user`         | Agregar `Usuario.fk_user` (OneToOne → auth.User)  |
| `0005_usuario_fk_user_set_null`    | `Usuario.fk_user`: CASCADE → SET_NULL             |
| `0006_cascade_to_set_null_protect` | Revisar 19 ForeignKey: CASCADE → SET_NULL/PROTECT |

---

## 2. Arquitectura por Módulos

### 2.1 Estrategia de Organización

Cada módulo del documento técnico se implementará como un módulo dentro de `rassa/`:

```
rassa/
├── auth_views.py              ← Login JWT (CustomTokenObtainPairView)
├── auth_serializers.py        ← Serializer con errores en español
├── permissions/               ← RBAC (8 clases de permiso)
│
├── blueprints/                ← Módulos futuros
│   ├── catalogo/              ← M1 - Catálogo y Ubicación
│   ├── publicacion/           ← M2 - Publicación Semanal
│   ├── usuarios/              ← M3 - Gestión de usuarios
│   ├── familias/              ← M4 - Familias
│   ├── pedidos/               ← M5 - Pedidos y Recolección
│   ├── pagos/                 ← M6 - Pagos y Cortes
│   ├── mermas/                ← M7 - Mermas
│   ├── logs/                  ← M8 - Logs y Seguridad
│   └── chat/                  ← M9 - Chat
│
├── middleware/
│   └── audit.py               ← Middleware de auditoría (M8)
│
├── tests/
│   ├── test_auth_views.py
│   ├── test_auth_serializers.py
│   └── test_role_permissions.py
│
└── management/
    └── commands/
        └── seed_rassa_data.py
```

---

## 3. Estrategia por Módulo

### 3.1 Módulo M1 - Catálogo y Ubicación

**Responsables:** Luis Contreras y Armando Frías
**Dependencias:** Ninguna (base)

#### Modelos Relacionados

- `CategoriaProducto`
- `Producto`
- `Unidad`
- `Municipio`
- `Localidad`
- `ProductoImagen`

#### Estrategia de Implementación

1. **Serializers** (`rassa/blueprints/catalogo/serializers.py`)
   - `CategoriaSerializer` - CRUD de categorías
   - `ProductoSerializer` - CRUD de productos con imagen
   - `UnidadSerializer` - CRUD de unidades
   - `MunicipioSerializer` - Lectura de municipios
   - `LocalidadSerializer` - Lectura de localidades

2. **Views** (`rassa/blueprints/catalogo/views.py`)
   - `CategoriaViewSet` - ViewSet para categorías
   - `ProductoViewSet` - ViewSet para productos
   - `UnidadViewSet` - ViewSet para unidades
   - `MunicipioViewSet` - Solo lectura
   - `LocalidadViewSet` - Solo lectura

3. **URLs** (`rassa/blueprints/catalogo/urls.py`)

   ```python
   router = DefaultRouter()
   router.register(r"categorias", CategoriaViewSet)
   router.register(r"productos", ProductoViewSet)
   router.register(r"unidades", UnidadViewSet)
   router.register(r"municipios", MunicipioViewSet, basename="municipio")
   router.register(r"localidades", LocalidadViewSet, basename="localidad")
   ```

4. **Permisos**
   - Admin: CRUD completo
   - Agricultor: Solo lectura de catálogos
   - Cliente: Solo lectura

#### Endpoints

| Endpoint                        | Método | Permisos |
| ------------------------------- | ------ | -------- |
| `/api/v1/catalogo/categorias/`  | CRUD   | Admin    |
| `/api/v1/catalogo/productos/`   | CRUD   | Admin    |
| `/api/v1/catalogo/unidades/`    | CRUD   | Admin    |
| `/api/v1/catalogo/municipios/`  | GET    | Todos    |
| `/api/v1/catalogo/localidades/` | GET    | Todos    |

---

### 3.2 Módulo M2 - Publicación Semanal

**Responsables:** César García y Cristiam García
**Dependencias:** M1 (Catálogo)

#### Modelos Relacionados

- `PublicacionSemanal`
- `ProductoSemanal`
- `ProductoImagen`

#### Estrategia de Implementación

1. **Regla de Negocio Crítica**
   - Publicaciones solo los **lunes**
   - Validar día en serializer o view

2. **Serializers** (`rassa/blueprints/publicacion/serializers.py`)
   - `PublicacionSemanalSerializer` - Crear publicación semanal
   - `ProductoSemanalSerializer` - Agregar productos a publicación
   - Validar que `fecha_publicacion` sea lunes

3. **Views** (`rassa/blueprints/publicacion/views.py`)
   - `PublicacionSemanalViewSet` - CRUD con validación de día
   - `ProductoSemanalViewSet` - CRUD de productos semanales
   - `PublicacionActivaView` - Obtener publicación de la semana

4. **Lógica de Validación**
   ```python
   def validate_fecha_publicacion(self, value):
       if value.weekday() != 0:  # 0 = Lunes
           raise ValidationError("Las publicaciones solo se realizan los lunes")
       return value
   ```

#### Endpoints

| Endpoint                         | Método | Permisos          |
| -------------------------------- | ------ | ----------------- |
| `/api/v1/publicacion/semanal/`   | CRUD   | Agricultor, Admin |
| `/api/v1/publicacion/productos/` | CRUD   | Agricultor, Admin |
| `/api/v1/publicacion/activa/`    | GET    | Cliente, Vendedor |

---

### 3.3 Módulo M3 - Usuarios y Roles

**Responsables:** Salvador González y Omar López
**Dependencias:** Base (requerido por todos)

#### Modelos Relacionados

- `Rol` (PROTECT — no se puede eliminar un rol con usuarios)
- `Persona`
- `Usuario` (fk_user → auth.User con SET_NULL)
- `LimiteCliente`

#### Estrategia de Implementación

1. **Serializers** (`rassa/blueprints/usuarios/serializers.py`)
   - `RegistroSerializer` - Registro completo (persona + usuario)
   - `UsuarioSerializer` - Perfil de usuario
   - `CambioContrasenaSerializer` - Cambio de contraseña
   - `AdminUsuarioSerializer` - Gestión admin (cambiar rol, desactivar)

2. **Views** (`rassa/blueprints/usuarios/views.py`)
   - `RegistroView` - POST /api/v1/usuarios/registro/
   - `PerfilView` - GET/PUT /api/v1/usuarios/perfil/
   - `CambioContrasenaView` - PUT /api/v1/usuarios/cambio-contrasena/
   - `AdminUsuarioViewSet` - CRUD para administradores

3. **Permisos RBAC**

   ```python
   from rassa.permissions.role_permissions import IsAdmin, IsOwnerOrAdmin


   class UsuarioViewSet(viewsets.ModelViewSet):
       def get_permissions(self):
             if self.action == "list":
               return [IsAdmin()]
           return [IsOwnerOrAdmin()]
   ```

4. **Integración con JWT**
   - Login: `/api/token/` (CustomTokenObtainPairView)
   - Refresh: `/api/token/refresh/` (TokenRefreshView)

#### Endpoints

| Endpoint                              | Método  | Permisos    |
| ------------------------------------- | ------- | ----------- |
| `/api/v1/usuarios/`                   | GET     | Admin       |
| `/api/v1/usuarios/{id}/`              | GET/PUT | Owner/Admin |
| `/api/v1/usuarios/cambio-contrasena/` | PUT     | Autenticado |
| `/api/v1/usuarios/admin/`             | CRUD    | Admin       |

---

### 3.4 Módulo M4 - Familias

**Responsables:** Mauricio Montero
**Dependencias:** M3 (Usuarios)

#### Modelos Relacionados

- `Familia` (SET_NULL→Usuario en fk_jefe_familia)
- `FamiliaUsuario`
- `LimiteCliente`

#### Estrategia de Implementación

1. **Serializers** (`rassa/blueprints/familias/serializers.py`)
   - `FamiliaSerializer` - CRUD de familias
   - `FamiliaUsuarioSerializer` - Asignar miembros
   - `LimiteClienteSerializer` - Gestión de crédito

2. **Views** (`rassa/blueprints/familias/views.py`)
   - `FamiliaViewSet` - CRUD con validación
   - `MiembrosFamiliaView` - Listar/agregar miembros
   - `LimiteClienteViewSet` - Gestión de crédito

3. **Reglas de Negocio**
   - Un usuario solo puede pertenerer a **una** familia (UNIQUE)
   - Un límite de crédito por cliente (UNIQUE)
   - Validar en serializer

#### Endpoints

| Endpoint                           | Método   | Permisos |
| ---------------------------------- | -------- | -------- |
| `/api/v1/familias/`                | CRUD     | Admin    |
| `/api/v1/familias/{id}/miembros/`  | GET/POST | Admin    |
| `/api/v1/familias/limite-credito/` | CRUD     | Admin    |

---

### 3.5 Módulo M5 - Pedidos y Recolección

**Responsables:** Kevin Quintero, Emmanuel Ramírez, Jordi Meza
**Dependencias:** M1, M2, M3, M4

#### Modelos Relacionados

- `PedidoCabecera` (SET_NULL→Cliente, PROTECT→EstadoPedido, SET_NULL→Vendedor)
- `DetallePedido` (CASCADE)
- `EstadoPedido` (PROTECT — no se puede eliminar un estado en uso)
- `HistorialEstadoPedido` (SET_NULL→Pedido/Usuario, PROTECT→EstadoNuevo)
- `Recoleccion` (SET_NULL→Usuario)

#### Estrategia de Implementación

1. **Serializers** (`rassa/blueprints/pedidos/serializers.py`)
   - `PedidoSerializer` - Crear pedido
   - `DetallePedidoSerializer` - Items del pedido
   - `HistorialEstadoSerializer` - Cambios de estado
   - `RecoleccionSerializer` - Programación de recolección

2. **Views** (`rassa/blueprints/pedidos/views.py`)
   - `PedidoViewSet` - CRUD con validación
   - `CarritoView` - Agregar/eliminar items
   - `CheckoutView` - Confirmar pedido (descuenta stock)
   - `HistorialPedidoView` - Historial del cliente
   - `PanelVendedorView` - Pedidos activos
   - `RecoleccionViewSet` - Gestión de recolección

3. **Flujo de Pedido**

   ```
   Cliente crea pedido → Pendiente
   Vendedor confirma → Confirmado → En preparación
   Listo para retirar → Entregado
   Cualquier estado → Cancelado
   ```

4. **Validación de Rol**
   - Solo usuarios con rol 'Cliente' pueden crear pedidos
   - Usar `IsCliente` o validar en serializer

5. **Descuento de Stock**
   - Al confirmar pedido: `ProductoSemanal.stock -= cantidad`
   - Validar stock suficiente antes de confirmar

#### Endpoints

| Endpoint                       | Método   | Permisos        |
| ------------------------------ | -------- | --------------- |
| `/api/v1/pedidos/`             | CRUD     | Cliente         |
| `/api/v1/pedidos/carrito/`     | GET/POST | Cliente         |
| `/api/v1/pedidos/checkout/`    | POST     | Cliente         |
| `/api/v1/pedidos/historial/`   | GET      | Cliente         |
| `/api/v1/pedidos/vendedor/`    | GET      | Vendedor        |
| `/api/v1/pedidos/{id}/estado/` | PUT      | Vendedor        |
| `/api/v1/pedidos/recoleccion/` | CRUD     | Admin, Vendedor |

---

### 3.6 Módulo M6 - Pagos y Cortes

**Responsables:** Abraham Rodríguez
**Dependencias:** M5 (Pedidos)

#### Modelos Relacionados

- `TipoPago` (PROTECT — no se puede eliminar un tipo con pagos)
- `Pago` (SET_NULL→Pedido, PROTECT→TipoPago)
- `Corte`
- `Recibo` (SET_NULL→Pago/Pedido)
- `Liquidacion` (SET_NULL→Usuario, SET_NULL→Pago)

#### Estrategia de Implementación

1. **Serializers** (`rassa/blueprints/pagos/serializers.py`)
   - `PagoSerializer` - Registrar pago
   - `CorteSerializer` - Corte de caja
   - `ReciboSerializer` - Generar recibo
   - `LiquidacionSerializer` - Liquidación de agricultor

2. **Views** (`rassa/blueprints/pagos/views.py`)
   - `PagoViewSet` - CRUD de pagos
   - `CorteViewSet` - Apertura/cierre de caja
   - `ReciboViewSet` - Generar recibos
   - `LiquidacionViewSet` - Liquidaciones

3. **Reglas de Negocio**
   - Monto pagado no puede exceder total del pedido
   - Corte: Abierto → Cerrado → Cuadrado
   - Calcular diferencia automáticamente

4. **Estados del Corte**
   ```python
   ESTADO_CORTE = [
       ("abierto", "Abierto"),
       ("cerrado", "Cerrado"),
       ("cuadrado", "Cuadrado"),
   ]
   ```

#### Endpoints

| Endpoint                     | Método | Permisos        |
| ---------------------------- | ------ | --------------- |
| `/api/v1/pagos/`             | CRUD   | Vendedor        |
| `/api/v1/pagos/corte/`       | CRUD   | Vendedor, Admin |
| `/api/v1/pagos/recibos/`     | CRUD   | Vendedor        |
| `/api/v1/pagos/liquidacion/` | CRUD   | Admin           |

---

### 3.7 Módulo M7 - Mermas

**Responsables:** Jesús Solís
**Dependencias:** M2 (Publicación)

#### Modelos Relacionados

- `Merma` (SET_NULL→ProductoSemanal, PROTECT→Decision)
- `DecisionMerma` (PROTECT — no se puede eliminar una decisión en uso)

#### Estrategia de Implementación

1. **Serializers** (`rassa/blueprints/mermas/serializers.py`)
   - `MermaSerializer` - Registrar merma
   - `DecisionMermaSerializer` - Catálogo de decisiones
   - `ResumenMermaSerializer` - Estadísticas

2. **Views** (`rassa/blueprints/mermas/views.py`)
   - `MermaViewSet` - CRUD de mermas
   - `DecisionMermaViewSet` - Catálogo
   - `ResumenMermaView` - Estadísticas por semana/mes

3. **Lógica de Descuento**
   - Al registrar merma: `ProductoSemanal.stock -= cantidad`
   - Registrar decisión (donar, desechar, etc.)

4. **Estadísticas**
   - Productos más afectados
   - Totales por semana y mes
   - Gráfica simple (frontend)

#### Endpoints

| Endpoint                     | Método | Permisos             |
| ---------------------------- | ------ | -------------------- |
| `/api/v1/mermas/`            | CRUD   | Vendedor, Agricultor |
| `/api/v1/mermas/decisiones/` | GET    | Todos                |
| `/api/v1/mermas/resumen/`    | GET    | Admin                |

---

### 3.8 Módulo M8 - Logs y Seguridad

**Responsables:** Luis Torres
**Dependencias:** Transversal (todos los módulos)

#### Modelos Relacionados

- `Log` (SET_NULL→Usuario — preservar auditoría)

#### Estrategia de Implementación

1. **Middleware de Auditoría** (`rassa/middleware/audit.py`)

   ```python
   class AuditMiddleware:
       def __init__(self, get_response):
           self.get_response = get_response

       def __call__(self, request):
           response = self.get_response(request)
           if request.user.is_authenticated:
               Log.objects.create(
                   fk_usuario=request.user.usuario,
                   accion=request.method,
                   ip=self.get_client_ip(request),
                   dispositivo=request.META.get("HTTP_USER_AGENT", ""),
               )
           return response
   ```

2. **Serializers** (`rassa/blueprints/logs/serializers.py`)
   - `LogSerializer` - Consulta de logs

3. **Views** (`rassa/blueprints/logs/views.py`)
   - `LogViewSet` - Solo lectura, filtrado por usuario/fecha/acción

4. **Configuración en settings.py**

   ```python
   MIDDLEWARE = [
       "rassa.middleware.audit.AuditMiddleware",
       # ... otros middleware
   ]
   ```

5. **Seguridad**
   - Credenciales en `.env`
   - Contraseñas encriptadas (Django User)
   - CORS configurado

#### Endpoints

| Endpoint                          | Método | Permisos |
| --------------------------------- | ------ | -------- |
| `/api/v1/logs/`                   | GET    | Admin    |
| `/api/v1/logs/?usuario=X&fecha=Y` | GET    | Admin    |

---

### 3.9 Módulo M9 - Chat

**Responsables:** Enrique Carrillo y Gerardo Sánchez
**Dependencias:** M3 (Usuarios), M4 (Familias), M5 (Pedidos)

#### Modelos Relacionados

- `Conversacion`
- `Integrante` (CASCADE)
- `Mensaje` (SET_NULL→Usuario, CASCADE→Conversacion)
- `Documento` (SET_NULL→Usuario)
- `MensajeDocumento` (CASCADE)

#### Estrategia de Implementación

1. **Serializers** (`rassa/blueprints/chat/serializers.py`)
   - `ConversacionSerializer` - Crear/listar conversaciones
   - `MensajeSerializer` - Enviar/recibir mensajes
   - `DocumentoSerializer` - Adjuntar archivos

2. **Views** (`rassa/blueprints/chat/views.py`)
   - `ConversacionViewSet` - CRUD de conversaciones
   - `MensajeViewSet` - Enviar mensajes
   - `DocumentoView` - Subir archivos

3. **Reglas de Negocio**
   - Cliente solo chatea con agricultor dueño del producto
   - Agricultor chatea con Admin y familia
   - Admin chatea con todos
   - Chat grupal automático por familia

4. **Permisos de Visibilidad**

   ```python
   class IsConversationMember(permissions.BasePermission):
       def has_object_permission(self, request, view, obj):
           return request.user.usuario in obj.integrantes.all()
   ```

5. **Tipos de Archivo**
   - Texto
   - Grupo familiar
   - Fotografías
   - Audio
   - Video

#### Endpoints

| Endpoint                       | Método | Permisos    |
| ------------------------------ | ------ | ----------- |
| `/api/v1/chat/conversaciones/` | CRUD   | Autenticado |
| `/api/v1/chat/mensajes/`       | CRUD   | Miembros    |
| `/api/v1/chat/documentos/`     | POST   | Miembros    |

---

## 4. Estructura de URLs Actual

```python
# rassa/urls.py
from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from rassa.auth_views import CustomTokenObtainPairView

urlpatterns = [
    path("admin/", admin.site.urls),
    # JWT auth (original)
    path("api/token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Blueprints (futuros)
    # path("api/v1/catalogo/", include("rassa.blueprints.catalogo.urls")),
    # path("api/v1/publicacion/", include("rassa.blueprints.publicacion.urls")),
    # ...
]
```

> **Nota:** Los blueprints se agregarán progresivamente cuando cada módulo
> sea implementado por los desarrolladores asignados.

---

## 5. Convenciones de Código

### 5.1 Estructura de un Módulo

```python
# rassa/blueprints/{modulo}/__init__.py
"""Módulo {Nombre} del proyecto Rassa JALA."""

# rassa/blueprints/{modulo}/serializers.py
"""Serializadores del módulo {Nombre}."""

from rest_framework import serializers
from rassa.models import ModeloX


class ModeloXSerializer(serializers.ModelSerializer):
    """Serializador para el modelo ModeloX."""

    class Meta:
        model = ModeloX
        fields = "__all__"


# rassa/blueprints/{modulo}/views.py
"""Vistas del módulo {Nombre}."""

from rest_framework import viewsets
from rassa.models import ModeloX
from .serializers import ModeloXSerializer


class ModeloXViewSet(viewsets.ModelViewSet):
    """ViewSet para CRUD de ModeloX."""

    queryset = ModeloX.objects.all()
    serializer_class = ModeloXSerializer


# rassa/blueprints/{modulo}/urls.py
"""Rutas del módulo {Nombre}."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ModeloXViewSet

router = DefaultRouter()
router.register(r"modelos-x", ModeloXViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
```

### 5.2 Permisos por Rol

```python
# rassa/permissions/role_permissions.py
from rest_framework import permissions


class IsAdmin(permissions.BasePermission):
    """Permiso para usuarios con rol Administrador."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.usuario.fk_rol.nombre_rol == "Administrador"
        except AttributeError:
            return False


class IsAgricultor(permissions.BasePermission):
    """Permiso para usuarios con rol Agricultor."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.usuario.fk_rol.nombre_rol == "Agricultor"
        except AttributeError:
            return False


class IsVendedor(permissions.BasePermission):
    """Permiso para usuarios con rol Vendedor."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.usuario.fk_rol.nombre_rol == "Vendedor"
        except AttributeError:
            return False


class IsCliente(permissions.BasePermission):
    """Permiso para usuarios con rol Cliente."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.usuario.fk_rol.nombre_rol == "Cliente"
        except AttributeError:
            return False
```

### 5.3 Naming Conventions

| Elemento   | Convención              | Ejemplo                                    |
| ---------- | ----------------------- | ------------------------------------------ |
| Modelo     | PascalCase              | `ProductoSemanal`                          |
| Serializer | PascalCase + Serializer | `ProductoSemanalSerializer`                |
| ViewSet    | PascalCase + ViewSet    | `ProductoSemanalViewSet`                   |
| URL        | kebab-case              | `/api/v1/publicacion/productos-semanales/` |
| Módulo     | snake_case              | `rassa/blueprints/publicacion/`            |

---

## 6. Tests

### 6.1 Cobertura Actual

| Archivo                    | Tests  | Descripción                        |
| -------------------------- | ------ | ---------------------------------- |
| `test_role_permissions.py` | 27     | Unitarios de permisos RBAC         |
| `test_auth_views.py`       | 2      | Importación de auth views          |
| `test_auth_serializers.py` | 6      | Serializer JWT con errores español |
| **Total**                  | **35** | **Todos pasan al 100%**            |

### 6.2 Ejecutar Tests

```bash
# Todos los tests
python manage.py test rassa.tests -v2

# Solo permisos RBAC
python manage.py test rassa.tests.test_role_permissions -v2

# Solo auth
python manage.py test rassa.tests.test_auth_views rassa.tests.test_auth_serializers -v2
```

---

**Documento generado como parte del plan de arquitectura para el desarrollo de módulos en RASSA JALA.**
