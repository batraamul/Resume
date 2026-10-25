"""Export service: compose → review → fit → render → validate → save version → log.

An export is reported successful only after validation passes. Files are
written to a private temporary folder first and moved to the destination
under a new, collision-free name, so earlier exports are never overwritten.
"""

from __future__ import annotations

import io
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from ris.composition.composer import ComposeContext, ResumeComposer, claims_by_bullet
from ris.composition.ir import ResumeDocument
from ris.domain.enums import Confidentiality, RecordKind, Verification
from ris.domain.models import Variant
from ris.errors import ConversionError, ExportError, NotFound
from ris.intelligence import disclosure
from ris.intelligence.analysis import VacancyAnalysis, analyse, target_relevance
from ris.intelligence.ats import QualityReport, check_quality
from ris.rendering.docx_renderer import render_docx
from ris.rendering.layout import plan_layout
from ris.rendering.libreoffice import convert_docx_to_pdf, find_soffice
from ris.rendering.pdf_renderer import PdfRenderer
from ris.rendering.specs import TemplateLibrary, TemplateSpec
from ris.rendering.text_export import render_text
from ris.rendering.validation import ValidationReport, confidential_phrases_from, validate_outputs
from ris.security.tempfiles import private_tempdir
from ris.services.profile import ProfileService, ProfileSnapshot
from ris.services.variants import VariantService
from ris.util import new_id, safe_filename, sha256_file, utc_now_iso

log = logging.getLogger(__name__)


@dataclass
class ReviewItem:
    kind: str  # unconfirmed | disclosure | identifier | sensitive
    record_id: str | None
    title: str
    detail: str
    blocking: bool


@dataclass
class ReviewSummary:
    items: list[ReviewItem] = field(default_factory=list)

    @property
    def blocking(self) -> list[ReviewItem]:
        return [i for i in self.items if i.blocking]

    @property
    def warnings(self) -> list[ReviewItem]:
        return [i for i in self.items if not i.blocking]

    @property
    def ok(self) -> bool:
        return not self.blocking


@dataclass
class Composed:
    doc: ResumeDocument
    spec: TemplateSpec
    snapshot: ProfileSnapshot
    analysis: VacancyAnalysis | None
    variant: Variant


@dataclass
class ExportOptions:
    formats: tuple[str, ...] = ("docx", "pdf")
    folder: Path | None = None
    filename: str | None = None
    pdf_engine: str = "auto"  # auto | libreoffice | builtin
    fit_to_pages: bool = True
    acknowledge_warnings: bool = False
    label: str = ""


@dataclass
class ExportedFile:
    path: Path
    format: str
    size: int
    sha256: str
    page_count: int | None = None
    engine: str = ""


@dataclass
class ExportOutcome:
    ok: bool
    message: str
    files: list[ExportedFile] = field(default_factory=list)
    report: ValidationReport | None = None
    review: ReviewSummary | None = None
    document: ResumeDocument | None = None
    version_id: str | None = None
    engine: str = ""
    quality: QualityReport | None = None


