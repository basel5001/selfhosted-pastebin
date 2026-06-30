.PHONY: dev test lint fmt docker-build docker-up docker-down clean

dev:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	python -m pytest tests/ -v

lint:
	ruff check src/ tests/

fmt:
	ruff format src/ tests/
	ruff check --fix src/ tests/

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache
