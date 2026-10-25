"""Record-level synchronisation with three-way merge (SYN-04/05, DEF-05).

The remote holds one state document (``ris-sync/state.json``, optionally
encrypted) containing record envelopes (stable id, revision, checksum,
tombstones) and immutable resume versions. Each device keeps the last synced
checksum per record in ``sync_base``.

For each record:
* changed only locally → pushed;
* changed only remotely → pulled;
* changed on both sides with different content → **conflict**: nothing is
  overwritten; both versions are stored for the user to compare and resolve.

Confidential records (and their descendants) are never uploaded. When a
record becomes confidential, its remote entry is replaced by a content-free
marker so other devices also mark their copy confidential.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from ris import __version__
from ris.backup import crypto
from ris.domain.enums import Confidentiality
from ris.errors import RemoteChanged, SyncError
from ris.storage.repository import RecordRepository
from ris.sync.remote import RemoteStore
from ris.util import new_id, utc_now_iso

log = logging.getLogger(__name__)

STATE_NAME = "ris-sync/state.json"
FORMAT_ID = "ris-sync"
FORMAT_VERSION = 1
MAX_RETRIES = 3


@dataclass
class SyncReport:
    pushed: int = 0
    pulled: int = 0
    conflicts: int = 0
    unchanged: int = 0
    redacted: int = 0
    versions_pushed: int = 0
    versions_pulled: int = 0
    attempts: int = 0
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{self.pushed} sent", f"{self.pulled} received"]
        if self.conflicts:
            parts.append(f"{self.conflicts} conflict(s) need your decision")
        if self.versions_pushed or self.versions_pulled:
            parts.append(f"{self.versions_pushed + self.versions_pulled} resume version(s) exchanged")
        return "Synchronised: " + ", ".join(parts) + "."


@dataclass
class Conflict:
    id: str
    object_id: str
    kind: str
    detected_at: str
    local: dict | None
    remote: dict | None


class SyncEngine:
    def __init__(self, repo: RecordRepository, remote: RemoteStore, *, passphrase: str | None = None,
                 include_confidential: bool = False, device_id: str = "") -> None:
        self.repo = repo
        self.db = repo.db
        self.remote = remote
        self.passphrase = passphrase
        self.include_confidential = include_confidential
        self.device_id = device_id or repo.device_id

    # ------------------------------------------------------------------ state document
    def _encode(self, state: dict) -> bytes:
        raw = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if self.passphrase:
            return crypto.encrypt(raw, self.passphrase, meta={"kind": "sync-state", "app_version": __version__})
        return raw

    def _decode(self, data: bytes) -> dict:
        if crypto.is_encrypted(data[:16]):
            if not self.passphrase:
                raise SyncError("The cloud data is encrypted; enter the sync passphrase in Synchronisation settings.")
            data, _ = crypto.decrypt(data, self.passphrase)
        elif self.passphrase:
            log.info("Remote sync state is not encrypted; it will be encrypted on the next write")
        try:
            state = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise SyncError("The cloud sync data is damaged.") from exc
        if state.get("format") != FORMAT_ID:
            raise SyncError("The cloud folder contains data that is not Resume Intelligence Studio sync data.")
        if int(state.get("format_version", 0)) > FORMAT_VERSION:
            raise SyncError("The cloud data was written by a newer version of the application.")
        return state

    def read_state(self) -> tuple[dict, str]:
        info = self.remote.stat(STATE_NAME)
        if info is None:
            return {"format": FORMAT_ID, "format_version": FORMAT_VERSION, "generation": 0, "records": {},
                    "versions": {}}, ""
        data, info = self.remote.read(STATE_NAME)
        return self._decode(data), info.version

    # ------------------------------------------------------------------ local view
    def _excluded_ids(self, envs: list[dict]) -> set[str]:
        if self.include_confidential:
            return set()
        by_parent: dict[str, list[str]] = {}
        for e in envs:
            if e.get("parent_id"):
                by_parent.setdefault(e["parent_id"], []).append(e["id"])
        stack = [e["id"] for e in envs if e["confidentiality"] == Confidentiality.CONFIDENTIAL.value]
        out: set[str] = set()
        while stack:
            rid = stack.pop()
            if rid in out:
                continue
            out.add(rid)
            stack.extend(by_parent.get(rid, []))
        return out

    def _base(self) -> dict[str, tuple[int, str]]:
        return {r["object_id"]: (int(r["revision"]), r["checksum"]) for r in self.db.query("SELECT * FROM sync_base")}

    def _set_base(self, object_id: str, revision: int, checksum: str) -> None:
        self.db.execute("INSERT INTO sync_base (object_id, revision, checksum, synced_at) VALUES (?, ?, ?, ?)"
                        " ON CONFLICT(object_id) DO UPDATE SET revision = excluded.revision,"
                        " checksum = excluded.checksum, synced_at = excluded.synced_at",
                        (object_id, revision, checksum, utc_now_iso()))

    def _local_versions(self) -> dict[str, dict]:
        rows = self.db.query("SELECT * FROM variant_versions")
        return {r["id"]: dict(r) for r in rows}

    # ------------------------------------------------------------------ conflicts
    def open_conflicts(self) -> list[Conflict]:
        rows = self.db.query("SELECT * FROM sync_conflicts WHERE status = 'open' ORDER BY detected_at")
        return [Conflict(r["id"], r["object_id"], r["kind"], r["detected_at"],
                         json.loads(r["local"]) if r["local"] else None,
                         json.loads(r["remote"]) if r["remote"] else None) for r in rows]

    def _record_conflict(self, object_id: str, kind: str, local: dict | None, remote: dict | None) -> bool:
        existing = self.db.query_one("SELECT id, remote FROM sync_conflicts WHERE object_id = ? AND status = 'open'",
                                     (object_id,))
        if existing is not None:
            prev = json.loads(existing["remote"]) if existing["remote"] else None
            if (prev or {}).get("checksum") == (remote or {}).get("checksum"):
                return False
            self.db.execute("UPDATE sync_conflicts SET local = ?, remote = ?, detected_at = ? WHERE id = ?",
                            (json.dumps(local), json.dumps(remote), utc_now_iso(), existing["id"]))
            return True
        self.db.execute("INSERT INTO sync_conflicts (id, object_id, kind, detected_at, local, remote, status)"
                        " VALUES (?, ?, ?, ?, ?, ?, 'open')",
                        (new_id(), object_id, kind, utc_now_iso(), json.dumps(local), json.dumps(remote)))
        return True

    def resolve(self, conflict_id: str, choice: str) -> None:
        """Resolve a conflict: keep_local | keep_remote | keep_both."""
        row = self.db.query_one("SELECT * FROM sync_conflicts WHERE id = ?", (conflict_id,))
        if row is None or row["status"] != "open":
            raise SyncError("That conflict is no longer open.")
        local = json.loads(row["local"]) if row["local"] else None
        remote = json.loads(row["remote"]) if row["remote"] else None
        with self.db.transaction():
            if choice == "keep_remote" and remote is not None:
                self.repo.write_envelope(remote, origin_override=remote.get("origin"), action="sync-resolve")
                self._set_base(remote["id"], int(remote["revision"]), remote["checksum"])
            elif choice == "keep_local" and remote is not None:
                # Make the remote checksum the base so the local copy counts as "changed locally" and is pushed.
                self._set_base(remote["id"], int(remote["revision"]), remote["checksum"])
                cur = self.repo.find(row["object_id"], include_deleted=True)
                if cur is not None and cur.revision <= int(remote["revision"]):
                    # Bump the revision so other devices treat the kept copy as the newer one.
                    env = cur.envelope()
                    env["revision"] = int(remote["revision"]) + 1
                    env["updated_at"] = utc_now_iso()
                    self.repo.write_envelope(env, origin_override=env["origin"], action="sync-resolve")
            elif choice == "keep_both" and remote is not None:
                copy = dict(remote)
                copy["id"] = new_id()
                copy["revision"] = 1
                copy["created_at"] = copy["updated_at"] = utc_now_iso()
                self.repo.write_envelope(copy, origin_override="synced", action="sync-resolve")
                self._set_base(remote["id"], int(remote["revision"]), remote["checksum"])
            else:
                raise SyncError("Unknown conflict resolution.")
            self.db.execute("UPDATE sync_conflicts SET status = 'resolved', resolution = ?, resolved_at = ? WHERE id = ?",
                            (choice, utc_now_iso(), conflict_id))
        del local

    # ------------------------------------------------------------------ main
    def sync(self) -> SyncReport:
        report = SyncReport()
        for attempt in range(1, MAX_RETRIES + 1):
            report.attempts = attempt
            try:
                return self._sync_once(report)
            except RemoteChanged:
                log.info("Remote changed during sync; retrying (attempt %d)", attempt)
                report = SyncReport(attempts=attempt)
                continue
        raise SyncError("The cloud copy kept changing during synchronisation. Try again shortly.")

    def _sync_once(self, report: SyncReport) -> SyncReport:
        state, version = self.read_state()
        remote_recs: dict[str, dict] = dict(state.get("records", {}))
        local_envs = self.repo.all_envelopes(include_deleted=True)
        excluded = self._excluded_ids(local_envs)
        local = {e["id"]: e for e in local_envs if e["id"] not in excluded}
        local_all = {e["id"]: e for e in local_envs}
        base = self._base()
        pushes: dict[str, dict] = {}
        pulls: list[dict] = []
        markers_in: list[dict] = []
        new_conflicts = 0

        for rid in sorted(set(local) | set(remote_recs) | excluded):
            L = local.get(rid)
            R = remote_recs.get(rid)
            B = base.get(rid)
            if rid in excluded:
                # Never upload confidential data; replace any older remote copy with a marker.
                if R is not None and not R.get("redacted"):
                    pushes[rid] = {"id": rid, "kind": local_all[rid]["kind"], "redacted": True,
                                   "confidentiality": "confidential", "revision": local_all[rid]["revision"],
                                   "checksum": "redacted"}
                    report.redacted += 1
                continue
            if R is not None and R.get("redacted"):
                markers_in.append(R)
                continue
            if L is not None and R is None:
                pushes[rid] = L
                continue
            if R is not None and L is None:
                if local_all.get(rid) is None:
                    pulls.append(R)
                continue
            assert L is not None and R is not None
            if L["checksum"] == R["checksum"]:
                if B is None or B[1] != L["checksum"]:
                    self._set_base(rid, int(L["revision"]), L["checksum"])
                report.unchanged += 1
                continue
            l_changed = B is None or L["checksum"] != B[1]
            r_changed = B is None or R["checksum"] != B[1]
            if B is None:
                # First sync of a record present on both sides with different content: let the user decide.
                if self._record_conflict(rid, L["kind"], L, R):
                    new_conflicts += 1
                continue
            if l_changed and not r_changed:
                pushes[rid] = L
            elif r_changed and not l_changed:
                pulls.append(R)
            else:
                if self._record_conflict(rid, L["kind"], L, R):
                    new_conflicts += 1

        # Immutable resume versions: union.
        local_versions = self._local_versions()
        remote_versions: dict[str, dict] = dict(state.get("versions", {}))
        excluded_variants = excluded
        push_versions = {vid: v for vid, v in local_versions.items()
                         if vid not in remote_versions and v["variant_id"] not in excluded_variants}
        pull_versions = [v for vid, v in remote_versions.items() if vid not in local_versions]

        if pushes or push_versions or not state.get("generation"):
            new_records = dict(remote_recs)
            new_records.update(pushes)
            new_versions = dict(remote_versions)
            new_versions.update(push_versions)
            new_state = {"format": FORMAT_ID, "format_version": FORMAT_VERSION,
                         "generation": int(state.get("generation", 0)) + 1, "updated_at": utc_now_iso(),
                         "updated_by": self.device_id, "app_version": __version__,
                         "encrypted": bool(self.passphrase), "records": new_records, "versions": new_versions}
            self.remote.write(STATE_NAME, self._encode(new_state), expected_version=version)
            for rid, env in pushes.items():
                if not env.get("redacted"):
                    self._set_base(rid, int(env["revision"]), env["checksum"])
            report.pushed = sum(1 for e in pushes.values() if not e.get("redacted"))
            report.versions_pushed = len(push_versions)

        if pulls or pull_versions or markers_in:
            with self.db.transaction():
                self.db.execute("PRAGMA defer_foreign_keys = ON")
                for env in sorted(pulls, key=lambda e: (e.get("parent_id") is not None, e["id"])):
                    self.repo.write_envelope(env, origin_override=env.get("origin"), action="sync")
                    self._set_base(env["id"], int(env["revision"]), env["checksum"])
                for m in markers_in:
                    rec = self.repo.find(m["id"], include_deleted=True)
                    if rec is not None and rec.confidentiality != Confidentiality.CONFIDENTIAL:
                        self.repo.update(rec.id, confidentiality=Confidentiality.CONFIDENTIAL, audit_action="sync-classify")
                for v in pull_versions:
                    if self.db.query_one("SELECT 1 FROM records WHERE id = ?", (v["variant_id"],)) is None:
                        continue
                    self.db.execute(
                        "INSERT OR IGNORE INTO variant_versions (id, variant_id, version_no, created_at, label, settings,"
                        " document, source_revisions, template_id, template_version, checksum)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (v["id"], v["variant_id"], v["version_no"], v["created_at"], v.get("label", ""), v["settings"],
                         v["document"], v["source_revisions"], v["template_id"], v["template_version"], v["checksum"]))
                    report.versions_pulled += 1
            report.pulled = len(pulls)
        report.conflicts = len(self.open_conflicts())
        if new_conflicts:
            report.notes.append(f"{new_conflicts} new conflict(s) recorded; nothing was overwritten.")
        return report

    def remote_summary(self) -> dict[str, Any]:
        state, version = self.read_state()
        return {"generation": state.get("generation", 0), "records": len(state.get("records", {})),
                "versions": len(state.get("versions", {})), "updated_at": state.get("updated_at", ""),
                "updated_by": state.get("updated_by", ""), "encrypted": state.get("encrypted", False),
                "remote_version": version}
