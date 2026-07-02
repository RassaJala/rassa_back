#!/bin/bash
# ============================================================================
# Rassa — Configuración del Entorno de Desarrollo
# ============================================================================
# Single-command setup: Python detection → venv → pip → PostgreSQL →
# environment → migrate → load schema → verify.
#
# Plataformas soportadas:
#   Linux     → bash setup.sh
#   macOS     → bash setup.sh
#   Windows   → bash setup.sh  (Git Bash)  o  .\setup.ps1  (PowerShell nativo)
#   Windows   → bash setup.sh  (WSL, se trata como Linux)
#
# Uso:
#   bash setup.sh          # Ejecución completa (salta fases ya completadas)
#   bash setup.sh --reset  # Ignora .setup_state, ejecuta todo de nuevo
#   bash setup.sh --help   # Muestra ayuda
#
# Estado: .setup_state guarda las fases completadas para saltarlas en re-runs.
# Log:    setup.log captura toda la salida.
# ============================================================================

set -Eeuo pipefail

SCRIPT_VERSION="1.0.0"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

LOG_FILE="${SCRIPT_DIR}/setup.log"
STATE_FILE="${SCRIPT_DIR}/.setup_state"

# Test-mode override for state functions (set by test script)
_STATE_FILE="${_STATE_FILE:-$STATE_FILE}"

MIN_PYTHON_VERSION="3.11"
CURRENT_PHASE=""

# ---------------------------------------------------------------------------
# Color helpers (testable)
# ---------------------------------------------------------------------------

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

_green()  { echo -e "${GREEN}$*${NC}"; }
_yellow() { echo -e "${YELLOW}$*${NC}"; }
_red()    { echo -e "${RED}$*${NC}"; }
_bold()   { echo -e "${BOLD}$*${NC}"; }

# ---------------------------------------------------------------------------
# Logging — all output goes to both stdout and setup.log
# ---------------------------------------------------------------------------

_setup_logging() {
    # Don't redirect in test mode
    if [[ "${SETUP_SH_TEST_MODE:-}" == "true" ]]; then
        return 0
    fi
    # Truncate log on fresh run (check before we exec redirection)
    if [[ "${1:-}" == "--reset" ]]; then
        : > "$LOG_FILE"
    fi
    exec > >(tee -a "$LOG_FILE") 2>&1
}

# ---------------------------------------------------------------------------
# OS detection (testable) — returns: linux | macos | windows-gitbash | windows-wsl | unknown
# ---------------------------------------------------------------------------

_detect_os() {
    local os_name
    os_name="$(uname -s)"
    case "$os_name" in
        Linux*)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                echo "windows-wsl"
            else
                echo "linux"
            fi
            ;;
        Darwin)  echo "macos" ;;
        CYGWIN*|MINGW*|MSYS*) echo "windows-gitbash" ;;
        *)       echo "unknown" ;;
    esac
}

_is_windows() {
    local os
    os=$(_detect_os)
    [[ "$os" == "windows-gitbash" || "$os" == "windows-wsl" ]]
}

