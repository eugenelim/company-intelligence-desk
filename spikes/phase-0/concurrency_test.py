#!/usr/bin/env python3
"""Phase 0 executable concurrency test — lock ordering and sequence integrity.

Three claims from runtime-architecture.md § Event log and stream mechanism and
§ Step execution are under test:

  A. Per-run `next_seq` allocated inside the append transaction yields a dense,
     duplicate-free sequence under concurrent writers. This is the reason the
     design rejects `bigserial`, whose allocation survives rollback.
  B. Lock order steps-before-runs does not deadlock under contention.
  C. Mixing the two orders deadlocks. Note the precision: a *uniformly*
     inverted order does not deadlock, because every writer takes the same
     `runs` row first and serializes there. The hazard is one path inverting
     *against* another, which is exactly what the design says. A rule nobody
     can show failing is not a rule.

Usage: ./.venv/bin/python concurrency_test.py
"""
import sys
import threading
import uuid

import psycopg

DSN = "host=127.0.0.1 port=55432 dbname=ced"
SUPER = DSN + " user=postgres password=spike_only_not_a_secret"
WORKER = DSN + " user=app_worker password=spike_worker"

WRITERS, PER_WRITER = 8, 25


def setup():
    run_id, step_ids = uuid.uuid4(), [uuid.uuid4() for _ in range(WRITERS)]
    with psycopg.connect(SUPER, autocommit=True) as c:
        c.execute("INSERT INTO runs (run_id) VALUES (%s)", (run_id,))
        for s in step_ids:
            c.execute("INSERT INTO steps (step_id, run_id, lease_epoch) "
                      "VALUES (%s, %s, 1)", (s, run_id))
    return run_id, step_ids


def claim_a_step(conn):
    """The claim half: SELECT ... FOR UPDATE SKIP LOCKED, stamp, commit fast."""
    with conn.cursor() as cur:
        cur.execute("SELECT step_id FROM steps WHERE state = 'runnable' "
                    "ORDER BY step_id FOR UPDATE SKIP LOCKED LIMIT 1")
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE steps SET owner = %s, lease_epoch = lease_epoch + 1, "
                        "lease_expires_at = now() + interval '60 seconds' "
                        "WHERE step_id = %s", (f"w{threading.get_ident()}", row[0]))
    conn.commit()


def run_phase(run_id, step_ids, inverted):
    """inverted=False: every writer takes steps then runs, as designed."""
    errors, deadlocks = [], []

    def writer(idx):
        try:
            with psycopg.connect(WORKER) as conn:
                for _ in range(PER_WRITER):
                    try:
                        with conn.cursor() as cur:
                            cur.execute(
                                "SELECT append_event(%s, NULL, 0, 'step.progress', %s)",
                                (run_id, f"w{idx}"))
                        conn.commit()
                        claim_a_step(conn)
                    except psycopg.errors.DeadlockDetected as e:
                        deadlocks.append(str(e).split("\n")[0][:80])
                        conn.rollback()
                    except Exception as e:
                        errors.append(f"{type(e).__name__}: {str(e)[:80]}")
                        conn.rollback()
        except Exception as e:
            errors.append(f"connect: {type(e).__name__}: {str(e)[:80]}")

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(WRITERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors, deadlocks


def run_mixed_orders(run_id, step_id, rounds=12):
    """Half the threads take steps->runs, half take runs->steps, on one pair.

    This is the cycle the design's lock-ordering rule exists to prevent. A
    uniformly inverted order cannot produce it.
    """
    deadlocks, errors, barrier = [], [], threading.Barrier(2)

    def contender(order):
        for _ in range(rounds):
            try:
                with psycopg.connect(SUPER) as conn:
                    with conn.cursor() as cur:
                        first, second = (
                            ("SELECT 1 FROM steps WHERE step_id = %s FOR UPDATE", (step_id,)),
                            ("UPDATE runs SET next_seq = next_seq WHERE run_id = %s", (run_id,)),
                        ) if order == "steps-first" else (
                            ("UPDATE runs SET next_seq = next_seq WHERE run_id = %s", (run_id,)),
                            ("SELECT 1 FROM steps WHERE step_id = %s FOR UPDATE", (step_id,)),
                        )
                        cur.execute(*first)
                        try:
                            barrier.wait(timeout=5)
                        except threading.BrokenBarrierError:
                            pass
                        cur.execute(*second)
                    conn.commit()
            except psycopg.errors.DeadlockDetected as e:
                deadlocks.append(str(e).split("\n")[0][:90])
            except Exception as e:
                errors.append(f"{type(e).__name__}: {str(e)[:60]}")

    ts = [threading.Thread(target=contender, args=(o,))
          for o in ("steps-first", "runs-first")]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return deadlocks, errors


print("Phase 0 — concurrency: lock ordering and sequence integrity\n")
results = []

# --- A + B: the design's order, under contention -----------------------------
run_id, step_ids = setup()
errors, deadlocks = run_phase(run_id, step_ids, inverted=False)

with psycopg.connect(SUPER) as c:
    seqs = [r[0] for r in c.execute(
        "SELECT seq FROM events WHERE run_id = %s ORDER BY seq", (run_id,)).fetchall()]
    next_seq = c.execute("SELECT next_seq FROM runs WHERE run_id = %s",
                         (run_id,)).fetchone()[0]

expected = WRITERS * PER_WRITER
dense = seqs == list(range(1, len(seqs) + 1))
results.append((len(seqs) == expected and dense and len(set(seqs)) == len(seqs),
                "A. sequence is dense and duplicate-free under concurrent writers",
                f"{len(seqs)}/{expected} events, seq 1..{max(seqs) if seqs else 0}, "
                f"next_seq={next_seq}, duplicates={len(seqs) - len(set(seqs))}"))
results.append((not deadlocks and not errors,
                "B. steps-before-runs does not deadlock",
                f"{len(deadlocks)} deadlock(s), {len(errors)} error(s)"
                + (f" — {errors[0]}" if errors else "")))

# --- C: mixed orders, which should deadlock ----------------------------------
run2, steps2 = setup()
deadlocks2, errors2 = run_mixed_orders(run2, steps2[0])
results.append((len(deadlocks2) > 0,
                "C. mixing steps-first and runs-first deadlocks",
                f"{len(deadlocks2)} deadlock(s) observed"
                + (f" — {deadlocks2[0]}" if deadlocks2 else " — none, rule unproven")))

for ok, name, detail in results:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n        {detail}")
failed = [r for r in results if not r[0]]
print(f"\n{len(results) - len(failed)}/{len(results)} claims held")
sys.exit(1 if failed else 0)
