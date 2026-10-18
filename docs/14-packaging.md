# WildLife — Phase 14: packaging

> **Renamed:** WildLife became **Thicket** in version 1.2.0. This record keeps the old name where it describes what was built then; see "The rename to Thicket" at the end for what changed.

**Date:** 17 October 2026
**Status:** Complete. Manual test M11 (a brand-new Windows account) passed on 17 Oct 2026; M12–M13 are yours to run.

WildLife 1.0.0 now has:
- a proper Windows installer;
- its own icon;
- version details in the program file;
- a credit for every component it includes.

An automated check installs it, upgrades it and uninstalls it, and confirms your data is never touched.

**Exit rule: installs cleanly on a clean Windows account.**
- ✅ The automated install, upgrade and uninstall check passes.
- ✅ Manual test M11: you installed WildLife on a brand-new Windows account on 17 Oct 2026, and it worked.

---

## 1. What you get

**`build\installer\WildLife-Setup-1.0.0.exe`**, about 150 MB.

| | |
|---|---|
| Installs to | `%LOCALAPPDATA%\Programs\WildLife`, for your Windows account only. **No administrator rights.** |
| Your data | `%LOCALAPPDATA%\WildLife`, a separate folder. **Installing, upgrading and uninstalling never touch it.** |
| Shortcuts | Start menu. A desktop icon if you tick the box (it's off by default). |
| Windows' "Installed apps" list | WildLife 1.0.0, with its icon and an Uninstall button |
| Upgrading | Run a newer installer. It finds the existing installation, replaces the program files completely, and keeps your data. |
| If WildLife is open | The installer and the uninstaller both ask you to close it first, rather than replacing files under a running app |
| Uninstalling | Removes the program and its shortcuts, then tells you your data was kept and where it is |

The program file itself now has:
- **an icon**: the leaf from the app's own icon set, in white on WildLife's green. Small sizes use a solid leaf so it still reads at 16 pixels.
- **version details**: right-click › Properties › Details shows "WildLife 1.0.0, English (United Kingdom)".
- **a fixed identity on the taskbar**, so the open window and a pinned shortcut share one taskbar button and show WildLife's icon, not Python's.

---

## 2. How it works

There are two steps. Each is one command:

```
uv run --with "pyinstaller==6.22.3" python scripts/build_exe.py
uv run python scripts/build_installer.py
```

1. **`build_exe.py`** makes the app folder (`build\dist\WildLife`):
   - PyInstaller bundles Python, Qt and everything else, as before.
   - The folder now also gets the icon, the version details, `THIRD-PARTY-NOTICES.txt` and a `licenses` folder.
   - Finally it runs the smoke test: the built app opens, loads the species list, shows the map, reads RAW files and finds its icon.
2. **`build_installer.py`** wraps that folder with **Inno Setup 7**, using `packaging\installer.iss`. Then it runs the installer check (section 3).

**Words you'll see in `installer.iss`:**
- **AppId:** a fixed code that tells Windows "this is WildLife". It must never change, or an upgrade would install a second copy instead of replacing the first.
- **PrivilegesRequired=lowest:** install for this user only, with no administrator prompt.
- **AppMutex:** a name WildLife announces while it's running (`WildLife.Running`, set in `app.py`). The installer checks for it, so it can ask you to close WildLife.
- **[InstallDelete]:** before an upgrade copies the new files, the old program's `_internal` folder is removed. That way files a newer version no longer uses don't pile up. It only ever touches the program folder.

**Inno Setup 7.1.0** is the latest release (12 Aug 2026). The plan said version 6; 7 builds the same kind of installer, with a 64-bit setup program.
- It was downloaded from the project's official GitHub release.
- Its SHA-256 checksum matched the published one, and its Windows signature is valid (publisher Pyrsys B.V.).
- It's installed for your account only. It's a build tool and isn't part of WildLife.

---

## 3. The installer check

`build_installer.py` builds a **test copy** of the installer, with its own name ("WildLife installer test") and its own AppId. Testing therefore never touches a real WildLife installation, and the installed copy only ever runs on a temporary data folder. Last run:

```
ok   WildLife-InstallerTest-Setup-0.0.1.exe installed (exit 0)
ok   old version registered
ok   Start-menu shortcut made
ok   WildLife-InstallerTest-Setup-1.0.0.exe installed (exit 0)
ok   upgraded to 1.0.0
ok   upgrade went into the same folder
ok   files the new version doesn't need were removed
ok   installed app works
ok   a running WildLife is visible to the installer
ok   the mark goes when WildLife closes (closed normally)
ok   removed from Windows' installed apps
ok   Start-menu shortcut removed
ok   program folder emptied (0 left)
ok   data folder untouched
ok   your real data untouched
Installer check: PASS
```

"Your real data untouched" means the size, timestamp and checksum of your real `wildlife.db` are the same before and after. The file is only read, never opened by WildLife.

---

## 4. "Windows protected your PC"

Windows shows this blue SmartScreen box for a program that:
- came from the internet (a download, or an email attachment), **and**
- isn't signed with a paid code-signing certificate.

An installer you build on your own PC doesn't carry the "from the internet" mark, so you won't normally see it. If you copy the installer to another PC through a download or a cloud link, click **More info › Run anyway** once.

Signing would remove the warning:
- A certificate costs about £120–250 a year.
- Microsoft's cheaper signing service still isn't open to individuals in the UK (as found in Phase 1).

For personal use it isn't needed. If you ever share WildLife publicly, revisit this.

---

## 5. Licences

`THIRD-PARTY-NOTICES.txt` and the `licenses` folder ship inside the app. They cover:
- Python;
- Qt and PySide6;
- Pillow;
- pi-heif (with libheif and libde265);
- rawpy (with LibRaw);
- NumPy;
- MapLibre GL JS;
- the Source Serif 4 font;
- the UK Species Inventory, with the Natural History Museum's required attribution;
- PyInstaller's starter program.

The notices also mention OpenFreeMap and OpenStreetMap, whose maps are loaded online.

**Qt and the HEIC libraries are under the GNU LGPL v3.** For a personal app this means three things:
- **Ship the licence texts.** Done. `LGPL-3.0.txt` came from gnu.org and matched the SPDX project's copy. `GPL-3.0.txt` is the complete text NumPy already includes.
- **Keep the libraries replaceable.** Done: they're separate files in `_internal\PySide6`, which is why WildLife is a folder app, not a single .exe.
- **Say where the source code is.** Done: the notices give Qt's official download addresses.

If you ever distribute WildLife to other people, have these terms looked at again. For your own use you're well covered.

`tests/unit/test_notices.py` fails if a new Python package ends up in the app without a notice entry. It already caught two: Qt 6.12 split itself into new `pyside6-webengine` and `pyside6-pdf` packages.

---

## 6. Spec section 11: the acceptance checklist, final status

| Item | Status |
|---|---|
| Scenarios S1–S7 work as described | ✅ `tests/ui/test_scenarios.py` |
| S1 under 10 s, keyboard only | ✅ Test, plus manual test M1 for the stopwatch |
| Every Must feature complete | ✅ Custom species moved to version 2 by your choice (spec section 12) |
| Every section 9 target met | ✅ docs/13-hardening.md, section 2 |
| Every row of section 10 tested | ✅ docs/13-hardening.md, section 3 |
| Backup → wipe → restore identical | ✅ `test_s6_new_pc_restore_from_the_backup_drive` |
| Export → import into an empty library identical | ✅ `test_round_trip_into_an_empty_library` |
| UI/UX audit has no open "high" items | ✅ Phase 12 |
| Installer works on a fresh account; uninstall keeps data | ✅ Automated check (section 3), and manual test M11 on a new account (17 Oct 2026) |

---

## 7. Problems found and fixed

- **The first close request didn't close WildLife.**
  - The installer check asks WildLife to close politely (the same request as the X button) and saw it ignored.
  - The cause: a brand-new data folder opens the welcome dialog, and a close request closes only the dialog. Every Windows program behaves this way while a dialog is open.
  - The main window itself closes politely, logs "Closed" and shuts the data file properly. The check now asks again after the dialog closes.
- **Inno Setup read one of my message lines as a command.** Its preprocessor treats any line starting with `#` as a directive, and `#13#10` (a line break code) began a line. The lines are wrapped differently now, with a comment explaining why.
- **The Bash tool turned `\n` into real line breaks again**, this time in the version-details file. It was fixed with the Edit tool, as the rule from Phase 9 says.
- **A stray `E:\c` folder.** A test of mine passed a `/c/Users/…` path to Windows Python, which read it as `E:\c\Users\…` and wrote 33 licence files there. Nothing else is in it, but the safety check rightly wouldn't let me delete a folder at the root of a drive. **Please delete `E:\c` yourself.** It only holds those copies.

## 8. What I learned

- **Test the installer the way Windows uses it.** That means a silent install, an upgrade without telling it the folder, and an uninstall that hands over to a copy of itself and returns early (the check waits for it). Each of these behaves differently from just running the program.
- **Keep the program and the data apart.** The program folder can then be wiped and replaced on every upgrade with no risk to your sightings. That's what makes "uninstall keeps your data" automatic rather than something to remember.
- **A small icon is a different drawing.** The outline leaf turned to mush at 16 pixels. A solid shape reads clearly.
- **Licences can be checked by a test.** A list kept by hand drifts. A test that compares it with what's actually installed doesn't.

## 9. Files

- `packaging/installer.iss`: the installer
- `packaging/licenses/`: the LGPL-3.0 and GPL-3.0 texts
- `scripts/build_installer.py`: builds the installer and runs the check
- `scripts/notices.py`: the third-party list and licence copying
- `scripts/make_icon.py` and `src/wildlife/resources/icons/`: the icon
- `scripts/build_exe.py`: now adds the icon, version details and notices
- `src/wildlife/app.py`: window icon, taskbar identity, the "running" mark
- `tests/unit/test_notices.py`

Version 1.0.0 installer SHA-256: `AC525F2A82DEA501635B15230DC80F8B85B7525E51ABFCCDF83E728A1A4A4A81`. A rebuild gives a different checksum, because build times are written into the files.

---

## 10. Publishing a release (added 17 Oct 2026)

Installers for download are built by GitHub, not on this PC (`.github/workflows/release.yml`). A build on GitHub's own clean Windows machine shows the release was made from exactly the source in the repository, and carries no traces of this PC (such as your Windows username in internal file paths).

**To publish a new version:**
1. Set the version in `pyproject.toml` and `src/wildlife/__init__.py`, then run `uv lock`.
2. Add what changed under a new `## <version>` heading in `CHANGELOG.md`. A test fails if you forget.
3. Commit and push.
4. Tag the commit and push the tag:

   ```
   git tag v1.0.3
   git push origin v1.0.3
   ```

GitHub then does, in order (if any step fails, nothing is published):
1. Checks the tag matches the version.
2. Runs all the tests.
3. Installs Inno Setup 7.1.0 after checking its checksum and signature.
4. Builds the app and runs its smoke test.
5. Builds the installer and runs the install, upgrade and uninstall check.
6. Publishes the release, with the installer (also as `Thicket-Setup.exe`, a name that never changes, for the website's download button; added 18 Oct 2026), a `SHA256SUMS.txt` file (Unix line endings, so `sha256sum -c` works) and the changelog notes for that version.

The progress is on the repository's **Actions** tab, and the result on its **Releases** page.

**Safeguards:**
- Outside code is pinned to exact versions: GitHub's actions by commit, Inno Setup by checksum and signature, PyInstaller 6.22.3, and every Python library by `uv.lock`.
- The workflow's only permission is `contents: write`, the one needed to publish a release (it also covers the repository's files, but the workflow only creates the release). Nothing else, such as settings or issues, is allowed. It uses GitHub's own short-lived token, so no password or key is stored anywhere.

**Licences:** a public download counts as distributing Qt, so the notices state that WildLife's terms allow modifying the Qt libraries and reverse engineering for debugging, as the LGPL requires (version 1.0.3).

**The map on GitHub's build machine.** It has no graphics card, and the map needs one (WebGL) to draw. Chromium inside Qt has no software fallback for it: SwiftShader and WARP were both tried, and neither works. So on GitHub (`WILDLIFE_NO_GPU=1` in the workflow), the smoke tests accept "WebGL isn't available" for the map step. That message means the map page and all its files loaded and ran; only the drawing is untested there. Every other check runs in full. A local build still requires the map to draw. On a PC without a graphics card (some virtual machines, Remote Desktop), WildLife shows its "the map can't be shown here" explanation instead of the map, as designed.

## The rename to Thicket (version 1.2.0)

Everything a person sees says **Thicket**: the window, the Start-menu and desktop shortcuts, Windows' "Installed apps" list, the .exe's Properties, the installer (`Thicket-Setup-<version>.exe`), messages and exports.

Some names are remembered by Windows or by files already on people's PCs, so they keep the first name. Changing any of them would make an upgrade lose track of something:

| Kept as WildLife | Why |
|---|---|
| AppId | Windows recognises the installed app by it; a new one would install a second copy |
| `WildLife.exe` | Taskbar pins point at the .exe by name |
| AppMutex `WildLife.Running` | A running WildLife 1.1.0 must still stop the installer |
| AppUserModelID `WildLife.WildLife` | Keeps the window and its pinned shortcut on one taskbar button |
| Data folder `%LOCALAPPDATA%\WildLife` | Where everyone's sightings and photos already are |
| Saved window and view choices (QSettings) | Stored under the old name in the registry |
| A chosen backup folder's "WildLife Backups" | Older backups stay listed and tidied; new backup folders are "Thicket Backups" |
| The export file format (`wildlife-export.json`) | Older exports still import, and newer ones still open in older versions |
| The program folder of an earlier install | Inno Setup reuses it (`UsePreviousAppDir`); new installs go to `Programs\Thicket` |

An upgrade from WildLife also removes the old "WildLife" Start-menu and desktop shortcuts (`[InstallDelete]`), so there aren't two icons. The installer check covers this with a test copy's own old-name shortcut, so your real shortcuts are never touched.
