"""Reproduce synthetic index plans in a disposable local PostgreSQL database.

Run with backend/.venv/bin/python ops/monitoring/benchmark-indexes.py.
Never connects to a remote host and never loads project settings or real data.
The temporary database is removed after the plans are written.
"""

import json
import statistics
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

LOCAL = "postgresql://calendar_test@127.0.0.1:55439/calendar_qa"
DATABASE = "sre_index_bench_" + uuid4().hex[:10]
REPORT = Path("output/sre-query-plans.txt")
NOW = "'2026-11-09 00:00:00+00'::timestamptz"

QUERIES = {
    "active_jobs": f"""
        SELECT p.provider, p.environment, j.kind, j.state, count(*),
               count(*) FILTER (WHERE j.state='pending' AND j.available_at <= {NOW}),
               min(j.available_at) FILTER (WHERE j.state='pending' AND j.available_at <= {NOW}),
               count(*) FILTER (WHERE j.state='running' AND j.lease_until < {NOW})
        FROM payment_job j JOIN payment_attempt p ON p.id=j.payment_id
        WHERE j.state <> 'done' GROUP BY p.provider,p.environment,j.kind,j.state
    """,
    "claim_job": f"""
        SELECT id FROM payment_job
        WHERE (state='pending' AND available_at <= {NOW})
           OR (state='running' AND lease_until < {NOW})
        ORDER BY available_at,id LIMIT 1 FOR UPDATE SKIP LOCKED
    """,
    "active_refunds": """
        SELECT p.provider,p.environment,r.status,count(*),min(r.created_at)
        FROM refund_request r JOIN payment_attempt p ON p.id=r.payment_id
        WHERE r.status IN ('queued','submitted','reconciliation_required')
        GROUP BY p.provider,p.environment,r.status
    """,
    "recent_webhooks": f"""
        SELECT p.provider,p.environment,count(*),max(w.received_at)
        FROM webhook_delivery w JOIN payment_attempt p ON p.id=w.payment_id
        WHERE w.received_at >= {NOW} - interval '1 hour'
        GROUP BY p.provider,p.environment
    """,
    "pending_holds": f"""
        SELECT count(*) FILTER (WHERE hold_expires_at <= {NOW}),
               min(hold_expires_at) FILTER (WHERE hold_expires_at <= {NOW}),
               count(*) FILTER (WHERE hold_expires_at IS NULL)
        FROM booking WHERE status='pending'
    """,
}
INDEXES = {
    "payment_job_active_idx": "CREATE INDEX payment_job_active_idx ON payment_job(state,available_at) WHERE state <> 'done'",
    "payment_job_lease_idx": "CREATE INDEX payment_job_lease_idx ON payment_job(state,lease_until)",
    "refund_status_age_idx": "CREATE INDEX refund_status_age_idx ON refund_request(status,created_at)",
    "webhook_received_at_idx": "CREATE INDEX webhook_received_at_idx ON webhook_delivery(received_at)",
    "booking_pending_hold_idx": "CREATE INDEX booking_pending_hold_idx ON booking(hold_expires_at) WHERE status='pending'",
}


def plans(connection):
    result = {}
    for name, query in QUERIES.items():
        runs = []
        for _ in range(6):
            plan = connection.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query
            ).fetchone()[0][0]
            runs.append(plan["Execution Time"])
        result[name] = {
            "median_ms_5_warm_runs": statistics.median(runs[1:]),
            "plan": plan,
        }
    return result


