.PHONY: install install-dev run test lint format build up down

install:
	pip install -r requirements.txt

install-dev: install
	pip install -r requirements-dev.txt

run:
	streamlit run app.py

test:
	pytest tests/

lint:
	flake8 .
	black --check .
	isort --check-only .

format:
	black .
	isort .

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down
