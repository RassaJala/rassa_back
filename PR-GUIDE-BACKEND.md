---
project: rassa_back
repository: https://github.com/ObedAlPa/rassa_back
stack: Django 5, Django REST Framework, PostgreSQL, JWT (SimpleJWT), Python 3.12+
base_branch: main
branch_prefixes:
  - feat/
  - fix/
  - refactor/
  - test/
  - docs/
  - chore/
  - hotfix/
commands:
  test: "python manage.py test rassa.tests -v2"
  test_verbose: "bash start.sh --test --verbose"
  lint: "flake8 ."
  check: "python manage.py check --deploy"
  migrations: "python manage.py migrate"
  seed: "python manage.py seed_rassa_data"
  server: "bash start.sh"
architecture: "blueprints — rassa/blueprints/{modulo}/"
modules:
  - catalogo
  - publicacion
  - usuarios
  - familias
  - pedidos
  - pagos
  - mermas
  - logs
  - chat
roles:
  - Administrador
  - Agricultor
  - Vendedor
  - Cliente
bruno_directory: "bruno/"
---

# PR Guide — Backend (rassa_back)

## INSTRUCCIONES PARA IA

Cuando un desarrollador solicite crear un PR para **rassa_back**, este documento es la referencia **obligatoria**. Lee cada sección y aplícala al contexto del PR.

**Flujo de uso:**
1. El desarrollador describe qué quiere hacer
2. Tú lees este documento completo
3. Aplicas las reglas de naming, commits, PR template, checklist y Bruno
4. Generas la rama, commits y PR siguiendo este formato

---

## 1. Nombre de Rama

### Formato

```
tipo/descripcion-corta-en-ingles
```

### Reglas

- **Sin espacios** — guiones (`-`) para separar palabras
- **Todo en minúsculas** — sin excepciones
- **Máximo 4 palabras** — ser conciso pero descriptivo
- **Nunca** incluir números de issue en la rama
- **Nunca** usar nombres genéricos: `update`, `fix`, `test`, `changes`

### Ejemplos Correctos

```
feat/user-registration-endpoint
fix/token-expiration-crash
refactor/catalogo-viewset
test/role-permissions-coverage
docs/api-endpoints-bruno
chore/requirements-update
```

### Ejemplos Incorrectos

```
fix-branch-2                          ← genérico
feat/issue-42-add-login               ← issue number no va aquí
Test Branch                           ← mayúsculas y espacios
WIP                                   ← trabajo en progreso
```

---

## 2. Nombre del PR

### Formato

```
tipo(alcance): descripción corta en inglés, imperative mood
```

### Reglas

- **Imperative mood**: "add", "fix", "resolve", "remove" — NUNCA "added", "fixed"
- **Máximo 72 caracteres**
- **Minúscula** después del paréntesis
- **Sin punto** al final
- Referencia a issue al final: `(#issue-number)`

### Ejemplos

```
feat(usuarios): add user registration endpoint with validation
fix(auth): resolve JWT token expiration race condition
refactor(catalogo): extract shared serializers for products
test(permissions): add RBAC tests for admin-only endpoints
```

---

## 3. Commits

### Convención

```
tipo(alcance): descripción corta

[Opcional: contexto adicional]
```

### Reglas

| Regla | Detalle |
|-------|---------|
| Un commit = Un cambio lógico | No mezclar feat + fix |
| Descripción clara | Explicar QUÉ y POR QUÉ |
| Sin código basura | No `print()`, `breakpoint()`, `pdb` |
| Tests incluidos | Si hay lógica nueva, incluir test |
| Compila | Cada commit debe pasar `manage.py check` |
| Tamaño ideal | 50-200 líneas, máx tolerable ~400 |

### Tipos Permitidos (Conventional Commits)

| Tipo | Uso |
|------|-----|
| `feat` | Nueva funcionalidad |
| `fix` | Corrección de bug |
| `refactor` | Reestructurar sin cambiar comportamiento |
| `test` | Agregar o mejorar tests |
| `docs` | Documentación |
| `chore` | Tareas de mantenimiento |
| `style` | Formato (no afecta lógica) |
| `ci` | Integración continua |
| `perf` | Mejoras de rendimiento |
| `migrate` | Migraciones de base de datos |

### Ejemplo de Historial Limpio

```
a1b2c3d feat(usuarios): add user registration endpoint
b2c3d4e feat(usuarios): add input validation in serializer
c3d4e5f feat(usuarios): add RBAC permissions for registration
d4e5f6g test(usuarios): add unit tests for registration flow
e5f6g7h docs(bruno): add registration endpoint to Bruno collection
```

