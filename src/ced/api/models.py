"""Request and response shapes for the run surface.

These mirror `contracts/openapi/runs.yaml` § components.schemas. AC-0009
asserts the served document agrees with that file, so the contract is the
authority and this module is what makes the application satisfy it.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from ced.domain.events import EventEnvelope


class StartRunRequest(BaseModel):
    """What a client must supply to start a run."""

    principal: str = Field(min_length=1)
    agent_role: str = Field(min_length=1)


class StartedRun(BaseModel):
    run_id: UUID
    step_id: UUID
    seq: int


class Snapshot(BaseModel):
    """A run's state and the sequence number it is current to.

    A client that has been disconnected long enough to be uncertain of its
    cursor reads this, discards local state and resumes at `as_of_seq`.
    """

    run_id: UUID
    state: str
    as_of_seq: int


class Event(BaseModel):
    schema_version: int
    run_id: UUID
    seq: int
    type: str
    principal: str
    step_id: UUID | None = None
    agent_role: str | None = None
    payload_ref: str | None = None
    idempotency_key: str | None = None

    @classmethod
    def of(cls, envelope: EventEnvelope) -> Event:
        return cls(
            schema_version=envelope.schema_version,
            run_id=envelope.run_id,
            seq=envelope.seq,
            type=envelope.type,
            principal=envelope.principal,
            step_id=envelope.step_id,
            agent_role=envelope.agent_role,
            payload_ref=envelope.payload_ref,
            idempotency_key=envelope.idempotency_key,
        )


class EventPage(BaseModel):
    run_id: UUID
    events: list[Event]
