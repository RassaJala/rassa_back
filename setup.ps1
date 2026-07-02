# ============================================================================
# Rassa — Configuración del Entorno de Desarrollo (PowerShell)
# ============================================================================
# Single-command setup: Python detection → venv → pip → PostgreSQL →
# environment → migrate → load schema → verify.
#
# Plataforma: Windows (PowerShell 5.1+ / PowerShell Core 7+)
# En Linux/macOS/Git-Bash usá: bash setup.sh
#
# Uso:
#   .\setup.ps1           # Ejecución completa (salta fases ya completadas)
#   .\setup.ps1 -Reset    # Ignora .setup_state, ejecuta todo de nuevo
#   .\setup.ps1 -Help     # Muestra ayuda
#
# Estado: .setup_state guarda las fases completadas para saltarlas en re-runs.
# Log:    setup.log captura toda la salida.
# ============================================================================

param(
    [switch]$Reset,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$script:Version = "1.0.0"
$script:ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:LogFile = Join-Path $script:ScriptDir "setup.log"
$script:StateFile = Join-Path $script:ScriptDir ".setup_state"
$script:MinPythonVersion = "3.11"
$script:PythonCmd = $null
$script:CurrentPhase = ""

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

function Write-Green  { Write-Host $args -ForegroundColor Green  }
function Write-Yellow { Write-Host $args -ForegroundColor Yellow }
function Write-Red    { Write-Host $args -ForegroundColor Red    }
function Write-Bold   { Write-Host $args -ForegroundColor White  }

function Write-Banner {
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════════════╗"
    Write-Host ("║         Rassa — Configuración del entorno  v{0}          ║" -f $script:Version)
    Write-Host "╚══════════════════════════════════════════════════════════════╝"
    Write-Host ""
}

function Show-Help {
    @"
Uso: .\setup.ps1 [OPCIONES]

Opciones:
  -Reset   Ignora .setup_state y ejecuta todas las fases de nuevo.
  -Help    Muestra esta ayuda.

Sin opciones, el script ejecuta solo las fases que no se hayan completado
anteriormente (según .setup_state).

En Linux/macOS/Git-Bash usá: bash setup.sh

Log: setup.log
"@
}

# ---------------------------------------------------------------------------
# State file management
# ---------------------------------------------------------------------------

function Test-PhaseDone {
    param([string]$Phase)
    if (Test-Path $script:StateFile) {
        $line = Select-String -Path $script:StateFile -Pattern "^${Phase}=done$" -SimpleMatch -Quiet
        return $line
    }
    return $false
}

function Set-PhaseDone {
    param([string]$Phase)
    $entry = "${Phase}=done"
    if (-not (Test-Path $script:StateFile) -or -not (Select-String -Path $script:StateFile -Pattern "^${Phase}=done$" -SimpleMatch -Quiet)) {
        Add-Content -Path $script:StateFile -Value $entry
    }
}

function Reset-State {
    Remove-Item -Path $script:StateFile -Force -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
# Phase 0: Pre-flight checks
# ---------------------------------------------------------------------------

function Invoke-Phase0Check {
    # Validate we're on Windows PowerShell
    if ($PSVersionTable.PSVersion.Major -lt 5) {
        Write-Red "ERROR: Se requiere PowerShell 5.1 o superior."
        Write-Red "Versión detectada: $($PSVersionTable.PSVersion)"
        exit 1
    }
    Write-Green "PowerShell $($PSVersionTable.PSVersion) detectado."
}

# ---------------------------------------------------------------------------
# Phase 1: Python detection
# ---------------------------------------------------------------------------

function Invoke-Phase1Python {
    Write-Host "Buscando instalaciones de Python..."

    $pythonPaths = @{}
    $allPaths = @()

    # Collect all python executables via 'where.exe'
    try {
        $paths = @(where.exe python 2>$null) + @(where.exe python3 2>$null) | Select-Object -Unique
    } catch {
        $paths = @()
    }

    foreach ($pypath in $paths) {
        if (-not $pypath) { continue }
        try {
            $raw = & $pypath --version 2>&1
            $ver = Parse-PythonVersion $raw
            if ($ver -and -not $pythonPaths.ContainsKey($ver)) {
                $pythonPaths[$ver] = $pypath
                $allPaths += @{ Version = $ver; Path = $pypath }
            }
        } catch {
            # Skip unresponsive python
        }
    }

    # Filter: only >= MinPythonVersion
    $compatible = $allPaths | Where-Object {
        Test-VersionGe -Version1 $_.Version -Version2 $script:MinPythonVersion
    }

    if (-not $compatible) {
        Write-Red "No se encontró Python >= $($script:MinPythonVersion)."
        Write-Host ""
        Show-PythonInstallGuide
        return $false
    }

    # Sort by version descending
    $compatible = $compatible | Sort-Object -Property Version -Descending

    if ($compatible.Count -eq 1) {
        $item = $compatible[0]
        Write-Host "Python $($item.Version) detectado en: $($item.Path)"
        $script:PythonCmd = $item.Path
        return $true
    }

    # Multiple versions — menu
    Write-Host ("Se encontraron {0} versiones de Python compatibles:" -f $compatible.Count)
    Write-Host ""
    for ($i = 0; $i -lt $compatible.Count; $i++) {
        Write-Host ("  [{0}] Python {1} — {2}" -f ($i + 1), $compatible[$i].Version, $compatible[$i].Path)
    }
    Write-Host ""
    Write-Host "Opciones:"
    Write-Host "  (a) Elegir una de la lista"
    Write-Host "  (b) Cancelar"
    Write-Host ""

    while ($true) {
        $answer = Read-Host "Elegí una opción [1-$($compatible.Count)/b]"
        if ($answer -eq 'b' -or $answer -eq 'B') {
            Write-Host "Cancelado."
            return $false
        }
        try {
            $idx = [int]$answer - 1
            if ($idx -ge 0 -and $idx -lt $compatible.Count) {
                $script:PythonCmd = $compatible[$idx].Path
                Write-Host ("Usando Python {0} ({1})" -f $compatible[$idx].Version, $compatible[$idx].Path)
                return $true
            }
        } catch {}
        Write-Host "Opción no válida. Intentá de nuevo."
    }
}

function Parse-PythonVersion {
    param([string]$Raw)
    # "Python 3.14.6" or path containing /3.14.6/
    if ($Raw -match 'Python\s+(\d+\.\d+(\.\d+)?)') {
        return $Matches[1]
    }
    if ($Raw -match '\\(\d+\.\d+(\.\d+)?)\\') {
        return $Matches[1]
    }
    return $null
}

function Test-VersionGe {
    param([string]$Version1, [string]$Version2)
    $a = [version]$Version1
    $b = [version]$Version2
    return $a -ge $b
}

function Show-PythonInstallGuide {
    Write-Host "Para instalar Python $($script:MinPythonVersion)+:"
    Write-Host ""
    Write-Host "  Descargá el instalador oficial: https://www.python.org/downloads/"
    Write-Host "  IMPORTANTE: Marcá 'Add Python to PATH' durante la instalación."
    Write-Host "  Luego cerrá y reabrí PowerShell para que detecte el nuevo PATH."
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Phase 2: Virtual environment
# ---------------------------------------------------------------------------

function Invoke-Phase2Venv {
    $py = if ($script:PythonCmd) { $script:PythonCmd } else { "python" }

    if (Test-Path "venv") {
        Write-Yellow "El entorno virtual 'venv\' ya existe."
        $answer = Read-Host "¿Recrearlo? Se eliminará el actual. [y/N]"
        if ($answer -match '^[sSyY]') {
            Write-Host "Eliminando venv\ existente..."
            Remove-Item -Recurse -Force venv
        } else {
            Write-Host "Usando venv\ existente."
            return $true
        }
    }

    Write-Host "Creando entorno virtual con: $py -m venv venv"
    & $py -m venv venv 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Red "Falló la creación del entorno virtual."
        return $false
    }

    Write-Green "Entorno virtual creado en venv\"
    Invoke-ActivateVenv
}

function Invoke-ActivateVenv {
    $activatePath = Join-Path $script:ScriptDir "venv\Scripts\Activate.ps1"
    if (Test-Path $activatePath) {
        . $activatePath
        Write-Host "  → pip: $(Get-Command pip | Select-Object -ExpandProperty Source)"
        Write-Host "  → python: $(Get-Command python | Select-Object -ExpandProperty Source)"
        return $true
    } else {
        Write-Red "No se encontró venv\Scripts\Activate.ps1. ¿Se creó correctamente?"
        return $false
    }
}

function Invoke-EnsureVenvActive {
    $activatePath = Join-Path $script:ScriptDir "venv\Scripts\Activate.ps1"
    if (Test-Path $activatePath) {
        . $activatePath 2>$null
    }
}

# ---------------------------------------------------------------------------
# Phase 3: Dependencies
# ---------------------------------------------------------------------------

function Invoke-Phase3Pip {
    Invoke-EnsureVenvActive

    if (-not (Test-Path "requirements.txt")) {
        Write-Red "No se encontró requirements.txt en $(Get-Location)"
        return $false
    }

    Write-Host "Instalando dependencias desde requirements.txt..."

    pip install -r requirements.txt 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Red "Falló la instalación de dependencias."
        Write-Host "Revisá el error arriba y asegurate de que todas las dependencias"
        Write-Host "estén disponibles para tu sistema operativo."
        return $false
    }

    Write-Host ""
    Write-Green "Dependencias instaladas exitosamente."
    return $true
}

# ---------------------------------------------------------------------------
# Phase 4: PostgreSQL
# ---------------------------------------------------------------------------

function Invoke-Phase4Postgres {
    Write-Host "Verificando PostgreSQL..."

    # Probe common PostgreSQL install paths and add to PATH
    $pgVersions = @(17, 16, 15, 14)
    $pgFound = $false
    foreach ($ver in $pgVersions) {
        $pgBin = "C:\Program Files\PostgreSQL\$ver\bin"
        if (Test-Path "$pgBin\pg_isready.exe") {
            $env:Path = "$pgBin;$env:Path"
            $pgFound = $true
            break
        }
    }

    if (-not $pgFound) {
        $pgBinEnv = [Environment]::GetEnvironmentVariable("PATH", "Machine")
        foreach ($ver in $pgVersions) {
            if ($pgBinEnv -match [regex]::Escape("PostgreSQL\$ver\bin")) {
                $pgFound = $true
                break
            }
        }
    }

    if (-not (Get-Command pg_isready -ErrorAction SilentlyContinue)) {
        Write-Red "PostgreSQL no está instalado o pg_isready no está en el PATH."
        Write-Host ""
        Show-PostgresInstallGuide
        return $false
    }

    $pgReady = & pg_isready -q 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Yellow "PostgreSQL está instalado pero no está corriendo."
        Write-Host ""
        Write-Host "Iniciá PostgreSQL desde Services (services.msc) o:"
        Write-Host "  net start postgresql-x64-16"
        return $false
    }

    Write-Green "PostgreSQL está corriendo."

    # Create database if it doesn't exist
    $result = createdb rassa 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Green "Base de datos 'rassa' creada."
    } else {
        Write-Yellow "La base de datos 'rassa' ya existe — continuando."
    }

    return $true
}

