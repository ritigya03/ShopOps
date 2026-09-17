-- Core schema separation per ShopOps Technical Design Document (section 6).
CREATE SCHEMA IF NOT EXISTS shopops_data;   -- raw Olist-derived structured records
CREATE SCHEMA IF NOT EXISTS shopops_views;  -- read-only, least-privilege views
CREATE SCHEMA IF NOT EXISTS shopops_ops;    -- policy, approval, and audit control tables
