# Makefile for SAGA

.PHONY: help lint lint-backend lint-frontend knip format format-backend format-frontend \
        test test-backend test-frontend test-all \
        test-infra-up test-infra-down check clean

# Cross-platform shell selection: PowerShell on Windows, sh elsewhere.
TEST_DB_URL := postgresql+asyncpg://saga_test:saga_test@localhost:5433/saga_test

ifeq ($(OS),Windows_NT)
	SHELL := powershell.exe
	.SHELLFLAGS := -Command
	# Call operator + quotes: $(MAKE) resolves to a path with spaces/parens that
	# PowerShell cannot invoke bare.
	SUBMAKE := & "$(MAKE)"
	RUN_FULL_SUITE := cd backend; $$env:TEST_DATABASE_URL='$(TEST_DB_URL)'; uv run python -m pytest tests/unit tests/integration tests/playtest
	CLEAN_CACHES := if (Test-Path backend/__pycache__) { Remove-Item -Recurse -Force backend/__pycache__ }; if (Test-Path backend/.pytest_cache) { Remove-Item -Recurse -Force backend/.pytest_cache }; if (Test-Path backend/.ruff_cache) { Remove-Item -Recurse -Force backend/.ruff_cache }
else
	SHELL := /bin/sh
	SUBMAKE := $(MAKE)
	RUN_FULL_SUITE := cd backend; TEST_DATABASE_URL='$(TEST_DB_URL)' uv run python -m pytest tests/unit tests/integration tests/playtest
	CLEAN_CACHES := rm -rf backend/__pycache__ backend/.pytest_cache backend/.ruff_cache
endif

help:
	@echo "Saga Project Management Commands:"
	@echo "  make lint          Check code style and quality"
	@echo "  make knip          Find unused code/deps in frontend"
	@echo "  make format        Auto-fix code style issues"
	@echo "  make test          Run unit tests"
	@echo "  make test-all      Run all tests (Unit + Integration + Playtest)"
	@echo "  make check         Full CI-like check"

# --- LINTING & FORMATTING ---

lint: lint-backend lint-frontend

lint-backend:
	@echo "Linting backend..."
	cd backend; uv run ruff check .

lint-frontend:
	@echo "Linting frontend..."
	cd frontend; npm run lint

knip:
	@echo "Checking for unused code and dependencies (frontend)..."
	cd frontend; npm run knip

format: format-backend format-frontend

format-backend:
	@echo "Formatting backend..."
	cd backend; uv run ruff check --fix .; uv run ruff format .

format-frontend:
	@echo "Formatting frontend..."
	cd frontend; npm run format

# --- TESTING ---

test: test-backend test-frontend

test-backend:
	@echo "Running backend unit tests..."
	cd backend; uv run python -m pytest tests/unit

test-frontend:
	@echo "Running frontend unit tests..."
	cd frontend; npm run test -- --run

test-infra-up:
	@echo "Starting test infrastructure..."
	docker compose -f docker-compose.test.yml up -d --wait

test-infra-down:
	@echo "Stopping test infrastructure..."
	docker compose -f docker-compose.test.yml down

test-all:
	@echo "Running full test suite (Unit + Integration + Playtest)..."
	-$(SUBMAKE) test-infra-up
	$(RUN_FULL_SUITE)
	-$(SUBMAKE) test-infra-down

# Comprehensive CI Check
check: format lint test-all

clean:
	@echo "Cleaning up caches..."
	$(CLEAN_CACHES)
