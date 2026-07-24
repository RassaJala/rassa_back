"""Retry deleting orphaned Google Drive files for images marked as pending cleanup.

Usage:
    python manage.py cleanup_orphan_drive_files          # show what would be cleaned
    python manage.py cleanup_orphan_drive_files --delete  # actually delete
"""

import logging

from django.core.management.base import BaseCommand
from googleapiclient.errors import HttpError

from rassa.models import ProductoImagen
from rassa.services.google_drive import delete_file

logger = logging.getLogger(__name__)

# HTTP 404: file already deleted on Drive — treat as success for cleanup.
_NOT_FOUND = 404


class Command(BaseCommand):
    help = "Retry deleting orphaned Google Drive files for images marked as pending cleanup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Actually delete files. Without this flag, only shows what would be cleaned.",
        )

    def handle(self, *args, **options):
        dry_run = not options["delete"]
        pending = ProductoImagen.objects.filter(eliminar_pendiente=True)

        count = pending.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("No pending orphan files to clean up."))
            return

        mode = "DRY RUN" if dry_run else "EXECUTING"
        self.stdout.write(f"[{mode}] Found {count} image(s) pending Drive cleanup:\n")

        deleted = 0
        failed = 0

        for imagen in pending:
            file_id = imagen.drive_file_id
            self.stdout.write(f"  - Image #{imagen.id_imagen} (product #{imagen.fk_producto_id}) file_id={file_id}")

            if dry_run:
                continue

            try:
                if file_id:
                    delete_file(file_id)
                imagen.delete()
                deleted += 1
                self.stdout.write(self.style.SUCCESS("    Deleted ✓"))
            except HttpError as exc:
                status_code = getattr(exc.resp, "status", None)
                if status_code == _NOT_FOUND:
                    # File already gone from Drive — clean up the DB record anyway.
                    imagen.delete()
                    deleted += 1
                    self.stdout.write(self.style.SUCCESS("    Deleted ✓ (file already gone from Drive)"))
                else:
                    failed += 1
                    logger.warning("Cleanup failed for image %s (file_id=%s): %s", imagen.id_imagen, file_id, exc)
                    self.stdout.write(self.style.WARNING(f"    Failed: {exc}"))
            except Exception as exc:
                failed += 1
                logger.warning("Cleanup failed for image %s (file_id=%s): %s", imagen.id_imagen, file_id, exc)
                self.stdout.write(self.style.WARNING(f"    Failed: {exc}"))

        if dry_run:
            self.stdout.write(f"\nRun with --delete to actually clean up {count} file(s).")
        else:
            self.stdout.write(self.style.SUCCESS(f"\nDone: {deleted} deleted, {failed} failed."))
