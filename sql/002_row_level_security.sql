-- The database decides who sees what, even if the app forgets a filter.
-- The client id is read from the login token, from app_metadata: only the server
-- can write there. user_metadata would not work, because the user can edit it.
CREATE FUNCTION current_client() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT nullif(auth.jwt() -> 'app_metadata' ->> 'client_id', '')::uuid
$$;

ALTER TABLE bronze_raw ENABLE ROW LEVEL SECURITY;        -- no policy: no dashboard user reads raw data
ALTER TABLE silver_person ENABLE ROW LEVEL SECURITY;
ALTER TABLE silver_operation ENABLE ROW LEVEL SECURITY;
ALTER TABLE silver_engagement ENABLE ROW LEVEL SECURITY;

CREATE POLICY own_rows ON silver_person FOR SELECT TO authenticated
  USING (client_id = (SELECT current_client()));
CREATE POLICY own_rows ON silver_operation FOR SELECT TO authenticated
  USING (client_id = (SELECT current_client()));
CREATE POLICY own_rows ON silver_engagement FOR SELECT TO authenticated
  USING (client_id = (SELECT current_client()));

-- Every gold table repeats the same rule in its own file.
-- An account with no client id gets NULL, matches nothing and sees an empty
-- dashboard. It never sees someone else's data.
