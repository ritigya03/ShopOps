# ShopOps

A conversational e-commerce operations agent for order, seller, policy, and
delivery workflows, built on the Olist e-commerce dataset. See
`docs/ShopOps_AI_Technical_Design_Document.pdf` for the full architecture.

This repo currently implements the **local data layer only**: a PostgreSQL
database (via Docker Compose) with the `shopops_data`, `shopops_views`, and
`shopops_ops` schemas, plus a script to ingest the Olist CSVs. Cloud
infrastructure (AWS RDS, Qdrant, etc.) is not used yet — everything here runs
locally.

## Project layout

```
data/raw/            Olist source CSVs (9 files; geolocation not yet ingested)
data/policy/          policy documents (empty for now)
db/migrations/        SQL run automatically on first database startup
scripts/ingest.py     loads the CSVs into shopops_data
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

## Stopping

```bash
docker compose down       # stop, keep data
docker compose down -v    # stop and delete all data
```
