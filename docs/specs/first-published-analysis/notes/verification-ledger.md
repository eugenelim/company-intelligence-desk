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
Mutation: remove the `_validate_submissions_cik` call. Red:
`test_run_ingest_from_bytes_refuses_wrong_submissions_cik` and the live-path
`test_a_live_metadata_refusal_makes_no_filing_request_and_no_write[other-company-cik]`.
The first version of this entry named a check inside `_select_filing` that
did not exist; review round 1 found that, and the guard now exists and has
been proven.

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

The `ced-ingest observe --out notes/sec-access.json` command is unit-tested
above. Its live run and redaction proof are recorded in
[§ T5 — AC-0417](#t5--ac-0417-the-live-sec-access-observation-2026-10-04).

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

---

## T4: The REST contract starts and reads a complete analysis without breaking existing runs

### AC-0411 — POST /runs validates the analysis object

**Guard: analysis object required for first-published-analysis role.**
Mutation: remove the `if request.analysis is None` check.
Red: `test_start_run_analysis_role_without_analysis_object_is_422` — 422 is not returned; 200 returned instead.

**Guard: analysis object forbidden for other roles.**
Mutation: remove the `elif request.analysis is not None` check.
Red: `test_start_run_non_analysis_role_with_analysis_object_is_422` — 422 is not returned.

**Guard: extra fields in analysis object are rejected.**
Mutation: remove `model_config = ConfigDict(extra="forbid")` from `AnalysisRequest`.
Red: `test_start_run_analysis_unknown_field_is_422` — 422 is not returned; extra field silently ignored.

**Guard: unsupported CIK is rejected.**
Mutation: remove the `ana.cik != _CANONICAL_CIK` check.
Red: `test_start_run_analysis_unsupported_cik_is_422` — 422 not returned for `"0000000001"`.

**Guard: unsupported as_of_date is rejected.**
Mutation: remove the `ana.as_of_date != _CANONICAL_AS_OF` check.
Red: `test_start_run_analysis_unsupported_as_of_date_is_422` — 422 not returned for `"2025-01-01"`.

**Guard: snapshot_ref pattern refuses wrong scope prefix.**
Mutation: drop the `_SNAPSHOT_REF_RE.fullmatch` call or change the pattern.
Red: `test_start_run_analysis_wrong_scope_in_snapshot_ref_is_422` — a ref with prefix `ced-other-scope/…` is accepted.

**Guard: snapshot_ref pattern refuses uppercase hex.**
Mutation: change `[0-9a-f]` to `[0-9a-fA-F]` in the compiled regex.
Red: `test_start_run_analysis_uppercase_hex_in_snapshot_ref_is_422` — uppercase-hex ref accepted.

**Guard: snapshot_ref pattern refuses overlong hex.**
Mutation: change `{64}` to `{1,}` in the compiled regex.
Red: `test_start_run_analysis_overlong_hex_in_snapshot_ref_is_422` — hex of length 65 accepted.

**Guard: fullmatch rejects trailing newline.**
Mutation: use `_SNAPSHOT_REF_RE.match(…)` instead of `_SNAPSHOT_REF_RE.fullmatch(…)`.
Red: `test_start_run_analysis_trailing_newline_in_snapshot_ref_is_422` — a ref with `\n` appended is accepted because `$` in Python matches before a trailing newline.

**Guard: missing snapshot key returns 422.**
Mutation: remove the `ObjectNotFoundError` catch or map it to 200.
Red: `test_start_run_analysis_missing_snapshot_is_422` (substrate) — 422 not returned for a nonexistent key.

**Guard: object store unavailable returns 503.**
Mutation: map `ObjectStoreError` to 422 instead of 503.
Red: `test_start_run_analysis_store_unavailable_is_503` (substrate) — 503 not returned when MinIO is unreachable.

### AC-0414 — GET /runs/{run_id}/analysis validates and returns artifact

**Guard: unknown run returns 404.**
Mutation: remove `_require_run` check.
Red: `test_read_analysis_unknown_run_is_404` — 409 returned instead of 404 (no events found, terminal is None, `_require_run` guards this path).

**Guard: pending run returns 409.**
Mutation: remove the `terminal is None` check.
Red: `test_read_analysis_pending_run_is_409` — 200 attempted on a run with no terminal event.

**Guard: failed run returns 409.**
Mutation: remove the `terminal.type != "run.completed"` check.
Red: `test_read_analysis_failed_run_is_409` — failed run returns 200 or proceeds to artifact read.

**Guard: non-analysis run returns 409.**
Mutation: remove the `terminal.agent_role != ANALYSIS_ROLE` check.
Red: `test_read_analysis_non_analysis_run_is_409` — a completed default-role run returns 200.

**Guard: missing artifact ref returns 409.**
Mutation: remove the `terminal.payload_ref is None` check.
Red: `test_read_analysis_missing_artifact_ref_is_409` — None ref passed to `read_payload_bytes`, raising AttributeError.

**Guard: missing artifact object returns 409.**
Mutation: remove the `except Exception` block around `read_payload_bytes`.
Red: `test_read_analysis_missing_artifact_is_409` — ClientError propagates as 500.

**Guard: digest mismatch returns 409.**
Mutation: remove the SHA-256 comparison.
Red: `test_read_analysis_digest_mismatch_is_409` — bytes with wrong digest returned as 200.

**Guard: invalid JSON bytes return 409.**
Mutation: remove the `except Exception` block around `json.loads`.
Red: `test_read_analysis_invalid_json_is_409` — json.JSONDecodeError propagates as 500.

**Guard: schema-invalid artifact returns 409.**
Mutation: remove the `parse_published_analysis` call.
Red: `test_read_analysis_schema_invalid_artifact_is_409` — schema-invalid JSON returned as 200.

### AC-0415 — No identity header required to read analysis

**Guard: no Authorization header is needed.**
Mutation: add `Authorization: Header` to the `read_analysis` signature.
Red: `test_read_analysis_requires_no_identity_header` — 422 returned for request without header.

**Guard: response omits initiating-principal values.**
Mutation: include `run.requested` event's payload in the response.
Red: `test_read_analysis_response_omits_principal_values` — principal value appears in response body.

### AC-0416 partial — HTTP API start and read e2e

**Guard: POST /runs with analysis creates a step with analysis role.**
Mutation: remove `agent_role` from the run row or pass wrong role.
Red: `test_http_api_start_run_creates_analysis_run` — `agent_role` in the step row does not equal `first-published-analysis`.

**Guard: GET /runs/{run_id}/analysis returns complete artifact after worker completes.**
Mutation: remove the `parse_published_analysis` call in `read_analysis`.
Red: `test_http_api_read_analysis_returns_complete_artifact` — response returns unvalidated bytes that may not conform to the schema.

### Contract agreement

**Guard: read_analysis operation is in the committed YAML.**
Mutation: remove `GET /runs/{run_id}/analysis` from `runs.yaml`.
Red: `test_the_contract_file_includes_the_analysis_operation` — assertion fires immediately (offline).

**Guard: POST /runs has 503 in the committed YAML.**
Mutation: remove 503 from `runs.yaml` POST /runs responses.
Red: `test_the_contract_file_includes_503_on_start_run` — assertion fires immediately (offline).

**Guard: read_analysis carries x-spec link.**
Mutation: remove `x-spec` from the GET /runs/{run_id}/analysis entry.
Red: `test_the_analysis_operation_carries_an_x_spec_link` — assertion fires immediately (offline).

**Guard: StartRunRequest schema includes analysis field.**
Mutation: remove `analysis` from the `StartRunRequest` schema.
Red: `test_the_start_run_schema_includes_the_analysis_field` — assertion fires immediately (offline).

**Guard: AnalysisRequest schema is documented.**
Mutation: remove `AnalysisRequest` from `components/schemas`.
Red: `test_the_analysis_request_schema_is_documented` — assertion fires immediately (offline).

**Guard: route table comparison detects removed analysis operation.**
Mutation: remove `GET /runs/{run_id}/analysis` from `runs.yaml`.
Red: `test_the_comparison_notices_a_removed_analysis_operation` — assertion fires (substrate).

**Guard: route table comparison detects removed 503.**
Mutation: remove 503 from POST /runs responses in `runs.yaml`.
Red: `test_the_comparison_notices_a_removed_503_on_start_run` — assertion fires (substrate).

**Guard: route table comparison detects renamed operationId.**
Mutation: rename `operationId` on GET /runs/{run_id}/analysis in `runs.yaml`.
Red: `test_the_comparison_notices_a_renamed_analysis_operation_id` — assertion fires (substrate).

### AC-0411 object-store cases (substrate, tests/api/test_start_and_read_a_run.py)

**Guard: request object stores exactly {cik, as_of_date, snapshot_ref}.**
Mutation: write the request object with additional keys (e.g., `principal`).
Red: `test_positive_control_request_object_has_three_keys` — set equality on `stored.keys()` fails.

**Guard: missing snapshot object returns 422, detail-free, no run created.**
Mutation: remove the `ObjectNotFoundError` catch or map it to 200.
Red: `test_absent_snapshot_returns_422_detail_free` — status is not 422, or the runs count increases.

**Guard: digest mismatch returns 422, no run created.**
Mutation: remove the `hashlib.sha256(snapshot_bytes).hexdigest() != expected_sha256` check.
Red: `test_digest_mismatch_returns_422` — the route proceeds with bytes whose digest disagrees with the key hex; status is not 422.

**Guard: manifest cik mismatch returns 422.**
Mutation: remove the `manifest["cik"] == cik` check from `_is_snapshot_manifest`.
Red: `test_manifest_mismatch_wrong_cik_returns_422` — a manifest with cik `0000000001` is accepted.

**Guard: manifest as_of_date mismatch returns 422.**
Mutation: remove the `manifest["as_of_date"] == as_of_date` check.
Red: `test_manifest_mismatch_wrong_as_of_date_returns_422` — a manifest with a wrong date is accepted.

**Guard: non-JSON bytes at snapshot_ref return 422.**
Mutation: use `json.loads` directly without catching the JSONDecodeError, mapping it to 500.
Red: `test_manifest_mismatch_filing_bytes_as_snapshot_ref_returns_422` — raw bytes cause a 500 instead of 422.

**Guard: request-object-shaped JSON (three keys) fails the exact-key-set check.**
Mutation: change `set(manifest) != _MANIFEST_KEYS` to `not _MANIFEST_KEYS.issubset(manifest)`.
Red: `test_manifest_mismatch_request_object_shaped_json_returns_422` — a three-key object passes the weakened check and a run is created.

**Guard: extra key in manifest fails the exact-key-set check.**
Mutation: change `set(manifest) != _MANIFEST_KEYS` to a subset check.
Red: `test_manifest_mismatch_extra_key_returns_422` — a twelve-key manifest is accepted.

**Guard: missing key in manifest fails the exact-key-set check.**
Mutation: change `set(manifest) != _MANIFEST_KEYS` to a superset check.
Red: `test_manifest_mismatch_missing_key_returns_422` — a ten-key manifest is accepted.

**Guard: ObjectStoreError on snapshot read returns detail-free 503.**
Mutation: remove the `ObjectStoreError` catch or map it to 422.
Red: `test_store_unavailable_on_snapshot_read_returns_503_detail_free` — status is not 503, or no log record with `snapshot_store_unavailable`.

**Guard: write_payload failure for the request object returns 503.**
Mutation: remove the `except Exception` block around `write_payload`.
Red: `test_request_object_write_failure_returns_503` — the exception propagates as 500 instead of 503.

### T4 controller notes

- `src/ced/adapters/objectstore/client.py` is outside T4's `Touches` (it is in
  T1's and T3's). T4 added `ObjectNotFoundError`, `ObjectStoreError` and
  `read_payload_bytes_checked` there because
  `tests/architecture/test_dependency_direction.py` forbids AWS SDK imports in
  `ced.api`. The adapter is the layer that owns that translation.
