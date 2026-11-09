# org-copy

Copy Sentry organization settings from one region to another through the public API. The destination organization must already exist. The script does not move events, issue history, billing, or releases.

## Install

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Tokens

Create one auth token in the source organization and one in the destination organization. We recommend creating an [Internal integration](https://docs.sentry.io/integrations/integration-platform/internal-integration/) in each organisation and use integration tokens.

Source token:

- `org:read`
- `project:read`
- `member:read`
- `team:read`
- `alerts:read`

Destination token:

- `org:write`
- `project:write`
- `member:read`

If you plan to pass `--send-invites` to invite users to join the new organisation, you will need to create a personal token instead (integration tokens can only be used to invite users with the `member` role), and will have to add the `member:write` scope.

These scopes are separate. `org:write` does not include `project:write` or `member:read`.

## Org slugs and tokens

The script reads both org slugs and both tokens from environment variables. Set them before you run it:

```bash
export SOURCE_ORG="..."
export SOURCE_TOKEN="..."
export DEST_ORG="..."
export DEST_TOKEN="..."
```

If one is not set, the command asks for it when it starts. Tokens are read without echoing them. Without a terminal, such as in CI, a missing value stops the command with an error.

Do not commit the tokens. They cannot be passed as command-line flags, so they stay out of shell history.

## What is copied

- Organization settings, including data scrubbing
- Teams, including a rename when the slug already exists
- Team membership for people who already belong to the destination organization
- Projects, project settings, inbound filters, and ownership rules
- New client keys, with new DSNs. The source DSN secret is not reused.
- Alerts, connected to the same monitors and projects as in the source, including alerts that have the same name in several projects and alerts that cover all projects. Actions that depend on an integration, such as Slack or PagerDuty, are dropped and listed in the checklist until the integration is set up.
- Metric monitors
- Cron monitors
- Uptime monitors. Auto-detected uptime monitors become manual ones, because the API only creates manual monitors.
- Custom dashboards. Prebuilt dashboards are skipped.
- Discover saved queries and recent searches
- Issue views that belong to the token user
- Data forwarders, including their configuration

## What stays manual

`manual-checklist.md` lists the items the API cannot write:

- SSO, SAML, and SCIM
- Integrations, repositories, code mappings, code owners, and service hooks
- Organization auth tokens (names and scopes only)
- Releases, source maps, and debug files
- Hidden environments, until events create them
- Replay access, until invited members accept
- Past events, issue history, replays, logs, and audit history

Switch SDK DSNs last, after alerts in the destination organization are working. New DSNs are written to `dsn-map.json`.

## Review after apply

After `apply`, `manual-checklist.md` starts with three sections for the review:

- **Review the destination** lists how many teams, projects, members, alerts, monitors, dashboards, saved queries, issue views, and data forwarders the source has, so you can compare them with the destination. It also lists the source's 2FA, data scrubbing, and relay settings, because the API can drop a rejected org setting without a failure.
- **Finish by hand** lists what needs people to accept their invites first: team admin roles, alert recipients and owners who were not members yet, and ownership rules that could not be saved.
- **Known gaps to check** lists what the script does not copy exactly, such as alert conditions that name a user or team.

## Run

Export reads the source organization and writes `snapshot.json` plus a checklist. It does not change either organization.

```bash
org-copy export --source-host https://us.sentry.io
```

Plan compares that snapshot with the destination and prints the writes it would make. It does not write.

```bash
org-copy plan --dest-host https://de.sentry.io
```

Apply writes the settings. Run it again to skip objects that already match by slug or name.

```bash
org-copy apply --dest-host https://de.sentry.io
```

Update team admins runs after every invited member has accepted. Invites only add people to teams, so team roles are not copied. This command reads the same `snapshot.json` and sets `teamRole` to `admin` on the destination for members whose org role is `member` and who were admins of a team in the source. It needs `member:write` on the destination token.

```bash
org-copy update-team-admins --dest-host https://de.sentry.io
```

`SOURCE_HOST` defaults to `https://us.sentry.io`. `DEST_HOST` defaults to `https://de.sentry.io`. `export` uses `SOURCE_ORG` and `SOURCE_TOKEN`. The other commands use `DEST_ORG` and `DEST_TOKEN`.

The command exits with status 1 when an export or apply step fails. Other steps still run. Read the checklist for the failures.

## Flags

`--send-invites` emails people who are not already members of the destination organization. Without it, existing members are added to the copied teams and nobody new is invited.

`--no-include-forwarders` skips data forwarders. Forwarders are copied by default. Their secrets are sent to the API and are not printed.

`--hide-environments` marks the source's hidden environments as hidden on the destination. Run this after the destination has received events for those environments.

`--apply-replay-access` copies the replay allow-list. Run this after members have accepted their invites, matched by email.

## Output files

These files are gitignored because they contain customer settings and credentials:

- `snapshot.json` holds the source export. Data-forwarder secrets stay in this file.
- `state.json` maps source ids to destination ids so a later apply does not create duplicates.
- `dsn-map.json` lists the new destination DSNs.
- `manual-checklist.md` lists work that still has to be done by hand and, after apply, what to review in the destination.

All four are written with mode `0600`.
