-- Phase 0 privilege model, per runtime-architecture.md § Identity — two layers.
--
-- The invariant under test: the database role that writes a `policy.decision`
-- event is not the role that performs the worker's general writes, and no
-- runtime identity holds both.
--
-- Postgres has no row-value-level grant, so the split is enforced by revoking
-- direct INSERT on `events` from everyone and exposing two SECURITY DEFINER
-- functions with disjoint EXECUTE grants.

CREATE ROLE ced_owner NOLOGIN;

CREATE ROLE app_api      LOGIN PASSWORD 'spike_api';
CREATE ROLE app_worker   LOGIN PASSWORD 'spike_worker';
CREATE ROLE app_policy   LOGIN PASSWORD 'spike_policy';

-- No role may create objects in public; schema is owned and granted explicitly.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO app_api, app_worker, app_policy;
ALTER SCHEMA public OWNER TO ced_owner;

SET ROLE ced_owner;

CREATE TABLE runs (
    run_id      uuid PRIMARY KEY,
    state       text NOT NULL DEFAULT 'requested',
    next_seq    bigint NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE steps (
    step_id           uuid PRIMARY KEY,
    run_id            uuid NOT NULL REFERENCES runs(run_id),
    state             text NOT NULL DEFAULT 'runnable',
    owner             text,
    lease_epoch       bigint NOT NULL DEFAULT 0,
    lease_expires_at  timestamptz
);

CREATE TABLE events (
    run_id       uuid NOT NULL REFERENCES runs(run_id),
    seq          bigint NOT NULL,
    occurred_at  timestamptz NOT NULL DEFAULT now(),
    type         text NOT NULL,
    step_id      uuid,
    agent_role   text,
    principal    text NOT NULL,
    payload_ref  text,
    PRIMARY KEY (run_id, seq)
);

-- Nobody holds direct DML on events. Both write paths go through a function.
REVOKE ALL ON events FROM PUBLIC;

GRANT SELECT ON runs, steps, events TO app_api, app_worker, app_policy;
GRANT INSERT, UPDATE ON runs  TO app_api;
GRANT INSERT, UPDATE ON steps TO app_api, app_worker;

-- Worker path: any event type EXCEPT policy.decision. next_seq is allocated in
-- the same transaction as the insert, so a rolled-back append leaves no hole.
CREATE FUNCTION append_event(
    p_run_id uuid, p_step_id uuid, p_lease_epoch bigint,
    p_type text, p_principal text, p_payload_ref text DEFAULT NULL)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE v_seq bigint;
BEGIN
    IF p_type = 'policy.decision' THEN
        -- session_user, not current_user: SECURITY DEFINER makes current_user
        -- the definer (ced_owner), which would name the wrong principal in an
        -- audit trail. Found by running this test.
        RAISE EXCEPTION 'append_event refuses policy.decision (caller %)', session_user
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- Fence first, then allocate: lock order is steps before runs.
    IF p_step_id IS NOT NULL THEN
        PERFORM 1 FROM steps
         WHERE step_id = p_step_id AND lease_epoch = p_lease_epoch
           FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'fenced: step % epoch %', p_step_id, p_lease_epoch
                USING ERRCODE = 'serialization_failure';
        END IF;
    END IF;

    UPDATE runs SET next_seq = next_seq + 1
     WHERE run_id = p_run_id RETURNING next_seq INTO v_seq;

    INSERT INTO events (run_id, seq, type, step_id, principal, payload_ref)
    VALUES (p_run_id, v_seq, p_type, p_step_id, p_principal, p_payload_ref);
    RETURN v_seq;
END $$;

-- Policy path: policy.decision ONLY.
CREATE FUNCTION append_policy_decision(
    p_run_id uuid, p_step_id uuid, p_principal text, p_payload_ref text DEFAULT NULL)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE v_seq bigint;
BEGIN
    UPDATE runs SET next_seq = next_seq + 1
     WHERE run_id = p_run_id RETURNING next_seq INTO v_seq;
    INSERT INTO events (run_id, seq, type, step_id, principal, payload_ref)
    VALUES (p_run_id, v_seq, 'policy.decision', p_step_id, p_principal, p_payload_ref);
    RETURN v_seq;
END $$;

RESET ROLE;

-- Disjoint execute grants are the whole control.
REVOKE ALL ON FUNCTION append_event(uuid,uuid,bigint,text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION append_policy_decision(uuid,uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION append_event(uuid,uuid,bigint,text,text,text) TO app_worker, app_api;
GRANT EXECUTE ON FUNCTION append_policy_decision(uuid,uuid,text,text)   TO app_policy;
