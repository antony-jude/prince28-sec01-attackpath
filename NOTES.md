# Engineering notes: ATTACKpath

## D03 · PostgreSQL

### Migrations (upgrade, downgrade, upgrade)

```text
Running downgrade 0002 -> 0001, Add GIN index on document metadata.
0001
Running upgrade 0001 -> 0002, Add GIN index on document metadata.
0001 -> 0002 (head), Add GIN index on document metadata.
<base> -> 0001, Create documents and pages tables.
```

### The loader is idempotent

```text
run 1: records=20 inserted=20 updated=0 unchanged=0
run 2: records=20 inserted=0 updated=0 unchanged=20
run 3 (after editing one record): records=20 inserted=0 updated=1 unchanged=19
```

### EXPLAIN for ?technique_id=T1059.001

```text
Seq Scan on documents  (cost=0.00..7.25 rows=1 width=36) (actual time=0.014..0.020 rows=1.00 loops=1)
  Filter: (metadata @> '{"technique_id": "T1059.001"}'::jsonb)
  Rows Removed by Filter: 19

Bitmap Heap Scan on documents  (cost=8.54..12.56 rows=1 width=36) (actual time=0.024..0.025 rows=1.00 loops=1)
  Recheck Cond: (metadata @> '{"technique_id": "T1059.001"}'::jsonb)
  Heap Blocks: exact=1
  ->  Bitmap Index Scan on ix_documents_metadata_gin  (cost=0.00..8.54 rows=1 width=0) (actual time=0.008..0.008 rows=1.00 loops=1)
        Index Cond: (metadata @> '{"technique_id": "T1059.001"}'::jsonb)
```

Why did the planner choose a Seq Scan on my table? (2 lines, your own words)

The table currently contains only 20 documents, so PostgreSQL estimates that reading the heap directly is cheaper than using a bitmap index. The FILTER then removes 19 rows and confirms the query matches one document.

When would it switch to the GIN index? (1 line)

As the table grows or selectivity improves, PostgreSQL should prefer the GIN index for matching JSONB containment predicates.

## Stretch tasks

### Migration 3 · typed technique_id

Migration `0003` adds `documents.technique_id`, backfills it from `metadata ->> 'technique_id'`, and creates a B-tree index named `ix_documents_technique_id`.

### Pruning

The loader reports `deleted=N`. Running without `--prune` leaves missing database documents untouched. Running with `--prune` deletes them transactionally:

```text
uv run python scripts/load_db.py --prune
records=20 inserted=0 updated=0 unchanged=20 deleted=0
```

### Sorting

`/v1/documents` accepts `title`, `-title`, `published_on`, `-published_on`, `external_id`, and `-external_id`. Unknown sort values return a 400 problem response.

### Pool status

The API logs `engine.pool.status()` when it starts and shuts down. `scripts/pool_status.py` sends 50 `/ready` requests, exercising database checkouts. At this scale, idle connections should not accumulate; a healthy QueuePool status is expected to show a zero checked-out connection count after each request completes.

## D04 · Docker, Compose and tests

### The image

```text
docker images attackpath:dev
IMAGE            ID             DISK USAGE   CONTENT SIZE   EXTRA
attackpath:dev   fccebedfb42c   301MB        70.1MB

docker run --rm attackpath:dev id
uid=999(app) gid=999(app) groups=999(app)
```

- The image is 70.1 MB of content (301 MB Docker disk usage), below the 400 MB target.
- The initial build took about 32 seconds while base layers and packages were fetched; the cached rebuild took 7.5 seconds.
- `uv sync --locked --no-install-project --no-dev` was `CACHED` on the rebuild because neither `pyproject.toml` nor `uv.lock` changed.

### The stack

```text
docker compose ps -a
attackpath-api-1       Up (healthy)       0.0.0.0:8000->8000/tcp
attackpath-db-1        Up (healthy)       0.0.0.0:5433->5432/tcp
attackpath-migrate-1   Exited (0)
attackpath-redis-1     Up (healthy)       0.0.0.0:6379->6379/tcp

docker compose logs migrate
first up:  records=20 inserted=20 updated=0 unchanged=0 deleted=0
second up: records=20 inserted=0 updated=0 unchanged=20 deleted=0
```

Compose starts PostgreSQL with pgvector, Redis, the migration/seed job, and the API in dependency order. The second start retained the volume and did not duplicate records.

### Breaking the database on purpose

```text
db stopped:  /health -> {"status":"ok"}
db stopped:  /ready  -> {"status":"not_ready","checks":{"database":false}}
db started:  /ready  -> {"status":"ready","checks":{"database":true}}
```

A load balancer should stop sending requests to an unready service because it cannot reach its data dependency. The API process remains healthy, so restarting it would not repair the database and is unnecessary once the dependency recovers.

### Tests and coverage

