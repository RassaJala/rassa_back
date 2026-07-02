# Rassa — Backend

API REST para Rassa, una app mobile de e-commerce donde agricultores venden productos directamente.

## Setup rápido

Un solo comando. Sin pasos manuales. El script detecta tu sistema operativo y se adapta solo.

| Plataforma | Comando |
|---|---|
| **Linux** | `bash setup.sh` |
| **macOS** | `bash setup.sh` |
| **Windows (Git Bash)** | `bash setup.sh` |
| **Windows (WSL)** | `bash setup.sh` |
| **Windows (PowerShell)** | `.\setup.ps1` |

```bash
git clone <repo-url>
cd Rassaback
bash setup.sh      # Linux / macOS / Windows (Git Bash o WSL)
# .\setup.ps1      # Windows (PowerShell nativo)
```

El script instala todo lo necesario y te avisa si algo falta. Al terminar:

```bash
source venv/bin/activate        # Linux / macOS / Git Bash
# venv\Scripts\activate         # Windows CMD
# .\venv\Scripts\Activate.ps1   # Windows PowerShell
python manage.py runserver
```

La API responde en `http://localhost:8000/api/`.

## Stack

| Componente | Tecnología |
|------------|-----------|
| Framework | Django 5.0 + Django REST Framework |
| Base de datos | PostgreSQL |
| Auth | JWT (SimpleJWT) — mensajes de error en español |
| Python | 3.11+ |

## Requisitos previos

El script verifica y ayuda a instalar lo que falte:

- **Python 3.11+** — si no está, el script muestra cómo instalarlo según tu SO
- **PostgreSQL** — ídem: `apt` en Linux, `brew` en macOS, instalador oficial en Windows

No necesitás instalar nada manualmente. El script te guía.

## Qué hace el script — 8 fases

Cada fase se ejecuta una sola vez. Si algo falla, el script te dice exactamente qué pasó y cómo arreglarlo.

| Fase | Descripción | Si falla |
|------|-------------|----------|
| 1. Python | Detecta versiones. Si hay varias, menú interactivo: elegir una, instalar la más reciente, o cancelar. | Muestra cómo instalar Python en tu SO |
| 2. Entorno virtual | Crea `venv/`. Si ya existe, pregunta si recrearlo. | Reporta el error de `venv` |
| 3. Dependencias | `pip install -r requirements.txt` con verificación por paquete. | Indica qué paquete falló |
| 4. PostgreSQL | Detecta si está instalado y corriendo. Crea la base de datos `rassa`. | Instrucciones de instalación según SO |
| 5. Variables de entorno | Crea `.env` desde `.env.template`. Valida `SECRET_KEY` y `DATABASE_URL`. | Advierte variables faltantes |
| 6. Migraciones | `python manage.py migrate` para tablas del sistema Django. | Reporta errores de migración |
| 7. Esquema SQL | `python manage.py load_rassa_schema` — 32 tablas + datos de prueba. | Reporta línea exacta del error SQL |
| 8. Verificación | `python manage.py check --deploy` y prueba de arranque. | Dice exactamente por qué no arranca |

### Re-ejecución segura

Cada fase guarda su estado en `.setup_state`. Si volvés a correr el script, las fases ya completadas se saltean.

```bash
bash setup.sh           # solo ejecuta lo que falta
bash setup.sh --reset   # ignora el estado y ejecuta todo de nuevo
```

El log completo queda en `setup.log`.

## Comando `load_rassa_schema`

Carga el esquema SQL completo (32 tablas + seeders de prueba) en PostgreSQL.

```bash
python manage.py load_rassa_schema          # carga normal (idempotente)
python manage.py load_rassa_schema --reset  # borra todo y recrea desde cero
python manage.py load_rassa_schema --dry-run # valida el SQL sin tocar la base de datos
```

## Verificación rápida

Después del setup, confirmá que todo funciona:

- [ ] `python manage.py check` — sin errores
- [ ] `python manage.py test` — tests pasan
- [ ] `python manage.py runserver` — arranca en `http://localhost:8000/api/`
- [ ] `python manage.py dbshell` — hay datos de prueba (12 usuarios, 20 productos, 10 órdenes)

## Estructura del proyecto

```
Rassaback/
├── rassa/                       # Configuración Django
│   ├── settings.py
│   ├── urls.py
│   ├── auth_serializers.py      # JWT con mensajes en español
│   ├── auth_views.py
│   ├── management/commands/
│   │   └── load_rassa_schema.py # Comando de carga SQL
│   └── tests/
├── db/
│   ├── rassa_jala.sql           # 32 tablas + seeders
│   └── migrations_archive/      # Migraciones viejas (respaldo)
├── scripts/
│   └── test_setup_helpers.sh    # Tests del script de setup
├── setup.sh                     # Setup automático (Linux / macOS / Git Bash / WSL)
├── setup.ps1                    # Setup automático (Windows PowerShell)
├── .env.template                # Template de variables de entorno
├── requirements.txt
└── manage.py
```

## Otros comandos

```bash
python manage.py test             # Ejecutar tests
python manage.py createsuperuser  # Crear superusuario admin
python manage.py shell            # Shell interactivo de Django
python manage.py check --deploy   # Verificar configuración de producción
```
