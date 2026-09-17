from decimal import Decimal

from qdrant_client import QdrantClient, models
from sqlalchemy import text

from app.config import settings
from app.db import get_engine
from app.schemas import (
    CompensationProposal,
    OrderTimeline,
    PolicyEvidence,
    RiskAssessment,
    SellerMetrics,
)

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
POLICY_COLLECTION = "shopops_policy"

_qdrant_client: QdrantClient | None = None


def _get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=settings.qdrant_url)
    return _qdrant_client


def get_order(order_id: str) -> OrderTimeline | None:
    query = text("""
        SELECT order_id, order_status, order_purchase_timestamp,
               order_estimated_delivery_date, order_delivered_customer_date,
               SUM(order_value) AS order_value, COUNT(DISTINCT seller_id) AS seller_count
        FROM shopops_views.vw_order_ops
        WHERE order_id = :order_id
        GROUP BY order_id, order_status, order_purchase_timestamp,
                 order_estimated_delivery_date, order_delivered_customer_date
    """)
    with get_engine().connect() as conn:
        row = conn.execute(query, {"order_id": order_id}).mappings().first()
    if row is None:
        return None
    return OrderTimeline(
        order_id=row["order_id"],
        order_status=row["order_status"],
        purchase_timestamp=row["order_purchase_timestamp"],
        estimated_delivery_date=row["order_estimated_delivery_date"],
        delivered_customer_date=row["order_delivered_customer_date"],
        order_value=row["order_value"],
        seller_count=row["seller_count"],
    )


def get_seller_metrics(seller_id: str) -> SellerMetrics | None:
    query = text("""
        SELECT seller_id, order_count, late_delivery_rate, avg_review_score
        FROM shopops_views.vw_seller_metrics
        WHERE seller_id = :seller_id
    """)
    with get_engine().connect() as conn:
        row = conn.execute(query, {"seller_id": seller_id}).mappings().first()
    if row is None:
        return None
    return SellerMetrics(**row)


def search_policy(query: str, domain: str | None = None, top_k: int = 5) -> list[PolicyEvidence]:
    top_k = min(top_k, 5)
    query_filter = None
    if domain is not None:
        query_filter = models.Filter(
            must=[models.FieldCondition(key="domain", match=models.MatchValue(value=domain))]
        )
    results = _get_qdrant_client().query_points(
        collection_name=POLICY_COLLECTION,
        query=models.Document(text=query, model=EMBEDDING_MODEL),
        query_filter=query_filter,
        limit=top_k,
    )
    return [
        PolicyEvidence(
            doc_id=p.payload["doc_id"],
            version=p.payload["version"],
            section=p.payload["section"],
            excerpt=p.payload["excerpt"],
            score=p.score,
        )
        for p in results.points
    ]


_SEVERITY_BANDS = [(3, "minor"), (7, "moderate")]  # >3 and <=7 -> moderate; >7 -> severe
# Decimal, not float: order_value comes back from Postgres as a Decimal
# (NUMERIC column), and Decimal * float raises TypeError in Python —
# both operands must be Decimal.
_COMPENSATION_PCT = {"minor": Decimal("0.10"), "moderate": Decimal("0.25"), "severe": Decimal("0.50")}
_SEVERE_CAP = Decimal(150)


def _severity_for_delay(delay_days: int) -> str:
    for threshold, label in _SEVERITY_BANDS:
        if delay_days <= threshold:
            return label
    return "severe"


def estimate_delivery_risk(order_id: str) -> RiskAssessment | None:
    query = text("""
        SELECT order_id, order_status, order_estimated_delivery_date,
               order_delivered_customer_date
        FROM shopops_views.vw_delivery_risk_inputs
        WHERE order_id = :order_id
    """)
    with get_engine().connect() as conn:
        row = conn.execute(query, {"order_id": order_id}).mappings().first()
    if row is None:
        return None

    delivered = row["order_delivered_customer_date"]
    estimated = row["order_estimated_delivery_date"]
    delay_days = None
    severity = None
    is_late = False
    is_at_risk = False

    if delivered is not None:
        diff = (delivered - estimated).days
        if diff > 0:
            is_late = True
            delay_days = diff
            severity = _severity_for_delay(diff)
    # An undelivered order past its estimate is "at risk"; determining
    # that against wall-clock "now" is out of scope here since the Olist
    # dataset is historical (2016-2018) and every undelivered row would
    # trivially read as at-risk against today's date.

    return RiskAssessment(
        order_id=row["order_id"],
        order_status=row["order_status"],
        is_late=is_late,
        is_at_risk=is_at_risk,
        delay_days=delay_days,
        severity=severity,
    )


def calculate_compensation(order_id: str, policy_version: str = "1.0") -> CompensationProposal | None:
    doc_id = "POL-COMP-001"
    with get_engine().connect() as conn:
        policy_row = conn.execute(text("""
            SELECT status FROM shopops_ops.policy_documents
            WHERE doc_id = :doc_id AND version = :version
        """), {"doc_id": doc_id, "version": policy_version}).mappings().first()

    if policy_row is None or policy_row["status"] != "active":
        return None  # no active policy at this version — nothing to propose against

    risk = estimate_delivery_risk(order_id)
    if risk is None:
        return None  # order_id doesn't exist

    eligibility_query = text("""
        SELECT order_status, order_value FROM shopops_views.vw_compensation_eligibility
        WHERE order_id = :order_id
    """)
    with get_engine().connect() as conn:
        elig_row = conn.execute(eligibility_query, {"order_id": order_id}).mappings().first()
    if elig_row is None:
        return None

    if elig_row["order_status"] != "delivered":
        return CompensationProposal(
            order_id=order_id, eligible=False, reason="Order is not yet delivered.",
            policy_doc_id=doc_id, policy_version=policy_version, severity=None,
            compensation_percentage=None, order_value=None, proposed_amount=None,
        )
    if not risk.is_late:
        return CompensationProposal(
            order_id=order_id, eligible=False, reason="Order was delivered on time.",
            policy_doc_id=doc_id, policy_version=policy_version, severity=None,
            compensation_percentage=None, order_value=None, proposed_amount=None,
        )

    pct = _COMPENSATION_PCT[risk.severity]
    order_value = elig_row["order_value"] or 0
    proposed_amount = order_value * pct
    cap_applied = False
    if risk.severity == "severe" and proposed_amount > _SEVERE_CAP:
        proposed_amount = _SEVERE_CAP
        cap_applied = True

    return CompensationProposal(
        order_id=order_id, eligible=True,
        reason=f"Order delivered {risk.delay_days} day(s) late ({risk.severity} delay).",
        policy_doc_id=doc_id, policy_version=policy_version, severity=risk.severity,
        compensation_percentage=pct, order_value=order_value,
        proposed_amount=proposed_amount, cap_applied=cap_applied,
    )
