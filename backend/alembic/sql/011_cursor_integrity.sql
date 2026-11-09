CREATE FUNCTION saga_validate_memory_cursor(campaign uuid, policy uuid, head uuid, checkpoint uuid, last_batch uuid)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    incorporated uuid;
    head_depth integer;
    compacted_depth integer;
    global_depth integer;
    raw_min integer;
    size integer;
    intermediates integer;
BEGIN
    IF checkpoint IS NULL AND last_batch IS NULL THEN RETURN; END IF;
    IF last_batch IS NULL THEN
        RAISE EXCEPTION 'A checkpoint requires compacted coverage.' USING ERRCODE = '23514';
    END IF;
    SELECT batch_id INTO incorporated FROM memory_global_checkpoints WHERE id = checkpoint;
    IF checkpoint IS NOT NULL AND NOT EXISTS (
        WITH RECURSIVE chain AS (
            SELECT id, previous_batch_id FROM memory_batches WHERE id = last_batch
            UNION ALL SELECT b.id, b.previous_batch_id FROM memory_batches b JOIN chain c ON b.id = c.previous_batch_id
        ) SELECT 1 FROM chain WHERE id = incorporated
    ) THEN
        RAISE EXCEPTION 'Coverage cursors must belong to the same batch chain.' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        WITH RECURSIVE chain AS (
            SELECT id, previous_batch_id FROM memory_batches WHERE id = last_batch
            UNION ALL SELECT b.id, b.previous_batch_id FROM memory_batches b JOIN chain c ON b.id = c.previous_batch_id
        ) SELECT 1 FROM chain c WHERE NOT EXISTS (SELECT 1 FROM memory_summaries s WHERE s.batch_id = c.id)
    ) THEN
        RAISE EXCEPTION 'Coverage cannot advance without published summaries.' USING ERRCODE = '23514';
    END IF;
    IF head IS NULL THEN RETURN; END IF;
    IF NOT EXISTS (
        SELECT 1 FROM memory_batches b WHERE b.id = last_batch
        AND saga_history_contains(campaign, head, b.source_head_turn_id)
    ) THEN
        RAISE EXCEPTION 'Coverage must belong to the selected history.' USING ERRCODE = '23514';
    END IF;
    SELECT history_depth INTO head_depth FROM turns WHERE id = head;
    SELECT t.history_depth INTO compacted_depth FROM memory_batches b JOIN turns t ON t.id = b.source_head_turn_id WHERE b.id = last_batch;
    SELECT t.history_depth INTO global_depth FROM memory_batches b JOIN turns t ON t.id = b.source_head_turn_id WHERE b.id = incorporated;
    SELECT (payload->>'raw_turns')::integer, (payload->>'batch_turns')::integer,
           (payload->>'intermediate_limit')::integer INTO raw_min, size, intermediates FROM memory_policies WHERE id = policy;
    IF compacted_depth > greatest(head_depth - raw_min, 0)
        OR coalesce(global_depth, 0) / size > greatest(greatest(head_depth - raw_min, 0) / size - intermediates, 0) THEN
        RAISE EXCEPTION 'Coverage cannot compact protected raw or intermediate detail.' USING ERRCODE = '23514';
    END IF;
END
$$;

CREATE FUNCTION saga_check_memory_cursor() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    state memory_states;
    campaign campaigns;
    save saves;
BEGIN
    IF TG_TABLE_NAME = 'memory_states' THEN
        SELECT * INTO state FROM memory_states WHERE id = NEW.id;
        IF NOT FOUND THEN RETURN NULL; END IF;
        PERFORM saga_validate_memory_cursor(state.campaign_id, state.policy_id, NULL, state.global_checkpoint_id, state.last_compacted_batch_id);
        SELECT * INTO campaign FROM campaigns WHERE active_memory_state_id = state.id;
        IF FOUND THEN
            IF campaign.context_epoch <> state.context_epoch THEN
                RAISE EXCEPTION 'The memory state belongs to a different context epoch.' USING ERRCODE = '23514';
            END IF;
            IF campaign.active_head_turn_id IS NULL AND state.last_compacted_batch_id IS NOT NULL THEN
                RAISE EXCEPTION 'An empty history cannot have compacted coverage.' USING ERRCODE = '23514';
            END IF;
            PERFORM saga_validate_memory_cursor(campaign.id, state.policy_id, campaign.active_head_turn_id, state.global_checkpoint_id, state.last_compacted_batch_id);
        END IF;
    ELSIF TG_TABLE_NAME = 'campaigns' THEN
        SELECT * INTO campaign FROM campaigns WHERE id = NEW.id;
        SELECT * INTO state FROM memory_states WHERE id = campaign.active_memory_state_id;
        IF FOUND THEN
            IF campaign.context_epoch <> state.context_epoch OR (campaign.active_head_turn_id IS NULL AND state.last_compacted_batch_id IS NOT NULL) THEN
                RAISE EXCEPTION 'The active memory context is incompatible with the history.' USING ERRCODE = '23514';
            END IF;
            PERFORM saga_validate_memory_cursor(campaign.id, state.policy_id, campaign.active_head_turn_id, state.global_checkpoint_id, state.last_compacted_batch_id);
        END IF;
    ELSE
        SELECT * INTO save FROM saves WHERE id = NEW.id;
        IF save.head_turn_id IS NULL AND save.last_compacted_batch_id IS NOT NULL THEN
            RAISE EXCEPTION 'An empty save cannot have compacted coverage.' USING ERRCODE = '23514';
        END IF;
        PERFORM saga_validate_memory_cursor(save.campaign_id, save.memory_policy_id, save.head_turn_id, save.global_checkpoint_id, save.last_compacted_batch_id);
    END IF;
    RETURN NULL;
END
$$;

CREATE CONSTRAINT TRIGGER memory_cursor_integrity AFTER INSERT OR UPDATE ON memory_states
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_check_memory_cursor();

CREATE CONSTRAINT TRIGGER memory_cursor_integrity AFTER INSERT OR UPDATE ON campaigns
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_check_memory_cursor();

CREATE CONSTRAINT TRIGGER memory_cursor_integrity AFTER INSERT ON saves
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_check_memory_cursor();

CREATE FUNCTION saga_memory_state_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.id, NEW.campaign_id, NEW.policy_id, NEW.context_epoch)
        IS DISTINCT FROM ROW(OLD.id, OLD.campaign_id, OLD.policy_id, OLD.context_epoch) THEN
        RAISE EXCEPTION 'A memory context identity is immutable.' USING ERRCODE = '23514';
    END IF;
    IF NEW.revision < OLD.revision OR (
        ROW(NEW.global_checkpoint_id, NEW.last_compacted_batch_id)
        IS DISTINCT FROM ROW(OLD.global_checkpoint_id, OLD.last_compacted_batch_id)
        AND NEW.revision <= OLD.revision
    ) THEN
        RAISE EXCEPTION 'A changed memory cursor requires a newer revision.' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER memory_state_guard BEFORE UPDATE ON memory_states
FOR EACH ROW EXECUTE FUNCTION saga_memory_state_guard();
