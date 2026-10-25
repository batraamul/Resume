"""Step 4 — a PDF with ReportLab."""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

from export_docx import period
from model import Profile


def export_pdf(profile: Profile, path: Path) -> Path:
    styles = getSampleStyleSheet()
    story = [Paragraph(escape(profile.name), styles["Title"])]
    for line in (profile.headline, profile.email):
        if line:
            story.append(Paragraph(escape(line), styles["Normal"]))
    if profile.summary:
        story += [Spacer(1, 4 * mm), Paragraph("Professional Summary", styles["Heading2"]),
                  Paragraph(escape(profile.summary), styles["Normal"])]
    if profile.jobs:
        story.append(Paragraph("Experience", styles["Heading2"]))
        for job in profile.jobs:
            story.append(Paragraph(f"<b>{escape(job.title)}, {escape(job.organisation)}</b> — "
                                   f"{escape(period(job.start, job.end))}", styles["Normal"]))
            if job.achievements:
                story.append(ListFlowable([ListItem(Paragraph(escape(a), styles["Normal"]))
                                           for a in job.achievements], bulletType="bullet"))
    if profile.skills:
        story += [Paragraph("Skills", styles["Heading2"]), Paragraph(escape(", ".join(profile.skills)),
                                                                     styles["Normal"])]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=16 * mm, bottomMargin=16 * mm, title=f"{profile.name} — Resume").build(story)
    return path
