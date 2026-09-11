#!/usr/bin/env python3
"""Phase 0 spike 3 — stream resumption across forced disconnects.

Hypothesis, from runtime-architecture.md § Rollout:

    Stream resumption across forced disconnects, **with concurrent writers**.

The concurrency is the whole difficulty. A resumable stream over a quiescent log
is easy; the design's claim is that a client can drop mid-stream, reconnect with
its cursor, and still observe every event exactly once and in order *while other
writers are appending*. § Event log and stream mechanism adds that the client
owns the cursor, the server prefers `Last-Event-ID` over a stale `after=`, and
the sink is idempotent on `(run_id, seq)`.

Falsified by: a gap, a duplicate, an out-of-order delivery, or a client that
cannot resume.

Usage: ./.venv/bin/python stream_resumption_spike.py
"""
import http.server
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

import psycopg

DSN = "host=127.0.0.1 port=55432 dbname=ced"
SUPER = DSN + " user=postgres password=spike_only_not_a_secret"
WORKER = DSN + " user=app_worker password=spike_worker"

WRITERS, PER_WRITER = 4, 40
TOTAL = WRITERS * PER_WRITER
results = []


def record(ok, name, detail):
    results.append((ok, name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n        {detail}")


class Handler(http.server.BaseHTTPRequestHandler):
    """Minimal SSE endpoint: /events?run=<uuid>&after=<seq>."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        run_id = q["run"][0]
        # The server prefers Last-Event-ID over a possibly-stale `after=`.
        after = int(self.headers.get("Last-Event-ID") or q.get("after", ["0"])[0])
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            with psycopg.connect(SUPER) as conn:
                idle = 0
                while idle < 25:
                    rows = conn.execute(
                        "SELECT seq, type FROM events WHERE run_id = %s AND seq > %s "
                        "ORDER BY seq LIMIT 20", (run_id, after)).fetchall()
                    conn.commit()
                    if not rows:
                        idle += 1
                        time.sleep(0.05)
                        continue
                    idle = 0
                    for seq, typ in rows:
                        self.wfile.write(f"id: {seq}\ndata: {typ}\n\n".encode())
                        self.wfile.flush()
                        after = seq
        except (BrokenPipeError, ConnectionResetError):
            pass


def append_concurrently(run_id):
    def writer(i):
        with psycopg.connect(WORKER) as conn:
            for n in range(PER_WRITER):
                for attempt in range(5):
                    try:
                        with conn.cursor() as cur:
                            cur.execute("SELECT append_event(%s, NULL, 0, %s, %s)",
                                        (run_id, f"step.progress.{i}.{n}", f"w{i}"))
                        conn.commit()
                        break
                    except psycopg.errors.DeadlockDetected:
                        conn.rollback()
                        time.sleep(0.02 * (attempt + 1))
                time.sleep(0.004)
    ts = [threading.Thread(target=writer, args=(i,)) for i in range(WRITERS)]
    for t in ts:
        t.start()
    return ts


print("Phase 0 spike 3 — stream resumption across forced disconnects\n")

with psycopg.connect(SUPER, autocommit=True) as c:
    run_id = uuid.uuid4()
    c.execute("INSERT INTO runs (run_id) VALUES (%s)", (run_id,))

port = socket.socket()
port.bind(("127.0.0.1", 0))
PORT = port.getsockname()[1]
port.close()
server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

writers = append_concurrently(run_id)     # writers run for the whole test

received, disconnects, cursor = [], 0, 0
deadline = time.time() + 60

while len(received) < TOTAL and time.time() < deadline:
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/events?run={run_id}&after=0",   # deliberately stale
        headers={"Last-Event-ID": str(cursor)} if cursor else {})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            read_this_leg = 0
            for raw in resp:
                line = raw.decode().strip()
                if line.startswith("id: "):
                    seq = int(line[4:])
                    received.append(seq)
                    cursor = seq                       # the client owns the cursor
                    read_this_leg += 1
                # Force a disconnect mid-stream, repeatedly.
                if read_this_leg >= 17 and len(received) < TOTAL:
                    disconnects += 1
                    break
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        disconnects += 1
        time.sleep(0.05)

for t in writers:
    t.join()

# Drain anything appended after the last leg closed.
with psycopg.connect(SUPER) as c:
    tail = [r[0] for r in c.execute(
        "SELECT seq FROM events WHERE run_id = %s AND seq > %s ORDER BY seq",
        (run_id, cursor)).fetchall()]
received.extend(tail)

record(disconnects >= 3, "stream was actually interrupted",
       f"{disconnects} forced disconnect(s) across the run")
record(len(set(received)) == TOTAL and len(received) == TOTAL,
       "every event delivered exactly once",
       f"{len(received)} delivered, {len(set(received))} distinct, expected {TOTAL}, "
       f"duplicates={len(received) - len(set(received))}")
record(sorted(set(received)) == list(range(1, TOTAL + 1)),
       "no gaps in the delivered sequence",
       f"covers 1..{max(received) if received else 0}")
record(received == sorted(received), "delivery was monotonic across resumes",
       "in order" if received == sorted(received) else "out of order at a resume boundary")

server.shutdown()
failed = [r for r in results if not r[0]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
