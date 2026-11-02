"""Pure scoring logic: no Django, no database, only plain data in and out.

Every score is a weighted average:  score = sum(weight * source_score) / sum(weights)

Missing sources are left out of both the numerator and the denominator and the result
is flagged ``is_incomplete``. If nothing feeds a score at all, no score is produced (None).
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ScoreResult:
    score: Decimal
    is_incomplete: bool = False

    def rounded(self, places=1):
        return round(self.score, places)


def to_decimal(value):
    return value if isinstance(value, Decimal) else Decimal(str(value))


def check_weight(weight):
    weight = to_decimal(weight)
    if weight <= 0:
        raise ValueError(f"Weight must be greater than 0, got {weight}")
    return weight


def check_grade(grade):
    grade = to_decimal(grade)
    if not Decimal("0") <= grade <= Decimal("100"):
        raise ValueError(f"Grade must be between 0 and 100, got {grade}")
    return grade


def weighted_average(sources, available):
    """Combine ``sources`` = [(key, weight)] using ``available`` = {key: score}.

    Returns ScoreResult, or None when none of the sources has a score.
    """
    numerator = Decimal("0")
    denominator = Decimal("0")
    missing = False
    for key, weight in sources:
        weight = check_weight(weight)
        if key in available:
            numerator += weight * to_decimal(available[key])
            denominator += weight
        else:
            missing = True
    if denominator == 0:
        return None
    return ScoreResult(score=numerator / denominator, is_incomplete=missing)


def compute_lo_score(assessment_weights, grades):
    """Learning outcome score from [(assessment_key, weight)] and {assessment_key: grade}."""
    checked_grades = {key: check_grade(grade) for key, grade in grades.items()}
    return weighted_average(assessment_weights, checked_grades)


def compute_po_score(lo_weights, lo_results):
    """Program outcome score from [(lo_key, weight)] and {lo_key: ScoreResult}.

    A learning outcome with no score, or an incomplete one, makes the PO incomplete.
    """
    available = {key: result.score for key, result in lo_results.items()}
    result = weighted_average(lo_weights, available)
    if result is None:
        return None
    inherited_incomplete = any(lo_results[key].is_incomplete for key, _ in lo_weights if key in lo_results)
    return ScoreResult(score=result.score, is_incomplete=result.is_incomplete or inherited_incomplete)
