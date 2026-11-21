DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM memory_jobs WHERE terminal_reason IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Cannot downgrade while structured memory terminal reasons exist.';
    END IF;
END
$$;

DROP TRIGGER trg_memory_jobs_terminal_reason ON memory_jobs;

DROP FUNCTION saga_memory_terminal_reason_guard();

ALTER TABLE memory_jobs
    DROP CONSTRAINT ck_memory_jobs_terminal_reason,
    DROP COLUMN terminal_reason;