- The request object is written under the default `ced-step-lifecycle` scope.
  Under the snapshot scope, a request reference matched the snapshot-reference
  pattern and carried a matching CIK and as-of date.
- `_is_snapshot_manifest` reduced to its former CIK and as-of check reds three
  checks in `tests/api/test_start_and_read_a_run.py`: the filing-key,
  request-shaped and extra/missing-key cases.

## T5 — AC-0416: the real local flow on a clean substrate (2026-10-04)

Run from a wiped volume (`docker-compose -f deploy/compose.yaml down -v`),
then `up -d --build postgres minio`, `alembic upgrade head` (exit 0), and
`up -d --build worker-analysis`. No test helper, direct event append or
in-process worker took part.

| Step | Command | Result |
| --- | --- | --- |
| Ingest | `ced-ingest --offline-fixture` | exit 0; `snapshot_ref` `ced-first-published-analysis-snapshot/b8caf66f…2560c7`; filing digest `23e47d33…2316f1` |
| Start | `POST /runs` with role `first-published-analysis` and the `analysis` object | `201`; one run and one step |
| Publish | Compose `worker-analysis` (pool class `analysis`) | events `run.requested`, `step.started`, `step.completed`, `run.completed` |
| Read | `GET /runs/{run_id}/analysis` | `200` about 10 s after the start |
| Unknown run | `GET /runs/<zero uuid>/analysis` | `404` |