function Show-PostgresInstallGuide {
    Write-Host "Para instalar PostgreSQL:"
    Write-Host ""
    Write-Host "  Descargá el instalador oficial: https://www.postgresql.org/download/windows/"
    Write-Host "  Durante la instalación, anotá el puerto (default: 5432) y la contraseña de postgres."
    Write-Host "  Asegurate de que pg_isready.exe y createdb.exe estén en:"
    Write-Host "  C:\Program Files\PostgreSQL\{version}\bin\"
    Write-Host "  (el script detecta automáticamente las versiones 14-17 en esa ubicación)."
    Write-Host ""
    Write-Host "Una vez instalado, volvé a ejecutar: .\setup.ps1"
    Write-Host "  (las fases ya completadas se saltean automáticamente)"
}

# ---------------------------------------------------------------------------
# Phase 5: Environment variables
# ---------------------------------------------------------------------------

function Invoke-Phase5Env {
    Invoke-EnsureVenvActive

    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.template") {
            Copy-Item .env.template .env
            Write-Green ".env creado desde .env.template."
        } else {
            Write-Red "No se encontró .env ni .env.template."
            return $false
        }
    } else {
        Write-Host ".env ya existe."
    }

    Write-Host ""
    Write-Host "Validando variables de entorno..."

    $hasWarnings = $false
    $envContent = Get-Content .env -Raw

    if ($envContent -notmatch '^SECRET_KEY=.+') {
        Write-Yellow "⚠ ADVERTENCIA: SECRET_KEY no está definido en .env"
        $hasWarnings = $true
    }
    if ($envContent -match '^SECRET_KEY=changeme') {
        Write-Yellow "⚠ ADVERTENCIA: SECRET_KEY tiene el valor por defecto 'changeme'."
        Write-Yellow "             Cambialo por una clave segura en producción."
        $hasWarnings = $true
    }
    if ($envContent -notmatch '^DATABASE_URL=.+') {
        Write-Yellow "⚠ ADVERTENCIA: DATABASE_URL no está definido en .env"
        $hasWarnings = $true
    }

    if ($hasWarnings) {
        Write-Host ""
        Write-Yellow "Se encontraron advertencias pero el script puede continuar."
    }

    return $true
}

