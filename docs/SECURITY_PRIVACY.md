# Security and privacy

This page describes what the application does with your information. The threat model is in
[THREAT_MODEL.md](THREAT_MODEL.md). No independent security audit has been carried out.

## Principles

* **Local first.** Everything is stored on your computer. There is no telemetry, analytics or advertising
  (an automated test scans the code for network use outside the three allowed modules: optional sync,
  optional AI and the update check).
* **Update checks.** Unless you turn them off (first-run window or *Settings → Updates*), the application asks
  GitHub at most once a day whether a newer version exists. The request carries no personal data — only the
  application name and version — and every update is verified against the project's Ed25519 signing key and
  the signed SHA-256 before it is offered and installed. See [UPDATES.md](UPDATES.md).
* **Nothing is invented.** Documents contain only facts you recorded. Rule-based suggestions rearrange your
  facts; any suggestion that adds or strengthens a claim is flagged and needs explicit approval.
* **You decide disclosure.** Unconfirmed facts and facts that require review cannot be exported. Confidential
  facts never enter a document, an AI request or (by default) a cloud copy.

## Where data is stored

* One SQLite database per workspace in your data folder (see INSTALL.md), with file permissions restricted to
  your user account on macOS and Linux. **The database is not encrypted at rest**: use full-disk encryption
  (FileVault, BitLocker, LUKS) and encrypted backups for stronger protection.
* Exports go to the folder you choose; backups to the workspace's `backups` folder or wherever you save them.
* Temporary files are created in private folders and removed; stale ones are cleaned at start-up.
* Secrets — the optional AI API key, the Google Drive token and the sync passphrase — are kept only in the
  operating system's credential store (macOS Keychain, Windows Credential Manager, Secret Service). If none is
  available they are kept in memory for the session and forgotten on exit. They are never written to the
  database, configuration files, backups or logs.

## Layers of protection for confidential records

1. **Composition** — confidential records (and their children) never enter the document model; redacted
   variants include Public items only.
2. **Pre-export review** — unconfirmed and unreviewed items block export; identifiers (for example PAN or
   Aadhaar-like numbers) block export; sensitive wording (others' contact details, operating frequencies,
   security markings) needs acknowledgement. Referee contacts are allowed only for referees whose permission
   you recorded.
3. **Validation** — the exported files are scanned for distinctive phrases from confidential records; a
   match stops the export and nothing is saved.
4. **AI payloads** — only one confirmed, approved statement with its recorded metrics, outcome, tools and
   involvement can be sent, and only after you see the exact request.
5. **Cloud copies** — confidential records are replaced by placeholders unless you explicitly include them;
   with a passphrase everything is encrypted on your computer first.
6. **Logs** — events, record ids and counts only; a redaction filter masks e-mail addresses, telephone
   numbers and tokens as a safety net.

## Encryption

Encrypted backups and sync state use AES-256-GCM with a key derived from your passphrase by scrypt
(N = 2^15, r = 8, p = 1) and a random salt and nonce per file; the header is authenticated. Passphrases must
have at least 10 characters. **A lost passphrase cannot be recovered.**

## Interview preparation and questionnaires

Interview answers, STAR stories and personal questionnaires (SSB PIQ, DAF-style forms) are private
preparation notes. They never appear in resumes, cover letters or portfolios. Questionnaires can hold
family details and addresses; they are exported only when you choose *Export copy…*, and confidential
profile records are never used to generate interview questions.

## Private particulars

Home address, date of birth, nationality, date of entry into service, pay level and nature of employment are
private by default. They appear only in a government bio-data when you tick each one in Resume Studio.

## Deletion

* *Delete* moves records to **Recently deleted** (restorable); *Delete permanently* removes them.
* Removing an export from the list does not delete the file. Deleting a cloud backup does not affect local data.
* Deleting a workspace's files and relocating the data folder require confirmation; relocation copies and
  verifies before switching and leaves the old folder for you to remove.
* Backups keep older states of your data; delete old backup files if you need data to be gone.

## Your responsibility

You are responsible for deciding what may be stored and disclosed under your employer's rules. Local
storage and cloud copies do not make sensitive official information permissible to keep or share. Mark
anything doubtful as *Requires review* or *Confidential*.
