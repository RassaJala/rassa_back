# Runbook de Migraciones

## Post-merge: migraciones squash (PR #67)

Al actualizar `main` después del PR #67, **todas las bases de datos existentes** deben ejecutar:

```bash
python manage.py migrate rassa 0007_squash_all_branches --fake
python manage.py migrate
```

### ¿Por qué?

El PR #67 consolidó 21 migraciones individuales (0007–0017) en una sola migración
squash (`0007_squash_all_branches`). En bases de datos existentes que ya tenían
algunas de esas migraciones aplicadas, la squash no puede ejecutar sus operaciones
porque duplicarían cambios ya existentes en el esquema.

`--fake` le indica a Django que registre la squash como aplicada sin ejecutar
sus operaciones, y luego `migrate` aplica las migraciones pendientes posteriores
(como `0008_productoimagen_eliminar_pendiente`).

### Bases de datos nuevas

No requieren `--fake`. Simplemente:

```bash
python manage.py migrate
```

### Verificación

```bash
python manage.py showmigrations rassa
```

Debe mostrar `[X]` en todas las migraciones listadas (0001–0008).

### Rollback

Si es necesario revertir el squash en una base existente:

```bash
python manage.py migrate rassa 0006_cascade_to_set_null_protect
```

Esto revierte `0008_productoimagen_eliminar_pendiente` y la squash en una sola
operación atómica. Las migraciones individuales 0007–0017 ya no existen como
archivos separados, así que el siguiente `migrate` forward requerirá `--fake`
nuevamente.
