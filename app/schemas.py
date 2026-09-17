from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class OrderTimeline(BaseModel):
    order_id: str
    order_status: str
    purchase_timestamp: datetime
    estimated_delivery_date: datetime
    delivered_customer_date: Optional[datetime] = None
    order_value: Decimal
    seller_count: int


class SellerMetrics(BaseModel):
    seller_id: str
    order_count: int
    late_delivery_rate: float
    avg_review_score: Optional[float] = None


class PolicyEvidence(BaseModel):
    doc_id: str
    version: str
    section: str
    excerpt: str
    score: float = Field(ge=0.0, le=1.0)


class RiskAssessment(BaseModel):
    order_id: str
    order_status: str
    is_late: bool
    is_at_risk: bool
    delay_days: Optional[int] = None
    severity: Optional[str] = None  # "minor" | "moderate" | "severe" | None
    signal_availability: str = "unavailable"  # no external shipping/weather signal wired up yet


class CompensationProposal(BaseModel):
    order_id: str
    eligible: bool
    reason: str
    policy_doc_id: str
    policy_version: str
    severity: Optional[str] = None
    compensation_percentage: Optional[float] = None
    order_value: Optional[Decimal] = None
    proposed_amount: Optional[Decimal] = None
    cap_applied: bool = False
