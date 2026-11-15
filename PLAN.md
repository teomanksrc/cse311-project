# PLAN.md

Working notes for the post-checkpoint features, so the work can be resumed in a new session.
Last updated: 2026-11-15.

## How the work is run

One orchestrating session plans, defines interfaces, reviews and verifies. Sonnet subagents write the code.
Two agents run in parallel only when they touch separate files. Agents test on SQLite
(`USE_SQLITE=True`) when another agent is using the PostgreSQL test database; the orchestrator runs
the full suite on PostgreSQL after each phase. No commits unless the user asks; ask for the commit author.

## Task order and progress

| # | Task | Backlog | Status |
|---|---|---|---|
| 0 | Shared wiring: `reporting` app skeleton, URL includes, settings, requirements, `.env.example` | | Done |
| 1 | Instructor setup UI (LOs, assessments, both weight grids) | B3 | Done, 110 tests green on PostgreSQL |
| 1 | Bulk grade import, CSV and XLSX | E2 | Done, same run |
| 1 | Performance report: rule-based summary + Gemini commentary | E3 | Done, same run; real API call verified |
| 2 | Syllabus upload that proposes LOs, assessments, weights | E1 | Done; real API call verified |
| 2 | Materialized view, index tuning, `seed_load`, `db_stats`, backup and restore, PO coverage page | F1, F2, F4, E5 | Done; no extra index was justified by the plans |
| 2 | Partitioning and replication | F3 | Done as a plan in `docs/scalability.md` |
| 3 | Final review: 178 tests green on PostgreSQL and SQLite, ruff clean, migrations in sync, every new page renders per role against the dev database | | Done |
| 3 | `docs/backlog.md` statuses updated | | Done |
| 3 | Click through the pages in a real browser; generate the demo reports | | Todo (user) |
| 3 | Update the layout and "out of scope" sections of `CLAUDE.md` | | Todo (ask the user first) |

## State on 2026-11-15 (end of day)

Everything is built, verified and committed on six stacked local branches. Each branch tip was checked
on its own: ruff, `makemigrations --check`, full test suite on PostgreSQL (final count 195).

| Order | Branch | Commits by | Contents |
|---|---|---|---|
| 1 | `feature/instructor-setup-import` | Ali Emre Sayan | B3 setup pages, E2 bulk import |
| 2 | `feature/performance-report` | teomanksrc, Batuhan Büyüknacar | Gemini client; E3 report |
| 3 | `feature/syllabus-upload` | teomanksrc | E1 |
| 4 | `feature/data-systems` | Başar Haktan Yaman | F1-F4 |
| 5 | `feature/alerts-and-coverage` | Batuhan Büyüknacar | E5 PO coverage, E4 alerts |
| 6 | `feature/cd-pipeline` | teomanksrc | Dockerfile, `cd.yml`, backlog and this file |

The branches are stacked (each contains the previous one). On GitHub, open one pull request per branch
with base `develop` and merge them **in this order** using "Create a merge commit". `gh` is not installed
on this PC, so pull requests are opened in the browser. Commits carry no Claude co-author line (user rule).

Still to do:
- Merge the six pull requests, then `develop` -> `main`. `cd.yml` only starts working once it is on `main`;
  its first run on GitHub is untested. The ghcr.io package may be created private: check its visibility.
- After the merges: `git checkout develop && git pull`, delete the local feature branches.
- Richer demo data (20-30 students, all 11 POs covered; no demo score is below 60, so alerts do not show).
  Run `seed_demo` before the demo to restore the guideline example values.
- Update diagrams and both final reports (new tables, materialized view, Gemini, alerts, CD; Redis and OBS dropped).
- `CLAUDE.md` still lists these features as out of scope and does not mention `reporting/` or `alerts/`.

Dropped: D3 dashboard filters. Velocity wording in the report is the team's own call.

Repository: https://github.com/teomanksrc/cse311-project

## Decisions

**Scope**
- Redis and a real OBS/LMS integration are dropped: the cached score tables already act as the cache,
  and CSV/Excel import is the realistic integration.
