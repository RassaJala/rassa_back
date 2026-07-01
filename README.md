# Rassa — Backend

API REST para Rassa, una app mobile de e-commerce donde agricultores venden productos directamente.

## Stack

- **Django 5** + **Django REST Framework**
- **PostgreSQL**
- **JWT Auth** (SimpleJWT)
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) para gestión de dependencias

## Requisitos

- Python 3.12 o superior
- PostgreSQL
- [uv](https://docs.astral.sh/uv/) (opcional, recomendado) o pip

## Instalación

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

### 2. Instalar uv (si no lo tienes)

[uv docs](https://docs.astral.sh/uv/getting-started/installation/#installation-methods)

### 3. Instalar dependencias

```bash
# Con uv (recomendado) — crea el venv automáticamente
uv sync

# O con pip
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Crear un archivo `.env` en la raíz del proyecto:

```bash
# Generar una SECRET_KEY segura
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copiar la clave generada y crear el `.env`:

```env
SECRET_KEY=<la-clave-generada>
DEBUG=True
DATABASE_URL=postgres://usuario:password@localhost:5432/rassa

CORS_ALLOWED_ORIGINS=http://localhost:8081,http://localhost:19006
```

### 5. Configurar PostgreSQL

> **IMPORTANTE**: SQLite no soporta todo el esquema de PostgreSQL. Se recomienda usar PostgreSQL incluso en desarrollo.

```bash
# Actualizar DATABASE_URL en .env
DATABASE_URL=postgres://usuario:password@localhost:5432/rassa
```

## Ejecutar

```bash
# Aplicar migraciones
uv run manage.py migrate

# Aplicar seeders si existen
uv run manage.py seed

# Iniciar servidor de desarrollo
uv run manage.py runserver
```

> Con pip (venv activado): reemplazar `uv run python` por `python`.

La API arranca en `http://localhost:8000/api/`.

## Comandos útiles

```bash
# Crear migraciones después de cambiar modelos
uv run python manage.py makemigrations

# Abrir shell de Django
uv run python manage.py shell

# Correr tests
uv run python manage.py test
```

## Estructura

```
rassa_back/
├── rassa/              # Configuración del proyecto
│   ├── settings.py
│   ├── urls.py         # Rutas principales
│   └── ...
├── apps/
│   ├── accounts/       # Usuarios, roles, auth
│   ├── products/       # Productos de agricultores
│   ├── orders/         # Órdenes de compra
│   └── categories/     # Categorías de productos
├── manage.py
├── pyproject.toml      # Dependencias y config del proyecto
└── requirements.txt    # Dependencias (fallback para pip)
```
