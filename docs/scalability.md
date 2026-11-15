# Scalability and fault tolerance (CSE 321)

## What is implemented and what is only a plan

| Technique | Status |
|---|---|
| B-tree indexes: primary keys, FK indexes, composite unique indexes | **Implemented**, measured in `docs/performance.md` (no extra index was justified) |
| Cached score tables `StudentLOScore`, `StudentPOScore` | **Implemented** |
| Materialized view `scoring_department_po_stats` (plain view on SQLite) | **Implemented**, 4.5 ms to 0.02 ms on the server |
| Transactions: atomic grade saves and recompute, `SELECT ... FOR UPDATE`, READ COMMITTED | **Implemented**, tested (`scoring/test_concurrency.py`, `scoring/test_views.py`) |
| Backup and restore (`backup_db`, `restore_db`) | **Implemented**, round trip verified |
| Table partitioning | **Plan only** (below) |
| Streaming replication with a read replica | **Plan only** (below) |

## Projected size (basis: the `db_stats` run in `docs/performance.md`)

Measured cost per row including its indexes: `grading_grade` 135 bytes, `grading_enrollment` 130 bytes,
`scoring_studentloscore` and `scoring_studentposcore` about 145 bytes.

A realistic single department, assuming about 600 enrolled students, 8 courses per student per term and 2 terms per
year, 4 assessments and 4 LOs per course:

| Table | Per year | After 5 years | After 10 years | Size after 10 years |
|---|---|---|---|---|
| `grading_enrollment` | 9,600 | 48,000 | 96,000 | about 12 MB |
| `grading_grade` | 38,400 | 192,000 | 384,000 | about 52 MB |
| `scoring_studentloscore` | 38,400 | 192,000 | 384,000 | about 56 MB |
| `scoring_studentposcore` | about 1,500 (one row per student and PO, so it grows with the number of distinct students, not with terms) | about 7,500 | about 15,000 | about 2 MB |

The test run already holds 76,000 grades (2,000 students x 10 courses), which is about 2 years of a department twice
this size, and every query ran in well under a millisecond (`docs/performance.md`). A single department stays below
100 MB after ten years. **Neither partitioning nor replication is needed for this application as scoped.** The plan
below is for the case where the system is rolled out to a whole university (assume 20 departments and the same
growth: about 770,000 grades per year, 7.7 million after 10 years, about 1 GB for `grading_grade` and about the same
for `scoring_studentloscore`).

## Partitioning plan

**Which table first: `grading_grade`** (and `scoring_studentloscore` right after it), because they are the largest
tables, grow linearly with every term, and are append-mostly: old terms are read rarely and almost never changed. The
cached `scoring_studentposcore` table is small (one row per student and PO) and is not worth partitioning. If it ever
were, hash partitioning on `student_id` would be the natural key because every query filters by student.

**Key: the term.** Partitioning by term lets PostgreSQL skip old terms (partition pruning) and lets us archive or
drop a whole term cheaply (`DETACH PARTITION`) instead of a huge `DELETE`.

**The complication.** A grade row has no term. The term lives on `CourseOffering` (`grade -> assessment -> offering`,
or `grade -> enrollment -> offering`). PostgreSQL can only partition by a column of the table itself, so the options
are:

1. Copy the term (or a numeric `term_start_year`) into `grading_grade` (and into the LO score table), set it when the
   row is created and treat it as read-only. This is the simple and standard choice: a small denormalization of 4-8
   bytes per row.
2. Partition by `assessment_id` or `enrollment_id` ranges. Ids grow over time, so this behaves like partitioning by
   time, but the partition boundaries are meaningless to a human and cannot be matched to a term.

Option 1 is the plan. Consequences to handle when it is built:

- A PostgreSQL partitioned table requires every primary key and unique constraint to **include the partition key**. The
  primary key becomes `(id, term)` (Django 5.2 supports `CompositePrimaryKey`), and
  `uniq_grade_enrollment_assessment` becomes unique on `(enrollment, assessment, term)`. The uniqueness guarantee stays
  correct because an enrollment and an assessment each belong to exactly one offering, hence one term.
- Foreign keys *to* a partitioned table need the full composite key; the cached tables reference enrollments, not
  grades, so nothing references `grading_grade` and this is not a problem.
- Django does not create partitioned tables itself; the migration would use `RunSQL` (create the new partitioned
  table, copy, swap names). The ORM keeps working with an ordinary-looking model.
- The recompute reads grades by `enrollment_id`, which would no longer prune partitions; the query should also filter
  on the term (known from the enrollment's offering) or accept scanning the index of each partition (cheap, but it
  grows with the number of partitions).

**When it becomes worth it:** when `grading_grade` reaches a size where its indexes no longer fit comfortably in
memory, or maintenance operations (VACUUM, index rebuild, backup) take too long, which in practice means tens of
millions of rows or several GB; or when the department wants to archive terms older than N years cheaply. For one
department that is never; for the 20-department university projection, the table reaches that range after roughly
30 years, so even there it is a "nice to have".

## Replication plan (streaming replication, read replica)

**Shape:** one primary PostgreSQL 16 server and one hot-standby replica fed by streaming (physical) replication
(`wal_level = replica`, a replication user, `primary_conninfo` on the standby, `hot_standby = on`). In Docker Compose
this would be a second `db` service started from a base backup (`pg_basebackup -R`). Replication is asynchronous by
default; synchronous replication would give zero data loss at the price of slower commits.

