# Working in this repo

A take-home for Zipline: inventory and order fulfillment for one nest. **Read DESIGN.md before changing code.** It is the source of truth; if code and DESIGN.md disagree, stop and ask rather than picking one.

The author must be able to explain every line in an interview. Favor small, readable changes over clever ones, and explain non-obvious choices in the PR or commit message.

## Commands

- `make install`: install everything
- `make test`: backend tests (run after every change)
- `make lint` / `make fmt`: ruff + oxlint
- `make dev`: run backend (:8000) and frontend (:5173)

Backend commands run from `backend/` via `uv run ...`. Frontend from `frontend/` via `npm run ...`.

## Architecture rules

- `backend/app/domain/` is pure Python. It must never import FastAPI, Pydantic, or anything from `app.api`.
- All state changes go through `FulfillmentService`. Routes never touch `stock` or `pending` directly.
- Every route that calls the service holds `app.state.lock` for the whole call.
- Pydantic models live only in `app/api/schemas.py`; convert to domain dataclasses with `.to_domain()`.
- Domain errors are raised in the core and mapped to HTTP in `app/api/errors.py` only.
- Masses are integer grams. No floats.
- Keep the invariants in DESIGN.md §2 true after every call.

## Don't

- Don't add abstractions without a second real implementation (no repository layer, no allocation-policy interface). See DESIGN.md §6.
- Don't add dependencies (data-fetching libraries, UI kits, ORMs, Docker) without asking.
- Don't change the spec's JSON shapes for request bodies or the console shipment output.
- Don't build more than the current build-plan step (DESIGN.md §17). Stop after each step so it can be reviewed.

## Build order

Follow DESIGN.md §17. Each step: implement, add tests, `make test && make lint`, then one focused commit. Tick the step's checkbox in DESIGN.md in the same commit.

## Style

- Python: type hints everywhere, small functions, docstrings on public methods. ruff decides formatting.
- TypeScript: function components, plain `fetch` through `src/api.ts`, plain CSS in `src/index.css`.
- Tests: assert on behavior and invariants, use `RecordingSink`, prefer the spec's sample data where it fits.
- Writing in docs and comments: no em dashes.
