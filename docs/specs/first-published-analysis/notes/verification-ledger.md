# Verification ledger — First published analysis

Records mutation proofs for each AC addressed by T1. Each entry names the guard,
the mutation that would remove it, and the assertion that reds when the guard is
absent.

No absolute paths, personal identifiers, or runtime `SEC_CONTACT` values appear
in this file.

---

## T1: One bounded SEC ingestion path produces an immutable snapshot

### AC-0401 — CIK and as-of date gate; primary document validation

**Guard: wrong CIK is refused.**
Mutation: replace `CANONICAL_CIK` equality with any string in `_select_filing`.
Red: `test_ingest_refuses_unsupported_cik` — `IngestionError` is not raised and
the assertion `pytest.raises(IngestionError, match="not found")` fails.

**Guard: post-as-of filing date is refused.**
Mutation: remove the `filing_date > as_of_date` check in `_select_filing`.
Red: `test_select_filing_refuses_future_filing` — no error is raised and
`pytest.raises(IngestionError, match="after the requested as-of date")` fails.

**Guard: wrong as-of date refuses the canonical filing.**
Mutation: remove the date comparison entirely.
Red: `test_ingest_refuses_unsupported_as_of_date` — the filing dated 2026-07-31
would still be returned when the requested as-of is 2026-01-01.

**Guard: absolute URL in primary document is refused.**
Mutation: remove the `://` membership check in `_validate_primary_doc`.
Red: `test_validate_primary_doc_refuses_absolute_url` — no error raised.

**Guard: userinfo (@) in primary document is refused.**
Mutation: remove the `@` check.
Red: `test_validate_primary_doc_refuses_userinfo` — no error raised.

**Guard: forward slash path separator is refused.**
Mutation: remove the `/` check.
Red: `test_validate_primary_doc_refuses_forward_slash` — no error raised.

**Guard: URL-encoded slash (%2f) is refused.**
Mutation: remove the `%2f` case-insensitive check.
Red: `test_validate_primary_doc_refuses_encoded_slash` — no error raised.

**Guard: backslash path separator is refused.**
Mutation: remove the `\\` check.
Red: `test_validate_primary_doc_refuses_backslash` — no error raised.

**Guard: dot-segment traversal (../  ./) is refused.**
Mutation: remove the `startswith("./")` / `startswith("../")` checks.
Red: `test_validate_primary_doc_refuses_dot_segment` and
`test_validate_primary_doc_refuses_current_dir_dot` — no errors raised.

**Guard: bare dot (.) is refused.**
Mutation: remove the `doc in (".", "..")` check.
Red: `test_validate_primary_doc_refuses_bare_dot` — no error raised.

**Guard: overlong basename (>256 chars) is refused.**
Mutation: remove the explicit length check.
Red: `test_validate_primary_doc_refuses_overlong` — the 257-char name would
pass through to the pattern check; the pattern itself also catches it, but the
error message would differ. With the guard absent the length check red fires on
names up to 256 chars that the pattern still refuses.

**Guard: disallowed characters refused by pattern.**
Mutation: remove `PRIMARY_DOC_PATTERN.fullmatch` check.
Red: `test_validate_primary_doc_refuses_disallowed_chars` — space-containing
name is not refused.

### AC-0402 — SEC client: hosts, redirects, blocked, size caps, TLS, timeouts

**Guard: disallowed host refused.**
Mutation: remove `host not in _ALLOWED_HOSTS` check.
Red: `test_fetch_url_refuses_disallowed_host` — no error raised for `evil.example.com`.

**Guard: HTTP 301 is refused as a redirect.**
Mutation: remove 301 from the redirect status set.
Red: `test_fetch_url_refuses_301` — `SecRedirectError` not raised.

**Guard: HTTP 302 is refused as a redirect.**
Mutation: remove 302.
Red: `test_fetch_url_refuses_302` — `SecRedirectError` not raised.

**Guard: HTTP 307 is refused as a redirect.**
Mutation: remove 307.
Red: `test_fetch_url_refuses_307` — `SecRedirectError` not raised.

**Guard: HTTP 403 raises SecBlockedError.**
Mutation: remove 403 from the blocked set.
Red: `test_fetch_url_raises_blocked_on_403` — generic `SecClientError` raised
instead of `SecBlockedError`.

**Guard: HTTP 429 raises SecBlockedError.**
Mutation: remove 429 from the blocked set.
Red: `test_fetch_url_raises_blocked_on_429` — same.

**Guard: declared Content-Length above size cap refused before reading.**
Mutation: remove the `cl > size_cap` check.
Red: `test_fetch_url_refuses_oversized_declared_length` — no error raised.

