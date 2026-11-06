# Brand Q&A Agent — developer convenience targets.
#
# POSIX shells (Linux / macOS / Git Bash / WSL). On Windows PowerShell you can
# call the same underlying commands directly, e.g.:
#     .venv\Scripts\python.exe -m pytest
#
# Override the interpreter if needed:  make test PY=python3

PY       ?= python
VENV     ?= .venv
PYTHON   := $(VENV)/bin/python
PIP      := $(VENV)/bin/pip

.DEFAULT_GOAL := help
.PHONY: help install run test test-mandatory lint format typecheck check clean docker-build docker-up docker-down

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/python:
	$(PY) -m venv $(VENV)

install: $(VENV)/bin/python ## Create the virtualenv and install all dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

run: ## Start the API with autoreload (http://localhost:8000)
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

serve: ## Start the API in production mode
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000

test: ## Run the full test suite
	$(PYTHON) -m pytest

test-mandatory: ## Run only the two mandatory assignment tests
	$(PYTHON) -m pytest tests/security/test_tenant_isolation.py tests/agent/test_graph_workflow.py -v

lint: ## Static lint with Ruff
	$(PYTHON) -m ruff check .

format: ## Auto-format with Ruff
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

typecheck: ## Static type checking with MyPy
	$(PYTHON) -m mypy app

check: lint typecheck test ## Lint + typecheck + test

docker-build: ## Build the Docker image
	docker build -t brand-qa-agent:latest .

docker-up: ## Start the stack with Docker Compose
	docker compose up --build

docker-down: ## Stop the Docker Compose stack
	docker compose down

clean: ## Remove caches and local runtime state
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
