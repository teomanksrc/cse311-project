# CLAUDE.md

University team project (CSE 311 + CSE 321, Fall 2026): a Django system that manages students' Program Outcome (PO) scores.
Talk to the user in Turkish. Code, comments, commit messages and docs are in English.

## Stack
Python 3.12, Django 5.2, PostgreSQL 16 (Docker), SQLite fallback, Bootstrap 5 + Chart.js (CDN), ruff. No SPA.
openpyxl (XLSX import), pypdf (syllabus PDF), Gemini free tier through the standard library (no SDK), gunicorn + whitenoise in the Docker image.

## Layout
- `config/` settings (env-driven, Postgres with automatic SQLite fallback), urls
- `accounts/` custom `User` with `role` (ADMIN, HEAD, INSTRUCTOR, STUDENT), `permissions.role_required`
- `curriculum/` ProgramOutcome, Course, CourseOffering, LearningOutcome, Assessment, AssessmentLOWeight, LOPOWeight; instructor setup UI (LOs, assessments, both weight grids); `syllabus.py` (syllabus upload: AI proposes, instructor approves)
- `grading/` Enrollment, Grade, instructor grade-entry views, `imports.py` (bulk grade import, CSV and XLSX)
- `scoring/` `services.py` (pure math), `recompute.py` + `signals.py` (cache upkeep), cached StudentLOScore/StudentPOScore, `stats.py` (materialized view `scoring_department_po_stats`), student and department dashboards, PO coverage page, commands `seed_demo`, `seed_load`, `refresh_stats`, `db_stats`, `backup_db`, `restore_db`
- `reporting/` performance report: `rules.py` (pure rule-based summary), `llm.py` (the only Gemini client), stored `PerformanceReport`
- `alerts/` `POAlert`, `services.py` (sync alerts with scores, e-mail the new ones), `send_alerts` command and dashboard button
- `templates/`, `docs/` (Mermaid diagrams, design decisions, backlog, performance, scalability), `reports/` (course report)
- `Dockerfile`, `.github/workflows/ci.yml` (tests + ruff), `cd.yml` (after CI passes on `main`, publishes the image to ghcr.io)
- `PLAN.md` local working notes (git-ignored, not in the repository): progress, decisions, what is still to do

## Commands
```
python manage.py runserver
python manage.py test
ruff check . && ruff format --check .
python manage.py seed_demo
python manage.py send_alerts
python manage.py refresh_stats
docker compose up -d --wait
```
On this Windows machine use `.\.venv\Scripts\python` if the venv is not activated. `gh` is not installed; pull requests are opened in the browser.

## Rules and decisions (details in docs/design-decisions.md)
- score = sum(weight x score) / sum(weights). Keep full precision, round to 1 decimal only for display.
- Missing grade: excluded from numerator and denominator, result `is_incomplete=True`. No grades for an LO: no LO score; the PO is incomplete.
- LO->PO weight is an integer 1-5 in the DB (CheckConstraint). `scoring/services.py` accepts any positive decimal.
- LOs, assessments, weights and enrollments belong to a CourseOffering, not a Course.
- Scores are computed only in `scoring/services.py` (pure, no Django). Cached rows are rewritten by `recompute.py` inside `transaction.atomic` (READ COMMITTED), after locking the student's row with `select_for_update`; take locks in student-id order.
- Don't add indexes on foreign keys: Django creates them already (a test checks for duplicates).
- Enforce permissions on the server. Students only ever see their own data; no student id in URLs.
- Constraints live in the database (unique, CHECK), not only in forms.
- Keep the code simple: the team must explain every part to the instructor.
- AI: `GEMINI_API_KEY` lives in `.env` only; an empty key turns AI off and everything still works. Only PO numbers, PO short names, scores, incomplete flags and department averages are sent, never personal data (a test asserts this). Numbers on pages come from the system; the AI writes commentary only. An API failure never breaks a page.
- Syllabus upload and bulk import: model output and uploaded files are untrusted input. Apply only adds, never overwrites or deletes. Import is all or nothing.
- Materialized view: never refreshed inside a recompute or a signal (deadlock risk with the student row locks); refresh after the writing transaction commits. The department dashboard can be stale after an admin-site edit until the next refresh.
- Alerts: e-mail is never sent from signals or the recompute; `sync_alerts` + `send_pending_alerts` run from the command or the button. Each alert is mailed once (`emailed_at`).
- Add an index only where a real query plan justifies it (`docs/performance.md`). Load tests use the scratch database `po_system_perf`, never `po_system`.

## Git
- Branches: `main`, `develop`, `feature/<name>`; feature branches go into `develop` through pull requests with a merge commit. Do not commit, push or merge unless the user asks.
- Ask who the commit author is and use `git commit --author="Name <github-email>"`; the CSE 311 report needs per-member contribution charts.
- No Claude co-author line in commit messages.

## Scope
- Built since checkpoint 1: instructor setup UI, bulk grade import, performance report with AI commentary, syllabus upload, materialized view and data-systems commands, PO coverage page, low-score alerts, CD pipeline.
- Dropped: Redis, a real OBS/LMS integration, dashboard filters (D3). Partitioning and replication are a written plan only (`docs/scalability.md`).
- Remaining work is tracked in the local `PLAN.md`, if present.