**Guard: streamed body crossing size cap is refused.**
Mutation: remove the `len(body) > size_cap` guard.
Red: `test_fetch_url_refuses_oversized_body_during_streaming` — no error raised
for a 51-byte body against a 50-byte cap.

**Guard: total budget check fires (pre-connect, in read loop, post-fetch).**
Mutation: remove the pre-connect `remaining <= 0` check in `_real_fetch`.
Red: `test_fetch_url_refuses_when_total_budget_exceeded` — when the injected
clock returns 35 s on the first `_real_fetch` clock call, remaining = 30 − 35
= −5 s; without the guard, no error is raised.

**Guard: total budget timer starts at admission, not at gate-wait start.**
Mutation: set `budget_start = gate_start` instead of `budget_start =
admission_time`.
Red: `test_fetch_url_total_budget_starts_at_admission` — the 25 s gate wait
would count against the 30 s budget leaving only 5 s; the request (which
succeeds in 1 s of admitted time) would be refused, but the test asserts
`stop_condition == "success"`.

**Guard: malformed Content-Length is refused (fail-closed) before read.**
Mutation: catch `ValueError` and set `cl = 0` (treat malformed as zero).
Red: `test_fetch_url_refuses_malformed_content_length` — no error raised;
the body would be read without a length check.

**Guard: retry_count is always 0.**
Mutation: set retry_count = 1.
Red: `test_attempt_record_has_zero_retry_count` — assertion fails.

**Guard: blocked=False on success.**
Mutation: always set blocked=True.
Red: `test_attempt_record_blocked_false_on_success` — assertion fails.

**Guard: no_response_class is None when HTTP response received.**
Mutation: always set no_response_class = "dns".
Red: `test_attempt_record_no_response_class_none_on_success` — assertion fails.

**Guard: missing SEC_CONTACT raises SecClientError.**
Mutation: return empty string instead of raising.
Red: `test_acquire_contact_raises_when_env_absent` — no exception raised.

**Guard: blank SEC_CONTACT raises SecClientError.**
Mutation: accept whitespace-only strings.
Red: `test_acquire_contact_raises_when_env_blank` — no exception raised.

**Guard: contact value absent from host-refusal, DNS, TLS, and redirect messages.**
Mutation: include `contact` in any error message.
Red: the corresponding `test_contact_value_absent_from_*` assertion fails.

**Guard: TLS context requires CERT_REQUIRED.**
Mutation: set `verify_mode = ssl.CERT_NONE`.
Red: `test_tls_context_has_cert_required` — structural check fails immediately.

**Guard: TLS context has check_hostname=True.**
Mutation: set `check_hostname = False`.
Red: `test_tls_context_has_check_hostname` — structural check fails.

**Guard: each address class is refused through connect() with zero socket opens.**
All tests below use a fake `resolve` callable that returns the specific
address. The real `connect()` code runs; `open_socket` tracks how many times
it is called. Deleting the `addr.is_global and not addr.is_multicast` predicate
in `_GatedSecConnection.connect()` makes every refused-address test pass without
raising and with `socket_opens != []`.

- Mutation: remove `is_global`. Red: `test_connect_refuses_ipv4_loopback` —
  127.0.0.1 admitted, `opens == ["127.0.0.1"]`, no `SecClientError`.
- Mutation: same. Red: `test_connect_refuses_ipv4_private` — 10.0.0.1 admitted.
- Mutation: same. Red: `test_connect_refuses_ipv4_link_local` — 169.254.1.1 admitted.
- Mutation: same. Red: `test_connect_refuses_ipv4_unspecified` — 0.0.0.0 admitted.
- Mutation: same. Red: `test_connect_refuses_ipv4_shared` — 100.64.0.1 admitted.
- Mutation: remove `not addr.is_multicast`. Red: `test_connect_refuses_ipv4_multicast` —
  239.255.0.1 (global multicast) admitted.
- Mutation: remove `is_global`. Red: `test_connect_refuses_ipv6_loopback` — ::1 admitted.
- Mutation: same. Red: `test_connect_refuses_ipv6_unique_local` — fc00::1 admitted.
- Mutation: remove `not addr.is_multicast`. Red: `test_connect_refuses_ipv6_multicast` —
  ff02::1 admitted.

**Guard: each refused address produces no_response_class="dns" and gate exits.**
Mutation: raise with `no_response_class=None`.
Red: `_assert_refused_with_gate_exit` asserts `exc.no_response_class == "dns"`;
`exited == [True]` asserts gate exits.

