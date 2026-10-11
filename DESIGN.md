# Nest Fulfillment: Design

This document explains the problem, the requirements we derived from it, and how the system solves it. It is the source of truth for implementation: code should match it, and when a decision changes, this file changes in the same commit.

**Contents**

1. [The problem](#1-the-problem)
2. [Requirements and invariants](#2-requirements-and-invariants)
3. [Assumptions](#3-assumptions)
4. [Why an order might not ship as received](#4-why-an-order-might-not-ship-as-received)
5. [Tech stack](#5-tech-stack)
6. [Architecture](#6-architecture)
7. [Domain model and data structures](#7-domain-model-and-data-structures)
8. [Core algorithms](#8-core-algorithms)
9. [Walkthrough: a full trace](#9-walkthrough-a-full-trace)
10. [API contract](#10-api-contract)
11. [Concurrency](#11-concurrency)
12. [Errors and validation](#12-errors-and-validation)
13. [Frontend](#13-frontend)
14. [Key decisions and tradeoffs](#14-key-decisions-and-tradeoffs)
15. [Testing strategy](#15-testing-strategy)
16. [Out of scope and future work](#16-out-of-scope-and-future-work)
17. [Build plan](#17-build-plan)
18. [Known tensions and open questions](#18-known-tensions-and-open-questions)

---

## 1. The problem

Zipline runs distribution centers called **nests**. Each nest keeps an inventory of medical supplies (mostly blood products) and ships orders from hospitals by drone.

We are building a lightweight inventory and order processing system for one nest. It must:

- manage an inventory of products,
- track which items have been stocked,
- turn incoming orders into outgoing shipments.

An order often can't be shipped exactly as received. It may be too heavy for one package (the maximum package mass is **1800 g**), or the nest may be out of some products, in which case part of the order waits until a restock.

### The four interfaces from the spec

| Function | Called by | What it does |
| --- | --- | --- |
| `init_catalog(product_info)` | Setup, exactly once, before anything else | Defines which products exist and their mass. Stock starts at 0 for each. |
| `process_order(order)` | A hospital (external service) | Injects an order. Must eventually cause every requested unit to be shipped. |
| `process_restock(restock)` | Supply (external service) | Adds stock. Any pending or partial orders that can now ship must ship immediately. |
| `ship_package(shipment)` | Our system (output) | One call per physical package. A stub that prints the shipment. |

### JSON shapes (from the spec)

```json
// init_catalog: a JSON array
[{"mass_g": 700, "product_name": "RBC A+ Adult", "product_id": 0}, ...]

// process_order: a JSON object
{"order_id": 123, "requested": [{"product_id": 0, "quantity": 2}, {"product_id": 10, "quantity": 4}]}

// process_restock: a JSON array
[{"product_id": 0, "quantity": 30}, {"product_id": 1, "quantity": 25}, ...]

// ship_package: a JSON object
{"order_id": 123, "shipped": [{"product_id": 0, "quantity": 1}, {"product_id": 10, "quantity": 2}]}
```

The full sample catalog, restock, and order live in [`backend/samples/`](backend/samples/).

### What "as many times as necessary" means

The spec says the program should invoke `ship_package` "as many times as necessary to fulfill an order." That means **as many as needed, not as many as possible**. One order can need several calls for two reasons:

1. **Weight.** The sample order is 2 × 700 g + 4 × 300 g = 1400 + 1200 = 2600 g. Since 2600 > 1800, it needs at least ⌈2600 / 1800⌉ = 2 packages.
2. **Time.** If stock is short, part of the order ships now and the rest ships after later restocks, each as its own package.

---

## 2. Requirements and invariants

These must hold after every call. They are the basis of the property tests (section 15).

| # | Invariant | In symbols |
| --- | --- | --- |
| I1 | No package exceeds the mass limit | ∀ shipment s: mass(s) ≤ 1800 g |
| I2 | Stock never goes negative; we never ship unstocked product | ∀ product p: stock[p] ≥ 0 |
| I3 | Conservation: nothing is lost or invented | ∀ order o, product p: shipped(o, p) + remaining(o, p) = requested(o, p) |
| I4 | No stock is held while someone waits for it | ∀ p: stock[p] = 0 ∨ no pending order needs p |
| I5 | Every package is non-empty and belongs to exactly one order | ∀ s: s.lines ≠ ∅ |

I4 is a consequence of serving pending orders eagerly in FIFO order. It also guarantees that a new order can never "cut the line": if older orders are waiting on p, then stock[p] = 0, so the new order queues behind them for p.

---

## 3. Assumptions

The spec leaves these open. Each is a deliberate choice, documented so a reviewer can disagree with it explicitly.

- **FIFO allocation.** When stock is scarce, the oldest pending order is served first. The spec does not mandate an order; with no priority data, FIFO is the neutral, predictable default. FIFO applies **per product**: an order waiting on product A never blocks a later order that only needs product B.
- **Ship partial fills immediately.** If some of an order can ship now, it ships now rather than waiting to consolidate. For medical supplies, latency beats flight efficiency (section 14 discusses the tradeoff).
- **One package belongs to one order.** Orders go to different hospitals, so packages are never shared across orders.
- **Integer grams** everywhere. No floats.
- **Single nest, single process,** in-memory state. Restarting the server resets the system.
- **Requests are all or nothing.** If any line of an order or restock is invalid, nothing in that request is applied.

---

## 4. Why an order might not ship as received

We brainstormed every reason an order can't go out as a single package right away, then split them into what this system handles and what it documents as future work.

### Handled in this system

| Reason | How it's handled |
| --- | --- |
| Order heavier than 1800 g | Split into packages with First Fit Decreasing (section 8) |
| A product is out of stock | That line waits as pending until a restock |
| Partial stock (want 10, have 4) | Ship the 4 now, hold the remaining 6 |
| Several orders want the same scarce stock | FIFO: oldest order first |
| A restock arrives while orders are pending | `process_restock` runs a fulfillment pass and ships immediately |
| Unknown `product_id` in an order or restock | Reject the request (422) |
| Quantity ≤ 0, non-integer, or missing; empty order | Reject (422) via Pydantic |
| Same product listed twice in one order or restock | Sum the lines into one quantity |
| Duplicate `order_id` (e.g. a retried request) | Same payload (compared after summing duplicate lines): ship nothing new and return the order's current status. Different payload: 409 |
| A catalog product heavier than 1800 g, or mass ≤ 0 | Rejected at `init_catalog`; such a product could never ship |
| Duplicate `product_id` in the catalog | Rejected at `init_catalog` |
| Empty catalog | Rejected at `init_catalog`: it runs only once, so an empty catalog could never take an order |
| Empty restock | Accepted; changes nothing and ships nothing |
| Order or restock before `init_catalog` | 409 |
| Second `init_catalog` | 409 |
| Two requests at the same moment | One lock serializes all service calls (section 11) |

### Real-world reasons, out of scope

These show up in a real blood-logistics system. Each has a sketched design in section 16.

- **Cold-chain incompatibility.** Platelets are stored at room temperature, red cells refrigerated, plasma and cryo frozen. They likely can't share a package.
- **Expiry.** Platelets last days, red cells weeks. Inventory would need lots and first-expired-first-out.
- **Urgency.** A trauma order should jump the queue.
- **Blood-type substitution.** O- red cells can stand in for other types, but that's a clinical decision.
- **Consolidation.** Waiting to fill a package may save a flight.
- **Orders that can never complete** because a product is never restocked.
- **`ship_package` failing** downstream (network, no drone, weather).
- **Operator packing failures** (damaged unit, miscount).
- **Cancellations and edits.**
- **Volume limits,** not just mass.

---

## 5. Tech stack

Kept deliberately small: each piece earns its place.

| Layer | Choice | Why | Considered instead |
| --- | --- | --- | --- |
| Backend language | Python 3.12+ | Fast to write; dataclasses and Protocols give clear types | TypeScript (shared types with the frontend) |
| Web framework | FastAPI | Pydantic validation and interactive docs at `/docs` for free | Flask (hand-written validation), Django (far too heavy) |
| Validation | Pydantic models at the API edge | Bad input is rejected with a precise 422 before the core runs | Hand-written `if` checks |
| Core types | Dataclasses | The core has no dependency on the web framework | Reusing Pydantic models everywhere |
| Storage | In-memory dicts | No durability requirement; keeps focus on the logic | SQLite, Postgres |
| Concurrency | One `threading.Lock` around service calls | Simplest correct option with FastAPI's thread pool | Async-only endpoints, DB transactions |
| Frontend | React + Vite + TypeScript, plain `fetch` | A real operator dashboard with minimal dependencies | Streamlit, a rich CLI |
| Live updates | A small polling hook (1 to 2 s) | Simplest thing that works | Server-Sent Events, WebSockets |
| Tooling | uv, ruff, pytest + hypothesis, one Makefile | Reproducible installs, lint, tests | Docker, CI (future work) |

---

## 6. Architecture

```
┌──────────────────────── Frontend: React dashboard ────────────────────────┐
│ Operator: Inventory, Queue, Shipments | Outside: Hospital, Supplier, Demo │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │ HTTP (/api, polled every 1 to 2 s)
┌───────────────────────────────────▼───────────────────────────────────────┐
│ API layer (FastAPI): Pydantic validation · routes · domain error → HTTP   │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │ method calls, under one lock
┌───────────────────────────────────▼───────────────────────────────────────┐
│ Domain core (pure Python, imports nothing from the web layer)             │
│                                                                           │
│                ┌──────────────── FulfillmentService ────────────────┐     │
│                │ init_catalog · process_order · process_restock     │     │
│                │ owns: catalog, stock, pending, orders, shipment log│     │
│                └──────────┬─────────────────────────────┬───────────┘     │
│                           │ pack(take)                  │ ship(shipment)  │
│                 ┌─────────▼─────────┐        ┌──────────▼───────────┐     │
│                 │ Packer (Protocol) │        │ ShipmentSink         │     │
│                 │  FFD by count     │        │  (Protocol)          │     │
│                 └───────────────────┘        └──────┬────────┬──────┘     │
│                                                     │        │            │
│                                          ConsoleSink│        │RecordingSink
│                                      (spec's stub) ─┘        └─ (tests)   │
└───────────────────────────────────────────────────────────────────────────┘
```

**Request flow for an order:** the frontend POSTs to `/api/orders` → Pydantic validates the body → the route takes the lock and calls `service.process_order` → the service records the order, runs a fulfillment pass, asks the `Packer` to split what it can ship, and hands each package to the `ShipmentSink` → the route returns the order's status and the shipments made by this call.

### Why these boundaries

- **The core is framework-free.** It can be tested directly, reused from a CLI or worker, and reasoned about without HTTP.
- **`ShipmentSink` is injected.** `ConsoleSink` satisfies the spec (print the shipment); tests inject `RecordingSink` and assert on a plain list instead of parsing stdout. That's two real implementations today, so the interface earns its place.
- **`Packer` is injected.** Packing is the trickiest algorithm, so it's tested on its own, and an optimal packer is an obvious alternative.

### What we deliberately did *not* abstract

Adding an interface has a cost: more files and more hops for a reader. We add one only when there is a real second implementation or an important test seam.

- **No allocation-policy interface.** FIFO is a loop inside `_fulfill`. Priority is future work; we'd extract a policy when a second policy exists.
- **No repository layer.** There's no database, so a repository would wrap a dict and nothing else. If we moved to Postgres, we would extract one then, and only the service would change.

---

## 7. Domain model and data structures

Code: [`backend/app/domain/models.py`](backend/app/domain/models.py), [`service.py`](backend/app/domain/service.py).

### Types

| Type | Fields | Notes |
| --- | --- | --- |
| `Product` | `id, name, mass_g` | Frozen |
| `OrderLine` | `product_id, quantity` | Used for both orders and restocks |
| `PendingOrder` | `order_id, seq, requested, remaining` | `seq` is the arrival number; `remaining` shrinks as units ship |
| `Shipment` | `shipment_id, order_id, lines, mass_g` | One package. `to_spec_dict()` gives the spec's `{order_id, shipped}` shape |

### State inside `FulfillmentService`

| State | Structure | Operations | Why |
| --- | --- | --- | --- |
| Catalog | `dict[product_id, Product]` | lookup O(1) | Immutable after init |
| Stock | `dict[product_id, int]` | read and update O(1) | Counts only, no lots |
| Pending | `dict[order_id, PendingOrder]` | iterate oldest first O(n), remove O(1), lookup O(1) | A queue that allows removal from the middle |
| Orders | `dict[order_id, PendingOrder]` | lookup O(1) | Idempotency and `GET /orders`; includes completed orders |
| Shipment log | `list[Shipment]` | append O(1) | Audit trail and the UI feed |

### Why an insertion-ordered dict for pending orders

Pending orders behave like a FIFO queue, but an order in the middle can finish before those ahead of it (it may want a different product). So we need ordered iteration *and* fast removal from anywhere.

| Structure | Iterate oldest first | Remove a finished order | Find by `order_id` |
| --- | --- | --- | --- |
| list | O(n) | O(n) (shifts) | O(n) |
| deque | O(n) | O(n) (fast only at the ends) | O(n) |
| doubly linked list | O(n) | O(1) if you hold the node | O(n) |
| **insertion-ordered dict** | O(n) | **O(1)** | **O(1)** |

Python's `dict` preserves insertion order (guaranteed since 3.7), so a plain `for` loop visits orders in arrival order. This is the same idea as Java's `LinkedHashMap`: a hash table with a linked list threaded through its entries.

Two details to remember:

- Adding or removing keys **while iterating** raises `RuntimeError`, so completed orders are collected during the loop and deleted after it. Mutating the *values* (an order's `remaining`) during the loop is fine.
- Deleting a key and re-inserting it moves it to the back. Nothing in this design does that.

### Order status is derived, never stored

| Condition | Status |
| --- | --- |
| shipped total = 0 | `PENDING` |
| 0 < shipped total < requested total | `PARTIALLY_SHIPPED` |
| shipped total = requested total | `FULFILLED` |

A stored status is one more field that can drift out of sync; a derived one can't.

---

## 8. Core algorithms

### 8.1 The fulfillment pass

Both `process_order` and `process_restock` change state and then call one shared pass, so all shipping logic lives in one place.

```python
def _fulfill(self) -> list[Shipment]:
    made, done = [], []
    for order_id, order in self.pending.items():            # oldest first
        take = {p: n for p, q in order.remaining.items()
                if (n := min(q, self.stock[p])) > 0}
        if not take:
            continue
        packages = self.packer.pack(take, self.catalog)     # pure: nothing changed yet
        shipments = [self._make_shipment(order_id, pkg) for pkg in packages]
        for p, q in take.items():                           # commit only after packing succeeded
            self.stock[p] -= q
            order.remaining[p] -= q
        for s in shipments:
            self.shipments.append(s)
            self.sink.ship(s)                               # prints {"order_id", "shipped"}
        made += shipments
        if order.is_complete():
            done.append(order_id)
    for order_id in done:                                   # delete after the loop
        del self.pending[order_id]
    return made
```

**Order of operations.** Packing is a pure function, so it runs before any state changes; stock and `remaining` are committed only once the packages exist. If a sink raised after the commit, stock would be spent without a recorded shipment. In-process sinks can't realistically fail, and a real shipping API would use an outbox (section 16). Shipping *before* committing would be worse: a crash in between could ship the same units twice.

### 8.2 Packing: First Fit Decreasing by count

Splitting units into packages of at most 1800 g is **bin packing**, which is NP-hard in general. The spec only requires that each package is ≤ 1800 g; it does not require the minimum number of packages. We still try to keep the count low, because each package is roughly a drone flight.

| Approach | Packages used | Cost | Verdict |
| --- | --- | --- | --- |
| Next Fit | ≤ 2 · OPT | O(n) | Wasteful |
| **First Fit Decreasing** | ≤ (11/9) · OPT + 6/9 | sort + fill | Standard heuristic, easy to explain |
| Exact (DP / ILP) | OPT | exponential | Overkill |

FFD is simple greedy with one extra step: sort heaviest first.

1. Sort the products in `take` by mass, heaviest first.
2. For each product, walk the open packages in the order they were opened. A package with remaining capacity c takes min(units left, ⌊c / mass⌋) units.
3. If units are still left, open a new package and repeat.

**Pack by count, not by unit.** Expanding quantities into individual units would make an order of 10,000 units cost 10,000 placements. Computing ⌊c / mass⌋ places many units at once, so the work depends on the number of products and packages, not the number of units.

**Why packing by count is still FFD.** Units of one product are adjacent in the sorted order, and a package's free capacity only shrinks. Once a package can't take one more unit of a product, it can't take any later unit of that product either. So putting ⌊c / mass⌋ units into each package in turn gives exactly the packages that unit-by-unit First Fit would give, and the 11/9 bound still applies.

**Ties: equal masses go in `product_id` order.** The sort key is `(-mass_g, product_id)`. Tied products never change the number of packages or their masses, since equal units use equal space. They only decide which product lands in which package. For example, 4 × FFP A+ (id 10) and 4 × FFP B+ (id 11), all 300 g, always pack as `{10: 4, 11: 2}` then `{11: 2}`, however the hospital listed the lines. Sorting by mass alone would also be deterministic (Python's sort is stable), but the output would then depend on the key order of `take`. With the id tie-breaker, the output depends only on what `take` contains, so tests can assert exact packages.

**Bad input is a programming error.** The packer skips zero quantities. It raises `ValueError` for a negative quantity or a product whose mass is outside (0, limit]. The service and catalog validation should make both impossible. Without the check, a too-heavy product would make the packer open empty packages forever. `ValueError` is deliberately not a `DomainError`, so if it ever happens the API returns a 500 instead of blaming the caller.

**Worked example** (the spec's sample order: 2 × RBC A+ at 700 g, 4 × FFP A+ at 300 g):

1. Total mass = 2 · 700 + 4 · 300 = 1400 + 1200 = 2600 g. Lower bound: ⌈2600 / 1800⌉ = 2 packages.
2. Sorted: RBC A+ (700 g) first, then FFP A+ (300 g).
3. RBC A+: package 1 is new, capacity 1800, fits ⌊1800 / 700⌋ = 2. Place both. Package 1 = 1400 g, remaining capacity 1800 − 1400 = 400.
4. FFP A+: package 1 fits ⌊400 / 300⌋ = 1. Place 1, package 1 = 1700 g. 3 left.
5. Open package 2: fits ⌊1800 / 300⌋ = 6 ≥ 3. Place 3, package 2 = 900 g.
6. Result: 2 packages (1700 g and 900 g), matching the lower bound, so optimal here.

```json
{"order_id": 123, "shipped": [{"product_id": 0, "quantity": 2}, {"product_id": 10, "quantity": 1}]}
{"order_id": 123, "shipped": [{"product_id": 10, "quantity": 3}]}
```

### 8.3 Complexity

For one fulfillment pass with N pending orders of about L lines each:

| Part | Cost |
| --- | --- |
| Allocation (scan orders, compute each take) | O(N · L) |
| Packing, per order that receives stock | O(L log L) to sort + O(L · P) to fill its P packages |
| Output | O(P) shipments |

**Scaling fix (future work):** a waiting index `product_id → set of order_ids`. A restock then visits only orders that need a restocked product, sorted by `seq` to keep FIFO, instead of every pending order.

---

## 9. Walkthrough: a full trace

Stock starts at 0. RBC A+ (id 0) weighs 700 g, FFP A+ (id 10) weighs 300 g.

| Step | Event | Pass | Ships | Stock after | Pending after |
| --- | --- | --- | --- | --- | --- |
| 1 | Order 1 wants 2 RBC | take = min(2, 0) = 0 | nothing | RBC 0 | O1: 2 RBC |
| 2 | Order 2 wants 3 FFP | O1: 0; O2: min(3, 0) = 0 | nothing | FFP 0 | O1: 2 RBC; O2: 3 FFP |
| 3 | Restock 1 RBC, 5 FFP | O1: min(2, 1) = 1; O2: min(3, 5) = 3 | O1: 700 g; O2: 3 · 300 = 900 g | RBC 1 − 1 = 0; FFP 5 − 3 = 2 | O1: 1 RBC |
| 4 | Restock 4 RBC | O1: min(1, 4) = 1 | O1: 700 g | RBC 4 − 1 = 3; FFP 2 | empty |

O2 was not blocked by O1 even though O1 arrived first, because they wanted different products.

### Scarce stock: how FIFO decides

A arrived first and wants 10 units of X. Then B, C, D, E each want 2. A restock of 8 arrives.

| Policy | A gets | B to E get | Orders completed |
| --- | --- | --- | --- |
| **Strict FIFO (ours)** | 8 | 0 | 0 |
| Completable first | 0 | 2 each | 4 |
| Proportional | 8 · 10/18 ≈ 4 | ≈ 1 each | 0 |

FIFO is predictable and never starves anyone, but one large order can absorb a restock that would have completed several small ones. With urgency data we would switch to priority classes with FIFO inside each class (section 16).

---

## 10. API contract

All routes are under `/api`. Interactive docs: `http://localhost:8000/docs`.

| Method | Path | Spec function | Body | Success | Errors |
| --- | --- | --- | --- | --- | --- |
| PUT | `/catalog` | `init_catalog` | JSON array of products | 201 | 409 already initialized, 422 invalid |
| POST | `/orders` | `process_order` | `{order_id, requested}` | 201: order status + shipments made now | 409 duplicate id with different payload, 409 no catalog, 422 invalid |
| POST | `/restocks` | `process_restock` | JSON array of `{product_id, quantity}` | 200: shipments made now | 409 no catalog, 422 invalid or unknown product |
| GET | `/catalog` | | | 200 (`[]` before `init_catalog`) | |
| GET | `/inventory` | | | 200: stock per product (`[]` before `init_catalog`) | |
| GET | `/orders` | | | 200: every order, oldest first, with derived status and per-line requested / shipped / remaining | |
| GET | `/orders/{id}` | | | 200 | 404 `OrderNotFoundError` |
| GET | `/shipments` | | | 200: newest first | |
| GET | `/health` | | | 200 | |
| POST | `/reset` | (demo only) | | 204: back to before `init_catalog` | |

**Preserving the spec's contracts.** Each write endpoint accepts exactly the spec's JSON shape; catalog and restock bodies are arrays, the order body is an object. Every package printed by `ConsoleSink` is exactly the spec's `ship_package` shape. The extra `shipment_id` and `mass_g` fields appear only in `GET /shipments`.

**Idempotency.** Re-sending `POST /orders` with the same `order_id` and the same requested quantities returns 201 with the order's current status and an empty `shipments` list. It is 201 rather than 200 so a retried request sees the same status code as the original. The same `order_id` with different quantities is a 409, because it's either a bug or a conflicting edit.

**Reset is demo only.** `POST /reset` is not in the spec. It clears the catalog, stock, orders, and shipments so the dashboard can start a fresh demo without restarting the server. `FulfillmentService.__init__` calls `reset()`, so all state is set up in one place and a reset can't miss a field. A real nest would not expose it; with deployment we'd remove it or put it behind an admin role.

**Error body.** Every error, domain or validation, has the shape `{"error": <name>, "detail": ...}`. For validation errors `detail` is Pydantic's list naming the exact field.

**Reads hold the lock too.** Building a response iterates the service's dicts; a concurrent write could change them mid-iteration.

**Why REST rather than RPC.** RPC style would mirror the spec's names (`POST /process_order`). REST names resources (`POST /orders`) and gives a consistent pattern for the reads the dashboard needs. The table above maps each spec function to its endpoint.

---

## 11. Concurrency

FastAPI runs plain `def` endpoints in a **thread pool**, so two requests can execute at the same time. Two concurrent orders could both read `stock[p] = 1` and both take it, breaking I2.

**Choice:** one `threading.Lock` (created in `app/main.py`) that every route holds for the duration of its service call. Every mutation is serialized, which is trivially correct. Throughput isn't a concern: a single nest handles orders at human speed.

| Option | Pros | Cons |
| --- | --- | --- |
| **One lock, one process (ours)** | Simple, obviously correct | One core; state lost on restart |
| `async def` endpoints with no `await` in the core | No lock needed | Subtle: one future `await` silently breaks atomicity |
| Single writer per nest (actor or queue) | Scales across nests, no locks | More moving parts |
| DB transactions with row locks | Works across processes | Deadlock risk; hot rows (O- blood) contend |

Scaling story: nests are independent, so the natural shard key is the nest. Run one writer per nest and scale horizontally across nests.

---

## 12. Errors and validation

Two layers, each catching what it's best at:

1. **Shape and type (API layer, Pydantic).** Missing fields, wrong types, unknown fields, quantity ≤ 0, empty order, product mass outside (0, 1800]. Returns 422 with the exact field.
2. **Domain rules (core).** Unknown product, duplicate order id, catalog state. Raised as domain exceptions in [`backend/app/domain/errors.py`](backend/app/domain/errors.py) and mapped to HTTP codes in one place, [`backend/app/api/errors.py`](backend/app/api/errors.py).

| Domain error | HTTP |
| --- | --- |
| `CatalogNotInitializedError` | 409 |
| `CatalogAlreadyInitializedError` | 409 |
| `DuplicateOrderError` | 409 |
| `InvalidCatalogError` | 422 |
| `UnknownProductError` | 422 |
| `OrderNotFoundError` | 404 |

All requests are all or nothing: validate every line, then apply.

---

## 13. Frontend

An operator dashboard for one nest, built to show how the system behaves.

The screen is split by **who acts**, because in the spec the nest doesn't create orders or stock: hospitals and suppliers call the API.

| Area | Who | Shows or does |
| --- | --- | --- |
| **Sidebar: Hospital** | Stand-in for a hospital system | Send an order; the order id is editable (prefilled with the next free one), so duplicate handling can be tried |
| **Sidebar: Supplier** | Stand-in for a supplier system | Deliver a restock, or the spec's sample restock |
| **Sidebar: Demo** | Plays both roles | A random order (60%) or restock (40%) every 1.5 s; **Reset demo** calls `POST /reset` and reloads the sample catalog |
| **Headline numbers** | Operator (read only) | Units in stock, orders waiting, packages shipped, average package fill |
| **Inventory** | Operator (read only) | Each product's stock and mass, and units still waited for; zero stock muted |
| **Packages shipped** | Operator (read only) | One card per package with a bar against the 1800 g limit, gridlines every 100 g |
| **Waiting for stock** | Operator (read only) | Orders oldest first; per line: shipped of requested |

The app is exactly one screen tall on desktop; each panel scrolls inside itself, so a long shipment feed never stretches the page. Below 1100 px everything stacks and the page scrolls instead.

**Color.** Product families are a categorical palette: red cells red, plasma orange, platelets teal, cryo indigo. It was checked with a colorblind-safety validator, light and dark separately (dark uses its own darker steps). Two pairs sit in the "needs secondary encoding" band, which the bars have: a 2 px gap between segments and a text legend under every bar. Status chips use the accent and a warm tone, never a product color.

The inventory panel shows stock next to what waiting orders still need, which makes invariant I4 visible: no product is ever both in stock and waited for. The sample catalog and sample restock are imported straight from `backend/samples/`, so there is one copy of the spec's data; `vite.config.ts` allows the dev server to read that folder.

Data comes from the GET endpoints through a small polling hook (`src/usePolling.ts`). One poll fetches inventory, orders, and shipments together, so the panels always agree with each other. TypeScript types are hand-written in `src/api.ts` to mirror the Pydantic schemas; there are only a handful. The Vite dev server proxies `/api` to the backend, so there is one origin and no CORS configuration.

---

## 14. Key decisions and tradeoffs

Each decision has a stated choice and the condition under which we'd choose differently.

| Decision | Choice | What it gives up | We'd change it if |
| --- | --- | --- | --- |
| Ship now vs. consolidate | Ship partial fills immediately | Flight efficiency. Three restocks of 1 × 600 g give 3 packages at 600 / 1800 ≈ 33% full instead of 1 at 100% | Flight cost data existed: then ship when a fill %, max wait, or urgency threshold is met |
| Allocation | Strict FIFO, per product | A big early order can absorb a restock that would complete several small ones | Orders carried urgency: then priority classes, FIFO within each, plus aging |
| When stock is spent | Decremented when packages are created | No model of operator packing or pack failures | We built an operator pack queue: then available vs. reserved, and reserved → packed → shipped |
| State model | Mutable state + append-only shipment log | Full replay and time travel | Audit needs grew: then event sourcing with snapshots |
| Sync vs. async | Synchronous core; `ship_package` called inline | Isolation from downstream failures | `ship_package` became a network call: then an outbox with retries and idempotent shipment IDs |
| Concurrency | One lock, one process | Throughput beyond one core | Multiple processes or nests: then a single writer per nest, or DB transactions |
| Validation | Whole request rejected if any line is invalid | Best-effort partial acceptance | Callers preferred best effort |
| Packing | FFD by count | Guaranteed optimal package count | Package count dominated cost: then an exact packer for small orders |
| Packer ties | Equal masses packed in `product_id` order | Packages following the hospital's line order | Operators wanted packages to mirror the order form |
| Packer bad input | `ValueError` (a bug, so 500), not a domain error | A friendly error if the service ever sends bad input | Never: the service validates first, so this should be unreachable |
| IDs and time | Sequential shipment IDs | Uniqueness across processes | Distributed deployment: then UUIDs |

---

## 15. Testing strategy

The core is tested directly with `RecordingSink`, so tests assert on a list of shipments instead of parsing console output.

- **Packer unit tests:** exactly 1800 g fits; 1801 g needs two packages; one heavy item; many light items; large quantities (10,000 units) stay fast; quantities are conserved; no empty packages; inputs not mutated.
- **Service unit tests:** each validation rule; idempotent duplicate order; conflicting duplicate order; duplicate lines summed in orders and restocks; catalog rules.
- **Scenario tests:** the spec's sample catalog, restock, and order; the trace in section 9; the same order sent twice ships only once; duplicate restock lines add up.
- **Property tests (hypothesis):** random catalogs, orders, and restocks in random interleavings, asserting I1 to I5 after every call.
- **API tests:** FastAPI `TestClient` for status codes, error mapping, and response shapes.

Run with `make test`; lint with `make lint`.

---

## 16. Out of scope and future work

| Item | Why not now | Design we'd use |
| --- | --- | --- |
| Cold-chain separation | Not in the spec's data | `storage_class` on products; the packer only groups items of the same class |
| Expiry / shelf life | No lot or date data | Inventory as lots, first-expired-first-out, skip lots expiring before delivery |
| Urgency / priority | No priority field | Priority classes with FIFO inside, plus aging so nothing starves |
| Blood-type substitution | Clinical decision | Explicit substitution rules approved per order |
| Consolidation threshold | No flight cost data | A dispatch policy: ship when fill %, max wait, or urgency is met |
| Orders that never complete | Spec assumes restocks arrive | TTL plus an operator alert |
| `ship_package` failure | Stub only prints | Outbox table written with the stock change; async delivery with retries; idempotent shipment IDs (at-least-once delivery) |
| Operator pack confirmation | Spec ships directly | Available vs. reserved stock; reserved → packed → shipped; a failed pack releases the reservation |
| Cancellations and edits | Not in spec | Release remaining demand, re-run the fulfillment pass |
| Persistence | No durability requirement | Postgres behind a repository extracted from the service |
| Multiple nests / processes | Single nest in spec | Partition by nest; single writer per nest |
| Volume limits | Only mass given | Volume on products, a second packing constraint |
| Restock cost with many pending orders | Fine at demo scale | Waiting index `product_id → order_ids` |
| Auth, audit, CI, Docker | Internal demo | API keys or SSO; audit log from shipments; GitHub Actions running `make lint test`; a Dockerfile per service |

---

## 17. Build plan

Each step ends with passing tests and its own commit.

- [x] **0. Scaffold:** repo layout, tooling, health endpoint, spec samples, sinks, model types, this document
- [x] **1. Packer:** `FirstFitDecreasingPacker.pack` + unit tests
- [x] **2. Service:** `init_catalog`, `process_order`, `process_restock`, `_fulfill` + unit and scenario tests
- [x] **3. Property tests:** invariants I1 to I5 under random operation sequences
- [x] **4. API:** request handling, response models, error mapping, API tests
- [x] **5. Frontend:** inventory, pending queue, shipment feed, controls, simulate
- [x] **6. Polish:** README run instructions verified end to end, screenshots

---

## 18. Known tensions and open questions

Things a reviewer might push on, written down so the answer is ready. When one is resolved, record the decision here and in the section it affects.

### Tensions in the design

| # | Tension | Where | Our answer |
| --- | --- | --- | --- |
| T1 | `Packer` is a Protocol with one implementation, while CLAUDE.md says no abstraction without a second implementation | §6, `packer.py` | It is a test seam for the trickiest algorithm, and a Protocol costs one class with no runtime cost. `ShipmentSink` has two real implementations, so it is clearly justified. We'd accept removing `Packer` if a reviewer prefers. |
| T2 | Catalog mass is checked twice: Pydantic (`ProductIn.mass_g`) and the core (`InvalidCatalogError`) | §12, `schemas.py` | Defense in depth. Over HTTP, Pydantic always fires first with a 422. The core check protects direct callers (tests, a future CLI). |
| T3 | `PendingOrder.remaining` defaults to `{}`, and `is_complete()` is `True` for an empty dict | `models.py` | The service must copy `requested` into `remaining` when it accepts an order. A test covers this. |
| T4 | The symbol for I5 only states "non-empty"; "belongs to exactly one order" holds because `Shipment` has a single `order_id` | §2 | Enforced by the type, not by a runtime check. |
| T5 | The packer raises `ValueError` on bad input instead of a `DomainError` | §8.2 | Bad input to the packer means a bug in the service, not a bad request, so it should surface as a 500. |

### Open questions

| # | Question | Status |
| --- | --- | --- |
| Q1 | Repeated order with the same payload: §4 said "return the original result", §10 says "current status, ships nothing new", the service docstring says `[]` | Resolved in step 2: the service returns `[]` (no new shipments); the API returns the current status. §4 now matches §10. |
| Q2 | Does "same payload" compare summed quantities (so `[{0:1},{0:1}]` equals `[{0:2}]`)? | Resolved in step 2: yes, both mean the same order |
| Q3 | Is an empty restock `[]` or empty catalog `[]` accepted? | Resolved in step 2: empty restock is a no-op; empty catalog is `InvalidCatalogError` (422) |
| Q4 | Upper bound on quantities? 10^9 units of 40 g would create about 22 million packages | Open |
| Q5 | A reset endpoint for demos? `init_catalog` works once per server start | Resolved: yes, `POST /reset`, documented as demo only (§10) |
| Q6 | Status code for an idempotent replay of `POST /orders`: 200 or 201? | Resolved in step 4: 201, the same as the original request |
