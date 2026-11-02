# System architecture

Solid boxes exist today. Dashed boxes are **planned** (not built yet).

```mermaid
flowchart LR
    subgraph Users
        S[Student]
        I[Instructor]
        H[Department Head / Admin]
    end

    B[Browser<br/>Bootstrap + Chart.js]

    subgraph Django["Django web app (Python)"]
        A[accounts<br/>login, roles]
        C[curriculum<br/>POs, courses, LOs, weights]
        G[grading<br/>enrollments, grades]
        SC[scoring<br/>pure service + recompute + dashboards]
    end

    DB[(PostgreSQL 16)]
    SQLITE[(SQLite<br/>local fallback)]

    CACHE[[Cache<br/>planned]]
    NOTIF[[Notification service<br/>planned]]
    EXT[[3rd-party integrations<br/>OBS / LMS import<br/>planned]]
    AI[[AI report + syllabus upload<br/>planned]]

    S & I & H --> B --> Django
    A & C & G & SC --> DB
    Django -. dev fallback .-> SQLITE
    SC -.-> CACHE
    Django -.-> NOTIF
    Django -.-> EXT
    Django -.-> AI

    style CACHE stroke-dasharray: 5 5
    style NOTIF stroke-dasharray: 5 5
    style EXT stroke-dasharray: 5 5
    style AI stroke-dasharray: 5 5
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
| Persistence | models + migrations | Constraints enforced in the DB, not only in forms |
