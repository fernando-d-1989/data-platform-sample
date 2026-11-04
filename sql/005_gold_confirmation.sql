-- Gold for the Appointment confirmation screen: of the assessments that were due,
-- how many people came, confirmed the day before or not. Booked ones that haven't
-- happened yet are not "due", so they stay out.
CREATE TABLE gold_confirmation_month (
    client_id uuid NOT NULL,
    month date NOT NULL,
    confirmed boolean NOT NULL,
    due integer NOT NULL,
    attended integer NOT NULL,
    PRIMARY KEY (client_id, month, confirmed)
);

ALTER TABLE gold_confirmation_month ENABLE ROW LEVEL SECURITY;
CREATE POLICY own_rows ON gold_confirmation_month FOR SELECT TO authenticated
  USING (client_id = (SELECT current_client()));

CREATE OR REPLACE FUNCTION gold_refresh_confirmation(p_client_id uuid)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE n_rows integer;
BEGIN
    DELETE FROM gold_confirmation_month WHERE client_id = p_client_id;

    INSERT INTO gold_confirmation_month (client_id, month, confirmed, due, attended)
    SELECT p_client_id, date_trunc('month', date)::date, coalesce(confirmed, false),
           count(*), count(*) FILTER (WHERE status = 'attended')
    FROM silver_operation
    WHERE client_id = p_client_id AND kind = 'assessment' AND status IN ('attended', 'no_show')
    GROUP BY 2, 3;

    GET DIAGNOSTICS n_rows = ROW_COUNT;
    RETURN n_rows;
END $$;
