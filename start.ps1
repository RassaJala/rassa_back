# ============================================================================
# Rassa — Iniciar Backend (PowerShell)
# ============================================================================
# Ejecuta los test automáticamente. Si pasan, enciende el servidor.
# Si fallan, muestra el error y NO enciende el servidor.
#
# Plataforma: Windows (PowerShell 5.1+ / PowerShell Core 7+)
# En Linux/macOS/Git-Bash usa: bash start.sh
#
# Uso:
#   .\start.ps1              # Corre test + server
#   .\start.ps1 -TestOnly    # Solo corre test, no enciende server
#   .\start.ps1 -Verbose     # Test con máximo detalle
#   .\start.ps1 -Skip        # Salta test (solo para emergencias)
#   .\start.ps1 -Help        # Muestra ayuda
# ============================================================================

param(
    [switch]$Skip,
    [switch]$TestOnly,
    [switch]$Verbose,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$script:ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Green  { Write-Host $args -ForegroundColor Green  }
function Write-Yellow { Write-Host $args -ForegroundColor Yellow }
function Write-Red    { Write-Host $args -ForegroundColor Red    }
function Write-Cyan   { Write-Host $args -ForegroundColor Cyan   }
function Write-Bold   { Write-Host $args -ForegroundColor White  }

function Write-Banner {
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════════════╗"
    Write-Host "║              Rassa — Iniciar Backend                        ║"
    Write-Host "╚══════════════════════════════════════════════════════════════╝"
    Write-Host ""
}

function Show-Help {
    @"
Uso: .\start.ps1 [OPCIONES]

Opciones:
  (sin opciones)   Corre test (verbosity 2) + enciende el servidor
  -TestOnly        Solo corre los test (no enciende server)
  -Verbose         Test con máximo detalle (verbosity 3)
  -Skip            Salta los test y enciende directamente (solo emergencias)
  -Help            Muestra esta ayuda

Comportamiento por defecto:
  1. Verifica que el entorno esté configurado (.env, venv, Python, PostgreSQL)
  2. Ejecuta TODOS los test del proyecto
  3. Si pasan -> enciende el servidor en http://localhost:8000
  4. Si fallan -> muestra qué tests fallaron y NO enciende el servidor

Ejemplos:
  .\start.ps1               # Uso normal
  .\start.ps1 -TestOnly     # Solo correr tests
  .\start.ps1 -TestOnly -Verbose  # Tests con máximo detalle
  .\start.ps1 -Verbose      # Tests detallados + encender server

En Linux/macOS/Git-Bash usa: bash start.sh
"@
}

# ---------------------------------------------------------------------------
# Activación del entorno virtual
# ---------------------------------------------------------------------------

function Activate-Venv {
    $candidates = @(
        "venv\Scripts\activate",
        ".venv\Scripts\activate",
        "venv\bin\activate",
        ".venv\bin\activate"
    )

    foreach ($path in $candidates) {
        $fullPath = Join-Path $script:ScriptDir $path
        if (Test-Path $fullPath) {
            try {
                . $fullPath
            } catch {
                Write-Red "╔══════════════════════════════════════════════════════╗"
                Write-Red "║  ERROR — El entorno virtual está corrupto            ║"
                Write-Red "╚══════════════════════════════════════════════════════╝"
                Write-Host ""
                Write-Host "  No se pudo activar el venv."
                Write-Host "  Solución: Remove-Item -Recurse venv,.venv; .\setup.ps1"
                Write-Host ""
                exit 1
            }

            # Verificar que el venv funciona
            try {
                $null = python --version
            } catch {
                Write-Red "╔══════════════════════════════════════════════════════╗"
                Write-Red "║  ERROR — El entorno virtual está corrupto            ║"
                Write-Red "╚══════════════════════════════════════════════════════╝"
                Write-Host ""
                Write-Host "  Python no funciona después de activar el venv."
                Write-Host "  Solución: Remove-Item -Recurse venv,.venv; .\setup.ps1"
                Write-Host ""
                exit 1
            }

            return
        }
    }

    Write-Red "╔══════════════════════════════════════════════════════╗"
    Write-Red "║  ERROR — No se encontró el entorno virtual           ║"
    Write-Red "╚══════════════════════════════════════════════════════╝"
    Write-Host ""
    Write-Host "Ejecuta primero: .\setup.ps1"
    Write-Host ""
    exit 1
}

# ---------------------------------------------------------------------------
# Verificaciones previas
# ---------------------------------------------------------------------------

function Test-Prechecks {
    $failed = $false

    # Verificar Python
    try {
        $null = python --version 2>&1
    } catch {
        Write-Red "✗ No se encontró Python en el PATH"
        Write-Host "  Instala Python 3.12+: https://www.python.org/downloads/"
        Write-Host "  O activa tu venv: .\venv\Scripts\activate"
        $failed = $true
    }

    $envPath = Join-Path $script:ScriptDir ".env"
    if (-not (Test-Path $envPath)) {
        Write-Red "✗ No se encontró .env"
        Write-Host "  Ejecuta: .\setup.ps1"
        $failed = $true
    }

    $managePy = Join-Path $script:ScriptDir "manage.py"
    if (-not (Test-Path $managePy)) {
        Write-Red "✗ No se encontró manage.py"
        Write-Host "  ¿Clonaste el repo correctamente?"
        $failed = $true
    }

    if ($failed) {
        Write-Host ""
        exit 1
    }
}

# ---------------------------------------------------------------------------
# Ejecutar test
# ---------------------------------------------------------------------------

function Invoke-Tests {
    param([int]$Verbosity = 2)

    Write-Bold "═══════════════════════════════════════════════════════════"
    Write-Bold "  FASE 1: Ejecutando suite de tests"
    Write-Bold "═══════════════════════════════════════════════════════════"
    Write-Host ""
    Write-Host "  Python: $(Get-Command python | Select-Object -ExpandProperty Source)" -ForegroundColor DarkGray
    Write-Host "  Directorio: $script:ScriptDir" -ForegroundColor DarkGray
    Write-Host "  Verbosidad: $Verbosity" -ForegroundColor DarkGray
    Write-Host ""

    Push-Location $script:ScriptDir
    try {
        $tmpFile = [System.IO.Path]::GetTempFileName()

        # Trap de limpieza
        try {
            python -m pytest --verbosity $Verbosity 2>&1 | Tee-Object -FilePath $tmpFile
            $testExit = $LASTEXITCODE
            $testOutput = Get-Content $tmpFile -Raw

            Write-Host ""

            # Contar resultados (formato pytest)
            $total = 0
            $passedCount = 0
            $failedCount = 0
            $errorCount = 0

            # Buscar línea de resumen: "5 passed, 2 failed in 0.5s" o similar
            if ($testOutput -match "=+ .* in [0-9.]+s =+") {
                if ($testOutput -match "(\d+) passed") {
                    $passedCount = [int]$Matches[1]
                }
                if ($testOutput -match "(\d+) failed") {
                    $failedCount = [int]$Matches[1]
                }
                if ($testOutput -match "(\d+) error") {
                    $errorCount = [int]$Matches[1]
                }
                $total = $passedCount + $failedCount + $errorCount
            }

            # Contar líneas FAILED y ERROR (formato pytest)
            $failedCount = ([regex]::Matches($testOutput, "(?m)^FAILED ")).Count
            $errorCount = ([regex]::Matches($testOutput, "(?m)^ERROR ")).Count

            # ============================================================
            # SI TODO PASÓ
            # ============================================================
            if ($testExit -eq 0) {
                Write-Bold "═══════════════════════════════════════════════════════════"
                Write-Green "  ✓ TODOS LOS TEST PASARON"
                Write-Green "    Total: $total tests ejecutados"
                Write-Green "    Estado: OK"
                Write-Bold "═══════════════════════════════════════════════════════════"
                Write-Host ""
                Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
                return $true
            }

            # ============================================================
            # SI HAY FALLOS — ANÁLISIS DETALLADO
            # ============================================================

            Write-Host ""
            Write-Red "╔══════════════════════════════════════════════════════════════╗"
            Write-Red "║  ✗ ALGUNOS TEST FALLARON — EL SERVIDOR NO SE ENCIENDE      ║"
            Write-Red "╚══════════════════════════════════════════════════════════════╝"
            Write-Host ""

            # Resumen numérico
            Write-Bold "  ┌─────────────────────────────────────┐"
            Write-Bold "  │  RESUMEN DE LA EJECUCIÓN            │"
            Write-Bold "  └─────────────────────────────────────┘"
            Write-Host ""
            Write-Cyan "    Tests ejecutados:  $total"
            if ($failedCount -gt 0) {
                Write-Red "    Tests fallidos:    $failedCount"
            }
            if ($errorCount -gt 0) {
                Write-Red "    Errores graves:    $errorCount"
            }
            Write-Host ""

            # ============================================================
            # DETALLE DE CADA TEST QUE FALLÓ
            # ============================================================

            if ($failedCount -gt 0 -or $errorCount -gt 0) {
                Write-Bold "  ┌─────────────────────────────────────┐"
                Write-Bold "  │  DETALLE DE CADA ERROR              │"
                Write-Bold "  └─────────────────────────────────────┘"
                Write-Host ""

                $failNum = 0
                $lines = $testOutput -split "`n"

                for ($i = 0; $i -lt $lines.Count; $i++) {
                    $line = $lines[$i]

                    if ($line -match "^(FAILED|ERROR) ") {
                        $failNum++
                        # Parsear formato pytest: "FAILED rassa/tests/test_file.py::test_name - AssertionError"
                        $testName = $line -replace "^(FAILED|ERROR) ", "" -replace " - .*", ""
                        $isError = $line -match "^ERROR "

                        if ($isError) {
                            Write-Red "  ━━━ ERROR GRAVE #$failNum ━━━━━━━━━━━━━━━━━━━━━━━"
                        } else {
                            Write-Red "  ━━━ ERROR #$failNum ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                        }
                        Write-Host ""
                        Write-Bold "    Test: $testName"

                        if ($isError) {
                            Write-Yellow "    (Este es un error GRAVE — el test ni siquiera pudo ejecutarse)"
                        }
                        Write-Host ""

                        # Extraer traceback (buscar bloque antes de esta línea)
                        $traceback = @()
                        $testFile = ($testName -split "::")[0] -replace "\.", "/" -replace "$", ".py"

                        # Buscar el bloque de traceback que contiene el archivo
                        for ($j = [Math]::Max(0, $i - 30); $j -lt $i; $j++) {
                            $tl = $lines[$j]
                            if ($tl -match "^_{3,}" -and $j -gt 0) {
                                # Inicio de un bloque de traceback
                                for ($k = $j; $k -lt $i; $k++) {
                                    $traceback += $lines[$k]
                                }
                                break
                            }
                        }

                        if ($traceback.Count -gt 0) {
                            Write-Cyan "    ¿Qué falló?"
                            $traceback | Select-Object -First 30 | ForEach-Object {
                                if ($_ -match "AssertionError|assert|FAIL") {
                                    Write-Red "      $_"
                                } elseif ($_ -match "Error|Exception|Traceback") {
                                    Write-Red "      $_"
                                } elseif ($_ -match "File """) {
                                    Write-Host "      $_" -ForegroundColor DarkGray
                                } else {
                                    Write-Host "      $_"
                                }
                            }
                            Write-Host ""
                        }

                        # Explicación simple
                        $tracebackText = $traceback -join " "
                        Write-Cyan "    ¿Qué significa?"
                        if ($tracebackText -match "AssertionError|assert") {
                            Write-Host "      El test esperaba un resultado pero obtuvo otro."
                            Write-Host "      Algo en tu código cambió el comportamiento esperado."
                        } elseif ($tracebackText -match "ImportError|ModuleNotFoundError") {
                            Write-Host "      Falta una librería o el import está mal escrito."
                        } elseif ($tracebackText -match "TypeError") {
                            Write-Host "      Estás pasando un tipo de dato incorrecto a una función."
                        } elseif ($tracebackText -match "AttributeError") {
                            Write-Host "      Estás usando un atributo o método que no existe."
                        } elseif ($tracebackText -match "IntegrityError|unique") {
                            Write-Host "      Estás creando un registro duplicado que debería ser único."
                        } elseif ($tracebackText -match "SyntaxError") {
                            Write-Host "      Tu código tiene un error de sintaxis (falta ':', paréntesis, etc.)"
                        } elseif ($tracebackText -match "NameError") {
                            Write-Host "      Estás usando una variable o función que no existe."
                        } elseif ($tracebackText -match "OperationalError|connection") {
                            Write-Host "      No se pudo conectar a la base de datos."
                            Write-Host "      Verifica que PostgreSQL esté corriendo."
                        } else {
                            Write-Host "      Revisa el traceback arriba para entender el problema."
                        }
                        Write-Host ""

                        # Archivo con el error
                        $fileMatch = ($traceback | Where-Object { $_ -match 'File "' } | Select-Object -Last 1)
                        if ($fileMatch) {
                            $filePath = [regex]::Match($fileMatch, 'File "([^"]+)"').Groups[1].Value
                            $lineNum = [regex]::Match($fileMatch, 'line (\d+)').Groups[1].Value
                            Write-Cyan "    Archivo con el error:"
                            Write-Host "      $filePath"
                            if ($lineNum) {
                                Write-Host "      Línea: $lineNum"
                            }
                            Write-Host ""
                        }

                        # Cómo arreglar
                        Write-Cyan "    Cómo arreglar:"
                        if ($tracebackText -match "AssertionError") {
                            Write-Host "      1. Abre el archivo indicado arriba"
                            Write-Host "      2. Busca la línea del error"
                            Write-Host "      3. Compara lo que el test espera vs lo que tu código devuelve"
                            Write-Host "      4. Corrige tu código para que pase el test"
                        } elseif ($tracebackText -match "ImportError|ModuleNotFoundError") {
                            Write-Host "      1. Verifica que el módulo esté en requirements.txt"
                            Write-Host "      2. Ejecuta: pip install -r requirements.txt"
                            Write-Host "      3. Revisa que el import en el archivo sea correcto"
                        } elseif ($tracebackText -match "SyntaxError") {
                            Write-Host "      1. Abre el archivo indicado"
                            Write-Host "      2. Busca la línea con el error de sintaxis"
                            Write-Host "      3. Agrega el ':' o paréntesis que falta"
                        } elseif ($tracebackText -match "IntegrityError|unique") {
                            Write-Host "      1. No crees el mismo registro dos veces en el test"
                            Write-Host "      2. Usa get_or_create() en vez de create()"
                        } elseif ($tracebackText -match "OperationalError|connection") {
                            Write-Host "      1. Verifica que PostgreSQL esté corriendo"
                            Write-Host "      2. Revisa DATABASE_URL en .env"
                        } else {
                            Write-Host "      1. Lee el traceback completo arriba"
                            Write-Host "      2. Busca la línea exacta del error en el archivo"
                            Write-Host "      3. Corrige el problema"
                            Write-Host "      4. Vuelve a ejecutar: .\start.ps1"
                        }
                        Write-Host ""
                    }
                }
            }

            # ============================================================
            # INSTRUCCIONES FINALES
            # ============================================================

            Write-Red "╔══════════════════════════════════════════════════════════════╗"
            Write-Red "║  EL SERVIDOR NO SE ENCIENDE HASTA QUE TODOS LOS TEST       ║"
            Write-Red "║  PASEN. Corrige los errores de arriba y vuelve a intentar. ║"
            Write-Red "╚══════════════════════════════════════════════════════════════╝"
            Write-Host ""
            Write-Bold "  Resumen de acciones:"
            Write-Host ""
            Write-Host "    1. Lee CADA error de arriba (están explicados)"
            Write-Host "    2. Abre el archivo indicado en cada error"
            Write-Host "    3. Corrige el problema"
            Write-Host "    4. Vuelve a ejecutar: .\start.ps1"
            Write-Host ""
            Write-Host "  Si necesitas ver los test sin encender el servidor:" -ForegroundColor DarkGray
            Write-Host "    .\start.ps1 -TestOnly" -ForegroundColor DarkGray
            Write-Host "  Si necesitas máximo detalle:" -ForegroundColor DarkGray
            Write-Host "    .\start.ps1 -TestOnly -Verbose" -ForegroundColor DarkGray
            Write-Host ""

            return $false
        } finally {
            Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
        }
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# Encender servidor
# ---------------------------------------------------------------------------

function Start-Server {
    Push-Location $script:ScriptDir
    try {
        Write-Green "╔══════════════════════════════════════════════════════════╗"
        Write-Green "║  ✓ Tests pasaron — encendiendo servidor...              ║"
        Write-Green "╚══════════════════════════════════════════════════════════╝"
        Write-Host ""
        Write-Host "  API: http://localhost:8000/api/"
        Write-Host ""
        Write-Host "  Usuarios de prueba:"
        Write-Host "    admin@rassa.com / admin123 (Administrador)"
        Write-Host "    vendedor@rassa.com / vendedor123 (Vendedor)"
        Write-Host "    juan.perez@email.com / juan123 (Agricultor)"
        Write-Host "    ana.ramirez@email.com / ana123 (Cliente)"
        Write-Host ""
        Write-Host "  Presiona Ctrl+C para detener el servidor." -ForegroundColor DarkGray
        Write-Host ""

        python manage.py runserver 0.0.0.0:8000
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------

if ($Help) {
    Show-Help
    exit 0
}

Write-Banner
Test-Prechecks
Activate-Venv

$verbosity = 2
if ($Verbose) { $verbosity = 3 }

if ($TestOnly) {
    $result = Invoke-Tests -Verbosity $verbosity
    if ($result) { exit 0 } else { exit 1 }
}

if (-not $Skip) {
    $result = Invoke-Tests -Verbosity $verbosity
    if (-not $result) {
        exit 1
    }
} else {
    Write-Yellow "AVISO: Saltando tests (-Skip). Usa esto solo en emergencias."
    Write-Host ""
}

Start-Server
