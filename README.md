# Rassa — Backend

API REST para Rassa, una app móvil de e-commerce donde agricultores venden productos directamente.

## Stack

- **Django 5** + **Django REST Framework**
- **PostgreSQL**
- **JWT Auth** (SimpleJWT)
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) o pip para gestión de dependencias

## Requisitos

- Python 3.12 o superior
- PostgreSQL

## Inicio rápido (2 comandos)

### 1. Clonar y configurar

```bash
git clone https://github.com/ObedAlPa/rassa_back.git
cd rassa_back
bash setup.sh      # Linux / macOS / Git Bash / WSL
# .\setup.ps1     # Windows (PowerShell)
```

El script te guía paso a paso: detecta Python, crea el entorno virtual, instala dependencias, configura PostgreSQL, genera SECRET_KEY, ejecuta migraciones y carga datos de prueba.

### 2. Iniciar el backend

```bash
bash start.sh      # Linux / macOS / Git Bash / WSL
# .\start.ps1     # Windows (PowerShell)
```

**¿Qué hace `start.sh`?**

1. Ejecuta TODOS los tests automáticamente
2. Si **pasan** → levanta el servidor en `http://localhost:8000/api/`
3. Si **fallan** → muestra el error exacto con explicación y NO levanta el servidor

> **IMPORTANTE:** Usa siempre `bash start.sh` para levantar el backend. Si ejecutas `python manage.py runserver` directamente, no se corren los tests automáticamente y puedes subir código con errores.

## Variables de entorno

Las variables se configuran en el archivo `.env` (creado por `setup.sh`).

| Variable | Descripción | Ejemplo |
| -------- | ----------- | ------- |
| `SECRET_KEY` | Clave secreta de Django (generada automáticamente) | `django-insecure-abc...` |
| `DEBUG` | Modo debug (solo `True` en desarrollo) | `True` |
| `DATABASE_URL` | URL de conexión a PostgreSQL | `postgres://user:pass@localhost:5432/db` |
| `ALLOWED_HOSTS` | Hosts permitidos | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | Orígenes permitidos para CORS | `http://localhost:5173` |

## Comandos

```bash
# Encender el backend (corre tests automáticamente)
bash start.sh

# Solo correr tests (sin levantar server)
bash start.sh --test

# Test con máximo detalle
bash start.sh --verbose

# Gestión de la base de datos
python manage.py migrate
python manage.py seed_rassa_data
python manage.py seed_rassa_data --clear  # limpiar y recargar

# Shell de Django
python manage.py shell
```

## Usuarios de prueba

| Usuario | Email | Contraseña | Rol |
| ------- | ----- | ---------- | --- |
| Admin | `admin@rassa.com` | `admin123` | Administrador |
| Vendedor | `vendedor@rassa.com` | `vendedor123` | Vendedor |
| Juan Pérez | `juan.perez@email.com` | `juan123` | Agricultor |
| Ana Ramírez | `ana.ramirez@email.com` | `ana123` | Cliente |

## Documentación

| Documento | Descripción |
| --------- | ----------- |
| [docs/ARQUITECTURA_MODULOS.md](docs/ARQUITECTURA_MODULOS.md) | Arquitectura por módulos, endpoints, permisos RBAC |
| [docs/USUARIOS_PRUEBA.md](docs/USUARIOS_PRUEBA.md) | Usuarios de prueba, credenciales, catálogos |

## Estructura del proyecto

```
rassa_back/
├── rassa/                          # App principal
│   ├── models.py                   # 32 modelos del dominio
│   ├── urls.py                     # Router principal
│   ├── settings.py                 # Configuración Django
│   ├── auth_views.py               # Autenticación JWT
│   ├── auth_serializers.py         # Serializadores de auth
│   ├── permissions/                # Permisos RBAC
│   │   └── role_permissions.py
│   ├── tests/                      # Tests del proyecto
│   └── management/commands/
│       └── seed_rassa_data.py      # Seeder principal
├── db/archive/                     # SQL original (respaldo)
├── docs/
│   ├── ARQUITECTURA_MODULOS.md
│   └── USUARIOS_PRUEBA.md
├── setup.sh                        # Setup interactivo (Linux/macOS/Git Bash)
├── setup.ps1                       # Setup interactivo (PowerShell)
├── start.sh                        # Iniciar backend con test automático
├── start.ps1                       # Iniciar backend (PowerShell)
├── .env.template
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
└── manage.py
```
