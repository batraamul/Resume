"""Headless command-line tools (for scripting, verification and recovery).

    python -m ris.cli templates
    python -m ris.cli workspaces
    python -m ris.cli sample-export --out ./examples
    python -m ris.cli export --variant "My resume" --formats docx,pdf --out ./exports
    python -m ris.cli backup [--encrypt]
    python -m ris.cli restore FILE
    python -m ris.cli integrity
    python -m ris.cli analyse --vacancy-file notice.txt
    python -m ris.cli import-json profile.json
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import date
from pathlib import Path

from ris.config import AppConfig
from ris.domain.enums import RecordKind, label


def _open_workspace(name: str | None, sample: bool = False):
    from ris.storage.workspace import WorkspaceManager

    mgr = WorkspaceManager(AppConfig.load())
    if sample:
        entry = mgr.ensure_sample()
    elif name:
        entry = next((w for w in mgr.entries() if w.name == name), None)
        if entry is None:
            raise SystemExit(f"No workspace called {name!r}. Use 'workspaces' to list them.")
    else:
        entry = mgr.active_entry()
    return mgr.open(entry)


def cmd_templates(_a) -> int:
    from ris.rendering.specs import TemplateLibrary

    for t in TemplateLibrary().list():
        print(f"{t.id:26s} v{t.version:7s} {t.name:28s} {'ATS-safe' if t.ats_safe else ''}")
    return 0


def cmd_workspaces(_a) -> int:
    from ris.storage.workspace import WorkspaceManager

    mgr = WorkspaceManager(AppConfig.load())
    for w in mgr.entries():
        print(f"{w.name:32s} {'(sample) ' if w.is_sample else ''}{mgr.folder_of(w)}")
    return 0


def cmd_sample_export(a) -> int:
    """Export the fictional sample with every template (examples and verification)."""
    from ris.domain.models import Variant
    from ris.rendering.export import ExportOptions, ExportService
    from ris.rendering.specs import TemplateLibrary

    ws = _open_workspace(None, sample=True)
    try:
        lib = TemplateLibrary()
        svc = ExportService(ws, lib)
        out = Path(a.out)
        base = ws.repo.list(RecordKind.VARIANT)[0]
        failures = 0
        templates = [lib.get(a.template)] if a.template else lib.list()
        for spec in templates:
            mode = spec.recommended_modes[0] if spec.recommended_modes else "general_professional"
            data = base.payload()
            data.update({"name": f"Sample - {spec.name}", "template_id": spec.id, "mode": mode,
                         "length": "full" if mode in ("academic_cv", "government_biodata") else "two_pages",
                         "max_pages": None, "official_particulars": ["date_of_birth", "present_pay_level"]
                         if mode == "government_biodata" else []})
            rec = next((r for r in ws.repo.list(RecordKind.VARIANT) if r.data.name == data["name"]), None)
            rec = ws.repo.update(rec.id, Variant.model_validate(data)) if rec else ws.repo.create(RecordKind.VARIANT, data)
            res = svc.export_variant(rec.id, ExportOptions(formats=tuple(a.formats.split(",")), folder=out,
                                                           pdf_engine=a.engine, filename=f"sample_{spec.id}",
                                                           acknowledge_warnings=True))
            status = "OK " if res.ok else "FAIL"
            failures += 0 if res.ok else 1
            pages = res.report.page_count if res.report else "-"
            print(f"[{status}] {spec.id:26s} pages={pages} engine={res.engine or '-'} {res.message}")
            if not res.ok and res.report:
                for c in res.report.failures:
                    print(f"        {c.name}: {c.message} {c.details[:3]}")
        return 1 if failures else 0
    finally:
        ws.close()


def cmd_export(a) -> int:
    from ris.rendering.export import ExportOptions, ExportService
    from ris.rendering.specs import TemplateLibrary

    ws = _open_workspace(a.workspace)
    try:
        var = next((v for v in ws.repo.list(RecordKind.VARIANT) if v.data.name == a.variant), None)
        if var is None:
            print("Variants:", ", ".join(v.data.name for v in ws.repo.list(RecordKind.VARIANT)))
            return 2
        res = ExportService(ws, TemplateLibrary()).export_variant(
            var.id, ExportOptions(formats=tuple(a.formats.split(",")), folder=Path(a.out), pdf_engine=a.engine,
                                  acknowledge_warnings=a.acknowledge))
        print(res.message)
        if res.review and res.review.items:
            for i in res.review.items:
                print(f"  review [{i.kind}] {i.title}: {i.detail}")
        if res.report:
            for c in res.report.checks:
                print(f"  {c.status:5s} {c.name}: {c.message}")
        for f in res.files:
            print(f"  {f.path} ({f.size} bytes, sha256 {f.sha256[:12]}…)")
        return 0 if res.ok else 1
    finally:
        ws.close()


def cmd_backup(a) -> int:
    from ris.backup.backup import BackupService

    ws = _open_workspace(a.workspace)
    try:
        pw = getpass.getpass("Backup passphrase: ") if a.encrypt else None
        info = BackupService(ws).create(reason="manual", passphrase=pw)
        print(f"Backup written: {info.path}")
        return 0
    finally:
        ws.close()


def cmd_restore(a) -> int:
    from ris.backup.backup import BackupService

    ws = _open_workspace(a.workspace)
    try:
        svc = BackupService(ws)
        pw = getpass.getpass("Backup passphrase (leave empty if not encrypted): ") or None
        v = svc.verify(Path(a.file), pw)
        if not v.ok:
            print("Verification failed:", "; ".join(v.problems))
            return 1
        res = svc.restore(Path(a.file), pw)
        print(f"Restored. Previous data saved as {res['pre_restore_snapshot']}")
        return 0
    finally:
        ws.close()


def cmd_integrity(a) -> int:
    from ris.backup.integrity import check_database

    ws = _open_workspace(a.workspace)
    try:
        rep = check_database(ws.db)
        print(rep.summary())
        for p in rep.problems:
            print("  problem:", p)
        for w in rep.warnings:
            print("  note:", w)
        return 0 if rep.ok else 1
    finally:
        ws.close()


def cmd_analyse(a) -> int:
    from ris.domain.models import Vacancy
    from ris.intelligence.analysis import analyse
    from ris.services.importers import vacancy_from_file
    from ris.services.profile import ProfileService

    ws = _open_workspace(a.workspace, sample=a.sample)
    try:
        fields = vacancy_from_file(Path(a.vacancy_file))
        vac = Vacancy.model_validate({k: v for k, v in fields.items() if k in Vacancy.model_fields})
        res = analyse(ProfileService(ws.repo).snapshot(), vac, today=date.today())
        for r in res.results:
            print(f"[{label(r.status):34s}] {'M' if r.requirement.mandatory else ' '} {r.requirement.text[:90]}")
        print()
        print("\n".join(res.assessment.explain()))
        return 0
    finally:
        ws.close()


def cmd_import_json(a) -> int:
    from ris.services import portable

    ws = _open_workspace(a.workspace)
    try:
        prev = portable.preview(ws.repo, portable.load_payload(Path(a.file)))
        print(json.dumps(prev.counts, indent=1))
        rep = portable.commit(ws.repo, prev)
        print(f"Imported {rep.created} record(s); skipped {rep.skipped}. Imported facts await your confirmation.")
        return 0
    finally:
        ws.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ris-cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("templates").set_defaults(fn=cmd_templates)
    sub.add_parser("workspaces").set_defaults(fn=cmd_workspaces)
    s = sub.add_parser("sample-export")
    s.add_argument("--out", required=True)
    s.add_argument("--template")
    s.add_argument("--formats", default="docx,pdf")
    s.add_argument("--engine", default="auto", choices=["auto", "libreoffice", "builtin"])
    s.set_defaults(fn=cmd_sample_export)
    e = sub.add_parser("export")
    e.add_argument("--workspace")
    e.add_argument("--variant", required=True)
    e.add_argument("--formats", default="docx,pdf")
    e.add_argument("--out", required=True)
    e.add_argument("--engine", default="auto", choices=["auto", "libreoffice", "builtin"])
    e.add_argument("--acknowledge", action="store_true", help="acknowledge sensitive-content warnings")
    e.set_defaults(fn=cmd_export)
    b = sub.add_parser("backup")
    b.add_argument("--workspace")
    b.add_argument("--encrypt", action="store_true")
    b.set_defaults(fn=cmd_backup)
    r = sub.add_parser("restore")
    r.add_argument("file")
    r.add_argument("--workspace")
    r.set_defaults(fn=cmd_restore)
    i = sub.add_parser("integrity")
    i.add_argument("--workspace")
    i.set_defaults(fn=cmd_integrity)
    an = sub.add_parser("analyse")
    an.add_argument("--vacancy-file", required=True)
    an.add_argument("--workspace")
    an.add_argument("--sample", action="store_true")
    an.set_defaults(fn=cmd_analyse)
    ij = sub.add_parser("import-json")
    ij.add_argument("file")
    ij.add_argument("--workspace")
    ij.set_defaults(fn=cmd_import_json)
    args = p.parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
