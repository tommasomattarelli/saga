CREATE FUNCTION saga_history_contains(campaign uuid, head uuid, candidate uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
    WITH RECURSIVE path AS (
        SELECT id, parent_turn_id FROM turns
        WHERE id = head AND campaign_id = campaign AND continuation_id IS NOT NULL
        UNION ALL
        SELECT t.id, t.parent_turn_id FROM turns t JOIN path p ON t.id = p.parent_turn_id
        WHERE t.campaign_id = campaign
    ) SELECT EXISTS (SELECT 1 FROM path WHERE id = candidate)
$$;

CREATE FUNCTION saga_continuation_contains(campaign uuid, continuation uuid, head uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1 FROM history_continuations c JOIN turns t ON t.id = head
        WHERE c.id = continuation AND c.campaign_id = campaign AND t.campaign_id = campaign
        AND (t.continuation_id = c.id OR saga_history_contains(campaign, c.fork_head_turn_id, head))
    )
$$;

CREATE FUNCTION saga_history_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'turns' AND to_jsonb(OLD)->>'continuation_id' IS NULL THEN
        IF to_jsonb(NEW)->>'continuation_id' IS NOT NULL THEN
            RAISE EXCEPTION 'Existing turns cannot be converted into history.' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_TABLE_NAME = 'saves' AND to_jsonb(OLD)->>'memory_policy_id' IS NULL THEN
        IF to_jsonb(NEW)->>'memory_policy_id' IS NOT NULL THEN
            RAISE EXCEPTION 'Existing saves cannot be converted into history.' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF to_jsonb(NEW) - 'updated_at' IS DISTINCT FROM to_jsonb(OLD) - 'updated_at' THEN
        RAISE EXCEPTION 'Committed history records are immutable.' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION saga_check_continuation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        WITH RECURSIVE ancestors AS (
            SELECT id, parent_continuation_id FROM history_continuations WHERE id = NEW.parent_continuation_id
            UNION
            SELECT c.id, c.parent_continuation_id FROM history_continuations c
            JOIN ancestors a ON c.id = a.parent_continuation_id
        ) SELECT 1 FROM ancestors WHERE id = NEW.id
    ) THEN
        RAISE EXCEPTION 'A continuation cannot contain a cycle.' USING ERRCODE = '23514';
    END IF;
    IF NEW.fork_head_turn_id IS NOT NULL AND NOT saga_continuation_contains(
        NEW.campaign_id, NEW.parent_continuation_id, NEW.fork_head_turn_id
    ) THEN
        RAISE EXCEPTION 'The fork must belong to the parent history.' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END
$$;

CREATE FUNCTION saga_history_preserved() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'turns' AND to_jsonb(OLD)->>'continuation_id' IS NULL THEN RETURN NULL; END IF;
    IF TG_TABLE_NAME = 'saves' AND to_jsonb(OLD)->>'memory_policy_id' IS NULL THEN RETURN NULL; END IF;
    IF TG_TABLE_NAME = 'memory_facts' AND to_jsonb(OLD)->>'batch_id' IS NULL THEN RETURN NULL; END IF;
    IF EXISTS (SELECT 1 FROM campaigns WHERE id = OLD.campaign_id) THEN
        RAISE EXCEPTION 'History sources cannot be removed from a retained campaign.' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END
$$;

CREATE FUNCTION saga_check_history_turn() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    fork uuid;
    parent_continuation uuid;
BEGIN
    IF NEW.continuation_id IS NULL THEN RETURN NULL; END IF;
    SELECT fork_head_turn_id INTO fork FROM history_continuations WHERE id = NEW.continuation_id;
    SELECT continuation_id INTO parent_continuation FROM turns WHERE id = NEW.parent_turn_id;
    IF parent_continuation IS DISTINCT FROM NEW.continuation_id
        AND NEW.parent_turn_id IS DISTINCT FROM fork THEN
        RAISE EXCEPTION 'The first turn must extend the continuation fork.' USING ERRCODE = '23514';
    END IF;
    IF NEW.parent_turn_id IS NULL AND fork IS NOT NULL THEN
        RAISE EXCEPTION 'A forked history cannot restart at depth one.' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END
$$;

CREATE FUNCTION saga_check_history_selection() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    continuation uuid;
    head uuid;
    campaign uuid;
BEGIN
    IF TG_TABLE_NAME = 'campaigns' THEN
        SELECT active_continuation_id, active_head_turn_id, id INTO continuation, head, campaign
        FROM campaigns WHERE id = NEW.id;
    ELSE
        SELECT continuation_id, head_turn_id, campaign_id INTO continuation, head, campaign
        FROM saves WHERE id = NEW.id;
    END IF;
    IF head IS NOT NULL AND NOT saga_continuation_contains(campaign, continuation, head) THEN
        RAISE EXCEPTION 'The selected head must belong to the selected history.' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END
$$;

CREATE CONSTRAINT TRIGGER history_turn AFTER INSERT ON turns
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_check_history_turn();

CREATE CONSTRAINT TRIGGER history_continuation AFTER INSERT ON history_continuations
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_check_continuation();

CREATE CONSTRAINT TRIGGER history_selection AFTER INSERT OR UPDATE ON campaigns
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_check_history_selection();

CREATE CONSTRAINT TRIGGER history_selection AFTER INSERT OR UPDATE ON saves
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_check_history_selection();

CREATE TRIGGER history_immutable BEFORE UPDATE ON turns
FOR EACH ROW EXECUTE FUNCTION saga_history_immutable();

CREATE TRIGGER history_immutable BEFORE UPDATE ON saves
FOR EACH ROW EXECUTE FUNCTION saga_history_immutable();

CREATE TRIGGER history_immutable BEFORE UPDATE ON history_continuations
FOR EACH ROW EXECUTE FUNCTION saga_history_immutable();

CREATE TRIGGER history_immutable BEFORE UPDATE ON memory_policies
FOR EACH ROW EXECUTE FUNCTION saga_history_immutable();

CREATE CONSTRAINT TRIGGER history_preserved AFTER DELETE ON turns
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_history_preserved();

CREATE CONSTRAINT TRIGGER history_preserved AFTER DELETE ON saves
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_history_preserved();

CREATE CONSTRAINT TRIGGER history_preserved AFTER DELETE ON history_continuations
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_history_preserved();

CREATE CONSTRAINT TRIGGER history_preserved AFTER DELETE ON memory_policies
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_history_preserved();
