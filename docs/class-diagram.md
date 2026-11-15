# Class diagram

```mermaid
classDiagram
    class User {
        +username
        +role : ADMIN | HEAD | INSTRUCTOR | STUDENT
        +student_number
    }
    class ProgramOutcome {
        +number : 1..11
        +short_name
    }
    class Course {
        +code
        +name
    }
    class CourseOffering {
        +term
    }
    class LearningOutcome {
        +code
        +description
    }
    class Assessment {
        +name
    }
    class AssessmentLOWeight {
        +weight : decimal > 0
    }
    class LOPOWeight {
        +weight : int 1..5
    }
    class Enrollment
    class Grade {
        +score : 0..100
    }
    class StudentLOScore {
        +score
        +is_incomplete
    }
    class StudentPOScore {
        +score
        +is_incomplete
    }
    class DepartmentPOStat {
        <<materialized view>>
        +average
        +students
        +incomplete
    }
    class PerformanceReport {
        +created_at
        +scores_snapshot : JSON
        +summary_text
        +ai_commentary
        +ai_model
    }
    class POAlert {
        +score
        +created_at
        +emailed_at
    }

    Course "1" --> "*" CourseOffering
    User "1" --> "*" CourseOffering : instructor
    CourseOffering "1" --> "*" LearningOutcome
    CourseOffering "1" --> "*" Assessment
    Assessment "1" --> "*" AssessmentLOWeight
    LearningOutcome "1" --> "*" AssessmentLOWeight
    LearningOutcome "1" --> "*" LOPOWeight
    ProgramOutcome "1" --> "*" LOPOWeight
    User "1" --> "*" Enrollment : student
    CourseOffering "1" --> "*" Enrollment
    Enrollment "1" --> "*" Grade
    Assessment "1" --> "*" Grade
    Enrollment "1" --> "*" StudentLOScore
    LearningOutcome "1" --> "*" StudentLOScore
    User "1" --> "*" StudentPOScore
    ProgramOutcome "1" --> "*" StudentPOScore
    ProgramOutcome "1" --> "1" DepartmentPOStat : summarized by
    User "1" --> "*" PerformanceReport : student
    User "0..1" --> "*" PerformanceReport : created_by
    User "1" --> "*" POAlert
    ProgramOutcome "1" --> "*" POAlert
```

## Relationships in words

- A **Course** (CSE 311) is taught as many **CourseOfferings** (CSE 311, 2026-Fall, taught by X).
- Learning outcomes, assessments and weights belong to the **offering**, so changing weights next semester never rewrites history.
- `AssessmentLOWeight` and `LOPOWeight` are association classes that carry the weights.
- `Enrollment` ties a student to an offering; `Grade` is one score on one assessment.
- `StudentLOScore` and `StudentPOScore` are cached results (see `data-model.md`).
- `DepartmentPOStat` is an unmanaged model over the materialized view `scoring_department_po_stats` (one read-only row per PO).
- `PerformanceReport` is a saved report for a student (rule-based summary plus optional AI commentary); `POAlert` is one row per student and PO whose score is below the threshold.

## Scoring code (not a model)

```mermaid
classDiagram
    class services {
        <<pure functions>>
        +weighted_average(sources, available)
        +compute_lo_score(assessment_weights, grades)
        +compute_po_score(lo_weights, lo_results)
    }
    class ScoreResult {
        +score : Decimal
        +is_incomplete : bool
    }
    class recompute {
        +recompute_student(student)
        +recompute_offering(offering)
    }
    recompute --> services : calls
    services --> ScoreResult : returns
```
