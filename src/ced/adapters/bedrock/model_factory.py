"""Deploy-time model factory for Amazon Bedrock.

DR3: the credential seam is the model/provider layer. `BedrockConverseModel`
resolves the ambient credential chain with no ``CredentialProvider``
indirection. `make_bedrock_model` is the callable that fills
``PoolConfig.model_factory`` for any deployment wiring Bedrock.

**Adapter name constants are declared here, not in the executor.**
The producer tuple (r8 § 5) records the names of the model adapter class and
the fetch adapter class so a fixture run cannot be mistaken for a live one.
``ced.worker.executor`` imports those names from here rather than naming a
provider class directly, which is the whole point of keeping provider knowledge
inside ``adapters/``.
"""

from __future__ import annotations

from pydantic_ai.models.bedrock import BedrockConverseModel

__all__ = ["FETCH_ADAPTER_NAME", "MODEL_ADAPTER_NAME", "make_bedrock_model"]

#: r8 § 5 producer tuple: the model-adapter class name on this pin. Written
#: once, here, so the tuple and the import reference the same string.
MODEL_ADAPTER_NAME: str = "BedrockConverseModel"

#: r8 § 5 producer tuple: the fetch-adapter (credential/transport layer) class
#: name on this pin.
FETCH_ADAPTER_NAME: str = "BedrockProvider"


def make_bedrock_model(model_id: str) -> BedrockConverseModel:
    """Return a ``BedrockConverseModel`` that resolves credentials from the ambient chain.

    DR3 lands here: no credential provider object is constructed, no session is
    built explicitly, and no key is read from configuration. The ambient
    credential chain — populated by the environment variables the assumed role
    set — is the only source of credentials.

    ``model_id`` is the inference profile id (e.g.
    ``us.anthropic.claude-haiku-4-5-20251001-v1:0``), passed through from the
    role record without transformation.
    """
    return BedrockConverseModel(model_id)
