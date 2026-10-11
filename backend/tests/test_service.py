"""FulfillmentService: validation rules, FIFO allocation, and the spec's scenarios."""

from __future__ import annotations

import pytest

from app.domain.errors import (
    CatalogAlreadyInitializedError,
    CatalogNotInitializedError,
    DuplicateOrderError,
    InvalidCatalogError,
    UnknownProductError,
)
from app.domain.models import OrderLine, Product
from app.domain.packer import FirstFitDecreasingPacker
from app.domain.service import FulfillmentService
from app.domain.sinks import RecordingSink

RBC_A = 0  # 700 g
RBC_B = 1  # 700 g
FFP_A = 10  # 300 g


def lines(*pairs: tuple[int, int]) -> list[OrderLine]:
    return [OrderLine(p, q) for p, q in pairs]


def shipped(shipments) -> list[tuple[int, dict[int, int]]]:
    return [(s.order_id, s.lines) for s in shipments]


@pytest.fixture
def sink() -> RecordingSink:
    return RecordingSink()


@pytest.fixture
def empty_service(sink) -> FulfillmentService:
    return FulfillmentService(FirstFitDecreasingPacker(), sink)


@pytest.fixture
def service(empty_service, sample_catalog) -> FulfillmentService:
    empty_service.init_catalog(
        Product(p["product_id"], p["product_name"], p["mass_g"]) for p in sample_catalog
    )
    return empty_service


# ---- init_catalog -----------------------------------------------------------


def test_init_catalog_starts_every_product_at_zero(service):
    assert len(service.catalog) == 13
    assert service.stock == {p: 0 for p in range(13)}


def test_second_init_catalog_raises(service):
    with pytest.raises(CatalogAlreadyInitializedError):
        service.init_catalog([Product(99, "x", 100)])


@pytest.mark.parametrize(
    "products",
    [
        [],
        [Product(1, "a", 100), Product(1, "b", 200)],
        [Product(1, "zero", 0)],
        [Product(1, "too heavy", 1801)],
    ],
    ids=["empty", "duplicate id", "zero mass", "over limit"],
)
def test_invalid_catalog_raises_and_leaves_service_uninitialized(empty_service, products):
    with pytest.raises(InvalidCatalogError):
        empty_service.init_catalog(products)
    assert empty_service.catalog is None


def test_catalog_at_exactly_the_limit_is_accepted(empty_service):
    empty_service.init_catalog([Product(1, "heavy", 1800)])
    assert empty_service.stock == {1: 0}


def test_order_and_restock_before_catalog_raise(empty_service):
    with pytest.raises(CatalogNotInitializedError):
        empty_service.process_order(1, lines((0, 1)))
    with pytest.raises(CatalogNotInitializedError):
        empty_service.process_restock(lines((0, 1)))


# ---- validation is all or nothing ---------------------------------------------


def test_order_with_unknown_product_changes_nothing(service):
    with pytest.raises(UnknownProductError):
        service.process_order(1, lines((RBC_A, 1), (99, 1)))
    assert service.orders == {}
    assert service.pending == {}


def test_restock_with_unknown_product_changes_nothing(service):
    with pytest.raises(UnknownProductError):
        service.process_restock(lines((RBC_A, 5), (99, 1)))
    assert service.stock[RBC_A] == 0


def test_empty_restock_is_a_no_op(service):
    assert service.process_restock([]) == []
    assert all(q == 0 for q in service.stock.values())


# ---- shipping -----------------------------------------------------------------


def test_spec_sample(service, sink, sample_restock, sample_order):
    service.process_restock(lines(*((r["product_id"], r["quantity"]) for r in sample_restock)))
    made = service.process_order(
        sample_order["order_id"],
        lines(*((r["product_id"], r["quantity"]) for r in sample_order["requested"])),
    )

    assert shipped(made) == [(123, {RBC_A: 2, FFP_A: 1}), (123, {FFP_A: 3})]
    assert [s.mass_g for s in made] == [1700, 900]
    assert service.stock[RBC_A] == 30 - 2
    assert service.stock[FFP_A] == 5 - 4
    assert service.pending == {}
    assert sink.shipments == made == service.shipments


def test_order_with_no_stock_waits(service, sink):
    assert service.process_order(1, lines((RBC_A, 2))) == []
    assert service.pending[1].remaining == {RBC_A: 2}
    assert not service.pending[1].is_complete()
    assert sink.shipments == []


