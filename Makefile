.DEFAULT_GOAL := help
SOURCES := src tests app.py scripts

.PHONY: help install run lint format typecheck test test-fast check eval screenshots screenshots-llm docker-build docker-up docker-down

help: ## Show available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'

install: ## Install the app and dev tools from the lock file
	uv sync --locked --all-groups
	uv run pre-commit install

run: ## Start the app on http://localhost:8501
	uv run streamlit run app.py

lint: ## Lint and check formatting
	uv run ruff check $(SOURCES)
	uv run ruff format --check $(SOURCES)

format: ## Auto-fix lint issues and format
	uv run ruff check --fix $(SOURCES)
	uv run ruff format $(SOURCES)

typecheck: ## Run mypy in strict mode
	uv run mypy

test: ## Run all tests with coverage
	uv run pytest --cov --cov-report=term-missing

test-fast: ## Run tests, skipping slow ones
	uv run pytest -m "not slow"

check: lint typecheck test ## Everything CI runs

eval: ## Measure NL-to-SQL accuracy (uses LLM_* settings if present, else rules)
	uv run python scripts/evaluate_nl_to_sql.py

screenshots: ## Regenerate README screenshots in rule-based mode (needs Chrome)
	uv run --group screenshots python scripts/capture_screenshots.py

screenshots-llm: ## Capture the AI screenshots using the LLM_* settings
	uv run --group screenshots python scripts/capture_screenshots.py --llm

docker-build: ## Build the production image
	docker compose build

docker-up: ## Run the app in Docker
	docker compose up -d

docker-down: ## Stop the Docker app
	docker compose down