```text
uv run poe test              -> 23 passed
uv run poe test-integration  -> 7 passed
uv run poe cov (unit only)   -> TOTAL 80%; 23 passed, 7 skipped
uv run poe cov (with integration tests) -> TOTAL 91%; 30 passed
```

Integration tests create a unique temporary database from Compose's `app_test` admin database, run the real migrations, and drop it afterward.

`logging_setup.py` has startup logging branches that the test client does not exercise; they matter, but are low-risk configuration code. `api/errors.py` still has an unhandled-exception response path not covered by normal endpoint tests; it should gain a focused regression test when that behavior changes.

## D05 · CI/CD and going live

- Live URL: https://prince28-sec01-attackpath.onrender.com
- CI run for pull request 1: https://github.com/antony-jude/prince28-sec01-attackpath/actions/runs/45337110363
- First merge-triggered CD workflow: https://github.com/antony-jude/prince28-sec01-attackpath/actions/runs/45337290698. It was triggered by merge commit `fcf1182`; its third attempt passed after the Render service was changed to the matching GHCR image source.
- Merge clicked at 11:29 IST → successful smoke test at 11:59 IST → lead time: about 30 minutes. The initial delay was configuration repair, not a code or migration failure.

### Smoke test output from CD

```text
ok  /health -> 200, version fcf11823a039b22ad0d5aab1abbbd179b530716e
ok  /ready -> 200 {'status': 'ready', 'checks': {'database': True}}
ok  /v1/documents?limit=1 -> 200
Smoke test passed
```

### Rollback drill

- Rolled back to `9c50a9d16aed1936c81ffbeec29b0eb09ec59ba2`: started 12:01 IST, smoke passed about 12:02 IST (38 seconds).
- Rolled forward to `fcf11823a039b22ad0d5aab1abbbd179b530716e`: started 12:03 IST, smoke passed about 12:04 IST (38 seconds).
- The rollback changes only the app image; `workflow_dispatch` skips migrations, so the database remains on the newer schema.
- That is safe here because migration `0003` only adds a nullable `technique_id` column and an index. Older code continues to use the existing columns, and no schema or data downgrade is attempted.

### Where my secrets live

- Neon string: GitHub Secret `DATABASE_URL` and the Render environment; it is not in Git or the image.
- Render deploy hook: GitHub Secret `RENDER_DEPLOY_HOOK` only.

### Monitoring and stretch work

- UptimeRobot checks `/health` every 5 minutes and alerts by email; monitor `804788231` is currently Up.
- A paid always-on Render instance would avoid the Free plan's cold-start delay on the first request.
- Dependabot checks GitHub Actions weekly, and CI runs pre-commit across all files.
- CD runs 1–3 completed in 23s, 38s, and 38s respectively (about 33s average); the smoke-test wait is the slowest observed step.
- A production human gate must be enabled manually in GitHub Environment settings because it changes repository security policy. It is worth the delay for high-risk production changes that need a human review before rollout.

## D06 · Collecting the corpus

- Start target: Enterprise matrix: all techniques + sub-techniques (about 800 objects).
- Collected today: **10 files, 10 measured pages, 54.91 MB** (from `DATASET.md`).
- Doors used: **URL list**. The official Enterprise STIX JSON is the large start-target file; nine focused ATT&CK technique pages support the seed questions.

### Licence check

| Source | Licence or terms, in my words | May I show full text in answers? |
|---|---|---|
| MITRE ATT&CK and ATT&CK STIX data | Reuse is allowed with attribution to The MITRE Corporation under the ATT&CK terms of use. | No: show links and short attributed excerpts, not an entire source document. |

### robots.txt

- Site: **attack.mitre.org**. Its robots.txt allows the bot except for `/previous/` and `/versions/`; the selected current technique pages were allowed.
- Site: **raw.githubusercontent.com**. Its robots.txt returned 404, which the downloader treats as no published restriction; the request completed successfully.
- Nothing was blocked for my bot. The downloader still records a `blocked` status if a future source denies `examate-student-bot` or returns a robots 5xx.

### Kill and resume

- Run 1: I pressed Ctrl+C after **8 files** completed; no `.part` file remained in `data/raw/`.
- Run 2: **downloaded=2, skipped=8**.
- Run 3: **downloaded=0, skipped=10**.

### Capacity (from docs/CAPACITY.md)

- Tokens per page, measured: **750** (conservative mixed-file estimate; refresh after more families are collected).
- Full corpus: **1.88 M tokens, 3,750 chunks, embedding about Rs 71, vectors 14.6 MB** at the documented assumptions.
- The number that surprised me most was the raw Enterprise export: the ten-file starter corpus is **54.91 MB** even though the focused HTML pages are small, so the worker needs object storage before the full three-version corpus.

### One thing that went wrong today, and how I fixed it

The first local report invocation hit a Windows sandbox cache permission error. I reran it with the approved environment, and the report completed. The interrupted crawl itself resumed cleanly from the manifest.
