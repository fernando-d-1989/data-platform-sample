"""One client's nightly job: CRM -> bronze -> silver -> gold.

Safe to run twice: inserts skip or update what already exists.
Silver is built from bronze, never straight from the CRM, so it can always be rebuilt.
Gold is refreshed last, so a screen never shows old numbers stamped as new.
"""
import gzip
import json
import os
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import Json, execute_values

import transform as t

load_dotenv(".env")
CLIENT_ID = "00000000-0000-0000-0000-000000000001"   # invented
SOURCES = {"contacts": "crm_clinic_contacts", "appointments": "crm_clinic_appointments"}
GOLD_REFRESHES = ["gold_refresh_funnel", "gold_refresh_confirmation"]


def fetch(kind: str) -> list[dict]:
    """Page through the CRM's API. The token comes from .env, never from the code."""
    if os.environ.get("CRM_EXPORT_DIR"):      # the demo reads files, because there is no real CRM behind it
        lines = gzip.decompress((Path(os.environ["CRM_EXPORT_DIR"]) / f"{kind}.jsonl.gz").read_bytes())
        return [json.loads(line) for line in lines.decode("utf-8").splitlines()]
    url, out = f"https://api.example-crm.com/{kind}", []
    while url:
        r = requests.get(url, headers={"Authorization": f"Bearer {os.environ['CRM_TOKEN']}"}, timeout=60)
        r.raise_for_status()
        body = r.json()
        out += body["results"]
        url = body.get("next")
    return out


def load_bronze(cur, kind, rows) -> None:
    """Exactly what arrived. A record that changed is a new row; one seen before only gets its
    last_seen_at moved, so a value changed BACK to an earlier version still wins."""
    unique = list({json.dumps(r, sort_keys=True): r for r in rows}.values())   # the CRM repeats rows across pages
    execute_values(cur, """INSERT INTO bronze_raw (source, payload) VALUES %s
                           ON CONFLICT (source, payload_hash) DO UPDATE SET last_seen_at = now()""",
                   [(SOURCES[kind], Json(r)) for r in unique], page_size=2000)


def read_bronze(cur, kind) -> list[dict]:
    """The version of each record the source sent most recently."""
    cur.execute("""SELECT DISTINCT ON (payload->>'id') payload FROM bronze_raw
                   WHERE source = %s ORDER BY payload->>'id', last_seen_at DESC, id DESC""", (SOURCES[kind],))
    return [row[0] for row in cur.fetchall()]


def load_silver(cur, people, operations, touches) -> None:
    """One shape for every client, always with the client id."""
    execute_values(cur, """
        INSERT INTO silver_person (client_id, external_id, email, phone, channel, procedure, city, advisor,
                                   created_on, metadata)
        VALUES %s
        ON CONFLICT (client_id, external_id) DO UPDATE SET
            email = EXCLUDED.email, phone = EXCLUDED.phone, channel = EXCLUDED.channel,
            procedure = EXCLUDED.procedure, city = EXCLUDED.city, advisor = EXCLUDED.advisor,
            created_on = EXCLUDED.created_on, metadata = EXCLUDED.metadata""",
        [(CLIENT_ID, p["external_id"], p["email"], p["phone"], p["channel"], p["procedure"], p["city"],
          p["advisor"], p["created_on"], Json(p["metadata"])) for p in people], page_size=2000)
    execute_values(cur, """
        INSERT INTO silver_operation (client_id, external_id, person_external_id, kind, status, date,
                                      confirmed, value, metadata)
        VALUES %s
        ON CONFLICT (client_id, external_id) DO UPDATE SET
            person_external_id = EXCLUDED.person_external_id, kind = EXCLUDED.kind, status = EXCLUDED.status,
            date = EXCLUDED.date, confirmed = EXCLUDED.confirmed, value = EXCLUDED.value,
            metadata = EXCLUDED.metadata""",
        [(CLIENT_ID, o["external_id"], o["person"], o["kind"], o["status"], o["date"], o["confirmed"],
          o["value"], Json(o["metadata"])) for o in operations], page_size=2000)
    execute_values(cur, """INSERT INTO silver_engagement (client_id, person_external_id, date) VALUES %s
                           ON CONFLICT DO NOTHING""",
                   [(CLIENT_ID, pid, day) for pid, day in touches], page_size=5000)


def refresh_gold(conn) -> None:
    """Python only presses the button. The work is a SQL function in the database."""
    for function in GOLD_REFRESHES:
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT {function}(%s)", (CLIENT_ID,))
                print(f"{function}: {cur.fetchone()[0]:,} rows")
            conn.commit()
        except Exception as e:  # a failed refresh must not undo a good load
            conn.rollback()
            print(f"WARNING: {function} failed, gold stays at yesterday's numbers: {e}")


def main() -> None:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn.cursor() as cur:
        for kind in SOURCES:
            load_bronze(cur, kind, fetch(kind))
        people, operations, touches, report = t.clean_contacts(read_bronze(cur, "contacts"),
                                                               read_bronze(cur, "appointments"))
        load_silver(cur, people, operations, touches)
    conn.commit()
    print(t.as_text(report))
    refresh_gold(conn)
    conn.close()


if __name__ == "__main__":
    main()
