#!/usr/bin/env bash
# pg-mcp.sh — Wrapper para crystaldba/postgres-mcp con fallback de runners.
# Lee RASSA_JALA_DB_URL del shell, valida formato, y ejecuta el MCP.
# Cross-platform: Linux, macOS, y Windows (Git Bash).
#
# NOTA DE SEGURIDAD: se usa --access-mode=unrestricted a proposito.
# El proyecto esta en desarrollo activo y aun no existe una version estable.
# El agente necesita libertad para analizar la base de datos, ejecutar
# consultas complejas y explorar datos bajo la supervision del desarrollador
# que utilice el MCP. En un entorno productivo estable se recomienda
# --access-mode=read-only o el modo restrictivo que aplique.

set -eu

DEFAULT_MCP_VERSION="0.3.0"
POSTGRES_MCP_VERSION="${POSTGRES_MCP_VERSION:-$DEFAULT_MCP_VERSION}"
ACCESS_MODE="--access-mode=unrestricted"

if [[ "${1:-}" == "--mcp-version" ]]; then
  version="${2:-$POSTGRES_MCP_VERSION}"
else
  version="$POSTGRES_MCP_VERSION"
fi

if [ -z "${RASSA_JALA_DB_URL:-}" ]; then
  echo "Error: RASSA_JALA_DB_URL no está definida en el shell." >&2
  echo "" >&2
  echo "  Agregala a tu config de shell y hace source:" >&2
  echo "    ~/.zshrc, ~/.bashrc, o Git Bash ~/.bashrc (Windows)" >&2
  echo "    echo 'export RASSA_JALA_DB_URL=\"postgresql://user:pass@host:5432/db\"' >> ~/.bashrc" >&2
  echo "    source ~/.bashrc" >&2
  exit 1
fi

if [[ "$RASSA_JALA_DB_URL" != postgres://* && "$RASSA_JALA_DB_URL" != postgresql://* ]]; then
  echo "Error: RASSA_JALA_DB_URL debe empezar con postgres:// o postgresql://" >&2
  echo "Actual: ${RASSA_JALA_DB_URL:0:30}..." >&2
  exit 1
fi

MCP_PACKAGE="postgres-mcp==$version"

run_mcp() {
  local last_exit=1
  local tried=0

  if command -v uvx >/dev/null 2>&1; then
    tried=1
    echo "postgres-mcp: intentando uvx" >&2
    if DATABASE_URI="$RASSA_JALA_DB_URL" uvx "$MCP_PACKAGE" "$ACCESS_MODE"; then
      exit 0
    else
      last_exit=$?
    fi
    echo "postgres-mcp: uvx falló con código $last_exit, intentando siguiente..." >&2
  fi

  if command -v pipx >/dev/null 2>&1; then
    tried=1
    echo "postgres-mcp: intentando pipx" >&2
    if DATABASE_URI="$RASSA_JALA_DB_URL" pipx run --spec "$MCP_PACKAGE" postgres-mcp "$ACCESS_MODE"; then
      exit 0
    else
      last_exit=$?
    fi
    echo "postgres-mcp: pipx falló con código $last_exit, intentando siguiente..." >&2
  fi

  if command -v python3 >/dev/null 2>&1; then
    tried=1
    echo "postgres-mcp: intentando python3 -m" >&2
    if DATABASE_URI="$RASSA_JALA_DB_URL" python3 -m postgres_mcp "$ACCESS_MODE"; then
      exit 0
    else
      last_exit=$?
    fi
    echo "postgres-mcp: python3 falló con código $last_exit, intentando siguiente..." >&2
  fi

  if command -v python >/dev/null 2>&1; then
    tried=1
    echo "postgres-mcp: intentando python -m" >&2
    if DATABASE_URI="$RASSA_JALA_DB_URL" python -m postgres_mcp "$ACCESS_MODE"; then
      exit 0
    else
      last_exit=$?
    fi
    echo "postgres-mcp: python falló con código $last_exit, intentando siguiente..." >&2
  fi

  if [ $tried -eq 0 ]; then
    echo "Error: no se encontró ningún runner de Python." >&2
    echo "" >&2
    echo "  Instalá alguno de estos:" >&2
    echo "    uvx:  curl -fsSL https://astral.sh/uv/install.sh | sh" >&2
    echo "    pipx: python3 -m pip install --user pipx && python3 -m pipx ensurepath" >&2
    echo "    python3: https://www.python.org/downloads/" >&2
  else
    echo "Error: todos los runners de Python fallaron." >&2
  fi
  exit $last_exit
}

run_mcp
