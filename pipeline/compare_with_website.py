"""After the load: read the figures back from gold and compare them, one by one, with what
the website's screens print (data/website_figures.json).

A load can finish without errors and still be wrong. This is the proof that cleaning the
messy export got back exactly the clinic the website shows.
"""
import json
from pathlib import Path

FIGURES = json.loads((Path(__file__).resolve().parent.parent / "data" / "website_figures.json").read_text(encoding="utf-8"))
MEASURES = ["leads", "assessments_attended", "no_shows", "surgeries", "revenue"]


def funnel(cur, client_id, period, where="", args=()):
    cur.execute(f"""SELECT sum(leads), sum(assessments_attended), sum(no_shows), sum(surgeries), sum(revenue)
                    FROM gold_funnel_month
                    WHERE client_id = %s AND to_char(month, 'YYYY-MM') BETWEEN %s AND %s {where}""",
                (client_id, period["from"], period["to"], *args))
    return dict(zip(MEASURES, (float(v or 0) for v in cur.fetchone())))


def confirmation(cur, client_id, period):
    cur.execute("""SELECT confirmed, sum(due), sum(attended) FROM gold_confirmation_month
                   WHERE client_id = %s AND to_char(month, 'YYYY-MM') BETWEEN %s AND %s GROUP BY 1""",
                (client_id, period["from"], period["to"]))
    rows = {c: {"due": int(d), "attended": int(a)} for c, d, a in cur.fetchall()}
    return {"confirmed": rows.get(True, {"due": 0, "attended": 0}), "unconfirmed": rows.get(False, {"due": 0, "attended": 0})}


def compare(cur, client_id) -> list[tuple[str, float, float]]:
    """Every figure as (name, website, gold). Empty mismatches = the screens would print the same."""
    out = []
    for when in ("before", "after"):
        got = funnel(cur, client_id, FIGURES[when])
        out += [(f"overview {when} · {m}", FIGURES["overview"][when][m], got[m]) for m in MEASURES]
        for dim, column in [("by_channel", "channel"), ("by_procedure", "procedure"), ("by_city", "city")]:
            for value, website in FIGURES[dim].items():
                got = funnel(cur, client_id, FIGURES[when], f"AND {column} = %s", (value,))
                out += [(f"{dim} {value} {when} · {m}", website[when][m], got[m]) for m in MEASURES]
        got = confirmation(cur, client_id, FIGURES[when])
        for group in ("confirmed", "unconfirmed"):
            out += [(f"confirmation {when} · {group} {k}", FIGURES["confirmation"][when][group][k], got[group][k])
                    for k in ("due", "attended")]
    return out