# ---------------------------------------------------------------------------
# Phase 6: Django migrations
# ---------------------------------------------------------------------------

function Invoke-Phase6Migrate {
    Invoke-EnsureVenvActive

    Write-Host "Aplicando migraciones de Django..."

    python manage.py migrate --noinput 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Red "Falló la migración. Revisá la conexión a la base de datos."
        return $false
    }

    Write-Host ""
    Write-Green "Migraciones aplicadas exitosamente."
    return $true
}

# ---------------------------------------------------------------------------
# Phase 7: Schema load
# ---------------------------------------------------------------------------

function Invoke-Phase7Schema {
    Invoke-EnsureVenvActive

    Write-Host "Cargando esquema SQL (32 tablas + seeders)..."

    python manage.py load_rassa_schema 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Red "Falló la carga del esquema."
        Write-Host "Podés reintentar con: python manage.py load_rassa_schema --reset"
        return $false
    }

    Write-Host ""
    Write-Green "Esquema cargado exitosamente."
    return $true
}

# ---------------------------------------------------------------------------
# Phase 8: Verification
# ---------------------------------------------------------------------------

function Invoke-Phase8Verify {
    Invoke-EnsureVenvActive

    Write-Host "Verificando configuración de Django..."

    python manage.py check --deploy 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Green "✓ check --deploy: SIN ERRORES CRÍTICOS"
    } else {
        Write-Yellow "⚠ check --deploy encontró advertencias (no bloqueantes)."
    }

    Write-Host ""

    # Brief runserver test
    Write-Host "Probando arranque del servidor (3 segundos)..."
    $serverProcess = Start-Process -FilePath "python" `
        -ArgumentList "manage.py","runserver","--noreload" `
        -NoNewWindow -PassThru `
        -RedirectStandardOutput "$env:TEMP\rassaback_runserver.log" `
        -RedirectStandardError "$env:TEMP\rassaback_runserver_err.log"

    Start-Sleep -Seconds 3

    $serverOk = $false
    if (-not $serverProcess.HasExited) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8000/api/" `
                -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($response.StatusCode -ge 100) {
                Write-Green "✓ Servidor responde en http://localhost:8000/api/"
                $serverOk = $true
            }
        } catch {
            # Server not ready yet or curl-equivalent failed — not fatal
        }
    }

    Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    Remove-Item "$env:TEMP\rassaback_runserver.log","$env:TEMP\rassaback_runserver_err.log" `
        -ErrorAction SilentlyContinue

    if (-not $serverOk) {
        Write-Yellow "⚠ No se pudo verificar el servidor (puede ser normal)."
    }

    Write-Host ""
    Write-Green "╔══════════════════════════════════════════════════════════╗"
    Write-Green "║  ✓ Setup completo — proyecto listo                      ║"
    Write-Green "╚══════════════════════════════════════════════════════════╝"
    Write-Host ""
    Write-Host "Para iniciar el servidor:"
    Write-Host "  .\venv\Scripts\Activate.ps1"
    Write-Host "  python manage.py runserver"
    Write-Host ""
    Write-Host "La API estará disponible en: http://localhost:8000/api/"
    Write-Host ""

    return $true
}

# ---------------------------------------------------------------------------
# Phase orchestration
# ---------------------------------------------------------------------------

function Invoke-RunPhase {
    param(
        [string]$PhaseKey,
        [string]$Label,
        [scriptblock]$PhaseScript
    )

    $script:CurrentPhase = $PhaseKey

    Write-Bold ("── {0}: {1} ──" -f $PhaseKey.Replace("_","."), $Label)
    Write-Host ""

    if (Test-PhaseDone $PhaseKey) {
        Write-Green ("✓ Fase {0} ya completada — saltando." -f $PhaseKey -replace "_"," ")
        Write-Host ""
        $script:CurrentPhase = ""
        return
    }

    try {
        $result = & $PhaseScript
        if ($result) {
            Write-Host ""
            Write-Green ("✓ Fase {0} completada." -f $PhaseKey -replace "_",".")
            Set-PhaseDone $PhaseKey
            Write-Host ""
        } else {
            Write-Host ""
            Write-Red ("✗ Fase {0} falló." -f $PhaseKey -replace "_",".")
            exit 1
        }
    } catch {
        Write-Host ""
        Write-Red ("✗ ERROR en fase {0}: {1}" -f $PhaseKey, $_.Exception.Message)
        Write-Host ""
        Write-Red "╔══════════════════════════════════════════════════════╗"
        Write-Red "║  ERROR — El script falló                            ║"
        Write-Red ("║  Fase: {0}                                    ║" -f $script:CurrentPhase)
        Write-Red ("╚══════════════════════════════════════════════════════╝")
        Write-Host ""
        Write-Host ("Revisá el log completo en: $($script:LogFile)")
        Write-Host "Corregí el error y volvé a ejecutar: .\setup.ps1"
        Write-Host "  (las fases ya completadas se saltean automáticamente)"
        Write-Host ""
        exit 1
    }

    $script:CurrentPhase = ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

function Invoke-Main {
    # Parse arguments
    if ($Help) {
        Show-Help
        exit 0
    }

    if ($Reset) {
        Reset-State
    }

    # Start logging
    try {
        Start-Transcript -Path $script:LogFile -Append -Force | Out-Null
    } catch {
        Write-Yellow "⚠ No se pudo iniciar el log en $($script:LogFile). Continuando sin log."
    }

    Write-Banner

    # Pre-flight
    try {
        Invoke-Phase0Check
    } catch {
        Write-Red "ERROR: Falló la verificación del entorno PowerShell."
        exit 1
    }

    Invoke-RunPhase "phase_1" "Detección de Python"      ${function:Invoke-Phase1Python}
    Invoke-RunPhase "phase_2" "Entorno virtual"          ${function:Invoke-Phase2Venv}
    Invoke-RunPhase "phase_3" "Dependencias"             ${function:Invoke-Phase3Pip}
    Invoke-RunPhase "phase_4" "PostgreSQL"               ${function:Invoke-Phase4Postgres}
    Invoke-RunPhase "phase_5" "Variables de entorno"     ${function:Invoke-Phase5Env}
    Invoke-RunPhase "phase_6" "Migraciones Django"       ${function:Invoke-Phase6Migrate}
    Invoke-RunPhase "phase_7" "Carga de esquema SQL"     ${function:Invoke-Phase7Schema}
    Invoke-RunPhase "phase_8" "Verificación final"       ${function:Invoke-Phase8Verify}

    try {
        Stop-Transcript | Out-Null
    } catch {}

    Write-Host "Log guardado en: $($script:LogFile)"
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

Invoke-Main
