#!/bin/bash
# ============================================================================
# Rassa — Iniciar el Backend
# ============================================================================
# Ejecuta los test automáticamente. Si pasan, enciende el servidor.
# Si fallan, muestra el error y NO enciende el servidor.
#
# Uso:
#   bash start.sh           # Corre test + server
#   bash start.sh --test    # Solo corre test, no enciende server
#   bash start.sh --verbose # Test con máximo detalle
#   bash start.sh --skip    # Salta test (solo para emergencias)
#   bash start.sh --help    # Muestra ayuda
#
# Plataformas: Linux | macOS | Windows (Git Bash / WSL)
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

# ---------------------------------------------------------------------------
# Colores
# ---------------------------------------------------------------------------

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

_green()  { echo -e "${GREEN}$*${NC}"; }
_yellow() { echo -e "${YELLOW}$*${NC}"; }
_red()    { echo -e "${RED}$*${NC}"; }
_cyan()   { echo -e "${CYAN}$*${NC}"; }
_bold()   { echo -e "${BOLD}$*${NC}"; }
_dim()    { echo -e "${DIM}$*${NC}"; }

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

_banner() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              Rassa — Iniciar Backend                        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
}

# ---------------------------------------------------------------------------
# Activación del entorno virtual
# ---------------------------------------------------------------------------

_activate_venv() {
    local candidates=(
        "venv/bin/activate"
        ".venv/bin/activate"
        "venv/Scripts/activate"
        ".venv/Scripts/activate"
    )

    for candidate in "${candidates[@]}"; do
        if [[ -f "$SCRIPT_DIR/$candidate" ]]; then
            # shellcheck disable=SC1090
            source "$SCRIPT_DIR/$candidate"
            # Verificar que el venv funciona
            if ! python --version &>/dev/null; then
                _red "╔══════════════════════════════════════════════════════╗"
                _red "║  ERROR — El entorno virtual está corrupto            ║"
                _red "╚══════════════════════════════════════════════════════╝"
                echo ""
                echo "  Python no funciona después de activar el venv."
                echo "  Solución: rm -rf venv .venv && bash setup.sh"
                echo ""
                exit 1
            fi
            return 0
        fi
    done

    _red "╔══════════════════════════════════════════════════════╗"
    _red "║  ERROR — No se encontró el entorno virtual           ║"
    _red "╚══════════════════════════════════════════════════════╝"
    echo ""
    echo "Ejecuta primero: bash setup.sh"
    echo ""
    exit 1
}

# ---------------------------------------------------------------------------
# Verificaciones previas
# ---------------------------------------------------------------------------

