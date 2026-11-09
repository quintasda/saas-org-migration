"""Command line for export, plan, and apply."""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from org_copy.apply import ApplyOptions, apply_snapshot
from org_copy.checklist import render_checklist
from org_copy.client import ApiError, SentryClient
from org_copy.export import export_snapshot
from org_copy.files import load_state, read_json, write_json, write_text
from org_copy.redact import error_text
from org_copy.team_admins import update_team_admins


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="org-copy",
        description="Copy Sentry organization settings from one region to another.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="Read the source org into snapshot.json")
    _source_args(export)
    export.add_argument("--snapshot", default="snapshot.json")
    export.add_argument("--checklist", default="manual-checklist.md")

    plan = sub.add_parser("plan", help="Show what apply would change. No writes.")
    _dest_args(plan)
    plan.add_argument("--snapshot", default="snapshot.json")
    plan.add_argument("--state", default="state.json")
    _copy_flags(plan)

    apply = sub.add_parser("apply", help="Write settings onto the destination org")
    _dest_args(apply)
    apply.add_argument("--snapshot", default="snapshot.json")
    apply.add_argument("--state", default="state.json")
    apply.add_argument("--checklist", default="manual-checklist.md")
    apply.add_argument("--dsn-map", default="dsn-map.json")
    _copy_flags(apply)

    team_admins = sub.add_parser(
        "update-team-admins",
        help="Make org members team admins where they were in the source. Run after invites are accepted.",
    )
    _dest_args(team_admins)
    team_admins.add_argument("--snapshot", default="snapshot.json")

    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            return _export(args)
        if args.command == "plan":
            return _plan(args)
        if args.command == "update-team-admins":
            return _update_team_admins(args)
        return _apply(args)
    except ApiError as exc:
        print(error_text(exc), file=sys.stderr)
        return 1


def _source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-host", default=os.environ.get("SOURCE_HOST", "https://us.sentry.io"))


def _dest_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dest-host", default=os.environ.get("DEST_HOST", "https://de.sentry.io"))


def _copy_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--send-invites", action="store_true")
    parser.add_argument("--include-forwarders", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--hide-environments", action="store_true")
    parser.add_argument("--apply-replay-access", action="store_true")


def _org_and_token(prefix: str, label: str) -> tuple[str, str]:
    """Ask for {prefix}_ORG and {prefix}_TOKEN on every run.

    Values already in the environment are ignored and removed, so a run never
    reuses an org or token left over from an earlier session.
    """
    stale = [name for name in (f"{prefix}_ORG", f"{prefix}_TOKEN") if os.environ.pop(name, None) is not None]
    if stale:
        print(f"Ignoring {' and '.join(stale)} from the environment. Enter them again.", file=sys.stderr)
    org = _ask(f"{label} org slug: ", f"{prefix}_ORG", secret=False)
    token = _ask(f"{label} token: ", f"{prefix}_TOKEN", secret=True)
    return org, token


def _ask(prompt: str, name: str, *, secret: bool) -> str:
    if not sys.stdin.isatty():
        raise SystemExit(f"{name} is asked for at startup. Run org-copy in a terminal.")
    value = (getpass.getpass(prompt) if secret else input(prompt)).strip()
    if not value:
        raise SystemExit(f"Missing {name}.")
    return value


def _export(args: argparse.Namespace) -> int:
    org, token = _org_and_token("SOURCE", "Source")
    with SentryClient(args.source_host, token, org) as client:
        snapshot = export_snapshot(client)
    write_json(args.snapshot, snapshot, secret=True)
    checklist = render_checklist(snapshot)
    write_text(args.checklist, checklist, secret=True)
    print(f"Wrote {args.snapshot} and {args.checklist}", file=sys.stderr)
    if snapshot.get("exportErrors"):
        print(f"{len(snapshot['exportErrors'])} export error(s). See the checklist.", file=sys.stderr)
        return 1
    return 0


def _options(args: argparse.Namespace, dry_run: bool) -> ApplyOptions:
    return ApplyOptions(
        dry_run=dry_run,
        send_invites=args.send_invites,
        include_forwarders=args.include_forwarders,
        hide_environments=args.hide_environments,
        apply_replay_access=args.apply_replay_access,
    )


def _plan(args: argparse.Namespace) -> int:
    snapshot = read_json(args.snapshot)
    org, token = _org_and_token("DEST", "Destination")
    with SentryClient(args.dest_host, token, org) as client:
        report = apply_snapshot(snapshot, client, load_state(args.state), args.state, _options(args, True))
    for action in report.actions:
        print(action)
    for note in report.notes:
        print(f"note: {note}")
    for failure in report.failures:
        print(f"fail: {failure['step']}: {failure['detail']}", file=sys.stderr)
    return 0 if report.ok else 1


def _apply(args: argparse.Namespace) -> int:
    snapshot = read_json(args.snapshot)
    org, token = _org_and_token("DEST", "Destination")
    state = load_state(args.state)
    with SentryClient(args.dest_host, token, org) as client:
        report = apply_snapshot(snapshot, client, state, args.state, _options(args, False))
    write_json(args.dsn_map, report.dsn_map, secret=True)
    checklist = render_checklist(
        snapshot,
        dest_org=org,
        actions=report.actions,
        failures=report.failures,
        dropped_actions=report.dropped_actions,
        dsn_map=report.dsn_map,
        rejected_org_fields=report.rejected_org_fields,
        rejected_project_options=report.rejected_project_options,
        notes=report.notes,
    )
    write_text(args.checklist, checklist, secret=True)
    for action in report.actions:
        print(action)
    for note in report.notes:
        print(f"note: {note}")
    for failure in report.failures:
        print(f"fail: {failure['step']}: {failure['detail']}", file=sys.stderr)
    return 0 if report.ok else 1


def _update_team_admins(args: argparse.Namespace) -> int:
    snapshot = read_json(args.snapshot)
    org, token = _org_and_token("DEST", "Destination")
    with SentryClient(args.dest_host, token, org) as client:
        report = update_team_admins(snapshot, client)
    for action in report.actions:
        print(action)
    for failure in report.failures:
        print(f"fail: {failure['step']}: {failure['detail']}", file=sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
