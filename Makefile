uvinstall:
	pip install uv && \
	uv pip install --upgrade pip && \
		uv pip install -r requirements.txt

install:
	pip install --upgrade pip && \
		pip install -r requirements.txt

format:
	black fundamentos/*.py

ruff_format:
	ruff format fundamentos/*.py

lint:
	pylint --disable=R,C fundamentos/*.py

ruff_lint:
	ruff check fundamentos/*.py

typepyright:
	pyright fundamentos/*.py

typemypy:
	mypy fundamentos/

test:
	python -m pytest -vv --cov=tests/test_*.py

refactor: format lint

all: install format lint typepyright typemypy ruff_format ruff_lint