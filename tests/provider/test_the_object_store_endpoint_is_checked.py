"""The object-store endpoint guard, which needs no substrate and no AWS.

Deliberately its own module: `test_a_step_runs_under_a_scoped_role.py` marks
every check in it `substrate`, and this one must run in the offline gate —
a guard that only executes when Postgres and MinIO happen to be up is not a
guard anyone can rely on.
"""

from __future__ import annotations

import pytest

from ced.adapters.objectstore.client import _checked_endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        # Where cloud instance metadata is served, and the case the guard
        # exists for: a perfectly well-formed http URL, so a scheme-only
        # check admits it.
        "http://169.254.169.254/",
        # The ECS task-metadata address, in the same range.
        "http://169.254.170.2/",
    ],
)
def test_a_link_local_endpoint_is_refused(endpoint: str) -> None:
    """An endpoint in the link-local range must not receive payload writes."""
    with pytest.raises(ValueError, match="link-local"):
        _checked_endpoint(endpoint)


@pytest.mark.parametrize("endpoint", ["file:///etc/passwd", "s3://bucket", "not-a-url", ""])
def test_an_endpoint_that_is_not_an_http_url_is_refused(endpoint: str) -> None:
    """Only http and https with a host are admitted."""
    with pytest.raises(ValueError, match="http or https"):
        _checked_endpoint(endpoint)


@pytest.mark.parametrize("endpoint", ["http://localhost:9000", "http://minio:9000"])
def test_the_deployments_own_endpoints_are_admitted(endpoint: str) -> None:
    """The guard must not refuse what the substrate and compose actually use.

    Loopback and ordinary private addresses stay admitted on purpose: MinIO is
    served on one, and a guard that refused them would refuse the deployment
    this module ships against rather than the hazard it targets.
    """
    assert _checked_endpoint(endpoint) == endpoint
