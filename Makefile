.PHONY: install run test docker-build docker-up cli profiles detect status retrieve ingest

# ── Local development ──

install:
	pip install -r requirements-core.txt
	pip install -e .

run:
	python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload

test:
	python -m pytest tests/ -x -q

test-all:
	python -m pytest tests/ -v

# ── CLI (no UI needed) ──

cli:
	python scripts/run.py $(filter-out $@,$(MAKECMDGOALS))

profiles:
	python scripts/run.py list-profiles

detect:
	python scripts/run.py detect $(SOURCE)

status:
	python scripts/run.py status

retrieve:
	python scripts/run.py retrieve "$(QUERY)" --k $(K)

ingest:
	python scripts/run.py ingest "$(SOURCE)" --profile "$(PROFILE)"

ingest-batch:
	python scripts/run.py ingest-batch $(SOURCES) --profile "$(PROFILE)"

# ── Docker ──

docker-build:
	docker build -t rag-pipeline:latest .

docker-up:
	docker-compose up --build -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-shell:
	docker-compose exec rag-pipeline /bin/bash

# ── Help ──

help:
	@echo "Usage:"
	@echo "  make install          Install dependencies"
	@echo "  make run              Start the API server locally"
	@echo "  make test             Run tests"
	@echo "  make profiles         List available profiles"
	@echo "  make detect SOURCE=file.pdf  Analyze a document"
	@echo "  make ingest SOURCE=file.pdf PROFILE=hybrid  Ingest with a profile"
	@echo "  make retrieve QUERY=\"your query\" K=5    Search"
	@echo "  make status           Show pipeline status"
	@echo "  make docker-build     Build Docker image"
	@echo "  make docker-up        Start all Docker services"
	@echo ""
	@echo "Examples:"
	@echo "  make profiles"
	@echo "  make detect SOURCE=~/doc.pdf"
	@echo "  make ingest SOURCE=~/doc.pdf PROFILE=hybrid"
	@echo "  make ingest SOURCE=~/doc.pdf PROFILE=standard"
	@echo "  make retrieve QUERY=\"option pricing greeks\" K=10"
	@echo "  make docker-up"
	@echo "  curl http://localhost:8000/profiles"
	@echo "  curl http://localhost:9090/targets  # Prometheus"
