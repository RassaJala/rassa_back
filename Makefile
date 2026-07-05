.PHONY: help setup test test-verbose lint format ci check

help:  ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup:  ## Instalar pre-commit hooks
	pre-commit install
	@echo "✓ Pre-commit hooks instalados"

test:  ## Ejecutar tests
	python manage.py test --verbosity 2

test-verbose:  ## Ejecutar tests con máximo detalle
	python manage.py test --verbosity 3

lint:  ## Verificar linting (sin modificar archivos)
	ruff check .
	ruff format --check .

format:  ## Auto-formatear código
	ruff check --fix .
	ruff format .

ci: lint test  ## Simular CI (lint + test)
	@echo "✓ CI pasó"

check:  ## Verificar configuración de Django
	python manage.py check
	python manage.py makemigrations --check --dry-run
