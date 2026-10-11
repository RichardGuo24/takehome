# Nest Fulfillment

An inventory management and order fulfillment system for a single Zipline distribution center ("nest"). It accepts a product catalog, hospital orders, and restocks, and turns orders into packages of at most 1.8 kg, shipping what stock allows right away and the rest as restocks arrive.

- **Backend:** Python, FastAPI, in-memory state, a framework-free domain core
- **Frontend:** React + TypeScript (Vite), an operator dashboard

The full problem statement, design, and tradeoffs are in **[DESIGN.md](DESIGN.md)**.

> **Status:** scaffold. The domain core, API endpoints, and dashboard are built step by step per [DESIGN.md §17](DESIGN.md#17-build-plan).

## Quick start

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
make install   # backend (uv sync) + frontend (npm install)
make dev       # backend on :8000, frontend on :5173
```

Open http://localhost:5173 for the dashboard, or http://localhost:8000/docs for interactive API docs.

| Command | What it does |
| --- | --- |
| `make test` | Backend tests (pytest + hypothesis) |
| `make lint` | ruff (backend) and oxlint (frontend) |
| `make fmt` | Auto-format the backend |

## How the spec maps to the API

| Spec function | Endpoint |
| --- | --- |
| `init_catalog(product_info)` | `PUT /api/catalog` |
| `process_order(order)` | `POST /api/orders` |
| `process_restock(restock)` | `POST /api/restocks` |
| `ship_package(shipment)` | Printed to the backend console in the spec's JSON shape; also visible at `GET /api/shipments` |

Request bodies use the spec's JSON shapes exactly. Sample payloads are in [`backend/samples/`](backend/samples/).

## Repository layout

```
backend/
  app/
    domain/      models, errors, packer, sinks, service (pure Python)
    api/         Pydantic schemas, routes, error mapping
    main.py      app wiring
  tests/
  samples/       catalog, restock, and order JSON from the spec
frontend/
  src/           App, api.ts (types + fetch), usePolling.ts, components/
DESIGN.md        problem, design, tradeoffs, build plan
CLAUDE.md        instructions for AI coding agents working in this repo
Makefile
```

## Use of AI

Built with help from Claude. The design, decisions, and tradeoffs in DESIGN.md are my own, and I can explain every part of the code.
