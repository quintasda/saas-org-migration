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

You don't need to set any environment variables. When it starts, `org-copy` asks for the details of both orgs. Tokens are not echoed.

It asks on every run, so a run never reuses an org or token from an earlier session. If `SOURCE_ORG`, `SOURCE_TOKEN`, `DEST_ORG`, or `DEST_TOKEN` is set in the environment, `org-copy` ignores it, removes it for that run, and asks again. It needs a terminal; without one, such as in CI, it stops with an error.

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

```bash
org-copy
```

`org-copy` asks for:

1. Source host. Press Enter for `https://us.sentry.io`.
2. Source org slug and token.
3. Destination host. Press Enter for `https://de.sentry.io`.
4. Destination org slug and token.

Then it offers two options:

- **Start migration** copies everything from start to finish. It reads the source, shows the changes it will make to the destination, asks whether to email invites to the source members, and asks you to confirm before it writes anything. When it finishes, open `manual-checklist.md` and start with **Review the destination**.
- **Plan** changes nothing in either org. It reads the source and prints what Start migration would copy to the destination. Use it first to check the source configuration.

Both options write the local files listed under Output files. Plan does not write `dsn-map.json`.

The command exits with status 1 when a step fails. Other steps still run. Read the checklist for the failures.

### One step at a time

The steps can also be run on their own, for example to use the flags below. Each one asks only for the org it needs.

```bash
org-copy export     # read the source into snapshot.json. Asks for the source org.
org-copy plan       # show what apply would write. Asks for the destination org.
org-copy apply      # write the settings. Asks for the destination org.
```

Pass `--source-host` or `--dest-host` to use other regions.

Update team admins runs after every invited member has accepted. Invites only add people to teams, so team roles are not copied. This command reads the same `snapshot.json` and sets `teamRole` to `admin` on the destination for members whose org role is `member` and who were admins of a team in the source. It needs `member:write` on the destination token.

```bash
org-copy update-team-admins
```

## Flags

These flags work with `plan` and `apply`. Start migration copies forwarders and asks about invites.

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
