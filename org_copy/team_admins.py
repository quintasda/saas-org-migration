"""Promote org members to team admin after they have accepted their invites."""

from __future__ import annotations

from typing import Any

from org_copy.apply import LIST_PARAMS, ApplyReport, Sink
from org_copy.client import ApiError, SentryClient
from org_copy.redact import error_text
from org_copy.remap import member_email


def update_team_admins(snapshot: dict[str, Any], client: SentryClient) -> ApplyReport:
    """Set teamRole admin on the destination for source members who were team admins."""
    report = ApplyReport()
    sink = Sink(client, report, dry_run=False)
    org = client.org
    members = client.get_all(f"/organizations/{org}/members/", LIST_PARAMS)
    dest_by_email = {member_email(member): member for member in members if member_email(member)}
    for member in snapshot.get("members") or []:
        if (member.get("orgRole") or "member") != "member":
            continue
        slugs = [
            item.get("teamSlug")
            for item in member.get("teamRoles") or []
            if isinstance(item, dict) and item.get("role") == "admin" and item.get("teamSlug")
        ]
        if not slugs:
            continue
        email = member_email(member)
        dest_member = dest_by_email.get(email)
        if dest_member is None:
            report.failures.append({"step": f"team admin {email}", "detail": "not a member of the destination org"})
            continue
        if dest_member.get("pending"):
            report.failures.append({"step": f"team admin {email}", "detail": "invite has not been accepted yet"})
            continue
        current = {
            item.get("teamSlug")
            for item in dest_member.get("teamRoles") or []
            if isinstance(item, dict) and item.get("role") == "admin"
        }
        for slug in slugs:
            summary = f"team role admin for {email} on {slug}"
            if slug in current:
                sink.skip(summary)
                continue
            try:
                sink.put(
                    f"/organizations/{org}/members/{dest_member.get('id')}/teams/{slug}/",
                    {"teamRole": "admin"},
                    summary,
                )
            except ApiError as exc:
                report.failures.append({"step": summary, "detail": error_text(exc)})
    return report
