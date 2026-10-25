# Installation

## Install a ready-made build (recommended)

Download the file for your computer from the latest release:
**https://github.com/batraamul/Resume/releases/latest**. No Python is needed. Check a download with
`SHA256SUMS.txt` from the same release if you wish.

| Computer | File | How to install |
|---|---|---|
| **Windows 10/11 (64-bit)** | `ResumeIntelligenceStudio-<version>-windows-x64-setup.exe` | Double-click and follow the steps. It installs for your user account only (no administrator rights), adds a Start-menu entry and an uninstaller. If Windows SmartScreen says "Windows protected your PC", choose *More info → Run anyway* — the community build is not code-signed. A portable zip is also provided. |
| **macOS 12 or later, Apple silicon (M1–M4)** | `ResumeIntelligenceStudio-<version>-macos-arm64.dmg` | Open the disk image and drag *Resume Intelligence Studio* onto *Applications*. The first time, right-click (Control-click) the app → *Open* → *Open*; on recent macOS you may need *System Settings → Privacy & Security → Open Anyway*. The app is not notarised by Apple unless the maintainer has configured signing. Intel Macs: run from source (below). |
| **Ubuntu / Debian (64-bit)** | `resume-intelligence-studio_<version>_amd64.deb` | `sudo apt install ./resume-intelligence-studio_<version>_amd64.deb` (installs dependencies, a menu entry and the `resume-intelligence-studio` command). |
| **Other Linux (64-bit)** | `ResumeIntelligenceStudio-<version>-linux-x86_64.tar.gz` | Extract anywhere you can write to, run `ResumeIntelligenceStudio/ResumeIntelligenceStudio`, and optionally `ResumeIntelligenceStudio/install-desktop-entry.sh` to add a menu entry. Needs the Qt runtime libraries (`libegl1`, `libxkbcommon-x11-0`, `libxcb-cursor0`). |

After installing, the app keeps itself up to date (*Settings & Security → Updates*; see
[UPDATES.md](UPDATES.md)). Optional: install **LibreOffice** for PDFs that match the Word layout most
closely; without it the built-in PDF engine is used.

Uninstalling (Windows: *Settings → Apps*; macOS: drag the app to the Bin; Debian/Ubuntu:
`sudo apt remove resume-intelligence-studio`; tar.gz: delete the folder) never removes your data folder.

## Run from source (any platform, including Intel Macs)

### Requirements

* Python **3.11, 3.12 or 3.13** (64-bit). On macOS install it from python.org (the system Python is too old);
  on Windows tick *Add python.exe to PATH* during installation.
* About 700 MB of disk space for the private Python environment (mostly the Qt toolkit).
* Internet access **once**, to download the pinned dependencies.

### Start with the launchers

1. Download the source (`git clone https://github.com/batraamul/Resume.git` or the release's source zip) and
   keep it somewhere outside a synced folder.
2. Start it:
   * **macOS** — double-click `launch_macos.command`. The first time macOS may refuse an unsigned script:
     right-click it → *Open* → *Open*.
   * **Windows** — double-click `launch_windows.bat`.
   * **Linux** — run `./launch_linux.sh` from a terminal (install `python3-venv` first on Debian/Ubuntu).
3. The first start creates `.venv` next to the launchers and installs `requirements.txt`; later starts are quick.
4. A welcome window offers: start your profile, import an existing CV or profile file, or explore the
   fictional sample. It also lets you turn automatic update checks off.

### Manual installation

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt          # Windows: .venv\Scripts\python
.venv/bin/python run_application.py
```

Optional Google Drive support: `.venv/bin/python -m pip install -r requirements-optional.txt`.

## Verify the installation

```bash
.venv/bin/python run_application.py --selftest
```

The self-test checks the Python packages, SQLite with full-text search, all templates, fonts and glyph
coverage, LibreOffice (optional), the credential store, a complete validated DOCX + PDF export of the
fictional sample in a temporary folder, and the Qt toolkit. It never touches your data.

## Where your data lives

| Platform | Folder |
|---|---|
| macOS | `~/Library/Application Support/Resume Intelligence Studio` |
| Windows | `%APPDATA%\ResumeIntelligenceStudio` |
| Linux | `~/.local/share/resume-intelligence-studio` (data) and `~/.config/resume-intelligence-studio` (settings) |

Move it with *Settings & Security → Move data folder…* (the data is copied and verified first). For testing,
`RIS_DATA_DIR` and `RIS_CONFIG_DIR` override both locations. The application folder never contains personal data.

## Building a stand-alone application (optional)

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/pyinstaller packaging/ris.spec --noconfirm --clean
dist/ResumeIntelligenceStudio/ResumeIntelligenceStudio --selftest
```

On macOS this also produces `Resume Intelligence Studio.app` (ad-hoc signed; right-click → Open the first time).
Installers are normally built by GitHub Actions for Windows, macOS and Linux from a version tag — see
[RELEASING.md](RELEASING.md). Locally you can package them with `packaging/windows/ris.iss` (Inno Setup),
`packaging/macos/make_dmg.sh` and `packaging/linux/make_packages.sh`.

### Signing and notarisation (not performed during development)

The builds are unsigned. To distribute them without security warnings you need your own certificates;
the commands below are the standard vendor tools and were **not** run during development.

macOS (Apple Developer ID certificate in your keychain; Xcode command-line tools):

```bash
APP="dist/Resume Intelligence Studio.app"
codesign --deep --force --options runtime --timestamp \
         --sign "Developer ID Application: <Your Name> (<TEAMID>)" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
# Store notarisation credentials once (prompts for an app-specific password; never put it in a file):
xcrun notarytool store-credentials ris-notary --apple-id <your-apple-id> --team-id <TEAMID>
ditto -c -k --keepParent "$APP" RIS-notarise.zip
xcrun notarytool submit RIS-notarise.zip --keychain-profile ris-notary --wait
xcrun stapler staple "$APP"
spctl --assess --type execute --verbose "$APP"
```

Windows (code-signing certificate; Windows SDK `signtool`):

```bat
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a ^
    dist\ResumeIntelligenceStudio\ResumeIntelligenceStudio.exe
signtool verify /pa dist\ResumeIntelligenceStudio\ResumeIntelligenceStudio.exe
```

Run `--selftest` on the signed build before distributing it.

## Upgrading

Installed builds update themselves (see [UPDATES.md](UPDATES.md)); with a source checkout run `git pull`
and start it again. The database is upgraded by numbered migrations; a
safety backup (`pre-upgrade-vN`) is written automatically before any migration, and newer databases are
never opened by older versions. Your data folder is shared between versions.

## Uninstalling

Delete the application folder. Your data folder is kept; delete it separately if you no longer need it
(make a backup first). Stored secrets can be removed from *Settings & Security* and *Synchronisation* before
uninstalling, or from your operating system's credential manager (service `ResumeIntelligenceStudio`).
