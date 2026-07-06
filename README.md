# Rassa — Backend

API REST para Rassa, una app móvil de e-commerce donde agricultores venden productos directamente.

## Stack

- **Django 5** + **Django REST Framework**
- **PostgreSQL**
- **JWT Auth** (SimpleJWT)
- Python 3.12+

## Requisitos

- Python 3.12 o superior
- PostgreSQL

## Inicio rápido

### 1. Clonar y configurar

**Linux / macOS / Git Bash / WSL:**

```bash
git clone https://github.com/ObedAlPa/rassa_back.git
cd rassa_back
bash setup.sh
```

**Windows (PowerShell):**

```powershell
git clone https://github.com/ObedAlPa/rassa_back.git
cd rassa_back
.\setup.ps1
```

El script detecta Python, crea el entorno virtual, instala dependencias, configura PostgreSQL, genera SECRET_KEY, ejecuta migraciones y carga datos de prueba.

### 2. Levantar el backend

**Linux / macOS / Git Bash / WSL:**

```bash
bash start.sh
```

**Windows (PowerShell):**

```powershell
.\start.ps1
```

¿Qué hace? Ejecuta todos los tests automáticamente. Si pasan, levanta el servidor. Si fallan, muestra el error con explicación y NO levanta el servidor.

> **IMPORTANTE:** Usa siempre `start.sh` / `start.ps1` para levantar el backend. Si ejecutas `python manage.py runserver` directamente, no se corren los tests y puedes subir código con errores.

## Comandos disponibles

| Acción | Linux / macOS / Git Bash | Windows (PowerShell) |
| ------ | ------------------------ | -------------------- |
| Levantar backend (tests + server) | `bash start.sh` | `.\start.ps1` |
| Solo correr tests | `bash start.sh --test` | `.\start.ps1 -TestOnly` |
| Tests con máximo detalle | `bash start.sh --verbose` | `.\start.ps1 -Verbose` |
| Tests + máximo detalle | `bash start.sh --test --verbose` | `.\start.ps1 -TestOnly -Verbose` |
| Saltar tests (emergencias) | `bash start.sh --skip` | `.\start.ps1 -Skip` |
| Ejecutar migraciones | `python manage.py migrate` | `python manage.py migrate` |
| Cargar datos de prueba | `python manage.py seed_rassa_data` | `python manage.py seed_rassa_data` |
| Limpiar y recargar datos | `python manage.py seed_rassa_data --clear` | `python manage.py seed_rassa_data --clear` |
| Shell de Django | `python manage.py shell` | `python manage.py shell` |

## Variables de entorno

Se configuran en el archivo `.env` (creado por `setup.sh` / `setup.ps1`).

| Variable | Descripción | Ejemplo |
| -------- | ----------- | ------- |
| `SECRET_KEY` | Clave secreta de Django (generada automáticamente) | `django-insecure-abc...` |
| `DEBUG` | Modo debug (solo `True` en desarrollo) | `True` |
| `DATABASE_URL` | URL de conexión a PostgreSQL | `postgres://user:pass@localhost:5432/db` |
| `ALLOWED_HOSTS` | Hosts permitidos | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | Orígenes permitidos para CORS | `http://localhost:5173` |

## Usuarios de prueba

| Usuario | Email | Contraseña | Rol |
| ------- | ----- | ---------- | --- |
| Admin | `admin@rassa.com` | `admin123` | Administrador |
| Vendedor | `vendedor@rassa.com` | `vendedor123` | Vendedor |
| Juan Pérez | `juan.perez@email.com` | `juan123` | Agricultor |
| Ana Ramírez | `ana.ramirez@email.com` | `ana123` | Cliente |

## Checklist de verificación

- [ ] `bash setup.sh` / `.\setup.ps1` ejecuta sin errores
- [ ] `bash start.sh` / `.\start.ps1` levanta el servidor
- [ ] Los tests pasan antes de que el servidor se levante
- [ ] `http://localhost:8000/api/` responde
- [ ] Puedes login con `admin@rassa.com` / `admin123`

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
├── setup.sh                        # Setup (Linux/macOS/Git Bash)
├── setup.ps1                       # Setup (PowerShell)
├── start.sh                        # Levantar backend (Linux/macOS/Git Bash)
├── start.ps1                       # Levantar backend (PowerShell)
├── .env.template
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
└── manage.py
```
