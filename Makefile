# Convenience targets for local development.
# Usage: make <target>

.PHONY: help up down logs backend-install backend-run backend-test frontend-install frontend-run lint

help:
	@echo "Targets:"
	@echo "  up                 docker compose up --build"
	@echo "  down               docker compose down"
	@echo "  logs               tail compose logs"
	@echo "  backend-install    create venv + install backend deps"
	@echo "  backend-run        run FastAPI (uvicorn --reload)"
	@echo "  backend-test       run backend pytest suite"
	@echo "  frontend-install   npm install"
	@echo "  frontend-run       run Next.js dev server"

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

backend-install:
	cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt

backend-run:
	cd backend && uvicorn app.main:app --reload

backend-test:
	cd backend && pytest

frontend-install:
	cd frontend && npm install

frontend-run:
	cd frontend && npm run dev
