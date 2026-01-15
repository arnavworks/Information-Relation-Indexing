.PHONY: install infra-up infra-down migrate graph-schema dev test lint typecheck check

install:
	python3 -m pip install -e '.[dev]'

infra-up:
	docker compose up -d --wait

infra-down:
	docker compose down

migrate:
	alembic upgrade head

graph-schema:
	neomodel_install_labels iri.graph.models --db "$${IRI_NEO4J_DSN:-bolt://neo4j:continuum-local@localhost:7687}"

dev:
	uvicorn iri.main:app --reload

test:
	pytest

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy

check: lint typecheck test