def test_partial_fill_ships_now_and_the_rest_after_restock(service):
    service.process_restock(lines((FFP_A, 4)))
    made = service.process_order(1, lines((FFP_A, 10)))
    assert shipped(made) == [(1, {FFP_A: 4})]
    assert service.pending[1].remaining == {FFP_A: 6}

    made = service.process_restock(lines((FFP_A, 6)))
    assert shipped(made) == [(1, {FFP_A: 6})]
    assert service.pending == {}
    assert service.stock[FFP_A] == 0


def test_design_trace(service):
    """DESIGN.md section 9, step by step."""
    assert service.process_order(1, lines((RBC_A, 2))) == []
    assert service.process_order(2, lines((FFP_A, 3))) == []

    made = service.process_restock(lines((RBC_A, 1), (FFP_A, 5)))
    assert shipped(made) == [(1, {RBC_A: 1}), (2, {FFP_A: 3})]
    assert [s.mass_g for s in made] == [700, 900]
    assert service.stock[RBC_A] == 0
    assert service.stock[FFP_A] == 2
    assert list(service.pending) == [1]

    made = service.process_restock(lines((RBC_A, 4)))
    assert shipped(made) == [(1, {RBC_A: 1})]
    assert service.stock[RBC_A] == 3
    assert service.pending == {}


def test_scarce_stock_goes_to_the_oldest_order(service):
    service.process_order(1, lines((FFP_A, 10)))
    for order_id in range(2, 6):
        service.process_order(order_id, lines((FFP_A, 2)))

    made = service.process_restock(lines((FFP_A, 8)))

    assert {s.order_id for s in made} == {1}
    assert service.pending[1].remaining == {FFP_A: 2}
    assert list(service.pending) == [1, 2, 3, 4, 5]


def test_new_order_cannot_cut_the_line(service):
    service.process_order(1, lines((RBC_A, 5)))
    service.process_restock(lines((RBC_A, 3)))
    assert service.process_order(2, lines((RBC_A, 1))) == []

    # Order 1 still needs 2, so it takes the whole restock; order 2 keeps waiting.
    made = service.process_restock(lines((RBC_A, 2)))
    assert shipped(made) == [(1, {RBC_A: 2})]
    assert list(service.pending) == [2]


def test_waiting_order_does_not_block_other_products(service):
    service.process_order(1, lines((RBC_A, 1)))
    service.process_restock(lines((RBC_B, 1)))
    made = service.process_order(2, lines((RBC_B, 1)))
    assert shipped(made) == [(2, {RBC_B: 1})]
    assert list(service.pending) == [1]


def test_duplicate_lines_are_summed(service):
    service.process_restock(lines((FFP_A, 2), (FFP_A, 3)))
    assert service.stock[FFP_A] == 5

    service.process_order(1, lines((FFP_A, 1), (FFP_A, 1)))
    assert service.orders[1].requested == {FFP_A: 2}
    assert service.stock[FFP_A] == 3


def test_shipments_have_sequential_ids_and_correct_mass(service):
    service.process_restock(lines((RBC_A, 3), (FFP_A, 1)))
    made = service.process_order(1, lines((RBC_A, 3), (FFP_A, 1)))
    assert [s.shipment_id for s in made] == [1, 2]
    assert [s.mass_g for s in made] == [1400 + 300, 700]


# ---- duplicate order ids --------------------------------------------------------


def test_same_order_twice_ships_once(service, sink):
    service.process_restock(lines((FFP_A, 10)))
    first = service.process_order(1, lines((FFP_A, 2)))
    assert service.process_order(1, lines((FFP_A, 2))) == []
    assert sink.shipments == first
    assert service.stock[FFP_A] == 8


def test_replay_compares_summed_quantities(service):
    service.process_order(1, lines((FFP_A, 2)))
    assert service.process_order(1, lines((FFP_A, 1), (FFP_A, 1))) == []
    assert len(service.orders) == 1


def test_same_id_with_different_lines_raises(service):
    service.process_order(1, lines((FFP_A, 2)))
    with pytest.raises(DuplicateOrderError):
        service.process_order(1, lines((FFP_A, 3)))
    assert service.orders[1].requested == {FFP_A: 2}


def test_completed_orders_are_kept_for_lookup(service):
    service.process_restock(lines((FFP_A, 1)))
    service.process_order(1, lines((FFP_A, 1)))
    assert 1 not in service.pending
    assert service.orders[1].is_complete()
    with pytest.raises(DuplicateOrderError):
        service.process_order(1, lines((FFP_A, 2)))
