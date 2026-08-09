"""Printable/Markdown export (Revision Prompt 9) — a plain-text render
of a `MorningPlanVersion`, suitable for printing or pasting elsewhere.
Pure formatting over already-loaded data; no new queries, no
side effects.
"""

from __future__ import annotations

from tradingos_api.schemas.morning_plan import (
    MorningPlanItemResponse,
    MorningPlanVersionDetailResponse,
)

_SECTION_TITLES: dict[str, str] = {
    "ACT_NOW": "Act Now",
    "APPROVAL_REQUIRED": "Approval Required",
    "BUY_AND_HOLD": "Buy and Hold",
    "TACTICAL_TRADES": "Tactical Trades",
    "WATCH_AND_AVOID": "Watch and Avoid",
    "UPCOMING_EVENTS": "Upcoming Events",
    "DATA_PROBLEMS": "Data Problems",
    "HOLD_MANAGE": "Hold / Manage",
    "INVESTMENT_WATCH": "Investment Watch",
    "TACTICAL_WATCH": "Tactical Watch",
    "AVOID": "Avoid",
}


def _render_item(item: MorningPlanItemResponse) -> str:
    lines = [f"- **{item.headline}**"]
    if item.action_label:
        lines[0] += f" _(action: {item.action_label})_"
    policy_result = item.card_detail.get("policy_result") if item.card_detail else None
    if policy_result:
        lines.append(f"  - Policy result: {policy_result}")
    ai_synthesis = item.card_detail.get("ai_synthesis") if item.card_detail else None
    if ai_synthesis and ai_synthesis.get("rationale"):
        lines.append(f"  - Rationale: {ai_synthesis['rationale']}")
    return "\n".join(lines)


def render_markdown(version: MorningPlanVersionDetailResponse) -> str:
    lines: list[str] = [
        f"# Morning Decision Plan — {version.plan_date.isoformat()}",
        "",
        f"**Version:** {version.version_label.value} #{version.version_number}  ",
        f"**Generated:** {version.generated_at.isoformat()}  ",
        f"**Evidence cutoff:** {version.evidence_cutoff.isoformat()}  ",
        f"**Completeness:** {version.completeness_status.value}",
        "",
    ]

    for section in version.sections:
        title = _SECTION_TITLES.get(section.section_key.value, section.section_key.value)
        lines.append(f"## {title}")
        lines.append("")
        if not section.items:
            lines.append("_No items._")
        else:
            for item in section.items:
                lines.append(_render_item(item))
        lines.append("")

    if version.quality_checks:
        lines.append("## Quality Checks")
        lines.append("")
        for check in version.quality_checks:
            mark = "✓" if check.passed else "✗"
            detail = f" — {check.detail}" if check.detail else ""
            lines.append(f"- [{mark}] {check.check_name}{detail}")
        lines.append("")

    return "\n".join(lines)
