# PO Score Management System

Web system that manages each student's Program Outcome (PO) scores.
CSE 311 and CSE 321 team project, Fall 2026. Stack: Python 3.12 + Django 5.2 + PostgreSQL.

Assessment grades -> Learning Outcomes -> Program Outcomes, every step a weighted average:
`score = sum(weight x score) / sum(weights)`.

## Setup on Windows (PowerShell)

Requirements: Python 3.12, Git, Docker Desktop (optional; without it the app uses SQLite).

```powershell
git clone <repo-url>
cd <repo-folder>

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env

# Option A: PostgreSQL (recommended)
docker compose up -d --wait

# Option B: no Docker. Set USE_SQLITE=True in .env (or just skip Docker:
# if PostgreSQL is not reachable the app falls back to SQLite automatically).

python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open http://127.0.0.1:8000/ and log in:

| User | Role | Sees |
|---|---|---|
| `Batuhan`, `Ali` | Student | Own PO profile |
| `instructor` | Instructor | Grade entry for own courses |
| `head` | Department Head | Department averages per PO |
| `admin` | Admin | Department view + `/admin/` |

Password for all demo users: `1234`. Usernames are case-sensitive.

If PowerShell blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or call `.\.venv\Scripts\python` directly.

## Setup on macOS / Linux (Terminal)

Requirements: Python 3.10+ (3.12 recommended, check with `python3 --version`), Git, Docker Desktop (optional).

```bash
git clone <repo-url>
cd <repo-folder>

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env

# Option A: PostgreSQL (recommended; the image also runs on Apple Silicon)
docker compose up -d --wait

# Option B: no Docker. Set USE_SQLITE=True in .env.

python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Then open http://127.0.0.1:8000/ and log in with the same users as above.

Notes for both platforms:
- The database is not part of the repository. Every machine starts empty and `seed_demo` creates the demo data. Changes made in one machine's database do not appear on another.
- If PostgreSQL is not reachable, the app silently falls back to SQLite (a warning is printed when the server starts). Start Docker **before** `runserver`, otherwise you may be looking at a different database than you expect.
- Bootstrap and Chart.js are loaded from a CDN, so the pages need an internet connection.
- `admin` sees an "Admin panel" button in the top bar; it opens `/admin/`, where courses, learning outcomes, weights and grades can be edited.

## Everyday commands

```powershell
python manage.py test        # all tests
ruff check . ; ruff format . # lint + format
python manage.py seed_demo   # reset demo data (safe to repeat)
docker compose down          # stop PostgreSQL (data is kept in a volume)
```

## Documentation

See [docs/](docs/): `architecture.md`, `class-diagram.md`, `data-model.md`, `design-decisions.md`, `backlog.md`.

## Scope

Current state is the first checkpoint: setup, data model, scoring, grade entry, student and department dashboards, CI.
Planned: syllabus upload auto-configuration, bulk grade import, AI-generated reports, third-party integrations.