# On Windows Git Bash, common PostgreSQL install paths (adds to PATH if found)
_find_pg_tools() {
    local -a pg_dirs=(
        "/c/Program Files/PostgreSQL/17/bin"
        "/c/Program Files/PostgreSQL/16/bin"
        "/c/Program Files/PostgreSQL/15/bin"
        "/c/Program Files/PostgreSQL/14/bin"
    )
    for dir in "${pg_dirs[@]}"; do
        if [[ -f "$dir/pg_isready.exe" ]]; then
            export PATH="$dir:$PATH"
            return 0
        fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# Python version helpers (testable)
# ---------------------------------------------------------------------------

_parse_python_version() {
    # Extract version from: "Python 3.14.6", "/path/to/versions/3.14.6/bin/python3", etc.
    local -r raw="$1"
    # Try "Python X.Y.Z" format first
    if [[ "$raw" =~ Python[[:space:]]+([0-9]+\.[0-9]+(\.[0-9]+)?) ]]; then
        echo "${BASH_REMATCH[1]}"
        return
    fi
    # Try path containing version like .../3.14.6/...
    if [[ "$raw" =~ /([0-9]+\.[0-9]+(\.[0-9]+)?)/ ]]; then
        echo "${BASH_REMATCH[1]}"
        return
    fi
    # Not recognized
    echo ""
}

_version_ge() {
    # Return 0 (true) if version $1 >= $2
    local -r v1="$1" v2="$2"
    local IFS=.
    local -a a1 a2
    read -ra a1 <<< "$v1"
    read -ra a2 <<< "$v2"
    # Pad to 3 components
    while [[ ${#a1[@]} -lt 3 ]]; do a1+=(0); done
    while [[ ${#a2[@]} -lt 3 ]]; do a2+=(0); done
    for i in 0 1 2; do
        local n1="${a1[$i]}" n2="${a2[$i]}"
        # Remove any trailing non-digits (like "a1", "rc1")
        n1="${n1//[!0-9]/}"
        n2="${n2//[!0-9]/}"
        n1="${n1:-0}"
        n2="${n2:-0}"
        if (( n1 > n2 )); then return 0; fi
        if (( n1 < n2 )); then return 1; fi
    done
    return 0  # equal
}

# ---------------------------------------------------------------------------
# State file management (testable)
# ---------------------------------------------------------------------------

_is_phase_done() {
    local -r phase="$1"
    [[ -f "$_STATE_FILE" ]] && grep -qFx "$phase=done" "$_STATE_FILE" 2>/dev/null
}

_mark_phase_done() {
    local -r phase="$1"
    if ! grep -qFx "$phase=done" "$_STATE_FILE" 2>/dev/null; then
        echo "$phase=done" >> "$_STATE_FILE"
    fi
}

_reset_state() {
    rm -f "$_STATE_FILE"
}

# ---------------------------------------------------------------------------
# Banner (testable)
# ---------------------------------------------------------------------------

_banner() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║         Rassa — Configuración del entorno  v${SCRIPT_VERSION}          ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
}

# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

_handle_error() {
    local -r exit_code="$1" line="$2"
    echo ""
    echo "$(_red "╔══════════════════════════════════════════════════════╗")"
    echo "$(_red "║  ERROR — El script falló                            ║")"
    if [[ -n "$CURRENT_PHASE" ]]; then
        echo "$(_red "║  Fase: ${CURRENT_PHASE}                                    ║")"
    fi
    echo "$(_red "║  Línea: ${line}                                          ║")"
    echo "$(_red "╚══════════════════════════════════════════════════════╝")"
    echo ""
    echo "Revisá el log completo en: $LOG_FILE"
    echo "Corregí el error y volvé a ejecutar: bash setup.sh"
    echo "  (las fases ya completadas se saltean automáticamente)"
    echo ""
    exit "$exit_code"
}

# Only set trap in production mode (not when sourced for testing)
if [[ "${SETUP_SH_TEST_MODE:-}" != "true" ]]; then
    trap '_handle_error $? $LINENO' ERR
fi

# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------

_skip_if_done() {
    local -r phase="$1"
    if _is_phase_done "$phase"; then
        echo "$(_green "✓ Fase ${phase/_/ } ya completada — saltando.")"
        echo ""
        return 0
    fi
    return 1
}

_run_phase() {
    local -r phase="$1" label="$2"
    shift 2
    CURRENT_PHASE="$phase"

    echo "$(_bold "── ${phase//_/.}: ${label} ──")"
    echo ""

    if _skip_if_done "$phase"; then
        CURRENT_PHASE=""
        return 0
    fi

    if "$@"; then
        echo ""
        echo "$(_green "✓ Fase ${phase//_/.} completada.")"
        _mark_phase_done "$phase"
        echo ""
    else
        echo ""
        echo "$(_red "✗ Fase ${phase//_/.} falló.")"
        exit 1
    fi

    CURRENT_PHASE=""
}

# ---------------------------------------------------------------------------
# Phase 1: Python detection
# ---------------------------------------------------------------------------

_phase_1_python() {
    echo "Buscando instalaciones de Python..."

    local os_name
    os_name=$(_detect_os)

    # Collect python3 results from which and pyenv
    local -a python_paths=()
    local -a python_versions=()
    local -A seen_versions

    case "$os_name" in
        windows-gitbash)
            # Use 'where' (native Windows) on Git Bash — more reliable than 'which'
            while IFS= read -r pypath; do
                [[ -n "$pypath" ]] || continue
                local ver
                ver=$("$pypath" --version 2>&1 || true)
                ver=$(_parse_python_version "$ver")
                if [[ -n "$ver" ]] && [[ -z "${seen_versions[$ver]:-}" ]]; then
                    python_paths+=("$pypath")
                    python_versions+=("$ver")
                    seen_versions[$ver]="$pypath"
                fi
            done < <({ where python 2>/dev/null; where python3 2>/dev/null; } || true)
            ;;
        *)
            # Unix: which -a python3 + pyenv
            while IFS= read -r pypath; do
                [[ -n "$pypath" ]] || continue
                local ver
                ver=$("$pypath" --version 2>&1 || true)
                ver=$(_parse_python_version "$ver")
                if [[ -n "$ver" ]] && [[ -z "${seen_versions[$ver]:-}" ]]; then
                    python_paths+=("$pypath")
                    python_versions+=("$ver")
                    seen_versions[$ver]="$pypath"
                fi
            done < <(command -v python3 2>/dev/null && which -a python3 2>/dev/null || true)

            # pyenv versions
            if command -v pyenv &>/dev/null; then
                while IFS= read -r pyline; do
                    local pyver
                    pyver=$(echo "$pyline" | sed 's/^[* ]*//' | awk '{print $1}')
                    if [[ -z "${seen_versions[$pyver]:-}" ]]; then
                        local pyp
                        pyp=$(pyenv which python3 2>/dev/null || echo "$HOME/.pyenv/versions/$pyver/bin/python3")
                        python_paths+=("$pyp")
                        python_versions+=("$pyver")
                        seen_versions[$pyver]="$pyp"
                    fi
                done < <(pyenv versions --bare 2>/dev/null || true)
            fi
            ;;
    esac

    # Filter: only ≥ MIN_PYTHON_VERSION
    local -a compatible_paths=()
    local -a compatible_versions=()
    for i in "${!python_versions[@]}"; do
        if _version_ge "${python_versions[$i]}" "$MIN_PYTHON_VERSION"; then
            compatible_paths+=("${python_paths[$i]}")
            compatible_versions+=("${python_versions[$i]}")
        fi
    done

    # No compatible Python
    if [[ ${#compatible_versions[@]} -eq 0 ]]; then
        echo "$(_red "No se encontró Python ≥ ${MIN_PYTHON_VERSION}.")"
        echo ""
        _show_python_install_guide
        return 1
    fi

    # Single compatible version — auto-select
    if [[ ${#compatible_versions[@]} -eq 1 ]]; then
        local v="${compatible_versions[0]}" p="${compatible_paths[0]}"
        echo "Python $v detectado en: $p"

        # Old but compatible
        if [[ "$v" == "$MIN_PYTHON_VERSION"* ]]; then
            echo "$(_yellow "ADVERTENCIA: Python ${MIN_PYTHON_VERSION} está en el límite mínimo.")"
            echo "Se recomienda actualizar a una versión más reciente (${MIN_PYTHON_VERSION}+)."
            echo -n "¿Querés continuar de todas formas? [s/N]: "
            read -r answer
            if [[ ! "$answer" =~ ^[sSyY] ]]; then
                return 1
            fi
        fi

        PYTHON_CMD="$p"
        return 0
    fi

    # Multiple versions — three-option menu
    echo "Se encontraron ${#compatible_versions[@]} versiones de Python compatibles:"
    echo ""
    for i in "${!compatible_versions[@]}"; do
        printf "  [%d] Python %s — %s\n" "$((i+1))" "${compatible_versions[$i]}" "${compatible_paths[$i]}"
    done
    echo ""
    echo "Opciones:"
    echo "  (a) Elegir una de la lista"
    echo "  (b) Cancelar"
    echo ""

    while true; do
        echo -n "Elegí una opción [1-${#compatible_versions[@]}/b]: "
        read -r answer
        case "$answer" in
            b|B) echo "Cancelado."; return 1 ;;
            [1-9]|[1-9][0-9])
                local idx=$((answer-1))
                if [[ $idx -ge 0 ]] && [[ $idx -lt ${#compatible_versions[@]} ]]; then
                    PYTHON_CMD="${compatible_paths[$idx]}"
                    echo "Usando Python ${compatible_versions[$idx]} (${compatible_paths[$idx]})"
                    return 0
                fi
                ;;
        esac
        echo "Opción no válida. Intentá de nuevo."
    done
}

_show_python_install_guide() {
    local os_name
    os_name=$(_detect_os)
    echo "Para instalar Python ${MIN_PYTHON_VERSION}+:"
    echo ""
    case "$os_name" in
        linux|windows-wsl)
            echo "  sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
            echo "  # o si necesitás una versión específica:"
            echo "  sudo add-apt-repository ppa:deadsnakes/ppa -y"
            echo "  sudo apt install -y python3.12 python3.12-venv" ;;
        macos)
            echo "  brew install python@3.12"
            echo "  # o con pyenv:"
            echo "  brew install pyenv && pyenv install 3.12" ;;
        windows-gitbash)
            echo "  Descargá el instalador oficial: https://www.python.org/downloads/"
            echo "  IMPORTANTE: Marcá 'Add Python to PATH' durante la instalación."
            echo "  Luego cerrá y reabrí Git Bash para que detecte el nuevo PATH." ;;
        *)
            echo "  Visitá https://www.python.org/downloads/" ;;
    esac
    echo ""
}

# ---------------------------------------------------------------------------
# Phase 2: Virtual environment
# ---------------------------------------------------------------------------

_phase_2_venv() {
    local -r py="${PYTHON_CMD:-python3}"

    if [[ -d "venv" ]]; then
        echo "$(_yellow "El entorno virtual 'venv/' ya existe.")"
        echo -n "¿Recrearlo? Se eliminará el actual. [y/N]: "
        read -r answer
        if [[ "$answer" =~ ^[sSyY] ]]; then
            echo "Eliminando venv/ existente..."
            rm -rf venv
        else
            echo "Usando venv/ existente."
            return 0
        fi
    fi

    echo "Creando entorno virtual con: $py -m venv venv"
    "$py" -m venv venv
    echo "$(_green "Entorno virtual creado en venv/")"

    # Activation note — we source in subsequent phases
    _activate_venv
}

_activate_venv() {
    if [[ -f "venv/bin/activate" ]]; then
        # shellcheck disable=SC1091
        source "venv/bin/activate"
    elif [[ -f "venv/Scripts/activate" ]]; then
        # shellcheck disable=SC1091
        source "venv/Scripts/activate"
    else
        echo "$(_red "No se encontró venv/bin/activate ni venv/Scripts/activate. ¿Se creó correctamente?")"
        return 1
    fi
    echo "  → pip: $(command -v pip)"
    echo "  → python: $(command -v python)"
}

# Unified venv activation — called by phases 3-8 (cross-platform)
_ensure_venv_active() {
    if [[ -f "venv/bin/activate" ]]; then
        # shellcheck disable=SC1091
        source "venv/bin/activate"
        return 0
    fi
    if [[ -f "venv/Scripts/activate" ]]; then
        # shellcheck disable=SC1091
        source "venv/Scripts/activate"
        return 0
    fi
    return 0  # Not fatal — phases handle missing venv gracefully
}

# ---------------------------------------------------------------------------
# Phase 3: Dependencies
# ---------------------------------------------------------------------------

_phase_3_pip() {
    _ensure_venv_active

    if [[ ! -f "requirements.txt" ]]; then
        echo "$(_red "No se encontró requirements.txt en $(pwd)")"
        return 1
    fi

    echo "Instalando dependencias desde requirements.txt..."

    if ! pip install -r requirements.txt 2>&1; then
        echo ""
        echo "$(_red "Falló la instalación de dependencias.")"
        echo "Revisá el error arriba y asegurate de que todas las dependencias"
        echo "estén disponibles para tu sistema operativo."
        return 1
    fi

    echo ""
    echo "$(_green "Dependencias instaladas exitosamente.")"
}

# ---------------------------------------------------------------------------
# Phase 4: PostgreSQL
# ---------------------------------------------------------------------------

_phase_4_postgres() {
    echo "Verificando PostgreSQL..."

    local os_name
    os_name=$(_detect_os)

    # On Windows Git Bash, probe common PostgreSQL bin dirs
    if [[ "$os_name" == "windows-gitbash" ]]; then
        _find_pg_tools
    fi

    if ! command -v pg_isready &>/dev/null; then
        echo "$(_red "PostgreSQL no está instalado o pg_isready no está en el PATH.")"
        echo ""
        _show_postgres_install_guide
        return 1
    fi

    if ! pg_isready -q 2>/dev/null; then
        echo "$(_yellow "PostgreSQL está instalado pero no está corriendo.")"
        os_name=$(_detect_os)
        echo ""
        case "$os_name" in
            linux)           echo "Iniciá PostgreSQL con: sudo systemctl start postgresql" ;;
            macos)           echo "Iniciá PostgreSQL con: brew services start postgresql@16" ;;
            windows-gitbash) echo "Iniciá PostgreSQL desde Services o: net start postgresql-x64-16" ;;
            windows-wsl)     echo "Iniciá PostgreSQL con: sudo service postgresql start" ;;
        esac
        return 1
    fi

    echo "$(_green "PostgreSQL está corriendo.")"

    # Create database if it doesn't exist
    if createdb rassa 2>/dev/null; then
        echo "$(_green "Base de datos 'rassa' creada.")"
    else
        echo "$(_yellow "La base de datos 'rassa' ya existe — continuando.")"
    fi
}

_show_postgres_install_guide() {
    local os_name
    os_name=$(_detect_os)
    echo "Para instalar PostgreSQL:"
    echo ""
    case "$os_name" in
        linux|windows-wsl)
            echo "  sudo apt update && sudo apt install -y postgresql postgresql-client"
            echo "  sudo systemctl start postgresql"
            echo "  sudo systemctl enable postgresql"
            echo ""
            echo "Luego creá el usuario postgres si no existe:"
            echo "  sudo -u postgres createuser -s \$USER" ;;
        macos)
            echo "  brew install postgresql@16"
            echo "  brew services start postgresql@16"
            echo ""
            echo "Luego creá el usuario postgres si no existe:"
            echo "  createuser -s postgres" ;;
        windows-gitbash)
            echo "  Descargá el instalador oficial: https://www.postgresql.org/download/windows/"
            echo "  Durante la instalación, anotá el puerto (default: 5432) y la contraseña de postgres."
            echo "  Asegurate de que pg_isready y createdb estén en C:\\Program Files\\PostgreSQL\\{version}\\bin\\"
            echo "  (el script detecta automáticamente las versiones 14-17 en esa ubicación)." ;;
        *)
            echo "  Visitá https://www.postgresql.org/download/" ;;
    esac
    echo ""
    echo "Una vez instalado, volvé a ejecutar: bash setup.sh"
    echo "  (las fases ya completadas se saltean automáticamente)"
}

# ---------------------------------------------------------------------------
# Phase 5: Environment variables
# ---------------------------------------------------------------------------

_phase_5_env() {
    _ensure_venv_active

    if [[ ! -f ".env" ]]; then
        if [[ -f ".env.template" ]]; then
            cp .env.template .env
            echo "$(_green ".env creado desde .env.template.")"
        else
            echo "$(_red "No se encontró .env ni .env.template.")"
            return 1
        fi
    else
        echo ".env ya existe."
    fi

    # Validate required variables
    echo ""
    echo "Validando variables de entorno..."

    local has_warnings=false

    if ! grep -qE '^SECRET_KEY=.+' .env 2>/dev/null; then
        echo "$(_yellow "⚠ ADVERTENCIA: SECRET_KEY no está definido en .env")"
        has_warnings=true
    fi

    if grep -qE '^SECRET_KEY=changeme' .env 2>/dev/null; then
        echo "$(_yellow "⚠ ADVERTENCIA: SECRET_KEY tiene el valor por defecto 'changeme'.")"
        echo "             Cambialo por una clave segura en producción."
        has_warnings=true
    fi

    if ! grep -qE '^DATABASE_URL=.+' .env 2>/dev/null; then
        echo "$(_yellow "⚠ ADVERTENCIA: DATABASE_URL no está definido en .env")"
        has_warnings=true
    fi

    if [[ "$has_warnings" == "true" ]]; then
        echo ""
        echo "$(_yellow "Se encontraron advertencias pero el script puede continuar.")"
    fi
}

# ---------------------------------------------------------------------------
# Phase 6: Django migrations
# ---------------------------------------------------------------------------

_phase_6_migrate() {
    _ensure_venv_active

    echo "Aplicando migraciones de Django..."

    if python manage.py migrate --noinput 2>&1; then
        echo ""
        echo "$(_green "Migraciones aplicadas exitosamente.")"
    else
        echo ""
        echo "$(_red "Falló la migración. Revisá la conexión a la base de datos.")"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Phase 7: Schema load
# ---------------------------------------------------------------------------

_phase_7_schema() {
    _ensure_venv_active

    echo "Cargando esquema SQL (32 tablas + seeders)..."

    if python manage.py load_rassa_schema 2>&1; then
        echo ""
        echo "$(_green "Esquema cargado exitosamente.")"
    else
        echo ""
        echo "$(_red "Falló la carga del esquema.")"
        echo "Podés reintentar con: python manage.py load_rassa_schema --reset"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Phase 8: Verification
# ---------------------------------------------------------------------------

_phase_8_verify() {
    _ensure_venv_active

    echo "Verificando configuración de Django..."

    # System check
    if python manage.py check --deploy 2>&1; then
        echo ""
        echo "$(_green "✓ check --deploy: SIN ERRORES CRÍTICOS")"
    else
        echo "$(_yellow "⚠ check --deploy encontró advertencias (no bloqueantes).")"
    fi

    echo ""

    # Brief runserver test
    echo "Probando arranque del servidor (3 segundos)..."
    python manage.py runserver --noreload 2>&1 &
    local server_pid=$!
    sleep 3

    # Check if it responded
    local server_ok=false
    if kill -0 "$server_pid" 2>/dev/null; then
        if command -v curl &>/dev/null; then
            if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/ 2>/dev/null | grep -q "2..\|3..\|4.."; then
                echo "$(_green "✓ Servidor responde en http://localhost:8000/api/")"
                server_ok=true
            fi
        fi
    fi

    # Kill the server
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true

    if [[ "$server_ok" != "true" ]]; then
        echo "$(_yellow "⚠ No se pudo verificar el servidor (puede ser normal si curl no está instalado).")"
    fi

    echo ""
    echo "$(_green "╔══════════════════════════════════════════════════════════╗")"
    echo "$(_green "║  ✓ Setup completo — proyecto listo                      ║")"
    echo "$(_green "╚══════════════════════════════════════════════════════════╝")"
    echo ""
    echo "Para iniciar el servidor:"
    echo "  source venv/bin/activate"
    echo "  python manage.py runserver"
    echo ""
    echo "La API estará disponible en: http://localhost:8000/api/"
    echo ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_usage() {
    cat <<EOF
Uso: bash setup.sh [OPCIONES]

Opciones:
  --reset   Ignora .setup_state y ejecuta todas las fases de nuevo.
  --help    Muestra esta ayuda.

Sin opciones, el script ejecuta solo las fases que no se hayan completado
anteriormente (según .setup_state).

Plataformas: Linux | macOS | Windows (Git Bash / WSL)
En Windows PowerShell nativo usá: .\\setup.ps1

Log: setup.log
EOF
}

_main() {
    local force_reset=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --reset)  force_reset=true ;;
            --help)   _usage; exit 0 ;;
            *)        echo "Opción desconocida: $1"; _usage; exit 1 ;;
        esac
        shift
    done

    if [[ "$force_reset" == "true" ]]; then
        _reset_state
        : > "$LOG_FILE"
    fi

    _setup_logging

    _banner

    _run_phase "phase_1" "Detección de Python" _phase_1_python
    _run_phase "phase_2" "Entorno virtual" _phase_2_venv
    _run_phase "phase_3" "Dependencias" _phase_3_pip
    _run_phase "phase_4" "PostgreSQL" _phase_4_postgres
    _run_phase "phase_5" "Variables de entorno" _phase_5_env
    _run_phase "phase_6" "Migraciones Django" _phase_6_migrate
    _run_phase "phase_7" "Carga de esquema SQL" _phase_7_schema
    _run_phase "phase_8" "Verificación final" _phase_8_verify
}

# ---------------------------------------------------------------------------
# Entry point — skip if being sourced for testing
# ---------------------------------------------------------------------------

if [[ "${SETUP_SH_TEST_MODE:-}" != "true" ]]; then
    _main "$@"
fi
