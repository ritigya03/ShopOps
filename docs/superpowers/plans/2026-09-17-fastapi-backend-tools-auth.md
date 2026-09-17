# FastAPI Backend – Tools, Cognito Auth, Guardrails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI backend exposing five read/calculate tools (`get_order`, `get_seller_metrics`, `search_policy`, `estimate_delivery_risk`, `calculate_compensation`) behind real AWS Cognito JWT auth and RBAC/evidence guardrails, with every request appended to the audit log.

**Architecture:** Tools are plain, independently-testable Python functions that read only from `shopops_views` (Postgres) and the `shopops_policy` Qdrant collection — never raw `shopops_data` tables, per the design doc's least-privilege rule. FastAPI routes wrap each tool with a Cognito JWT auth dependency and an RBAC guardrail dependency, and log an audit event on every call. The LangGraph orchestrator (LLM-driven routing/synthesis) is explicitly **out of scope** for this plan — it depends on an LLM provider choice the user deferred — so routes call tools directly for now. This is a superset of MVP §13 minus the LLM-driven parts.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy (already in the project), PyJWT for Cognito token verification, boto3 for Cognito test-token retrieval, qdrant-client (already in the project), pytest + httpx for testing.

**Spec:** `docs/ShopOps_AI_Technical_Design_Document.pdf` — sections referenced below are copied verbatim so executors don't need to re-open the PDF.

## Global Constraints

- Tools never write raw SQL strings interpolated with user input — always parameterized queries against `shopops_views.*`, never `shopops_data.*` directly (§3.1, §5).
- `calculate_compensation` produces a **proposal only, no database mutation** — it must not insert into `action_requests` (§5: "Proposal only; no mutation; includes cited rule and amount basis"). Building the actual approval/write workflow is a separate future plan.
- Backend authorization is deny-by-default: every route validates the Cognito JWT's issuer, audience, signature, and expiry before running any tool (§3.2).
- Every tool call appends one row to `shopops_ops.audit_events` — INSERT only, the existing trigger already blocks UPDATE/DELETE (§3.3).
- No hardcoded secrets anywhere — Cognito pool IDs are not secret and may live in `.env`/code, but the AWS access key/secret used for test token retrieval must only ever live in `.env` (gitignored).
- Reuse the existing `.venv`, `requirements.txt`, and `.env` conventions already established in this repo — don't introduce a second dependency/config system.
- Tests run against the **local Docker Postgres** (port 5433) and **local Docker Qdrant** (port 6333), never against RDS — `.env`'s `DATABASE_URL` currently points at RDS, so tests use a separate `LOCAL_DATABASE_URL` added in Task 2.

---

## File Structure

```
app/
  __init__.py       empty, marks the package
  config.py         loads/validates env vars (DB, Qdrant, Cognito)
  db.py             SQLAlchemy engine, shared across tools
  schemas.py        Pydantic request/response models (§5 tool contracts)
  tools.py          the 5 tool functions + a TOOL_REGISTRY dict
  auth.py           Cognito JWT verification + get_current_user dependency
  guardrails.py     RBAC dependency + policy-evidence validator
  routes.py         APIRouter wiring auth + guardrails + tools + audit logging
  main.py           FastAPI() app instance, includes the router

tests/
  conftest.py       shared fixtures: local DB engine, Qdrant client, Cognito test tokens
  test_tools.py     tests for get_order, get_seller_metrics, search_policy
  test_calc_tools.py  tests for estimate_delivery_risk, calculate_compensation
  test_auth.py      tests for Cognito JWT verification
  test_guardrails.py  tests for RBAC + evidence validation
  test_routes.py    end-to-end tests via FastAPI TestClient with real tokens

scripts/
  verify_cognito_tokens.py   one-off script for Task 1 to fetch + decode real test tokens
```

---

### Task 1: AWS Cognito User Pool + test users

