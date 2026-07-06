# Rassa — Backend

API REST para Rassa, una aplicación móvil de e-commerce donde agricultores venden productos directamente.

## Stack

- **Django 5** + **Django REST Framework**
- **PostgreSQL**
- **JWT Auth** (SimpleJWT)
- Python 3.12+

## Inicio rápido

### Usar el script de setup (recomendado)

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

El script detecta Python, crea el entorno virtual, instala dependencias, configura PostgreSQL, genera la SECRET_KEY, ejecuta migraciones y carga los datos de prueba.

> **Nota para Windows:** Si el script no encuentra Python, prueba con `py` en vez de `python`. El Python Launcher (`py.exe`) encuentra todas las instalaciones sin importar el PATH.

### Iniciar el servidor

**Linux / macOS / Git Bash / WSL:**

```bash
bash start.sh
```

**Windows (PowerShell):**

```powershell
.\start.ps1
```

El script ejecuta todos los tests automáticamente. Si pasan, inicia el servidor. Si fallan, muestra el error con una explicación y NO inicia el servidor.

> **Importante:** usa siempre `start.sh` / `start.ps1` para iniciar el backend. Si ejecutas `python manage.py runserver` directamente, los tests no se ejecutan y puedes enviar código con errores.

## Instalación manual paso a paso

Si el script de setup no funciona en tu sistema, sigue estos pasos para configurar el proyecto manualmente.

### Requisitos previos

- Python 3.12 o superior
- PostgreSQL instalado y corriendo (puerto 5432)
- Git

### 1. Clonar el repositorio

```bash
git clone https://github.com/ObedAlPa/rassa_back.git
cd rassa_back
```

### 2. Crear y activar el entorno virtual

**Linux / macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Git Bash):**

```bash
python -m venv venv
source venv/Scripts/activate
```

> **Nota:** si `python` no funciona en Windows, usa el Python Launcher:
> ```powershell
> py -m venv venv
> .\venv\Scripts\Activate.ps1
> ```

### 3. Instalar dependencias

Con el entorno virtual activo:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 4. Configurar variables de entorno

Crea un archivo `.env` en la raíz del proyecto con el siguiente contenido:

```
SECRET_KEY=django-insecure-<reemplazar con una clave única>
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:8081,http://localhost:19006
DATABASE_URL=postgres://postgres:contraseña@localhost:5432/rassa_jala_db
```

Para generar una SECRET_KEY automáticamente:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Crear la base de datos

```bash
psql -U postgres -c "CREATE DATABASE rassa_jala_db;"
```

### 6. Ejecutar migraciones y cargar datos de prueba

```bash
python manage.py migrate
python manage.py seed_rassa_data
```

### 7. Verificar la instalación

```bash
python manage.py check --deploy
```

### 8. Iniciar el servidor

```bash
python manage.py runserver
```

La API estará disponible en http://localhost:8000/api/

## Comandos disponibles

| Acción | Linux / macOS / Git Bash | Windows (PowerShell) |
| ------ | ------------------------ | -------------------- |
| Iniciar backend (tests + server) | `bash start.sh` | `.\start.ps1` |
| Solo ejecutar tests | `bash start.sh --test` | `.\start.ps1 -TestOnly` |
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

- [ ] `bash setup.sh` / `.\setup.ps1` se ejecuta sin errores
- [ ] `bash start.sh` / `.\start.ps1` inicia el servidor
- [ ] Los tests pasan antes de que el servidor se inicie
- [ ] `http://localhost:8000/api/` responde
- [ ] Puedes iniciar sesión con `admin@rassa.com` / `admin123`

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
├── start.sh                        # Iniciar backend (Linux/macOS/Git Bash)
├── start.ps1                       # Iniciar backend (PowerShell)
├── .env.template
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
└── manage.py
```
