"""FirstFitDecreasingPacker: package mass limit, conservation, and the FFD order."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.models import MAX_PACKAGE_MASS_G, Product
from app.domain.packer import FirstFitDecreasingPacker, Package

RBC_A = 0  # 700 g
FFP_A = 10  # 300 g
FFP_B = 11  # 300 g
CRYO_A = 8  # 40 g


@pytest.fixture
def catalog(sample_catalog) -> dict[int, Product]:
    return {
        p["product_id"]: Product(p["product_id"], p["product_name"], p["mass_g"])
        for p in sample_catalog
    }


def mass(package: Package, catalog: dict[int, Product]) -> int:
    return sum(catalog[p].mass_g * q for p, q in package.items())


def totals(packages: list[Package]) -> dict[int, int]:
    out: dict[int, int] = {}
    for package in packages:
        for p, q in package.items():
            out[p] = out.get(p, 0) + q
    return out


def test_spec_sample_order_packs_into_two_packages(catalog):
    packages = FirstFitDecreasingPacker().pack({RBC_A: 2, FFP_A: 4}, catalog)
    assert packages == [{RBC_A: 2, FFP_A: 1}, {FFP_A: 3}]
    assert [mass(p, catalog) for p in packages] == [1700, 900]


def test_exactly_the_limit_fits_in_one_package(catalog):
    assert FirstFitDecreasingPacker().pack({FFP_A: 6}, catalog) == [{FFP_A: 6}]


def test_one_gram_over_the_limit_needs_two_packages():
    catalog = {1: Product(1, "a", 1000), 2: Product(2, "b", 801)}
    assert FirstFitDecreasingPacker().pack({1: 1, 2: 1}, catalog) == [{1: 1}, {2: 1}]


def test_single_item_at_the_limit():
    catalog = {1: Product(1, "heavy", MAX_PACKAGE_MASS_G)}
    assert FirstFitDecreasingPacker().pack({1: 2}, catalog) == [{1: 1}, {1: 1}]


def test_many_light_items(catalog):
    packer = FirstFitDecreasingPacker()
    assert packer.pack({CRYO_A: 45}, catalog) == [{CRYO_A: 45}]
    assert packer.pack({CRYO_A: 46}, catalog) == [{CRYO_A: 45}, {CRYO_A: 1}]


def test_light_items_fill_gaps_left_by_heavy_ones(catalog):
    # 2 x 700 g leaves 400 g free, exactly enough for 10 x 40 g.
    packages = FirstFitDecreasingPacker().pack({CRYO_A: 10, RBC_A: 2}, catalog)
    assert packages == [{RBC_A: 2, CRYO_A: 10}]


def test_equal_masses_are_packed_in_product_id_order(catalog):
    # FFP B is listed first, but FFP A has the lower id, so it is placed first.
    packages = FirstFitDecreasingPacker().pack({FFP_B: 4, FFP_A: 4}, catalog)
    assert packages == [{FFP_A: 4, FFP_B: 2}, {FFP_B: 2}]


def test_zero_quantities_and_empty_take_give_no_packages(catalog):
    packer = FirstFitDecreasingPacker()
    assert packer.pack({}, catalog) == []
    assert packer.pack({RBC_A: 0}, catalog) == []
    assert packer.pack({RBC_A: 0, FFP_A: 1}, catalog) == [{FFP_A: 1}]


def test_negative_quantity_raises(catalog):
    with pytest.raises(ValueError):
        FirstFitDecreasingPacker().pack({RBC_A: -1}, catalog)


def test_product_over_the_limit_raises(catalog):
    with pytest.raises(ValueError):
        FirstFitDecreasingPacker(max_mass_g=600).pack({RBC_A: 1}, catalog)


def test_inputs_are_not_mutated(catalog):
    take = {RBC_A: 2, FFP_A: 4}
    take_before, catalog_before = dict(take), dict(catalog)
    FirstFitDecreasingPacker().pack(take, catalog)
    assert take == take_before
    assert catalog == catalog_before


def test_large_quantity_packs_by_count(catalog):
    packages = FirstFitDecreasingPacker().pack({CRYO_A: 10_000}, catalog)
    assert len(packages) == 223  # ceil(10_000 / 45)
    assert totals(packages) == {CRYO_A: 10_000}


def test_custom_limit_is_respected(catalog):
    packages = FirstFitDecreasingPacker(max_mass_g=1000).pack({RBC_A: 2, FFP_A: 1}, catalog)
    assert packages == [{RBC_A: 1, FFP_A: 1}, {RBC_A: 1}]


@given(
    masses=st.lists(st.integers(1, MAX_PACKAGE_MASS_G), min_size=1, max_size=8),
    data=st.data(),
)
def test_packages_are_within_limit_non_empty_and_conserve_quantities(masses, data):
    catalog = {i: Product(i, f"p{i}", m) for i, m in enumerate(masses)}
    take = {i: data.draw(st.integers(0, 50)) for i in catalog}

    packages = FirstFitDecreasingPacker().pack(take, catalog)

    assert all(mass(p, catalog) <= MAX_PACKAGE_MASS_G for p in packages)
    assert all(p and all(q > 0 for q in p.values()) for p in packages)
    assert totals(packages) == {p: q for p, q in take.items() if q > 0}