**Guard: mixed resolution connects to first public address only.**
Mutation: connect to the first address regardless of type.
Red: `test_connect_mixed_resolution_uses_first_public_addr_only` — `opens`
would include "127.0.0.1" before "8.8.8.8".

**Guard: resolver called exactly once per request.**
Mutation: call `socket.getaddrinfo` again before connecting.
Red: `test_resolver_called_exactly_once` — `call_count[0] == 2`.

**Guard: server_hostname equals the SEC host.**
Mutation: pass `server_hostname=None` to `wrap`.
Red: `test_server_hostname_equals_sec_host` — `wrap_calls != [_HOST]`.

**Guard: TLS failure maps to no_response_class="tls".**
Mutation: map `ssl.SSLError` to `no_response_class="dns"` or leave it `None`.
Red: `test_tls_failure_maps_to_tls_class` — assertion on `no_response_class` fails.

**Guard: connect timeout maps to no_response_class="connect_timeout".**
Mutation: map `TimeoutError` from `open_socket` to `no_response_class="dns"`.
Red: `test_connect_timeout_maps_to_connect_timeout_class` — assertion fails.

**Guard: read timeout maps to no_response_class="read_timeout".**
Mutation: map `TimeoutError` from send/receive to `no_response_class="dns"`.
Red: `test_read_timeout_maps_to_read_timeout_class` — assertion fails.

**Guard: total_timeout no_response_class set on budget exhaustion.**
Mutation: raise without `no_response_class`.
Red: `test_total_timeout_class_set_on_budget_exceeded` — assertion fails.

**Guard: gate exits after DNS or TLS failure.**
Mutation: gate context manager is not exited on error.
Red: `test_gate_exits_after_dns_failure`, `test_gate_exits_after_tls_failure` —
`exited == []` assertion fires.

### AC-0403 — Shared Postgres rate gate

**Guard: two processes are serialised by at least `_GATE_INTERVAL`.**
Mutation 1: replace `pg_advisory_lock` with a threading.Lock — each spawned
process gets its own thread-local lock and both are admitted instantly.
Red: `test_two_processes_gate_admission_separated` — `separation` is near 0 and
`< _GATE_INTERVAL` assertion fires.

Mutation 2: delete the `time.sleep(remaining)` hold in `open_postgres_gate` —
the lock is released immediately after admission.
Red: same test — the second process is admitted before the interval elapses.

**Guard: terminating holder releases lock without deadlock.**
Mutation: use a file lock without `LOCK_NB` that is not released on process death.
Red: `test_holder_termination_releases_contender` — the `queue.get(timeout=15)`
call times out and `contender_admitted` is False.

### AC-0404 — Content-addressed snapshot storage and redaction

**Guard: filing stored under SNAPSHOT_SCOPE prefix.**
Mutation: use `OWNER_SCOPE` instead.
Red: `test_filing_bytes_stored_under_snapshot_scope` — the prefix assertion fails.

**Guard: snapshot manifest round-trips correctly.**
Mutation: write manifest to a different key.
Red: `test_snapshot_manifest_round_trip` — `read_payload(snapshot_ref)` raises
NoSuchKey or returns wrong data.

**Guard: duplicate writes yield same filing_ref.**
Mutation: add a random nonce to the key.
Red: `test_duplicate_filing_write_returns_same_filing_ref` — `fil1_ref != fil2_ref`.

**Guard: retrieval_time change moves only snapshot_ref.**
Mutation: exclude `retrieved_at` from the manifest.
Red: `test_retrieval_time_change_moves_only_manifest_ref` — both snapshot_refs
are identical even with different retrieval times.

**Guard: round-trip digest mismatch fails before parsing.**
Mutation: remove the digest verification in `_verify_round_trip`.
Red: `test_round_trip_digest_check_fails_on_tampered_filing` — tampered bytes
are accepted without error.

**Guard: SEC_CONTACT absent from stored filing bytes.**
Mutation: store the contact value in the filing or manifest.
Red: `test_contact_value_absent_from_stored_filing_and_manifest` — the MARKER
string found in stored bytes.

**Guard: SEC_CONTACT absent from ingest stdout.**
Mutation: print the contact value to stdout.
Red: `test_contact_value_absent_from_ingest_stdout` — MARKER found in output.

**Guard: offline ingest produces a readable snapshot ref.**
Mutation: return a hardcoded fake ref.
Red: `test_offline_ingest_produces_readable_snapshot_ref` — `read_payload`
raises NoSuchKey.

**Guard: FILING_CONTENT_HASH matches the committed file.**
Mutation: change the constant without updating the fixture.
Red: `test_fixture_hash_matches_file` — hash comparison fails immediately.