- F3 is a written plan, not an implementation; the data is far too small to justify either.

**AI (Gemini free tier, no paid API)**
- One client, `reporting/llm.py`, standard library only: `is_configured()`, `generate_text()`,
  `generate_json()`, `LLMError`. Used by both the report and the syllabus feature.
- Key in `.env` as `GEMINI_API_KEY`; never in `.env.example`, which is tracked. Empty key = AI off,
  everything still works.
- Model `gemini-flash-lite-latest` (`GEMINI_MODEL`). `gemini-2.5-flash` is closed to new users, and the
  larger flash models timed out or returned 503 on the free tier when tried on 2026-11-15.
- Only PO numbers, PO short names, scores, incomplete flags and department averages are sent.
  No names, usernames, student numbers, emails or course grades. A test asserts this.
- Numbers on the page always come from the system; the AI writes commentary only.
- Reports are stored (`reporting.PerformanceReport`). A stored report is reused when the student's own
  scores are unchanged; a report without AI commentary is rebuilt once a key is configured.
- The client retries once on HTTP 503 (free tier busy). An API failure never breaks the page: the rule-based summary (`reporting/rules.py`, pure Python) shows alone.
- PDF = print-friendly page plus the browser's "Save as PDF". No PDF library.
- Generate reports before the demo on the demo machine: the free tier can be slow or busy.

**Syllabus upload**
- The AI proposes, the instructor approves. Flow: upload (`.pdf`, `.txt` or pasted text) -> Gemini JSON ->
  `validate_proposal` -> proposal kept in the session -> review page -> Apply.
- Apply only adds what does not exist; it never overwrites or deletes. Model output is treated as
  untrusted input and auto-escaped.

**Instructor setup UI and import**
- Function views, own offerings only (others get 404). Any invalid cell: nothing saved.
- Only changed cells are written, so an unchanged grid triggers no recompute.
- Import file: first column `student_number`, other columns are assessment names, cells 0-100,
  blank = leave the grade as it is. All or nothing, written in student-id order.

**Materialized view**
- `scoring_department_po_stats`; a MATERIALIZED VIEW on PostgreSQL, an ordinary VIEW on SQLite,
  read through the unmanaged model `DepartmentPOStat`.
- Never refreshed inside a recompute or a signal: the refresh's exclusive lock plus the student row
  locks can deadlock. It is refreshed after the writing transaction commits
  (`scoring.stats.refresh_department_stats()`), by `seed_demo`, by the `refresh_stats` command and by a
  Refresh button on the department dashboard.
- Accepted trade-off: the dashboard can be stale after an admin-site edit until the next refresh.

**Measurement**
- Load data goes into a scratch database (`po_system_perf`), never into `po_system`, which holds the demo data.
- Add an index only where a real query plan justifies it; "no index needed" is a valid result.

## Where things live

- `curriculum/views.py`, `forms.py`, `urls.py`, `syllabus.py`, `templates/curriculum/`: setup UI and syllabus upload (`/instructor/setup/...`)
- `grading/imports.py`, `grading/views.py`: import (`/instructor/offerings/<id>/import/`)
- `reporting/`: report (`/reports/me/`, `/reports/students/`)
- `scoring/stats.py`, `scoring/migrations/0003_department_po_stats.py`, commands `refresh_stats`, `db_stats`, `seed_load`, `backup_db`, `restore_db`: data systems
- `scoring/views.py`: PO coverage (`/department/coverage/`), dashboard refresh
- `docs/performance.md` (query plans, sizes), `docs/scalability.md` (partitioning, replication, fault tolerance)

## Open items for the user

- Not committed. Decide the branch (`feature/<name>`) and the author of each commit.
- Nothing has been checked in a real browser yet; only through the test client.
- E3 covers one student at a time; the cohort report in the backlog wording is not built.
- `recompute_student` runs about 240 statements per student (see `docs/performance.md`); fine now, a candidate for later tuning.
