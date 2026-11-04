"""Path to surgery: of the people still on the way, who should the team call first?

Same question, same candidates and same test as the website's screen: on a given day,
people who came in during the last year and haven't had surgery; did they have surgery
in the following three months?

STEP 0 comes first because it can invalidate everything after it: is a field reading
the future? The CRM export was taken today, so a field filled in AFTER the outcome
already contains the answer.
STEP 1 goes back to 30 June 2026, orders the list as the model would have, and counts
who had surgery by 30 September. It compares with what a receptionist does without a
model: call whoever moved most recently. (Against "the newest lead" it looks far
better, because new leads haven't even booked yet. That comparison is a straw man.)
STEP 2 orders today's list and promotes it to gold.

The model only sees what the clinic knew on that day, and nothing after it.
"""
import json
import os
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from sklearn.compose import make_column_transformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

CLIENT_ID = "00000000-0000-0000-0000-000000000001"   # invented
MODEL_VERSION = "path_to_surgery_v1"
HORIZON = timedelta(days=92)
LOOKBACK = timedelta(days=365)
TEST_DAY = pd.Timestamp("2026-06-30")
CALLS = 600
TRAIN_DAYS = pd.date_range("2025-01-31", TEST_DAY - HORIZON, freq="ME")    # their outcomes end before the test day
CATEGORIES = ["channel", "procedure"]
NUMBERS = ["came", "came_recently", "booked", "missed", "touches", "days_still"]
SUSPECT = ["has_record_number"]          # fields from the CRM that STEP 0 must clear first
SUSPICIOUS_AUC = 0.90                    # no single honest field predicts surgery this well
WEBSITE = json.loads((Path(__file__).resolve().parent.parent / "data" / "website_figures.json").read_text(encoding="utf-8"))


def read(conn) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    q = lambda sql: pd.read_sql(sql, conn, params={"c": CLIENT_ID})
    people = q("""SELECT external_id AS person, channel, coalesce(procedure, 'unknown') AS procedure, created_on,
                         (metadata->>'patient_record_number' IS NOT NULL)::int AS has_record_number
                  FROM silver_person WHERE client_id = %(c)s AND created_on IS NOT NULL""")
    ops = q("SELECT person_external_id AS person, kind, status, date FROM silver_operation WHERE client_id = %(c)s")
    touches = q("SELECT person_external_id AS person, date FROM silver_engagement WHERE client_id = %(c)s")
    for frame in (people, ops, touches):
        for col in ("created_on", "date"):
            if col in frame:
                frame[col] = pd.to_datetime(frame[col])
    return people, ops, touches


def snapshot(day, people, ops, touches, today=False) -> pd.DataFrame:
    """Every candidate on `day`, with what the clinic knew then, and what happened next."""
    done = ops[(ops.kind == "surgery") & (ops.status == "done")]
    out = set(done[done.date <= day].person)
    if today:   # today a scheduled surgery is known, so that person is no longer on the way
        out |= set(ops[(ops.kind == "surgery") & (ops.status == "scheduled")].person)
    s = people[(people.created_on > day - LOOKBACK) & (people.created_on <= day) & ~people.person.isin(out)].copy()

    assessments = ops[ops.kind == "assessment"]
    past = assessments[assessments.date <= day]
    last_came = past[past.status == "attended"].groupby("person").date.max()
    days_since_came = (day - s.person.map(last_came)).dt.days
    s["came"] = days_since_came.notna().astype(int)
    s["came_recently"] = (days_since_came <= 120).astype(int)
    s["booked"] = s.person.isin(assessments[(assessments.date > day) & (assessments.date <= day + timedelta(days=10))].person).astype(int)
    s["missed"] = s.person.isin(past[past.status == "no_show"].person).astype(int)
    seen = touches[touches.date <= day]
    s["touches"] = s.person.map(seen.groupby("person").size()).fillna(0).clip(upper=6)
    last_move = pd.concat([seen.groupby("person").date.max(), past.groupby("person").date.max()]).groupby(level=0).max()
    last = pd.concat([s.created_on, s.person.map(last_move)], axis=1).max(axis=1)
    s["days_still"] = (day - last).dt.days.clip(upper=240)
    s["surgery_next"] = s.person.isin(done[(done.date > day) & (done.date <= day + HORIZON)].person).astype(int)
    s["day"] = day
    return s