### AC-0405 — Selection does not fall back to a different filing

**Guard: missing accessionNumber field fails ingestion.**
Mutation: swallow KeyError and proceed.
Red: `test_select_filing_refuses_missing_accession_field` — no IngestionError.

**Guard: missing filingDate field fails ingestion.**
Mutation: same.
Red: `test_select_filing_refuses_missing_filing_date_field` — no IngestionError.

**Guard: no matching accession fails ingestion.**
Mutation: return a default empty filing dict instead of raising.
Red: `test_select_filing_refuses_no_match` — no IngestionError.

### AC-0417 — Observation schedule, counts, and redaction

**Guard: planned and started counts are recorded.**
Mutation: omit `planned_attempts` from the record.
Red: `test_observation_records_planned_and_started_counts` — KeyError or wrong value.

**Guard: every per-attempt record has retry_count == 0.**
Mutation: set retry_count = 1 in any attempt.
Red: `test_observation_records_zero_retries_per_attempt` — assertion fails.

**Guard: outcome_counts is present.**
Mutation: omit `outcome_counts` key.
Red: `test_observation_records_outcome_counts` — KeyError.

**Guard: target_start_interval_seconds is present.**
Mutation: omit the field.
Red: `test_observation_records_target_interval` — KeyError or wrong value.

**Guard: first_to_last_start_duration_seconds is present.**
Mutation: omit the field.
Red: `test_observation_records_first_to_last_duration` — KeyError.

**Guard: statement field is present and non-empty.**
Mutation: omit the statement.
Red: `test_observation_records_statement_about_limitations` — KeyError or length check fails.

**Guard: min_interval < 1 s fails the observation.**
Mutation: remove the `min_interval < interval_seconds` check.
Red: `test_observation_fails_when_min_interval_below_one_second` — function
returns without raising on a clock that produces 0.01 s intervals.

**Guard: 403 is recorded as a valid blocked outcome.**
Mutation: raise on 403 instead of recording it.
Red: `test_observation_treats_403_as_valid_blocked_outcome` — SecClientError
propagates; started_attempts assertion fails.

**Guard: 429 is a valid blocked outcome.**
Mutation: same.
Red: `test_observation_treats_429_as_valid_blocked_outcome` — same failure mode.

**Guard: no retries — exactly N transport calls.**
Mutation: add a retry loop.
Red: `test_observation_never_retries_on_error` — call_count > N or retry_count > 0.

**Guard: contact value absent from observation record.**
Mutation: include contact in any record field.
Red: `test_contact_value_absent_from_observation_record` — MARKER found in serialised JSON.

---

## Owner scope extension (objectstore/client.py)

**Guard: unrecognised scope refused before any S3 call.**
Mutation: remove the `owner_scope not in _ADMITTED_SCOPES` check.
Red: `test_write_payload_bytes_refuses_unrecognised_scope` and
`test_write_payload_refuses_unrecognised_scope` — no ValueError raised.

**Guard: default scope is still OWNER_SCOPE.**
Mutation: change the default to SNAPSHOT_SCOPE.
Red: `test_write_payload_bytes_default_scope_is_owner_scope` and
`test_write_payload_default_scope_is_owner_scope` — `param.default` assertion fails.

**Guard: SNAPSHOT_SCOPE used in key prefix when passed explicitly.**
Mutation: ignore the `owner_scope` argument and always use `OWNER_SCOPE`.
Red: `test_write_payload_bytes_uses_snapshot_scope_in_key` — key prefix assertion fails.

**Guard: default call produces OWNER_SCOPE prefix.**
Mutation: change default scope constant.
Red: `test_write_payload_bytes_default_uses_owner_scope_in_key` — key prefix assertion fails.

---

## Live observation (AC-0417 goal-based)

The `ced-ingest observe --out notes/sec-access.json` command is implemented and
the observation module is fully unit-tested above. The command-produced record
is created by the controller's live run (T5). This ledger entry is a placeholder
for the controller to record: planned/started counts, per-attempt zero retries,
minimum interval, first-to-last duration, outcome counts, blocked result, and
all-stream redaction pass/fail.

---

## T2: The pinned filing deterministically produces the linked memo and manifest

### Stub red phase — AC-0407

The stub (`# STUB: AC-0407`) was materialized at `tests/diligence/test_build_published_analysis.py`
before `src/ced/domain/diligence.py` existed. Running `pytest tests/diligence/` produced:

```
ERROR tests/diligence/test_build_published_analysis.py — ModuleNotFoundError:
No module named 'ced.domain.diligence'
```