What the read returned:

- The memo's one claim reads: "Quarterly net sales increased 16.36% year over
  year, from USD 94.036 billion to USD 109.417 billion."
- The calculation is `16.36` percent, `ROUND_HALF_UP`, output scale 2, with
  numerator `15381` and denominator `94036`. Its inputs are facts `c-18`
  (`109417`, period ending 2026-06-27) and `c-19` (`94036`, period ending
  2025-06-28), both USD at scale 6.
- Each fact resolves to the archived source
  `https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm`
  at fragments `#f-381` and `#f-382`. Re-parsing the response leaves
  `unresolved_claim_ids()` empty.
- The response bytes hash to `72329a90…5450b1a`, which is the digest in the
  `run.completed` payload reference.
- The initiating principal is absent from the response.

### T5 controller correction — the observation keeps its spacing and its records (AC-0417)

Found while reading the observation command before its live run:

- **Slow responses bunched later starts.** Each start was scheduled from a
  fixed origin. One response slower than 1 s let the following starts catch
  up early, which broke the 1 s minimum, so a slow SEC response would have
  failed the observation. Each start now also waits at least one interval
  after the previous start.
- **Failed attempts lost their gate wait.** A blocked or failed attempt was
  re-recorded with `gate_wait_seconds=0.0`. `fetch_url` now attaches its own
  record to the error, and the observation keeps it.
