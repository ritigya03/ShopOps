from typing import Optional

from qdrant_client import QdrantClient, models
from sqlalchemy import text

from app.config import settings
from app.db import get_engine
from app.schemas import OrderTimeline, PolicyEvidence, SellerMetrics

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
POLICY_COLLECTION = "shopops_policy"

_qdrant_client: Optional[QdrantClient] = None


def _get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=settings.qdrant_url)
    return _qdrant_client


def get_order(order_id: str) -> Optional[OrderTimeline]:
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


def get_seller_metrics(seller_id: str) -> Optional[SellerMetrics]:
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


def search_policy(query: str, domain: Optional[str] = None, top_k: int = 5) -> list[PolicyEvidence]:
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
