"""Explicit unrelated owner for secondary-property authorization fixtures."""

from contextlib import contextmanager

from django.db import connection
from django.test.utils import CaptureQueriesContext

from .models import User


def unrelated_owner():
    user, _ = User.objects.get_or_create(
        email="unrelated-owner@example.test",
        defaults={
            "username": "unrelated-owner@example.test",
            "name": "Unrelated test owner",
            "password": "!",
        },
    )
    return user


@contextmanager
def assert_calendar_query_budget(test_case, *, cold_quota=True):
    """Keep the four domain reads separate from the real, bounded quota overhead."""
    with CaptureQueriesContext(connection) as captured:
        yield
    queries = [entry["sql"] for entry in captured]
    counter_queries = [sql for sql in queries if '"booking_loginattempt"' in sql]
    transaction_queries = [
        sql for sql in queries if sql.startswith(("SAVEPOINT ", "RELEASE SAVEPOINT "))
    ]
    domain_queries = [
        sql for sql in queries if sql not in counter_queries and sql not in transaction_queries
    ]
    # A newly created window: SELECT/INSERT/UPDATE + two savepoint pairs.
    # A warm window: SELECT/UPDATE + one savepoint pair. No limiter mock.
    test_case.assertEqual(
        [sql.split()[0] for sql in counter_queries],
        ["SELECT", "INSERT", "UPDATE"] if cold_quota else ["SELECT", "UPDATE"],
    )
    test_case.assertEqual(len(transaction_queries), 4 if cold_quota else 2)
    test_case.assertEqual(len(domain_queries), 4, domain_queries)
    test_case.assertEqual(len(queries), 11 if cold_quota else 8)
