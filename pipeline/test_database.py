"""Runs the SQL files and the loader against a real, empty, throwaway Postgres.

    pip install -r requirements-dev.txt
    python pipeline/test_database.py

Supabase provides auth.jwt() and the 'authenticated' role. Plain Postgres does not,
so ops/local_supabase_standin.sql plays that part here.
"""
import json
import os
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "pipeline"), str(ROOT / "ops")]
import load_crm  # noqa: E402
from local_postgres import throwaway_postgres  # noqa: E402

CLIENT_A = load_crm.CLIENT_ID
CLIENT_B = "00000000-0000-0000-0000-000000000002"
FIXTURE = json.loads((ROOT / "pipeline" / "test_fixture.json").read_text(encoding="utf-8"))
results = []


def check(name, got, expected):
    results.append(got == expected)
    print(f"{'ok  ' if got == expected else 'FAIL'} {name}" + ("" if got == expected else f": got {got!r}, expected {expected!r}"))


def one(cur, sql, args=None):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def refused(conn, sql):
    """True if the database rejects this statement."""
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.rollback()
        return False
    except psycopg2.Error:
        conn.rollback()
        return True


def visible_as_user(admin, client_id, table="gold_funnel_month"):
    """How many rows a logged-in dashboard user sees, per client."""
    claims = {"app_metadata": {"client_id": client_id}} if client_id else {"app_metadata": {}}
    with admin.cursor() as cur:
        cur.execute("SELECT set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))
        cur.execute("SET LOCAL ROLE authenticated")
        cur.execute(f"SELECT client_id::text, count(*) FROM {table} GROUP BY 1")
        rows = dict(cur.fetchall())
    admin.rollback()
    return rows


def serve(contacts, appointments):
    load_crm.fetch = lambda kind: contacts if kind == "contacts" else appointments    # no real CRM here


def gold(cur):
    cur.execute("""SELECT to_char(month, 'YYYY-MM'), channel, leads, assessments_attended, no_shows, surgeries,
                          revenue::float FROM gold_funnel_month WHERE client_id = %s ORDER BY 1, 2""", (CLIENT_A,))
    return cur.fetchall()


def run_checks(dsn):
    os.environ["DATABASE_URL"] = dsn
    admin = psycopg2.connect(dsn)
    with admin.cursor() as cur:
        # A second client, so "only this client" has something to protect.
        cur.execute("INSERT INTO silver_person (client_id, external_id, created_on) VALUES (%s, 'b', '2026-03-01')", (CLIENT_B,))
        cur.execute("""INSERT INTO silver_operation (client_id, external_id, person_external_id, kind, status, date)
                       VALUES (%s, 'b-1', 'b', 'assessment', 'attended', '2026-03-05')""", (CLIENT_B,))
        cur.execute("SELECT gold_refresh_funnel(%s), gold_refresh_confirmation(%s)", (CLIENT_B, CLIENT_B))
    admin.commit()
    print("ok   the SQL files applied in order")

    contacts, appointments = FIXTURE["contacts"], FIXTURE["appointments"]
    serve(contacts, appointments)
    load_crm.main()
    load_crm.main()                                              # the second run must change nothing

    expected_gold = [("2026-01", "Google", 1, 1, 0, 0, 0.0), ("2026-01", "Website", 1, 0, 0, 0, 0.0),
                     ("2026-02", "Google", 0, 0, 0, 1, 12500.0), ("2026-02", "Referral", 1, 0, 1, 0, 0.0)]
    with admin.cursor() as cur:
        check("bronze keeps 6 records after two runs", one(cur, "SELECT count(*) FROM bronze_raw"), 6)
        check("silver has 3 people, duplicate removed",
              one(cur, "SELECT count(*) FROM silver_person WHERE client_id = %s", (CLIENT_A,)), 3)
        check("silver has 3 appointments",
              one(cur, "SELECT count(*) FROM silver_operation WHERE client_id = %s", (CLIENT_A,)), 3)
        cur.execute("SELECT email, phone, channel, city FROM silver_person WHERE external_id = '1001'")
        check("a messy contact arrives clean", cur.fetchone(), ("ana@example.com", "3125550142", "Google", "Chicago"))
        check("gold values, not only the count", gold(cur), expected_gold)
        cur.execute("""SELECT confirmed, due, attended FROM gold_confirmation_month WHERE client_id = %s
                       ORDER BY confirmed""", (CLIENT_A,))
        check("confirmation values", cur.fetchall(), [(False, 1, 0), (True, 1, 1)])
        check("the other client's gold was not touched",
              one(cur, "SELECT count(*) FROM gold_funnel_month WHERE client_id = %s", (CLIENT_B,)), 1)
    admin.commit()

    # A rescheduled surgery: the new date must reach silver and move gold to the new month.
    serve(contacts, [dict(a, date="2026-03-03") if a["id"] == "5002" else a for a in appointments])
    load_crm.main()
    with admin.cursor() as cur:
        check("rescheduled surgery moves to its new month",
              [r for r in gold(cur) if r[5]], [("2026-03", "Google", 0, 0, 0, 1, 12500.0)])
        check("the changed appointment is kept as a new bronze row", one(cur, "SELECT count(*) FROM bronze_raw"), 7)
    admin.commit()

    # A failed refresh must keep yesterday's gold and not undo the load.
    with admin.cursor() as cur:
        cur.execute("ALTER FUNCTION gold_refresh_funnel(uuid) RENAME TO gold_refresh_hidden")
    admin.commit()
    serve(contacts, appointments)
    load_crm.main()
    with admin.cursor() as cur:
        cur.execute("ALTER FUNCTION gold_refresh_hidden(uuid) RENAME TO gold_refresh_funnel")
        check("failed refresh leaves gold as it was",
              [r for r in gold(cur) if r[5]], [("2026-03", "Google", 0, 0, 0, 1, 12500.0)])
        check("while silver already has the date changed back",
              one(cur, "SELECT date::text FROM silver_operation WHERE external_id = '5002'"), "2026-02-01")
        check("and bronze kept both versions, once each", one(cur, "SELECT count(*) FROM bronze_raw"), 7)
    admin.commit()

    # An empty model run must not wipe yesterday's list.
    with admin.cursor() as cur:
        cur.execute("""INSERT INTO silver_model_score_raw (client_id, person_external_id, model_version, score)
                       VALUES (%s, '1002', 'v1', 0.5), (%s, '1003', 'v1', 0.2)""", (CLIENT_A, CLIENT_A))
        check("scores promoted", one(cur, "SELECT gold_promote_lead_score(%s)", (CLIENT_A,)), 2)
        cur.execute("SELECT person_external_id, place FROM gold_lead_score ORDER BY place")
        check("highest score gets place 1", cur.fetchall(), [("1002", 1), ("1003", 2)])
        cur.execute("DELETE FROM silver_model_score_raw")
        check("empty model run promotes nothing", one(cur, "SELECT gold_promote_lead_score(%s)", (CLIENT_A,)), 0)
        check("and keeps the previous list", one(cur, "SELECT count(*) FROM gold_lead_score"), 2)
    admin.commit()

    # Row level security: only the login token decides.
    check("user of client A sees only A", set(visible_as_user(admin, CLIENT_A)), {CLIENT_A})
    check("user of client B sees only B", visible_as_user(admin, CLIENT_B), {CLIENT_B: 1})
    check("account with no client sees nothing", visible_as_user(admin, None), {})
    check("confirmation is isolated too", set(visible_as_user(admin, CLIENT_B, "gold_confirmation_month")), {CLIENT_B})
    check("the call list is isolated too", visible_as_user(admin, CLIENT_B, "gold_lead_score"), {})
    check("dashboard users can't read raw scores", visible_as_user(admin, CLIENT_A, "silver_model_score_raw"), {})
    with admin.cursor() as cur:
        cur.execute("SELECT set_config('request.jwt.claims', %s, true)", (json.dumps({"app_metadata": {"client_id": CLIENT_A}}),))
        cur.execute("SET LOCAL ROLE authenticated")
        check("dashboard users can't read bronze", one(cur, "SELECT count(*) FROM bronze_raw"), 0)
    admin.rollback()

    # The AI's user: a real login, because its limits only apply at login.
    agent = psycopg2.connect(dsn, user="demo_agent_ro")
    with agent.cursor() as cur:
        check("agent sees its own client", one(cur, "SELECT count(*) FROM silver_operation"), 3)
        check("agent sees 0 rows of the other client",
              one(cur, "SELECT count(*) FROM silver_operation WHERE client_id = %s", (CLIENT_B,)), 0)
        check("agent session is read only", one(cur, "SHOW default_transaction_read_only"), "on")
    agent.rollback()
    write = f"INSERT INTO silver_person (client_id, external_id) VALUES ('{CLIENT_A}', 'x')"
    check("agent write is refused", refused(agent, write), True)
    check("agent write is refused even after switching read only off",
          refused(agent, f"SET default_transaction_read_only = off; {write}"), True)
    check("agent cannot read gold", refused(agent, "SELECT * FROM gold_funnel_month"), True)
    agent.close()
    admin.close()


def main() -> int:
    with throwaway_postgres() as dsn:
        run_checks(dsn)
    print(f"{sum(results)} of {len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
