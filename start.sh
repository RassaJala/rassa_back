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
    if [[ -f "$SCRIPT_DIR/venv/bin/activate" ]]; then
        source "$SCRIPT_DIR/venv/bin/activate"
        return 0
    fi
    if [[ -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
        source "$SCRIPT_DIR/.venv/bin/activate"
        return 0
    fi
    if [[ -f "$SCRIPT_DIR/venv/Scripts/activate" ]]; then
        source "$SCRIPT_DIR/venv/Scripts/activate"
        return 0
    fi
    if [[ -f "$SCRIPT_DIR/.venv/Scripts/activate" ]]; then
        source "$SCRIPT_DIR/.venv/Scripts/activate"
        return 0
    fi

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

    if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
        _red "✗ No se encontró .env"
        echo "  Ejecuta: bash setup.sh"
        failed=1
    fi

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
# Ejecutar test
# ---------------------------------------------------------------------------

_run_tests() {
    local verbosity="${1:-2}"

    _bold "═══════════════════════════════════════════════════════════"
    _bold "  FASE 1: Ejecutando suite de tests"
    _bold "═══════════════════════════════════════════════════════════"
    echo ""
    _dim "  Python: $(command -v python)"
    _dim "  Directorio: $SCRIPT_DIR"
    _dim "  Verbosidad: $verbosity"
    echo ""

    cd "$SCRIPT_DIR"

    # Guardar salida completa en archivo temporal para analizar
    local tmp_output
    tmp_output=$(mktemp)
    local test_exit=0

    python manage.py test --verbosity "$verbosity" 2>&1 | tee "$tmp_output" || test_exit=$?

    echo ""

    # Contar resultados
    local total=0 failed_count=0 error_count=0
    total=$(grep -cP "^(test_|    test_|ok$|FAIL$|ERROR$)" "$tmp_output" 2>/dev/null || echo "0")
    local ran_line
    ran_line=$(grep "Ran " "$tmp_output" | tail -1 || true)
    if [[ -n "$ran_line" ]]; then
        total=$(echo "$ran_line" | grep -oP 'Ran \K[0-9]+' || echo "0")
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
        rm -f "$tmp_output"
        return 0
    fi

    # ============================================================
    # SI HAY FALLOS — ANÁLISIS DETALLADO
    # ============================================================

    # Contar tipos de fallo
    failed_count=$(grep -cP "^FAIL:" "$tmp_output" 2>/dev/null || echo "0")
    error_count=$(grep -cP "^ERROR:" "$tmp_output" 2>/dev/null || echo "0")

    echo ""
    _red "╔══════════════════════════════════════════════════════════════╗"
    _red "║  ✗ ALGUNOS TEST FALLARON — EL SERVIDOR NO SE ENCIENDE      ║"
    _red "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    # Resumen numérico
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

        # Procesar cada FAIL
        if [[ "$failed_count" -gt 0 ]]; then
            grep -Pn "^FAIL:" "$tmp_output" | while IFS=: read -r line_num line_content; do
                fail_num=$((fail_num + 1))
                local test_name
                test_name=$(echo "$line_content" | sed 's/^FAIL: //')

                _red "  ━━━ ERROR #${fail_num} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                echo ""
                _bold "    Test: ${test_name}"
                echo ""

                # Extraer el traceback de este test específico
                # Django pone el traceback entre "FAIL:" y la siguiente línea "---" o "FAIL:" o "ERROR:" o "Ran"
                local traceback
                traceback=$(sed -n "$((line_num+1)),\$p" "$tmp_output" | sed '/^---/q' | sed '/^FAIL:/q' | sed '/^ERROR:/q' | sed '/^Ran /q' | head -30)

                if [[ -n "$traceback" ]]; then
                    _cyan "    ¿Qué falló?"
                    echo "$traceback" | sed 's/^/      /' | while IFS= read -r tl; do
                        # Colorear líneas clave
                        if echo "$tl" | grep -qP "AssertionError|assert"; then
                            _red "$tl"
                        elif echo "$tl" | grep -qP "File \""; then
                            _dim "$tl"
                        elif echo "$tl" | grep -qP "Error|Exception|Traceback"; then
                            _red "$tl"
                        else
                            echo "      $tl"
                        fi
                    done
                    echo ""
                fi

                # Explicación simple del tipo de error
                _cyan "    ¿Qué significa?"
                if echo "$traceback" | grep -qiP "AssertionError|assert"; then
                    echo "      El test esperaba un resultado pero obtuvo otro."
                    echo "      Algo en tu código cambió el comportamiento esperado."
                elif echo "$traceback" | grep -qiP "ImportError|ModuleNotFoundError"; then
                    echo "      Falta una librería o el import está mal escrito."
                elif echo "$traceback" | grep -qiP "TypeError"; then
                    echo "      Estás pasando un tipo de dato incorrecto a una función."
                elif echo "$traceback" | grep -qiP "AttributeError"; then
                    echo "      Estás usando un atributo o método que no existe."
                elif echo "$traceback" | grep -qiP "IntegrityError|unique"; then
                    echo "      Estás creando un registro duplicado que debería ser único."
                elif echo "$traceback" | grep -qiP "PermissionDenied|permission"; then
                    echo "      El usuario no tiene permiso para esta acción."
                else
                    echo "      Revisa el traceback arriba para entender el problema."
                fi
                echo ""

                # Buscar el archivo exacto
                local file_line
                file_line=$(echo "$traceback" | grep -oP 'File "\K[^"]+.*line \K[0-9]+' | tail -1 || true)
                local file_path
                file_path=$(echo "$traceback" | grep -oP 'File "\K[^"]+' | tail -1 || true)

                if [[ -n "$file_path" ]]; then
                    _cyan "    Archivo con el error:"
                    echo "      ${file_path}"
                    if [[ -n "$file_line" ]]; then
                        echo "      Línea: ${file_line}"
                    fi
                    echo ""
                fi

                # Cómo arreglar
                _cyan "    Cómo arreglar:"
                if echo "$traceback" | grep -qiP "AssertionError"; then
                    echo "      1. Abre el archivo indicado arriba"
                    echo "      2. Busca la línea ${file_line:-la línea del error}"
                    echo "      3. Compara lo que el test espera vs lo que tu código devuelve"
                    echo "      4. Corrige tu código para que pase el test"
                elif echo "$traceback" | grep -qiP "ImportError|ModuleNotFoundError"; then
                    echo "      1. Verifica que el módulo esté en requirements.txt"
                    echo "      2. Ejecuta: pip install -r requirements.txt"
                    echo "      3. Revisa que el import en el archivo sea correcto"
                elif echo "$traceback" | grep -qiP "IntegrityError|unique"; then
                    echo "      1. No crees el mismo registro dos veces en el test"
                    echo "      2. Usa get_or_create() en vez de create()"
                else
                    echo "      1. Lee el traceback completo arriba"
                    echo "      2. Busca la línea exacta del error en el archivo"
                    echo "      3. Corrige el problema"
                    echo "      4. Vuelve a ejecutar: bash start.sh"
                fi
                echo ""
            done
        fi

        # Procesar cada ERROR (más grave que FAIL)
        if [[ "$error_count" -gt 0 ]]; then
            grep -Pn "^ERROR:" "$tmp_output" | while IFS=: read -r line_num line_content; do
                fail_num=$((fail_num + 1))
                local test_name
                test_name=$(echo "$line_content" | sed 's/^ERROR: //')

                _red "  ━━━ ERROR GRAVE #${fail_num} ━━━━━━━━━━━━━━━━━━━━━━━"
                echo ""
                _bold "    Test: ${test_name}"
                _yellow "    (Este es un error GRAVE — el test ni siquiera pudo ejecutarse)"
                echo ""

                # Extraer traceback
                local traceback
                traceback=$(sed -n "$((line_num+1)),\$p" "$tmp_output" | sed '/^---/q' | sed '/^ERROR:/q' | sed '/^Ran /q' | head -30)

                if [[ -n "$traceback" ]]; then
                    _cyan "    ¿Qué falló?"
                    echo "$traceback" | sed 's/^/      /' | while IFS= read -r tl; do
                        if echo "$tl" | grep -qP "Error|Exception|Traceback"; then
                            _red "$tl"
                        elif echo "$tl" | grep -qP "File \""; then
                            _dim "$tl"
                        else
                            echo "      $tl"
                        fi
                    done
                    echo ""
                fi

                _cyan "    ¿Qué significa?"
                if echo "$traceback" | grep -qiP "ImportError|ModuleNotFoundError"; then
                    echo "      Falta instalar una dependencia o el import está roto."
                    echo "      El test NO PUEDE correr sin esta librería."
                elif echo "$traceback" | grep -qiP "SyntaxError"; then
                    echo "      Tu código tiene un error de sintaxis (falta un ':', paréntesis, etc.)"
                elif echo "$traceback" | grep -qiP "NameError"; then
                    echo "      Estás usando una variable o función que no existe."
                elif echo "$traceback" | grep -qiP "TypeError"; then
                    echo "      Estás pasando argumentos de tipo incorrecto a una función."
                else
                    echo "      El test falló antes de poder ejecutarse."
                    echo "      Revisa el traceback arriba."
                fi
                echo ""

                # Cómo arreglar
                _cyan "    Cómo arreglar:"
                if echo "$traceback" | grep -qiP "ImportError|ModuleNotFoundError"; then
                    echo "      1. pip install -r requirements.txt"
                    echo "      2. Verifica que el import en el archivo sea correcto"
                elif echo "$traceback" | grep -qiP "SyntaxError"; then
                    local file_path
                    file_path=$(echo "$traceback" | grep -oP 'File "\K[^"]+' | tail -1 || true)
                    echo "      1. Abre: ${file_path:-el archivo indicado}"
                    echo "      2. Busca la línea con el error de sintaxis"
                    echo "      3. Agrega el ':' o paréntesis que falta"
                else
                    echo "      1. Lee el traceback completo arriba"
                    echo "      2. El error está en el archivo indicado"
                    echo "      3. Corrige el problema y vuelve a ejecutar"
                fi
                echo ""
            done
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

    rm -f "$tmp_output"
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
  1. Verifica que el entorno esté configurado (.env, venv)
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
