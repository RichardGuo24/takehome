.PHONY: install dev backend frontend test lint fmt

install:          ## Install backend and frontend dependencies
	cd backend && uv sync
	cd frontend && npm install

dev:              ## Run backend (:8000) and frontend (:5173) together
	$(MAKE) -j2 backend frontend

backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:             ## Run backend tests
	cd backend && uv run pytest

lint:             ## Lint and format-check everything
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint

fmt:              ## Auto-format and auto-fix the backend
	cd backend && uv run ruff format . && uv run ruff check --fix .
