# Google Drive setup (optional)

Synchronisation is **off** by default and the application is fully usable without a Google account.
There are two ways to use Google Drive.

## Option A — a synced folder (simplest, no Google setup)

1. Install **Google Drive for desktop** and sign in there.
2. In *Synchronisation* choose **A folder…** and pick a folder inside your Google Drive (for example
   `My Drive/Resume Intelligence Studio`).
3. Click **Set sync passphrase…** (strongly recommended), then **Sync now**.

The application only reads and writes files in that folder; Google Drive for desktop uploads them.

## Option B — Google Drive directly

This uses the Drive API with the **`drive.file`** permission: the application can see and change only the
files it created, nothing else in your Drive. You sign in on Google's own page in your browser; the
application never sees your Google password. No credentials are bundled with the application — you create
your own OAuth client once.

1. Install the optional packages: `.venv/bin/python -m pip install -r requirements-optional.txt`, then restart.
2. In the [Google Cloud Console](https://console.cloud.google.com/): create a project → *APIs & Services* →
   enable **Google Drive API**.
3. *OAuth consent screen*: user type *External* (or *Internal* for a Workspace domain), add yourself as a test
   user, and add the scope `https://www.googleapis.com/auth/drive.file`.
4. *Credentials* → *Create credentials* → *OAuth client ID* → application type **Desktop app** → download the
   JSON file. Keep it private.
5. In *Synchronisation* choose **Google Drive directly**, **Choose client file…** (the JSON from step 4) and
   **Connect Google account…**. Complete the consent in your browser.
6. Set a sync passphrase and click **Sync now**.

The refresh token is stored only in your operating system's credential store. **Disconnect** revokes it and
removes it from this computer; files already in Drive are not deleted.

## What is uploaded

* `ris-sync/state.json` — your records (encrypted when a passphrase is set), with confidential records
  replaced by placeholders unless you tick *Include records marked Confidential*.
* `ris-backups/…` — encrypted backups you upload explicitly (*Upload an encrypted backup*).

## Several devices

Use the same passphrase everywhere. Changes are merged record by record against the last synchronised
state; a record changed on two devices becomes a **conflict** that you resolve (keep this computer's, keep
the other device's, keep both). Deletions sync as tombstones. Nothing is overwritten silently.

## Status of testing

The Drive integration was tested against a mocked HTTP session (folder creation, upload, conditional update
with version checks, listing, download, deletion, expired authorisation, network failures). It has not been
exercised against a live Google account during development.