def main():
    report = {
        "kind": "synthetic-local-plan-comparison-not-production-capacity",
        "postgresql": "17",
        "warm_runs": 5,
        "queries": QUERIES,
        "candidate_indexes": INDEXES,
        "limitations": "Synthetic narrow tables, vacuumed visibility map, warm cache; serial query execution with parallel gather and JIT disabled. Not end-to-end or production capacity evidence.",
        "decision": "Retain active-refund, recent-webhook and pending-hold indexes. Reject both payment_job_lease_idx and payment_job_active_idx: repeated trials showed variable financial claim plans without a stable hot-path benefit; the original queue aggregate remains within the pilot collection timeout.",
    }
    admin = psycopg.connect(LOCAL, autocommit=True)
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DATABASE)))
    try:
        with psycopg.connect(LOCAL, dbname=DATABASE, autocommit=True) as connection:
            connection.execute("SET max_parallel_workers_per_gather = 0")
            connection.execute("SET jit = off")
            connection.execute(
                "CREATE TABLE payment_attempt(id bigint PRIMARY KEY, provider text, environment text)"
            )
            connection.execute(
                "INSERT INTO payment_attempt SELECT n, 'xpayment', CASE WHEN n%2=0 THEN 'production' ELSE 'sandbox' END FROM generate_series(1,25000) n"
            )
            connection.execute(
                "CREATE TABLE payment_job(id bigint PRIMARY KEY,payment_id bigint,kind text,state text,available_at timestamptz,lease_until timestamptz)"
            )
            connection.execute(f"""
                INSERT INTO payment_job
                SELECT n,(n%25000)+1,'verify',
                  CASE WHEN n%1000=0 THEN 'dead' WHEN n%500=1 THEN 'running'
                       WHEN n%100=2 THEN 'pending' ELSE 'done' END,
                  {NOW} + CASE WHEN n%200=2 THEN interval '1 hour' ELSE -interval '10 minutes' END,
                  {NOW} + CASE WHEN n%5000=1 THEN -interval '1 minute' ELSE interval '1 minute' END
                FROM generate_series(1,250000) n
            """)
            connection.execute(
                "CREATE INDEX existing_job_state_available ON payment_job(state,available_at)"
            )
            connection.execute(
                "CREATE INDEX existing_job_payment ON payment_job(payment_id)"
            )
            connection.execute(
                "CREATE TABLE refund_request(id bigint PRIMARY KEY,payment_id bigint,status text,created_at timestamptz)"
            )
            connection.execute(
                f"INSERT INTO refund_request SELECT n,(n%25000)+1,CASE WHEN n%200=0 THEN 'submitted' ELSE 'succeeded' END,{NOW}-interval '1 day' FROM generate_series(1,100000) n"
            )
            connection.execute(
                "CREATE INDEX existing_refund_payment ON refund_request(payment_id)"
            )
            connection.execute(
                "CREATE TABLE webhook_delivery(id bigint PRIMARY KEY,payment_id bigint,received_at timestamptz)"
            )
            connection.execute(
                f"INSERT INTO webhook_delivery SELECT n,(n%25000)+1,{NOW}-CASE WHEN n%1000=0 THEN interval '30 minutes' ELSE interval '30 days' END FROM generate_series(1,250000) n"
            )
            connection.execute(
                "CREATE INDEX existing_webhook_payment ON webhook_delivery(payment_id)"
            )
            connection.execute(
                "CREATE TABLE booking(id bigint PRIMARY KEY,resort_id bigint,status text,created_at timestamptz,hold_expires_at timestamptz)"
            )
            connection.execute(f"""
                INSERT INTO booking SELECT n,(n%1000)+1,CASE WHEN n%100=0 THEN 'pending' ELSE 'confirmed' END,
                  {NOW}-interval '1 day',
                  CASE WHEN n%5000=0 THEN NULL WHEN n%200=0 THEN {NOW}-interval '10 minutes' ELSE {NOW}+interval '10 minutes' END
                FROM generate_series(1,250000) n
            """)
            connection.execute(
                "CREATE INDEX existing_booking_resort_status_created ON booking(resort_id,status,created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX existing_booking_hold_expiry ON booking(hold_expires_at)"
            )
            for table in (
                "payment_attempt",
                "payment_job",
                "refund_request",
                "webhook_delivery",
                "booking",
            ):
                connection.execute(
                    sql.SQL("VACUUM ANALYZE {}").format(sql.Identifier(table))
                )
            report["rows"] = {
                table: connection.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                ).fetchone()[0]
                for table in (
                    "payment_attempt",
                    "payment_job",
                    "refund_request",
                    "webhook_delivery",
                    "booking",
                )
            }
            report["before"] = plans(connection)
            for command in INDEXES.values():
                connection.execute(command)
            report["after_all_candidates"] = plans(connection)
            report["index_bytes"] = {
                name: connection.execute(
                    "SELECT pg_relation_size(%s)", [name]
                ).fetchone()[0]
                for name in INDEXES
            }
            connection.execute("DROP INDEX payment_job_lease_idx")
            report["without_lease_index"] = plans(connection)
            connection.execute("DROP INDEX payment_job_active_idx")
            report["final_retained_indexes"] = plans(connection)
            report["retained_indexes"] = [
                "refund_status_age_idx",
                "webhook_received_at_idx",
                "booking_pending_hold_idx",
            ]
            report["rejected_indexes"] = [
                "payment_job_active_idx",
                "payment_job_lease_idx",
            ]
        REPORT.parent.mkdir(exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    finally:
        admin.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(DATABASE))
        )
        admin.close()
    print(
        json.dumps(
            {
                "report": str(REPORT),
                "rows": report["rows"],
                "timings_ms": {
                    stage: {
                        name: value["median_ms_5_warm_runs"]
                        for name, value in report[stage].items()
                    }
                    for stage in (
                        "before",
                        "after_all_candidates",
                        "without_lease_index",
                        "final_retained_indexes",
                    )
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
