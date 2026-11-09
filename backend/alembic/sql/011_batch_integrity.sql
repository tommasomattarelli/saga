CREATE FUNCTION saga_memory_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'memory_facts' AND to_jsonb(OLD)->>'batch_id' IS NULL THEN
        IF to_jsonb(NEW)->>'batch_id' IS NOT NULL THEN
            RAISE EXCEPTION 'Existing facts cannot be converted into batch facts.' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF to_jsonb(NEW) - 'updated_at' IS DISTINCT FROM to_jsonb(OLD) - 'updated_at' THEN
        RAISE EXCEPTION 'Memory source records are immutable.' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION saga_check_memory_batch() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    batch uuid;
    item memory_batches;
    size integer;
    previous_head uuid;
    first_parent uuid;
    count_members integer;
BEGIN
    batch := CASE WHEN TG_TABLE_NAME = 'memory_batches' THEN to_jsonb(NEW)->>'id' ELSE to_jsonb(NEW)->>'batch_id' END;
    SELECT * INTO item FROM memory_batches WHERE id = batch;
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT (payload->>'batch_turns')::integer INTO size FROM memory_policies WHERE id = item.policy_id;
    SELECT count(*) INTO count_members FROM memory_batch_turns WHERE batch_id = batch;
    IF size IS NULL OR count_members <> size OR EXISTS (
        SELECT 1 FROM memory_batch_turns m WHERE m.batch_id = batch AND m.ordinal NOT BETWEEN 1 AND size
    ) THEN
        RAISE EXCEPTION 'A memory batch must contain exactly the configured number of turns.' USING ERRCODE = '23514';
    END IF;
    SELECT source_head_turn_id INTO previous_head FROM memory_batches WHERE id = item.previous_batch_id;
    SELECT t.parent_turn_id INTO first_parent FROM memory_batch_turns m JOIN turns t ON t.id = m.turn_id
    WHERE m.batch_id = batch AND m.ordinal = 1;
    IF first_parent IS DISTINCT FROM previous_head OR EXISTS (
        SELECT 1 FROM memory_batch_turns m JOIN turns t ON t.id = m.turn_id
        LEFT JOIN memory_batch_turns p ON p.batch_id = m.batch_id AND p.ordinal = m.ordinal - 1
        WHERE m.batch_id = batch AND (t.continuation_id IS NULL OR (m.ordinal > 1 AND t.parent_turn_id IS DISTINCT FROM p.turn_id))
    ) OR NOT EXISTS (
        SELECT 1 FROM memory_batch_turns WHERE batch_id = batch AND ordinal = size AND turn_id = item.source_head_turn_id
    ) THEN
        RAISE EXCEPTION 'Memory batches must partition one contiguous history prefix.' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END
$$;

CREATE CONSTRAINT TRIGGER memory_batch_integrity AFTER INSERT ON memory_batches
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_check_memory_batch();

CREATE CONSTRAINT TRIGGER memory_batch_integrity AFTER INSERT ON memory_batch_turns
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_check_memory_batch();

CREATE TRIGGER memory_immutable BEFORE UPDATE ON memory_batches
FOR EACH ROW EXECUTE FUNCTION saga_memory_immutable();

CREATE TRIGGER memory_immutable BEFORE UPDATE ON memory_batch_turns
FOR EACH ROW EXECUTE FUNCTION saga_memory_immutable();

CREATE CONSTRAINT TRIGGER memory_preserved AFTER DELETE ON memory_batches
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_history_preserved();

CREATE CONSTRAINT TRIGGER memory_preserved AFTER DELETE ON memory_batch_turns
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_history_preserved();
