-- Gold for the Path to surgery screen: who to call today, in order.
-- The model writes its scores to a staging table. A function promotes them to gold,
-- so a bad model run never reaches the screen by itself.
CREATE TABLE silver_model_score_raw (
    client_id uuid NOT NULL,
    person_external_id text NOT NULL,
    model_version text NOT NULL,
    score numeric(8, 7) NOT NULL CHECK (score BETWEEN 0 AND 1),
    computed_at timestamptz DEFAULT now(),
    PRIMARY KEY (client_id, person_external_id)
);

CREATE TABLE gold_lead_score (
    client_id uuid NOT NULL,
    person_external_id text NOT NULL,
    place integer NOT NULL,
    call_group integer NOT NULL CHECK (call_group BETWEEN 1 AND 10),
    model_version text NOT NULL,
    PRIMARY KEY (client_id, person_external_id)
);

ALTER TABLE silver_model_score_raw ENABLE ROW LEVEL SECURITY;   -- no policy: no dashboard user reads it
ALTER TABLE gold_lead_score ENABLE ROW LEVEL SECURITY;
CREATE POLICY own_rows ON gold_lead_score FOR SELECT TO authenticated
  USING (client_id = (SELECT current_client()));

-- The screen shows a place and a group, never the score: the score orders people,
-- it is not a probability, and "62% chance of surgery" would be read as one.
CREATE OR REPLACE FUNCTION gold_promote_lead_score(p_client_id uuid)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE n_rows integer;
BEGIN
    -- An empty staging table means the model didn't run. Yesterday's list beats no list.
    IF NOT EXISTS (SELECT 1 FROM silver_model_score_raw WHERE client_id = p_client_id) THEN
        RAISE WARNING 'no scores for this client, keeping the previous list';
        RETURN 0;
    END IF;

    DELETE FROM gold_lead_score WHERE client_id = p_client_id;

    INSERT INTO gold_lead_score (client_id, person_external_id, place, call_group, model_version)
    SELECT client_id, person_external_id, place, least(10, (place - 1) * 10 / total + 1), model_version
    FROM (SELECT *, row_number() OVER (ORDER BY score DESC, person_external_id) AS place,
                 count(*) OVER () AS total
          FROM silver_model_score_raw WHERE client_id = p_client_id) ranked;

    GET DIAGNOSTICS n_rows = ROW_COUNT;
    RETURN n_rows;
END $$;