**Files:**
- Create: `scripts/verify_cognito_tokens.py`
- Modify: `.env` (add `COGNITO_REGION`, `COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, three test-user password vars)
- Modify: `.env.example` (add the same keys with placeholder values, no real secrets)

**Interfaces:**
- Produces: three real Cognito ID tokens (one per role) that Task 6's auth tests and Task 8's route tests consume via a `cognito_tokens` pytest fixture.

This task is manual AWS console work plus one verification script — there's no application code to unit-test yet.

- [ ] **Step 1: Create the User Pool**

AWS Console → search **Cognito** → **User pools** → **Create user pool**.
- Sign-in options: **Email**
- Password policy: default (Cognito's standard requirements) is fine
- MFA: **No MFA** (this is local dev, not production)
- User pool name: `shopops-users`
- Skip Hosted UI branding
- Click **Create user pool**, wait for it to finish, then copy the **User pool ID** (looks like `ap-south-1_XXXXXXXXX`).

- [ ] **Step 2: Create three groups**

In the new user pool → **Groups** tab → **Create group**, three times:
- `Viewer`
- `SupportAgent`
- `OperationsManager`

(These map to the RBAC roles in TDD §3.2. `Admin` is out of scope for this plan.)

- [ ] **Step 3: Create an app client**

**App integration** tab → **App clients** → **Create app client**.
- App type: **Public client**
- App client name: `shopops-local-dev`
- **Uncheck** "Generate a client secret" (simplifies token retrieval for local dev/testing)
- Under "Authentication flows", enable **ALLOW_USER_PASSWORD_AUTH** (needed for the test-token script in Step 6)
- Create it, then copy the **Client ID**.

- [ ] **Step 4: Create one test user per role**

**Users** tab → **Create user**, three times. For each: enter an email as username, set "Mark email as verified", and set a temporary password. Then for each user, click into them → **Group memberships** → add to `Viewer`, `SupportAgent`, or `OperationsManager` respectively (one group per user is enough for this plan).

- [ ] **Step 5: Set a permanent password for each test user**

New Cognito users start in `FORCE_CHANGE_PASSWORD` state, which the simple `USER_PASSWORD_AUTH` flow used below cannot complete on its own. In the console: click into each user → **Actions** → **Reset password** is not enough by itself; instead use **Actions → Set password**, choose **Permanent**, and set the same password you'll put in `.env` for that user (or set a password of your choosing).

- [ ] **Step 6: Create an IAM access key for boto3**

AWS Console → search **IAM** → **Users** → your user (`ritigya_g`) → **Security credentials** tab → **Create access key** → choose **Command Line Interface (CLI)** → acknowledge the warning → **Create access key**. Copy the **Access key** and **Secret access key** immediately (the secret is only shown once).

- [ ] **Step 7: Add everything to `.env`**

```
COGNITO_REGION=ap-south-1
COGNITO_USER_POOL_ID=<paste from Step 1>
COGNITO_APP_CLIENT_ID=<paste from Step 3>
AWS_ACCESS_KEY_ID=<paste from Step 6>
AWS_SECRET_ACCESS_KEY=<paste from Step 6>
COGNITO_TEST_VIEWER_EMAIL=<viewer test user email>
COGNITO_TEST_VIEWER_PASSWORD=<viewer test user password>
COGNITO_TEST_SUPPORT_EMAIL=<support test user email>
COGNITO_TEST_SUPPORT_PASSWORD=<support test user password>
COGNITO_TEST_MANAGER_EMAIL=<manager test user email>
COGNITO_TEST_MANAGER_PASSWORD=<manager test user password>
```

Add the same keys to `.env.example` with placeholder values (`changeme`, `ap-south-1_XXXXXXXXX`, etc.) — never real secrets in the example file.

- [ ] **Step 8: Install boto3 and PyJWT**

```bash
source .venv/bin/activate
pip install boto3 "pyjwt[crypto]"
```

- [ ] **Step 9: Write the verification script**

`scripts/verify_cognito_tokens.py`:

```python
#!/usr/bin/env python3
"""One-off check that Cognito is set up correctly: fetches a real ID
token for each of the three test users and prints its claims. Run this
once after Task 1's console setup, and again any time token retrieval
breaks, to isolate whether the problem is Cognito config or app code.
"""
import os

import boto3
import jwt
from dotenv import load_dotenv

load_dotenv()

ROLE_USERS = [
    ("Viewer", "COGNITO_TEST_VIEWER_EMAIL", "COGNITO_TEST_VIEWER_PASSWORD"),
    ("SupportAgent", "COGNITO_TEST_SUPPORT_EMAIL", "COGNITO_TEST_SUPPORT_PASSWORD"),
    ("OperationsManager", "COGNITO_TEST_MANAGER_EMAIL", "COGNITO_TEST_MANAGER_PASSWORD"),
]


def fetch_id_token(client, app_client_id, email, password):
    resp = client.initiate_auth(
        ClientId=app_client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )
    return resp["AuthenticationResult"]["IdToken"]


def main():
    region = os.environ["COGNITO_REGION"]
    app_client_id = os.environ["COGNITO_APP_CLIENT_ID"]
    client = boto3.client("cognito-idp", region_name=region)

    for role_label, email_var, password_var in ROLE_USERS:
        email = os.environ[email_var]
        password = os.environ[password_var]
        token = fetch_id_token(client, app_client_id, email, password)
        claims = jwt.decode(token, options={"verify_signature": False})
        print(f"{role_label}: groups={claims.get('cognito:groups')} "
              f"email={claims.get('email')} aud={claims.get('aud')}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 10: Run it and confirm**

```bash
python scripts/verify_cognito_tokens.py
```

Expected output: three lines, each showing the correct `cognito:groups` value (`['Viewer']`, `['SupportAgent']`, `['OperationsManager']`) and matching `aud` (the app client ID). If a user is stuck in `FORCE_CHANGE_PASSWORD`, `initiate_auth` raises `NotAuthorizedException` or returns a challenge instead of tokens — go back to Step 5.

- [ ] **Step 11: Commit**

```bash
git add .env.example scripts/verify_cognito_tokens.py
git commit -m "chore: add Cognito test-token verification script"
```

(`.env` itself stays untracked — only `.env.example` is committed.)

---

### Task 2: Project scaffolding

**Files:**
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/db.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`
- Modify: `requirements.txt`
- Modify: `.env` (add `LOCAL_DATABASE_URL`)
- Modify: `.env.example` (add `LOCAL_DATABASE_URL` placeholder)

**Interfaces:**
- Produces: `app.config.settings` (a module-level object with `.local_database_url`, `.qdrant_url`, `.cognito_region`, `.cognito_user_pool_id`, `.cognito_app_client_id`), `app.db.get_engine()` (returns a cached SQLAlchemy `Engine` bound to `LOCAL_DATABASE_URL`).

- [ ] **Step 1: Add dependencies**

Append to `requirements.txt`:

```
fastapi>=0.115
uvicorn[standard]>=0.32
pyjwt[crypto]>=2.9
boto3>=1.35
pytest>=8.3
httpx>=0.27
```

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 2: Register the `integration` pytest marker**

`pytest.ini`:

```ini
[pytest]
markers =
    integration: needs live Postgres/Qdrant/Cognito (excluded from CI in Task 10)
```

Registering it here (before any test uses it) avoids pytest's "unknown marker" warning once Tasks 4, 5, 6, and 8 apply `@pytest.mark.integration` to their DB/Qdrant/Cognito-dependent tests.

- [ ] **Step 3: Add `LOCAL_DATABASE_URL` to `.env` and `.env.example`**

In `.env`, add a line (this always points at the local Docker Postgres regardless of what `DATABASE_URL` is currently pointed at):

```
LOCAL_DATABASE_URL=postgresql+psycopg2://shopops_admin:sILjkmKb7Rgjb4yXZex61yvk@localhost:5433/shopops
```

In `.env.example`, add the placeholder equivalent:

```
LOCAL_DATABASE_URL=postgresql+psycopg2://shopops_admin:changeme@localhost:5433/shopops
```

- [ ] **Step 4: Write the failing test**

`tests/conftest.py`:

```python
import pytest
from sqlalchemy import Engine

from app.config import settings
from app.db import get_engine


@pytest.fixture(scope="session")
def engine() -> Engine:
    return get_engine()
```

`tests/__init__.py`: empty file.

Add this permanent connectivity smoke test to the bottom of `tests/conftest.py` — no later task consumes the `engine` fixture directly (Tasks 4-5's tool functions manage their own engine internally via `get_engine()`), so this is not a throwaway: it stays as the one test that fails fast and clearly if the local Docker Postgres container isn't running, before any tool test gets a chance to fail with a more confusing error. It's marked `integration` since it needs the live container.

```python
@pytest.mark.integration
def test_local_database_is_reachable(engine):
    with engine.connect() as conn:
        assert conn.execute(__import__("sqlalchemy").text("SELECT 1")).scalar() == 1
```

- [ ] **Step 5: Run test to verify it fails**

Run: `pytest tests/conftest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 6: Write minimal implementation**

`app/__init__.py`: empty file.

`app/config.py`:

```python
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings:
    local_database_url: str = os.environ["LOCAL_DATABASE_URL"]
    qdrant_url: str = os.environ.get("QDRANT_URL", "http://localhost:6333")
    cognito_region: str = os.environ["COGNITO_REGION"]
    cognito_user_pool_id: str = os.environ["COGNITO_USER_POOL_ID"]
    cognito_app_client_id: str = os.environ["COGNITO_APP_CLIENT_ID"]


settings = Settings()
```

`app/db.py`:

```python
from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.config import settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(settings.local_database_url)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/conftest.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/__init__.py app/config.py app/db.py tests/__init__.py tests/conftest.py \
        pytest.ini requirements.txt .env.example
git commit -m "feat: add app config, DB engine scaffolding, and pytest markers"
```

---

### Task 3: Pydantic schemas

**Files:**
- Create: `app/schemas.py`
- Test: `tests/test_schemas.py`

**Interfaces:**
- Consumes: nothing (pure data models)
- Produces: `OrderTimeline`, `SellerMetrics`, `PolicyEvidence`, `RiskAssessment`, `CompensationProposal` — the exact types Tasks 4–5 return and Task 8's routes serialize.

- [ ] **Step 1: Write the failing test**

`tests/test_schemas.py`:

```python
from decimal import Decimal

from app.schemas import PolicyEvidence


def test_policy_evidence_requires_score_between_0_and_1():
    evidence = PolicyEvidence(
        doc_id="POL-COMP-001", version="1.0", section="3. Compensation tiers",
        excerpt="...", score=0.53,
    )
    assert evidence.score == 0.53
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas'`

- [ ] **Step 3: Write minimal implementation**

`app/schemas.py`:

```python
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class OrderTimeline(BaseModel):
    order_id: str
    order_status: str
    purchase_timestamp: datetime
    estimated_delivery_date: datetime
    delivered_customer_date: Optional[datetime]
    order_value: Decimal
    seller_count: int


class SellerMetrics(BaseModel):
    seller_id: str
    order_count: int
    late_delivery_rate: float
    avg_review_score: Optional[float]


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
    delay_days: Optional[int]
    severity: Optional[str]  # "minor" | "moderate" | "severe" | None
    signal_availability: str = "unavailable"  # no external shipping/weather signal wired up yet


class CompensationProposal(BaseModel):
    order_id: str
    eligible: bool
    reason: str
    policy_doc_id: str
    policy_version: str
    severity: Optional[str]
    compensation_percentage: Optional[float]
    order_value: Optional[Decimal]
    proposed_amount: Optional[Decimal]
    cap_applied: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas.py tests/test_schemas.py
git commit -m "feat: add Pydantic schemas for tool contracts"
```

---

### Task 4: Read tools — `get_order`, `get_seller_metrics`, `search_policy`

**Files:**
- Create: `app/tools.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Consumes: `app.db.get_engine()` (Task 2), `OrderTimeline`/`SellerMetrics`/`PolicyEvidence` (Task 3), `app.config.settings.qdrant_url` (Task 2)
- Produces: `get_order(order_id: str) -> Optional[OrderTimeline]`, `get_seller_metrics(seller_id: str) -> Optional[SellerMetrics]`, `search_policy(query: str, domain: Optional[str] = None, top_k: int = 5) -> list[PolicyEvidence]` — Task 5 adds two more functions to this same file, Task 8's routes call all five.

- [ ] **Step 1: Write the failing tests**

`tests/test_tools.py` (use a real order/seller ID from the ingested Olist data). All tests here need the live local Postgres + Qdrant containers, so the whole file is marked `integration`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.tools'`

- [ ] **Step 3: Write minimal implementation**

`app/tools.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tools.py -v`
Expected: PASS (requires `docker compose up -d postgres qdrant` running locally with data already ingested, per the existing README)

- [ ] **Step 5: Commit**

```bash
git add app/tools.py tests/test_tools.py
git commit -m "feat: add get_order, get_seller_metrics, search_policy tools"
```

---

### Task 5: Calculation tools — `estimate_delivery_risk`, `calculate_compensation`

**Files:**
- Modify: `app/tools.py` (append two functions)
- Test: `tests/test_calc_tools.py`

**Interfaces:**
- Consumes: `get_engine()` (Task 2), `RiskAssessment`/`CompensationProposal` (Task 3)
- Produces: `estimate_delivery_risk(order_id: str) -> Optional[RiskAssessment]`, `calculate_compensation(order_id: str, policy_version: str = "1.0") -> Optional[CompensationProposal]` — Task 8's routes call both.

Delay severity bands (POL-DELIVERY-001 §4): 1-3 days late = minor, 4-7 = moderate, >7 = severe.
Compensation tiers (POL-COMP-001 §3): minor = 10%, moderate = 25%, severe = 50% capped at 150.

- [ ] **Step 1: Write the failing tests**

`tests/test_calc_tools.py` (pick a real late-delivered order and a real on-time order from the data — run a quick query against `shopops_data.orders` locally to find one of each if these specific IDs don't fit). Needs the live local Postgres container, so marked `integration`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_calc_tools.py -v`
Expected: FAIL with `ImportError: cannot import name 'calculate_compensation'`

- [ ] **Step 3: Write minimal implementation**

Append to `app/tools.py`:

```python
from app.schemas import CompensationProposal, RiskAssessment

_SEVERITY_BANDS = [(3, "minor"), (7, "moderate")]  # >3 and <=7 -> moderate; >7 -> severe
_COMPENSATION_PCT = {"minor": 0.10, "moderate": 0.25, "severe": 0.50}
_SEVERE_CAP = 150


def _severity_for_delay(delay_days: int) -> str:
    for threshold, label in _SEVERITY_BANDS:
        if delay_days <= threshold:
            return label
    return "severe"


def estimate_delivery_risk(order_id: str) -> Optional[RiskAssessment]:
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


def calculate_compensation(order_id: str, policy_version: str = "1.0") -> Optional[CompensationProposal]:
    doc_id = "POL-COMP-001"
    with get_engine().connect() as conn:
        policy_row = conn.execute(text("""
            SELECT status FROM shopops_ops.policy_documents
            WHERE doc_id = :doc_id AND version = :version
        """), {"doc_id": doc_id, "version": policy_version}).mappings().first()

    if policy_row is None or policy_row["status"] != "active":
        return None  # unknown order_id is also routed here below; distinguished next

    risk = estimate_delivery_risk(order_id)
    if risk is None:
        return None

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_calc_tools.py -v`
Expected: PASS. If the sample order ID doesn't match "on-time" in your actual data, query `SELECT order_id FROM shopops_data.orders WHERE order_delivered_customer_date <= order_estimated_delivery_date LIMIT 1;` against the local DB to find a real one and swap it in.

- [ ] **Step 5: Commit**

```bash
git add app/tools.py tests/test_calc_tools.py
git commit -m "feat: add estimate_delivery_risk and calculate_compensation tools"
```

---

### Task 6: Cognito JWT auth

**Files:**
- Create: `app/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `app.config.settings` (Task 2), real tokens from Task 1's test users
- Produces: `CurrentUser` (Pydantic model: `sub: str`, `email: str`, `role: str`), `decode_cognito_token(token: str) -> CurrentUser` (raises `jwt.InvalidTokenError` on failure), `get_current_user` (FastAPI dependency reading the `Authorization: Bearer <token>` header) — Task 7's `require_permission` depends on `get_current_user` directly, and Task 8's routes depend on it transitively through `require_permission`.

- [ ] **Step 1: Write the failing test**

`tests/conftest.py` — append a fixture that fetches real tokens once per test session:

```python
import boto3


@pytest.fixture(scope="session")
def cognito_tokens():
    import os
    client = boto3.client("cognito-idp", region_name=os.environ["COGNITO_REGION"])
    app_client_id = os.environ["COGNITO_APP_CLIENT_ID"]

    def _fetch(email_var, password_var):
        resp = client.initiate_auth(
            ClientId=app_client_id, AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": os.environ[email_var], "PASSWORD": os.environ[password_var]},
        )
        return resp["AuthenticationResult"]["IdToken"]

    return {
        "Viewer": _fetch("COGNITO_TEST_VIEWER_EMAIL", "COGNITO_TEST_VIEWER_PASSWORD"),
        "SupportAgent": _fetch("COGNITO_TEST_SUPPORT_EMAIL", "COGNITO_TEST_SUPPORT_PASSWORD"),
        "OperationsManager": _fetch("COGNITO_TEST_MANAGER_EMAIL", "COGNITO_TEST_MANAGER_PASSWORD"),
    }
```

`tests/test_auth.py` (needs live Cognito for token retrieval and JWKS fetch, so marked `integration`):

```python
import pytest

from app.auth import decode_cognito_token

pytestmark = pytest.mark.integration


def test_decode_valid_viewer_token(cognito_tokens):
    user = decode_cognito_token(cognito_tokens["Viewer"])
    assert user.role == "Viewer"
    assert user.email


def test_decode_rejects_garbage_token():
    with pytest.raises(Exception):
        decode_cognito_token("not-a-real-token")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 3: Write minimal implementation**

`app/auth.py`:

```python
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient
from pydantic import BaseModel

from app.config import settings

_ROLE_PRIORITY = ["OperationsManager", "SupportAgent", "Viewer"]


class CurrentUser(BaseModel):
    sub: str
    email: str
    role: str


@lru_cache
def _jwks_client() -> PyJWKClient:
    issuer = f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}"
    return PyJWKClient(f"{issuer}/.well-known/jwks.json")


def _primary_role(groups: list[str]) -> str:
    for role in _ROLE_PRIORITY:
        if role in groups:
            return role
    raise jwt.InvalidTokenError("token has no recognized cognito:groups role")


def decode_cognito_token(token: str) -> CurrentUser:
    issuer = f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}"
    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token, signing_key.key, algorithms=["RS256"],
        audience=settings.cognito_app_client_id, issuer=issuer,
    )
    role = _primary_role(claims.get("cognito:groups", []))
    return CurrentUser(sub=claims["sub"], email=claims.get("email", ""), role=role)


def get_current_user(authorization: str = Header(...)) -> CurrentUser:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        return decode_cognito_token(token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
```

`PyJWKClient` fetches the JWKS itself internally (via `urllib`, bundled with `pyjwt`) — no extra HTTP dependency needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/auth.py tests/test_auth.py tests/conftest.py requirements.txt
git commit -m "feat: add Cognito JWT verification"
```

---

### Task 7: Guardrails — fine-grained permission matrix and evidence validation

**Files:**
- Create: `app/guardrails.py`
- Test: `tests/test_guardrails.py`

**Interfaces:**
- Consumes: `CurrentUser` (Task 6), `PolicyEvidence` (Task 3)
- Produces: `require_permission(permission: str)` (returns a FastAPI dependency that 403s if `CurrentUser.role` doesn't hold `permission`), `assert_evidence_present(evidence: list[PolicyEvidence], min_score: float = 0.3) -> list[PolicyEvidence]` (raises `InsufficientEvidenceError` if empty or all below `min_score`) — Task 8's routes use both.

Per TDD §3.2 RBAC table (Viewer: order/status/policy; Support Agent: + proposal creation; Operations Manager: + seller/delivery metrics), expressed as an explicit permission matrix rather than inline role lists — each route checks a named capability, not a role name directly, so adding a role or a tool later never means hunting through route code:

| Permission | Viewer | SupportAgent | OperationsManager | Used by |
|---|---|---|---|---|
| `can_view_order` | ✅ | ✅ | ✅ | `get_order` |
| `can_search_policy` | ✅ | ✅ | ✅ | `search_policy` |
| `can_view_delivery_risk` | ❌ | ✅ | ✅ | `estimate_delivery_risk` |
| `can_propose_compensation` | ❌ | ✅ | ✅ | `calculate_compensation` |
| `can_view_seller_metrics` | ❌ | ❌ | ✅ | `get_seller_metrics` |

- [ ] **Step 1: Write the failing test**

`tests/test_guardrails.py`:

```python
import pytest
from fastapi import HTTPException

from app.auth import CurrentUser
from app.guardrails import InsufficientEvidenceError, assert_evidence_present, require_permission
from app.schemas import PolicyEvidence


def test_require_permission_allows_role_that_has_it():
    dependency = require_permission("can_view_seller_metrics")
    user = CurrentUser(sub="1", email="a@b.com", role="OperationsManager")
    assert dependency(current_user=user) == user


def test_require_permission_rejects_role_without_it():
    dependency = require_permission("can_view_seller_metrics")
    user = CurrentUser(sub="1", email="a@b.com", role="Viewer")
    with pytest.raises(HTTPException) as exc_info:
        dependency(current_user=user)
    assert exc_info.value.status_code == 403


def test_support_agent_can_propose_compensation_but_not_view_seller_metrics():
    user = CurrentUser(sub="1", email="a@b.com", role="SupportAgent")
    assert require_permission("can_propose_compensation")(current_user=user) == user
    with pytest.raises(HTTPException):
        require_permission("can_view_seller_metrics")(current_user=user)


def test_assert_evidence_present_raises_when_empty():
    with pytest.raises(InsufficientEvidenceError):
        assert_evidence_present([])


def test_assert_evidence_present_raises_when_all_low_score():
    low = [PolicyEvidence(doc_id="X", version="1.0", section="s", excerpt="e", score=0.1)]
    with pytest.raises(InsufficientEvidenceError):
        assert_evidence_present(low, min_score=0.3)
```

(These are pure in-memory tests, no DB/network — do not mark them `@pytest.mark.integration`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_guardrails.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.guardrails'`

- [ ] **Step 3: Write minimal implementation**

`app/guardrails.py`:

```python
from fastapi import Depends, HTTPException

from app.auth import CurrentUser, get_current_user
from app.schemas import PolicyEvidence

PERMISSIONS: dict[str, set[str]] = {
    "Viewer": {"can_view_order", "can_search_policy"},
    "SupportAgent": {
        "can_view_order", "can_search_policy",
        "can_view_delivery_risk", "can_propose_compensation",
    },
    "OperationsManager": {
        "can_view_order", "can_search_policy", "can_view_delivery_risk",
        "can_propose_compensation", "can_view_seller_metrics",
    },
}


class InsufficientEvidenceError(Exception):
    pass


def require_permission(permission: str):
    def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if permission not in PERMISSIONS.get(current_user.role, set()):
            raise HTTPException(
                status_code=403,
                detail=f"Role '{current_user.role}' lacks permission '{permission}'",
            )
        return current_user
    return dependency


def assert_evidence_present(evidence: list[PolicyEvidence], min_score: float = 0.3) -> list[PolicyEvidence]:
    strong = [e for e in evidence if e.score >= min_score]
    if not strong:
        raise InsufficientEvidenceError("No policy passage met the minimum relevance score")
    return strong
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_guardrails.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/guardrails.py tests/test_guardrails.py
git commit -m "feat: add fine-grained permission matrix and evidence guardrail"
```

---

### Task 8: FastAPI routes + audit logging

**Files:**
- Create: `app/routes.py`
- Create: `app/main.py`
- Test: `tests/test_routes.py`

**Interfaces:**
- Consumes: everything from Tasks 2–7
- Produces: a running FastAPI app (`app.main.app`) with routes `GET /orders/{order_id}`, `GET /sellers/{seller_id}/metrics`, `GET /policy/search?query=...`, `GET /orders/{order_id}/risk`, `GET /orders/{order_id}/compensation`

- [ ] **Step 1: Write the failing tests**

`tests/test_routes.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

pytestmark = pytest.mark.integration


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_get_order_accessible_to_viewer(cognito_tokens):
    resp = client.get("/orders/00010242fe8c5a6d1ba2dd792cb16214", headers=_auth(cognito_tokens["Viewer"]))
    assert resp.status_code == 200
    assert resp.json()["order_status"] == "delivered"


def test_get_order_without_token_is_rejected():
    resp = client.get("/orders/00010242fe8c5a6d1ba2dd792cb16214")
    assert resp.status_code in (401, 422)


def test_seller_metrics_forbidden_for_viewer(cognito_tokens):
    resp = client.get(
        "/sellers/48436dade18ac8b2bce089ec2a041202/metrics",
        headers=_auth(cognito_tokens["Viewer"]),
    )
    assert resp.status_code == 403


def test_seller_metrics_allowed_for_manager(cognito_tokens):
    resp = client.get(
        "/sellers/48436dade18ac8b2bce089ec2a041202/metrics",
        headers=_auth(cognito_tokens["OperationsManager"]),
    )
    assert resp.status_code == 200


def test_policy_search_returns_citations(cognito_tokens):
    resp = client.get(
        "/policy/search", params={"query": "late delivery compensation"},
        headers=_auth(cognito_tokens["Viewer"]),
    )
    assert resp.status_code == 200
    assert len(resp.json()) > 0
    assert "doc_id" in resp.json()[0]
```

(`pytestmark = pytest.mark.integration` marks every test in this file — they all need the live FastAPI app talking to real Postgres/Qdrant/Cognito. Task 10's CI workflow excludes this marker.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Write minimal implementation**

`app/routes.py`:

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.auth import CurrentUser
from app.db import get_engine
from app.guardrails import InsufficientEvidenceError, assert_evidence_present, require_permission
from app.schemas import CompensationProposal, OrderTimeline, PolicyEvidence, RiskAssessment, SellerMetrics
from app.tools import calculate_compensation, estimate_delivery_risk, get_order, get_seller_metrics, search_policy

router = APIRouter()


def _log_audit(user: CurrentUser, tool_name: str, outcome: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO shopops_ops.audit_events
                (event_id, occurred_at, request_id, user_id, role_snapshot, tool_name, outcome)
            VALUES (:event_id, :occurred_at, :request_id, :user_id, :role, :tool_name, :outcome)
        """), {
            "event_id": str(uuid.uuid4()), "occurred_at": datetime.now(timezone.utc),
            "request_id": str(uuid.uuid4()), "user_id": user.sub, "role": user.role,
            "tool_name": tool_name, "outcome": outcome,
        })


@router.get("/orders/{order_id}", response_model=OrderTimeline)
def read_order(
    order_id: str,
    current_user: CurrentUser = Depends(require_permission("can_view_order")),
):
    result = get_order(order_id)
    _log_audit(current_user, "get_order", "success" if result else "not_found")
    if result is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@router.get("/sellers/{seller_id}/metrics", response_model=SellerMetrics)
def read_seller_metrics(
    seller_id: str,
    current_user: CurrentUser = Depends(require_permission("can_view_seller_metrics")),
):
    result = get_seller_metrics(seller_id)
    _log_audit(current_user, "get_seller_metrics", "success" if result else "not_found")
    if result is None:
        raise HTTPException(status_code=404, detail="Seller not found")
    return result


@router.get("/policy/search", response_model=list[PolicyEvidence])
def read_policy_search(
    query: str,
    domain: str | None = None,
    current_user: CurrentUser = Depends(require_permission("can_search_policy")),
):
    results = search_policy(query, domain=domain)
    try:
        results = assert_evidence_present(results)
        _log_audit(current_user, "search_policy", "success")
    except InsufficientEvidenceError:
        _log_audit(current_user, "search_policy", "insufficient_evidence")
        raise HTTPException(status_code=404, detail="No sufficiently relevant policy passage found")
    return results


@router.get("/orders/{order_id}/risk", response_model=RiskAssessment)
def read_delivery_risk(
    order_id: str,
    current_user: CurrentUser = Depends(require_permission("can_view_delivery_risk")),
):
    result = estimate_delivery_risk(order_id)
    _log_audit(current_user, "estimate_delivery_risk", "success" if result else "not_found")
    if result is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@router.get("/orders/{order_id}/compensation", response_model=CompensationProposal)
def read_compensation_proposal(
    order_id: str,
    current_user: CurrentUser = Depends(require_permission("can_propose_compensation")),
):
    result = calculate_compensation(order_id)
    _log_audit(current_user, "calculate_compensation", "success" if result else "not_found")
    if result is None:
        raise HTTPException(status_code=404, detail="Order or active policy not found")
    return result
```

`get_current_user` is no longer imported directly in this file — every route now goes through `require_permission`, which itself depends on `get_current_user` (see Task 7). This is deliberate: every endpoint states its capability requirement explicitly, so `test_get_order_without_token_is_rejected` still exercises the same auth failure path (`require_permission` fails at the `get_current_user` step before the permission check ever runs).

`app/main.py`:

```python
from fastapi import FastAPI

from app.routes import router

app = FastAPI(title="ShopOps AI Backend")
app.include_router(router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routes.py app/main.py tests/test_routes.py
git commit -m "feat: add FastAPI routes with auth, guardrails, and audit logging"
```

---

### Task 9: Manual end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

```bash
source .venv/bin/activate
pytest -v
```

Expected: all tests from Tasks 2–8 pass.

- [ ] **Step 2: Start the server**

```bash
uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 3: Get a real token and hit each route by hand**

```bash
python scripts/verify_cognito_tokens.py   # copy a token from the output
curl -H "Authorization: Bearer <viewer-token>" http://localhost:8000/orders/00010242fe8c5a6d1ba2dd792cb16214
curl -H "Authorization: Bearer <viewer-token>" http://localhost:8000/sellers/48436dade18ac8b2bce089ec2a041202/metrics   # expect 403
curl -H "Authorization: Bearer <manager-token>" http://localhost:8000/sellers/48436dade18ac8b2bce089ec2a041202/metrics  # expect 200
curl -H "Authorization: Bearer <viewer-token>" "http://localhost:8000/policy/search?query=late+delivery+compensation"
```

- [ ] **Step 4: Confirm audit events were written**

```bash
LOCAL_PG_PASSWORD=$(python3 -c "
import os
from urllib.parse import urlparse
from dotenv import load_dotenv
load_dotenv()
print(urlparse(os.environ['LOCAL_DATABASE_URL'].replace('+psycopg2', '')).password)
")
docker exec -e PGPASSWORD="$LOCAL_PG_PASSWORD" shopops_postgres \
  psql -U shopops_admin -d shopops -c "SELECT tool_name, outcome, role_snapshot, occurred_at FROM shopops_ops.audit_events ORDER BY occurred_at DESC LIMIT 10;"
```

Expected: one row per request made in Step 3, with the correct `tool_name`/`outcome`/`role_snapshot`.

---

### Task 10: CI — lint and unit tests on GitHub Actions

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `requirements.txt` (add `ruff`)

**Interfaces:**
- Consumes: the `integration` pytest marker (Task 2) to know which tests to skip — CI has no Postgres/Qdrant/Cognito available, so it runs only the fast, dependency-free tests (`test_schemas.py`, `test_guardrails.py`).

This is a "checkbox" CI setup, not full environment provisioning: spinning up seeded Postgres + Qdrant + real Cognito test users inside a GitHub Actions runner is real infrastructure work with its own failure modes, disproportionate to what a lint+unit gate needs to prove. Integration tests keep running locally (Task 9) and are excluded here by design, not by oversight.

- [ ] **Step 1: Add `ruff` and confirm the codebase lints clean**

Append to `requirements.txt`:

```
ruff>=0.7
```

```bash
source .venv/bin/activate
pip install -r requirements.txt
ruff check .
```

Fix anything it flags in `app/` or `tests/` before proceeding — a first CI run that immediately fails on pre-existing lint debt defeats the point of adding it.

- [ ] **Step 2: Confirm the unit-only test subset passes locally**

```bash
pytest -m "not integration" -v
```

Expected: PASS — only `tests/test_schemas.py` and `tests/test_guardrails.py` should run (both have zero external dependencies); everything else is skipped by the marker filter.

- [ ] **Step 3: Write the workflow**

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Lint
        run: ruff check .
      - name: Run unit tests (integration tests need local Postgres/Qdrant/Cognito — excluded here, see Task 9)
        run: pytest -m "not integration" -v
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml requirements.txt
git commit -m "chore: add CI workflow for lint and unit tests"
```

Pushing this to GitHub to see the workflow actually trigger is optional and up to you — Steps 1-2's local dry run already prove the commands the workflow runs are correct.

---

## Explicitly out of scope for this plan

- **LangGraph orchestrator / LLM-driven routing and synthesis** — blocked on the deferred LLM provider decision. A follow-up plan once that's chosen.
- **The write path** (`create_compensation`/`refund`, `action_requests` approval workflow, signed approval tokens) — `calculate_compensation` here is read-only/proposal-only by design.
- **Audit hash-chaining** (`prev_hash` linking each event to the last) — this plan writes flat audit rows; tamper-evident chaining is a separate hardening task.
- **CloudWatch/Langfuse observability, CI/CD, EC2 deployment** — TDD §9/§11, correctly deferred per §13's MVP-first ordering.
- **Active-version / expiry filtering inside `search_policy` itself** (TDD §7: "retrieval requires an active policy version... conflicting or expired passages trigger abstention"). `calculate_compensation` checks `policy_documents.status` directly, but `search_policy` doesn't cross-check it yet — with only one version of each doc today (all `status='active'`) this can't be exercised. Add the check when a second policy version is introduced.
