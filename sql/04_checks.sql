-- Section 2.2 step 3  Checks (compare with results/capture_audit.json)
--   psql -d mobile_money -f sql/04_checks.sql
\pset footer off
SHOW timezone;

SELECT 'customers' AS table_name, COUNT(*) AS rows, 228000 AS expected FROM customers
UNION ALL SELECT 'accounts',        COUNT(*), 248000   FROM accounts
UNION ALL SELECT 'devices',         COUNT(*), 228600   FROM devices
UNION ALL SELECT 'account_devices', COUNT(*), 285600   FROM account_devices
UNION ALL SELECT 'transfers',       COUNT(*), 20003300 FROM transfers;

-- Transfer audit totals (must equal capture.py)
SELECT COUNT(*) AS transfer_count,
       MIN(occurred_at) AS earliest, to_timestamp(MIN(occurred_at)) AS earliest_cat,
       MAX(occurred_at) AS latest,   to_timestamp(MAX(occurred_at)) AS latest_cat,
       SUM(amount_rwf::bigint) AS sum_amount_rwf
FROM transfers;

-- Roles: 240,000 person / 6,000 merchant / 2,000 agent
SELECT role, COUNT(*) FROM accounts GROUP BY role ORDER BY role;

-- All constraints and whether they are validated
SELECT conrelid::regclass AS table_name, conname, contype, convalidated
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace
ORDER BY 1, 2;

-- Indexes
SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY 1, 2;

-- Data and index sizes in GB (1 GB = 1,000,000,000 bytes)
SELECT c.relname AS table_name,
       ROUND(pg_table_size(c.oid)   / 1e9, 4) AS data_gb,
       ROUND(pg_indexes_size(c.oid) / 1e9, 4) AS index_gb
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY 1;
SELECT ROUND(pg_database_size(current_database()) / 1e9, 4) AS database_gb;
