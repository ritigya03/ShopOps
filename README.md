# ShopOps

A conversational e-commerce operations agent for order, seller, policy, and
delivery workflows, built on the Olist e-commerce dataset. See
`docs/ShopOps_AI_Technical_Design_Document.pdf` for the full architecture.

This repo implements the data layer: PostgreSQL with the `shopops_data`,
`shopops_views`, and `shopops_ops` schemas, plus a script to ingest the
Olist CSVs. It can run against either a local Docker Postgres or an AWS RDS
Postgres instance — same schema, same ingestion script, only `.env` differs.
Qdrant and the FastAPI/agent layer from the design doc are not built yet.

## Project layout

```
data/raw/            Olist source CSVs (9 files; geolocation not yet ingested)
data/policy/          policy documents (empty for now)
db/migrations/        SQL run automatically on first database startup
scripts/ingest.py     loads the CSVs into shopops_data
scripts/eval_agent.py LLM eval benchmark — see below
data/eval/cases.yaml  eval benchmark case definitions
docker-compose.yml     local PostgreSQL service
```

## Schemas

- `shopops_data` — raw Olist-derived tables: `product_category_name_translation`,
  `customers`, `sellers`, `products`, `orders`, `order_items`,
  `order_payments`, `order_reviews`, `geolocation` (table exists, not loaded
  yet — see below).
- `shopops_views` — read-only views for agent/tool access: `vw_order_ops`,
  `vw_customer_order_history`, `vw_seller_metrics`, `vw_delivery_risk_inputs`,
  `vw_compensation_eligibility`.
- `shopops_ops` — control-plane tables: `policy_documents`, `action_requests`,
  `audit_events` (append-only; a trigger blocks UPDATE/DELETE).

## Policy documents

`data/policy/*.md` holds the actual policy content (delivery SLA,
compensation/refund eligibility, seller escalation) — the source of truth
for `search_policy` and `calculate_compensation` once the agent layer
exists. Each file has a YAML frontmatter block (`doc_id`, `version`,
`title`, `domain`, `effective_from`, `status`).

```bash
source .venv/bin/activate
python scripts/register_policy_docs.py
```

Syncs each file's metadata + a content checksum into
`shopops_ops.policy_documents` (upsert on `doc_id, version` — safe to
re-run after editing a policy file).

## Qdrant (policy retrieval)

Qdrant runs locally via the same `docker-compose.yml` (REST on `6333`,
gRPC on `6334`). It's the RAG layer behind `search_policy`: policy
documents get chunked section-by-section, embedded, and indexed so a
natural-language query can retrieve the right passage with a citation.

```bash
docker compose up -d qdrant
source .venv/bin/activate
python scripts/ingest_policy_to_qdrant.py
```

This parses each `## heading` in `data/policy/*.md` as one chunk (mirrors
the "section-aware chunks" design in the TDD §7), embeds it locally with
`sentence-transformers/all-MiniLM-L6-v2` via Qdrant's built-in FastEmbed
integration — **no external embedding API key needed** — and writes it to
the `shopops_policy` collection (recreated each run, so it's safe to
re-run after editing a policy doc). Each point's payload carries
`doc_id`, `version`, `section`, `domain`, `status`, `source_uri`, and an
`excerpt`, matching the `PolicyEvidence` shape `search_policy` is meant to
return.

Quick sanity check:

```bash
source .venv/bin/activate
python3 -c "
from qdrant_client import QdrantClient, models
client = QdrantClient(url='http://localhost:6333')
res = client.query_points(
    collection_name='shopops_policy',
    query=models.Document(text='What compensation do I get for a late delivery?',
                           model='sentence-transformers/all-MiniLM-L6-v2'),
    limit=5,
)
for p in res.points:
    print(f\"{p.score:.3f}  {p.payload['doc_id']} v{p.payload['version']} §{p.payload['section']}\")
"
```

## Prerequisites

- Docker Desktop (or compatible) running locally
- Python 3.11+

## Setup

1. Copy the env template and fill in a real local password:

   ```bash
   cp .env.example .env
   ```

   `.env` is gitignored — never commit it. The default host port is `5433`
   (not `5432`) to avoid clashing with other local Postgres containers.

2. Start PostgreSQL. On first start, everything in `db/migrations/` runs
   automatically to create the schemas, tables, views, and constraints:

   ```bash
   docker compose up -d
   docker compose ps          # wait for "healthy"
   ```

3. Create a virtualenv and install ingestion dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Ingest the CSVs from `data/raw` into `shopops_data`:

   ```bash
   python scripts/ingest.py
   ```

   This loads tables in FK-safe order (category translation → customers →
   sellers → products → orders → order_items → order_payments →
   order_reviews) and **skips `olist_geolocation_dataset.csv`** (~1M rows)
   for now — the `geolocation` table is created but left empty. The script
   truncates target tables first, so it's safe to re-run.

## Verifying the data

Row counts (expected values shown):

```bash
docker exec -it shopops_postgres psql -U shopops_admin -d shopops -c "
SELECT 'customers' t, count(*) FROM shopops_data.customers
UNION ALL SELECT 'sellers', count(*) FROM shopops_data.sellers
UNION ALL SELECT 'products', count(*) FROM shopops_data.products
UNION ALL SELECT 'orders', count(*) FROM shopops_data.orders
UNION ALL SELECT 'order_items', count(*) FROM shopops_data.order_items
UNION ALL SELECT 'order_payments', count(*) FROM shopops_data.order_payments
UNION ALL SELECT 'order_reviews', count(*) FROM shopops_data.order_reviews
UNION ALL SELECT 'product_category_name_translation', count(*) FROM shopops_data.product_category_name_translation;
"
```

