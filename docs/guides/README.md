# docs/guides/

Guides for people using what this repository ships. They are organized by
[Diátaxis](https://diataxis.fr/), which sorts user docs by what the reader is
trying to do.

| Kind | What belongs there | Present today |
| --- | --- | --- |
| `how-to/` | Steps for one real task, for a reader who already knows the goal | [Publish the first analysis](how-to/publish-first-analysis.md) |
| `reference/` | Exact descriptions to look things up in | none. The HTTP contract lives in [`contracts/openapi/runs.yaml`](../../contracts/openapi/runs.yaml) |
| `tutorials/` | A guided first lesson | none yet |
| `explanation/` | Why the system works the way it does | none yet. The [architecture](../architecture/README.md) covers this |

A guide describes shipped behavior, so it is **living**: it changes in the same
change as the behavior it describes. A guide does not restate a spec's
acceptance criteria. It links to the spec instead.