- **Refusals looked like success.** Over-cap and malformed-length refusals
  left `stop_condition` at `success`. They now record `refused`.

| Check | Mutation | Observed |
| --- | --- | --- |
| `test_a_slow_response_delays_later_starts_instead_of_bunching_them` | previous-start floor dropped | red |
| `test_a_blocked_attempt_keeps_its_real_gate_wait` | blocked record rebuilt with zero gate wait | red |
| `test_an_over_cap_attempt_is_recorded_as_refused` | `refused` fallback dropped | red |

### T5 — the how-to guide, run as written (2026-10-04)

Every command in `docs/guides/how-to/publish-first-analysis.md` was pasted in
order on a wiped volume, and each one exited 0. The `POST /runs` returned
`201`. `GET /runs/{run_id}/analysis` returned `200` within 20 s with the
approved memo sentence. Clean-up (`down -v`, `rm snapshot.json`) left no
file behind.

This second ingestion stored a different snapshot reference (`d31fc9ef…`),
because its retrieval time differed. The artifact it produced was still
byte-identical to the first run's (`72329a90…`). Retrieval time does not enter
the published bytes, as AC-0410 requires.

Every local link in the guide was opened and resolves:
`contracts/openapi/runs.yaml`,
`docs/architecture/pydantic-ai-worker-runtime/operations.md#sec-acquisition`
and `docs/specs/first-published-analysis/spec.md`.

