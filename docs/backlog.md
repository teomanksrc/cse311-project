# Product backlog

Story points use the Fibonacci scale (1, 2, 3, 5, 8). Move these into GitHub Projects (or the team's chosen tool); the tool choice belongs in the CSE 311 report, section 1.

Status: **Done** = exists in the current foundation, **Todo** = not built yet.

## Epic A: Foundation

| # | User story | Pts | Status |
|---|---|---|---|
| A1 | As a developer, I can set up the project (Django, Postgres via Docker, `.env`) in one README | 3 | Done |
| A2 | As a developer, CI runs lint and tests on every push against PostgreSQL | 3 | Done |
| A3 | As an admin, I can log in with a role (admin, head, instructor, student) | 3 | Done |

## Epic B: Curriculum setup

| # | User story | Pts | Status |
|---|---|---|---|
| B1 | As a head, I can manage the 11 POs | 2 | Done (admin site) |
| B2 | As a head, I can create courses, offerings and assign instructors | 3 | Done (admin site) |
| B3 | As an instructor, I can define LOs, assessments and weights for my offering | 5 | Todo (instructor UI; admin site works today) |
| B4 | As an instructor, weights are validated (positive, 1-5) | 2 | Done |

## Epic C: Grades and scores

| # | User story | Pts | Status |
|---|---|---|---|
| C1 | As an instructor, I can enter grades for an assessment in a table | 5 | Done |
| C2 | As the system, I compute LO and PO scores with weighted averages | 8 | Done |
| C3 | As a student, I see a PO score reported as incomplete when grades are missing | 3 | Done |
| C4 | As the system, scores are recomputed when grades or weights change | 5 | Done |

## Epic D: Dashboards

| # | User story | Pts | Status |
|---|---|---|---|
| D1 | As a student, I see my PO profile as a chart plus per-course LO breakdown | 5 | Done |
| D2 | As a head, I see the average score per PO | 3 | Done |
| D3 | As a head, I can filter the department view by course, term or student group | 5 | Todo |

## Epic E: Innovative features (the higher bar)

| # | User story | Pts | Status |
|---|---|---|---|
| E1 | As an instructor, I upload a syllabus and the LOs/assessments/weights are proposed automatically | 8 | Todo |
| E2 | As an instructor, I import grades in bulk from CSV/Excel | 5 | Todo |
| E3 | As a head, I generate a student or cohort performance report (PDF) | 8 | Todo |
| E4 | As a student, I get an alert when a PO falls below a threshold | 5 | Todo |
| E5 | As a head, I see which POs are weakly covered by the current syllabi | 5 | Todo |

## Epic F: Data systems (CSE 321)

| # | User story | Pts | Status |
|---|---|---|---|
| F1 | Index tuning from real query plans | 3 | Todo |
| F2 | Materialized view for department averages | 5 | Todo |
| F3 | Partitioning and replication plan | 5 | Todo |
| F4 | Failure handling and backups | 3 | Todo |

## Proposed sprints (1 week each)

Midterms to plan around: CSE 311 on 10 Nov and 22 Dec, CSE 321 on 19 Nov and 24 Dec.

| Sprint | Dates | Goal | Stories |
|---|---|---|---|
| 1 | 26 Oct - 1 Nov | Foundation, models, scoring | A1, A3, B1, B2, B4, C2 |
| 2 | 2 - 8 Nov | Grades, dashboards, CI, docs; **checkpoint prep** | A2, C1, C3, C4, D1, D2 |
| Checkpoint | 12 / 17 Nov | Presentations and reports | |
| 3 | 18 - 29 Nov | Instructor UI, bulk import | B3, E2 |
| 4 | 30 Nov - 6 Dec | Syllabus upload | E1 |
| 5 | 7 - 13 Dec | Reports and alerts | E3, E4 |
| 6 | 14 - 20 Dec | Data systems tuning | F1, F2, F3, D3 |
| 7 | 21 - 27 Dec | Hardening, polish, final report | F4, E5 |
| Final | 29 - 30 Dec | Demo and hardcopy report | |

Velocity so far: fill in at the end of each sprint (points Done / sprint). Difficulty is rated with Fibonacci story points in planning.
