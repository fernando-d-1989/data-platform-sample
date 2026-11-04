"""Turns the website's clinic into what a CRM really sends: data/crm_export/.

The input, website_clinic.json.gz, is the clinic behind bizi.solutions/en/demo/clinica,
exported from the website's own generator. Every person and figure is invented.

Most of the mess added here can be undone by the cleaning rules, on purpose: after
cleaning, gold has to print exactly what the website's screens print
(data/website_figures.json). The mess that can't be undone is kept to fields no figure
uses, and those rows get a review mark instead.

The seed is fixed, so every run writes the same files.
"""
import gzip
import json
import random
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "crm_export"
rng = random.Random(20261104)

CHANNEL_SPELLINGS = {
    "Instagram": ["Instagram", "instagram", "IG", "Instagram Ads"],
    "Google": ["Google", "google ads", "GoogleAds", "PPC"],
    "Facebook": ["Facebook", "fb", "FB Lead Form", "facebook "],
    "WhatsApp": ["WhatsApp", "whatsapp", "WA"],
    "Referral": ["Referral", "referred by patient", "REFERRAL "],
    "Website": ["Website", "web form", "site"],
}
CITY_SPELLINGS = {
    "Chicago": ["Chicago", "chicago", "CHICAGO, IL", "Chicgo"],
    "Houston": ["Houston", "houston tx", "HOUSTON"],
    "Dallas": ["Dallas", "dallas", "Dallas, TX"],
    "Miami": ["Miami", "MIAMI FL", "miami"],
    "Other cities": ["Other", "other city", "--"],
    "Abroad": ["International", "abroad", "Outside US"],
}
KIND_SPELLINGS = {"assessment": ["Assessment", "assessment", "Consultation", "consult "],
                  "surgery": ["Surgery", "surgery", "Procedure", "SURGERY"]}
STATUS_SPELLINGS = {
    "attended": ["Attended", "attended", "Showed", "completed"],
    "no_show": ["No show", "no-show", "NoShow", "missed"],
    "booked": ["Booked", "scheduled", "Pending"],
    "done": ["Done", "Completed", "performed"],
    "scheduled": ["Scheduled", "booked", "Upcoming"],
}
YES, NO = ["yes", "Yes", "Y", "TRUE", "1"], ["no", "No", "N", "FALSE", "0"]


def messy_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    moment = datetime(d.year, d.month, d.day, rng.randint(8, 19), rng.randint(0, 59))
    fmt = rng.choices(["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y"], [55, 15, 20, 10])[0]
    return moment.strftime(fmt)


def messy_money(value: float) -> str:
    return rng.choice([f"${value:,.2f}", f"{value:.0f}", f"USD {value:,.0f}", f"{value:,.2f}"])


def crm_id(website_id: str) -> str:
    return str(100000 + int(website_id[1:]))


def contact(p: dict, n: int, record_holders: set) -> dict:
    roll = rng.random()
    email = None if roll < .05 else f"patient{n}@example.com"
    if email and roll < .17:
        email = rng.choice([email.upper(), f" {email}", email.title()])
    if roll > .995:
        email = f"patient{n}@example"                       # can't be fixed: review mark
    area = {"Chicago": 312, "Houston": 713, "Dallas": 214, "Miami": 305}.get(p["city"], 646)
    phone = None if rng.random() < .12 else rng.choice(
        [f"+1 {area} 555 {n % 10000:04d}", f"({area}) 555-{n % 10000:04d}", f"{area}555{n % 10000:04d}",
         f"{area}.555.{n % 10000:04d}"])
    if phone and rng.random() < .01:
        phone = phone[:8]                                   # cut short: review mark
    return {
        "id": crm_id(p["id"]), "email": email, "phone": phone,
        "source": rng.choice(CHANNEL_SPELLINGS[p["channel"]]),
        "procedure_of_interest": p["procedure"],
        "city": rng.choice(CITY_SPELLINGS[p["city"]]),
        "age": p["age"] if rng.random() > .03 else None,
        "owner": p["advisor"],
        "created": messy_date(p["created_on"]),
        "activity_dates": [messy_date(t) for t in p["touches"]],
        # The CRM opens a medical record when a patient is operated on. The export is taken
        # today, so this field already knows the future. The model's first step must catch it.
        "patient_record_number": f"MR-{40000 + n}" if p["id"] in record_holders else None,
    }


def appointment(a: dict) -> dict:
    return {
        "id": str(5000000 + int(a["id"][1:])), "contact_id": crm_id(a["person"]),
        "type": rng.choice(KIND_SPELLINGS[a["kind"]]),
        "status": rng.choice(STATUS_SPELLINGS[a["status"]]),
        "date": messy_date(a["date"]),
        "confirmed_day_before": None if a["confirmed"] is None else rng.choice(YES if a["confirmed"] else NO),
        "amount": messy_money(a["value"]) if a["kind"] == "surgery" else rng.choice(["0", "", None, "$0.00"]),
    }


def main() -> None:
    clinic = json.loads(gzip.decompress((HERE / "website_clinic.json.gz").read_bytes()))
    record_holders = {a["person"] for a in clinic["appointments"] if a["kind"] == "surgery" and a["status"] == "done"}
    contacts = [contact(p, n, record_holders) for n, p in enumerate(clinic["people"], 1)]
    appointments = [appointment(a) for a in clinic["appointments"]]

    # The same person entered again under a new id, and some of their visits logged there.
    twins = []
    for original in rng.sample([c for c in contacts if c["email"] and "@example.com" in c["email"].lower()], 250):
        twin = dict(original, id=str(900000 + len(twins)), email=original["email"].strip().upper(),
                    activity_dates=[], patient_record_number=None)
        twins.append(twin)
        for a in appointments:
            if a["contact_id"] == original["id"] and rng.random() < .4:
                a["contact_id"] = twin["id"]
    contacts += twins

    # Staff testing the CRM.
    contacts += [{"id": str(990000 + i), "email": f"test{i}@example.com", "phone": None, "source": "Website",
                  "procedure_of_interest": "Rhinoplasty", "city": "Chicago", "age": None, "owner": "adv-01",
                  "created": "2025-06-02", "activity_dates": [], "patient_record_number": None, "notes": "TEST - ignore"}
                 for i in range(60)]

    # The CRM's paging sends some rows twice.
    contacts += rng.sample(contacts, 200)
    appointments += rng.sample(appointments, 150)
    rng.shuffle(contacts)
    rng.shuffle(appointments)

    OUT.mkdir(exist_ok=True)
    for name, rows in [("contacts", contacts), ("appointments", appointments)]:
        lines = "".join(json.dumps(r) + "\n" for r in rows)
        (OUT / f"{name}.jsonl.gz").write_bytes(gzip.compress(lines.encode("utf-8"), mtime=0))
        (OUT / f"{name}_first_100.jsonl").write_text("".join(lines.splitlines(True)[:100]), encoding="utf-8")
        print(f"{len(rows):,} {name}")


if __name__ == "__main__":
    main()
