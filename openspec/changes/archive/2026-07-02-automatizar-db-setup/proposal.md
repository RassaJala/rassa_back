# Proposal: Automatizar Setup de Base de Datos

## Intent

Reemplazar el onboarding manual de 5-6 pasos con **un solo comando** (`bash setup.sh`) que detecte el entorno, instale todo lo necesario, maneje errores con mensajes claros, y al finalizar verifique que el proyecto arranca. Si algo falla en el camino, el script debe reportar exactamente qué falló y por qué, sin dejar al desarrollador adivinando.

Los modelos ORM viejos/incompletos de 4 apps se eliminan porque `rassa_jala.sql` (fuente de verdad confirmada) los reemplaza por completo.

## Scope

### In Scope

**`setup.sh` — Script de orquestación inteligente**, fases en orden:

| Fase | Qué hace | Manejo de errores |
|------|----------|-------------------|
| 1. Detección de Python | Detecta versiones instaladas. Si hay varias, ofrece 3 opciones: (a) elegir una manualmente, (b) eliminar todas e instalar la más reciente, (c) cancelar. Si la versión es vieja pero compatible (≥3.11), pregunta si actualizar. Si no hay Python, da instrucciones para instalarlo. | ❌ Sale con mensaje claro si no hay Python compatible |
| 2. Entorno virtual | Crea `venv/` con la versión de Python elegida. Si ya existe, pregunta si recrearlo. | ❌ Reporta el error de `venv` |
| 3. Dependencias | `pip install -r requirements.txt`. Verifica que cada paquete se instaló. | ❌ Muestra qué paquete falló y el error de pip |
| 4. PostgreSQL | Verifica si PostgreSQL está instalado y corriendo. Si no, da instrucciones específicas por SO. Crea la base de datos `rassa`. | ❌ Sale si `pg_isready` falla, muestra cómo instalar |
| 5. Variables de entorno | Crea `.env` desde template si no existe. Valida que `SECRET_KEY` y `DATABASE_URL` estén presentes. | ⚠️ Advierte si faltan variables, usa defaults seguros |
| 6. Migraciones Django | `python manage.py migrate` para tablas de sistema (auth, sessions, admin). | ❌ Reporta errores de migración |
| 7. Carga de schema SQL | `python manage.py load_rassa_schema` — ejecuta `db/rassa_jala.sql` con las 32 tablas + seeders. | ❌ Reporta línea específica del SQL que falló |
| 8. Verificación final | Intenta `python manage.py check --deploy` y opcionalmente `runserver` (breve). | ✅ "Todo listo" o ❌ "No arranca: [razón]" |

**Otros entregables:**
- `db/rassa_jala.sql` — movido y renombrado desde raíz del proyecto
- Management command `load_rassa_schema` — ejecuta el SQL vía `connection.cursor()` con soporte para `--reset` (DROP + recreate) y `--dry-run` (validar sin ejecutar)
- `.env.template` — template documentado con defaults para desarrollo
- `.env` actualizado — default a PostgreSQL
- Eliminar 4 apps obsoletas: `apps/accounts`, `apps/products`, `apps/orders`, `apps/categories` y sus referencias en `settings.py`
- Actualizar `README.md` — nuevo flujo: clonar → `bash setup.sh` → listo

### Out of Scope
- Generar modelos Django a partir de las 32 tablas SQL (posible con `inspectdb` en fase futura)
- Docker / docker-compose
- CI/CD pipeline
- Soporte para Windows (primera versión: Linux/macOS)

## Capabilities

### New Capabilities
- `db-automation`: Carga de esquema SQL + seeders vía management command con soporte `--reset`
- `dev-environment-setup`: Orquestación one-command del entorno de desarrollo completo

### Modified Capabilities
None — `openspec/specs/` está vacío. No hay specs existentes que modificar.

## Approach

