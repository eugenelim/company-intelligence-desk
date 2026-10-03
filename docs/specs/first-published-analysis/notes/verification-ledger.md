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
