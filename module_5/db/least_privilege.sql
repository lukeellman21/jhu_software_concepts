-- Least-privilege database role for the Grad Café analytics app.
--
-- Rationale: the web application only ever reads the applicants table and
-- appends new rows to it. It never creates, alters or drops objects, never
-- deletes or updates rows, and never needs another database's data. Granting
-- exactly those two privileges means a successful SQL injection against the
-- app still cannot drop the table, reach another schema, or escalate.
--
-- Run as an administrator:
--   psql -d gradcafe -v app_password="'<password>'" -f db/least_privilege.sql
-- Then set DB_USER / DB_PASSWORD in .env to match.

-- 1. The role. NOSUPERUSER / NOCREATEDB / NOCREATEROLE are stated explicitly
--    rather than left implied, so the intent is visible in the definition.
DROP ROLE IF EXISTS gradcafe_app;
CREATE ROLE gradcafe_app
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOBYPASSRLS
    PASSWORD :app_password;

-- 2. Connect to this database and resolve names in the public schema, nothing
--    more. USAGE does NOT include CREATE, so the role cannot add or replace
--    objects.
GRANT CONNECT ON DATABASE gradcafe TO gradcafe_app;
GRANT USAGE ON SCHEMA public TO gradcafe_app;
REVOKE CREATE ON SCHEMA public FROM gradcafe_app;

-- 3. Exactly the table privileges the application uses:
--    SELECT -> the analysis page and every reporting query
--    INSERT -> POST /pull-data appending newly scraped rows
--    No UPDATE, DELETE, TRUNCATE, REFERENCES or TRIGGER.
GRANT SELECT, INSERT ON TABLE applicants TO gradcafe_app;

-- 4. Nothing is granted on future objects, so a newly created table stays
--    inaccessible until an administrator deliberately grants access.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM gradcafe_app;

-- 5. Verify: expect rolsuper = false and exactly INSERT + SELECT.
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin
FROM pg_roles WHERE rolname = 'gradcafe_app';

SELECT grantee, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'gradcafe_app' AND table_name = 'applicants'
ORDER BY privilege_type;