**Combinado**: `setup.sh` orquesta el entorno (venv → pip → PostgreSQL DB creation → migrate → load_rassa_schema). El management command carga el SQL directamente con `psycopg2` cursor, ejecutando el archivo entero en una transacción. PostgreSQL es ahora requerido para desarrollo (no más SQLite, consistente con el SQL que usa SERIAL, INET, CHECK, funciones PL/pgSQL).

**¿Por qué no hook en pip?** Pip no tiene post-install hooks. La alternativa más cercana es un script de orquestación.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `rassa_jala.sql` → `db/rassa_jala.sql` | Moved | Reubicado a directorio `db/` |
| `db/` | New | Directorio para artefactos de base de datos |
| `setup.sh` | New | Script de orquestación del entorno |
| `apps/accounts/` | Removed | modelos Django viejos/incompletos |
| `apps/products/` | Removed | ídem |
| `apps/orders/` | Removed | ídem |
| `apps/categories/` | Removed | ídem |
| `rassa/settings.py` | Modified | Eliminar LOCAL_APPS, quitar AUTH_USER_MODEL |
| `.env` | Modified | Default DATABASE_URL → PostgreSQL |
| `README.md` | Modified | Nuevo flujo de onboarding |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Usuario tiene múltiples versiones de Python y no sabe cuál elegir | Medium | El script lista todas, recomienda la más reciente ≥3.11, pregunta antes de actuar |
| PostgreSQL no está instalado | High | `setup.sh` verifica `pg_isready` y da instrucciones por SO (apt, brew, etc.) |
| App rota sin modelos Django de negocio | High | Mantener `django.contrib.auth` para admin; las apps de negocio se recrearán con `inspectdb` en fase siguiente |
| Pérdida de migraciones existentes | Low | Archivar migraciones viejas en `db/migrations_archive/` antes de eliminarlas |
| El script falla a mitad de camino y deja estado inconsistente | Medium | Cada fase es idempotente o detecta estado previo. El script informa en qué fase falló y cómo retomar. |
| macOS vs Linux diferencias en comandos de sistema | Low | Detectar SO al inicio y adaptar comandos (`apt` vs `brew`, paths de PostgreSQL) |
| Variables de entorno sensibles en `.env.template` | Low | Template usa placeholders (`changeme`), nunca valores reales |

## Rollback Plan

1. Revertir `settings.py` a restaurar LOCAL_APPS y AUTH_USER_MODEL
2. Restaurar apps desde git (`git checkout apps/`)
3. Volver `.env` a `DATABASE_URL=sqlite:///db.sqlite3`

## Dependencies

- PostgreSQL ≥ 14 instalado localmente (requisito nuevo para dev)
- `psycopg2-binary` ya está en `requirements.txt`

## Success Criteria

- [ ] `bash setup.sh` completa sin errores en máquina limpia (Linux, Python 3.11+, PostgreSQL)
- [ ] Si el usuario tiene Python 3.9, el script advierte "versión no soportada" y sale con instrucciones
- [ ] Si el usuario tiene Python 3.11 y 3.14, el script ofrece: elegir una, eliminar todas e instalar la más reciente, o cancelar
- [ ] Si PostgreSQL no está instalado, el script muestra instrucciones de instalación según el SO
- [ ] `python manage.py load_rassa_schema --reset` recrea las 32 tablas + seeders
- [ ] `python manage.py load_rassa_schema --dry-run` valida el SQL sin ejecutarlo
- [ ] `python manage.py dbshell` muestra datos de prueba (12 usuarios, 20 productos, 10 órdenes)
- [ ] `python manage.py check --deploy` pasa sin warnings
- [ ] `python manage.py runserver` arranca y responde en `http://localhost:8000/api/`
- [ ] Si algo falla en cualquier fase, el script reporta: qué fase falló, el error exacto, y sugerencia para arreglarlo
- [ ] README refleja el nuevo flujo: clonar → `bash setup.sh` → listo
