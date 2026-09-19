"""Company Intelligence Desk — the application package.

Five layers, one package, two entry points, per ADR-0003 D3. The layer
boundaries that matter are enforced by `tests/architecture`, not by packaging:

  domain/    pure rules and types; no framework, no I/O
  agents/    the reasoning layer; may import `pydantic_ai`
  adapters/  everything that talks to a real system; may import `pydantic_ai`
             and the AWS SDK
  api/       the HTTP surface
  worker/    the pool and step executor
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