Implementation was begun only after confirming this collection error.

### AC-0406 — XBRL extraction: concept, context, period, unit, scale, CIK, duplicate collapse

**Guard: target concept must be present.**
Mutation: replace all occurrences of
`us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` with
`us-gaap:DifferentConcept` in the fixture bytes.
Red: `test_absent_concept_raises_diligence_error` — `DiligenceError` with `"absent"` is not raised.

**Guard: current context c-18 must be present.**
Mutation: remove the `<xbrli:context id="c-18">` element from the fixture bytes.
Red: `test_absent_current_context_raises_diligence_error` — `DiligenceError` matching `"c-18"` is not raised.

**Guard: prior context c-19 must be present.**
Mutation: remove the `<xbrli:context id="c-19">` element from the fixture bytes.
Red: `test_absent_prior_context_raises_diligence_error` — `DiligenceError` matching `"c-19"` is not raised.

**Guard: c-18 period end must equal `2026-06-27`.**
Mutation: replace the first `<xbrli:endDate>2026-06-27</xbrli:endDate>` with `2026-09-27`.
Red: `test_period_mismatch_current_raises_diligence_error` — `DiligenceError` matching `"period end"` is not raised.

**Guard: c-19 period end must equal `2025-06-28`.**
Mutation: replace `<xbrli:endDate>2025-06-28</xbrli:endDate>` with `2025-09-27`.
Red: `test_period_mismatch_prior_raises_diligence_error` — `DiligenceError` matching `"period end"` is not raised.

**Guard: unit measure must be `iso4217:USD`.**
Mutation: replace `<xbrli:measure>iso4217:USD</xbrli:measure>` with `iso4217:EUR`.
Red: `test_unit_mismatch_raises_diligence_error` — `DiligenceError` matching `"iso4217:USD"` is not raised.

**Guard: scale attribute must be `6`.**
Mutation: replace `scale="6"` with `scale="7"` globally.
Red: `test_scale_mismatch_raises_diligence_error` — `DiligenceError` matching `"scale"` is not raised.

**Guard: identical duplicates collapse to one fact per context; conflicting values raise.**
Mutation (conflict): change `id="f-381"` fact value from `109,417` to `108,000`.
Red: `test_conflicting_duplicates_raises_diligence_error` — `DiligenceError` matching `"conflicting"` is not raised.

**Guard: identical duplicates collapse; exactly two facts survive.**
Mutation: treat each `id` tag as a distinct fact (no collapse).
Red: `test_identical_duplicates_collapse_to_two_facts` — `len(facts) != 2`.

**Guard: CIK must equal `0000320193` under `http://www.sec.gov/CIK`.**
Mutation: replace `>0000320193<` with `>0000000001<`.
Red: `test_cik_mismatch_raises_diligence_error` — `DiligenceError` matching `"CIK"` is not raised.

**Guard: stable fragment selection — lexically smallest element id among identical duplicates.**
Fixture c-18 carries ids `f-56`, `f-381`, `f-731`; lexically smallest is `f-381`.
Fixture c-19 carries ids `f-57`, `f-382`, `f-760`; lexically smallest is `f-382`.
Mutation: select the first-seen id instead of the minimum.
Red: `test_stable_fragment_selection_among_identical_duplicates` — `source_fragment` assertions fail
(`"#f-381"` and `"#f-382"` expected).

### AC-0407 — Calculation lineage: value, rounding, operation, input fact refs

**Guard: calculated value equals `Decimal("16.36")`.**
Mutation (ROUND_DOWN): replace `ROUND_HALF_UP` with `ROUND_DOWN`.
Red: `test_the_canonical_filing_builds_the_linked_net_sales_claim` — `calculation.value` equals
`Decimal("16.35")` not `Decimal("16.36")`.

**Guard: operation field is `"year_over_year_percent_change"`.**
Mutation: set `operation = "pct_change"`.
Red: `test_calculation_has_correct_operation` — string equality fails.

**Guard: `input_fact_refs` names both extracted facts.**
Mutation: record only the current fact id.
Red: `test_calculation_lineage_records_both_fact_refs` — set equality fails.

**Guard: numerator and denominator are `Decimal`, not `float`.**
Mutation: convert to `float` before storing.
Red: `test_calculation_records_correct_numerator_and_denominator` — `isinstance(calc.numerator, Decimal)` fails.

**Guard: rounding_rule is `"ROUND_HALF_UP"` and output_scale is `2`.**
Mutation: omit `rounding_rule` from the `Calculation` dataclass.
Red: `test_calculation_rounding_rule_and_output_scale` — `AttributeError` or wrong value.

