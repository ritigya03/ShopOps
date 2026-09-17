-- Olist-derived tables, loaded in FK-safe order by scripts/ingest.py.
SET search_path TO shopops_data;

CREATE TABLE IF NOT EXISTS product_category_name_translation (
    product_category_name          TEXT PRIMARY KEY,
    product_category_name_english  TEXT
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id                TEXT PRIMARY KEY,
    customer_unique_id         TEXT NOT NULL,
    customer_zip_code_prefix   TEXT,
    customer_city              TEXT,
    customer_state             TEXT
);
CREATE INDEX IF NOT EXISTS idx_customers_unique_id ON customers (customer_unique_id);

CREATE TABLE IF NOT EXISTS sellers (
    seller_id               TEXT PRIMARY KEY,
    seller_zip_code_prefix  TEXT,
    seller_city             TEXT,
    seller_state            TEXT
);

CREATE TABLE IF NOT EXISTS products (
    product_id                     TEXT PRIMARY KEY,
    product_category_name          TEXT,
    product_name_lenght             NUMERIC,
    product_description_lenght      NUMERIC,
    product_photos_qty              NUMERIC,
    product_weight_g                NUMERIC,
    product_length_cm               NUMERIC,
    product_height_cm               NUMERIC,
    product_width_cm                NUMERIC
);

-- Kept intentionally FK-free against product_category_name_translation:
-- the source dataset has category names in `products` that are absent
-- from the translation table, so an FK would break ingestion.
CREATE INDEX IF NOT EXISTS idx_products_category ON products (product_category_name);

CREATE TABLE IF NOT EXISTS orders (
    order_id                        TEXT PRIMARY KEY,
    customer_id                     TEXT NOT NULL REFERENCES customers (customer_id),
    order_status                    TEXT,
    order_purchase_timestamp        TIMESTAMP,
    order_approved_at               TIMESTAMP,
    order_delivered_carrier_date    TIMESTAMP,
    order_delivered_customer_date   TIMESTAMP,
    order_estimated_delivery_date   TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (order_status);

CREATE TABLE IF NOT EXISTS order_items (
    order_id             TEXT NOT NULL REFERENCES orders (order_id),
    order_item_id        INTEGER NOT NULL,
    product_id           TEXT NOT NULL REFERENCES products (product_id),
    seller_id            TEXT NOT NULL REFERENCES sellers (seller_id),
    shipping_limit_date  TIMESTAMP,
    price                NUMERIC(12, 2),
    freight_value        NUMERIC(12, 2),
    PRIMARY KEY (order_id, order_item_id)
);
CREATE INDEX IF NOT EXISTS idx_order_items_seller_id ON order_items (seller_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items (product_id);

CREATE TABLE IF NOT EXISTS order_payments (
    order_id              TEXT NOT NULL REFERENCES orders (order_id),
    payment_sequential    INTEGER NOT NULL,
    payment_type          TEXT,
    payment_installments  INTEGER,
    payment_value         NUMERIC(12, 2),
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE IF NOT EXISTS order_reviews (
    review_id                 TEXT NOT NULL,
    order_id                  TEXT NOT NULL REFERENCES orders (order_id),
    review_score              INTEGER,
    review_comment_title      TEXT,
    review_comment_message    TEXT,
    review_creation_date      TIMESTAMP,
    review_answer_timestamp   TIMESTAMP,
    PRIMARY KEY (review_id, order_id)
);
CREATE INDEX IF NOT EXISTS idx_order_reviews_order_id ON order_reviews (order_id);

-- Schema created for completeness; ingestion skips loading this ~1M-row
-- table for now (see scripts/ingest.py SKIP_TABLES).
CREATE TABLE IF NOT EXISTS geolocation (
    geolocation_zip_code_prefix  TEXT,
    geolocation_lat              NUMERIC,
    geolocation_lng              NUMERIC,
    geolocation_city             TEXT,
    geolocation_state            TEXT
);
CREATE INDEX IF NOT EXISTS idx_geolocation_zip ON geolocation (geolocation_zip_code_prefix);
