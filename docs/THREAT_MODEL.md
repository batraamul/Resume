# Threat Model — Resume Intelligence Studio

Method: asset-centric review of a single-user, local-first desktop application with optional cloud and AI connectors. It covers implemented controls and their limits. It does not claim the software is secure against every threat.

## Assets

| Asset | Where it lives |
|---|---|
| Master profile (personal details, career history, projects, official particulars) | Workspace SQLite database |
| Confidential records (classification "Confidential") | Same database, filtered from every outbound channel |
| Exported documents | Folders chosen by the user |
| Backups (plain or encrypted) | Workspace `backups/` folder, optional cloud copy |
| Secrets: Google OAuth refresh token, AI API key, cloud backup passphrase | OS credential store (Keychain on macOS) or session memory |
| Logs | Workspace-independent `logs/` folder in the data directory |

## Trust boundaries

1. The user's account on the local machine (trusted while unlocked).
2. Imported files, pasted vacancy text and AI responses (untrusted input).
3. Google Drive and external AI endpoints (third parties, reached only on explicit user action).
4. LibreOffice subprocess (local, trusted binary; runs with an isolated profile and a timeout).

## Threats and controls

| ID | Threat | Controls implemented | Residual risk / limitation |
|---|---|---|---|
| T1 | **Local device compromise** (malware, stolen unlocked laptop) | Data kept in the per-user data directory with user-only permissions (0700 folders, 0600 database on POSIX); secrets in the OS credential store; encrypted backup option. | The working database is **not encrypted at rest**. Rely on full-disk encryption (FileVault on macOS). Documented in `SECURITY_PRIVACY.md` and shown in Settings. |
| T2 | **Accidental disclosure** of confidential or sensitive official information in a resume | Four-level classification; uncertain items default to *Requires review*; composer excludes Confidential; export blocked until review items are resolved; sensitive-pattern scanner (internal systems, deployment/location specifics, security procedures, identifiers); post-render scan of DOCX/PDF/TXT for confidential phrases; redacted export mode. | Pattern scanning is heuristic. The user remains responsible for disclosure decisions (stated in the UI). |
| T3 | **Malformed or hostile imported files** (corrupt DOCX/PDF, huge files, archive path traversal, JSON bombs) | Size limits per file type; parsing in try/except with structured errors; backup archives validated (no absolute paths, no `..`, allow-listed member names, size caps); JSON depth/size limits; imported records are unconfirmed and require review. | Third-party parsers (python-docx, pypdf) could have undiscovered bugs; keep dependencies updated. |
| T4 | **Credential leakage** | No credentials in source, config, database or logs; keyring storage with session-only fallback; logging redaction filter for tokens, keys, bearer headers, emails and phone numbers; secrets never shown after entry. | A compromised OS account can read keychain items it is authorised for. |
| T5 | **Cloud conflict or corruption** | Stable record ids, revisions and checksums; three-way merge; conflicts stored with both versions and resolved by the user; downloads verified by SHA-256 before use; pre-restore snapshot always taken; remote manifest re-checked before upload (optimistic concurrency). | Drive API has no atomic compare-and-swap for app files; a small race window between the check and the upload remains (documented). |
| T6 | **Backup exposure** | Optional AES-256-GCM encryption with scrypt key derivation; cloud uploads exclude Confidential records; local backup folder permissions restricted. | Unencrypted local backups are as sensitive as the database. |
| T7 | **Temporary-file leakage** | All rendering and conversion happen in private temporary directories (0700) removed in `finally` blocks; preview PDFs held in memory where possible; LibreOffice runs with an isolated throw-away profile. | A crash can leave a temp folder until the next start; startup cleanup removes stale RIS temp folders. |
| T8 | **Unauthorised AI transmission** | External AI disabled by default; enabling requires endpoint, model and key; every request builds a minimal payload of approved, non-confidential facts; exact payload preview and per-request confirmation; requests logged by size and purpose only. | Once sent, data is governed by the provider's terms. |
| T9 | **Prompt injection in imported material** | Vacancy text and imported documents are treated as data. The rules engine never executes instructions. AI prompts delimit untrusted text and instruct the model to treat it as data. AI output can only produce suggestions that go through claim validation and approval; it cannot change settings, classifications or records. | A model may still produce misleading suggestions; approval is the final control. |
| T10 | **Telemetry/background transmission** | No telemetry. Network access: explicit user actions (Drive connect/sync, AI request) and the daily update check, which can be turned off and sends only the application name and version to GitHub. A test restricts network imports to three modules. | GitHub sees the IP address of update checks. |
| T12 | **Malicious or tampered update** (compromised download, mirror or release asset) | Ed25519-signed manifest verified against embedded public keys; manifest bound to this repository and its release-download URLs; installer size and SHA-256 checked before use; HTTPS to GitHub hosts only, including redirects; no downgrades; user consent before installing; unsigned builds published only as drafts; build-provenance attestations. | Theft of the private signing key or a malicious workflow change by someone with write access would defeat the scheme; protect secrets, branches, tags and workflow changes. OS code signing is optional. |
| T13 | **Interview notes and questionnaires** containing family details or addresses | Stored as non-fact records; never composed into resumes; confidential profile records excluded from generated questions; exported only on request, with a "private copy" label. | Exported copies are as sensitive as the questionnaire; store them carefully. |
| T11 | **Data loss** (bad restore, corruption, mistaken delete) | Soft delete with tombstones; confirmation for destructive actions; automatic backups with retention; integrity checks; restore verifies the archive before touching data. | Backups stored on the same disk do not protect against disk failure; use cloud or external copies. |

## Security assumptions

* The operating system account is protected by a password and, ideally, full-disk encryption.
* LibreOffice and Python packages come from trusted sources.
* The user creates their own Google Cloud OAuth client; the app never ships shared client secrets.

## Review triggers

Re-review this model when adding a new outbound channel, a new import format, a new secret, or changing the storage format.
