# ============================================================================
# Rassa — Configuración del Entorno de Desarrollo (PowerShell)
# ============================================================================
# Setup interactivo: Python → venv → dependencias → PostgreSQL →
# .env (SECRET_KEY + DATABASE_URL) → migrate → seed → verify.
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
$script:Version = "2.0.0"
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

    try {
        $paths = @(where.exe python 2>$null) + @(where.exe python3 2>$null) |
            Where-Object { $_ -notmatch '\\(venv|env)\\' } |
            Select-Object -Unique
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
        } catch {}
    }

    $compatible = $allPaths | Where-Object {
        Test-VersionGe -Version1 $_.Version -Version2 $script:MinPythonVersion
    }

    if (-not $compatible) {
        Write-Red "No se encontró Python >= $($script:MinPythonVersion)."
        Write-Host ""
        Show-PythonInstallGuide
        return $false
    }

    $compatible = $compatible | Sort-Object -Property Version -Descending

    if ($compatible.Count -eq 1) {
        $item = $compatible[0]
        Write-Host "Python $($item.Version) detectado en: $($item.Path)"
        $script:PythonCmd = $item.Path
        return $true
    }

    Write-Host ("Se encontraron {0} versiones de Python compatibles:" -f $compatible.Count)
    Write-Host ""
    for ($i = 0; $i -lt $compatible.Count; $i++) {
        Write-Host ("  [{0}] Python {1} — {2}" -f ($i + 1), $compatible[$i].Version, $compatible[$i].Path)
    }
    Write-Host ""

    while ($true) {
        $answer = Read-Host "Elegí una opción [1-$($compatible.Count)]"
        try {
            $idx = [int]$answer - 1
            if ($idx -ge 0 -and $idx -lt $compatible.Count) {
                $script:PythonCmd = $compatible[$idx].Path
                Write-Host ("Usando Python {0}" -f $compatible[$idx].Version)
                return $true
            }
        } catch {}
        Write-Host "Opción no válida."
    }
}

