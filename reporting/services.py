from decimal import Decimal

from django.conf import settings
from django.db.models import Avg

from curriculum.models import ProgramOutcome
from reporting import llm, rules
from reporting.models import PerformanceReport
from scoring.models import StudentPOScore


def _decimal_or_none(value):
    return None if value is None else Decimal(str(value))


def collect_rows(student):
    """The student's PO rows (score None when there is no score yet) with department averages."""
    scores = {s.program_outcome_id: s for s in StudentPOScore.objects.filter(student=student)}
    averages = dict(StudentPOScore.objects.values_list("program_outcome_id").annotate(avg=Avg("score")))
    rows = []
    for po in ProgramOutcome.objects.all():
        score = scores.get(po.id)
        average = _decimal_or_none(averages.get(po.id))
        rows.append(
            {
                "number": po.number,
                "name": po.short_name,
                "score": score.score if score else None,
                "incomplete": bool(score and score.is_incomplete),
                "department_average": average.quantize(Decimal("0.0001")) if average is not None else None,
            }
        )
    return rows


def to_snapshot(rows):
    """JSON-safe copy of the rows: Decimals become strings."""
    return [
        {
            **row,
            "score": None if row["score"] is None else str(row["score"]),
            "department_average": None if row["department_average"] is None else str(row["department_average"]),
        }
        for row in rows
    ]


def own_scores(snapshot):
    """Only the student's own numbers from a snapshot (used to decide whether a report is still current)."""
    return [(row["number"], row["score"], row["incomplete"]) for row in snapshot]


def build_prompt(rows):
    # Personal data is deliberately excluded: only PO numbers, short names, scores,
    # incomplete flags and department averages go to the external API. Never add
    # a name, username, student number, email or course-level grades here.
    lines = []
    for r in rows:
        if r["score"] is None:
            score = "no score yet"
        else:
            score = f"{r['score']:.1f}" + (" (incomplete: some grades are missing)" if r["incomplete"] else "")
        average = "n/a" if r["department_average"] is None else f"{r['department_average']:.1f}"
        lines.append(f"- PO{r['number']} ({r['name']}): score {score}; department average {average}")
    return (
        "You are an academic advisor. Below are one student's Program Outcome (PO) scores on a 0-100 scale, "
        "next to the department average for each PO.\n"
        "Some scores are marked incomplete (grades are still missing) and some POs have no score yet; "
        "say so where relevant.\n\n"
        + "\n".join(lines)
        + "\n\nWrite a short, constructive commentary of about 150 words with 2 or 3 concrete suggestions. "
        "Comment only on the numbers given above. Do not invent numbers and do not recompute or "
        "change any score. Use plain text without markdown."
    )


def build_report(student, created_by):
    rows = collect_rows(student)
    snapshot = to_snapshot(rows)

    # Reuse the stored report (no API call) when the student's own scores are unchanged.
    # Department averages move whenever any other student is graded, so they are not compared.
    # A report that has no AI commentary yet is rebuilt once AI is available.
    latest = PerformanceReport.objects.filter(student=student).first()
    if latest is not None and own_scores(latest.scores_snapshot) == own_scores(snapshot):
        if latest.ai_commentary or not llm.is_configured():
            return latest

    commentary, model = "", ""
    if llm.is_configured():
        try:
            commentary = llm.generate_text(build_prompt(rows))
            model = settings.GEMINI_MODEL
        except llm.LLMError:
            commentary = ""  # the page then shows the rule-based summary alone

    return PerformanceReport.objects.create(
        student=student,
        created_by=created_by,
        scores_snapshot=snapshot,
        summary_text=rules.summary_to_text(rules.summarize(rows)),
        ai_commentary=commentary,
        ai_model=model,
    )
