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
