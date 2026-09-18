from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class OrderTimeline(BaseModel):
    order_id: str
    order_status: str
    purchase_timestamp: datetime
    estimated_delivery_date: datetime
    delivered_customer_date: datetime | None = None
    order_value: Decimal
    seller_count: int


class SellerMetrics(BaseModel):
    seller_id: str
    order_count: int
    late_delivery_rate: float
    avg_review_score: float | None = None


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
    is_at_risk: bool | None = None
    delay_days: int | None = None
    severity: str | None = None  # "minor" | "moderate" | "severe" | None
    signal_availability: str = "unavailable"  # no external shipping/weather signal wired up yet


class CompensationProposal(BaseModel):
    order_id: str
    eligible: bool
    reason: str
    policy_doc_id: str
    policy_version: str
    severity: str | None = None
    compensation_percentage: float | None = None
    order_value: Decimal | None = None
    proposed_amount: Decimal | None = None
    cap_applied: bool = False


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    citations: list[PolicyEvidence] = []
    proposal: CompensationProposal | None = None
    action_id: str | None = None


class ActionReceipt(BaseModel):
    action_id: str
    status: str
    approved_by: str | None
    order_id: str
    proposed_amount: Decimal | None
    occurred_at: datetime
