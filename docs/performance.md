# Performance measurements (CSE 321)

All numbers below come from one real run on a separate database `po_system_perf` (PostgreSQL 16 in Docker, default
settings, same machine as the application). The demo database `po_system` was not touched. The load database was
created, measured and dropped; to repeat the run:

```
docker exec po_system_db createdb -U po_user po_system_perf
POSTGRES_DB=po_system_perf python manage.py migrate
POSTGRES_DB=po_system_perf python manage.py seed_load        # deterministic, seed 42, about 6 minutes
docker exec po_system_db psql -U po_user -d po_system_perf -c "VACUUM ANALYZE"
POSTGRES_DB=po_system_perf python manage.py db_stats
```

## Dataset

`seed_load` defaults: 2,000 students, 40 course offerings (10 courses x 4 terms), 4 LOs and 4 assessments per offering,
each LO feeds 2 POs, each assessment feeds 2 LOs, each student is enrolled in 10 offerings, 5 % of the grades are
missing. Rows go in with `bulk_create` (no signals); then `recompute_student` runs once per student.
Load time: 3 s for the raw rows, 343 s for the 2,000 recomputes (about 170 ms per student).

## db_stats output (after `VACUUM ANALYZE`)

"Rows" is `count(*)`, "columns" is the number of columns of the table, sizes come from `pg_relation_size` (table),
`pg_indexes_size` and `pg_total_relation_size` (table + indexes + TOAST).

```
table                           rows   columns  table_size  index_size  total_size
accounts_user                   2005   13       400 kB      384 kB      824 kB
accounts_user_groups            0      3        0 bytes     32 kB       32 kB
accounts_user_user_permissions  0      3        0 bytes     32 kB       32 kB
auth_group                      0      2        0 bytes     24 kB       24 kB
auth_group_permissions          0      3        0 bytes     32 kB       32 kB
auth_permission                 76     4        8192 bytes  48 kB       88 kB
curriculum_assessment           160    3        16 kB       48 kB       96 kB
curriculum_assessmentloweight   320    4        24 kB       80 kB       136 kB
curriculum_course               10     3        8192 bytes  48 kB       88 kB
curriculum_courseoffering       40     4        8192 bytes  64 kB       104 kB
curriculum_learningoutcome      160    4        16 kB       48 kB       104 kB
curriculum_lopoweight           320    4        24 kB       80 kB       136 kB
curriculum_programoutcome       11     4        8192 bytes  32 kB       80 kB
django_admin_log                0      8        0 bytes     24 kB       32 kB
django_content_type             19     3        8192 bytes  32 kB       72 kB
django_session                  0      3        0 bytes     24 kB       32 kB
grading_enrollment              20000  3        1024 kB     1488 kB     2544 kB
grading_grade                   76000  4        4472 kB     5728 kB     10232 kB
reporting_performancereport     0      8        0 bytes     24 kB       32 kB
scoring_studentloscore          79799  6        5320 kB     5936 kB     11 MB
scoring_studentposcore          21998  6        1472 kB     1600 kB     3104 kB
```

The materialized view `scoring_department_po_stats` has 11 rows and 4 columns and is not listed (a view has no table of
its own to count; `db_stats` skips unmanaged models). The whole database is roughly 30 MB. Per-row cost including
indexes: about 135 bytes for `grading_grade`, 130 for `grading_enrollment`, 145 for the two score tables.
Indexes are larger than the heap for every big table, because each table carries one FK index plus the composite
unique index behind its `UniqueConstraint`.

## Index types in the schema

- **B-tree** (the PostgreSQL default and the only type used): the primary key of every table, one index per foreign key
  (created by Django), and a **unique composite B-tree** behind every `UniqueConstraint`
  (`uniq_grade_enrollment_assessment`, `uniq_enrollment_student_offering`, `uniq_po_score`, `uniq_lo_score`, ...).
  Lookups by the leading column of a composite unique index (for example `student_id` on `uniq_po_score`) are served
  by it too.
- **Unique index on the materialized view**: `scoring_dept_po_stats_po_idx` on `program_outcome_id` (required for
  `REFRESH ... CONCURRENTLY`, which we do not use today; see `docs/design-decisions.md`).
- **Partial and covering indexes:** none in the schema. One covering index was *measured* (see below) and rejected.
- A test (`scoring/test_concurrency.py`) checks `pg_index` so duplicate indexes cannot be added by accident.

## Query plans (`EXPLAIN (ANALYZE, BUFFERS)`, warm cache)

Each query was run through `QuerySet.explain(analyze=True, buffers=True)` after five warm-up runs. "Execution" is the
server-side time from the plan. `shared hit` = pages found in PostgreSQL's cache (no `read` lines appeared: everything
is cached at this size).

