CREATE OR REPLACE FUNCTION saga_memory_generation_retention_guard()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    owner_state text;
    owner_terminal_at timestamptz;
BEGIN
    IF OLD.status IS NOT NULL THEN
        IF to_jsonb(NEW) - ARRAY['updated_at', 'raw_candidate', 'receipt']
           IS DISTINCT FROM
           to_jsonb(OLD) - ARRAY['updated_at', 'raw_candidate', 'receipt'] THEN
            RAISE EXCEPTION 'Recorded memory generation evidence is immutable.'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.raw_candidate IS DISTINCT FROM OLD.raw_candidate
           OR NEW.receipt IS DISTINCT FROM OLD.receipt THEN
            IF NEW.raw_candidate IS NOT NULL
               OR NEW.receipt IS NOT NULL
               OR (OLD.raw_candidate IS NULL AND OLD.receipt IS NULL) THEN
                RAISE EXCEPTION 'Terminal cleanup may only clear persisted generation payloads.'
                    USING ERRCODE = '23514';
            END IF;
            SELECT state, terminal_at INTO owner_state, owner_terminal_at
            FROM memory_jobs
            WHERE id = OLD.job_id AND campaign_id = OLD.campaign_id
              AND policy_id = OLD.policy_id AND batch_id = OLD.batch_id;
            IF NOT FOUND OR owner_state NOT IN ('succeeded', 'exhausted')
               OR owner_terminal_at IS NULL THEN
                RAISE EXCEPTION 'Generation payloads may only be cleared for a definitive terminal job.'
                    USING ERRCODE = '23514';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_memory_generation_retention_guard
BEFORE UPDATE ON memory_generations
FOR EACH ROW EXECUTE FUNCTION saga_memory_generation_retention_guard();