_prechecks() {
    local failed=0

    # Verificar Python
    if ! command -v python &>/dev/null && ! command -v python3 &>/dev/null; then
        _red "✗ No se encontró Python en el PATH"
        echo "  Instala Python 3.12+: https://www.python.org/downloads/"
        echo "  O activa tu venv: source venv/bin/activate"
        failed=1
    fi

    # Verificar .env
    if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
        _red "✗ No se encontró .env"
        echo "  Ejecuta: bash setup.sh"
        failed=1
    fi

    # Verificar manage.py
    if [[ ! -f "$SCRIPT_DIR/manage.py" ]]; then
        _red "✗ No se encontró manage.py"
        echo "  ¿Clonaste el repo correctamente?"
        failed=1
    fi

    if [[ $failed -eq 1 ]]; then
        echo ""
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Verificar conexión a PostgreSQL
# ---------------------------------------------------------------------------

_check_postgres() {
    # Verificar que DATABASE_URL existe en .env
    if ! grep -q "^DATABASE_URL=" "$SCRIPT_DIR/.env" 2>/dev/null; then
        _red "✗ No se encontró DATABASE_URL en .env"
        echo "  Ejecuta: bash setup.sh"
        echo ""
        exit 1
    fi

    # Intentar conectar con Python
    if ! python -c "import psycopg2; psycopg2.connect('${DATABASE_URL:-}')" 2>/dev/null; then
        if command -v pg_isready &>/dev/null; then
            if ! pg_isready -q 2>/dev/null; then
                _red "✗ PostgreSQL no está corriendo"
                echo "  Inicia PostgreSQL:"
                echo "    Linux:  sudo systemctl start postgresql"
                echo "    macOS:  brew services start postgresql@16"
                echo "    WSL:    sudo service postgresql start"
                echo ""
                exit 1
            fi
        else
            _red "✗ No se pudo conectar a PostgreSQL"
            echo "  Verifica DATABASE_URL en .env"
            echo "  Verifica que PostgreSQL esté corriendo"
            echo ""
            exit 1
        fi
    fi
}

# ---------------------------------------------------------------------------
# Funciones de análisis de errores
# ---------------------------------------------------------------------------

# Extraer traceback de un test específico
_extract_traceback() {
    local tmp_file="$1"
    local line_num="$2"
    sed -n "$((line_num+1)),\$p" "$tmp_file" \
        | sed '/^---/q' | sed '/^FAIL:/q' | sed '/^ERROR:/q' | sed '/^Ran /q' \
        | head -30
}

# Clasificar tipo de error y dar explicación
_classify_error() {
    local traceback="$1"
    local is_grave="${2:-false}"

    _cyan "    ¿Qué significa?"
    if echo "$traceback" | grep -qiE "AssertionError|assert"; then
        echo "      El test esperaba un resultado pero obtuvo otro."
        echo "      Algo en tu código cambió el comportamiento esperado."
    elif echo "$traceback" | grep -qiE "ImportError|ModuleNotFoundError"; then
        echo "      Falta una librería o el import está mal escrito."
    elif echo "$traceback" | grep -qiE "SyntaxError"; then
        echo "      Tu código tiene un error de sintaxis (falta un ':', paréntesis, etc.)"
    elif echo "$traceback" | grep -qiE "TypeError"; then
        echo "      Estás pasando un tipo de dato incorrecto a una función."
    elif echo "$traceback" | grep -qiE "AttributeError"; then
        echo "      Estás usando un atributo o método que no existe."
    elif echo "$traceback" | grep -qiE "IntegrityError|unique"; then
        echo "      Estás creando un registro duplicado que debería ser único."
    elif echo "$traceback" | grep -qiE "PermissionDenied|permission"; then
        echo "      El usuario no tiene permiso para esta acción."
    elif echo "$traceback" | grep -qiE "NameError"; then
        echo "      Estás usando una variable o función que no existe."
    elif echo "$traceback" | grep -qiE "OperationalError|connection"; then
        echo "      No se pudo conectar a la base de datos."
        echo "      Verifica que PostgreSQL esté corriendo."
    else
        if [[ "$is_grave" == "true" ]]; then
            echo "      El test falló antes de poder ejecutarse."
        else
            echo "      Revisa el traceback arriba para entender el problema."
        fi
    fi
}

# Dar instrucciones de cómo arreglar
_suggest_fix() {
    local traceback="$1"

    _cyan "    Cómo arreglar:"
    if echo "$traceback" | grep -qiE "AssertionError"; then
        echo "      1. Abre el archivo indicado arriba"
        echo "      2. Busca la línea del error"
        echo "      3. Compara lo que el test espera vs lo que tu código devuelve"
        echo "      4. Corrige tu código para que pase el test"
    elif echo "$traceback" | grep -qiE "ImportError|ModuleNotFoundError"; then
        echo "      1. Verifica que el módulo esté en requirements.txt"
        echo "      2. Ejecuta: pip install -r requirements.txt"
        echo "      3. Revisa que el import en el archivo sea correcto"
    elif echo "$traceback" | grep -qiE "SyntaxError"; then
        local file_path
        file_path=$(echo "$traceback" | grep -oE 'File "[^"]+"' | tail -1 | sed 's/File "//;s/"//' || true)
        echo "      1. Abre: ${file_path:-el archivo indicado}"
        echo "      2. Busca la línea con el error de sintaxis"
        echo "      3. Agrega el ':' o paréntesis que falta"
    elif echo "$traceback" | grep -qiE "IntegrityError|unique"; then
        echo "      1. No crees el mismo registro dos veces en el test"
        echo "      2. Usa get_or_create() en vez de create()"
    elif echo "$traceback" | grep -qiE "OperationalError|connection"; then
        echo "      1. Verifica que PostgreSQL esté corriendo"
        echo "      2. Revisa DATABASE_URL en .env"
    else
        echo "      1. Lee el traceback completo arriba"
        echo "      2. Busca la línea exacta del error en el archivo"
        echo "      3. Corrige el problema"
        echo "      4. Vuelve a ejecutar: bash start.sh"
    fi
}

# Imprimir traceback con colores
_print_traceback() {
    local traceback="$1"
    echo "$traceback" | sed 's/^/      /' | while IFS= read -r tl; do
        if echo "$tl" | grep -qE "AssertionError|assert"; then
            _red "$tl"
        elif echo "$tl" | grep -qE 'File "'; then
            _dim "$tl"
        elif echo "$tl" | grep -qE "Error|Exception|Traceback"; then
            _red "$tl"
        else
            echo "      $tl"
        fi
    done
}

# Extraer archivo y línea del traceback
_extract_file_info() {
    local traceback="$1"
    local file_path file_line
    file_path=$(echo "$traceback" | grep -oE 'File "[^"]+"' | tail -1 | sed 's/File "//;s/"//' || true)
    file_line=$(echo "$traceback" | grep -oE 'line [0-9]+' | tail -1 | sed 's/line //' || true)
    echo "$file_path|$file_line"
}

# Procesar un test fallido (FAIL o ERROR)
_process_failed_test() {
    local tmp_file="$1"
    local line_num="$2"
    local line_content="$3"
    local fail_num="$4"
    local is_grave="${5:-false}"

    local test_name
    test_name=$(echo "$line_content" | sed 's/^[^:]*: //')

    if [[ "$is_grave" == "true" ]]; then
        _red "  ━━━ ERROR GRAVE #${fail_num} ━━━━━━━━━━━━━━━━━━━━━━━"
    else
        _red "  ━━━ ERROR #${fail_num} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    fi
    echo ""
    _bold "    Test: ${test_name}"
    if [[ "$is_grave" == "true" ]]; then
        _yellow "    (Este es un error GRAVE — el test ni siquiera pudo ejecutarse)"
    fi
    echo ""

    local traceback
    traceback=$(_extract_traceback "$tmp_file" "$line_num")

    if [[ -n "$traceback" ]]; then
        _cyan "    ¿Qué falló?"
        _print_traceback "$traceback"
        echo ""
    fi

    _classify_error "$traceback" "$is_grave"
    echo ""

    local file_info
    file_info=$(_extract_file_info "$traceback")
    local file_path="${file_info%%|*}"
    local file_line="${file_info##*|}"

    if [[ -n "$file_path" ]]; then
        _cyan "    Archivo con el error:"
        echo "      ${file_path}"
        if [[ -n "$file_line" ]]; then
            echo "      Línea: ${file_line}"
        fi
        echo ""
    fi

    _suggest_fix "$traceback"
    echo ""
}

# ---------------------------------------------------------------------------
# Ejecutar test
# ---------------------------------------------------------------------------

_run_tests() {
    local verbosity="${1:-2}"

    _bold "═══════════════════════════════════════════════════════════"
    _bold "  FASE 1: Ejecutando suite de tests"
    _bold "═══════════════════════════════════════════════════════════"
    echo ""
    _dim "  Python: $(command -v python 2>/dev/null || echo 'no encontrado')"
    _dim "  Directorio: $SCRIPT_DIR"
    _dim "  Verbosidad: $verbosity"
    echo ""

    cd "$SCRIPT_DIR"

    # Archivo temporal con trap de limpieza
    local tmp_output
    tmp_output=$(mktemp)
    trap 'rm -f "$tmp_output"' EXIT

    # Ejecutar tests y capturar exit code real
    local test_exit=0
    set +e
    python -m pytest --verbosity="$verbosity" 2>&1 | tee "$tmp_output"
    test_exit=${PIPESTATUS[0]}
    set -e

    echo ""

    # Extraer total de tests
    local total=0
    local ran_line
    ran_line=$(grep "Ran " "$tmp_output" | tail -1 || true)
    if [[ -n "$ran_line" ]]; then
        total=$(echo "$ran_line" | grep -oE 'Ran [0-9]+' | grep -oE '[0-9]+' || echo "0")
    fi

    # ============================================================
    # SI TODO PASÓ
    # ============================================================
    if [[ "$test_exit" -eq 0 ]]; then
        _bold "═══════════════════════════════════════════════════════════"
        _green "  ✓ TODOS LOS TEST PASARON"
        _green "    Total: ${total} tests ejecutados"
        _green "    Estado: OK"
        _bold "═══════════════════════════════════════════════════════════"
        echo ""
        return 0
    fi

    # ============================================================
    # SI HAY FALLOS — ANÁLISIS DETALLADO
    # ============================================================

    local failed_count error_count
    failed_count=$(grep -cE "^FAIL:" "$tmp_output" 2>/dev/null || echo "0")
    error_count=$(grep -cE "^ERROR:" "$tmp_output" 2>/dev/null || echo "0")

    echo ""
    _red "╔══════════════════════════════════════════════════════════════╗"
    _red "║  ✗ ALGUNOS TEST FALLARON — EL SERVIDOR NO SE ENCIENDE      ║"
    _red "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    _bold "  ┌─────────────────────────────────────┐"
    _bold "  │  RESUMEN DE LA EJECUCIÓN            │"
    _bold "  └─────────────────────────────────────┘"
    echo ""
    _cyan "    Tests ejecutados:  ${total}"
    if [[ "$failed_count" -gt 0 ]]; then
        _red "    Tests fallidos:    ${failed_count}"
    fi
    if [[ "$error_count" -gt 0 ]]; then
        _red "    Errores graves:    ${error_count}"
    fi
    echo ""

    # ============================================================
    # DETALLE DE CADA TEST QUE FALLÓ
    # ============================================================

    if [[ "$failed_count" -gt 0 ]] || [[ "$error_count" -gt 0 ]]; then
        _bold "  ┌─────────────────────────────────────┐"
        _bold "  │  DETALLE DE CADA ERROR              │"
        _bold "  └─────────────────────────────────────┘"
        echo ""

        local fail_num=0

        # Procesar FAILs y ERRORs juntos (process substitution para evitar subshell)
        while IFS=: read -r line_num line_content; do
            fail_num=$((fail_num + 1))
            _process_failed_test "$tmp_output" "$line_num" "$line_content" "$fail_num" "false"
        done < <(grep -nE "^(FAIL|ERROR):" "$tmp_output" 2>/dev/null || true)

        # Marcar errores graves
        if [[ "$error_count" -gt 0 ]]; then
            while IFS=: read -r line_num line_content; do
                fail_num=$((fail_num + 1))
                _process_failed_test "$tmp_output" "$line_num" "$line_content" "$fail_num" "true"
            done < <(grep -nE "^ERROR:" "$tmp_output" 2>/dev/null || true)
        fi
    fi

    # ============================================================
    # INSTRUCCIONES FINALES
    # ============================================================

    _red "╔══════════════════════════════════════════════════════════════╗"
    _red "║  EL SERVIDOR NO SE ENCIENDE HASTA QUE TODOS LOS TEST       ║"
    _red "║  PASEN. Corrige los errores de arriba y vuelve a intentar. ║"
    _red "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    _bold "  Resumen de acciones:"
    echo ""
    echo "    1. Lee CADA error de arriba (están explicados)"
    echo "    2. Abre el archivo indicado en cada error"
    echo "    3. Corrige el problema"
    echo "    4. Vuelve a ejecutar: bash start.sh"
    echo ""
    _dim "  Si necesitas ver los test sin encender el servidor:"
    _dim "    bash start.sh --test"
    _dim "  Si necesitas máximo detalle:"
    _dim "    bash start.sh --test --verbose"
    echo ""

    return 1
}

# ---------------------------------------------------------------------------
# Encender servidor
# ---------------------------------------------------------------------------

_start_server() {
    cd "$SCRIPT_DIR"

    _green "╔══════════════════════════════════════════════════════════╗"
    _green "║  ✓ Tests pasaron — encendiendo servidor...              ║"
    _green "╚══════════════════════════════════════════════════════════╝"
    echo ""
    echo "  API: http://localhost:8000/api/"
    echo ""
    echo "  Usuarios de prueba:"
    echo "    admin@rassa.com / admin123 (Administrador)"
    echo "    vendedor@rassa.com / vendedor123 (Vendedor)"
    echo "    juan.perez@email.com / juan123 (Agricultor)"
    echo "    ana.ramirez@email.com / ana123 (Cliente)"
    echo ""
    _dim "  Presiona Ctrl+C para detener el servidor."
    echo ""

    python manage.py runserver
}

# ---------------------------------------------------------------------------
# Ayuda
# ---------------------------------------------------------------------------

_usage() {
    cat <<EOF
Uso: bash start.sh [OPCIONES]

Opciones:
  (sin opciones)   Corre test (verbosity 2) + enciende el servidor
  --test           Solo corre los test (no enciende server)
  --verbose        Test con máximo detalle (verbosity 3)
  --skip           Salta los test y enciende directamente (solo emergencias)
  --help           Muestra esta ayuda

Comportamiento por defecto:
  1. Verifica que el entorno esté configurado (.env, venv, Python, PostgreSQL)
  2. Ejecuta TODOS los test del proyecto
  3. Si pasan → enciende el servidor en http://localhost:8000
  4. Si fallan → muestra qué tests fallaron y NO enciende el servidor

Ejemplos:
  bash start.sh              # Uso normal
  bash start.sh --test       # Solo correr tests
  bash start.sh --test --verbose  # Tests con máximo detalle
  bash start.sh --verbose    # Tests detallados + encender server

Plataformas: Linux | macOS | Windows (Git Bash / WSL)
EOF
}

# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------

_main() {
    local skip_tests=false
    local test_only=false
    local verbosity=2

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --skip)
                skip_tests=true
                _yellow "AVISO: Saltando tests (--skip). Usa esto solo en emergencias."
                echo ""
                ;;
            --test)
                test_only=true
                ;;
            --verbose)
                verbosity=3
                ;;
            --help)
                _usage
                exit 0
                ;;
            *)
                _red "Opción desconocida: $1"
                echo ""
                _usage
                exit 1
                ;;
        esac
        shift
    done

    _banner
    _prechecks
    _activate_venv
    _check_postgres

    if [[ "$test_only" == "true" ]]; then
        _run_tests "$verbosity"
        exit $?
    fi

    if [[ "$skip_tests" == "false" ]]; then
        if ! _run_tests "$verbosity"; then
            exit 1
        fi
    fi

    _start_server
}

_main "$@"
