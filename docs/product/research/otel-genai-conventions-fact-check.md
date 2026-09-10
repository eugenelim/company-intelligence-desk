# OpenTelemetry GenAI semantic conventions — fact check

> Discipline: primary-source fact check (OpenTelemetry specification and repos)

Commissioned 2026-09-10 to settle which instrumentation standard the
observability companion should name, and whether its "no free text crosses the
telemetry boundary" rule conflicts with the standard.

**Everything here is dated.** These conventions are on a deliberately fast,
independent release cadence; a restatement without a date will go stale.

## The headline results

1. **The conventions exist and are usable, but nothing is Stable.** Every
   `gen_ai.*` span, metric, event and attribute carries the **Development**
   badge — OpenTelemetry's current label for what used to be called
   Experimental. Attribute names can and do change.
2. **They moved out of the core repository.** In semantic-conventions **v1.42.0
   (June 2026)** all `gen_ai.*`, `openai.*` and `mcp.*` definitions were
   deprecated in the core repo and relocated to
   `open-telemetry/semantic-conventions-genai`. This is an organisational split
   for release cadence, **not a graduation to Stable**.
3. **There is no versioned GenAI schema URL to pin against.** The new repo's
   `CHANGELOG.md` has only an "Unreleased" section with no tags, and the
   README's Schema URL section is marked `TODO`. Pin *instrumentation library
   versions*, not schema URLs.
4. **Content capture is opt-in, and the default is no content.** This is the
   answer that matters here: a design forbidding all free text in telemetry is
   **fully compatible with the conventions, not a deviation from them.**

## Content capture — the load-bearing detail

`gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`,
`gen_ai.prompt.variable`, and the `gen_ai.memory.*` and `gen_ai.retrieval.*`
content attributes are all marked requirement level **`Opt-In`**, the lowest
level OpenTelemetry defines.

The normative text: *"Instrumentations SHOULD NOT capture this attribute by
default. Capture SHOULD be gated by an explicit user opt-in, for example
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`."*

**Note "for example".** That environment variable is referenced
*illustratively* by the semantic conventions and is **not defined in the OTel
SDK environment-variable specification** — confirmed by checking that spec and
not finding it. Its concrete behaviour lives in language instrumentation. In
OpenTelemetry Python contrib the documented values are `true` on the legacy
path, or `span_only` / `event_only` / `span_and_event` when
`OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` is set, and the
default is `NO_CONTENT`. **Do not write "the spec defines this variable"** —
other languages may differ, and JS, Java and .NET were not checked.

The spec carries its own privacy warning, verbatim on both message attributes:
*"This attribute is likely to contain sensitive information including user/PII
data."*

**No redaction mechanism is mandated.** The only text is permissive:
*"Instrumentations MAY provide a way for users to filter or truncate input
messages."* There is no specified redaction pipeline, no PII-scrubbing
processor, and no required filtering hook. Collector-side redaction exists but
is generic OpenTelemetry machinery, not part of these conventions.

**Consequence.** Every Required and Conditionally Required attribute is
metadata, never content: `gen_ai.operation.name`, `gen_ai.provider.name`, the
model names, token counts, `error.type`, `gen_ai.tool.name`. A system that never
exercises the content opt-in loses no MUST- or SHOULD-level conformance. The
right phrasing is *"we do not exercise the content opt-in"*, which is stronger
and clearer than *"we deviate from the standard"*.

**Where free text would otherwise leak in:** `gen_ai.tool.call.arguments`,
`gen_ai.tool.call.result`, and `gen_ai.retrieval.query.text`. All are Opt-In,
and all are exactly the attributes a diligence system would be tempted to
enable.

## Attribute surface

Exact keys, all Development.

- **Provider and model** — `gen_ai.provider.name` (**replaces the deprecated
  `gen_ai.system`**), `gen_ai.request.model`, `gen_ai.response.model`,
  `gen_ai.response.id`, `gen_ai.response.finish_reasons`, `gen_ai.output.type`.
- **Operation** — `gen_ai.operation.name`, with values including `chat`,
  `embeddings`, `create_agent`, `invoke_agent`, `invoke_workflow`,
  `execute_tool`, `plan`.
- **Tokens** — `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
  (**superseding `prompt_tokens` / `completion_tokens`**),
  `gen_ai.usage.reasoning.output_tokens`, `gen_ai.usage.cache_read.input_tokens`,
  `gen_ai.usage.cache_creation.input_tokens`, `gen_ai.token.type`.
- **Request parameters** — `gen_ai.request.temperature`, `.top_p`, `.top_k`,
  `.max_tokens`, `.stop_sequences`, `.seed`, `.stream`, `.choice.count`,
  `.frequency_penalty`, `.presence_penalty`, `.encoding_formats`.
