from decimal import Decimal

import pytest

from app.tools import calculate_compensation, estimate_delivery_risk

pytestmark = pytest.mark.integration


def test_estimate_delivery_risk_on_time_order():
    # 00010242fe8c5a6d1ba2dd792cb16214: delivered 2017-09-20, estimated 2017-09-29
    result = estimate_delivery_risk("00010242fe8c5a6d1ba2dd792cb16214")
    assert result is not None
    assert result.is_late is False
    assert result.severity is None


def test_calculate_compensation_not_eligible_when_on_time():
    result = calculate_compensation("00010242fe8c5a6d1ba2dd792cb16214")
    assert result is not None
    assert result.eligible is False
    assert result.proposed_amount is None


def test_calculate_compensation_unknown_order_returns_none():
    assert calculate_compensation("does-not-exist") is None


def test_calculate_compensation_eligible_moderate_delay():
    # 33a3edb84b9df4cb49546859b990ac6d: estimated 2018-03-16, delivered
    # 2018-03-22 (6 days late -> moderate); order_value = 67.50 in the DB.
    # This exercises the actual proposal-computation path (order_value * pct)
    # that the two tests above never reach, since both return early on
    # ineligibility.
    result = calculate_compensation("33a3edb84b9df4cb49546859b990ac6d")
    assert result is not None
    assert result.eligible is True
    assert result.severity == "moderate"
    assert result.compensation_percentage == 0.25
    assert result.proposed_amount == Decimal("67.50") * Decimal("0.25")
    assert result.cap_applied is False