function Parse-PythonVersion {
    param([string]$Raw)
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
            return
        }
    }
    if (Test-Path ".venv") {
        Write-Yellow "El entorno virtual '.venv\' ya existe (creado por uv)."
        $answer = Read-Host "¿Recrearlo? Se eliminará el actual. [y/N]"
        if ($answer -match '^[sSyY]') {
            Write-Host "Eliminando .venv\ existente..."
            Remove-Item -Recurse -Force .venv
        } else {
            Write-Host "Usando .venv\ existente."
            return
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
    return $true
}

function Invoke-ActivateVenv {
    $venvCandidates = @(
        "venv\Scripts\Activate.ps1",
        ".venv\Scripts\Activate.ps1"
    )
    foreach ($candidate in $venvCandidates) {
        $activatePath = Join-Path $script:ScriptDir $candidate
        if (Test-Path $activatePath) {
            . $activatePath
            Write-Host "  → python: $(Get-Command python | Select-Object -ExpandProperty Source)"
            Write-Host "  → pip: $(Get-Command pip | Select-Object -ExpandProperty Source)"
            return $true
        }
    }
    Write-Red "No se encontró Activate.ps1 en venv/ ni .venv/."
    return $false
}

function Invoke-EnsureVenvActive {
    $venvCandidates = @(
        "venv\Scripts\Activate.ps1",
        ".venv\Scripts\Activate.ps1"
    )
    foreach ($candidate in $venvCandidates) {
        $activatePath = Join-Path $script:ScriptDir $candidate
        if (Test-Path $activatePath) {
            . $activatePath 2>$null
            return
        }
    }
}

# ---------------------------------------------------------------------------
# Phase 3: Dependencies
# ---------------------------------------------------------------------------

function Invoke-Phase3Deps {
    Invoke-EnsureVenvActive

    # Detectar si el venv fue creado por uv
    $uvCreated = $false
    @("venv\pyvenv.cfg", ".venv\pyvenv.cfg") | ForEach-Object {
        if (Test-Path $_) {
            $content = Get-Content $_ -Raw
            if ($content -match "uv") { $uvCreated = $true }
        }
    }

    if ($uvCreated) {
        Write-Yellow "El venv fue creado por uv. Se usará uv automáticamente."
        $depChoice = "2"
    } else {
        Write-Host "¿Cómo querés instalar las dependencias?"
        Write-Host ""
        Write-Host "  [1] pip (requirements.txt)"
        Write-Host "  [2] uv (pyproject.toml)"
        Write-Host ""

        while ($true) {
            $depChoice = Read-Host "Elegí una opción [1/2]"
            if ($depChoice -eq '1' -or $depChoice -eq '2') { break }
            Write-Host "Opción no válida."
        }
    }

    if ($depChoice -eq '2') {
        $uvExists = Get-Command uv -ErrorAction SilentlyContinue
        if (-not $uvExists) {
            Write-Yellow "uv no está instalado. Instalando con pip..."
            pip install uv 2>&1 | Out-Null
        }
        Write-Host "Instalando dependencias con uv..."
        uv sync 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Red "Falló la instalación con uv."
            return $false
        }
    } else {
        if (-not (Test-Path "requirements.txt")) {
            Write-Red "No se encontró requirements.txt"
            return $false
        }
        Write-Host "Instalando dependencias con pip..."
        pip install -r requirements.txt 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Red "Falló la instalación de dependencias."
            return $false
        }
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

    $baseDirs = @("C:\Program Files", "C:\Program Files (x86)")
    $pgFound = $false
    foreach ($base in $baseDirs) {
        for ($ver = 10; $ver -le 99; $ver++) {
            $pgBin = "$base\PostgreSQL\$ver\bin"
            if (Test-Path "$pgBin\pg_isready.exe") {
                $env:Path = "$pgBin;$env:Path"
                $pgFound = $true
                break
            }
        }
        if ($pgFound) { break }
    }

    if (-not (Get-Command pg_isready -ErrorAction SilentlyContinue)) {
        Write-Red "PostgreSQL no está instalado o pg_isready no está en el PATH."
        Write-Host ""
        Show-PostgresInstallGuide
        return $false
    }

    try {
        $pgReady = & pg_isready -q 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Yellow "PostgreSQL está instalado pero no está corriendo."
            Write-Host ""
            Write-Host "Iniciá PostgreSQL desde Services (services.msc) o:"
            Write-Host "  net start postgresql-x64-16"
            return $false
        }
    } catch {
        Write-Yellow "PostgreSQL no está disponible."
        return $false
    }

    Write-Green "PostgreSQL está corriendo."
    return $true
}

