-- Section 2.2 step 1  Bulk load. Run from the project folder in psql so the
-- relative data/ paths resolve:   psql -d mobile_money -f sql/02_load.sql
-- Parents first: customers and devices, then accounts, account_devices, transfers.
\timing on
SELECT 'LOAD START' AS step, clock_timestamp() AS at_cat;
\copy customers       FROM 'data/customers.csv'       CSV HEADER
\copy devices         FROM 'data/devices.csv'         CSV HEADER
\copy accounts        FROM 'data/accounts.csv'        CSV HEADER
\copy account_devices FROM 'data/account_devices.csv' CSV HEADER
\copy transfers       FROM 'data/transfers.csv'       CSV HEADER
SELECT 'LOAD END' AS step, clock_timestamp() AS at_cat;
