.PHONY: help setup test test-verbose lint format ci check

VENV_BIN := $(shell test -d venv && echo venv/bin || test -d .venv && echo .venv/bin || echo "")
PYTHON := $(if $(VENV_BIN),$(VENV_BIN)/python,python)
PYTEST := $(if $(VENV_BIN),$(VENV_BIN)/python -m pytest,python -m pytest)
RUFF := $(if $(VENV_BIN),$(VENV_BIN)/ruff,ruff)

help:  ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup:  ## Instalar pre-commit hooks y configurar entorno
	@if [ ! -d venv ] && [ ! -d .venv ]; then \
		echo "Entorno virtual no encontrado. Ejecuta: bash setup.sh"; \
		exit 1; \
	fi
	$(PYTHON) -m pre_commit install 2>/dev/null || $(if $(VENV_BIN),$(VENV_BIN)/pre-commit install,pre-commit install)
	@echo "✓ Pre-commit hooks instalados"

test:  ## Ejecutar tests
	$(PYTEST) --verbosity 2

test-verbose:  ## Ejecutar tests con máximo detalle
	$(PYTEST) --verbosity 3

lint:  ## Verificar linting (sin modificar archivos)
	$(RUFF) check .
	$(RUFF) format --check .

format:  ## Auto-formatear código
	$(RUFF) check --fix .
	$(RUFF) format .

ci: lint test  ## Simular CI (lint + test)
	@echo "✓ CI pasó"

check:  ## Verificar configuración de Django
	$(PYTHON) manage.py check
	$(PYTHON) manage.py makemigrations --check --dry-run
