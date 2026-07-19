"""Management command para autorizar el acceso a Google Drive.

Ejecutar: python manage.py authorize_drive

Abre un navegador para que el usuario autorice la app.
Luego guarda el refresh token en el archivo .env.
"""

import os
import sys

from decouple import config
from django.core.management.base import BaseCommand
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# URI de redireccionamiento para el servidor local
REDIRECT_URI = "http://localhost:8090/"


class Command(BaseCommand):
    help = "Autoriza el acceso a Google Drive y guarda el refresh token"

    def handle(self, *args, **options):
        client_id = config("GOOGLE_DRIVE_CLIENT_ID", default="")
        client_secret = config("GOOGLE_DRIVE_CLIENT_SECRET", default="")

        if not client_id or not client_secret:
            self.stderr.write(
                "Error: Configurá GOOGLE_DRIVE_CLIENT_ID y "
                "GOOGLE_DRIVE_CLIENT_SECRET en tu archivo .env"
            )
            return

        # Crear el flujo OAuth2
        flow = InstalledAppFlow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [REDIRECT_URI],
                }
            },
            scopes=SCOPES,
        )

        # Ejecutar el flow localmente
        self.stdout.write(
            "\nSe abrirá tu navegador para autorizar la app.\n"
            "Si no se abre, copiá esta URL y pegala en tu navegador:\n"
        )

        credentials = flow.run_local_server(
            port=8090,
            authorization_prompt_message="Abriendo navegador...",
            success_message="¡Autorización exitosa! Podés cerrar esta pestaña.",
            open_browser=True,
            access_type="offline",
            prompt="consent",
        )

        refresh_token = credentials.refresh_token

        if not refresh_token:
            self.stderr.write("Error: No se obtuvo el refresh token")
            return

        # Guardar en .env
        env_path = os.path.join(os.getcwd(), ".env")

        self._update_env("GOOGLE_DRIVE_REFRESH_TOKEN", refresh_token, env_path)

        self.stdout.write(
            self.style.SUCCESS(
                f"\n¡Listo! Refresh token guardado en .env\n"
                f"Token: {refresh_token[:20]}...\n"
            )
        )

    def _update_env(self, key, value, env_path):
        """Agrega o actualiza una variable en el archivo .env."""
        lines = []
        found = False

        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for i, line in enumerate(lines):
                    if line.strip().startswith(f"{key}="):
                        lines[i] = f"{key}={value}\n"
                        found = True
                        break

        if not found:
            lines.append(f"\n{key}={value}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