**Guard: claim evidence_refs resolves to the calculation id.**
Mutation: leave `evidence_refs` as `()`.
Red: `test_the_canonical_filing_builds_the_linked_net_sales_claim` — `evidence_refs` tuple assertion fails.

**Guard: `unresolved_claim_ids()` returns `()` on a fully linked artifact.**
Mutation: omit the `claim_links` entry.
Red: `test_the_canonical_filing_builds_the_linked_net_sales_claim` — `unresolved_claim_ids() != ()`.

### AC-0408 — No model call; fixed memo sentence

**Guard: `BedrockConverseModel.__init__` is never called.**
Mutation: construct `BedrockConverseModel` inside `build_published_analysis`.
Red: `test_no_model_adapter_constructed` — `AssertionError` from the monkeypatched init fires,
which is the expected mechanism; if the guard is absent the function raises before reaching the
result assertion.

**Guard: memo text does not derive from filing HTML prose.**
Mutation: derive `_MEMO_SENTENCE` from filing HTML rather than a fixed constant.
Red: `test_distinctive_non_fact_string_not_in_memo` — the canary string
`DILIGENCE_CANARY_XQZ987654` injected into a non-fact section would appear in the memo text.

**Guard: exactly one claim with the approved sentence.**
Mutation: emit zero claims or two claims.
Red: `test_memo_has_exactly_one_factual_claim` — `len(claims) != 1` or text equality fails.

### AC-0409 — Exhaustive lineage validator refuses serialisation on any gap

**Guard: empty `evidence_refs` is detected.**
Mutation: skip the `not claim.evidence_refs` check in `unresolved_claim_ids`.
Red: `test_empty_evidence_refs_makes_claim_unresolved` — claim does not appear in the returned
tuple; `canonical_bytes` does not raise.

**Guard: missing `claim_link` is detected.**
Mutation: skip the `cid not in link_by_claim` check.
Red: `test_missing_claim_link_makes_claim_unresolved` — claim resolves despite no link present.

**Guard: dangling `calculation_ref` is detected.**
Mutation: skip the `link.calculation_ref not in calc_by_id` check.
Red: `test_dangling_calculation_ref_makes_claim_unresolved` — claim resolves to a nonexistent calculation.

**Guard: dangling `input_fact_ref` is detected.**
Mutation: skip the `fref not in fact_by_id` check.
Red: `test_dangling_input_fact_ref_makes_claim_unresolved` — claim resolves against missing facts.

**Guard: missing source is detected.**
Mutation: skip the `fact.source_id not in source_by_id` check.
Red: `test_missing_source_makes_claim_unresolved` — claim resolves against a missing source.

**Guard: empty `source_fragment` is detected.**
Mutation: skip the `not fact.source_fragment` check.
Red: `test_empty_source_fragment_makes_claim_unresolved` — empty fragment goes undetected.

### AC-0410 — Canonical byte stability and input sensitivity

**Guard: two builds from identical inputs produce identical bytes.**
Mutation: include `datetime.utcnow()` or `uuid.uuid4()` in the artifact.
Red: `test_canonical_bytes_are_deterministic` — `b1 != b2`.

**Guard: changing `filing_sha256` changes canonical output.**
Mutation: exclude `filing_sha256` from `EvidenceSource`.
Red: `test_different_filing_sha256_produces_different_bytes` — `b1 == b2` even with a different digest.

**Guard: changing `as_of_date` changes canonical output.**
Mutation: exclude `as_of_date` from serialisation.
Red: `test_different_as_of_date_produces_different_bytes` — `b1 == b2`.

**Guard: changing `source_url` changes canonical output.**
Mutation: exclude `source_url` from `EvidenceSource`.
Red: `test_different_source_url_produces_different_bytes` — `b1 == b2`.

**Guard: `canonical_bytes → parse_published_analysis` round-trips losslessly.**
Mutation: drop a field during serialisation.
Red: `test_canonical_bytes_round_trip` — second call to `canonical_bytes(restored)` produces different bytes.

**Guard: wrong `schema_version` is rejected at parse time.**
Mutation: accept any schema_version string.
Red: `test_parse_published_analysis_rejects_wrong_schema_version` — `DiligenceError` matching
`"schema_version"` is not raised.

**Guard: non-UTF-8 bytes are rejected at parse time.**
Mutation: decode with `errors="replace"` instead of raising.
Red: `test_parse_published_analysis_rejects_non_utf8` — `DiligenceError` matching `"UTF-8"` is not raised.

### T2 controller correction — the memo sentence follows its evidence (AC-0408)

