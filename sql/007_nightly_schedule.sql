-- The database's own alarm clock. This file runs once, and that saves the schedule
-- in pg_cron's table. From then on the database wakes up by itself, with no VM.
--
-- One alarm, every client, several functions: a new client is covered with no edit.
-- 08:20 UTC falls after the VM has finished, as a safety net for the nightly refresh.
-- Skipped where pg_cron isn't installed, such as a plain local Postgres.
DO $outer$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        RAISE NOTICE 'pg_cron not installed, schedule skipped';
        RETURN;
    END IF;

    PERFORM cron.schedule('gold_refresh_daily', '20 8 * * *', $job$
        DO $loop$
        DECLARE v_client uuid;
        BEGIN
            FOR v_client IN SELECT DISTINCT client_id FROM silver_person LOOP
                PERFORM gold_refresh_funnel(v_client);
                PERFORM gold_refresh_confirmation(v_client);
            END LOOP;
        END $loop$;
    $job$);
END $outer$;
