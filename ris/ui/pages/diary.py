"""My Professional Diary — the dashboard."""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ris.domain import dates
from ris.domain.enums import ApplicationStatus, RecordKind, Verification, label
from ris.domain.registry import info as kind_info
from ris.services.chronology import check_chronology
from ris.services.completeness import compute
from ris.services.duplicates import find_duplicate_groups
from ris.strings import PAGE_SUBTITLES, RESPONSIBILITY_NOTICE
from ris.ui.widgets.common import Card, Page, StatTile, banner, button, muted

ACTIVE_APPS = {ApplicationStatus.SAVED.value, ApplicationStatus.RESEARCHING.value,
               ApplicationStatus.ELIGIBILITY_REVIEW.value, ApplicationStatus.PREPARING.value,
               ApplicationStatus.APPLIED.value, ApplicationStatus.INTERVIEW.value,
               ApplicationStatus.AWAITING_DECISION.value}


def _greeting(now: datetime) -> str:
    h = now.hour
    return "Good morning" if h < 12 else ("Good afternoon" if h < 17 else "Good evening")


class DiaryPage(Page):
    key = "diary"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "My Professional Diary", PAGE_SUBTITLES["diary"])
        self.greeting = QLabel("")
        self.greeting.setObjectName("SectionTitle")
        self.body.addWidget(self.greeting)
        grid = QGridLayout()
        grid.setSpacing(10)
        self.t_complete = StatTile("–", "Profile completeness")
        self.t_unconfirmed = StatTile("–", "Facts awaiting confirmation")
        self.t_review = StatTile("–", "Items requiring a disclosure review")
        self.t_variants = StatTile("–", "Resume variants")
        self.t_apps = StatTile("–", "Active applications")
        self.t_deadlines = StatTile("–", "Deadlines in the next 30 days")
        for i, t in enumerate((self.t_complete, self.t_unconfirmed, self.t_review, self.t_variants, self.t_apps,
                               self.t_deadlines)):
            grid.addWidget(t, i // 3, i % 3)
        holder = QWidget()
        holder.setLayout(grid)
        self.body.addWidget(holder)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.attention = Card("Needs your attention")
        self.attention_list = QListWidget()
        self.attention_list.setWordWrap(True)
        self.attention_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.attention_list.setAccessibleName("Items needing attention")
        self.attention_list.setMinimumHeight(190)
        self.attention_list.itemActivated.connect(self._open_item)
        self.attention.add(self.attention_list)
        self.attention.add(muted("Double-click or press Enter on an item to open it."))
        row.addWidget(self.attention, 3)
        self.deadlines = Card("Upcoming dates")
        self.deadline_list = QListWidget()
        self.deadline_list.setWordWrap(True)
        self.deadline_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.deadline_list.setAccessibleName("Upcoming dates")
        self.deadline_list.setMinimumHeight(190)
        self.deadline_list.itemActivated.connect(self._open_item)
        self.deadlines.add(self.deadline_list)
        row.addWidget(self.deadlines, 2)
        rw = QWidget()
        rw.setLayout(row)
        self.body.addWidget(rw)
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.recent = Card("Recent documents")
        self.recent_list = QListWidget()
        self.recent_list.setWordWrap(True)
        self.recent_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.recent_list.setAccessibleName("Recent documents")
        self.recent_list.setMinimumHeight(150)
        self.recent.add(self.recent_list)
        row2.addWidget(self.recent, 3)
        quick = Card("Quick actions")
        for text, page in (("Add a position", "experience"), ("Analyse a vacancy", "opportunities"),
                           ("Compose a resume", "studio"), ("Back up now", "backup")):
            quick.add(button(text, on_click=lambda p=page: self.ctx.navigate.emit(p, "")))
        quick.body.addStretch(1)
        row2.addWidget(quick, 2)
        rw2 = QWidget()
        rw2.setLayout(row2)
        self.body.addWidget(rw2)
        self.body.addWidget(banner(RESPONSIBILITY_NOTICE, "info"))
        self.body.addStretch(1)

    def refresh(self) -> None:
        ctx = self.ctx
        snap = ctx.snapshot()
        today = ctx.today or date.today()
        p = snap.personal_data
        name = p.preferred_name or p.full_name
        self.greeting.setText(f"{_greeting(datetime.now())}{', ' + name if name else ''}.")
        c = compute(snap)
        self.t_complete.set(f"{c.overall}%")
        facts = list(snap.facts())
        unconfirmed = [r for r in facts if r.verification == Verification.UNCONFIRMED]
        review = [r for r in facts if r.confidentiality.value == "review"]
        self.t_unconfirmed.set(str(len(unconfirmed)))
        self.t_review.set(str(len(review)))
        variants = snap.of(RecordKind.VARIANT)
        self.t_variants.set(str(len(variants)))
        apps = [a for a in snap.of(RecordKind.APPLICATION) if a.data.status in ACTIVE_APPS]
        self.t_apps.set(str(len(apps)))

        # attention
        self.attention_list.clear()

        def add_att(text: str, page: str, rid: str = "") -> None:
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, (page, rid))
            self.attention_list.addItem(it)

        if unconfirmed:
            add_att(f"Confirm {len(unconfirmed)} fact(s) awaiting confirmation — first: "
                    f"{unconfirmed[0].title or label(unconfirmed[0].kind)}", "record", unconfirmed[0].id)
        if review:
            add_att(f"Complete the disclosure review for {len(review)} item(s) — first: "
                    f"{review[0].title or label(review[0].kind)}", "record", review[0].id)
        for issue in check_chronology(snap, today)[:6]:
            add_att(("⚠ " if issue.severity != "info" else "ℹ ") + issue.message, "record", issue.record_id)
        groups = find_duplicate_groups([r for r in facts if kind_info(r.kind).is_fact and r.kind != RecordKind.BULLET])
        for g in groups[:3]:
            add_att(f"Possible duplicates: '{g[0].title}' appears {len(g)} times", "record", g[0].id)
        vs = ctx.variants()
        for v in variants:
            rep = vs.variant_outdated(v)
            if rep.outdated:
                add_att(f"Resume '{v.data.name}': {rep.summary()}", "library", v.id)
        try:
            conflicts = ctx.sync().engine().open_conflicts() if ctx.settings.get("sync.provider") != "off" else []
        except Exception:  # noqa: BLE001 - sync problems are shown on the sync page
            conflicts = []
        if conflicts:
            add_att(f"{len(conflicts)} synchronisation conflict(s) need your decision", "sync")
        for action in c.top_actions(4):
            add_att("Profile: " + action, "profile")
        if self.attention_list.count() == 0:
            self.attention_list.addItem("Nothing needs attention. Your diary is in order.")

        # deadlines
        self.deadline_list.clear()
        upcoming: list[tuple[str, str, str, str]] = []
        for v in snap.of(RecordKind.VACANCY):
            if v.data.deadline:
                upcoming.append((v.data.deadline, f"Closing date — {v.data.title or 'vacancy'}", "opportunities", v.id))
        for a in snap.of(RecordKind.APPLICATION):
            for field, what in (("deadline", "Deadline"), ("interview_date", "Interview"),
                                ("follow_up_date", "Follow up")):
                d = getattr(a.data, field)
                if d and a.data.status in ACTIVE_APPS:
                    upcoming.append((d, f"{what} — {a.data.vacancy_title or a.data.organisation}", "tracker", a.id))
        soon = 0
        rows = []
        for d, text, page, rid in upcoming:
            pd = dates.parse_or_none(d)
            if pd is None:
                continue
            day = date(pd.year, pd.month or 12, pd.day or 28)
            delta = (day - today).days
            if delta < -7:
                continue
            if 0 <= delta <= 30:
                soon += 1
            when = "overdue" if delta < 0 else ("today" if delta == 0 else f"in {delta} day{'' if delta == 1 else 's'}")
            shown = day.strftime("%d %b %Y") if pd.day else dates.format_date(d)
            rows.append((day, f"{shown} ({when}) · {text}", page, rid))
        for _day, text, page, rid in sorted(rows)[:12]:
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, (page, rid))
            self.deadline_list.addItem(it)
        if not rows:
            self.deadline_list.addItem("No upcoming dates. Add closing dates to vacancies and applications.")
        self.t_deadlines.set(str(soon))

        # recent exports
        self.recent_list.clear()
        rows = ctx.repo.db.query("SELECT created_at, document_kind, format, path, page_count, status FROM exports "
                                 "WHERE removed = 0 ORDER BY created_at DESC LIMIT 6")
        for r in rows:
            from pathlib import Path

            self.recent_list.addItem(f"{r['created_at'][:16].replace('T', ' ')} · {r['format'].upper()} · "
                                     f"{Path(r['path']).name}" + (f" · {r['page_count']} page(s)" if r['page_count'] else ""))
        if not rows:
            self.recent_list.addItem("No documents exported yet.")

    def _open_item(self, it: QListWidgetItem) -> None:
        data = it.data(Qt.ItemDataRole.UserRole)
        if data:
            page, rid = data
            self.ctx.navigate.emit(page, rid or "")


_ = QVBoxLayout
