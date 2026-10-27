from django.db import DatabaseError, connection, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET


def result(ready):
    response = JsonResponse(
        {"status": "ok" if ready else "unavailable"}, status=200 if ready else 503
    )
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def live(request):
    return result(True)


@require_GET
def ready(request):
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '1000ms'")
            cursor.execute("SELECT 1")
            healthy = cursor.fetchone() == (1,)
    except DatabaseError:
        healthy = False
    return result(healthy)
