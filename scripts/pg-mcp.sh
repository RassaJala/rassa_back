#!/usr/bin/env bash
# pg-mcp.sh — Wrapper para crystaldba/postgres-mcp con fallback de runners.
# Lee RASSA_JALA_DB_URL del shell, valida formato, y ejecuta el MCP.
# Cross-platform: Linux, macOS, y Windows (Git Bash).

set -eu

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

run_mcp() {
  if command -v uvx >/dev/null 2>&1; then
    echo "postgres-mcp: usando uvx" >&2
    exec env DATABASE_URI="$RASSA_JALA_DB_URL" \
      uvx "postgres-mcp==0.3.0" --access-mode=unrestricted
  fi

  if command -v pipx >/dev/null 2>&1; then
    echo "postgres-mcp: usando pipx" >&2
    exec env DATABASE_URI="$RASSA_JALA_DB_URL" \
      pipx run --spec "postgres-mcp==0.3.0" postgres-mcp --access-mode=unrestricted
  fi

  if command -v python3 >/dev/null 2>&1; then
    echo "postgres-mcp: usando python3 -m" >&2
    exec env DATABASE_URI="$RASSA_JALA_DB_URL" \
      python3 -m postgres_mcp --access-mode=unrestricted
  fi

  if command -v python >/dev/null 2>&1; then
    echo "postgres-mcp: usando python -m" >&2
    exec env DATABASE_URI="$RASSA_JALA_DB_URL" \
      python -m postgres_mcp --access-mode=unrestricted
  fi

  echo "Error: no se encontró ningún runner de Python." >&2
  echo "" >&2
  echo "  Instalá alguno de estos:" >&2
  echo "    uvx:  curl -fsSL https://astral.sh/uv/install.sh | sh" >&2
  echo "    pipx: python3 -m pip install --user pipx && python3 -m pipx ensurepath" >&2
  echo "    python3: https://www.python.org/downloads/" >&2
  exit 1
}

run_mcp
