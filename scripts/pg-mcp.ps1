#!/usr/bin/env pwsh
# pg-mcp.ps1 — Wrapper para crystaldba/postgres-mcp con fallback de runners.
# Lee RASSA_JALA_DB_URL del shell, valida formato, y ejecuta el MCP.
# Uso desde terminal:
#   powershell -ExecutionPolicy Bypass -File scripts/pg-mcp.ps1
# Uso desde opencode.json:
#   ["powershell", "-ExecutionPolicy", "Bypass", "-File", "scripts/pg-mcp.ps1"]
# Nota: sin -ExecutionPolicy Bypass, Windows puede bloquear scripts .ps1 por defecto.

$ErrorActionPreference = "Stop"

if (-not $env:RASSA_JALA_DB_URL) {
  Write-Host "Error: RASSA_JALA_DB_URL no está definida en el shell." -ForegroundColor Red
  Write-Host ""
  Write-Host "  Para definirla en el sistema ejecuta el siguiente comando en PowerShell (requiere reiniciar la terminal actual para que se cargue):"
  Write-Host "    [Environment]::SetEnvironmentVariable('RASSA_JALA_DB_URL', 'postgresql://user:pass@host:5432/rassa_jala_db', 'User') "
  Write-Host ""
  Write-Host "  Nota: Solo debes reemplazar los datos de la URL (user:pass@host:5432/db), el texto 'User' del final déjalo tal cual."
  Write-Host ""
  Write-Host "  Puedes sobrescribir el valor de la variable anterior ejecutando nuevamente:"
  Write-Host "    [Environment]::SetEnvironmentVariable('RASSA_JALA_DB_URL', 'postgresql://NUEVO_USUARIO:PAS@HOST:5432/NUEVA_BD', 'User') "
  exit 1
}

$uri = $env:RASSA_JALA_DB_URL
if (-not ($uri.StartsWith("postgres://") -or $uri.StartsWith("postgresql://"))) {
  Write-Host "Error: RASSA_JALA_DB_URL debe empezar con postgres:// o postgresql://" -ForegroundColor Red
  Write-Host "Actual: $($uri.Substring(0, [Math]::Min(30, $uri.Length)))..."
  exit 1
}

function Invoke-Mcp {
  if (Get-Command uvx -ErrorAction SilentlyContinue) {
    Write-Host "postgres-mcp: usando uvx"
    $env:DATABASE_URI = $uri
    & uvx "postgres-mcp==0.3.0" --access-mode=unrestricted
    return
  }

  if (Get-Command pipx -ErrorAction SilentlyContinue) {
    Write-Host "postgres-mcp: usando pipx"
    $env:DATABASE_URI = $uri
    & pipx run --spec "postgres-mcp==0.3.0" postgres-mcp --access-mode=unrestricted
    return
  }

  if (Get-Command python3 -ErrorAction SilentlyContinue) {
    Write-Host "postgres-mcp: usando python3 -m"
    $env:DATABASE_URI = $uri
    & python3 -m postgres_mcp --access-mode=unrestricted
    return
  }

  if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host "postgres-mcp: usando python -m"
    $env:DATABASE_URI = $uri
    & python -m postgres_mcp --access-mode=unrestricted
    return
  }

  Write-Host "Error: no se encontró ningún runner de Python." -ForegroundColor Red
  Write-Host ""
  Write-Host "  Instalá alguno de estos:"
  Write-Host "    uvx:   powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\""
  Write-Host "    pipx:  python -m pip install --user pipx"
  Write-Host "    python: https://www.python.org/downloads/"
  exit 1
}

Invoke-Mcp
