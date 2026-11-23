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
