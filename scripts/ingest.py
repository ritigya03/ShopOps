#!/usr/bin/env python3
"""Load the Olist CSVs in data/raw into the shopops_data schema.

Loads in FK-safe order (parents before children) and skips the
~1M-row geolocation file for now. Safe to re-run: truncates target
tables first, so repeated runs don't duplicate rows.
"""
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
SCHEMA = "shopops_data"

# (csv filename, table name, parse_dates, dedupe subset)
LOAD_ORDER = [
    ("product_category_name_translation.csv", "product_category_name_translation", None, None),
    ("olist_customers_dataset.csv", "customers", None, None),
    ("olist_sellers_dataset.csv", "sellers", None, None),
    ("olist_products_dataset.csv", "products", None, None),
    ("olist_orders_dataset.csv", "orders",
     ["order_purchase_timestamp", "order_approved_at",
      "order_delivered_carrier_date", "order_delivered_customer_date",
      "order_estimated_delivery_date"], None),
    ("olist_order_items_dataset.csv", "order_items", ["shipping_limit_date"], None),
    ("olist_order_payments_dataset.csv", "order_payments", None, None),
    ("olist_order_reviews_dataset.csv", "order_reviews",
     ["review_creation_date", "review_answer_timestamp"],
     ["review_id", "order_id"]),
]

# Created by the migrations but intentionally not loaded yet.
SKIPPED = ["olist_geolocation_dataset.csv (geolocation, ~1M rows)"]


def get_engine():
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL not set. Copy .env.example to .env and fill it in.")
    return create_engine(database_url)


def reset_tables(engine):
    tables = ", ".join(f"{SCHEMA}.{name}" for _, name, _, _ in LOAD_ORDER)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    print(f"Truncated {len(LOAD_ORDER)} tables in {SCHEMA}.")


def load_csv(engine, filename, table, parse_dates, dedupe_subset):
    csv_path = RAW_DIR / filename
    df = pd.read_csv(csv_path, parse_dates=parse_dates)
    if dedupe_subset:
        before = len(df)
        df = df.drop_duplicates(subset=dedupe_subset)
        if len(df) != before:
            print(f"  dropped {before - len(df)} duplicate rows on {dedupe_subset}")
    df.to_sql(table, engine, schema=SCHEMA, if_exists="append",
               index=False, method="multi", chunksize=5000)
    print(f"  loaded {len(df):,} rows into {SCHEMA}.{table}")


def main():
    engine = get_engine()
    print(f"Connected. Loading Olist CSVs from {RAW_DIR}")
    reset_tables(engine)
    for filename, table, parse_dates, dedupe_subset in LOAD_ORDER:
        print(f"Loading {filename} -> {SCHEMA}.{table}")
        load_csv(engine, filename, table, parse_dates, dedupe_subset)
    print("\nSkipped for now:")
    for note in SKIPPED:
        print(f"  - {note}")
    print("\nDone.")


if __name__ == "__main__":
    main()
