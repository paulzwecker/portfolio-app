-- Run once using psql as your local PostgreSQL administrator.
-- This script intentionally does not overwrite existing roles or databases.
\set ON_ERROR_STOP on
CREATE ROLE portfolio_app LOGIN;
\password portfolio_app
CREATE DATABASE portfolio_app OWNER portfolio_app;
CREATE DATABASE portfolio_app_test OWNER portfolio_app;
\echo 'Databases created. Set the application password in the root .env file.'

