# WildLife

A personal wildlife sighting journal for Windows: record what you see in seconds, then explore
your sightings on a calendar, a map and in statistics. Everything stays on your PC and works
offline.

## Status

In development. See `docs/` for the research, specification, architecture and UI design, and
`prototype/index.html` for the clickable design prototype.

## Developer setup

Requires [uv](https://docs.astral.sh/uv/). uv installs the right Python (3.13) automatically.

```bash
uv sync                      # create .venv and install everything
uv run wildlife              # start the app
uv run pytest                # run the tests
uv run ruff check .          # lint
uv run ruff format .         # format
uv run python scripts/make_demo_data.py --sightings 20000   # build a demo library
```

## Project layout

| Folder | What's in it |
|---|---|
| `src/wildlife/domain` | Plain data classes and rules (no Qt, no SQL) |
| `src/wildlife/data` | Database connection, migrations and all SQL |
| `src/wildlife/services` | The app's actions: save a sighting, back up, import… |
| `src/wildlife/ui` | Windows, pages, components and theme |
| `tests/` | Automated tests |
| `scripts/` | Developer tools (demo data, species catalogue builder) |
| `spikes/` | Throwaway experiments that answered a risky question |
| `docs/` | Design documents |
