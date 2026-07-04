#!/bin/bash
# ============================================================================
# Rassa — Configuración del Entorno de Desarrollo
# ============================================================================
# Setup interactivo: Python → venv → dependencias → PostgreSQL →
# .env (SECRET_KEY + DATABASE_URL) → migrate → seed → verify.
#
# Plataformas soportadas:
#   Linux     → bash setup.sh
#   macOS     → bash setup.sh
#   Windows   → bash setup.sh  (Git Bash / WSL)
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

SCRIPT_VERSION="2.0.0"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

LOG_FILE="${SCRIPT_DIR}/setup.log"
STATE_FILE="${SCRIPT_DIR}/.setup_state"
_STATE_FILE="${_STATE_FILE:-$STATE_FILE}"

MIN_PYTHON_VERSION="3.12"
CURRENT_PHASE=""
server_pid=""

# ---------------------------------------------------------------------------
# Cleanup trap
# ---------------------------------------------------------------------------
_cleanup() {
    local code=$?
    [[ -n "${server_pid:-}" ]] && kill "$server_pid" 2>/dev/null || true
    exit "$code"
}
trap _cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

_green()  { echo -e "${GREEN}$*${NC}"; }
_yellow() { echo -e "${YELLOW}$*${NC}"; }
_red()    { echo -e "${RED}$*${NC}"; }
_bold()   { echo -e "${BOLD}$*${NC}"; }

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_setup_logging() {
    if [[ "${SETUP_SH_TEST_MODE:-}" == "true" ]]; then
        return 0
    fi
    if [[ "${1:-}" == "--reset" ]]; then
        : > "$LOG_FILE"
    fi
}

_log() {
    echo "$@"
    echo "$@" >> "$LOG_FILE"
}

# ---------------------------------------------------------------------------
# OS detection
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

_find_pg_tools() {
    local -a base_dirs=("/c/Program Files" "/c/Program Files (x86)")
    for base in "${base_dirs[@]}"; do
        for ver in $(seq 10 99); do
            local dir="$base/PostgreSQL/$ver/bin"
            if [[ -f "$dir/pg_isready.exe" ]]; then
                export PATH="$dir:$PATH"
                return 0
            fi
        done
    done
    return 1
}

# ---------------------------------------------------------------------------
# Python version helpers
# ---------------------------------------------------------------------------

_parse_python_version() {
    local -r raw="$1"
    if [[ "$raw" =~ Python[[:space:]]+([0-9]+\.[0-9]+(\.[0-9]+)?) ]]; then
        echo "${BASH_REMATCH[1]}"
        return
    fi
    if [[ "$raw" =~ /([0-9]+\.[0-9]+(\.[0-9]+)?)/ ]]; then
        echo "${BASH_REMATCH[1]}"
        return
    fi
    echo ""
}

