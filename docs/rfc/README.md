# Requests For Comments

> Proposals for change. See
> [`../CONVENTIONS.md`](../CONVENTIONS.md#3-rfc--request-for-comments--docsrfc)
> for when to open an RFC vs. an ADR vs. just opening a PR.

| #    | Title | Status | Opened     | Closed |
| ---- | ----- | ------ | ---------- | ------ |
| 0001 | [Initial Project Charter — Company Intelligence Desk](0001-initial-project-charter.md) | Accepted | 2026-09-09 | 2026-09-10 |

## Adding a new RFC

```bash
# Find the next number (portable across macOS, Linux, native Windows).
# Point SKILL at wherever your agent installed the `new-rfc` skill.
SKILL=<path to the installed new-rfc skill>
N=$(python3 "$SKILL/scripts/next-ordinal.py" docs/rfc)
cp "$SKILL/assets/rfc.md" "docs/rfc/${N}-<kebab-title>.md"
```

Or invoke the `new-rfc` skill by name in your agent.