The first T2 build carried the approved sentence as a fixed string, so changed
facts would still publish 16.36%. The sentence is now rendered from the Decimal
result and the scale-6 input facts, and a non-increase refuses.

| Check | Mutation | Observed |
| --- | --- | --- |
| `test_memo_sentence_is_rendered_from_the_calculated_values` | sentence restored to the fixed string | red |
| `test_a_non_increase_has_no_approved_sentence` | sentence restored to the fixed string | red |

---

## T3: An analysis-class worker publishes the deterministic artifact under the lease fence

### AC-0412 — Request pinning: pool_class and payload_ref stored atomically

**Guard: step row carries pool_class='analysis'.**
Mutation: omit `pool_class` from the `INSERT INTO steps` statement in `start_run`.
Red: `test_start_run_stores_pool_class_and_payload_ref` — `pool_class` assertion reads `'default'` or NULL.

**Guard: run.requested event carries payload_ref.**
Mutation: pass `None` instead of `payload_ref` to `append_run_event` in `start_run`.
Red: `test_start_run_stores_pool_class_and_payload_ref` — `events[0].payload_ref` is `None`.

**Guard: database failure leaves no run with dangling payload_ref.**
Mutation: separate the step INSERT from the run INSERT with individual commits.
Red: `test_database_failure_leaves_no_run_with_dangling_payload_ref` — `_counts` returns `(1, 0, 0)` (run row committed, no step or event).

### AC-0413 — Analysis body: event ordering, artifact, and failure paths

**Guard: event sequence is run.requested → step.started → step.completed → run.completed.**
Mutation: remove the `step.started` append from `_analysis_body`.
Red: `test_analysis_body_commits_ordered_events_and_artifact` — expected list has four types; actual list has three (step.started absent).

Mutation: swap the `step.completed` and `run.completed` appends.
Red: same test — list order assertion fails.

**Guard: artifact stored under ANALYSIS_SCOPE.**
Mutation: use OWNER_SCOPE as the scope for `write_payload_bytes(artifact_bytes, ...)`.
Red: `test_analysis_artifact_resolves_by_digest` — `artifact_ref.startswith(ANALYSIS_SCOPE + "/")` fails.

**Guard: artifact digest matches the key.**
Mutation: write `b""` as the artifact bytes.
Red: `test_analysis_artifact_resolves_by_digest` — SHA-256 of empty bytes disagrees with the hex in the key.

**Guard: step.completed and run.completed share the artifact reference.**
Mutation: pass different refs to the two appends.
Red: `test_step_completed_and_run_completed_carry_same_artifact_ref` — equality assertion fails.

**Guard: snapshot digest mismatch triggers step.failed + run.failed.**
Mutation: remove the `snapshot_sha256 != expected_snapshot_sha256` check.
Red: `test_snapshot_digest_mismatch_produces_failed_events` — the body proceeds past a corrupted snapshot and either raises an unhandled parse error or appends run.completed instead of run.failed.

**Guard: filing digest mismatch (vs key) triggers step.failed + run.failed.**
Mutation: remove the `filing_sha256 != expected_filing_key_sha256` check.
Red: `test_filing_digest_mismatch_against_key_produces_failed_events` — the body proceeds past corrupted filing bytes.

**Guard: manifest CIK mismatch triggers step.failed + run.failed.**
Mutation: remove the `manifest.get("cik") != cik` check.
Red: `test_manifest_cik_mismatch_produces_failed_events` — `build_published_analysis` runs against mismatched CIK and either raises or produces an artifact for the wrong company.

**Guard: DiligenceError from build_published_analysis maps to step.failed + run.failed.**
Mutation: swallow the exception and return without appending failure events.
Red: `test_domain_error_produces_failed_events` — run stays non-terminal (no run.failed).

**Guard: object-store failure during artifact write maps to step.failed + run.failed.**
Mutation: swallow the write exception.
Red: `test_artifact_store_failure_produces_failed_events` — run stays non-terminal.

**Guard: analysis step not claimable by default-class worker.**
Mutation: remove the `pool_class = %s` predicate from `claim_one`.
Red: `test_analysis_step_is_not_claimable_by_default_class_worker` — claim_one returns the analysis step for a default-class config.

### AC-0416 preparation — pool class partition

**Guard: start_run stores the supplied pool_class.**
Mutation: omit pool_class from start_run's step INSERT.
Red: `test_analysis_step_pool_class_is_stored` — pool_class reads 'default'.

**Guard: default-class worker does not claim analysis steps.**
Mutation: remove pool_class predicate from claim_one.
Red: `test_default_class_worker_does_not_claim_analysis_step` — default-class worker claims the analysis step.

