CREATE FUNCTION saga_operation_integrity() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    source uuid;
    version integer;
    expected integer;
    actual integer;
    last_ordinal integer;
BEGIN
    source := (to_jsonb(NEW)->>CASE WHEN TG_TABLE_NAME = 'turns' THEN 'id' ELSE 'turn_id' END)::uuid;
    SELECT operations_version, operation_count INTO version, expected FROM turns WHERE id=source;
    SELECT count(*), max(ordinal) INTO actual, last_ordinal FROM turn_operations WHERE turn_id=source;
    IF (version IS NULL AND actual <> 0)
       OR (version IS NOT NULL AND (actual <> expected OR COALESCE(last_ordinal, 0) <> expected)) THEN
        RAISE EXCEPTION 'Turn operations must match their complete ordered recording.' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END
$$;

CREATE CONSTRAINT TRIGGER operations_integrity AFTER INSERT ON turns
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_operation_integrity();

CREATE CONSTRAINT TRIGGER operations_integrity AFTER INSERT ON turn_operations
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_operation_integrity();

CREATE FUNCTION saga_operations_marker_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.operations_version, NEW.operation_count) IS DISTINCT FROM
       ROW(OLD.operations_version, OLD.operation_count) THEN
        RAISE EXCEPTION 'A committed operation recording cannot be changed or reconstructed.' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER operations_marker_guard BEFORE UPDATE ON turns
FOR EACH ROW EXECUTE FUNCTION saga_operations_marker_guard();

CREATE FUNCTION saga_operation_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' AND NOT EXISTS (SELECT 1 FROM campaigns WHERE id=OLD.campaign_id) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'Committed operation sources are immutable.' USING ERRCODE='23514';
END
$$;

CREATE TRIGGER operation_immutable BEFORE UPDATE OR DELETE ON turn_operations
FOR EACH ROW EXECUTE FUNCTION saga_operation_immutable();
