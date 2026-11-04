-- Gold for the Overview and Conversion screens: the funnel, already counted.
-- One row per month, channel, procedure, city and advisor: a few thousand rows
-- instead of every person and every appointment.
--
-- Counted BY PERIOD, as the clinic's own dashboard does: leads created in the month,
-- assessments attended in it, surgeries done in it. A July surgery usually comes from
-- a May assessment, so "surgeries per 100 assessments" compares two different groups
-- of people. The screens say "per 100", never "conversion".
--
-- The function lives in the database. The loader calls it, and a daily scheduled
-- job (sql/007) also calls it for every client as a safety net.
CREATE TABLE gold_funnel_month (
    client_id uuid NOT NULL,
    month date NOT NULL,
    channel text NOT NULL,
    procedure text NOT NULL,
    city text NOT NULL,
    advisor text NOT NULL,
    leads integer NOT NULL,
    assessments_attended integer NOT NULL,
    no_shows integer NOT NULL,
    surgeries integer NOT NULL,
    revenue numeric(14, 2) NOT NULL,
    PRIMARY KEY (client_id, month, channel, procedure, city, advisor)
);

ALTER TABLE gold_funnel_month ENABLE ROW LEVEL SECURITY;
CREATE POLICY own_rows ON gold_funnel_month FOR SELECT TO authenticated
  USING (client_id = (SELECT current_client()));

CREATE OR REPLACE FUNCTION gold_refresh_funnel(p_client_id uuid)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE n_rows integer;
BEGIN
    -- Only THIS client. Delete and rebuild happen in one transaction, so a reader
    -- sees the old numbers or the new ones, never a half.
    DELETE FROM gold_funnel_month WHERE client_id = p_client_id;

    WITH events AS (
        -- An appointment is counted under the PERSON's channel, procedure and city.
        SELECT p.channel, coalesce(p.procedure, 'unknown') AS procedure, coalesce(p.city, 'unknown') AS city,
               coalesce(p.advisor, 'unknown') AS advisor, date_trunc('month', p.created_on)::date AS month,
               1 AS leads, 0 AS attended, 0 AS no_shows, 0 AS surgeries, 0::numeric AS revenue
        FROM silver_person p
        WHERE p.client_id = p_client_id AND p.created_on IS NOT NULL
        UNION ALL
        SELECT p.channel, coalesce(p.procedure, 'unknown'), coalesce(p.city, 'unknown'),
               coalesce(p.advisor, 'unknown'), date_trunc('month', o.date)::date,
               0, (o.kind = 'assessment' AND o.status = 'attended')::int,
               (o.kind = 'assessment' AND o.status = 'no_show')::int,
               (o.kind = 'surgery' AND o.status = 'done')::int,
               CASE WHEN o.kind = 'surgery' AND o.status = 'done' THEN coalesce(o.value, 0) ELSE 0 END
        FROM silver_operation o
        JOIN silver_person p ON p.client_id = o.client_id AND p.external_id = o.person_external_id
        WHERE o.client_id = p_client_id
    )
    INSERT INTO gold_funnel_month (client_id, month, channel, procedure, city, advisor,
                                   leads, assessments_attended, no_shows, surgeries, revenue)
    SELECT p_client_id, month, channel, procedure, city, advisor,
           sum(leads), sum(attended), sum(no_shows), sum(surgeries), sum(revenue)
    FROM events
    GROUP BY month, channel, procedure, city, advisor;

    GET DIAGNOSTICS n_rows = ROW_COUNT;
    RETURN n_rows;
END $$;
