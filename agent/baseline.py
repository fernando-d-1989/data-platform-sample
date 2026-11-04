"""Nightly data check. No AI here. Known answers about a CLOSED past period should not
move, so if one does, the data or a definition changed, not the model.

The answers were frozen from the website's screens for April to September 2025.
A tolerance, not exact decimals: late records drip in on a live table, and a false
alarm teaches people to ignore the check."""
import os
import sys

import psycopg2

CLIENT_ID = "00000000-0000-0000-0000-000000000001"   # invented
PERIOD = ("2025-04", "2025-09")
TOLERANCE_POINTS = 0.1
KNOWN = {
    "surgeries": 301,
    "attendance %": 63.17,          # 585 came of 926 due
    "surgeries per 100 assessments": 51.45,
}


def measure(cur) -> dict:
    cur.execute("""SELECT sum(surgeries), sum(assessments_attended), sum(no_shows) FROM gold_funnel_month
                   WHERE client_id = %s AND to_char(month, 'YYYY-MM') BETWEEN %s AND %s""", (CLIENT_ID, *PERIOD))
    surgeries, came, missed = (float(v) for v in cur.fetchone())
    return {"surgeries": surgeries, "attendance %": 100 * came / (came + missed),
            "surgeries per 100 assessments": 100 * surgeries / came}


def main() -> int:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn.cursor() as cur:
        got = measure(cur)
    conn.close()
    failed = []
    for name, expected in KNOWN.items():
        ok = abs(got[name] - expected) < TOLERANCE_POINTS
        print(f"{name:<32}{got[name]:>8.2f}   expected {expected:>8.2f}   {'ok' if ok else 'MOVED'}")
        failed += [] if ok else [name]
    print("failed:", failed or "none")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