def unique_path(folder: Path, base: str, ext: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{base}.{ext}"
    n = 2
    while p.exists():
        p = folder / f"{base} ({n}).{ext}"
        n += 1
    return p


class ExportService:
    def __init__(self, workspace, templates: TemplateLibrary, *, soffice_path: str | None = None,
                 today: date | None = None) -> None:
        self.ws = workspace
        self.repo = workspace.repo
        self.templates = templates
        self.soffice_path = soffice_path
        self.today = today
        self.variants = VariantService(self.repo)

    # ------------------------------------------------------------------ composition
    def _analysis(self, snap: ProfileSnapshot, v: Variant) -> tuple[VacancyAnalysis | None, object, object]:
        target = snap.get(v.target_id) if v.target_id else None
        target = target if (target is not None and target.kind == RecordKind.CAREER_TARGET) else None
        vac = snap.get(v.vacancy_id) if v.vacancy_id else None
        vac = vac if (vac is not None and vac.kind == RecordKind.VACANCY) else None
        if vac is None:
            return None, target, None
        weights = self.ws.settings.get("scoring.weights")
        return analyse(snap, vac.data, target=target.data if target else None, weights=weights,
                       today=self.today), target, vac

    def compose(self, variant: Variant, snapshot: ProfileSnapshot | None = None,
                variant_id: str | None = None) -> Composed:
        snap = snapshot or ProfileService(self.repo).snapshot()
        spec = self.templates.get(variant.template_id)
        analysis, target, vac = self._analysis(snap, variant)
        if analysis is not None:
            relevance = analysis.relevance
        else:
            relevance = target_relevance(target.data if target else None)
        if variant_id is None:
            variant_id = next((r.id for r in snap.of(RecordKind.VARIANT) if r.data is variant), None)
        claim_recs = snap.kids(variant_id, RecordKind.CLAIM) if variant_id else []
        ctx = ComposeContext(
            snapshot=snap, variant=variant, template_id=spec.id, template_version=spec.version,
            date_style=spec.entry.date_style, photo_allowed=spec.photo.allowed, relevance=relevance,
            approved_claims=claims_by_bullet(claim_recs),
            requirements_matrix=analysis.matrix() if analysis is not None else None,
            emphasis=analysis.emphasis if analysis is not None else {},
            target=target, vacancy_title=vac.data.title if vac else "", vacancy=vac.data if vac else None,
            mandatory_gaps=analysis.mandatory_gaps() if analysis is not None else [],
            is_sample=bool(getattr(self.ws, "is_sample", False)),
            today=self.today or date.today(),
        )
        doc = ResumeComposer(ctx).compose()
        return Composed(doc, spec, snap, analysis, variant)

    def compose_record(self, variant_id: str) -> Composed:
        snap = ProfileService(self.repo).snapshot()
        rec = snap.get(variant_id)
        if rec is None or rec.kind != RecordKind.VARIANT:
            raise NotFound("The resume variant no longer exists.")
        return self.compose(rec.data, snap, variant_id=rec.id)

    # ------------------------------------------------------------------ review
    @staticmethod
    def review(doc: ResumeDocument, snap: ProfileSnapshot) -> ReviewSummary:
        items: list[ReviewItem] = []
        for rid in sorted(doc.all_source_ids()):
            rec = snap.get(rid)
            if rec is None:
                continue
            if rec.kind == RecordKind.CLAIM:
                continue
            if snap.effective_verification(rec) == Verification.UNCONFIRMED:
                items.append(ReviewItem("unconfirmed", rid, rec.title, "Awaiting your confirmation.", True))
            conf = snap.effective_confidentiality(rec)
            if conf == Confidentiality.REVIEW:
                items.append(ReviewItem("disclosure", rid, rec.title,
                                        "Requires a disclosure review before it can appear in an exported document.",
                                        True))
            elif conf == Confidentiality.CONFIDENTIAL:  # defence in depth: composer should never include these
                items.append(ReviewItem("disclosure", rid, rec.title, "Confidential — must not be exported.", True))
        for f in disclosure.scan_document(doc):
            rid = f.source_ids[0] if f.source_ids else None
            title = snap.get(rid).title if (rid and snap.get(rid)) else f.category
            items.append(ReviewItem("identifier" if f.severity == disclosure.BLOCK else "sensitive", rid, title,
                                    f"{f.message} …{f.excerpt}…", f.severity == disclosure.BLOCK))
        return ReviewSummary(items)

    # ------------------------------------------------------------------ rendering helpers
    def _builtin_pages(self, doc: ResumeDocument, spec: TemplateSpec) -> tuple[int, set[str]]:
        data, res = PdfRenderer(plan_layout(doc, spec)).render_bytes()
        del data
        return res.page_count, res.missing_glyphs

    def _libreoffice_pages(self, doc: ResumeDocument, spec: TemplateSpec, soffice) -> int:
        try:
            with private_tempdir("fit") as tmp:
                d = render_docx(plan_layout(doc, spec), tmp / "fit.docx")
                pdf = convert_docx_to_pdf(d, tmp / "fit.pdf", soffice)
                return len(PdfReader(str(pdf)).pages)
        except ConversionError:
            return self._builtin_pages(doc, spec)[0]

    def preview_pdf(self, doc: ResumeDocument, spec: TemplateSpec, engine: str = "builtin") -> tuple[bytes, int, str, list[str]]:
        """Render a preview PDF in memory. Returns (bytes, pages, engine used, warnings)."""
        layout = plan_layout(doc, spec)
        warnings: list[str] = []
        soffice = find_soffice(self.soffice_path) if engine in ("auto", "libreoffice") else None
        if engine == "libreoffice" and soffice is None:
            warnings.append("LibreOffice is not installed; the preview uses the built-in PDF engine.")
        if soffice is not None and engine in ("auto", "libreoffice"):
            try:
                with private_tempdir("preview") as tmp:
                    d = render_docx(layout, tmp / "preview.docx")
                    pdf = convert_docx_to_pdf(d, tmp / "preview.pdf", soffice)
                    data = pdf.read_bytes()
                pages = len(PdfReader(io.BytesIO(data)).pages)
                return data, pages, "libreoffice", warnings
            except ConversionError as exc:
                warnings.append(f"{exc.user_message} The preview uses the built-in PDF engine.")
        data, res = PdfRenderer(layout).render_bytes()
        return data, res.page_count, "builtin", warnings + res.warnings

    # ------------------------------------------------------------------ fit to page limit
    def fit(self, doc: ResumeDocument, spec: TemplateSpec, target_pages: int, page_counter=None) -> tuple[ResumeDocument, int]:
        counter = page_counter or (lambda d: self._builtin_pages(d, spec)[0])
        doc = doc.model_copy(deep=True)
        pages = counter(doc)
        if pages <= target_pages:
            return doc, pages
        # Presentation adjustments first (no content removed).
        for change in ({"spacing": "compact"}, {"font_scale": round(min(doc.font_scale, 0.96), 2)},
                       {"font_scale": round(min(doc.font_scale, 0.92), 2)}):
            if all(getattr(doc, k) == v for k, v in change.items()):
                continue
            for k, v in change.items():
                setattr(doc, k, v)
            pages = counter(doc)
            if pages <= target_pages:
                doc.trimmed.append(f"Fit to {target_pages} page(s): adjusted spacing/type size.")
                return doc, pages
        for _ in range(60):
            what = _trim_once(doc)
            if what is None:
                break
            doc.trimmed.append(f"Fit to {target_pages} page(s): removed {what}")
            pages = counter(doc)
            if pages <= target_pages:
                break
        return doc, pages

    # ------------------------------------------------------------------ export
    def export_variant(self, variant_id: str, options: ExportOptions, *, version_id: str | None = None) -> ExportOutcome:
        rec = self.repo.find(variant_id)
        if rec is None or rec.kind != RecordKind.VARIANT:
            raise NotFound("The resume variant no longer exists.")
        snap = ProfileService(self.repo).snapshot()
        if version_id:
            doc, settings = self.variants.load_document(version_id)
            spec = TemplateSpec.model_validate(settings["template_spec"])
            review = self.review(doc, snap)
            # Re-exports reproduce a saved version; only items that became confidential block it.
            review.items = [i for i in review.items if i.kind in ("disclosure", "identifier")
                            and snap.get(i.record_id or "") is not None
                            and snap.effective_confidentiality(snap.get(i.record_id)) == Confidentiality.CONFIDENTIAL]
            analysis = None
        else:
            comp = self.compose(rec.data, snap, variant_id=rec.id)
            doc, spec, analysis = comp.doc, comp.spec, comp.analysis
            review = self.review(doc, snap)
        blocking = review.blocking
        if not options.acknowledge_warnings:
            blocking = blocking + [w for w in review.warnings if w.kind == "sensitive"]
        if blocking:
            return ExportOutcome(False, "Export needs your review first: resolve or acknowledge the listed items.",
                                 review=review, document=doc)
        target = doc.max_pages or {"one_page": 1, "two_pages": 2}.get(doc.length)
        if not version_id and options.fit_to_pages and target:
            doc, _ = self.fit(doc, spec, target)
            soffice = find_soffice(self.soffice_path) if options.pdf_engine in ("auto", "libreoffice") else None
            if soffice is not None and "pdf" in options.formats:
                # Confirm with the engine that will produce the final PDF; continue trimming if needed.
                doc, _ = self.fit(doc, spec, target, page_counter=lambda d: self._libreoffice_pages(d, spec, soffice))
        return self._render_and_finish(rec, doc, spec, snap, options, analysis, review, save_version=not version_id,
                                       version_id=version_id)

    def _render_and_finish(self, rec, doc: ResumeDocument, spec: TemplateSpec, snap: ProfileSnapshot,
                           options: ExportOptions, analysis: VacancyAnalysis | None, review: ReviewSummary,
                           *, save_version: bool, version_id: str | None,
                           document_kind: str = "resume") -> ExportOutcome:
        formats = [f for f in options.formats if f in ("docx", "pdf", "txt")]
        if not formats:
            raise ExportError("Choose at least one format to export.")
        folder = Path(options.folder) if options.folder else self.ws.exports_dir
        base = safe_filename(options.filename or self._default_name(doc, rec))
        engine_used = ""
        missing_glyphs: set[str] = set()
        with private_tempdir("export") as tmp:
            layout = plan_layout(doc, spec)
            docx_path = render_docx(layout, tmp / "out.docx")
            pdf_path = None
            if "pdf" in formats:
                engine = options.pdf_engine
                soffice = find_soffice(self.soffice_path) if engine in ("auto", "libreoffice") else None
                if engine == "libreoffice" and soffice is None:
                    return ExportOutcome(False, "LibreOffice was selected as the PDF engine but is not installed. "
                                         "Install LibreOffice or choose the built-in PDF engine.", document=doc,
                                         review=review)
                if soffice is not None:
                    try:
                        pdf_path = convert_docx_to_pdf(docx_path, tmp / "out.pdf", soffice)
                        engine_used = "libreoffice"
                    except ConversionError as exc:
                        if engine == "libreoffice":
                            return ExportOutcome(False, exc.user_message + " " + exc.detail[:200], document=doc,
                                                 review=review)
                        log.warning("LibreOffice conversion failed; using built-in renderer")
                if pdf_path is None:
                    res = PdfRenderer(layout).render(tmp / "out.pdf")
                    pdf_path = tmp / "out.pdf"
                    engine_used = "builtin"
                    missing_glyphs = res.missing_glyphs
            txt_path = None
            if "txt" in formats:
                txt_path = tmp / "out.txt"
                txt_path.write_text(render_text(doc), encoding="utf-8")
            footer = [layout.footer.left_text, layout.footer.note]
            report = validate_outputs(
                doc, docx_path=docx_path, pdf_path=pdf_path, txt_path=txt_path,
                confidential_phrases=confidential_phrases_from(snap), footer_strings=footer, engine=engine_used,
                missing_glyphs=missing_glyphs, check_chronology=doc.doc_type == "resume",
            )
            quality = check_quality(doc, spec, analysis.relevance if analysis else None, report.page_count)
            if not report.ok:
                return ExportOutcome(False, "Export stopped: the generated files failed validation. Nothing was saved.",
                                     report=report, review=review, document=doc, engine=engine_used, quality=quality)
            if save_version and rec is not None and rec.kind == RecordKind.VARIANT:
                info = self.variants.save_version(rec.id, doc, settings=rec.payload(),
                                                  template_spec=spec.model_dump(mode="json"),
                                                  label=options.label or "Exported")
                version_id = info.id
            files: list[ExportedFile] = []
            produced = [("docx", docx_path)] if "docx" in formats else []
            if pdf_path is not None:
                produced.append(("pdf", pdf_path))
            if txt_path is not None:
                produced.append(("txt", txt_path))
            for fmt, src in produced:
                dest = unique_path(folder, base, fmt)
                shutil.move(str(src), str(dest))
                ef = ExportedFile(dest, fmt, dest.stat().st_size, sha256_file(dest),
                                  page_count=report.page_count if fmt == "pdf" else None,
                                  engine=engine_used if fmt == "pdf" else ("python-docx" if fmt == "docx" else "text"))
                files.append(ef)
                self._log_export(document_kind, rec.id if rec is not None else None, version_id, ef, report,
                                 redacted=bool(getattr(rec.data, "redacted", False)) if rec is not None else False)
        msg = "Export complete and validated." if not report.warnings else \
            f"Export complete with {len(report.warnings)} warning(s); review them."
        return ExportOutcome(True, msg, files=files, report=report, review=review, document=doc,
                             version_id=version_id, engine=engine_used, quality=quality)

    def export_document(self, doc: ResumeDocument, spec: TemplateSpec, options: ExportOptions, *,
                        document_kind: str, source_id: str | None = None) -> ExportOutcome:
        """Export a composed non-variant document (cover letter, portfolio)."""
        snap = ProfileService(self.repo).snapshot()
        review = self.review(doc, snap)
        blocking = review.blocking + ([] if options.acknowledge_warnings else
                                      [w for w in review.warnings if w.kind == "sensitive"])
        if blocking:
            return ExportOutcome(False, "Export needs your review first.", review=review, document=doc)
        src = self.repo.find(source_id) if source_id else None
        return self._render_and_finish(src, doc, spec, snap, options, None, review, save_version=False,
                                       version_id=None, document_kind=document_kind)

    def _default_name(self, doc: ResumeDocument, rec) -> str:
        pattern = self.ws.settings.get("export.filename_pattern") or "{name} - {variant} - {date}"
        variant_name = getattr(rec.data, "name", "") if rec is not None else doc.doc_type
        try:
            return pattern.format(name=doc.name or "Resume", variant=variant_name or doc.mode,
                                  date=date.today().isoformat(), template=doc.template_id)
        except (KeyError, IndexError, ValueError):
            return f"{doc.name or 'Resume'} - {date.today().isoformat()}"

    def _log_export(self, kind: str, source_id: str | None, version_id: str | None, f: ExportedFile,
                    report: ValidationReport, redacted: bool) -> None:
        self.repo.db.execute(
            "INSERT INTO exports (id, created_at, document_kind, variant_id, version_id, source_id, format, path,"
            " size_bytes, sha256, engine, page_count, status, validation, redacted, removed)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (new_id(), utc_now_iso(), kind, source_id if kind == "resume" else None, version_id, source_id, f.format,
             str(f.path), f.size, f.sha256, f.engine, f.page_count, "warnings" if report.warnings else "valid",
             json.dumps(report.to_dict()), 1 if redacted else 0),
        )


