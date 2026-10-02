"""Confined static serving for the browser client."""

from __future__ import annotations

import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ced.api.main import _STATIC_ROOT

from .conftest import Client

pytestmark = pytest.mark.substrate


def _status(api_server: Client, path: str) -> int:
    request = urllib.request.Request(api_server.base_url + path)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_run_page_serves_only_the_fixed_index(api_server: Client, clean_runs: None) -> None:
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    request = urllib.request.Request(api_server.base_url + f"/runs/{run_id}")
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read().decode()

    assert response.status == 200
    assert response.headers.get_content_type() == "text/html"
    assert '<div id="root"></div>' in body


def test_static_paths_never_escape_the_bundle_root(api_server: Client) -> None:
    # Use the first JS asset from the built bundle; the filename is hash-based
    # so we discover it from the static directory rather than hardcoding it.
    assets = sorted((Path(_STATIC_ROOT) / "assets").glob("*.js"))
    assert assets, "no JS asset found in static/assets — rebuild the bundle first"
    assert _status(api_server, f"/static/assets/{assets[0].name}") == 200
    assert _status(api_server, "/static/../main.py") in {400, 404}
    assert _status(api_server, "/static/%2e%2e/main.py") in {400, 404}

    with tempfile.NamedTemporaryFile() as outside:
        link = Path(_STATIC_ROOT) / "out-of-root-link"
        try:
            os.symlink(outside.name, link)
        except (OSError, NotImplementedError):
            pytest.skip("filesystem does not support symlink creation")
        try:
            assert _status(api_server, "/static/out-of-root-link") in {400, 404}
        finally:
            link.unlink(missing_ok=True)