function Show-PostgresInstallGuide {
    Write-Host "Para instalar PostgreSQL:"
    Write-Host ""
    Write-Host "  Descargá el instalador oficial: https://www.postgresql.org/download/windows/"
    Write-Host "  Durante la instalación, anotá el puerto (default: 5432) y la contraseña de postgres."
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Phase 5: Environment variables (.env)
# ---------------------------------------------------------------------------

function Invoke-Phase5Env {
    Invoke-EnsureVenvActive

    Write-Host "Configuración del archivo .env"
    Write-Host ""

    # --- SECRET_KEY ---
    $secretKey = ""
    if (Test-Path ".env") {
        $envContent = Get-Content .env -Raw
        if ($envContent -match "^SECRET_KEY=['""]?(.+?)['""]?$") {
            $secretKey = $Matches[1]
        }
    }

    if (-not $secretKey -or $secretKey -eq "changeme") {
        Write-Host "Generando SECRET_KEY segura..."
        Invoke-EnsureVenvActive
        $secretKey = & python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" 2>$null
        if (-not $secretKey) {
            Write-Yellow "No se pudo generar SECRET_KEY automáticamente."
            $secretKey = Read-Host "Ingresá una SECRET_KEY (o Enter para 'changeme')"
            if (-not $secretKey) { $secretKey = "changeme" }
        }
        Write-Green "SECRET_KEY generada."
    } else {
        Write-Host "SECRET_KEY ya está configurada."
    }

    # --- DATABASE_URL ---
    Write-Host ""
    Write-Host "Configuración de PostgreSQL:"
    Write-Host ""

    $dbHost = "localhost"
    $dbPort = "5432"
    $dbName = "rassa_jala_db"
    $dbUser = "postgres"
    $dbPass = ""

    if (Test-Path ".env") {
        $envContent = Get-Content .env -Raw
        if ($envContent -match '^DATABASE_URL=(.+)') {
            Write-Host "DATABASE_URL actual: $($Matches[1])"
            $reconfig = Read-Host "¿Querés reconfigurar la base de datos? [y/N]"
            if ($reconfig -notmatch '^[sSyY]') {
                Write-Host "Manteniendo configuración actual."
                Write-EnvFile -SecretKey $secretKey
                return $true
            }
        }
    }

    $userInput = Read-Host "Host [$dbHost]"
    if ($userInput) { $dbHost = $userInput }

    $userInput = Read-Host "Puerto [$dbPort]"
    if ($userInput) { $dbPort = $userInput }

    $userInput = Read-Host "Nombre de la base de datos [$dbName]"
    if ($userInput) { $dbName = $userInput }

    $userInput = Read-Host "Usuario de PostgreSQL [$dbUser]"
    if ($userInput) { $dbUser = $userInput }

    $dbPass = Read-Host "Contraseña de PostgreSQL" -AsSecureString
    $dbPassPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($dbPass)
    )

    if (-not $dbPassPlain) {
        Write-Yellow "Contraseña vacía. Se usará conexión sin contraseña."
    }

    # Crear base de datos
    Write-Host ""
    Write-Host "Creando base de datos '$dbName' si no existe..."

    $env:PGPASSWORD = $dbPassPlain
    try {
        $dbExists = & psql -h $dbHost -p $dbPort -U $dbUser -tc "SELECT 1 FROM pg_database WHERE datname = '$dbName'" 2>$null
        if ($dbExists -and $dbExists -match '1') {
            Write-Yellow "La base de datos '$dbName' ya existe."
        } else {
            & psql -h $dbHost -p $dbPort -U $dbUser -c "CREATE DATABASE $dbName" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Green "Base de datos '$dbName' creada."
            } else {
                Write-Red "No se pudo crear la base de datos."
                Write-Host "Podés crearla manualmente:"
                Write-Host "  psql -h $dbHost -p $dbPort -U $dbUser -c `"CREATE DATABASE $dbName;`""
            }
        }
    } catch {
        Write-Yellow "No se pudo verificar la base de datos (psql no encontrado o error de conexión)."
        Write-Host "Creá la base de datos manualmente si es necesario."
    }
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue

    # Construir DATABASE_URL
    if ($dbPassPlain) {
        $databaseUrl = "postgres://${dbUser}:${dbPassPlain}@${dbHost}:${dbPort}/${dbName}"
    } else {
        $databaseUrl = "postgres://${dbUser}@${dbHost}:${dbPort}/${dbName}"
    }

    Write-EnvFile -SecretKey $secretKey -DatabaseUrl $databaseUrl
    return $true
}

function Write-EnvFile {
    param(
        [string]$SecretKey,
        [string]$DatabaseUrl = ""
    )

    $envLines = @()

    if (Test-Path ".env") {
        $existingContent = Get-Content .env -ErrorAction SilentlyContinue
        if ($existingContent) {
            $envLines = @($existingContent | ForEach-Object {
                if ($_ -match '^SECRET_KEY=') { "SECRET_KEY=`"$SecretKey`"" }
                elseif ($DatabaseUrl -and $_ -match '^DATABASE_URL=') { "DATABASE_URL=$DatabaseUrl" }
                else { $_ }
            })
        }
    }

    if ($envLines.Count -eq 0) {
        $envLines = @("SECRET_KEY=`"$SecretKey`"")
        if ($DatabaseUrl) {
            $envLines += "DATABASE_URL=$DatabaseUrl"
        }
    }

    # Defaults
    $hasDebug = $envLines | Where-Object { $_ -match '^DEBUG=' }
    if (-not $hasDebug) { $envLines += "DEBUG=True" }

    $hasHosts = $envLines | Where-Object { $_ -match '^ALLOWED_HOSTS=' }
    if (-not $hasHosts) { $envLines += "ALLOWED_HOSTS=localhost,127.0.0.1" }

    $hasCors = $envLines | Where-Object { $_ -match '^CORS_ALLOWED_ORIGINS=' }
    if (-not $hasCors) { $envLines += "CORS_ALLOWED_ORIGINS=http://localhost:8081,http://localhost:19006" }

    $envLines | Set-Content .env
    Write-Green ".env configurado exitosamente."
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
        Write-Red "Falló la migración. Revisá la conexión a la base de datos en .env"
        return $false
    }

    Write-Host ""
    Write-Green "Migraciones aplicadas exitosamente."
    return $true
}

# ---------------------------------------------------------------------------
# Phase 7: Seed data
# ---------------------------------------------------------------------------

function Invoke-Phase7Seed {
    Invoke-EnsureVenvActive

    Write-Host "Cargando datos de prueba (32 tablas + seeders)..."

    python manage.py seed_rassa_data 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Red "Falló la carga de datos."
        Write-Host "Podés reintentar con: python manage.py seed_rassa_data --clear"
        return $false
    }

    Write-Host ""
    Write-Green "Datos de prueba cargados exitosamente."
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
        } catch {}
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
    Write-Host "Usuarios de prueba:"
    Write-Host "  admin@rassa.com / admin123 (Administrador)"
    Write-Host "  vendedor@rassa.com / vendedor123 (Vendedor)"
    Write-Host "  juan.perez@email.com / juan123 (Agricultor)"
    Write-Host "  ana.ramirez@email.com / ana123 (Cliente)"
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
        exit 1
    }

    $script:CurrentPhase = ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

function Invoke-Main {
    if ($Help) {
        Show-Help
        exit 0
    }

    if ($Reset) {
        Reset-State
    }

    try {
        Start-Transcript -Path $script:LogFile -Append -Force | Out-Null
    } catch {
        Write-Yellow "⚠ No se pudo iniciar el log. Continuando sin log."
    }

    Write-Banner

    try {
        Invoke-Phase0Check
    } catch {
        Write-Red "ERROR: Falló la verificación del entorno PowerShell."
        exit 1
    }

    Invoke-RunPhase "phase_1" "Detección de Python"      ${function:Invoke-Phase1Python}
    Invoke-RunPhase "phase_2" "Entorno virtual"          ${function:Invoke-Phase2Venv}
    Invoke-RunPhase "phase_3" "Dependencias"             ${function:Invoke-Phase3Deps}
    Invoke-RunPhase "phase_4" "PostgreSQL"               ${function:Invoke-Phase4Postgres}
    Invoke-RunPhase "phase_5" "Variables de entorno"     ${function:Invoke-Phase5Env}
    Invoke-RunPhase "phase_6" "Migraciones Django"       ${function:Invoke-Phase6Migrate}
    Invoke-RunPhase "phase_7" "Datos de prueba"          ${function:Invoke-Phase7Seed}
    Invoke-RunPhase "phase_8" "Verificación final"       ${function:Invoke-Phase8Verify}

    try {
        Stop-Transcript | Out-Null
    } catch {}

    Write-Host "Log guardado en: $($script:LogFile)"
}

Invoke-Main
