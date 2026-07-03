# Rassa — Backend

API REST para Rassa, una app mobile de e-commerce donde agricultores venden productos directamente.

## Stack

- **Django 5** + **Django REST Framework**
- **PostgreSQL**
- **JWT Auth** (SimpleJWT)
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) o pip para gestión de dependencias

## Requisitos

- Python 3.12 o superior
- PostgreSQL

## Instalación

### Opción rápida — Script interactivo

Un solo comando. El script detecta tu sistema operativo y te guía paso a paso:

| Plataforma               | Comando         |
| ------------------------ | --------------- |
| **Linux**                | `bash setup.sh` |
| **macOS**                | `bash setup.sh` |
| **Windows (Git Bash)**   | `bash setup.sh` |
| **Windows (WSL)**        | `bash setup.sh` |
| **Windows (PowerShell)** | `.\setup.ps1`   |

```bash
git clone <repo-url>
cd Rassaback
bash setup.sh      # Linux / macOS / Windows (Git Bash / WSL)
# .\setup.ps1      # Windows (PowerShell)
```

El script pregunta:

1. Versión de Python a usar
2. Gestor de dependencias (pip o uv)
3. Configuración de PostgreSQL (host, puerto, DB, usuario, contraseña)
4. Genera SECRET_KEY automáticamente
5. Crea la base de datos si no existe
6. Ejecuta migraciones y seeds

### Instalación manual

### 1. Clonar el repo

**Opción A — Solo backend:**

```bash
gh repo clone ObedAlPa/rassa_back
cd rassa_back
```

**Opción B — Monorepo (backend + frontend):**

```bash
mkdir rassa-monorepo && cd rassa-monorepo
gh repo clone ObedAlPa/rassa_back back
gh repo clone ObedAlPa/rassa_front front
cd back
```

### 2. Instalar dependencias

**Con uv:**

```bash
uv sync
```

**Con pip:**

```bash
python -m venv venv
source venv/bin/activate   # Linux / macOS / Git Bash
# venv\Scripts\activate    # Windows CMD
# .\venv\Scripts\Activate.ps1  # Windows PowerShell
pip install -r requirements.txt
```

**Dependencias de desarrollo (pylint + pylint-django):**

```bash
# uv
uv sync --all-extras

# pip
pip install -r requirements-dev.txt
```

### 3. Configurar PostgreSQL

Crear la base de datos (comando de sugerencia):

```bash
# Linux / macOS / Windows (PowerShell)
psql -h localhost -U postgres -c "CREATE DATABASE rassa_jala_db;"
```

### 4. Configurar variables de entorno

```bash
cp .env.template .env
```

Editar `.env`:

| Variable               | Descripción                  | Ejemplo                                                     |
| ---------------------- | ---------------------------- | ----------------------------------------------------------- |
| `SECRET_KEY`           | Clave secreta de Django      | Generar con el comando abajo                                |
| `DATABASE_URL`         | URL de conexión a PostgreSQL | `postgres://postgres:password@localhost:5432/rassa_jala_db` |
| `DEBUG`                | Modo debug                   | `True` en desarrollo                                        |
| `ALLOWED_HOSTS`        | Hosts permitidos             | `localhost,127.0.0.1`                                       |
| `CORS_ALLOWED_ORIGINS` | Orígenes CORS permitidos     | `http://localhost:8081,http://localhost:19006`              |

Generar `SECRET_KEY`:

```bash
# uv
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# pip
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Ejecutar migraciones y seeders

```bash
# uv
uv run manage.py migrate
uv run manage.py seed_rassa_data

# pip
python manage.py migrate
python manage.py seed_rassa_data
```

### 6. Iniciar el servidor

```bash
# uv
uv run manage.py runserver

# pip
python manage.py runserver
```

La API estará disponible en `http://localhost:8000/api/`.

## Comandos útiles

```bash
# uv
uv run python manage.py migrate
uv run python manage.py seed_rassa_data
uv run python manage.py seed_rassa_data --clear  # limpiar y recargar
uv run python manage.py runserver
uv run python manage.py shell
uv run python manage.py test

# pip (con venv activado)
python manage.py migrate
python manage.py seed_rassa_data
python manage.py runserver
python manage.py shell
python manage.py test
```

## Documentación

| Documento                                                    | Descripción                                        |
| ------------------------------------------------------------ | -------------------------------------------------- |
| [docs/ARQUITECTURA_MODULOS.md](docs/ARQUITECTURA_MODULOS.md) | Arquitectura por módulos, endpoints, permisos RBAC |
| [docs/USUARIOS_PRUEBA.md](docs/USUARIOS_PRUEBA.md)           | Usuarios de prueba, credenciales, catálogos        |

## Usuarios de prueba

| Usuario     | Email                   | Contraseña    | Rol           |
| ----------- | ----------------------- | ------------- | ------------- |
| Admin       | `admin@rassa.com`       | `admin123`    | Administrador |
| Vendedor    | `vendedor@rassa.com`    | `vendedor123` | Vendedor      |
| Juan Pérez  | `juan.perez@email.com`  | `juan123`     | Agricultor    |
| Ana Ramírez | `ana.ramirez@email.com` | `ana123`      | Cliente       |

Ver [docs/USUARIOS_PRUEBA.md](docs/USUARIOS_PRUEBA.md) para la lista completa.

## Estructura del proyecto

```
back/
├── rassa/                          # App principal
│   ├── models.py                   # 32 modelos del dominio
│   ├── urls.py                     # Router principal
│   ├── settings.py                 # Configuración Django
│   ├── auth/                       # Autenticación JWT
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   ├── permissions/                # Permisos RBAC
│   │   └── role_permissions.py
│   └── management/commands/
│       └── seed_rassa_data.py      # Seeder principal
├── db/archive/                     # SQL original (respaldo)
├── docs/
│   ├── ARQUITECTURA_MODULOS.md
│   └── USUARIOS_PRUEBA.md
├── setup.sh                        # Setup interactivo (Linux/macOS/Git Bash)
├── setup.ps1                       # Setup interactivo (PowerShell)
├── .env.template
├── .pylintrc
├── pyproject.toml
├── requirements.txt
└── manage.py
```
