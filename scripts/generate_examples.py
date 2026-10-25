#!/usr/bin/env python3
"""Export the fictional sample profile with every template into examples/ (DOCX + PDF), plus contact sheets.

    python scripts/generate_examples.py [--engine builtin|libreoffice|auto] [--out examples]

Every file passes the export validation before it is written. Uses a temporary sample workspace;
real user data is never read.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="builtin", choices=["builtin", "libreoffice", "auto"])
    ap.add_argument("--out", default=str(ROOT / "examples"))
    args = ap.parse_args()
    from ris.domain.enums import RecordKind
    from ris.domain.models import Variant
    from ris.rendering.export import ExportOptions, ExportService
    from ris.rendering.specs import TemplateLibrary
    from ris.services.sample import load_sample_profile
    from ris.storage.workspace import Workspace

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for old in [*out.glob("example_*.docx"), *out.glob("example_*.pdf")]:
        old.unlink()  # generated files only; the export service never overwrites, so clear the previous run
    failures = 0
    lines = ["# Example documents", "", "Generated from the **fictional** sample profile (Dr. Anika Sharma is not a "
             "real person). Every file passed the automated export validation; see docs/TEST_REPORT.md for which "
             "pages were also inspected visually.", "", "| Template | Mode | Pages | Engine | Files |", "|---|---|---|---|---|"]
    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace(Path(tmp) / "ws", "Examples", is_sample=True).open()
        try:
            load_sample_profile(ws)
            lib = TemplateLibrary()
            svc = ExportService(ws, lib, today=date.today())
            base = next(v for v in ws.repo.list(RecordKind.VARIANT) if v.data.mode == "defence_technical")
            for spec in lib.list():
                mode = spec.recommended_modes[0] if spec.recommended_modes else "general_professional"
                full = mode in ("academic_cv", "government_biodata", "research_portfolio", "project_portfolio")
                data = {**base.payload(), "name": f"Example — {spec.name}", "template_id": spec.id, "mode": mode,
                        "length": "full" if full else "two_pages", "max_pages": None,
                        "official_particulars": ["present_pay_level"] if mode == "government_biodata" else [],
                        "publication_scope": "all" if mode == "research_portfolio" else "relevant"}
                rec = ws.repo.create(RecordKind.VARIANT, Variant.model_validate(data))
                res = svc.export_variant(rec.id, ExportOptions(formats=("docx", "pdf"), folder=out,
                                                               pdf_engine=args.engine, filename=f"example_{spec.id}",
                                                               acknowledge_warnings=True))
                if not res.ok:
                    failures += 1
                    print(f"[FAIL] {spec.id}: {res.message}")
                    continue
                pages = res.report.page_count
                print(f"[ OK ] {spec.id:24s} {pages} page(s) via {res.engine}")
                files = ", ".join(f"`{f.path.name}`" for f in res.files)
                lines.append(f"| {spec.name} | {mode} | {pages} | {res.engine} | {files} |")
        finally:
            ws.close()
    sheet = _contact_sheet(out, "overview_first_pages" + ("" if args.engine == "builtin" else f"_{args.engine}") + ".png")
    if sheet:
        lines += ["", f"`{sheet.name}` shows the first page of every template side by side."]
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if failures else 0


def _contact_sheet(out: Path, name: str) -> Path | None:
    """First page of every example PDF on one image (needs `pdftoppm` from Poppler; skipped otherwise)."""
    import shutil
    import subprocess

    from PIL import Image, ImageDraw

    from ris.rendering.specs import TemplateLibrary

    if shutil.which("pdftoppm") is None:
        print("pdftoppm not found; contact sheet skipped.")
        return None
    thumbs = []
    with tempfile.TemporaryDirectory() as tmp:
        for spec in TemplateLibrary().list():
            pdf = out / f"example_{spec.id}.pdf"
            if not pdf.exists():
                continue
            stem = Path(tmp) / spec.id
            subprocess.run(["pdftoppm", "-r", "40", "-f", "1", "-l", "1", "-png", str(pdf), str(stem)],
                           check=True, capture_output=True, timeout=60)
            png = sorted(Path(tmp).glob(f"{spec.id}-*.png"))[0]
            thumbs.append((spec.id, Image.open(png).convert("RGB")))
    if not thumbs:
        return None
    w, h = thumbs[0][1].size
    cols = 5
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + 10) + 10, rows * (h + 30) + 10), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (tid, im) in enumerate(thumbs):
        x, y = 10 + (i % cols) * (w + 10), 10 + (i // cols) * (h + 30)
        sheet.paste(im.resize((w, h)), (x, y + 20))
        draw.text((x, y + 4), tid, fill="black")
    path = out / name
    sheet.save(path)
    return path


if __name__ == "__main__":
    sys.exit(main())
