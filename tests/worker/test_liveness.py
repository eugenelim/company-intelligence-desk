# STUB: AC-0331
def test_an_idle_worker_reports_healthy() -> None:
    """The mark the poll loop refreshes, not the heartbeat a lease drives."""
    from ced.worker.liveness import liveness_state

    assert liveness_state(seconds_since_poll=1.0, lease_ttl_seconds=60).healthy is True
