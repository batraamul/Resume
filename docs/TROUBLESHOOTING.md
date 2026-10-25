# Troubleshooting

Start with `python run_application.py --selftest`; it names most problems directly. Logs (events and
counts only, never content) are in the data folder under `logs/` — *Settings & Security → Open log folder*.

| Problem | What to do |
|---|---|
| "needs Python 3.11 or newer" | Install Python 3.11+ from python.org and run the launcher again. Delete `.venv` if it was created with an older Python. |
| First start fails while installing | Check the internet connection, then delete `.venv` and start again. Behind a proxy, set `HTTPS_PROXY` before launching. |
| macOS says the launcher cannot be opened | Right-click `launch_macos.command` → *Open* → *Open*. If it is not executable: `chmod +x launch_macos.command`. |
| Window does not appear on Linux | Install the Qt runtime libraries (`libxcb-cursor0`, `libegl1`) or run under Wayland with `QT_QPA_PLATFORM=wayland`. |
| Export says it "needs your review first" | Facts that are awaiting confirmation or require a disclosure review are listed. Confirm/approve them, leave them out of this resume, or open the record. |
| Export "stopped: failed validation" | The report lists the failed checks (for example a missing section, a confidential phrase, too many pages). Nothing was saved. Fix the cause and export again. |
| Text in Hindi/Devanagari is missing from the PDF | The built-in engine cannot shape complex scripts. Install LibreOffice and choose it as the PDF engine. |
| PDF pagination differs from Word | Install LibreOffice and use it as the PDF engine, or preview with "export engine". Fonts are metric-compatible, but LibreOffice gives the closest match. |
| A two-column resume puts a heading at the bottom of a page in Word | Keep-with-next is disabled inside column layouts so the columns can split across pages. Adjust the section order or spacing, or use a single-column template. |
| The career timeline is missing | It needs at least two positions with start dates (consecutive posts in the same organisation form one bar). Check the dates and that the positions are not confidential or excluded. |
| No competency bars | Bars appear only for skills with a proficiency set (not "Not rated") in a graphical template. |
| A referee does not appear | Tick *This person has agreed to be named as a referee* on the referee record. |
| "This record was changed elsewhere" | Another window or a sync changed it. Choose *Reload* (your unsaved edits are discarded) or keep editing and copy your text first. |
| Restore failed verification | The file is damaged or the passphrase is wrong. Try another backup; your current data is unchanged. |
| Forgot a backup or sync passphrase | Encrypted data cannot be recovered without it. Use an unencrypted local backup if you have one. |
| Sync: "authorisation has expired" | *Synchronisation → Disconnect*, then *Connect Google account…* again. |
| Sync conflicts | Open each conflict and choose a version; then *Sync now* to send your decision. Nothing is lost until you choose. |
| The database will not open | The sample workspace opens instead. Use *Backup & Restore → Restore from a file…* with your latest backup, then *Check database integrity*. |
| The application is slow with a very large profile | Use one- or two-page lengths while editing; full CVs with hundreds of publications take a second or two to preview. |

## Recovering your data

1. **Deleted a record by mistake** — *Backup & Restore → Recently deleted* → select it → *Restore selected*. Linked
   items deleted with it come back too.
2. **Unwanted changes** — every record keeps its revision history; restore the latest backup taken before
   the change (*Backup & Restore* → select it → *Restore selected…*). Your current data is saved first as a *pre-restore* backup,
   so a restore can itself be undone.
3. **Database damaged or will not open** — the application opens the sample workspace instead. Choose
   *Backup & Restore → Restore from a file…*, pick the newest backup (automatic backups are in the
   workspace's `backups` folder — *Open backup folder* shows it), then run *Check database integrity*. If the search box returns nothing,
   use *Rebuild search index*.
4. **After a failed upgrade** — a `pre-upgrade-vN` backup was written before the migration; restore it
   with the version you were using before.
5. **New computer** — install the application, then restore a backup file (or connect synchronisation
   with the same passphrase). Encrypted backups need their passphrase; it cannot be recovered.
6. **Portable copy** — *Backup & Restore → Portable profile → Export profile…* produces a readable file that can be
   imported into a new workspace (imported facts return as *Awaiting confirmation*).

Reporting a problem: include the self-test output and the relevant lines of the log. Never include
backups, exports or your database.
