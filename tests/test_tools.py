import pytest

from app.tools import get_order, get_seller_metrics, search_policy

pytestmark = pytest.mark.integration


def test_get_order_returns_known_order():
    result = get_order("00010242fe8c5a6d1ba2dd792cb16214")
    assert result is not None
    assert result.order_status == "delivered"
    assert result.seller_count == 1


def test_get_order_returns_none_for_unknown_id():
    assert get_order("does-not-exist") is None


def test_get_seller_metrics_returns_known_seller():
    result = get_seller_metrics("48436dade18ac8b2bce089ec2a041202")
    assert result is not None
    assert result.order_count >= 1


def test_search_policy_finds_compensation_doc():
    results = search_policy("What compensation do I get for a late delivery?", top_k=5)
    assert len(results) > 0
    assert any(r.doc_id == "POL-COMP-001" for r in results)
