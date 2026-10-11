from __future__ import annotations

import json
from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def load_sample(name: str):
    return json.loads((SAMPLES / name).read_text())


@pytest.fixture
def sample_catalog():
    return load_sample("catalog.json")


@pytest.fixture
def sample_restock():
    return load_sample("restock.json")


@pytest.fixture
def sample_order():
    return load_sample("order.json")