- **Identifiers** — `gen_ai.conversation.id`, `gen_ai.agent.id`, `.name`,
  `.description`, `.version`, `gen_ai.workflow.name`, `gen_ai.data_source.id`,
  `gen_ai.prompt.name`.
- **Tools** — `gen_ai.tool.name`, `gen_ai.tool.type`
  (`function` / `extension` / `datastore`), `gen_ai.tool.description`,
  `gen_ai.tool.call.id`, and the content-bearing `.arguments`, `.result`,
  `gen_ai.tool.definitions`.

## Spans, metrics, events

**Spans** — one per operation. Naming is normative: inference and embeddings
spans are `"{gen_ai.operation.name} {gen_ai.request.model}"`; retrieval is
`"{gen_ai.operation.name} {gen_ai.data_source.id}"`; fetch-response and memory
spans use the operation name alone, with the response ID **deliberately
excluded for cardinality**. Most require `gen_ai.operation.name` and
`gen_ai.provider.name`, with `error.type` conditionally required on failure.

**Metrics** — all histograms: `gen_ai.client.token.usage`,
`gen_ai.client.operation.duration`, `.time_to_first_chunk`,
`.time_per_output_chunk`; server-side `gen_ai.server.request.duration`,
`.time_to_first_token`, `.time_per_output_token`; agentic
`gen_ai.invoke_agent.duration`, `.inference_calls`, `.tool_calls`,
`gen_ai.invoke_workflow.duration`, `gen_ai.execute_tool.duration`.

**Content representation has been through three generations**, which matters
when reading any older integration:

1. *Superseded* — `gen_ai.prompt` / `gen_ai.completion` span attributes,
   deprecated with no direct replacement.
2. *Superseded* — per-message span events (`gen_ai.user.message`,
   `gen_ai.choice`).
3. *Current* — a single event `gen_ai.client.inference.operation.details`
   carrying structured `gen_ai.input.messages` / `gen_ai.output.messages`.

## Agentic coverage

Defined, all Development: `create_agent` (CLIENT); `invoke_agent` in **two
flavours** — CLIENT for remote agent services such as Bedrock Agents, INTERNAL
for in-process frameworks; `invoke_workflow` (INTERNAL, "an operation that
executes a coordinated process composed of multiple agents"); `plan` (INTERNAL,
task decomposition); and `execute_tool`.

**Agent-to-agent handoff semantics are not defined.** No handoff span or
attribute exists; multi-agent coordination is expressed only through
`invoke_workflow` nesting and `gen_ai.workflow.name`.

## Evaluation

OpenTelemetry has taken a position here that most vendor schemas have not:
`gen_ai.evaluation.name`, `gen_ai.evaluation.score.value`,
`gen_ai.evaluation.score.label`, `gen_ai.evaluation.explanation`, and a
`gen_ai.evaluation.result` event.

**There is no `gen_ai.usage.cost` attribute.** Cost is not standardised; it is
derived downstream from token counts and model name.

## Adjacent standards

- **OpenLLMetry (Traceloop)** — upstreamed into OpenTelemetry; the deprecated
  `gen_ai.prompt` / `gen_ai.completion` attributes are its lineage. Converging.
- **OpenInference (Arize)** — a parallel, complementary spec using `llm.*`,
  `input.value`, `output.value`. Not upstreamed; Arize normalises inbound
  `gen_ai.*` into OpenInference at ingest. Convergence expected but not
  scheduled — treat as an ongoing fork.
- **Langfuse** — ingests OTLP over HTTP/JSON and HTTP/protobuf at
  `/api/public/otel`, with **no gRPC**. It aims at GenAI-convention compliance
  and maps `gen_ai.prompt`, `gen_ai.completion`, `gen_ai.request.model`,
  `gen_ai.usage.*`, plus OpenInference and MLflow attributes. Its own
  `langfuse.*` namespace **takes precedence** over the generic conventions.
  **Caveat:** the attributes it names are the *deprecated* generation; verify
  current `gen_ai.input.messages` support before relying on it.

## Known unknowns

Answerable, not answered here. Close before anything ratifies on them.

- **The v1.42.0 release date.** The release page rendered "June 12, 2024",
  inconsistent with the version number and with secondary sources giving
  **12 June 2026**. June 2026 is used above; verify against the tag before
  citing a date.
- **The canonical definition of the content-capture environment variable** in
  languages other than Python. Its allowed values above are Python-contrib
  behaviour, not spec mandate.
- **Whether a multi-agent handoff proposal is open.** No handoff construct was
  found, but the repo has roughly 120 open issues and open PRs were not
  enumerated.

## A hazard worth recording

The core registry page now renders every `gen_ai.*` attribute as **Deprecated**.
That reflects the June 2026 repository move, **not** genuine deprecation of the
concepts. Any automated conformance check built against the core registry will
therefore report the entire GenAI surface as deprecated and be wrong.