def model(numbers):
    return make_pipeline(
        make_column_transformer((OneHotEncoder(handle_unknown="ignore"), CATEGORIES), (StandardScaler(), numbers)),
        LogisticRegression(max_iter=2000))


def main() -> None:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    people, ops, touches = read(conn)
    train = pd.concat([snapshot(d, people, ops, touches) for d in TRAIN_DAYS], ignore_index=True)
    print(f"{len(people):,} people · {len(TRAIN_DAYS)} past days to learn from · {len(train):,} candidate rows · "
          f"{train.surgery_next.mean():.1%} had surgery within three months")

    # STEP 0
    print("\nSTEP 0 · Is any field reading the future?")
    numbers = list(NUMBERS)
    for field in SUSPECT + NUMBERS:
        auc = roc_auc_score(train.surgery_next, train[field])
        if auc >= SUSPICIOUS_AUC:
            print(f"  {field}: predicts surgery alone with AUC {auc:.2f}. It is filled in when the patient is "
                  "operated on, so it already knows the answer. Left out.")
        elif field in SUSPECT:
            numbers.append(field)
    print(f"  the model uses: {', '.join(CATEGORIES + numbers)}")

    # STEP 1
    fitted = model(numbers).fit(train[CATEGORIES + numbers], train.surgery_next)
    test = snapshot(TEST_DAY, people, ops, touches)
    test["score"] = fitted.predict_proba(test[CATEGORIES + numbers])[:, 1]
    by_model = test.sort_values(["score", "created_on"], ascending=[False, False]).head(CALLS)
    by_recent = test.sort_values(["days_still", "created_on"], ascending=[True, False]).head(CALLS)
    found, recent = by_model.surgery_next.sum(), by_recent.surgery_next.sum()
    print(f"\nSTEP 1 · Back to {TEST_DAY:%d %b %Y}: {len(test):,} people on the way, "
          f"{test.surgery_next.sum()} had surgery by {TEST_DAY + HORIZON:%d %b}")
    print(f"  calling {CALLS} in the model's order finds {found} of them")
    print(f"  calling the {CALLS} who moved most recently finds {recent}")
    print(f"  {found / recent:.1f}x more surgeries for the same calls · AUC {roc_auc_score(test.surgery_next, test.score):.2f}")
    web = WEBSITE["path_to_surgery_backtest"]
    print(f"  the website's screen, same day and candidates ({web['candidates']:,}, {web['surgeries_among_candidates']} "
          f"surgeries), uses fixed weights: {web['model_finds']} against {web['most_recent_finds']}")
    print("  It shows who was going to have surgery. It does not show that calling them made it happen.")

    # STEP 2
    final = model(numbers).fit(pd.concat([train, test])[CATEGORIES + numbers],
                                pd.concat([train, test]).surgery_next)
    today = snapshot(people.created_on.max(), people, ops, touches, today=True)
    today["score"] = final.predict_proba(today[CATEGORIES + numbers])[:, 1]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM silver_model_score_raw WHERE client_id = %s", (CLIENT_ID,))
        execute_values(cur, """INSERT INTO silver_model_score_raw (client_id, person_external_id, model_version, score)
                               VALUES %s""",
                       [(CLIENT_ID, p, MODEL_VERSION, float(np.round(s, 7))) for p, s in zip(today.person, today.score)],
                       page_size=5000)
        cur.execute("SELECT gold_promote_lead_score(%s)", (CLIENT_ID,))
        print(f"\nSTEP 2 · Today's list: {cur.fetchone()[0]:,} people ordered and promoted to gold")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
