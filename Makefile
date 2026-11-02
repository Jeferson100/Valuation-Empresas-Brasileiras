PYTHON ?= python

uvinstall:
	$(PYTHON) -m pip install uv
	$(PYTHON) -m uv pip install --upgrade pip
	$(PYTHON) -m uv pip install -e ".[dev]"

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

format:
	$(PYTHON) -m ruff format valuation tests
	$(PYTHON) -m ruff check --fix valuation tests

lint:
	$(PYTHON) -m ruff check valuation tests

typecheck:
	$(PYTHON) -m mypy valuation

test:
	$(PYTHON) -m pytest --cov=valuation --cov-report=term-missing

test-fast:
	$(PYTHON) -m pytest -m "not network"

valuation:
	$(PYTHON) -m valuation.pipeline.run

all: format lint typecheck test
