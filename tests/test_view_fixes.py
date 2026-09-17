from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import get_engine
from app.tools import get_order

pytestmark = pytest.mark.integration


def test_get_order_value_not_inflated_by_multi_item_single_seller_order():
    # 00143d0f86d6fbd9f9b38ab440ac16f5: 1 seller, 3 items, 1 payment of
    # 109.29 — pre-fix this returned 327.87 (3x inflated).
    # Compared against a Decimal (not a bare float) because order_value
    # comes back from Postgres as a Decimal, and pytest.approx raises
    # TypeError comparing a Decimal actual to a float expected.
    result = get_order("00143d0f86d6fbd9f9b38ab440ac16f5")
    assert result is not None
    assert result.order_value == pytest.approx(Decimal("109.29"))


def test_vw_seller_metrics_matches_order_weighted_truth():
    # A seller with a known true late-delivery rate, computed independently
    # via DISTINCT order_id (not through the view under test).
    with get_engine().connect() as conn:
        seller_id = conn.execute(text("""
            SELECT seller_id FROM shopops_data.order_items
            GROUP BY seller_id HAVING COUNT(DISTINCT order_id) >= 20 LIMIT 1
        """)).scalar()

        true_rate = conn.execute(text("""
            SELECT AVG(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
                             THEN 1.0 ELSE 0.0 END)
            FROM (SELECT DISTINCT seller_id, order_id FROM shopops_data.order_items
                  WHERE seller_id = :seller_id) so
            JOIN shopops_data.orders o ON o.order_id = so.order_id
        """), {"seller_id": seller_id}).scalar()

        view_rate = conn.execute(text("""
            SELECT late_delivery_rate FROM shopops_views.vw_seller_metrics
            WHERE seller_id = :seller_id
        """), {"seller_id": seller_id}).scalar()

    assert view_rate == pytest.approx(true_rate)