Expected: customers 99,441 · sellers 3,095 · products 32,951 · orders 99,441 ·
order_items 112,650 · order_payments 103,886 · order_reviews 99,224 ·
product_category_name_translation 71.

Spot-check a view:

```bash
docker exec -it shopops_postgres psql -U shopops_admin -d shopops -c \
  "SELECT * FROM shopops_views.vw_order_ops LIMIT 5;"
```

## Resetting the database

To wipe all data and re-run migrations from scratch (destroys the volume):

```bash
docker compose down -v
docker compose up -d
docker compose ps                 # wait for "healthy"
source .venv/bin/activate
python scripts/ingest.py
```

To just reload the CSVs without touching schema (`ingest.py` truncates
before loading):

```bash
source .venv/bin/activate
python scripts/ingest.py
```

## Stopping (local Docker)

```bash
docker compose down       # stop, keep data
docker compose down -v    # stop and delete all data
```

## AWS RDS (quick local experiment against a public RDS instance)

**For a real production deployment, see `infra/README.md`** — it
provisions a full stack (EC2 + non-publicly-accessible RDS + self-hosted
Qdrant + Cognito + Nginx/SSL + GitHub Actions) and is the authoritative
production runbook. The RDS instance it creates is **never publicly
accessible** and the app reads `LOCAL_DATABASE_URL` for it, per
`app/config.py`.

The steps below are a different, smaller thing: pointing your local dev
checkout's schema/ingestion at a lightweight, temporary, publicly-reachable
RDS instance (e.g. to poke at cloud Postgres without spinning up the full
production stack). It uses `DATABASE_URL`, not `LOCAL_DATABASE_URL` —
don't confuse the two.

1. Create the RDS instance (PostgreSQL, Free Tier `db.t3.micro`), with
   **Public access = Yes** and its security group's inbound rule restricted
   to **My IP** on port 5432 — never `0.0.0.0/0`. Manage the master password
   in AWS Secrets Manager, not by hand.
2. RDS only creates the default `postgres` database — create `shopops`
   yourself once, connected to `postgres`:
   ```sql
   CREATE DATABASE shopops;
   ```
3. Update `.env` with the RDS endpoint, port `5432`, and
   `?sslmode=require` on `DATABASE_URL` (RDS requires SSL). URL-encode the
   password if it contains special characters
   (`python3 -c "from urllib.parse import quote_plus; print(quote_plus('<password>'))"`).
4. Run the migrations and ingestion exactly as before — no `psql` binary is
   required, `db/migrations/*.sql` can be applied with psycopg2 directly:
   ```bash
   source .venv/bin/activate
   python3 -c "
   import psycopg2
   from pathlib import Path
   import os
   from dotenv import load_dotenv
   load_dotenv()
   conn = psycopg2.connect(os.environ['DATABASE_URL'].replace('postgresql+psycopg2', 'postgresql'))
   conn.autocommit = True
   cur = conn.cursor()
   for f in sorted(Path('db/migrations').glob('*.sql')):
       print(f.name); cur.execute(f.read_text())
   "
   python scripts/ingest.py
   ```

The RDS Free Tier instance is billed (~$0.03/hr, or free for 12 months on a
new account) — delete it from the console when you're done experimenting to
avoid ongoing charges. `.env` currently keeps both the RDS values (active)
and the local Docker values (commented out) so you can switch back by
swapping which block is commented.

## Eval benchmark

`scripts/eval_agent.py` runs a fixed set of eval cases
(`data/eval/cases.yaml`) through the real agent graph and scores three
dimensions per case:

- **tool selection** — did the agent call exactly the expected tools?
- **citation** — did the cited evidence include the expected policy
  `doc_id`? (skipped for cases with no `expected_citation_doc_id`)
- **abstention** — did the graph's `abstain` flag match the expectation?

It prints a per-case line plus aggregate accuracies, and writes a timestamped
JSON file to `data/eval/results/` containing every case record and a summary
(including the `agent_model` and git SHA the run used, for comparing runs).
A case that raises is recorded with `status: "error"`, scored as a failure,
and the run continues.

```bash
source .venv/bin/activate
python scripts/eval_agent.py    # from the repo root
```

> **⚠️ This is not a read-only script.** Every case invokes the real agent
> against the configured database, Gemini API key and Qdrant instance:
>
> - it writes **permanent** rows to `shopops_ops.audit_events`, which is
>   append-only (a trigger blocks UPDATE/DELETE) — eval audit rows can never
>   be cleaned up;
> - cases where the agent proposes compensation insert a **real `PROPOSED`
>   row** into `shopops_ops.action_requests`, which appears in the live
>   Approvals dashboard like any human-originated proposal;
> - it spends real Gemini API credits.
>
> Eval-created rows are tagged `requested_by='eval'`, and every created
> `action_id` is printed and stored in the results JSON. To find or reject
> them:
>
> ```sql
> SELECT * FROM shopops_ops.action_requests WHERE requested_by = 'eval';
> ```
