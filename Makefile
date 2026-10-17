# Makefile for SAGA

.PHONY: help lint lint-backend lint-frontend knip format format-backend format-frontend \
        test test-backend test-backend-all test-frontend test-all \
        test-infra-up test-infra-down check clean

# Cross-platform shell selection: PowerShell on Windows, sh elsewhere.
TEST_DB_URL := postgresql+asyncpg://saga_test:saga_test@localhost:5433/saga_test

ifeq ($(OS),Windows_NT)
	SHELL := powershell.exe
	.SHELLFLAGS := -NoProfile -ExecutionPolicy Bypass -Command
	# Call operator + quotes: $(MAKE) resolves to a path with spaces/parens that
	# PowerShell cannot invoke bare.
	SUBMAKE := & "$(MAKE)"
	WITH_NODE := & "../scripts/with_node.ps1"
	RUN_FULL_SUITE := cd backend; $$env:TEST_DATABASE_URL='$(TEST_DB_URL)'; uv run python -m pytest tests/unit tests/integration tests/playtest
	RUN_ALL_TESTS = $$result = 0; try { foreach ($$target in @('test-infra-up', 'test-backend-all', 'test-frontend')) { $(SUBMAKE) $$target; if ($$LASTEXITCODE -ne 0) { $$result = $$LASTEXITCODE; break } } } finally { $(SUBMAKE) test-infra-down; if ($$result -eq 0) { $$result = $$LASTEXITCODE } }; exit $$result
	CLEAN_CACHES := if (Test-Path backend/__pycache__) { Remove-Item -Recurse -Force backend/__pycache__ }; if (Test-Path backend/.pytest_cache) { Remove-Item -Recurse -Force backend/.pytest_cache }; if (Test-Path backend/.ruff_cache) { Remove-Item -Recurse -Force backend/.ruff_cache }
else
	SHELL := /bin/sh
	SUBMAKE := $(MAKE)
	WITH_NODE := bash ../scripts/with_node.sh
	RUN_FULL_SUITE := cd backend; TEST_DATABASE_URL='$(TEST_DB_URL)' uv run python -m pytest tests/unit tests/integration tests/playtest
	RUN_ALL_TESTS = trap 'status=$$?; $(SUBMAKE) test-infra-down; cleanup=$$?; if [ "$$status" -ne 0 ]; then exit "$$status"; fi; exit "$$cleanup"' EXIT; $(SUBMAKE) test-infra-up && $(SUBMAKE) test-backend-all && $(SUBMAKE) test-frontend
	CLEAN_CACHES := rm -rf backend/__pycache__ backend/.pytest_cache backend/.ruff_cache
endif

help:
	@echo "Saga Project Management Commands:"
	@echo "  make lint          Check code style and quality"
	@echo "  make knip          Find unused code/deps in frontend"
	@echo "  make format        Auto-fix code style issues"
	@echo "  make test          Run unit tests"
	@echo "  make test-all      Run backend and frontend tests (with test DB)"
	@echo "  make check         Full CI-like check"

# --- LINTING & FORMATTING ---

lint: lint-backend lint-frontend

lint-backend:
	@echo "Linting backend..."
	cd backend; uv run ruff check .

lint-frontend:
	@echo "Linting frontend..."
	cd frontend; $(WITH_NODE) npm run lint

knip:
	@echo "Checking for unused code and dependencies (frontend)..."
	cd frontend; $(WITH_NODE) npm run knip

format: format-backend format-frontend

format-backend:
	@echo "Formatting backend..."
	cd backend; uv run ruff check --fix .; uv run ruff format .

format-frontend:
	@echo "Formatting frontend..."
	cd frontend; $(WITH_NODE) npm run format

# --- TESTING ---

test: test-backend test-frontend

test-backend:
	@echo "Running backend unit tests..."
	cd backend; uv run python -m pytest tests/unit

test-backend-all:
	$(RUN_FULL_SUITE)

test-frontend:
	@echo "Running frontend unit tests..."
	cd frontend; $(WITH_NODE) npm run test -- --run

test-infra-up:
	@echo "Starting test infrastructure..."
	docker compose -f docker-compose.test.yml up -d --wait

test-infra-down:
	@echo "Stopping test infrastructure..."
	docker compose -f docker-compose.test.yml down

test-all:
	@echo "Running backend and frontend test suites..."
	@$(RUN_ALL_TESTS)

# Comprehensive CI Check
check: format lint test-all

clean:
	@echo "Cleaning up caches..."
	$(CLEAN_CACHES)
