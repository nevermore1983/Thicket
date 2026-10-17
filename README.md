# WildLife

A personal wildlife sighting journal for Windows: record what you see in seconds, then explore
your sightings on a calendar, a map and in statistics. Everything stays on your PC and works
offline.

## Installing

Run `WildLife-Setup-1.0.2.exe` (or newer). It installs for your Windows account only, with no
administrator rights, and adds WildLife to the Start menu. See
[docs/14-packaging.md](docs/14-packaging.md) for what it does, including the "Windows
protected your PC" message.

Your data lives in `%LOCALAPPDATA%\WildLife`. Upgrading and uninstalling never touch it.

## Status

Version 1.0.2. See `docs/` for the research, specification, architecture, UI design and
each phase's record, and `prototype/index.html` for the clickable design prototype.

## Developer setup

Requires [uv](https://docs.astral.sh/uv/). uv installs the right Python (3.13) automatically.

```bash
uv sync                      # create .venv and install everything
uv run wildlife              # start the app
uv run pytest                # run the tests
uv run ruff check .          # lint
uv run ruff format .         # format
uv run python scripts/make_demo_data.py --data-dir local_data/demo --sightings 20000
```

Building a release (needs [Inno Setup 7](https://jrsoftware.org/isinfo.php)):

```bash
uv run --with "pyinstaller>=6.16" python scripts/build_exe.py   # app folder + smoke test
uv run python scripts/build_installer.py                        # installer + install check
```

## Project layout

| Folder | What's in it |
|---|---|
| `src/wildlife/domain` | Plain data classes and rules (no Qt, no SQL) |
| `src/wildlife/data` | Database connection, migrations and all SQL |
| `src/wildlife/services` | The app's actions: save a sighting, back up, import… |
| `src/wildlife/ui` | Windows, pages, components and theme |
| `tests/` | Automated tests |
| `scripts/` | Developer tools (demo data, species catalogue, benchmark, build) |
| `packaging/` | Installer script and licence texts |
| `spikes/` | Throwaway experiments that answered a risky question |
| `docs/` | Design documents |
