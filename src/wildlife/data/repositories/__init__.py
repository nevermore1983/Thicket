"""SQL for each kind of record. Every repository function takes an open connection."""

# The time now, in SQL, in the form every *_at column uses (UTC, e.g. 2026-10-17T09:30:00Z)
NOW = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