| Query (where the app runs it) | Plan | Execution |
|---|---|---|
| S1 `StudentPOScore` of one student (student dashboard) | Index Scan using the student FK index, 11 rows, 3 buffers | 0.014 ms |
| S2 all 11 POs (student dashboard) | Seq Scan of 11 rows + sort | 0.011 ms |
| S3 enrollments of one student with offering and course | Index Scan on `grading_enrollment_student_id`, hash joins to two tiny tables (seq scans of 40 and 10 rows) | 0.034 ms |
| S4 LO scores of one enrollment | Index Scan on `scoring_studentloscore_enrollment_id` (4 rows), hash join to `learningoutcome` (seq scan of 160 rows) | 0.028 ms |
| S5 grades of one enrollment with assessment | Index Scan on `grading_grade_enrollment_id` (4 rows), hash join to `assessment` (seq scan of 160 rows) | 0.031 ms |
| D1 department dashboard BEFORE: live aggregate | Seq Scan of all 21,998 `scoring_studentposcore` rows (184 pages), Hash Right Join with the 11 POs, HashAggregate | **4.495 ms** |
| D2 department dashboard AFTER: materialized view | Seq Scan of 11 rows joined to the 11 POs, 2 buffers | **0.020 ms** |
| G1 grade entry: assessment + offering + course for the instructor | tiny seq scans (160, 40, 10 rows), 4 buffers | 0.025 ms |
| G2 grade entry: enrollments of one offering with students (515 rows) | Bitmap Index Scan on `grading_enrollment_offering_id`, hash join with a seq scan of 2,005 users, sort by last name | 0.425 ms |
| G3 grade entry: existing grades of the assessment (492 rows) | Bitmap Index Scan on `grading_grade_assessment_id`, 360 buffers | 0.135 ms |
| R1 recompute: lock the student row | LockRows over Index Scan on `accounts_user_pkey` | 0.014 ms |
| R2 recompute: enrollments of the student | Index Scan on the student FK index | 0.011 ms |
| R3 recompute: grades of one enrollment | Index Scan on `grading_grade_enrollment_id` | 0.012 ms |
| R4 recompute: assessment->LO weights of an offering | Seq Scan of 160 LOs (filter offering) hash-joined to a seq scan of 320 weights | 0.038 ms |
| R5 recompute: LOs of an offering | seq scans of 160 / 40 / 10 rows | 0.029 ms |
| R6 recompute: LO->PO weights for the student's 10 offerings | Seq Scan of 160 LOs, hash join to a seq scan of 320 weights | 0.049 ms |
| R7 recompute: existing PO scores of the student | Index Scan on the student FK index | 0.013 ms |
| C1 PO coverage, all terms (one annotated query) | seq scans of 320 weights, 160 LOs, 11 POs; hash joins; sort + GroupAggregate | 0.204 ms |
| C2 PO coverage, one term | same plus a seq scan of 40 offerings | 0.238 ms |

Every query on a large table (`grading_grade`, `grading_enrollment`, `scoring_studentloscore`,
`scoring_studentposcore`) uses an index (index scan, or bitmap index scan when it returns hundreds of rows). The only
sequential scans are on the curriculum tables (at most 320 rows, 2-3 pages: a seq scan is the cheapest plan for
PostgreSQL there) and the one full-table aggregate D1, which by definition reads every row.

### Materialized view: before and after

| | Server execution (EXPLAIN) | Python wall clock (ORM, median of 30) |
|---|---|---|
| Live aggregate over `StudentPOScore` (before) | 4.495 ms | 3.82 ms |
| Read from `scoring_department_po_stats` (after) | 0.020 ms | 0.79 ms |
| `REFRESH MATERIALIZED VIEW` (the price) | n/a | 7.1 ms |

The aggregate becomes about 200x cheaper on the server and about 5x cheaper as seen from Django (the remaining 0.8 ms
is mostly the ORM building 11 `ProgramOutcome` objects). The refresh costs about 7 ms, paid once per grade-entry or
import request instead of once per dashboard view. Honest reading: at 22,000 rows the live aggregate is still only 4
ms, so the view is not *needed* at this size; it is worth having because the aggregate grows with the number of
students and because it is a course topic that costs us very little (one migration, one refresh call). Staleness is
the price (see `docs/design-decisions.md`).

### Index decision: nothing added

- No plan contains a sequential scan or sort over a large table that an index could remove: all lookups by student,
  enrollment, assessment and offering already use the Django FK indexes or the composite unique indexes.
- Experiment 1: with `SET enable_seqscan = off` (forcing PostgreSQL to use indexes wherever it can) every query was
  equal or slower: D1 5.04 ms (vs 4.55), R4 0.050 (vs 0.038), R6 0.059 (vs 0.049), C1 0.230 (vs 0.204). The planner's
  choice of seq scans on the small curriculum tables is correct.
- Experiment 2: a covering index `scoring_studentposcore (program_outcome_id) INCLUDE (score, is_incomplete)`
  (696 kB) was created inside a rolled-back transaction to try to turn D1 into an index-only scan. The planner ignored
  it and still chose the Seq Scan (5.06 ms), since the query has to read all 22,000 rows anyway. Rejected; it would only
  cost write time and 696 kB. The materialized view is the right fix for D1, not an index.
- The migration `0002_remove_studentposcore_po_score_po_idx` earlier removed an index that duplicated a
  FK index; this run confirms that was right.

### Where the time really goes: the recompute

`recompute_student` for a student with 10 enrollments runs **240 SQL statements** and takes a median of **134 ms**
(10 runs), although each individual statement takes 0.01-0.06 ms on the server. The cost is the number of round trips
and the per-row `update_or_create` (a SELECT plus INSERT/UPDATE per cached row), not a missing index. This is why
`seed_load` needs 6 minutes for 2,000 students. It is acceptable for interactive use (an instructor saving a grade
recomputes one student, a bulk import recomputes each affected student once), and a possible future optimization is to
batch the writes with `bulk_create(update_conflicts=True)`; it is not done because it would make the code harder to
explain and nothing is slow enough yet.

### Student dashboard cost

One dashboard view issues 3 queries plus 2 per enrollment (about 23 for 10 enrollments). Using the numbers above the
database time is about 0.014 + 0.011 + 0.034 + 10 x (0.028 + 0.031) = 0.65 ms; the rest of the request is Python and
template rendering. No index would change that.
