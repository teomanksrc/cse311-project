"""Rule-based summary of a student's PO scores. Pure Python, no Django.

Each row is a dict:
{"number": 1, "name": "...", "score": Decimal or None, "incomplete": bool, "department_average": Decimal or None}
"""

from decimal import Decimal

LOW_SCORE_THRESHOLD = Decimal("60")
TOP_COUNT = 3  # how many strongest / weakest POs to list


def summarize(rows):
    """Return a dict of lists of rows, grouped by what the report wants to say."""
    scored = [r for r in rows if r["score"] is not None]
    ranked = sorted(scored, key=lambda r: (-r["score"], r["number"]))
    n = min(TOP_COUNT, len(ranked) // 2)  # never list the same PO as both strongest and weakest
    comparison = []
    for r in scored:
        if r["department_average"] is not None:
            comparison.append({**r, "difference": r["score"] - r["department_average"]})
    return {
        "strongest": ranked[:n],
        "weakest": list(reversed(ranked[len(ranked) - n :])) if n else [],
        "below_threshold": [r for r in scored if r["score"] < LOW_SCORE_THRESHOLD],
        "incomplete": [r for r in scored if r["incomplete"]],
        "no_score": [r for r in rows if r["score"] is None],
        "comparison": comparison,
    }


def _one_decimal(value):
    return f"{value:.1f}"


def _label(row):
    return f"PO{row['number']} ({row['name']})"


def _labels(rows):
    return ", ".join(_label(r) for r in rows)


def summary_to_text(summary):
    """Turn the summary into a few readable English sentences."""
    sentences = []
    if summary["strongest"]:
        parts = [f"{_label(r)} at {_one_decimal(r['score'])}" for r in summary["strongest"]]
        sentences.append("Strongest outcomes: " + ", ".join(parts) + ".")
    if summary["weakest"]:
        parts = [f"{_label(r)} at {_one_decimal(r['score'])}" for r in summary["weakest"]]
        sentences.append("Weakest outcomes: " + ", ".join(parts) + ".")
    if summary["below_threshold"]:
        sentences.append(f"Below the threshold of {LOW_SCORE_THRESHOLD}: " + _labels(summary["below_threshold"]) + ".")
    elif summary["strongest"]:
        sentences.append(f"No outcome is below the threshold of {LOW_SCORE_THRESHOLD}.")
    if summary["incomplete"]:
        sentences.append("Based on incomplete data (some grades are missing): " + _labels(summary["incomplete"]) + ".")
    if summary["no_score"]:
        sentences.append("No score yet: " + _labels(summary["no_score"]) + ".")
    if summary["comparison"]:
        above = [r for r in summary["comparison"] if r["difference"] > 0]
        below = [r for r in summary["comparison"] if r["difference"] < 0]
        sentences.append(
            f"Compared with the department average, the student is above it in {len(above)} "
            f"and below it in {len(below)} of {len(summary['comparison'])} comparable outcomes."
        )
        if below:
            worst = min(below, key=lambda r: r["difference"])
            sentences.append(
                f"The largest gap below the department average is {_label(worst)}, "
                f"{_one_decimal(-worst['difference'])} points lower."
            )
    if not sentences:
        sentences.append("There are no scores yet, so no summary can be given.")
    return " ".join(sentences)
