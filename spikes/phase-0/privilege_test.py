#!/usr/bin/env python3
"""Phase 0 executable privilege test.

Proves the invariant in runtime-architecture.md § Identity — two layers:

    the database role that writes a `policy.decision` event is not the role
    that performs the worker's general writes, and no runtime identity holds
    both.

A green result here is only meaningful because each assertion runs as the role
actually under test. Run as a superuser, every one of these would pass
vacuously.

Usage: python3 privilege_test.py
Exit 1 if any assertion fails.
"""
import subprocess
import sys
import uuid

CONTAINER = "ced-spike-pg"
PASSWORDS = {"app_worker": "spike_worker", "app_policy": "spike_policy",
             "app_api": "spike_api", "postgres": "spike_only_not_a_secret"}


def sql(role, statement):
    """Run one statement as `role`. Returns (ok, output)."""
    proc = subprocess.run(
        ["docker", "exec", "-e", f"PGPASSWORD={PASSWORDS[role]}", CONTAINER,
         "psql", "-h", "127.0.0.1", "-U", role, "-d", "ced",
         "-v", "ON_ERROR_STOP=1", "-t", "-A", "-c", statement],
        capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


results = []


def expect_refused(name, role, statement, because):
    ok, out = sql(role, statement)
    passed = not ok
    results.append((passed, name, "refused" if passed else f"ALLOWED — {out[:120]}"))
    if passed:
        detail = [l for l in out.splitlines() if "ERROR" in l]
        results[-1] = (True, name, (detail[0][:120] if detail else because))


def expect_allowed(name, role, statement):
    ok, out = sql(role, statement)
    results.append((ok, name, "allowed" if ok else f"REFUSED — {out[:120]}"))


run_id = str(uuid.uuid4())
step_id = str(uuid.uuid4())
sql("postgres", f"INSERT INTO runs (run_id) VALUES ('{run_id}')")
sql("postgres", f"INSERT INTO steps (step_id, run_id, lease_epoch) "
                f"VALUES ('{step_id}', '{run_id}', 1)")

# 1. The worker must not reach `events` directly at all.
expect_refused(
    "worker: direct INSERT into events", "app_worker",
    f"INSERT INTO events (run_id, seq, type, principal) "
    f"VALUES ('{run_id}', 999, 'step.started', 'w')",
    "no INSERT privilege on events")

# 2. The worker's own append path must refuse the reserved type.
expect_refused(
    "worker: append_event(type='policy.decision')", "app_worker",
    f"SELECT append_event('{run_id}', NULL, 0, 'policy.decision', 'w')",
    "function refuses the reserved type")

# 3. The worker must not hold the policy path.
expect_refused(
    "worker: append_policy_decision", "app_worker",
    f"SELECT append_policy_decision('{run_id}', NULL, 'w')",
    "no EXECUTE on append_policy_decision")

# 4. The policy writer must not hold the general path.
expect_refused(
    "policy-writer: append_event", "app_policy",
    f"SELECT append_event('{run_id}', NULL, 0, 'step.started', 'p')",
    "no EXECUTE on append_event")

# 5. Each role must still be able to do its own job, or the split is useless.
expect_allowed("worker: append_event(normal type)", "app_worker",
               f"SELECT append_event('{run_id}', NULL, 0, 'step.started', 'w')")
expect_allowed("policy-writer: append_policy_decision", "app_policy",
               f"SELECT append_policy_decision('{run_id}', NULL, 'p')")

# 6. Fencing: a stale lease_epoch must not be able to append.
expect_refused(
    "worker: append with stale lease_epoch", "app_worker",
    f"SELECT append_event('{run_id}', '{step_id}', 99, 'step.progress', 'w')",
    "fenced on lease_epoch mismatch")

ok, seqs = sql("postgres",
               f"SELECT string_agg(seq::text || ':' || type, ', ' ORDER BY seq) "
               f"FROM events WHERE run_id = '{run_id}'")

print("Phase 0 — executable privilege test\n")
for passed, name, detail in results:
    print(f"  {'PASS' if passed else 'FAIL'}  {name}\n        {detail}")
print(f"\n  event log for the run: {seqs}")

failed = [r for r in results if not r[0]]
print(f"\n{len(results) - len(failed)}/{len(results)} assertions passed")
sys.exit(1 if failed else 0)
