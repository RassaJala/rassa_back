# Rassa — Backend

API REST para Rassa, una app mobile de e-commerce donde agricultores venden productos directamente.

## Stack

- **Django 5** + **Django REST Framework**
- **PostgreSQL**
- **JWT Auth** (SimpleJWT)
- Python 3.11+

## Requisitos

- Python 3.11 o superior
- PostgreSQL (o SQLite para desarrollo local sin instalar nada)

## Instalación

```bash
# 1. Clonar el repo (si no lo hiciste)
git clone <repo-url>
cd Rassaback

# 2. Crear y activar entorno virtual
python -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows

# 3. Instalar dependencias
pip install -r requirements.txt
```

## Configuración

Crear un archivo `.env` en la raíz del proyecto:

```env
SECRET_KEY=una-clave-segura-acá
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3

# Para PostgreSQL:
# DATABASE_URL=postgres://usuario:password@localhost:5432/rassa

CORS_ALLOWED_ORIGINS=http://localhost:8081,http://localhost:19006
```

> **Tips**: En desarrollo podés usar SQLite (`sqlite:///db.sqlite3`) sin instalar PostgreSQL. En producción usá PostgreSQL.

## Ejecutar

```bash
# Aplicar migraciones
python manage.py migrate

# Crear superusuario
python manage.py createsuperuser

# Iniciar servidor de desarrollo
python manage.py runserver
```

La API arranca en `http://localhost:8000/api/`.

## Comandos útiles

```bash
# Crear migraciones después de cambiar modelos
python manage.py makemigrations

# Abrir shell de Django
python manage.py shell

# Correr tests
python manage.py test
```

## Estructura

```
Rassaback/
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
└── requirements.txt
```