def _drop_section(doc: ResumeDocument, key: str) -> str | None:
    sec = doc.section(key)
    if sec is None:
        return None
    doc.sections.remove(sec)
    return f"section '{sec.title}'"


def _trim_once(doc: ResumeDocument) -> str | None:
    """Remove one low-priority item from the IR. Returns a description, or None if nothing is left to trim.

    Order: unpublished work, low-relevance statements in older roles, extra projects and
    activities, minor sections, then progressively deeper cuts. Every cut is reported.
    """
    def section(key):
        return doc.section(key)

    man = section("manuscripts")
    if man is not None and man.entries:
        e = man.entries.pop()
        if not man.entries:
            doc.sections.remove(man)
        return f"manuscript '{e.title[:60]}'"
    exp = section("experience")
    if exp is not None and exp.layout == "entries":
        candidates = []
        for i, e in enumerate(exp.entries[1:], start=1):
            if len(e.bullets) > 1:
                for j, b in enumerate(e.bullets):
                    candidates.append((b.relevance, -i, -j, i, j))
        if candidates:
            candidates.sort()
            _, _, _, i, j = candidates[0]
            b = exp.entries[i].bullets.pop(j)
            return f"statement '{b.text[:60]}…'"
        for e in exp.entries:
            for c in e.children:
                if c.bullets:
                    b = c.bullets.pop()
                    return f"statement '{b.text[:60]}…'"
    proj = section("projects")
    if proj is not None and len(proj.entries) > 1:
        e = proj.entries.pop()
        return f"project '{e.title[:60]}'"
    for key, keep in (("leadership", 2), ("training", 1), ("awards", 2), ("presentations", 1), ("other_activities", 0)):
        s = section(key)
        if s is not None and len(s.entries) > keep:
            e = s.entries.pop()
            if not s.entries:
                doc.sections.remove(s)
            return f"{s.title.lower()} item '{e.title[:60]}'"
    sk = section("skills")
    if sk is not None and len(sk.skill_groups) > 4:
        g = sk.skill_groups.pop()
        return f"skill group '{g.label}'"
    if proj is not None:
        for e in proj.entries:
            if len(e.bullets) > 1:
                b = e.bullets.pop()
                return f"project statement '{b.text[:60]}…'"
            if e.meta:
                e.meta.pop()
                return f"technology line for '{e.title[:40]}'"
    if exp is not None and exp.layout == "entries" and exp.entries:
        first = exp.entries[0]
        if len(first.bullets) > 3:
            b = first.bullets.pop()
            return f"statement '{b.text[:60]}…'"
        for e in exp.entries:
            if e.meta:
                e.meta.pop()
                return f"tools line for '{e.title[:40]}'"
    comp = section("competencies")
    if comp is not None and len(comp.items) > 6:
        comp.items.pop()
        return "a competency area"
    pubs = section("publications")
    if pubs is not None and len(pubs.entries) > 2:
        e = pubs.entries.pop()
        return f"publication '{e.title[:60]}'"
    # Deeper cuts for tight limits (typically one page).
    for key in ("languages", "other_activities", "memberships", "presentations", "patents", "awards", "training"):
        what = _drop_section(doc, key)
        if what:
            return what
    if exp is not None and exp.layout == "entries":
        for e in exp.entries:
            if e.children:
                c = e.children.pop()
                return f"concurrent responsibility '{c.title[:50]}' (kept in your profile)"
            if e.description:
                e.description = ""
                return f"role summary for '{e.title[:40]}'"
    edu = section("education")
    if edu is not None and edu.layout == "entries":
        for e in edu.entries:
            if e.meta:
                e.meta.pop()
                return f"detail line for '{e.title[:40]}'"
    lead = section("leadership")
    if lead is not None:
        for e in lead.entries:
            if e.bullets:
                e.bullets.pop()
                return f"leadership detail for '{e.title[:40]}'"
            if e.description:
                e.description = ""
                return f"leadership description for '{e.title[:40]}'"
        if len(lead.entries) > 1:
            e = lead.entries.pop()
            return f"leadership item '{e.title[:60]}'"
    if sk is not None:
        if len(sk.skill_groups) > 3:
            g = sk.skill_groups.pop()
            return f"skill group '{g.label}'"
        for g in sk.skill_groups:
            if len(g.items) > 5:
                g.items.pop()
                return f"skill '{g.label}'"
    if pubs is not None and len(pubs.entries) > 1:
        e = pubs.entries.pop()
        return f"publication '{e.title[:60]}'"
    if comp is not None and len(comp.items) > 4:
        comp.items.pop()
        return "a competency area"
    if exp is not None and exp.layout == "entries" and len(exp.entries) > 2:
        e = exp.entries.pop()
        return f"earlier position '{e.title[:50]}' (kept in your profile)"
    if exp is not None and exp.layout == "entries":
        for e in exp.entries[1:]:
            if e.bullets:
                e.bullets.pop()
                return "statement from an earlier position"
        if exp.entries and len(exp.entries[0].bullets) > 2:
            exp.entries[0].bullets.pop()
            return "statement from the current position"
    for key in ("leadership", "projects", "skills", "publications"):
        if section(key) is not None and key != "skills" or (key == "skills" and section("competencies") is not None):
            what = _drop_section(doc, key)
            if what:
                return what
    return None