### AC-0418 — Object-store readiness: sentinel written and verified before poll

**Guard: ensure_readiness writes the sentinel and calls HeadObject.**
Mutation: remove the `head_object(key)` call from `ensure_readiness`.
Red: `test_ensure_readiness_writes_and_heads_sentinel` — no error raised when the head call is absent, but the test also calls `head_object` directly; the real test for the guard is `test_readiness_head_failure_prevents_poll`.

**Guard: HeadObject failure propagates from ensure_readiness.**
Mutation: catch `ClientError` in `ensure_readiness` and continue.
Red: `test_readiness_head_failure_prevents_poll` — no exception raised; the poll loop would start with an unverified sentinel.

**Guard: put failure propagates from ensure_readiness.**
Mutation: catch write failures in `ensure_readiness` and continue.
Red: `test_readiness_put_failure_prevents_poll` — no exception raised.

**Guard: ensure_readiness is called before run_forever.**
Mutation: move the `ensure_readiness()` call inside `Worker.run_forever`.
Red: `test_pool_run_dispatches_readiness_before_poll` — `call_log` shows `["run_forever", "readiness"]` instead of `["readiness", "run_forever"]`.

**Guard: bucket-ensure failure propagates from pool.run() before run_forever.**
Mutation: catch `ClientError` from `_ensure_bucket` inside `ensure_readiness` and continue.
Red: `test_pool_run_propagates_bucket_ensure_failure` — no exception propagates from `pool.run()`; the seeded step would be claimed by `run_forever`.

**Guard: put failure propagates from pool.run() before run_forever.**
Mutation: catch the put `ClientError` inside `ensure_readiness` and continue.
Red: `test_pool_run_propagates_put_failure` — no exception propagates; the step state advances past `runnable`.

**Guard: HeadObject failure propagates from pool.run() before run_forever.**
Mutation: catch `ClientError` from `head_object` inside `ensure_readiness` and continue.
Red: `test_pool_run_propagates_head_failure` — no exception propagates; the step state advances past `runnable`.

### Role dispatch and termination

**Guard: unexpected agent_role commits step.started then appends fenced failure.**
Mutation: remove the `lease.agent_role != ANALYSIS_ROLE` check.
Red: `test_unexpected_role_produces_failed_events` — `step.failed` and `run.failed` are absent; the body attempts Phase 3 with the wrong role.

**Guard: BedrockConverseModel is never constructed by the analysis body.**
Mutation: construct `BedrockConverseModel` inside `_analysis_body`.
Red: `test_model_executor_not_constructed_for_analysis_role` — the patched `__init__` fires `AssertionError`; the body raises instead of completing.

**Guard: missing payload_ref commits step.started then appends fenced failure.**
Mutation: restore the silent-return path for missing `payload_ref`.
Red: `test_missing_payload_ref_produces_failed_events` — `step.failed` and `run.failed` are absent; the run is left in the `requested` state (non-terminal).

### Filing digest vs manifest

**Guard: manifest filing_sha256 mismatch triggers step.failed + run.failed.**
Mutation: remove the `filing_sha256 != manifest_filing_sha256` check.
Red: `test_filing_digest_mismatch_against_manifest_produces_failed_events` — the body passes the tampered lineage field to `build_published_analysis` without refusing it.

### Fence and ordering mutations

**Guard: Phase 4 completion appends are fenced on lease_epoch.**
Mutation: omit `lease_epoch` from the `append_step_event` call in Phase 4, or pass a stale epoch.
Red: `test_stale_epoch_on_phase4_append_leaves_run_nonterminal` — the injected `Fenced` exception (simulating a stale epoch) must leave `step.completed` absent from events; without the fence argument the DB procedure commits regardless of epoch and the test passes even with a stale epoch, making the guard invisible.

**Guard: step.completed is appended before run.completed.**
Mutation: swap the `append_step_event("step.completed")` and `append_run_terminal("run.completed")` calls in Phase 4.
Red: `test_analysis_body_commits_ordered_events_and_artifact` — the exact-order assertion `["run.requested", "step.started", "step.completed", "run.completed"]` fails with the two terminal events swapped.

**Guard: artifact is written before the completion appends.**
Mutation: move `artifact_ref = write_payload_bytes(...)` to after the `append_step_event("step.completed")` call in Phase 4.
Red: `test_artifact_store_failure_produces_failed_events` — with the write moved outside Phase 3's try block, a patched `write_payload_bytes` failure fires after `step.completed` is committed; the body propagates without calling `_append_failure`, so events include `step.completed` and `run.completed` — but the test asserts both are absent.
