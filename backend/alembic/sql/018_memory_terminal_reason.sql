ALTER TABLE memory_jobs
    ADD COLUMN terminal_reason varchar(64),
    ADD CONSTRAINT ck_memory_jobs_terminal_reason
    CHECK (
        terminal_reason IS NULL
        OR (state = 'exhausted'
            AND terminal_reason = 'required_result_send_budget_exhausted')
    );

CREATE OR REPLACE FUNCTION saga_memory_terminal_reason_guard()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.terminal_reason IS NOT NULL
       AND (NEW.state <> 'exhausted'
            OR NEW.terminal_reason <> 'required_result_send_budget_exhausted') THEN
        RAISE EXCEPTION 'Memory terminal reason is invalid.' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.state = 'exhausted'
           AND NEW.execution_contract_version = 1
           AND NEW.terminal_reason IS NULL THEN
            RAISE EXCEPTION 'Current memory exhaustion requires a terminal reason.'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        IF OLD.state IN ('succeeded', 'exhausted')
           AND NEW.terminal_reason IS DISTINCT FROM OLD.terminal_reason THEN
            RAISE EXCEPTION 'A definitive memory terminal reason is immutable.'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.state = 'exhausted'
           AND OLD.state <> 'exhausted'
           AND NEW.execution_contract_version = 1
           AND NEW.terminal_reason IS NULL THEN
            RAISE EXCEPTION 'Current memory exhaustion requires a terminal reason.'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_memory_jobs_terminal_reason
BEFORE INSERT OR UPDATE OF state, terminal_reason, execution_contract_version
ON memory_jobs
FOR EACH ROW EXECUTE FUNCTION saga_memory_terminal_reason_guard();