---

## 4. Template del PR (Obligatorio)

Todo PR **DEBE** incluir esta descripción:

```markdown
## 📌 Descripción
<!-- 2-3 oraciones: QUÉ hace este PR y POR QUÉ es necesario -->

## 🔄 Tipo de Cambio
- [ ] 🐛 Bug fix
- [ ] ✨ Feature
- [ ] ♻️ Refactor
- [ ] 📝 Docs
- [ ] 🧪 Test
- [ ] 🔧 Chore
- [ ] 🗄️ Migración

## 📂 Archivos Modificados
| Archivo | Qué cambió | Por qué |
|---------|-----------|---------|
| `rassa/blueprints/...` | Descripción | Razón |

## 🔗 Endpoints Afectados
| Endpoint | Método | Permisos | Estado |
|----------|--------|----------|--------|
| `/api/v1/...` | POST | Admin | NUEVO |

## 🧪 Cómo Probarlo
1. [Paso para verificar]
2. [Resultado esperado]

## 📁 Bruno
<!-- SI el PR crea o modifica endpoints, esta sección es OBLIGATORIA -->
- [ ] Archivos `.bru` incluidos en `bruno/`
- [ ] Variables de entorno configuradas
- [ ] Request body con ejemplo real
- [ ] Headers documentados

## 🔐 Permisos RBAC
<!-- SI el PR maneja autenticación/autorización -->
| Endpoint | Permiso requerido | Rol |
|----------|-------------------|-----|
| `POST /api/v1/...` | `IsAdmin` | Administrador |

## 🗄️ Migraciones
<!-- SI el PR genera migraciones -->
- [ ] Migración generada y incluida
- [ ] `python manage.py migrate` ejecuta sin errores
- [ ] `python manage.py check --deploy` pasa

## ✅ Checklist
- [ ] `python manage.py test rassa.tests -v2` pasa
- [ ] `python manage.py check --deploy` pasa
- [ ] No hay `print()`, `breakpoint()`, `pdb` olvidados
- [ ] Rama actualizada con main (sin conflictos)
- [ ] Serializers con errores en español
- [ ] Permisos RBAC documentados en el PR
- [ ] Archivos Bruno incluidos (si hay endpoints nuevos/modificados)
```

---

## 5. Verificación Antes de Abrir PR

### Comandos Obligatorios

```bash
# 1. Tests
python manage.py test rassa.tests -v2

# 2. Check de Django
python manage.py check --deploy

# 3. Verificar migraciones pendientes
python manage.py showmigrations --list

# 4. Si hay migraciones nuevas, verificar que aplican
python manage.py migrate --run-syncdb
```

### REGLA INQUEBRANTABLE

**No solicitar review si:**
- ❌ Tests fallan
- ❌ `manage.py check` tiene errores
- ❌ Hay migraciones sin aplicar
- ❌ Hay conflictos sin resolver
- ❌ CI está rojo

---

## 6. Arquitectura Backend — Blueprints

### Estructura de un Módulo

```
rassa/blueprints/{modulo}/
├── __init__.py         ← Docstring del módulo
├── serializers.py      ← Serializadores DRF
├── views.py            ← ViewSets y Views
├── urls.py             ← Rutas del módulo
└── tests.py            ← Tests del módulo (opcional, puede ir en rassa/tests/)
```

### Convenciones de Naming

| Elemento | Convención | Ejemplo |
|----------|-----------|---------|
| Modelo | PascalCase | `ProductoSemanal` |
| Serializer | PascalCase + Serializer | `ProductoSemanalSerializer` |
| ViewSet | PascalCase + ViewSet | `ProductoSemanalViewSet` |
| URL | kebab-case | `/api/v1/publicacion/productos-semanales/` |
| Módulo | snake_case | `rassa/blueprints/publicacion/` |

### Ejemplo de ViewSet

```python
# rassa/blueprints/catalogo/views.py
"""Vistas del módulo Catálogo."""

from rest_framework import viewsets
from rassa.models import Producto
from rassa.permissions.role_permissions import IsAdmin, IsAdminOrAgricultor
from .serializers import ProductoSerializer


class ProductoViewSet(viewsets.ModelViewSet):
    """ViewSet para CRUD de Productos."""

    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [IsAdminOrAgricultor()]
        return [IsAdmin()]
```

### Ejemplo de Serializer

```python
# rassa/blueprints/catalogo/serializers.py
"""Serializadores del módulo Catálogo."""

from rest_framework import serializers
from rassa.models import Producto


class ProductoSerializer(serializers.ModelSerializer):
    """Serializador para Producto."""

    class Meta:
        model = Producto
        fields = "__all__"

    def validate_nombre(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError("El nombre debe tener al menos 3 caracteres.")
        return value.strip()
```

