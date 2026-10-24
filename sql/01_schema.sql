-- Section 2.1  Table definitions (run in psql:  \i sql/01_schema.sql)
-- Tables are created with NOT NULL only so the bulk load is fast; keys, foreign
-- keys and CHECK rules are added afterwards by 03_constraints.sql and timed separately.
SET timezone = 'Africa/Kigali';
ALTER DATABASE mobile_money SET timezone = 'Africa/Kigali';

DROP TABLE IF EXISTS transfers, account_devices, accounts, devices, customers CASCADE;

CREATE TABLE customers (
    customer_id  INTEGER NOT NULL,      -- customer identifier
    region       TEXT    NOT NULL       -- Kigali, Northern, Southern, Eastern, Western
);

CREATE TABLE accounts (
    account_id   INTEGER NOT NULL,      -- wallet identifier
    customer_id  INTEGER NOT NULL,      -- owning customer
    role         TEXT    NOT NULL       -- person, merchant or agent
);

CREATE TABLE devices (
    device_id    INTEGER NOT NULL,      -- device identifier
    access_type  TEXT    NOT NULL       -- handset or public_terminal
);

CREATE TABLE account_devices (
    account_id   INTEGER  NOT NULL,     -- wallet observed on the device
    device_id    INTEGER  NOT NULL,     -- device observed
    first_day    SMALLINT NOT NULL,     -- first observation day, 0 = 1 Sep 2026 CAT, inclusive
    last_day     SMALLINT NOT NULL,     -- last observation day, 29 = 30 Sep 2026 CAT, inclusive
    observations INTEGER  NOT NULL      -- number of observations within [first_day, last_day]
);

CREATE TABLE transfers (
    transfer_id  BIGINT  NOT NULL,      -- event identifier
    sender_id    INTEGER NOT NULL,      -- paying wallet
    receiver_id  INTEGER NOT NULL,      -- receiving wallet
    occurred_at  BIGINT  NOT NULL,      -- Unix epoch seconds (UTC instant; CAT = UTC+2)
    amount_rwf   INTEGER NOT NULL       -- whole Rwandan francs
);
