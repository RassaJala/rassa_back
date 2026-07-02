# Rassa — Backend

API REST para Rassa, una app mobile de e-commerce donde agricultores venden productos directamente.

## Setup rápido

Un solo comando configura todo el entorno de desarrollo:

```bash
git clone <repo-url>
cd Rassaback
bash setup.sh
```

El script detecta Python, crea el entorno virtual, instala dependencias, configura PostgreSQL, crea la base de datos `rassa`, ejecuta migraciones, carga el esquema SQL con seeders y verifica que todo funcione.

Al terminar, el proyecto está listo:

```bash
source venv/bin/activate
python manage.py runserver
```

La API responde en `http://localhost:8000/api/`.

## Stack

| Componente | Tecnología |
|------------|-----------|
| Framework | Django 5.0 + Django REST Framework |
| Base de datos | PostgreSQL |
| Auth | JWT (SimpleJWT) |
| Python | 3.11+ |

## Requisitos

- Python 3.11 o superior
- PostgreSQL (el script da instrucciones de instalación si no está)

## Qué hace `setup.sh`

| Fase | Descripción |
|------|-------------|
| 1. Python | Detecta versiones instaladas. Si hay varias, ofrece un menú para elegir. |
| 2. Entorno virtual | Crea `venv/`. Si ya existe, pregunta si recrearlo. |
| 3. Dependencias | `pip install -r requirements.txt` con verificación. |
| 4. PostgreSQL | Verifica `pg_isready`. Si no está instalado, muestra guía de instalación por SO. Crea la base de datos `rassa`. |
| 5. Variables de entorno | Crea `.env` desde `.env.template`. Valida `SECRET_KEY` y `DATABASE_URL`. |
| 6. Migraciones | `python manage.py migrate` para tablas del sistema Django. |
| 7. Esquema SQL | `python manage.py load_rassa_schema` — crea 32 tablas + datos de prueba. |
| 8. Verificación | `python manage.py check --deploy` y prueba de arranque del servidor. |

Cada fase guarda su estado en `.setup_state`. Al re-ejecutar `setup.sh`, las fases completadas se saltean automáticamente.

```bash
bash setup.sh --reset   # ignora el estado y ejecuta todo de nuevo
```

El log completo queda en `setup.log`.

## Comando `load_rassa_schema`

Carga `db/rassa_jala.sql` (32 tablas + seeders) en PostgreSQL:

```bash
python manage.py load_rassa_schema          # carga normal
python manage.py load_rassa_schema --reset  # elimina tablas existentes y las recrea
python manage.py load_rassa_schema --dry-run # valida el SQL sin modificar la base de datos
```

El comando es **idempotente**: re-ejecutarlo sin `--reset` no duplica tablas ni datos.

## Estructura

```
Rassaback/
├── rassa/                  # Configuración del proyecto Django
│   ├── settings.py
│   ├── urls.py
│   ├── auth_serializers.py # Serializadores JWT con mensajes en español
│   ├── auth_views.py       # Vistas de autenticación
│   ├── management/
│   │   └── commands/
│   │       └── load_rassa_schema.py  # Comando de carga de esquema SQL
│   └── tests/
├── db/
│   ├── rassa_jala.sql       # Esquema SQL: 32 tablas + seeders
│   └── migrations_archive/  # Migraciones viejas archivadas
├── setup.sh                 # Script de configuración one-command
├── .env.template            # Template de variables de entorno
├── requirements.txt
└── manage.py
```

## Otros comandos

```bash
# Ejecutar tests
python manage.py test

# Crear superusuario
python manage.py createsuperuser

# Shell de Django
python manage.py shell

# Ver configuración de despliegue
python manage.py check --deploy
```
