#Requires -Version 7.0
#!/usr/bin/env pwsh
# pg-mcp.ps1 — Wrapper para crystaldba/postgres-mcp con fallback de runners.
# Lee RASSA_JALA_DB_URL del shell, valida formato, y ejecuta el MCP.
# Uso desde terminal:
#   powershell -ExecutionPolicy Bypass -File scripts/pg-mcp.ps1
# Uso desde opencode.json:
#   ["powershell", "-ExecutionPolicy", "Bypass", "-File", "scripts/pg-mcp.ps1"]
# Nota: sin -ExecutionPolicy Bypass, Windows puede bloquear scripts .ps1 por defecto.
#
# NOTA DE SEGURIDAD: se usa --access-mode=unrestricted a proposito.
# El proyecto esta en desarrollo activo y aun no existe una version estable.
# El agente necesita libertad para analizar la base de datos, ejecutar
# consultas complejas y explorar datos bajo la supervision del desarrollador
# que utilice el MCP. En un entorno productivo estable se recomienda
# --access-mode=read-only o el modo restrictivo que aplique.

Param(
  [string]$version
)

$ErrorActionPreference = "Stop"

$DefaultMcpVersion = "0.3.0"
$McpVersion = if ($version) {
  $version
} elseif ($env:POSTGRES_MCP_VERSION) {
  $env:POSTGRES_MCP_VERSION
} else {
  $DefaultMcpVersion
}
$McpPackage = "postgres-mcp==$McpVersion"
$AccessMode = "--access-mode=unrestricted"

if (-not $env:RASSA_JALA_DB_URL) {
  Write-Error "Error: RASSA_JALA_DB_URL no está definida en el shell." -ErrorAction Continue
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
  Write-Error "Error: RASSA_JALA_DB_URL debe empezar con postgres:// o postgresql://" -ErrorAction Continue
  Write-Host "Actual: $($uri.Substring(0, [Math]::Min(30, $uri.Length)))..."
  exit 1
}

function Invoke-Mcp {
  $env:DATABASE_URI = $uri
  $lastExitCodeValue = 1
  $tried = $false
  try {
    if (Get-Command uvx -ErrorAction SilentlyContinue) {
      $tried = $true
      Write-Host "postgres-mcp: intentando uvx"
      & uvx "$McpPackage" $AccessMode
      $lastExitCodeValue = $LASTEXITCODE
      if ($lastExitCodeValue -eq 0) { exit 0 }
      Write-Warning "postgres-mcp: uvx falló con código $lastExitCodeValue, intentando siguiente..."
    }

    if (Get-Command pipx -ErrorAction SilentlyContinue) {
      $tried = $true
      Write-Host "postgres-mcp: intentando pipx"
      & pipx run --spec "$McpPackage" postgres-mcp $AccessMode
      $lastExitCodeValue = $LASTEXITCODE
      if ($lastExitCodeValue -eq 0) { exit 0 }
      Write-Warning "postgres-mcp: pipx falló con código $lastExitCodeValue, intentando siguiente..."
    }

    if (Get-Command python3 -ErrorAction SilentlyContinue) {
      $tried = $true
      Write-Host "postgres-mcp: intentando python3 -m"
      & python3 -m postgres_mcp $AccessMode
      $lastExitCodeValue = $LASTEXITCODE
      if ($lastExitCodeValue -eq 0) { exit 0 }
      Write-Warning "postgres-mcp: python3 falló con código $lastExitCodeValue, intentando siguiente..."
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
      $tried = $true
      Write-Host "postgres-mcp: intentando python -m"
      & python -m postgres_mcp $AccessMode
      $lastExitCodeValue = $LASTEXITCODE
      if ($lastExitCodeValue -eq 0) { exit 0 }
      Write-Warning "postgres-mcp: python falló con código $lastExitCodeValue, intentando siguiente..."
    }

    if (-not $tried) {
      Write-Error "Error: no se encontró ningún runner de Python." -ErrorAction Continue
      Write-Host ""
      Write-Host "  Instalá alguno de estos:"
      Write-Host "    uvx:   powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\""
      Write-Host "    pipx:  python -m pip install --user pipx"
      Write-Host "    python: https://www.python.org/downloads/"
    } else {
      Write-Error "Error: todos los runners de Python fallaron." -ErrorAction Continue
    }
    exit $lastExitCodeValue
  } finally {
    Remove-Item Env:DATABASE_URI -ErrorAction SilentlyContinue
  }
}

Invoke-Mcp
