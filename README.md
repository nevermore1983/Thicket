# WildLife

A personal wildlife sighting journal for Windows: record what you see in seconds, then explore
your sightings on a calendar, a map and in statistics. Everything stays on your PC and works
offline.

## Download

**[Download the latest WildLife installer](https://github.com/nevermore1983/WildlifeTracker/releases/latest)**: the file called `WildLife-Setup-<version>.exe`.

Run it. It installs for your Windows account only, with no administrator password, and adds WildLife to the Start menu. Running a newer installer upgrades your copy.
- Windows may say "Windows protected your PC", because the installer isn't signed with a paid certificate. Click **More info**, then **Run anyway**.
- Your data lives in `%LOCALAPPDATA%\WildLife`. Upgrading and uninstalling never touch it.

What changed in each version: [CHANGELOG.md](CHANGELOG.md). How the installer works: [docs/14-packaging.md](docs/14-packaging.md).

## Status

Version 1.0.3. See `docs/` for the research, specification, architecture, UI design and
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
uv run --with "pyinstaller==6.22.3" python scripts/build_exe.py   # app folder + smoke test
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
