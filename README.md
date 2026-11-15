# PO Score Management System

Web system that manages each student's Program Outcome (PO) scores for Acibadem CSE.
CSE 311 (Software) and CSE 321 (Data Systems) team project, Fall 2026. Stack: Python 3.12 + Django 5.2 + PostgreSQL.

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

## Deployment / CD

Two GitHub Actions workflows live in `.github/workflows/`:

- `ci.yml` (CI): on every push and pull request it runs ruff, the migration check and the tests on PostgreSQL.
- `cd.yml` (CD): when CI has finished successfully for a push to `main`, it checks out that exact commit, builds the `Dockerfile` and pushes the image to the GitHub Container Registry as `ghcr.io/teomanksrc/cse311-project` with two tags: `latest` and the commit SHA. It only uses the built-in `GITHUB_TOKEN`. It can also be started by hand from the Actions tab. Delivery stops at the published image; no server is deployed to yet.

Run the published image against a PostgreSQL database (variables as in `.env.example`; the image has no `.env` and applies no migrations by itself):

```bash
docker pull ghcr.io/teomanksrc/cse311-project:latest   # a private package needs: docker login ghcr.io

docker run -d --name po-app -p 8000:8000   -e DJANGO_SECRET_KEY=<long-random-string>   -e DJANGO_DEBUG=False   -e DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1   -e POSTGRES_DB=po_system -e POSTGRES_USER=po_user -e POSTGRES_PASSWORD=po_password   -e POSTGRES_HOST=host.docker.internal -e POSTGRES_PORT=5432   ghcr.io/teomanksrc/cse311-project:latest

docker exec po-app python manage.py migrate      # deliberate step, run once per release
docker exec po-app python manage.py seed_demo    # optional demo data
```

Then open http://localhost:8000/. If PostgreSQL is not reachable the app falls back to SQLite inside the container (see the notes above), so check `POSTGRES_HOST`. To build the image locally instead: `docker build -t po-system .`

## Documentation

See [docs/](docs/): `architecture.md`, `class-diagram.md`, `data-model.md`, `design-decisions.md`, `backlog.md`.

## Scope

Current state is the first checkpoint: setup, data model, scoring, grade entry, student and department dashboards, CI.
Planned: syllabus upload auto-configuration, bulk grade import, AI-generated reports, third-party integrations.
