# Product

> The product-side counterpart to [`architecture/`](../architecture/).
> Architecture answers "what is the code, today?"; product answers "what
> is the product, today?" Both are *living* docs — kept in sync with
> reality, not historical record.

## What lives here

What the product is *currently* doing — the counterpart to `architecture/`.
Without this layer you have per-feature contracts and decision history, but no
answer to "what is the product up to right now?"

| Path | Holds | Note |
| --- | --- | --- |
| [`roadmap.md`](roadmap.md) | Direction for the next few quarters | Direction, not commitments. An item that has not moved in two consecutive reviews is a drift signal. |
| [`changelog.md`](changelog.md) | User-visible changes by release, in [Keep a Changelog](https://keepachangelog.com/) format | One section per release, naming every artifact it covers. Updated in the same change that bumps a released artifact's version. |
| [`intents/`](intents/) | One admitted outcome each, recorded before a solution is chosen | Structurally linted by `tools/lint-intents.py`. |
| [`briefs/`](briefs/) | One delivery outcome each, and the specs that deliver it | For work too large to be one spec. |
| [`research/`](research/) | One answered question each, with the sources that answered it | Frozen once answered; supersede rather than edit. |

The changelog's heading level is load-bearing. A section carrying a version and
a date is released, so it sits at the top level directly beneath
`[Unreleased]` — never nested inside it.

## What does NOT live here

- **Why we made past choices** → [`../adr/`](../adr/) (immutable history).
- **What we're proposing to change** → [`../rfc/`](../rfc/) (governance).
- **What an individual feature does** → [`../specs/<feature>/spec.md`](../specs/).
- **The mission and scope of the project** → [`../CHARTER.md`](../CHARTER.md).
- **How users actually use the product** → `guides/`, Diátaxis-organized user
  docs. Not present yet; it arrives with the first shipped capability.

## The product/ layer is *living*

Unlike ADRs and shipped specs (which are frozen records), files here must
match current reality. Drift is a bug. The maintenance rules are in
[`../README.md` § The three lifecycle classes](../README.md#the-three-lifecycle-classes).
