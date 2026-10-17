# WildLife — manual test script

These are the checks the automated tests can't do: real hands, real hardware, real Windows. Allow about an hour (M11 takes longest). Tick each one, and note anything odd next to it.

**Before you start:**

- **Back up your real data folder.** Copy `%LOCALAPPDATA%\WildLife` somewhere safe. Most checks below use a separate test folder, so your real data isn't touched. Only M9 uses your real data.
- **Make the test data, then open the app on it:**

  ```
  uv run python scripts/make_demo_data.py --data-dir local_data/manual
  ```

  ```
  uv run wildlife --data-dir local_data/manual
  ```

---

## Everyday use

**☐ M1: Quick add with the keyboard only (scenario S1), under 10 seconds**
1. Start a stopwatch.
2. Press **Ctrl+N**, type `robin`, then press **Enter**.
3. Tab to Count, type `2`, then press **Ctrl+S**.

Expected:
- The sighting is saved, **once**.
- It took under 10 seconds.
- The mouse was never needed.

**☐ M2: Drag photos in from File Explorer**
1. Select 3 photos in Explorer and drag them onto the Photos page.
2. Then drag 1 photo onto an open sighting.

Expected:
- They import while you keep working.
- The single photo is attached to that sighting.

**☐ M3: Display scaling at 150% and 200%**
1. In Windows Settings › Display › Scale, choose 150%. Restart WildLife.
2. Visit every page and open the add-sighting panel.
3. Repeat at 200%.

Expected:
- No text is cut off.
- No overlapping.
- Icons are sharp.

**☐ M4: Screen reader (Narrator)**
1. Turn on Narrator with **Ctrl+Win+Enter**.
2. Tab through the sidebar, the add-sighting panel and the Photos page.

Expected:
- Every button and field is read out with a sensible name.
- Field help is read out too.

## When things go wrong

**☐ M5: Damaged data file at start-up**
1. Close WildLife and make a backup first (Settings › Back up now).
2. In `local_data/manual`, open `wildlife.db` in Notepad.
3. Type some letters near the start and save.
4. Start WildLife.

Expected:
- A clear message, with **"Restore latest backup"** and **"Open data folder"**.
- Choosing Restore opens the app with the backup's data.
- A safety copy of the damaged file is kept in the data folder.

**☐ M6: Backup drive unplugged**
1. Set the backup folder to a USB stick (Settings).
2. Back up once.
3. Unplug the stick and click **Back up now**.

Expected:
- A message saying the drive isn't connected.
- The dashboard shows **"Last backup failed"**.
- Plug the stick back in: the next backup works.

**☐ M7: Power cut while saving**

Only do this on the test data, never your real data.
1. Add a sighting and save it.
2. Start adding another and press Save.
3. Straight away, end WildLife in Task Manager (**End task**).
4. Reopen it.

Expected:
- The first sighting is there.
- The second is either fully there or not there at all, never half-saved.

**☐ M8: No internet**
1. Turn off Wi-Fi.
2. Open the Map, the iNaturalist import and Settings.

Expected:
- The map shows a plain background with a note.
- Online parts say they're offline.
- Nothing freezes.

## Your real data

**☐ M9: Restore from a backup on another PC (scenario S6)**

Best done straight after M11, on the test account.
1. On a second PC (or the test account from M11), install WildLife with `WildLife-Setup-1.0.0.exe`.
2. Choose **Settings › Restore…**, then **Choose a backup file…**.
3. Pick the newest backup on your backup drive.
4. Let WildLife restart.

Expected:
- All sightings, photos and places are there.
- The dashboard numbers match the old PC.

**☐ M10: Second copy of the app**
1. With WildLife open, start it again from the Start menu.

Expected:
- The open window comes to the front.
- No second window opens.

## The installer (added in Phase 14)

The installer is `build\installer\WildLife-Setup-1.0.0.exe`. Copy it somewhere both accounts can reach, such as `C:\Users\Public\Downloads`.

**☐ M11: A Windows account that has never run WildLife** (spec acceptance item)
1. Create a test account: Windows Settings › Accounts › Other users › Add account › "I don't have this person's sign-in information" › "Add a user without a Microsoft account".
2. Sign in as the test account and run the installer.
   - If Windows says "Windows protected your PC", click **More info › Run anyway**. This only appears for files that came from the internet. See [14-packaging.md](14-packaging.md).
3. Click through the installer. No administrator password should be asked for.
4. Tick **Start WildLife now** at the end.

Expected:
- WildLife opens with the welcome screen.
- You can add a sighting, and the map shows.
- It's in the Start menu, with the green leaf icon.

Then uninstall it on the test account: Windows Settings › Apps › Installed apps › WildLife › Uninstall.

Expected:
- A message says your data was kept, and where.
- `C:\Users\<test account>\AppData\Local\WildLife` still has `wildlife.db`.
- WildLife is gone from the Start menu and the Installed apps list.

When you're done, delete the test account (Settings › Accounts › Other users).

**☐ M12: Upgrade while WildLife is open**

On your own account, after installing once:
1. Open WildLife.
2. Run the installer again.

Expected:
- The installer says WildLife is running and asks you to close it.
- After you close WildLife and click **OK**, it carries on and finishes.
- Your sightings are all there afterwards.

**☐ M13: Icon, taskbar and Start menu**
1. Start WildLife from the Start menu.
2. Right-click its taskbar button › **Pin to taskbar**.
3. Close it, then start it from the pinned button.

Expected:
- The green leaf icon appears in the title bar, taskbar and Start menu (not a Python icon).
- The pinned button and the open window are one taskbar button, not two.

---

Found a problem? Note the time it happened. In the app, **Settings › Open log folder** opens the log, and the log has the details.
