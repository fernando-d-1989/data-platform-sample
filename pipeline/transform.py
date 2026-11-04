"""Cleaning rules: raw CRM contacts and appointments -> silver rows. No database here, so it
can be tested alone.

Three habits run through every rule:
- Nothing is invented. A value we can't read becomes empty, never a guess.
- A doubtful row stays in, with a review mark saying why, so a person can fix it.
- Every rule counts what it did, so the report shows how dirty the source really was.
"""
import re
from collections import Counter
from datetime import datetime

CHANNELS = {
    "instagram": "Instagram", "ig": "Instagram", "instagram ads": "Instagram",
    "google": "Google", "google ads": "Google", "googleads": "Google", "ppc": "Google",
    "facebook": "Facebook", "fb": "Facebook", "fb lead form": "Facebook",
    "whatsapp": "WhatsApp", "wa": "WhatsApp",
    "referral": "Referral", "referred by patient": "Referral",
    "website": "Website", "web form": "Website", "site": "Website",
}
CITIES = {
    "chicago": "Chicago", "chicgo": "Chicago", "houston": "Houston", "dallas": "Dallas", "miami": "Miami",
    "other": "Other cities", "other city": "Other cities", "--": "Other cities",
    "international": "Abroad", "abroad": "Abroad", "outside us": "Abroad",
}
KINDS = {"assessment": "assessment", "consultation": "assessment", "consult": "assessment",
         "surgery": "surgery", "procedure": "surgery"}
# The same word means different things by type: "completed" is an attended assessment, or a done surgery.
STATUSES = {
    "assessment": {"attended": "attended", "showed": "attended", "completed": "attended",
                   "no show": "no_show", "no-show": "no_show", "noshow": "no_show", "missed": "no_show",
                   "booked": "booked", "scheduled": "booked", "pending": "booked"},
    "surgery": {"done": "done", "completed": "done", "performed": "done",
                "scheduled": "scheduled", "booked": "scheduled", "upcoming": "scheduled"},
}
YES = {"yes", "y", "true", "1"}
NO = {"no", "n", "false", "0"}
DATE_FORMATS = ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y"]   # slashes are month first in this CRM
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")
MAX_PLAUSIBLE_AMOUNT = 100_000


def clean_email(value):
    email = (value or "").strip().lower()
    return email if EMAIL.match(email) else None


def clean_phone(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def clean_channel(value):
    return CHANNELS.get((value or "").strip().lower())


def clean_city(value):
    text = (value or "").strip().lower()
    return CITIES.get(text) or CITIES.get(re.split(r"[,\s]", text)[0])


def parse_date(value):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime((value or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_money(value):
    """'$18,500.00', 'USD 18,500', '18500'. A comma followed by two digits at the end is a decimal comma."""
    text = re.sub(r"[^\d.,-]", "", value or "")
    if not re.search(r"\d", text):
        return None
    if re.search(r",\d{2}$", text):
        text = text.replace(".", "").replace(",", ".")
    return float(text.replace(",", ""))


def parse_yes_no(value):
    text = (value or "").strip().lower()
    return True if text in YES else False if text in NO else None


def is_test_record(raw):
    return (raw.get("email") or "").lower().startswith("test") or "TEST" in (raw.get("notes") or "")


def review(reason, detail):
    """Fixed wording for the reason, because people filter by it. The raw value goes in detail."""
    return {"status": "pending", "reason": reason, "detail": detail, "marked_by": "loader"}


def clean_contacts(raw_contacts, raw_appointments):
    """Everything the CRM sent in; (people, operations, touches, report) out."""
    report = Counter(contacts_in=len(raw_contacts), appointments_in=len(raw_appointments))
    people, keeper, owner_of_email = {}, {}, {}

    for raw in sorted(raw_contacts, key=lambda r: int(r["id"])):
        if is_test_record(raw):
            report["test records left out"] += 1
            continue
        email = clean_email(raw.get("email"))
        # The same email under a second id is the same person: the lowest id keeps the record.
        if email and email in owner_of_email:
            keeper[raw["id"]] = owner_of_email[email]
            report["duplicate people merged"] += 1
            continue
        if email:
            owner_of_email[email] = raw["id"]
        keeper[raw["id"]] = raw["id"]
        people[raw["id"]] = person(raw, email, report)

    operations = {}
    for raw in raw_appointments:
        op = operation(raw, keeper, report)
        if op:
            operations[op["external_id"]] = op

    touches = sorted({(keeper[r["id"]], d) for r in raw_contacts if r["id"] in keeper
                      for d in map(parse_date, r.get("activity_dates") or []) if d})
    for op in operations.values():
        created = people[op["person"]]["created_on"]
        if op["date"] and created and op["date"] < created:
            op["metadata"].setdefault("review", []).append(review("appointment before lead date", str(op["date"])))

    report["people out"] = len(people)
    report["operations out"] = len(operations)
    report["activity dates out"] = len(touches)
    report["rows marked for review"] = sum("review" in r["metadata"] for r in [*people.values(), *operations.values()])
    return list(people.values()), list(operations.values()), touches, report


def person(raw, email, report):
    marks = []
    phone, channel, city = clean_phone(raw.get("phone")), clean_channel(raw.get("source")), clean_city(raw.get("city"))
    if raw.get("email") and raw["email"] != email:
        report["emails normalised"] += 1
    if raw.get("email") and not email:
        marks.append(review("email not valid", raw["email"]))
    if raw.get("phone") and not phone:
        marks.append(review("phone not valid", raw["phone"]))
    if channel and raw["source"] != channel:
        report["channels mapped to one name"] += 1
    if (raw.get("source") or "").strip() and not channel:
        marks.append(review("channel not recognised", raw["source"]))
    if raw.get("city") and not city:
        marks.append(review("city not recognised", raw["city"]))
    elif city and raw["city"] != city:
        report["cities mapped to one name"] += 1
    metadata = {"age": raw.get("age"), "patient_record_number": raw.get("patient_record_number")}
    return {
        "external_id": raw["id"], "email": email, "phone": phone, "channel": channel or "unknown",
        "procedure": raw.get("procedure_of_interest"), "city": city, "advisor": raw.get("owner"),
        "created_on": parse_date(raw.get("created")),
        "metadata": {k: v for k, v in metadata.items() if v is not None} | ({"review": marks} if marks else {}),
    }


def operation(raw, keeper, report):
    person_id = keeper.get(raw.get("contact_id"))
    if not person_id:
        report["appointments of unknown contacts left out"] += 1
        return None
    if person_id != raw["contact_id"]:
        report["appointments moved to the kept person"] += 1
    kind = KINDS.get((raw.get("type") or "").strip().lower())
    status = STATUSES.get(kind, {}).get((raw.get("status") or "").strip().lower())
    day = parse_date(raw.get("date"))
    if not (kind and status and day):
        report["appointments unreadable, left out"] += 1
        return None
    report[f"{kind} {status}"] += 1
    marks, amount = [], None
    if kind == "surgery":
        amount = parse_money(raw.get("amount"))
        if amount is None:
            marks.append(review("amount missing", raw.get("amount")))
        elif amount > MAX_PLAUSIBLE_AMOUNT:
            marks.append(review("amount out of range", raw["amount"]))
            amount = None
    return {"external_id": raw["id"], "person": person_id, "kind": kind, "status": status, "date": day,
            "confirmed": parse_yes_no(raw.get("confirmed_day_before")), "value": amount,
            "metadata": {"review": marks} if marks else {}}


def as_text(report):
    return "\n".join(f"{name:<44}{count:>8,}" for name, count in report.items())
