#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  --set=metadata_password="$METADATA_PASSWORD" --set=readonly_password="$READONLY_PASSWORD" <<'SQL'
CREATE ROLE metadata LOGIN PASSWORD :'metadata_password';
CREATE ROLE analyst LOGIN PASSWORD :'readonly_password';
ALTER ROLE analyst SET default_transaction_read_only = on;
CREATE DATABASE metadata OWNER metadata;
CREATE DATABASE business;
REVOKE CONNECT ON DATABASE metadata FROM PUBLIC;
GRANT CONNECT ON DATABASE metadata TO metadata;
REVOKE CONNECT ON DATABASE business FROM PUBLIC;
GRANT CONNECT ON DATABASE business TO analyst;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname business -f /docker-entrypoint-initdb.d/business.sql.seed