**What can go to the replica (Django: a second entry in `DATABASES` and a small database router):**

- the **student dashboard**, the **department dashboard** and the **PO coverage** page: read-only, tolerate a delay of
  a fraction of a second (replication lag);
- the planned reporting and AI performance-report reads.

Caveat for the department dashboard: the materialized view is refreshed on the primary and the refresh is
WAL-replicated, so the replica sees the refreshed data after the lag. Nothing extra is needed.

**What must stay on the primary:**

- **Grade entry and bulk import**: they write.
- **Recompute**: it takes `SELECT ... FOR UPDATE` row locks, and a standby cannot take them (it is read-only).
- **The grade-entry form's own read**: an instructor who has just saved must see their grades immediately
  (read-your-writes); a lagging replica could show the old values. Reads right after a write also stay on the primary.
- Login and sessions (sessions are written on every login).

**When it becomes worth it:** when read traffic (dashboards during registration or end-of-term weeks) starts to
compete with the writes of grade entry on the primary, or when we need a hot standby for fast failover. With the
numbers above, one dashboard costs well under 1 ms of database time, so one PostgreSQL server could serve thousands
of requests per second; replication is therefore justified by availability (failover) long before it is justified by
load.

## Fault tolerance

### What the system already does

| Mechanism | Where | What it gives |
|---|---|---|
| **Atomic grade saves** | `grading/views.py` wraps all grade writes of one save or import in `transaction.atomic()`; `recompute_student` is `@transaction.atomic` too | All or nothing: a validation error or a crash in the middle saves nothing (`GradeEntryTests.test_invalid_grade_saves_nothing`), and the cached score tables never disagree with the grades after a commit |
| **Row locks** | `recompute_student` locks the student row with `SELECT ... FOR UPDATE`, in student-id order | Two concurrent grade saves for the same student cannot lose an update, and the fixed order prevents deadlocks |
| **Database constraints** | unique and CHECK constraints in the schema | Bad data is rejected even if a form is bypassed |
| **Docker health check and restart policy** | `docker-compose.yml`: `pg_isready` every 5 s, `restart: unless-stopped` | The database container restarts after a crash or a reboot; `docker compose up --wait` waits until it is healthy |
| **Named volume** | `po_system_pgdata` | Data survives container removal and image upgrades (`docker compose down` keeps it; only `down -v` deletes it) |
| **Automatic SQLite fallback** | `config/settings.py` probes the Postgres port and falls back to SQLite | The application and the developers keep working when Docker is off. The fallback is a development convenience, not a copy of production data |
| **CI on PostgreSQL** | `.github/workflows/ci.yml` runs ruff, `makemigrations --check`, `migrate` and the whole test suite against a `postgres:16` service | PostgreSQL-only behaviour (row locks, the materialized view, duplicate-index check) is tested on every push |
| **Backups and restore** | `backup_db`, `restore_db` (below) | Recovery from data loss or a wrong bulk import |

### Backup and restore

```
python manage.py backup_db                                    # -> backups/<db>_<YYYYmmdd_HHMMSS>.dump
python manage.py restore_db backups/<file>.dump --yes         # destructive: --yes is required
```

`backup_db` runs `docker compose exec -T db pg_dump -U <user> -Fc <database>` through `subprocess` (a list of
arguments, no shell syntax, so it works the same on Windows and macOS) and writes the custom-format (compressed)
dump into `backups/` (git-ignored). It prints the path and size. If Docker or the container is not available, or
`pg_dump` fails, it raises a `CommandError` with the reason and removes the partial file, so no empty backup is left
behind. `restore_db` pipes the file into `pg_restore --clean --if-exists --no-owner` inside the container, replaces the
dumped objects (the materialized view is rebuilt and filled by the restore) and refuses to run without `--yes`.

**What was verified (2026-11-15, on the scratch database `po_system_perf`, never on `po_system`):**
`backup_db` produced a 1,981,236-byte dump of the 2,000-student database; SQL `DELETE` removed 7,600 of 76,000 grades
and 3,142 of 21,998 PO scores; `restore_db` without `--yes` refused (exit code 1); `restore_db ... --yes` finished
with exit code 0 and the counts were back to 76,000 grades, 21,998 PO scores and 11 rows in the materialized view. A
`backup_db` against a database that does not exist failed with the `pg_dump` error message and left no file in
`backups/`. The test suite covers the same logic with `subprocess` mocked (CI has no Docker container).

### What is lost

- **Everything written after the last backup.** A dump is a point-in-time snapshot. Backups are manual (or run from a
  scheduler such as cron or Windows Task Scheduler calling `backup_db`); if the team backs up nightly, up to a day of
  grade entries can be lost. The cached score tables can always be rebuilt from grades and weights, so only grades,
  weights, users and enrollments matter.
- **Backups stored on the same machine** do not survive the loss of that machine; copy the file elsewhere.
- Continuous protection (point-in-time recovery with WAL archiving, or a synchronous standby from the replication plan)
  is **not implemented**; it is the next step if the loss window must shrink from "since the last dump" to seconds.
- After an admin-site edit the department dashboard is stale until the next refresh (a consistency trade-off, not a
  loss): see `docs/design-decisions.md`.
