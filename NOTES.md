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
