.PHONY: help setup test run deploy clean format lint docker-build docker-run

# Default target
.DEFAULT_GOAL := help

# Variables
PYTHON := python3.11
VENV := venv
BIN := $(VENV)/bin
AZURE_FUNCTION_APP_NAME ?= epicor-hubspot-sync-production
AZURE_RESOURCE_GROUP ?= epicor-hubspot-rg

help: ## Show this help message
	@echo "Epicor-HubSpot Integration - Available Commands"
	@echo "================================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Set up development environment
	@echo "Setting up development environment..."
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt
	$(BIN)/pip install -r requirements-dev.txt
	cp .env.example .env
	@echo " Setup complete! Edit .env with your credentials."

test: ## Run all tests
	@echo "Running tests..."
	$(BIN)/pytest tests/ -v --cov=src --cov-report=term-missing

test-coverage: ## Run tests with HTML coverage report
	@echo "Running tests with coverage report..."
	$(BIN)/pytest tests/ -v --cov=src --cov-report=html
	@echo " Coverage report generated in htmlcov/index.html"

test-connection: ## Test API connections
	@echo "Testing API connections..."
	$(BIN)/python scripts/test_connection.py

run: ## Run sync locally
	@echo "Running Epicor-HubSpot sync..."
	$(BIN)/python -m src.main

func-start: ## Run Azure Function locally
	@echo "Starting Azure Function locally..."
	func start

format: ## Format code with black
	@echo "Formatting code..."
	$(BIN)/black src/ tests/
	$(BIN)/isort src/ tests/
	@echo " Code formatted"

lint: ## Run linters
	@echo "Running linters..."
	$(BIN)/pylint src/
	$(BIN)/mypy src/ --ignore-missing-imports
	@echo " Linting complete"

docker-build: ## Build Docker image
	@echo "Building Docker image..."
	docker-compose -f docker/docker-compose.yml build
	@echo " Docker image built"

docker-run: ## Run Docker container
	@echo "Running Docker container..."
	docker-compose -f docker/docker-compose.yml up

docker-stop: ## Stop Docker container
	@echo "Stopping Docker container..."
	docker-compose -f docker/docker-compose.yml down

deploy: ## Deploy to Azure Functions
	@echo "Deploying to Azure Functions..."
	chmod +x scripts/deploy.sh
	./scripts/deploy.sh

deploy-infra: ## Deploy Azure ARM template
	@echo "Deploying Azure infrastructure..."
	chmod +x scripts/deploy.sh
	./scripts/deploy.sh --deploy-infra

clean: ## Clean up generated files
	@echo "Cleaning up..."
	rm -rf build/
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo " Cleanup complete"

logs: ## View Azure Function logs
	@echo "Querying Azure Function logs..."
	az monitor app-insights query \
		--app $(AZURE_FUNCTION_APP_NAME)-insights-production \
		--resource-group $(AZURE_RESOURCE_GROUP) \
		--analytics-query "traces | order by timestamp desc | take 50" \
		--output table

invoke: ## Invoke Azure Function manually via HTTP trigger
	@echo "Invoking Azure Function..."
	func azure functionapp logstream $(AZURE_FUNCTION_APP_NAME) &
	curl -s -X POST "https://$(AZURE_FUNCTION_APP_NAME).azurewebsites.net/api/sync" \
		-H "x-functions-key: $$(az functionapp keys list --name $(AZURE_FUNCTION_APP_NAME) --resource-group $(AZURE_RESOURCE_GROUP) --query 'functionKeys.default' -o tsv)" | python -m json.tool
