"""§ Grounding probe row 6 — `DeferredToolRequests` at the package root.

The type resolves from a private module and is re-exported at the package
root. r5's risk register names exactly this as the additive-minor drift to
catch: a re-export moving is not classed as breaking by the vendor, so this
module pins the import path the runtime uses as well as the two fields the
approval gate reads.
"""

from __future__ import annotations

import dataclasses
import importlib

import pydantic_ai
from pydantic_ai import DeferredToolRequests


def test_the_type_is_reachable_from_the_package_root() -> None:
    """The root binding is the contract, not the private module it currently lives in."""
    root = importlib.import_module("pydantic_ai")
    assert "DeferredToolRequests" in vars(root), "the root re-export moved or went lazy"
    assert vars(root)["DeferredToolRequests"] is DeferredToolRequests
    assert "DeferredToolRequests" in pydantic_ai.__all__


def test_the_type_carries_both_the_calls_and_the_approvals_the_gate_reads() -> None:
    """Both fields, and both defaulted, so a gate can construct an empty request set."""
    fields = {field.name: field for field in dataclasses.fields(DeferredToolRequests)}
    assert {"calls", "approvals"} <= set(fields)

    empty = DeferredToolRequests()
    assert empty.calls == []
    assert empty.approvals == []
