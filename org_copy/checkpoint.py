"""Checkpoint after plan: compare what the source has with what apply would do."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from org_copy.apply import OBJECT_KINDS, ApplyReport, ObjectKind, action_outcome

_REASON = re.compile(r"\(([^()]*)\)$")


@dataclass
class Row:
    label: str
    source: int
    create: int
    existing: int
    not_copied: Counter[str]

    @property
    def unaccounted(self) -> int:
        return self.source - self.create - self.existing - sum(self.not_copied.values())


def render_checkpoint(snapshot: dict[str, Any], report: ApplyReport, source_org: str, dest_org: str) -> str:
    rows = [row for row in (_row(kind, snapshot, report) for kind in OBJECT_KINDS) if row.source or row.create]
    width = max([len(row.label) for row in rows] + [len("Members")])
    columns = (source_org, "To create", "Already there", "Not copied")
    header = " " * (width + 2) + "  ".join(f"{name:>{max(len(name), 6)}}" for name in columns)
    lines = [f"Check before writing to {dest_org}", "", header]
    for row in rows:
        values = (row.source, row.create, row.existing, row.source - row.create - row.existing)
        cells = "  ".join(f"{value:>{max(len(name), 6)}}" for name, value in zip(columns, values))
        lines.append(f"  {row.label:<{width}}{cells}")
    members = len(snapshot.get("members") or [])
    lines.append(f"  {'Members':<{width}}{members:>{max(len(source_org), 6)}}  invited only if you answer y next")

    reasons = [(row.label, reason, count) for row in rows for reason, count in row.not_copied.items()]
    reasons.extend((row.label, "not in the plan, such as an entry with no name", row.unaccounted) for row in rows if row.unaccounted > 0)
    if reasons:
        lines.extend(["", "Not copied:"])
        lines.extend(f"  {label}: {count} {reason}" for label, reason, count in reasons)
    return "\n".join(lines) + "\n"


def _row(kind: ObjectKind, snapshot: dict[str, Any], report: ApplyReport) -> Row:
    row = Row(kind.label, kind.count(snapshot), 0, 0, Counter())
    for section in report.sections:
        if section.label != kind.section:
            continue
        for action in section.actions:
            if not action.partition(" ")[2].startswith(kind.prefixes):
                continue
            outcome = action_outcome(action)
            if outcome in ("create", "created"):
                row.create += 1
            elif outcome == "not copied":
                match = _REASON.search(action)
                row.not_copied[match.group(1) if match else "skipped"] += 1
            else:
                row.existing += 1
        failed = sum(1 for item in section.failures if str(item.get("step") or "").startswith(kind.prefixes))
        if failed:
            row.not_copied["failed, listed under Went wrong"] += failed
    return row
