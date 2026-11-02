# Design decisions

Answers to the open design questions in the project guidelines (slide 8).

## Setting it up

| Question | Decision |
|---|---|
| Who provides the program outcomes? | Admin / Department Head. The 11 POs are seeded and editable in the admin site. |
| Who creates the courses? | Admin / Department Head (course + offering + instructor assignment). |
| Who creates the learning outcomes? | The instructor of the offering (admin site for now; instructor UI is planned). |
| Who enters the percentages? | The instructor: Assessment -> LO weights and LO -> PO weights (1-5). |

## Grades and syllabi

| Question | Decision |
|---|---|
| Who enters the grades? | The instructor of that offering only. Others get 404. |
| When and how? | Any time, per assessment, in a table form. An empty cell means "no grade yet". Save and recompute happen in one transaction. |
| Syllabus <-> PO relationship | Syllabus = offering's LOs + assessments + weights. LOs link to POs via `LOPOWeight`. Syllabus upload auto-configuration is **planned**. |

## Users and roles

| Role | Can do |
|---|---|
| Admin | Everything in the admin site; department dashboard. |
| Department Head | Manage POs, courses, offerings; department-wide PO statistics. |
| Instructor | Own offerings only: LOs, assessments, weights, grades. |
| Student | Own grades, LO scores and PO profile only (no student id in any URL). |

## Scoring rules

- `score = sum(weight x score) / sum(weights)` at both steps (assessment -> LO, LO -> PO).
- A student's PO score combines every LO -> PO link across all courses.
- **Missing grade:** left out of numerator and denominator, result flagged `is_incomplete`.
  - No grade at all for an LO: no LO score is produced, it does not take part in the PO, and the PO is `is_incomplete`.
  - An incomplete or missing LO makes the PO incomplete.
- **Weights:** LO -> PO is an integer 1-5 in the database (department convention). The pure service accepts any positive decimal, so the guideline's Elif example (1.0 and 0.5) is tested exactly; the DB test and the demo seed use 2 and 1 (same ratio, same 85.0 and 82.9).
- Full precision is kept internally; results are rounded to 1 decimal only for display.

## Technical decisions

| Decision | Why |
|---|---|
| Custom `User` model from day one | Changing the user model later is painful. |
| `Course` vs `CourseOffering` | Weights and LOs can change between semesters without breaking history. |
| Pure `scoring/services.py` | Testable without a database; easy to explain. |
| Cached score tables | Fast dashboards; always recomputed in the same transaction as the change. |
| DB constraints (unique, CHECK) | The database stays valid even if a form is bypassed. |
| PostgreSQL, SQLite fallback | Postgres is needed for CSE 321 features; SQLite keeps local work unblocked when Docker is off. |
| Isolation level: READ COMMITTED | PostgreSQL default. Readers never see a half-finished recompute. Recomputes for different students touch different rows; recomputes for the same student are serialized by locking the student's row (`SELECT ... FOR UPDATE`), always in student-id order to avoid deadlocks. SERIALIZABLE would also work but needs retry logic everywhere. |
| No duplicate indexes | Django already indexes every foreign key; `scoring/test_concurrency.py` checks `pg_index` so duplicates cannot come back. |

## Integrations (possible, planned)

Acibadem OBS export/import of grades and POs, LMS grade import, CSV/Excel bulk grade ingestion, email notifications when scores change.

## Planned features (not built)

Syllabus upload auto-configuration, bulk grade ingestion, AI-generated student performance reports, third-party integrations, instructor UI for LO and weight management.
