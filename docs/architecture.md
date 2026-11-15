# System architecture

Solid boxes are part of the running system. Dashed boxes are development-only or optional.

```mermaid
flowchart LR
    subgraph Users
        S[Student]
        I[Instructor]
        H[Department Head / Admin]
    end

    B[Browser<br/>Bootstrap 5 + Chart.js]

    subgraph Django["Django 5.2 web app (Python 3.12, gunicorn + WhiteNoise in Docker)"]
        A[accounts<br/>login, roles]
        C[curriculum<br/>POs, courses, LOs, weights,<br/>instructor setup UI, syllabus upload]
        G[grading<br/>enrollments, grades,<br/>grade entry, CSV/XLSX import]
        SC[scoring<br/>signals, recompute, pure services,<br/>dashboards, PO coverage]
        RP[reporting<br/>performance report:<br/>rule-based summary + AI commentary]
        AL[alerts<br/>low-score alerts]
    end

    DB[(PostgreSQL 16<br/>READ COMMITTED)]
    MV[[Materialized view<br/>scoring_department_po_stats]]
    SQLITE[(SQLite<br/>development-only fallback)]

    GEM[[Google Gemini API<br/>only anonymous PO scores are sent]]
    MAIL[[E-mail<br/>console backend, SMTP optional]]
    FILES[[CSV / Excel files<br/>bulk grade import]]

    GH[GitHub repository] --> CI[GitHub Actions CI<br/>ruff, migration check, tests on PostgreSQL]
    CI --> CD[CD: Docker image<br/>published to ghcr.io]

    S & I & H --> B --> Django
    A & C & G & SC & RP & AL --> DB
    DB --- MV
    Django -. dev fallback .-> SQLITE
    RP -.-> GEM
    C -.-> GEM
    AL --> MAIL
    FILES --> G

    style SQLITE stroke-dasharray: 5 5
    style GEM stroke-dasharray: 5 5
```

## Request flow: an instructor saves grades

```mermaid
sequenceDiagram
    participant I as Instructor
    participant V as grading.views.enter_grades
    participant DB as PostgreSQL
    participant R as scoring.recompute
    participant S as scoring.services (pure)

    I->>V: POST grades
    V->>V: validate (0-100), check ownership
    V->>DB: BEGIN
    V->>DB: upsert/delete Grade rows
    DB-->>R: post_save / post_delete signal
    R->>DB: read grades + weights
    R->>S: compute_lo_score / compute_po_score
    S-->>R: ScoreResult(score, is_incomplete)
    R->>DB: write StudentLOScore, StudentPOScore
    V->>DB: COMMIT
    V-->>I: redirect + "saved" message
```

## Layers

| Layer | Where | Rule |
|---|---|---|
| Presentation | `templates/`, views | Role checks on the server (`accounts.permissions.role_required`) |
| Domain logic | `scoring/services.py` | Pure Python, no Django, unit-tested |
| Orchestration | `scoring/recompute.py`, `scoring/signals.py` | Reads DB, calls the service, stores cached scores, always inside `transaction.atomic` |
| Persistence | models + migrations | Constraints enforced in the DB, not only in forms; the department averages come from a materialized view |

## Notifications (low-score alerts)

The `alerts` app e-mails a student when a PO score is below the threshold (`reporting.rules.LOW_SCORE_THRESHOLD`, 60).
`alerts.services.sync_alerts()` keeps one `POAlert` row per student and PO in step with the cached scores, and
`send_pending_alerts()` sends one message per student for the alerts not yet mailed (`emailed_at` empty). It runs from
`manage.py send_alerts` (what a scheduled job would call) or the "Send low-score alerts" button on the department
dashboard. E-mail is deliberately not sent from signals or the recompute (see `docs/design-decisions.md`).
By default Django's console backend prints the message in the terminal; real SMTP is chosen with the `EMAIL_*`
environment variables (see `.env.example`).

## AI commentary and syllabus upload

`reporting` (performance report commentary) and `curriculum.syllabus` (syllabus upload) call the Google Gemini API
(`GEMINI_API_KEY`, `GEMINI_MODEL`). Only anonymous PO scores are sent, never names or student numbers. Without a key
the report still has its rule-based summary.

## Delivery

GitHub Actions CI runs ruff, a migration check and the test suite on PostgreSQL. After CI passes on `main`, the CD
workflow builds the Docker image (gunicorn + WhiteNoise) and publishes it to ghcr.io. There is no deployed production
server; migrations are run on purpose by whoever starts the container.