### Ejemplo de URLs

```python
# rassa/blueprints/catalogo/urls.py
"""Rutas del módulo Catálogo."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductoViewSet

router = DefaultRouter()
router.register(r"productos", ProductoViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
```

---

## 7. Permisos RBAC

### Permisos Disponibles

| Permiso | Rol Requerido | Uso |
|---------|--------------|-----|
| `IsAdmin` | Administrador | CRUD completo |
| `IsAgricultor` | Agricultor | Publicar productos |
| `IsVendedor` | Vendedor | Gestionar pedidos |
| `IsCliente` | Cliente | Ver catálogo, crear pedidos |
| `IsAdminOrAgricultor` | Admin o Agricultor | Gestión productos |
| `IsAdminOrVendedor` | Admin o Vendedor | Gestión ventas |
| `IsOwnerOrAdmin` | Propietario o Admin | Perfil propio |

### Cómo Documentar en el PR

Si el PR incluye endpoints con permisos, **DEBE** incluir esta tabla en la descripción:

```markdown
## 🔐 Permisos RBAC
| Endpoint | Permiso | Rol |
|----------|---------|-----|
| `POST /api/v1/usuarios/registro/` | Sin permiso | Público |
| `GET /api/v1/usuarios/` | `IsAdmin` | Administrador |
| `PUT /api/v1/usuarios/{id}/` | `IsOwnerOrAdmin` | Propietario o Admin |
```

---

## 8. Bruno — OBLIGATORIO para Endpoints

### Cuándo Incluir

Si el PR **crea, modifica o elimina** un endpoint de la API, los archivos de Bruno **DEBEN** estar incluidos.

### Estructura Actual

```
bruno/
├── bruno.json
├── auth/
│   ├── login.bru
│   ├── refresh_token.bru
│   ├── register.bru
│   ├── get_me.bru
│   ├── patch_me.bru
│   └── change_password.bru
├── catalogos/
│   ├── municipios.bru
│   └── localidades.bru
└── environments/
    └── local.bru
```

### Formato de Archivo Bruno

```http
### Login - POST /api/token/
POST {{baseUrl}}/api/token/
Content-Type: application/json
Accept: application/json

{
  "email": "admin@rassa.com",
  "password": "admin123"
}

### Refresh Token - POST /api/token/refresh/
POST {{baseUrl}}/api/token/refresh/
Content-Type: application/json
Accept: application/json

{
  "refresh": "{{refreshToken}}"
}
```

### Reglas para Bruno

| Regla | Detalle |
|-------|---------|
| Un archivo `.bru` por endpoint | No agrupar múltiples endpoints |
| Comentario descriptivo | `### Nombre - MÉTODO /url` |
| Variables de entorno | Usar `{{baseUrl}}`, `{{accessToken}}`, etc. |
| Body con ejemplo real | No datos vacíos, usar datos de prueba |
| Headers completos | Incluir Content-Type, Authorization si aplica |
| Ubicación correcta | En la carpeta del módulo: `bruno/{modulo}/` |

### Checklist Bruno para el PR

- [ ] Archivo `.bru` creado para cada endpoint nuevo/modificado
- [ ] Variables de entorno configuradas (`{{baseUrl}}`, `{{accessToken}}`)
- [ ] Request body con ejemplo real
- [ ] Headers documentados
- [ ] Ubicación correcta en `bruno/{modulo}/`

---

## 9. Migraciones

### Cuándo Generar

Si el PR agrega o modifica modelos:

```bash
# Generar migración
python manage.py makemigrations rassa

# Verificar que aplica
python manage.py migrate

# Verificar que tests pasan
python manage.py test rassa.tests -v2
```

### Reglas

- **Siempre** incluir la migración generada en el PR
- **Nunca** editar migraciones existentes (generar nueva)
- **Verificar** que `python manage.py migrate` ejecuta sin errores
- **Documentar** en el PR qué cambia la migración

---

## 10. Seguridad

### Datos Sensibles

- [ ] No hardcodear `SECRET_KEY`, `DATABASE_URL`, contraseñas
- [ ] No commitear `.env` (solo `.env.template`)
- [ ] No commitear `__pycache__/`, `*.pyc`, `.venv/`
- [ ] Verificar `.gitignore`

### Autenticación

- [ ] JWT configurado con SimpleJWT
- [ ] Endpoints protegidos con permisos RBAC
- [ ] Contraseñas hasheadas (Django User)
- [ ] CORS configurado correctamente

