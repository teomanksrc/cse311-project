# CLAUDE.md

University team project (CSE 311 + CSE 321, Fall 2026): a Django system that manages students' Program Outcome (PO) scores.
Talk to the user in Turkish. Code, comments, commit messages and docs are in English.

## Stack
Python 3.12, Django 5.2, PostgreSQL 16 (Docker), SQLite fallback, Bootstrap 5 + Chart.js (CDN), ruff. No SPA.

## Layout
- `config/` settings (env-driven, Postgres with automatic SQLite fallback), urls
- `accounts/` custom `User` with `role` (ADMIN, HEAD, INSTRUCTOR, STUDENT), `permissions.role_required`
- `curriculum/` ProgramOutcome, Course, CourseOffering, LearningOutcome, Assessment, AssessmentLOWeight, LOPOWeight
- `grading/` Enrollment, Grade, instructor grade-entry views
- `scoring/` `services.py` (pure math), `recompute.py` + `signals.py` (cache upkeep), cached StudentLOScore/StudentPOScore, student and department dashboards, `seed_demo` command
- `templates/`, `docs/` (Mermaid diagrams, design decisions, backlog)

## Commands
```
python manage.py runserver
python manage.py test
ruff check . && ruff format --check .
python manage.py seed_demo
docker compose up -d --wait
```
On this Windows machine use `.\.venv\Scripts\python` if the venv is not activated.

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

## Git
- Branches: `main`, `develop`, `feature/<name>`. Do not commit, push or merge unless the user asks.
- Ask who the commit author is and use `git commit --author="Name <github-email>"`; the CSE 311 report needs per-member contribution charts.

## Out of scope for the first checkpoint (planned)
Syllabus upload auto-configuration, bulk grade import, AI reports, third-party integrations, instructor UI for LOs and weights.
