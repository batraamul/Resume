"""Section ordering adapted to the mode, user choices, career target and vacancy emphasis."""

from __future__ import annotations

from ris.composition.modes import ALL_SECTION_KEYS, ResumeMode


def _move_after(order: list[str], keys: list[str], anchor_candidates: list[str]) -> list[str]:
    present = [k for k in keys if k in order]
    if not present:
        return order
    rest = [k for k in order if k not in present]
    anchor_idx = -1
    for a in anchor_candidates:
        if a in rest:
            anchor_idx = rest.index(a)
            break
    return rest[: anchor_idx + 1] + present + rest[anchor_idx + 1 :]


def resolve_order(
    mode: ResumeMode,
    *,
    user_order: list[str] | None = None,
    target_order: list[str] | None = None,
    hidden: list[str] | None = None,
    emphasis: dict[str, float] | None = None,
    custom_keys: list[str] | None = None,
) -> list[str]:
    """Return the section keys to render, in order.

    Priority: explicit user order > career-target order > mode order adapted
    to the vacancy's emphasis. Unknown keys are dropped; sections the order
    does not mention are appended so new content is never silently lost.
    """
    known = set(ALL_SECTION_KEYS)
    base: list[str]
    if user_order:
        base = [k for k in user_order if k in known or k.startswith("custom:")]
    elif target_order:
        base = [k for k in target_order if k in known or k.startswith("custom:")]
    else:
        base = list(mode.section_order)
        emphasis = emphasis or {}
        if not mode.government:
            if emphasis.get("education", 0) >= 0.3:
                base = _move_after(base, ["education"], ["summary"])
            if emphasis.get("research", 0) >= 0.25:
                edu_leads = ("education" in base and "experience" in base
                             and base.index("education") < base.index("experience"))
                base = _move_after(base, ["publications", "manuscripts"],
                                   ["education", "summary"] if edu_leads else ["summary"])
            if emphasis.get("leadership", 0) >= 0.25:
                base = _move_after(base, ["leadership"], ["experience"])
            if emphasis.get("projects", 0) >= 0.3:
                base = _move_after(base, ["projects"], ["experience", "summary"])
    for k in mode.section_order:
        if k not in base:
            base.append(k)
    for ck in custom_keys or []:
        if ck not in base:
            base.append(ck)
    hidden_set = set(hidden or [])
    seen: set[str] = set()
    out: list[str] = []
    for k in base:
        if k in hidden_set or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out