### Input Validation

- [ ] Serializers con validación en campos obligatorios
- [ ] No usar `allow_blank=True` en campos sensibles
- [ ] Sanitizar input del usuario

---

## 11. Tamaño del PR

| Tamaño | Líneas | Veredicto |
|--------|--------|-----------|
| 🟢 Ideal | 50-200 | Review rápida |
| 🟡 Aceptable | 200-400 | Justificar en descripción |
| 🔴 Grande | 400-800 | Dividir si es posible |
| ⛔ Problema | 800+ | OBLIGATORIO dividir |

**Un PR = Una cosa.** No mezclar feat + fix + refactor.

---

## 12. Responder a Review

### Flujo

1. Leer TODOS los comentarios
2. Hacer cambios en commits nuevos (NO amend)
3. Responder cada comentario:
   - ✅ `Done` — cambio aplicado
   - 💬 `Done — ajusté porque [razón]` — con variación
   - 🤔 `Prefiero no cambiar porque [razón]` — discrepar
4. Push commits nuevos
5. Comentar: "Changes applied, ready for re-review ✅"

**Nunca:**
- Ignorar comentarios
- Hacer squash de fixes
- Pedir re-review sin responder todo

---

## 13. Ejemplo de PR Completo

### Rama
```
feat/usuarios-registration
```

### Título
```
feat(usuarios): add user registration endpoint with RBAC and Bruno
```

### Commits
```
a1b2c3d feat(usuarios): add registration serializer with validation
b2c3d4e feat(usuarios): add registration view with RBAC permissions
c3d4e5f feat(usuarios): add registration URL to router
d4e5f6g test(usuarios): add unit tests for registration flow
e5f6g7h docs(bruno): add registration endpoint to Bruno collection
```

### Descripción
```markdown
## 📌 Descripción
Implementación del endpoint de registro de usuarios con validación
completa, permisos RBAC, y archivo Bruno para testing.

## 🔄 Tipo de Cambio
- [x] ✨ Feature

## 📂 Archivos Modificados
| Archivo | Qué cambió | Por qué |
|---------|-----------|---------|
| `rassa/blueprints/usuarios/serializers.py` | RegistroSerializer | Validación de registro |
| `rassa/blueprints/usuarios/views.py` | RegistroView | Endpoint de registro |
| `rassa/blueprints/usuarios/urls.py` | URL /registro/ | Routing |
| `rassa/tests/test_usuarios.py` | Tests de registro | Cobertura |
| `bruno/usuarios/registro.bru` | Endpoint Bruno | Testing manual |

## 🔗 Endpoints Afectados
| Endpoint | Método | Permisos | Estado |
|----------|--------|----------|--------|
| `/api/v1/usuarios/registro/` | POST | Público | NUEVO |

## 🧪 Cómo Probarlo
1. Ejecutar `python manage.py test rassa.tests -v2`
2. Abrir Bruno y ejecutar `registro.bru`
3. Verificar que retorna 201 con datos válidos
4. Verificar que retorna 400 con datos inválidos

## 📁 Bruno
- [x] Archivo `bruno/usuarios/registro.bru` incluido
- [x] Variables de entorno configuradas
- [x] Request body con ejemplo real
- [x] Headers documentados

## 🔐 Permisos RBAC
| Endpoint | Permiso | Rol |
|----------|---------|-----|
| `POST /api/v1/usuarios/registro/` | Sin permiso | Público |

## ✅ Checklist
- [x] `python manage.py test rassa.tests -v2` pasa
- [x] `python manage.py check --deploy` pasa
- [x] No hay print() olvidados
- [x] Rama actualizada con main
- [x] Serializers con errores en español
- [x] Permisos RBAC documentados
- [x] Archivos Bruno incluidos
```

---

## 📌 Resumen

| # | Requisito | Obligatorio |
|---|-----------|:-----------:|
| 1 | Rama `tipo/descripcion` | ✅ |
| 2 | PR con título imperative mood | ✅ |
| 3 | Commits atómicos y descriptivos | ✅ |
| 4 | Template completo en descripción | ✅ |
| 5 | Tests pasando antes de pedir review | ✅ |
| 6 | Responder TODOS los comments | ✅ |
| 7 | Serializers con errores en español | ✅ |
| 8 | Permisos RBAC documentados | ✅ |
| 9 | Archivos Bruno para endpoints nuevos | ✅ |
| 10 | Migraciones incluidas (si aplica) | ✅ |
| 11 | PR con scope acotado | ✅ |
