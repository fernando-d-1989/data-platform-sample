-- An AI that chooses its own queries gets its own limited user, never the builder's.
CREATE ROLE demo_agent_ro LOGIN PASSWORD 'set-outside-this-file'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;

ALTER ROLE demo_agent_ro SET default_transaction_read_only = on;
ALTER ROLE demo_agent_ro SET statement_timeout = '30s';

GRANT SELECT ON silver_person, silver_operation, silver_engagement TO demo_agent_ro;

CREATE POLICY agent_one_client ON silver_operation FOR SELECT TO demo_agent_ro
  USING (client_id = '00000000-0000-0000-0000-000000000001');
CREATE POLICY agent_one_client ON silver_person FOR SELECT TO demo_agent_ro
  USING (client_id = '00000000-0000-0000-0000-000000000001');
CREATE POLICY agent_one_client ON silver_engagement FOR SELECT TO demo_agent_ro
  USING (client_id = '00000000-0000-0000-0000-000000000001');

-- Checked by logging in as this role, not by reading this file:
-- other clients' rows = 0, and every write is refused.
