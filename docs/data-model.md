# Data model

```mermaid
erDiagram
    USER ||--o{ COURSE_OFFERING : "teaches"
    USER ||--o{ ENROLLMENT : "student"
    USER ||--o{ STUDENT_PO_SCORE : "has"
    COURSE ||--o{ COURSE_OFFERING : "offered as"
    COURSE_OFFERING ||--o{ LEARNING_OUTCOME : "defines"
    COURSE_OFFERING ||--o{ ASSESSMENT : "defines"
    COURSE_OFFERING ||--o{ ENROLLMENT : "has"
    ASSESSMENT ||--o{ ASSESSMENT_LO_WEIGHT : "feeds"
    LEARNING_OUTCOME ||--o{ ASSESSMENT_LO_WEIGHT : "fed by"
    LEARNING_OUTCOME ||--o{ LO_PO_WEIGHT : "feeds"
    PROGRAM_OUTCOME ||--o{ LO_PO_WEIGHT : "fed by"
    ENROLLMENT ||--o{ GRADE : "has"
    ASSESSMENT ||--o{ GRADE : "graded in"
    ENROLLMENT ||--o{ STUDENT_LO_SCORE : "has"
    LEARNING_OUTCOME ||--o{ STUDENT_LO_SCORE : "scored"
    PROGRAM_OUTCOME ||--o{ STUDENT_PO_SCORE : "scored"

    USER { bigint id PK
           string username UK
           string role
           string student_number UK }
    PROGRAM_OUTCOME { bigint id PK
                      smallint number UK
                      string short_name }
    COURSE { bigint id PK
             string code UK
             string name }
    COURSE_OFFERING { bigint id PK
                      bigint course_id FK
                      string term
                      bigint instructor_id FK }
    LEARNING_OUTCOME { bigint id PK
                       bigint offering_id FK
                       string code }
    ASSESSMENT { bigint id PK
                 bigint offering_id FK
                 string name }
    ASSESSMENT_LO_WEIGHT { bigint id PK
                           bigint assessment_id FK
                           bigint learning_outcome_id FK
                           decimal weight }
    LO_PO_WEIGHT { bigint id PK
                   bigint learning_outcome_id FK
                   bigint program_outcome_id FK
                   smallint weight }
    ENROLLMENT { bigint id PK
                 bigint student_id FK
                 bigint offering_id FK }
    GRADE { bigint id PK
            bigint enrollment_id FK
            bigint assessment_id FK
            decimal score }
    STUDENT_LO_SCORE { bigint id PK
                       bigint enrollment_id FK
                       bigint learning_outcome_id FK
                       decimal score
                       bool is_incomplete }
    STUDENT_PO_SCORE { bigint id PK
                       bigint student_id FK
                       bigint program_outcome_id FK
                       decimal score
                       bool is_incomplete }
```

## Tables

| Table | Purpose | Constraints and indexes |
|---|---|---|
| `accounts_user` | Login + role | `username` unique, `student_number` unique |
| `curriculum_programoutcome` | The 11 department POs | `number` unique |
| `curriculum_course` | Catalogue entry (CSE 311) | `code` unique |
| `curriculum_courseoffering` | Course in a term, with its instructor | unique (course, term) |
| `curriculum_learningoutcome` | LO of one offering | unique (offering, code) |
| `curriculum_assessment` | Midterm, project, ... of one offering | unique (offering, name) |
| `curriculum_assessmentloweight` | Assessment -> LO weight | unique (assessment, LO); CHECK weight > 0 |
| `curriculum_lopoweight` | LO -> PO weight | unique (LO, PO); CHECK weight BETWEEN 1 AND 5 |
| `grading_enrollment` | Student in an offering | unique (student, offering) |
| `grading_grade` | One score on one assessment | unique (enrollment, assessment); CHECK 0 <= score <= 100; FK indexes on `assessment_id` and `enrollment_id` (created by Django) |
| `scoring_studentloscore` | **Cached** LO score | unique (enrollment, LO) |
| `scoring_studentposcore` | **Cached** PO score | unique (student, PO); FK index on `program_outcome_id` |

## Normalized vs denormalized

- **Normalized (3NF):** everything in `accounts`, `curriculum` and `grading`. Each fact is stored once: a weight lives in exactly one row, a grade in exactly one row. This is the source of truth.
- **Denormalized on purpose:** `StudentLOScore` and `StudentPOScore`. They are derived values that could be recomputed from grades and weights at any time. We store them so dashboards read one row per student and PO instead of joining and aggregating grades, weights and LOs for every page view.
- **Keeping the cache correct:** signals on `Grade`, `Enrollment`, `AssessmentLOWeight` and `LOPOWeight` call `scoring.recompute`, inside the same transaction as the change. If a score has no sources anymore, its cached row is deleted so stale values never remain.
- **Not a star/snowflake warehouse (yet):** the operational schema is normalized. A star schema with `StudentPOScore` as a fact table is a possible future analytics layer.

## Final row counts and sizes (CSE 321 report)

Fill in at the end of the project, from the production-like database:

```sql
SELECT relname, n_live_tup, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_stat_user_tables ORDER BY relname;
```

## Planned for the final (not built yet)

Index tuning from real query plans, a materialized view for department averages, partitioning of `grading_grade` by term, replication and failure handling.
