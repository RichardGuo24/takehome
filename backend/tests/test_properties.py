"""Property tests: invariants I1 to I5 (DESIGN.md section 2) after every call.

Hypothesis builds a random catalog and a random sequence of orders and restocks.
Order ids come from a small range so duplicate ids happen, and product ids
sometimes fall outside the catalog so rejected requests happen too.
"""

from __future__ import annotations

import copy
from collections import Counter

from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.errors import DomainError
from app.domain.models import MAX_PACKAGE_MASS_G, OrderLine, Product
from app.domain.packer import FirstFitDecreasingPacker
from app.domain.service import FulfillmentService
from app.domain.sinks import RecordingSink

MAX_PRODUCTS = 5

masses = st.lists(st.integers(1, MAX_PACKAGE_MASS_G), min_size=1, max_size=MAX_PRODUCTS)
# Ids up to MAX_PRODUCTS, so an id can be one past the catalog and get rejected.
line_lists = st.lists(
    st.builds(OrderLine, st.integers(0, MAX_PRODUCTS), st.integers(1, 20)), max_size=4
)
operations = st.lists(
    st.one_of(
        st.tuples(st.just("order"), st.integers(0, 6), line_lists.filter(bool)),
        st.tuples(st.just("restock"), st.none(), line_lists),
    ),
    max_size=25,
)


def state(service: FulfillmentService) -> tuple:
    return copy.deepcopy((service.stock, service.orders, service.pending, service.shipments))


def check_invariants(service: FulfillmentService, sink: RecordingSink, restocked: Counter) -> None:
    catalog = service.catalog
    assert catalog is not None
    shipped: Counter = Counter()  # (order_id, product_id) -> units
    for s in service.shipments:
        # I1: no package over the limit, and its recorded mass is right.
        assert s.mass_g == sum(catalog[p].mass_g * q for p, q in s.lines.items())
        assert s.mass_g <= MAX_PACKAGE_MASS_G
        # I5: non-empty, and it belongs to an order we accepted.
        assert s.lines and all(q > 0 for q in s.lines.values())
        assert s.order_id in service.orders
        for p, q in s.lines.items():
            shipped[s.order_id, p] += q

    # I2: stock never negative.
    assert all(q >= 0 for q in service.stock.values())

    # I3: per order and product, shipped + remaining = requested.
    for order_id, order in service.orders.items():
        for p, q in order.requested.items():
            assert shipped[order_id, p] + order.remaining[p] == q

    # I4: no stock held while a pending order needs it.
    for p, q in service.stock.items():
        assert q == 0 or all(o.remaining.get(p, 0) == 0 for o in service.pending.values())

    # Bookkeeping: pending is exactly the unfinished orders, stock is restocks minus
    # shipments, and the sink saw every shipment.
    assert set(service.pending) == {i for i, o in service.orders.items() if not o.is_complete()}
    for p in catalog:
        units_shipped = sum(q for (_, prod), q in shipped.items() if prod == p)
        assert service.stock[p] == restocked[p] - units_shipped
    assert sink.shipments == service.shipments


@settings(max_examples=300)
@given(masses=masses, ops=operations)
def test_invariants_hold_after_every_call(masses, ops):
    sink = RecordingSink()
    service = FulfillmentService(FirstFitDecreasingPacker(), sink)
    service.init_catalog(Product(i, f"p{i}", m) for i, m in enumerate(masses))
    restocked: Counter = Counter()

    for kind, order_id, lines in ops:
        before = state(service)
        try:
            if kind == "order":
                service.process_order(order_id, lines)
            else:
                service.process_restock(lines)
                for line in lines:
                    restocked[line.product_id] += line.quantity
        except DomainError:
            # A rejected request must change nothing.
            assert state(service) == before
        check_invariants(service, sink, restocked)

    # Eventually: a restock covering every remaining unit empties the queue.
    needed: Counter = Counter()
    for order in service.pending.values():
        needed.update(order.remaining)
    service.process_restock([OrderLine(p, q) for p, q in needed.items() if q > 0])
    restocked.update(needed)
    assert service.pending == {}
    check_invariants(service, sink, restocked)
