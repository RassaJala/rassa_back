"""Management command para autorizar el acceso a Google Drive.

Ejecutar: python manage.py authorize_drive

Abre un navegador para que el usuario autorice la app.
Luego guarda el refresh token en el archivo .env.

Requiere que las siguientes variables estén en .env:
- GOOGLE_DRIVE_CLIENT_ID
- GOOGLE_DRIVE_CLIENT_SECRET

Pasos:
1. Crear credenciales OAuth2 en Google Cloud Console
2. Ejecutar este comando
3. Autorizar en el navegador
4. El refresh token se guarda automáticamente
"""

import os

from decouple import config
from django.core.management.base import BaseCommand
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

REDIRECT_URI = "http://localhost:8090/"


class Command(BaseCommand):
    """Command para autorizar el acceso a Google Drive mediante OAuth2.

    Guía al usuario a través del flujo de autorización OAuth2,
    obtiene el refresh token y lo guarda en el archivo .env.
    """

    help = "Autoriza el acceso a Google Drive y guarda el refresh token"

    def handle(self, *args, **options):
        """Ejecuta el flujo de autorización OAuth2 con Google Drive."""
        client_id = config("GOOGLE_DRIVE_CLIENT_ID", default="")
        client_secret = config("GOOGLE_DRIVE_CLIENT_SECRET", default="")

        if not client_id or not client_secret:
            self.stderr.write(
                self.style.ERROR(
                    "Error: Faltan credenciales OAuth2 en .env.\n"
                    "Configurá GOOGLE_DRIVE_CLIENT_ID y GOOGLE_DRIVE_CLIENT_SECRET\n"
                    "Guía: https://console.cloud.google.com/apis/credentials"
                )
            )
            return

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

        self.stdout.write(
            "\nSe abrirá tu navegador para autorizar la app.\n"
            "Si no se abre, copiá esta URL y pegala en tu navegador:\n"
        )

        try:
            credentials = flow.run_local_server(
                port=8090,
                authorization_prompt_message="Abriendo navegador...",
                success_message="¡Autorización exitosa! Podés cerrar esta pestaña.",
                open_browser=True,
                access_type="offline",
                prompt="consent",
            )
        except Exception as exc:
            self.stderr.write(
                self.style.ERROR(
                    f"Error durante la autorización: {exc}\n"
                    "Verificá que:\n"
                    "1. Tengas acceso a internet\n"
                    "2. El puerto 8090 no esté en uso\n"
                    "3. Autorizaste la app en el navegador"
                )
            )
            return

        refresh_token = credentials.refresh_token

        if not refresh_token:
            self.stderr.write(
                self.style.ERROR(
                    "Error: No se obtuvo el refresh token.\n"
                    "Esto puede pasar si ya autorizaste antes.\n"
                    "Intentá revocar el acceso en: https://myaccount.google.com/permissions"
                )
            )
            return

        env_path = os.path.join(os.getcwd(), ".env")

        try:
            self._update_env("GOOGLE_DRIVE_REFRESH_TOKEN", refresh_token, env_path)
        except OSError as exc:
            self.stderr.write(
                self.style.ERROR(f"Error al guardar en .env: {exc}")
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"\n¡Listo! Refresh token guardado en .env\n"
                f"Token: {refresh_token[:20]}...\n"
                f"Archivo: {env_path}\n"
            )
        )

    def _update_env(self, key, value, env_path):
        """Agrega o actualiza una variable en el archivo .env.

        Si la variable ya existe, la reemplaza.
        Si no existe, la agrega al final del archivo.

        Args:
            key (str): Nombre de la variable.
            value (str): Valor de la variable.
            env_path (str): Ruta al archivo .env.

        Raises:
            OSError: Si no se puede leer o escribir el archivo.
        """
        lines = []
        found = False

        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
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
