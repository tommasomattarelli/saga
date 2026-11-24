CREATE FUNCTION saga_check_memory_fact() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    fact uuid;
    item memory_facts;
    maximum integer;
BEGIN
    fact := CASE WHEN TG_TABLE_NAME = 'memory_facts' THEN to_jsonb(NEW)->>'id' ELSE to_jsonb(NEW)->>'fact_id' END;
    SELECT * INTO item FROM memory_facts WHERE id = fact;
    IF NOT FOUND OR item.batch_id IS NULL THEN RETURN NULL; END IF;
    IF jsonb_typeof(item.fact_metadata) IS DISTINCT FROM 'object'
        OR NOT (item.fact_metadata ?& ARRAY['entities','attribution','temporal_references','importance'])
        OR item.fact_metadata - ARRAY['entities','attribution','temporal_references','importance'] <> '{}'::jsonb
        OR jsonb_typeof(item.fact_metadata->'entities') IS DISTINCT FROM 'array'
        OR jsonb_typeof(item.fact_metadata->'attribution') IS DISTINCT FROM 'array'
        OR jsonb_typeof(item.fact_metadata->'temporal_references') IS DISTINCT FROM 'array'
        OR jsonb_typeof(item.fact_metadata->'importance') IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'Fact metadata must contain valid entities, attribution, time, and importance.' USING ERRCODE = '23514';
    END IF;
    SELECT (payload->'facts'->>'max_per_batch')::integer INTO maximum FROM memory_policies WHERE id = item.policy_id;
    IF NOT EXISTS (SELECT 1 FROM memory_fact_sources WHERE fact_id = fact) OR NOT EXISTS (
        SELECT 1 FROM memory_policies p, jsonb_array_elements(p.payload->'facts'->'importance_levels') level
        WHERE p.id = item.policy_id AND level->>'name' = item.fact_metadata->'importance'->>'level'
    ) OR (item.assertion_type <> 'occurrence' AND jsonb_array_length(item.fact_metadata->'attribution') = 0)
    OR maximum IS NULL OR (SELECT count(*) FROM memory_facts WHERE batch_id = item.batch_id) > maximum THEN
        RAISE EXCEPTION 'Fact sources, attribution, importance, and batch limits must be valid.' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(item.fact_metadata->'attribution') reference
        WHERE jsonb_typeof(reference) <> 'number' OR reference::text !~ '^[0-9]+$'
           OR reference::numeric >= jsonb_array_length(item.fact_metadata->'entities')
    ) OR (SELECT count(*) <> count(DISTINCT reference) FROM jsonb_array_elements(item.fact_metadata->'attribution') reference) THEN
        RAISE EXCEPTION 'Fact attribution must reference distinct entities.' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END
$$;

CREATE FUNCTION saga_check_memory_checkpoint() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    expected uuid;
    incorporated uuid;
BEGIN
    SELECT previous_batch_id INTO expected FROM memory_batches WHERE id = NEW.batch_id;
    SELECT batch_id INTO incorporated FROM memory_global_checkpoints WHERE id = NEW.previous_checkpoint_id;
    IF expected IS DISTINCT FROM incorporated OR (NEW.previous_checkpoint_id IS NULL AND expected IS NOT NULL) THEN
        RAISE EXCEPTION 'Global checkpoints must incorporate the next original batch.' USING ERRCODE = '23514';
    END IF;
    IF NOT (NEW.payload ?& ARRAY['story_so_far','open_threads','relationships','resolved_threads'])
    OR NEW.payload - ARRAY['story_so_far','open_threads','relationships','resolved_threads'] <> '{}'::jsonb
    OR jsonb_typeof(NEW.payload->'story_so_far') <> 'string' OR btrim(NEW.payload->>'story_so_far') = ''
    OR jsonb_typeof(NEW.payload->'open_threads') <> 'array'
    OR jsonb_typeof(NEW.payload->'relationships') <> 'array'
    OR jsonb_typeof(NEW.payload->'resolved_threads') <> 'array' THEN
        RAISE EXCEPTION 'A global checkpoint must have exactly four valid sections.' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements((NEW.payload->'open_threads') || (NEW.payload->'relationships') || (NEW.payload->'resolved_threads')) entry
        WHERE jsonb_typeof(entry) <> 'string' OR btrim(entry #>> '{}') = ''
    ) THEN
        RAISE EXCEPTION 'Global checkpoint lists must contain nonempty text.' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END
$$;

CREATE CONSTRAINT TRIGGER memory_fact_integrity AFTER INSERT ON memory_facts
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_check_memory_fact();

CREATE CONSTRAINT TRIGGER memory_fact_integrity AFTER INSERT ON memory_fact_sources
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_check_memory_fact();

CREATE CONSTRAINT TRIGGER memory_checkpoint_integrity AFTER INSERT ON memory_global_checkpoints
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_check_memory_checkpoint();

CREATE TRIGGER memory_immutable BEFORE UPDATE ON memory_summaries
FOR EACH ROW EXECUTE FUNCTION saga_memory_immutable();

CREATE TRIGGER memory_immutable BEFORE UPDATE ON memory_facts
FOR EACH ROW EXECUTE FUNCTION saga_memory_immutable();

CREATE TRIGGER memory_immutable BEFORE UPDATE ON memory_fact_sources
FOR EACH ROW EXECUTE FUNCTION saga_memory_immutable();

CREATE TRIGGER memory_immutable BEFORE UPDATE ON memory_global_checkpoints
FOR EACH ROW EXECUTE FUNCTION saga_memory_immutable();

CREATE CONSTRAINT TRIGGER memory_preserved AFTER DELETE ON memory_summaries
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_history_preserved();

CREATE CONSTRAINT TRIGGER memory_preserved AFTER DELETE ON memory_facts
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_history_preserved();

CREATE CONSTRAINT TRIGGER memory_preserved AFTER DELETE ON memory_fact_sources
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_history_preserved();

CREATE CONSTRAINT TRIGGER memory_preserved AFTER DELETE ON memory_global_checkpoints
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_history_preserved();