## T5 — AC-0417: the live SEC access observation (2026-10-04)

The command ran once:
`SEC_CONTACT=<runtime value> ced-ingest observe --out docs/specs/first-published-analysis/notes/sec-access.json`.
It exited 0, and `notes/sec-access.json` is its unedited output. It made 60
requests to `data.sec.gov` for the submissions document, through the
Postgres request gate.

| Field | Value |
| --- | --- |
| Planned / started attempts | 60 / 60 |
| Target / minimum observed start interval | 1.0 s / 1.00009 s |
| First-to-last start | 59.26 s |
| Outcomes | 60 `success`, all `2xx` |
| Retries | 0 on every attempt |
| `blocked` | `false` |
| Largest gate wait / largest request duration | 0.47 s / 0.21 s |

What this does not establish: 60 seconds at one request a second says nothing
about sustained or fleet-wide access. The record's `statement` field says the
same.

Redaction proof: the full runtime value, its email address, and that
address's local part and domain were compared byte-for-byte with the record,
captured stdout, captured stderr, every tracked or untracked file in the
working tree, and the full patch history of every branch. None matched. The
captures and the runtime value's file were then deleted. The value's other
words also occur in the repository's own text, such as the project name, so
they cannot discriminate.

## Review round 1 repairs

### Finding 8 — an unreadable principal no longer reads as a completed step

`_analysis_body` now raises `_AnalysisBodyFailed` when the run's principal
cannot be read, so the pool records the step as `failed`. The run stays
non-terminal, because no event can be built without a principal.
`docs/architecture/README.md` now says so rather than claiming every failed
analysis run is terminal.

| Check | Mutation | Observed |
| --- | --- | --- |
| `test_an_unreadable_principal_makes_the_pool_record_failure` | `return` instead of raising | red |

### Finding 10 — the schema-status table matches migration 0002

Migration 0002 adds the `tool.invoked` idempotency index,
`steps.pool_class` and `owner_scope`. The last two are both
`NOT NULL DEFAULT 'default'`. All three rows now read **Built** with that
shape.

### Finding 1 — every filing value in the artifact has a closed shape (AC-0406, AC-0408, AC-0409)

`ced.domain.diligence` now refuses each of the following before publication:

- a fact without an `id`;
- a fact `id` outside `[A-Za-z_][A-Za-z0-9_.-]{0,127}`;
- a fact `id` that is not unique in the filing;
- a `sign` attribute;
- a `format` other than `ixt:num-dot-decimal`;
- a display value that is anything but digits and commas;
- a context `startDate` that is not an ISO date or is not the expected
  quarter start (`2026-03-29` or `2025-03-30`);
- a context carrying a segment, since such a context is not consolidated.

Period dates are serialized from the parsed date, never from the raw text. The
lineage check now requires every fragment to be `#` followed by a valid id.
The canonical fixture's artifact bytes are unchanged.

| Guard removed | Red |
| --- | --- |
| fact id required | `pytest.raises(DiligenceError)` for an id-less fact |
| fact id pattern | id `0invalid` accepted |
| fact id unique | duplicate id accepted |
| `sign` refused | `sign="-"` accepted |
| `format` checked | wrong and missing `format` accepted |
| start date parsed | `26-03-29` stored as the period start |
| start date value | `2026-03-30` accepted |
| segment refused | segmented context accepted |
| digits-only value | `109e3` accepted, giving 15.9% |
| fragment shape | `#` passes `unresolved_claim_ids()` |

The controller re-ran the `sign` and segment mutations, and each produced one
red.

### Findings 2, 3, 4, 6, 7, 9, 11 — ingestion and the SEC client

