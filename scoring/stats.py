"""Department-level statistics (materialized view upkeep)."""

from django.db import connection


def refresh_department_stats():
    """Refresh the department averages. Call it after a transaction that changed scores has committed.

    Never call it from inside ``recompute_student``: REFRESH takes an exclusive lock on the view
    until the transaction ends, and a recompute holds student row locks, so two transactions could
    wait for each other (deadlock). See docs/design-decisions.md.

    Plain REFRESH, not CONCURRENTLY: the view has 11 rows and refreshes in milliseconds, and
    CONCURRENTLY cannot run inside a transaction block (Django tests and atomic views use one).
    On SQLite the object is an ordinary view that is always current, so there is nothing to do.
    """
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW scoring_department_po_stats")