_version_ge() {
    local -r v1="$1" v2="$2"
    local IFS=.
    local -a a1 a2
    read -ra a1 <<< "$v1"
    read -ra a2 <<< "$v2"
    local i
    # Pad to 3 components
    while [[ ${#a1[@]} -lt 3 ]]; do a1+=(0); done
    while [[ ${#a2[@]} -lt 3 ]]; do a2+=(0); done
    for i in 0 1 2; do
        local n1="${a1[$i]}" n2="${a2[$i]}"
        n1="${n1//[!0-9]/}"
        n2="${n2//[!0-9]/}"
        n1="${n1:-0}"
        n2="${n2:-0}"
        if (( n1 > n2 )); then return 0; fi
        if (( n1 < n2 )); then return 1; fi
    done
    return 0
}

# ---------------------------------------------------------------------------
# State file management
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
# Banner
# ---------------------------------------------------------------------------

_banner() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║         Rassa — Configuración del entorno  v${SCRIPT_VERSION}            ║"
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
        return 1
    fi

    CURRENT_PHASE=""
}

# ---------------------------------------------------------------------------
# Phase 1: Python detection
# ---------------------------------------------------------------------------

_phase_1_python() {
    _log "Buscando instalaciones de Python..."

    local os_name
    os_name=$(_detect_os)

    # Usar un array asociativo para emparejar versiones con rutas
    declare -A version_to_path
    local -a all_versions=()

    case "$os_name" in
        windows-gitbash)
            while IFS= read -r pypath; do
                [[ -n "$pypath" ]] || continue
                local ver
                ver=$("$pypath" --version 2>&1 || true)
                ver=$(_parse_python_version "$ver")
                if [[ -n "$ver" ]] && [[ -z "${version_to_path[$ver]:-}" ]]; then
                    version_to_path[$ver]="$pypath"
                    all_versions+=("$ver")
                fi
            done < <({ where python 2>/dev/null; where python3 2>/dev/null; } || true)
            ;;
        *)
            while IFS= read -r pypath; do
                [[ -n "$pypath" ]] || continue
                local ver
                ver=$("$pypath" --version 2>&1 || true)
                ver=$(_parse_python_version "$ver")
                if [[ -n "$ver" ]] && [[ -z "${version_to_path[$ver]:-}" ]]; then
                    version_to_path[$ver]="$pypath"
                    all_versions+=("$ver")
                fi
            done < <(command -v python3 2>/dev/null && which -a python3 2>/dev/null || true)

            if command -v pyenv &>/dev/null; then
                while IFS= read -r pyline; do
                    local pyver
                    pyver=$(echo "$pyline" | sed 's/^[* ]*//' | awk '{print $1}')
                    if [[ -n "$pyver" ]] && [[ -z "${version_to_path[$pyver]:-}" ]]; then
                        local pyp
                        pyp=$(PYENV_VERSION="$pyver" pyenv which python3 2>/dev/null || echo "$HOME/.pyenv/versions/$pyver/bin/python3")
                        version_to_path[$pyver]="$pyp"
                        all_versions+=("$pyver")
                    fi
                done < <(pyenv versions --bare 2>/dev/null || true)
            fi
            ;;
    esac

    # Filtrar versiones compatibles
    local -a compatible_versions=()
    local -a compatible_paths=()
    for ver in "${all_versions[@]}"; do
        local path="${version_to_path[$ver]}"
        if [[ -n "$path" ]] && _version_ge "$ver" "$MIN_PYTHON_VERSION"; then
            compatible_versions+=("$ver")
            compatible_paths+=("$path")
        fi
    done

    if [[ ${#compatible_versions[@]} -eq 0 ]]; then
        echo "$(_red "No se encontró Python ≥ ${MIN_PYTHON_VERSION}.")"
        echo ""
        _show_python_install_guide
        return 1
    fi

    if [[ ${#compatible_versions[@]} -eq 1 ]]; then
        local v="${compatible_versions[0]}" p="${compatible_paths[0]}"
        echo "Python $v detectado en: $p"

        if [[ "$v" == "$MIN_PYTHON_VERSION"* ]]; then
            echo "$(_yellow "ADVERTENCIA: Python ${MIN_PYTHON_VERSION} está en el límite mínimo.")"
            echo "Se recomienda actualizar a una versión más reciente."
            echo -n "¿Querés continuar de todas formas? [s/N]: "
            [[ -t 0 ]] && read -r answer || answer="n"
            if [[ ! "$answer" =~ ^[sSyY] ]]; then
                return 1
            fi
        fi

        PYTHON_CMD="$p"
        return 0
    fi

    echo "Se encontraron ${#compatible_versions[@]} versiones de Python compatibles:"
    echo ""
    for i in "${!compatible_versions[@]}"; do
        printf "  [%d] Python %s — %s\n" "$((i+1))" "${compatible_versions[$i]}" "${compatible_paths[$i]}"
    done
    echo ""

    while true; do
        echo -n "Elegí una opción [1-${#compatible_versions[@]}]: "
        [[ -t 0 ]] && read -r answer || answer="1"
        if [[ "$answer" =~ ^[1-9][0-9]*$ ]]; then
            local idx=$((answer-1))
            if [[ $idx -ge 0 ]] && [[ $idx -lt ${#compatible_versions[@]} ]]; then
                PYTHON_CMD="${compatible_paths[$idx]}"
                echo "Usando Python ${compatible_versions[$idx]}"
                return 0
            fi
        fi
        echo "Opción no válida."
    done
}

_show_python_install_guide() {
    local os_name
    os_name=$(_detect_os)
    echo "Para instalar Python ${MIN_PYTHON_VERSION}+:"
    echo ""
    case "$os_name" in
        linux|windows-wsl)
            echo "  sudo apt update && sudo apt install -y python3 python3-venv python3-pip" ;;
        macos)
            echo "  brew install python@3.12" ;;
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

    # Verificar si ya existe un venv (venv o .venv)
    if [[ -d "venv" ]] || [[ -d ".venv" ]]; then
        local venv_dir="venv"
        [[ -d ".venv" ]] && venv_dir=".venv"
        echo "$(_yellow "El entorno virtual '${venv_dir}/' ya existe.")"
        echo -n "¿Recrearlo? Se eliminará el actual. [y/N]: "
        [[ -t 0 ]] && read -r answer || answer="n"
        if [[ "$answer" =~ ^[sSyY] ]]; then
            echo "Eliminando ${venv_dir}/ existente..."
            rm -rf venv .venv
            echo "Reseteando fases dependientes del venv..."
            for p in phase_3 phase_4 phase_5 phase_6 phase_7 phase_8; do
                sed -i "/^${p}=done$/d" "$_STATE_FILE" 2>/dev/null
            done
        else
            echo "Usando ${venv_dir}/ existente."
            _activate_venv
            return 0
        fi
    fi

    echo "Creando entorno virtual con: $py -m venv venv"
    if ! "$py" -m venv venv 2>&1; then
        echo "$(_yellow "Falló venv. python3-venv no está instalado.")"
        echo -n "Intentar instalar python3-venv? (requiere sudo) [s/N]: "
        read -r answer
        if [[ "$answer" =~ ^[sSyY] ]]; then
            sudo apt install -y python3-venv && "$py" -m venv venv
        else
            echo "Intentá: pip install virtualenv && virtualenv venv"
            return 1
        fi
    fi
    _log "$(_green "Entorno virtual creado en venv/")"
    _activate_venv
}

_activate_venv() {
    if [[ -f "venv/bin/activate" ]]; then
        source "venv/bin/activate"
    elif [[ -f ".venv/bin/activate" ]]; then
        source ".venv/bin/activate"
    elif [[ -f "venv/Scripts/activate" ]]; then
        source "venv/Scripts/activate"
    elif [[ -f ".venv/Scripts/activate" ]]; then
        source ".venv/Scripts/activate"
    else
        echo "$(_red "No se encontró activate. ¿Se creó correctamente el venv?")"
        return 1
    fi
    echo "  → python: $(command -v python)"
    echo "  → pip: $(command -v pip)"
}

_ensure_venv_active() {
    if [[ -f "venv/bin/activate" ]]; then
        source "venv/bin/activate"
        return 0
    fi
    if [[ -f ".venv/bin/activate" ]]; then
        source ".venv/bin/activate"
        return 0
    fi
    if [[ -f "venv/Scripts/activate" ]]; then
        source "venv/Scripts/activate"
        return 0
    fi
    if [[ -f ".venv/Scripts/activate" ]]; then
        source ".venv/Scripts/activate"
        return 0
    fi
    echo "$(_yellow "Advertencia: No se encontró venv/activate. Algunas fases pueden fallar.")"
    return 0
}

# ---------------------------------------------------------------------------
# Phase 3: Dependencies
# ---------------------------------------------------------------------------

_phase_3_deps() {
    _ensure_venv_active

    # Detectar si el venv fue creado por uv
    local uv_created=false
    if [[ -f ".venv/pyvenv.cfg" ]] && grep -q "uv" .venv/pyvenv.cfg 2>/dev/null; then
        uv_created=true
    fi
    if [[ -f "venv/pyvenv.cfg" ]] && grep -q "uv" venv/pyvenv.cfg 2>/dev/null; then
        uv_created=true
    fi

    if [[ "$uv_created" == "true" ]]; then
        echo "$(_yellow "El venv fue creado por uv. Se usará uv automáticamente.")"
        dep_choice=2
    else
        echo "¿Cómo querés instalar las dependencias?"
        echo ""
        echo "  [1] pip (requirements.txt)"
        echo "  [2] uv (pyproject.toml)"
        echo ""
        echo -n "Elegí una opción [1/2]: "
        [[ -t 0 ]] && read -r dep_choice || dep_choice="1"
    fi

    case "$dep_choice" in
        2)
            if ! command -v uv &>/dev/null; then
                echo "$(_yellow "uv no está instalado. Instalando con pip...")"
                pip install uv
            fi
            _log "Instalando dependencias con uv..."
            if ! uv sync 2>&1; then
                echo "$(_red "Falló la instalación con uv.")"
                return 1
            fi
            ;;
        *)
            if [[ ! -f "requirements.txt" ]]; then
                echo "$(_red "No se encontró requirements.txt")"
                return 1
            fi
            _log "Instalando dependencias con pip..."
            if ! pip install -r requirements.txt 2>&1; then
                echo "$(_red "Falló la instalación de dependencias.")"
                return 1
            fi
            ;;
    esac

    echo ""
    _log "$(_green "Dependencias instaladas exitosamente.")"
}

# ---------------------------------------------------------------------------
# Phase 4: PostgreSQL
# ---------------------------------------------------------------------------

_phase_4_postgres() {
    _log "Verificando PostgreSQL..."

    local os_name
    os_name=$(_detect_os)

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
        echo ""
        case "$os_name" in
            linux)           echo "Iniciá PostgreSQL con: sudo systemctl start postgresql" ;;
            macos)           echo "Iniciá PostgreSQL con: brew services start postgresql@16" ;;
            windows-gitbash) echo "Iniciá PostgreSQL desde Services o: net start postgresql-x64-16" ;;
            windows-wsl)     echo "Iniciá PostgreSQL con: sudo service postgresql start" ;;
        esac
        return 1
    fi

    _log "$(_green "PostgreSQL está corriendo.")"
}

_show_postgres_install_guide() {
    local os_name
    os_name=$(_detect_os)
    echo "Para instalar PostgreSQL:"
    echo ""
    case "$os_name" in
        linux|windows-wsl)
            echo "  sudo apt update && sudo apt install -y postgresql postgresql-client" ;;
        macos)
            echo "  brew install postgresql@16" ;;
        *)
            echo "  Visitá https://www.postgresql.org/download/" ;;
    esac
    echo ""
}

# ---------------------------------------------------------------------------
# Phase 5: Environment variables (.env)
# ---------------------------------------------------------------------------

_phase_5_env() {
    _ensure_venv_active

    _log "Configuración del archivo .env"
    echo ""

    # --- SECRET_KEY ---
    local secret_key=""
    if [[ -f ".env" ]] && grep -qE '^SECRET_KEY=' .env 2>/dev/null; then
        secret_key=$(grep '^SECRET_KEY=' .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    fi

    if [[ -z "$secret_key" || "$secret_key" == "changeme" ]]; then
        _log "Generando SECRET_KEY segura..."
        _ensure_venv_active
        secret_key=$(python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" 2>/dev/null || true)
        if [[ -z "$secret_key" ]]; then
            echo "$(_yellow "No se pudo generar SECRET_KEY automáticamente.")"
            echo -n "Ingresá una SECRET_KEY manualmente (o Enter para usar 'changeme'): "
            [[ -t 0 ]] && read -r secret_key || secret_key="changeme"
            secret_key="${secret_key:-changeme}"
        fi
        _log "$(_green "SECRET_KEY generada.")"
    else
        _log "SECRET_KEY ya está configurada."
    fi

    # --- DATABASE_URL ---
    echo ""
    _log "Configuración de PostgreSQL:"
    echo ""

    local db_host="localhost"
    local db_port="5432"
    local db_name="rassa_jala_db"
    local db_user="postgres"
    local db_pass=""

    if [[ -f ".env" ]] && grep -qE '^DATABASE_URL=.+' .env 2>/dev/null; then
        echo "DATABASE_URL actual: $(grep '^DATABASE_URL=' .env | cut -d'=' -f2-)"
        echo -n "¿Querés reconfigurar la base de datos? [y/N]: "
        [[ -t 0 ]] && read -r reconfig || reconfig="n"
        if [[ ! "$reconfig" =~ ^[sSyY] ]]; then
            echo "Manteniendo configuración actual."
            _write_env_file "$secret_key"
            return 0
        fi
    fi

    echo -n "Host [${db_host}]: "
    [[ -t 0 ]] && read -r input || input=""
    db_host="${input:-$db_host}"

    echo -n "Puerto [${db_port}]: "
    [[ -t 0 ]] && read -r input || input=""
    db_port="${input:-$db_port}"

    echo -n "Nombre de la base de datos [${db_name}]: "
    [[ -t 0 ]] && read -r input || input=""
    db_name="${input:-$db_name}"

    echo -n "Usuario de PostgreSQL [${db_user}]: "
    [[ -t 0 ]] && read -r input || input=""
    db_user="${input:-$db_user}"

    echo -n "Contraseña de PostgreSQL: "
    [[ -t 0 ]] && read -rs db_pass || db_pass=""
    echo ""

    if [[ -z "$db_pass" ]]; then
        echo "$(_yellow "Contraseña vacía. Se usará conexión sin contraseña.")"
    fi

    # Crear base de datos si no existe
    echo ""
    _log "Creando base de datos '${db_name}' si no existe..."

    export PGPASSWORD="$db_pass"
    if psql -h "$db_host" -p "$db_port" -U "$db_user" -tc "SELECT 1 FROM pg_database WHERE datname = '${db_name}'" | grep -q 1; then
        echo "$(_yellow "La base de datos '${db_name}' ya existe.")"
    else
        if psql -h "$db_host" -p "$db_port" -U "$db_user" -c "CREATE DATABASE ${db_name}" 2>/dev/null; then
            _log "$(_green "Base de datos '${db_name}' creada.")"
        else
            echo "$(_red "No se pudo crear la base de datos.")"
            echo "Podés crearla manualmente:"
            echo "  psql -h $db_host -p $db_port -U $db_user -c \"CREATE DATABASE ${db_name};\""
            echo ""
            echo -n "¿Continuar de todas formas? [s/N]: "
            [[ -t 0 ]] && read -r answer || answer="n"
            if [[ ! "$answer" =~ ^[sSyY] ]]; then
                return 1
            fi
        fi
    fi
    unset PGPASSWORD

    # Construir DATABASE_URL
    local database_url
    if [[ -n "$db_pass" ]]; then
        database_url="postgres://${db_user}:${db_pass}@${db_host}:${db_port}/${db_name}"
    else
        database_url="postgres://${db_user}@${db_host}:${db_port}/${db_name}"
    fi

    _write_env_file "$secret_key" "$database_url"
}

_write_env_file() {
    local -r secret_key="$1"
    local -r database_url="${2:-}"

    local env_content=""
    if [[ -f ".env" ]]; then
        env_content=$(cat .env)
    fi

    # SECRET_KEY
    if [[ -n "$env_content" ]] && grep -qE '^SECRET_KEY=' .env 2>/dev/null; then
        env_content=$(echo "$env_content" | sed "s|^SECRET_KEY=.*|SECRET_KEY=\"${secret_key}\"|")
    else
        env_content="${env_content}
SECRET_KEY=\"${secret_key}\""
    fi

    # DATABASE_URL
    if [[ -n "$database_url" ]]; then
        if echo "$env_content" | grep -qE '^DATABASE_URL='; then
            env_content=$(echo "$env_content" | sed "s|^DATABASE_URL=.*|DATABASE_URL=${database_url}|")
        else
            env_content="${env_content}
DATABASE_URL=${database_url}"
        fi
    fi

    # Defaults
    if ! echo "$env_content" | grep -qE '^DEBUG='; then
        env_content="${env_content}
DEBUG=True"
    fi
    if ! echo "$env_content" | grep -qE '^ALLOWED_HOSTS='; then
        env_content="${env_content}
ALLOWED_HOSTS=localhost,127.0.0.1"
    fi
    if ! echo "$env_content" | grep -qE '^CORS_ALLOWED_ORIGINS='; then
        env_content="${env_content}
CORS_ALLOWED_ORIGINS=http://localhost:8081,http://localhost:19006"
    fi

    echo "$env_content" > .env
    chmod 600 .env 2>/dev/null || true
    _log "$(_green ".env configurado exitosamente.")"
}

# ---------------------------------------------------------------------------
# Phase 6: Django migrations
# ---------------------------------------------------------------------------

_phase_6_migrate() {
    _ensure_venv_active

    _log "Aplicando migraciones de Django..."

    if python manage.py migrate --noinput 2>&1; then
        echo ""
        _log "$(_green "Migraciones aplicadas exitosamente.")"
    else
        echo ""
        echo "$(_red "Falló la migración. Revisá la conexión a la base de datos en .env")"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Phase 7: Seed data
# ---------------------------------------------------------------------------

_phase_7_seed() {
    _ensure_venv_active

    _log "Cargando datos de prueba (32 tablas + seeders)..."

    if python manage.py seed_rassa_data 2>&1; then
        echo ""
        _log "$(_green "Datos de prueba cargados exitosamente.")"
    else
        echo ""
        echo "$(_red "Falló la carga de datos.")"
        echo "Podés reintentar con: python manage.py seed_rassa_data --clear"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Phase 8: Verification
# ---------------------------------------------------------------------------

_phase_8_verify() {
    _ensure_venv_active

    _log "Verificando configuración de Django..."

    if python manage.py check --deploy 2>&1; then
        echo ""
        _log "$(_green "✓ check --deploy: SIN ERRORES CRÍTICOS")"
    else
        echo "$(_yellow "⚠ check --deploy encontró advertencias (no bloqueantes).")"
    fi

    echo ""

    _log "Probando arranque del servidor (3 segundos)..."
    python manage.py runserver --noreload 2>&1 &
    server_pid=$!
    sleep 3

    local server_ok=false
    if kill -0 "$server_pid" 2>/dev/null; then
        if command -v curl &>/dev/null; then
            if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/ 2>/dev/null | grep -q "2..\|3..\|4.."; then
                echo "$(_green "✓ Servidor responde en http://localhost:8000/api/")"
                server_ok=true
            fi
        fi
    fi

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
    echo "Usuarios de prueba:"
    echo "  admin@rassa.com / admin123 (Administrador)"
    echo "  vendedor@rassa.com / vendedor123 (Vendedor)"
    echo "  juan.perez@email.com / juan123 (Agricultor)"
    echo "  ana.ramirez@email.com / ana123 (Cliente)"
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

Log: setup.log
EOF
}

_main() {
    local force_reset=false

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

    _run_phase "phase_1" "Detección de Python"     _phase_1_python
    _run_phase "phase_2" "Entorno virtual"          _phase_2_venv
    _run_phase "phase_3" "Dependencias"             _phase_3_deps
    _run_phase "phase_4" "PostgreSQL"               _phase_4_postgres
    _run_phase "phase_5" "Variables de entorno"     _phase_5_env
    _run_phase "phase_6" "Migraciones Django"       _phase_6_migrate
    _run_phase "phase_7" "Datos de prueba"          _phase_7_seed
    _run_phase "phase_8" "Verificación final"       _phase_8_verify
}

if [[ "${SETUP_SH_TEST_MODE:-}" != "true" ]]; then
    _main "$@"
fi