| Finding | Guard | Mutation | Red |
| --- | --- | --- | --- |
| 2 (AC-0405) | duplicate canonical accession refused | first-match `break` restored | `test_select_filing_refuses_duplicate_accession_entries`; live `[duplicate-accession]` case |
| 3 (AC-0401) | submissions CIK, normalised for zero padding | call removed; normalisation removed | `test_validate_submissions_cik_refuses_wrong_cik`; `test_validate_submissions_cik_accepts_short_form` |
| 3 (AC-0401) | accession filer prefix | call removed from `_run_ingest_from_bytes` | `test_run_ingest_from_bytes_refuses_misplaced_dash_accession`. `test_validate_accession_filer_prefix_refuses_wrong_prefix` pins the helper alone and stays green under this mutation |
| 3 (AC-0401) | live refusal makes one request and no write | CIK check or duplicate check removed | `test_a_live_metadata_refusal_makes_no_filing_request_and_no_write` (controller-run) |
| 4 (AC-0404) | snapshot bytes re-hashed on read-back | snapshot digest check removed | `test_round_trip_digest_check_fails_on_tampered_snapshot_manifest` |
| 4 (AC-0404) | declared client absent on the live path | contact stored in the manifest | `test_contact_value_absent_from_stored_objects_via_live_ingest` |
| 4 (AC-0404) | offline path never opens Phase 0 | a Phase 0 read added | `test_offline_ingest_does_not_open_phase_0_fixture` |
| 6 (AC-0417) | TLS handshake timeout recorded | `TimeoutError` dropped from the wrap handler | `test_tls_handshake_timeout_produces_attempt_record` |
| 6 (AC-0417) | protocol errors recorded | `HTTPException` dropped from the request and read handlers | `test_http_exception_during_request_produces_attempt_record`; `…_during_body_read_…` |
| 7 | SEC refusals print one `error:` line | `SecClientError` dropped from `run()` | `test_run_catches_sec_client_error_and_writes_to_stderr` |
| 7 | live attempts printed | `attempts` key removed | `test_ingest_live_includes_attempts_in_result` |
| 9 | every `3xx` refused | explicit five-code list restored | `test_fetch_url_refuses_300_…`, `…_304_…`, `…_305_…` |
| 11 | path-free refusal without a checkout | raw `OSError` propagated | `test_offline_ingest_refuses_with_path_free_message_when_fixture_absent` |

The unused `cik` and `accession` parameters of `_validate_primary_doc`, and
`required_cik` of `_select_filing`, were removed.

### Finding 5 — the served and committed contracts agree on this slice's schemas (AC-0411, AC-0414)

The 200 response of `GET /runs/{run_id}/analysis` is now the typed
`PublishedAnalysis` model, with `extra="forbid"` throughout, on both sides.
The route still returns the stored canonical bytes. The agreement test
compares the following, served against committed:

- the read operation's `x-spec` and response set;
- the resolved 200 schema;
- `AnalysisRequest`;
- `StartRunRequest.analysis`;
- the start operation's response set;
- the 503 `x-spec`.

| Break | Red |
| --- | --- |
| analysis operation removed | `test_analysis_view_notices_removed_analysis_operation` |
| `snapshot_ref` removed from `AnalysisRequest` | `test_analysis_view_notices_removed_request_field` |
| `memo` removed from `PublishedAnalysis` | `test_analysis_view_notices_removed_artifact_property` |
| 200 or 409 removed | `…_removed_200_response`, `…_removed_409_response` |
| read `x-spec` removed | `test_analysis_view_notices_removed_x_spec` |
| `memo` dropped from the served schema | `test_analysis_view_notices_dropped_served_property` |
| `StartRunRequest.analysis` removed or made non-nullable; start 503 or its `x-spec` removed | `test_analysis_view_notices_start_run_changes` |
| committed `analysis` field written as `oneOf` rather than the served `anyOf` | served-vs-committed agreement test (controller-run) |

## Review round 2 repairs

### Finding 1 — filing guards apply to the selected facts only (AC-0406)

Round 1 placed the segment, `sign` and `format` refusals on every context and
fact in the filing. The real filing has segmented contexts such as `c-2`,
signed facts, and facts with other formats, so it was refused before `c-18`
and `c-19` were read. Those refusals now apply only to `c-18`, `c-19` and
every copy of the target-concept facts in them. The fact-id rules stay
filing-wide, because the real filing satisfies them.

