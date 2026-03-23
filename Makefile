.PHONY: help lint lint-backend lint-frontend format format-backend format-frontend test test-backend test-frontend test-all test-backend-all test-infra-up test-infra-down test-playtest coverage coverage-backend coverage-frontend check

help:
	@echo "Saga Project Management Commands:"
	@echo "  lint               Run linters for both backend and frontend"
	@echo "  format             Run formatters for both backend and frontend"
	@echo "  test               Run all unit tests"
	@echo "  coverage           Generate coverage reports for both"
	@echo "  check              Run lint, format (check only), and tests"

lint: lint-backend lint-frontend
lint-backend:
	cd backend && uv run ruff check .
lint-frontend:
	cd frontend && npm run lint

format: format-backend format-frontend
format-backend:
	cd backend && uv run ruff format .
format-frontend:
	cd frontend && npm run format

check: lint test-all

test-all: test-backend-all test-frontend

test-backend-all:
	@echo "Running all backend tests (Unit + Integration)..."
	$(MAKE) test-infra-up
	-cd backend && TEST_DATABASE_URL=postgresql+asyncpg://saga_test:saga_test@localhost:5433/saga_test TEST_REDIS_URL=redis://localhost:6380/0 uv run pytest tests/unit tests/integration
	$(MAKE) test-infra-down

test-infra-up:
	docker compose -f docker-compose.test.yml up -d --wait

test-infra-down:
	docker compose -f docker-compose.test.yml down

test-backend:
	cd backend && uv run pytest tests/unit --cov=app --cov-report=term-missing:skip-covered
test-frontend:
	cd frontend && npm run test -- --run --coverage.enabled --coverage.reporter=text --coverage.include="src/**/*.{ts,tsx}"

coverage: coverage-backend coverage-frontend
coverage-backend:
	cd backend && uv run pytest --cov=app --cov-report=term-missing --cov-report=html
coverage-frontend:
	cd frontend && npm run test:coverage

check: lint test
