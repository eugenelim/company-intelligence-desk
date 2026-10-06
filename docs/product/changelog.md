# Changelog

Document notable user-visible changes to this project here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project may follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
when that matches its release model.

> Maintenance: add a `## [<artifact>][<version>] — YYYY-MM-DD` section in the
> same change that bumps a released artifact's version. Keep released entries
> newest-first and write them for users rather than contributors.

<!-- Example entry (replace with your first real version):

## [pack-name][version] — YYYY-MM-DD

### Added / Changed / Fixed

- Describe the user-visible change.

-->

## [Unreleased]

### Added

- The first published analysis. `ced-ingest` stores one SEC filing snapshot,
  and `POST /runs` with the `first-published-analysis` role turns it into a
  memo with an evidence manifest, read from `GET /runs/{run_id}/analysis`. The
  memo reports Apple Inc.'s quarterly net sales change year over year, as of
  2026-07-31. Every figure links back to the filing's XBRL facts. No model is
  called. The same snapshot bytes and request always produce byte-identical
  memo and manifest JSON.
- Its limits: it covers one company, one filing and one calculation; it is
  read through the API only; and any caller who can reach the API and knows a
  run id can read the result. See
  [`docs/guides/how-to/publish-first-analysis.md`](../guides/how-to/publish-first-analysis.md).