Real-filing check, run by hand and not in any test: the Phase 0 copy of
accession `0000320193-26-000020` (SHA-256 `4ad5bea6…b9177`) builds `16.36`,
with the approved sentence, fragments `#f-381` and `#f-382`, and no
unresolved claim.

| Check | Mutation | Red |
| --- | --- | --- |
| `test_non_target_segment_sign_format_facts_do_not_refuse_build` | refusals back to filing-wide | `DiligenceError` on a non-target fact |
| `test_segmented_target_context_still_raises_diligence_error`, `test_target_fact_with_sign_…`, `…_wrong_format_…`, `…_missing_format_…` | target-scoped check removed | the target case is accepted |

### Finding 2 — a nested target fact is refused

Facts are tracked on a stack, so every `ix:nonFraction` keeps its own
attributes and text. A target-concept fact that contains a nested
`ix:nonFraction` is refused.

| Check | Mutation | Red |
| --- | --- | --- |
| `test_nested_nonfraction_with_target_concept_raises_diligence_error` | nesting check removed | `match="nested"` fails |

### Finding 3 — the read admits only the published 200 schema (AC-0414)

`GET /runs/{run_id}/analysis` now validates the stored bytes with the strict
`PublishedAnalysis` model, which forbids unknown keys and coerces nothing,
and requires complete claim lineage. Otherwise it returns the
`artifact_schema_invalid` `409`.

| Check | Mutation | Red |
| --- | --- | --- |
| `test_read_analysis_refuses_an_artifact_outside_the_published_schema` (four cases: top-level key, claim key, non-string ref, unresolved lineage) | lenient domain parser only | all four return 200 |

### Finding 5 — submission metadata is shape- and date-checked (AC-0405)

The following are refused before any filing request, and the manifest carries
the parsed `isoformat()`:

- a non-object document, `filings` or `recent`;
- required arrays that are not lists, are not of equal length, or hold
  non-strings;
- a selected `filingDate` or `reportDate` that is not a strict ISO date, with
  dates compared as dates;
- a `form` other than `10-Q`.

| Check | Mutation | Red |
| --- | --- | --- |
| `test_run_ingest_from_bytes_refuses_non_object_submissions`, `…_non_object_filings`, `…_non_object_recent` | `isinstance` check removed | `AttributeError` instead of `IngestionError` |
| `test_select_filing_refuses_non_list_array_field`, `…_unequal_length_arrays`, `…_non_string_array_element` | shape check removed | wrong error or `IndexError` |
| `test_select_filing_refuses_filing_date_with_leading_space`, `…_empty_filing_date`, `…_non_iso_report_date` | date parse removed | malformed date admitted |
| `test_select_filing_refuses_wrong_form` | form check removed | `10-K` admitted |
| `test_a_live_malformed_filing_date_makes_no_filing_request_and_no_write` | date parse removed | a second socket open |

### Findings 4, 7, 8 — record and message corrections

- The filer-prefix row above now cites the call-site check, with mutation
  proof from `test_run_ingest_from_bytes_refuses_misplaced_dash_accession`.
- The analysis module docstring states the unreadable-principal exception.
- The offline refusal prints one `error:` prefix. This is pinned by
  `test_offline_fixture_missing_error_has_exactly_one_error_prefix`.

### Finding 6 — connection failures get their own class (AC-0417 amendment)

**Owner decision, 2026-10-04:** the owner chose to add a `connection` class
to AC-0417's closed no-response set, through the controlled amendment route,
rather than label resets as `read_timeout`. A refused connection, a reset or
other socket error, and a garbled HTTP response are now recorded as
`connection`. The other classes are unchanged: an `ssl.SSLError` is `tls`,
and a timeout is still its timeout class.

| Check | Mutation | Red |
| --- | --- | --- |
| `test_a_refused_connection_maps_to_connection_class`, `test_a_reset_during_the_tls_handshake_maps_to_connection_class`, `test_http_exception_during_request_…`, `…_during_body_read_…` | `connection` mapped back to `read_timeout` | 4 red |
