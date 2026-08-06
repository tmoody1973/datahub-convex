# datahub-convex — a Convex ingestion source for DataHub

The first [Convex](https://convex.dev) metadata source for [DataHub](https://datahubproject.io):
recipe-driven like official sources, it discovers every table in one or more Convex
deployments via the [streaming export API](https://docs.convex.dev/http-api/#streaming-export)
and lands in DataHub:

- one **container** per deployment
- one **dataset** per table with **schema fields** mapped from Convex's JSON Schema
  (unions, nested objects, arrays), document-reference descriptions (`Id(<table>)`)
- **exact row counts** as dataset profiles
- Works against a stock `datahub docker quickstart` — no DataHub modifications

Licensed Apache 2.0. Built for the Build with DataHub Agent Hackathon; structured for
upstream submission.

## What it does, in plain English

[Convex](https://convex.dev) is the database behind a lot of modern web and
mobile apps. [DataHub](https://datahubproject.io) is an open-source catalog —
the place a data team goes to answer "what data do we have, what shape is it,
and can we trust it?" Until now those two didn't talk: your warehouse and
dashboards showed up in the catalog, but the Convex tables actually powering
your product were invisible.

This connector fixes that. Point it at a Convex deployment (all it needs is a
read-only deploy key) and it walks every table through Convex's built-in
streaming export API, then registers what it finds in DataHub:

- your **deployment** appears as a container, like a database;
- every **table** appears as a dataset inside it, with its full field-by-field
  schema — including nested objects, unions, and references between tables;
- each table shows its **exact row count**, so you can see at a glance what's
  big, what's empty, and what changed since the last run.

Re-running it is safe: it updates what's already there instead of duplicating.
Nothing is installed on the Convex side, and it never writes to your app's
data — it only reads structure and counts.

## Why would you use it? (use cases)

- **See your product data next to your analytics data.** Most teams catalog
  the warehouse but not the operational database actually running the app.
  If Convex is your backend, this puts those tables in the same catalog your
  data team already searches — with schemas and row counts, not tribal
  knowledge.
- **Impact analysis before schema changes.** Once Convex tables are in
  DataHub, you can attach lineage from them to whatever consumes them
  (exports, ETL jobs, ML features, dashboards) and answer "what breaks if I
  rename this field?" before you rename it.
- **Governance over app data.** DataHub's assertions, incidents, owners,
  domains, and glossary all work on Convex datasets once they're ingested —
  quality checks on user tables, PII tagging, ownership for on-call. (This is
  exactly how [Liner Notes](https://github.com/tmoody1973/liner-notes) uses
  it: an AI steward agent reads and writes governance state over ingested
  Convex tables.)
- **Growth and drift monitoring.** Each run records exact row counts as
  dataset profiles, so the catalog keeps a history — spot a table that
  suddenly doubled or a queue that never drains.
- **Onboarding and discovery.** New engineers and data scientists can search
  "what tables does our app have?" instead of reading the schema file — field
  descriptions include cross-table references (`Id(<table>)`), so the data
  model is browsable.
- **AI agents over app data.** Anything that speaks to DataHub's MCP Server
  (Claude, other agents) can now see your Convex schema and metadata as
  context — the connector is the bridge that puts app data in the agent's
  world model.

## Use it on your own Convex app

```sh
# 1. Install (alongside the DataHub CLI it plugs into)
pip install "git+https://github.com/tmoody1973/datahub-convex.git"

# 2. Get a read-only deploy key for your deployment
#    Convex dashboard → your project → Settings → Deploy keys
#    (scope "deployment:data:view" is enough), or:
cd your-app && npx convex deployment token create datahub

# 3. Write a recipe (see the Recipe section below) and run:
export CONVEX_DEPLOY_KEY='...'
datahub ingest -c your-recipe.yml

# 4. Browse http://localhost:9002 → search your table names
```

If you don't have DataHub running yet, `datahub docker quickstart` brings one
up locally in Docker — this connector works against it unmodified.

## Install (standalone)

```sh
pip install "git+https://github.com/tmoody1973/datahub-convex.git"
# then: datahub ingest -c recipes/convex.yml   (see Recipe below)
```

## Provenance

Built for the Build with DataHub Agent Hackathon as part of
[Liner Notes](https://github.com/tmoody1973/liner-notes), where it ingests two
production Convex deployments. Also submitted upstream to
[datahub-project/datahub](https://github.com/datahub-project/datahub)
(branch [`feat/convex-ingestion-source`](https://github.com/tmoody1973/datahub/tree/feat/convex-ingestion-source)).
The copy in the Liner Notes monorepo is the working source of truth until the
upstream PR lands; this repo mirrors it for standalone use.

## Requirements

- Python 3.9–3.12 (`uv venv --python 3.11` works well)
- Docker (for the DataHub quickstart)
- A Convex deploy key per deployment — read-only scope `deployment:data:view` is enough
  (Convex dashboard → Settings → Deploy keys, or `npx convex deployment token create <name>`)

## Quickstart (copy-paste)

```sh
cd connector
uv venv --python 3.11 .venv
uv pip install -p .venv/bin/python -e .

# 1. DataHub up (first run downloads images; UI at http://localhost:9002)
.venv/bin/datahub docker quickstart

# 2. Keys in (never in the recipe file itself)
export CONVEX_SOURCE_DEPLOY_KEY='...'
export CONVEX_LINER_NOTES_DEPLOY_KEY='...'

# 3. One ingest command
.venv/bin/datahub ingest -c recipes/convex.yml

# 4. Browse: http://localhost:9002 → search "convex" or browse the Convex platform
```

## Recipe

```yaml
source:
  type: convex
  config:
    deployments:
      - name: my-app
        url: https://happy-animal-123.convex.cloud
        deploy_key: ${CONVEX_DEPLOY_KEY}
    include_row_counts: true   # default; page-counts each table via list_snapshot
    max_count_pages: 200       # safety cap (~1024 rows per page)
sink:
  type: datahub-rest
  config:
    server: http://localhost:8080
```

The package registers the `convex` source type via the
`datahub.ingestion.source.plugins` entry point, so recipes reference it exactly
like built-in sources. Re-running ingest is idempotent — aspects are upserts
keyed by URN.

## Development

```sh
uv pip install -p .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest tests/ -q
```
