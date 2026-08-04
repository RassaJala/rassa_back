"""Management command para sanear nombres de archivos adjuntos de chat.

Los nombres subidos desde la app móvil llegan con `%20`/caracteres especiales
codificados (React Native deja `%20` literal en disco, p. ej.
`documentos/{uuid}_listen%20before%20i%20go.mp3`). Como los servidores WSGI
decodifican el PATH_INFO, la URL construida con `%20` nunca coincide con el
archivo en disco -> 404 al cargar el adjunto.

Este comando renombra los archivos a un nombre seguro (`[A-Za-z0-9._-]`) y
actualiza `url_documento` en la base de datos para que vuelvan a cargar.

Ejecuta:
    python manage.py sanitizar_documentos
    python manage.py sanitizar_documentos --dry-run
"""

import os
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from rassa.models import Documento

UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
UUID_PREFIX = re.compile(r"^[0-9a-f]{32}_")


def sanitize_filename(name: str) -> str:
    """Devuelve un nombre seguro (misma regla que el frontend `sanitizeFileName`).

    Preserva el prefijo uuid de 32 hex (que ya es seguro) y solo sane/acota el
    resto del nombre para no truncar la parte legible.
    """
    name = os.path.basename(name)
    ext_match = re.search(r"\.[A-Za-z0-9]+$", name)
    ext = ext_match.group(0).lower() if ext_match else ""
    base = name[: -len(ext)] if ext else name
    prefix = ""
    uuid_match = UUID_PREFIX.match(base)
    if uuid_match:
        prefix = uuid_match.group(0)
        base = base[uuid_match.end() :]
    base = UNSAFE_CHARS.sub("_", base)
    base = re.sub(r"_+", "_", base)
    base = base.strip("._-")
    base = base[:60]
    return f"{prefix}{base or 'archivo'}{ext}"


class Command(BaseCommand):
    help = "Renombra adjuntos de chat con nombres inseguros y actualiza url_documento."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra los cambios sin renombrar archivos ni tocar la base de datos.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        docs_dir = Path(settings.MEDIA_ROOT) / "documentos"
        if not docs_dir.is_dir():
            self.stderr.write(self.style.ERROR(f"No existe el directorio {docs_dir}"))
            return

        if dry_run:
            self.stdout.write(self.style.NOTICE("Dry-run. Cambios que se aplicarían:"))
        else:
            self.stdout.write(self.style.NOTICE("Renombrando adjuntos..."))

        changed = 0
        skipped = 0
        for doc in Documento.objects.filter(url_documento__startswith="documentos/"):
            old_rel = doc.url_documento
            old_name = Path(old_rel).name
            new_name = sanitize_filename(old_name)
            if new_name == old_name:
                continue

            old_path = docs_dir / old_name
            new_path = docs_dir / new_name
            if not old_path.is_file():
                self.stdout.write(self.style.WARNING(f"Falta archivo en disco: {old_rel}"))
                skipped += 1
                continue
            if new_path.exists():
                self.stdout.write(self.style.WARNING(f"Destino ya existe: {new_name}"))
                skipped += 1
                continue

            message = f"{old_name} -> {new_name}"
            if dry_run:
                self.stdout.write(message)
            else:
                # El orden importa: primero disco, luego DB. Si el proceso muere
                # entre rename y save, el archivo queda con nombre nuevo pero la
                # DB apunta al viejo. Usar --dry-run para validar antes de ejecutar.
                os.rename(old_path, new_path)
                doc.url_documento = f"documentos/{new_name}"
                doc.save(update_fields=["url_documento"])
                self.stdout.write(self.style.SUCCESS(message))
            changed += 1

        summary_style = self.style.NOTICE if dry_run else self.style.SUCCESS
        self.stdout.write(
            summary_style(f"\n{changed} adjuntos {('a renombrar' if dry_run else 'renombrados')}, {skipped} omitidos.")
        )
