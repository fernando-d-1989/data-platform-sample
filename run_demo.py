"""The whole night in one command, on a throwaway database:

    pip install -r requirements-dev.txt
    python run_demo.py

The same scripts the VM runs, in the same order. At the end it reads the figures back
from gold and compares them with what the website's clinic screens print.
"""
import gzip
import os
import subprocess
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "ops"), str(ROOT / "pipeline")]
from compare_with_website import FIGURES, compare  # noqa: E402
from local_postgres import throwaway_postgres  # noqa: E402

EXPORT = ROOT / "data" / "crm_export"
CLIENT = "00000000-0000-0000-0000-000000000001"


def step(title: str, script: str, env: dict) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}", flush=True)
    code = subprocess.run([sys.executable, script], cwd=ROOT, env=env).returncode
    if code != 0:
        sys.exit(f"{script} stopped with code {code}")


def one(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def main() -> None:
    with throwaway_postgres() as dsn:
        env = dict(os.environ, DATABASE_URL=dsn, CRM_EXPORT_DIR=str(EXPORT), PYTHONIOENCODING="utf-8")
        step("LOAD: CRM export -> bronze -> silver -> gold", "pipeline/load_crm.py", env)
        step("DATA CHECK: known answers about a closed period, no AI", "agent/baseline.py", env)
        step("MODEL: is it reading the future? Then the honest test, then today's call list",
             "ml/train_lead_score.py", env)

        conn = psycopg2.connect(dsn)
        with conn.cursor() as cur:
            print(f"\n{'=' * 78}\nWHAT EACH LAYER HOLDS\n{'=' * 78}")
            arrived = sum(len(gzip.decompress((EXPORT / f).read_bytes()).splitlines())
                          for f in ("contacts.jsonl.gz", "appointments.jsonl.gz"))
            rows = [("rows in the two CRM exports", arrived)]
            for name, table in [("bronze: raw rows kept", "bronze_raw"), ("silver: people", "silver_person"),
                                ("silver: assessments and surgeries", "silver_operation"),
                                ("silver: activity dates", "silver_engagement"),
                                ("gold: funnel rows for two screens", "gold_funnel_month"),
                                ("gold: confirmation rows", "gold_confirmation_month"),
                                ("gold: today's call list", "gold_lead_score")]:
                rows.append((name, one(cur, f"SELECT count(*) FROM {table}")))
            for name, n in rows:
                print(f"{name:<40}{n:>8,}")

            print(f"\n{'=' * 78}\nGOLD AGAINST THE WEBSITE'S SCREENS (bizi.solutions/en/demo/clinica)\n{'=' * 78}")
            figures = compare(cur, CLIENT)
            o = FIGURES["overview"]
            print(f"Overview, {FIGURES['after']['from']} to {FIGURES['after']['to']} vs a year earlier:")
            for m in ["leads", "assessments_attended", "no_shows", "surgeries", "revenue"]:
                gold = next(g for n, _, g in figures if n == f"overview after · {m}")
                print(f"  {m:<22} website {o['after'][m]:>12,.0f}   gold {gold:>12,.0f}   (a year earlier {o['before'][m]:,.0f})")
            wrong = [(n, w, g) for n, w, g in figures if round(w, 2) != round(g, 2)]
            print(f"\n{len(figures) - len(wrong)} of {len(figures)} figures match the website exactly")
            for n, w, g in wrong[:10]:
                print(f"  MISMATCH {n}: website {w}, gold {g}")
        conn.close()
        if wrong:
            sys.exit(1)


if __name__ == "__main__":
    main()
