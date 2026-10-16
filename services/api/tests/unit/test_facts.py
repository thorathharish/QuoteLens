from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.enums import Provenance
from app.domain.facts import Fact, actual, assumed, calculated, recommended, unavailable


def test_helpers_set_provenance() -> None:
    assert actual(Decimal(2), "ev_1").provenance is Provenance.ACTUAL
    assert calculated(Decimal(4), "qty_per × volume").provenance is Provenance.CALCULATED
    assert assumed(Decimal("0.02"), "Price-tier scrap default").provenance is Provenance.ASSUMED
    assert recommended("off_1", "Cheapest with full stock").provenance is Provenance.RECOMMENDED
    assert unavailable("No distributor price at this quantity").provenance is Provenance.UNAVAILABLE


def test_unavailable_has_no_value_and_is_not_available() -> None:
    fact: Fact[Decimal] = unavailable("No stock data")
    assert fact.value is None
    assert not fact.is_available


@pytest.mark.parametrize(
    "kwargs",
    [
        {"provenance": Provenance.ACTUAL, "value": 1},  # no evidence
        {"provenance": Provenance.CALCULATED, "value": 1},  # no formula
        {"provenance": Provenance.ASSUMED, "value": 1},  # no note
        {"provenance": Provenance.RECOMMENDED, "value": 1},  # no note
        {"provenance": Provenance.UNAVAILABLE, "value": 1, "note": "x"},  # has value
        {"provenance": Provenance.UNAVAILABLE},  # no reason
        {"provenance": Provenance.CALCULATED, "formula": "a+b"},  # no value: must be UNAVAILABLE
    ],
)
def test_invariants_reject_unexplained_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Fact[int].model_validate(kwargs)


def test_fact_round_trips_through_json_with_exact_decimals() -> None:
    fact = calculated(Decimal("1234.5678"), "buy_qty × unit_price", "ev_1", unit="USD")
    restored = Fact[Decimal].model_validate(fact.model_dump(mode="json"))
    assert restored == fact
    assert restored.value == Decimal("1234.5678")


def test_facts_are_immutable() -> None:
    fact = actual(1, "ev_1")
    with pytest.raises(ValidationError):
        fact.value = 2  # type: ignore[misc]
