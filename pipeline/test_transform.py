"""The cleaning rules, one messy value at a time. No database needed."""
from datetime import date

import transform as t


def contact(**fields):
    return {"id": "1", "email": None, "phone": None, "source": "Instagram", "procedure_of_interest": "Rhinoplasty",
            "city": "Dallas", "age": 30, "owner": "adv-01", "created": "2026-01-10", "activity_dates": [],
            "patient_record_number": None, **fields}


def appointment(**fields):
    return {"id": "5001", "contact_id": "1", "type": "Assessment", "status": "Attended", "date": "2026-01-20",
            "confirmed_day_before": None, "amount": "", **fields}


def test_emails():
    assert t.clean_email(" Ana@Example.COM") == "ana@example.com"
    assert t.clean_email("patient@example") is None


def test_phones():
    for messy in ["+1 312 555 0142", "(312) 555-0142", "312.555.0142", "13125550142"]:
        assert t.clean_phone(messy) == "3125550142"
    assert t.clean_phone("312.555") is None


def test_channels_and_cities():
    assert t.clean_channel("REFERRAL ") == "Referral"
    assert t.clean_channel("FB Lead Form") == "Facebook"
    assert t.clean_channel("radio?") is None
    assert t.clean_city("CHICAGO, IL") == "Chicago"
    assert t.clean_city("Chicgo") == "Chicago"
    assert t.clean_city("--") == "Other cities"


def test_dates():
    assert t.parse_date("04/03/2026") == date(2026, 4, 3)      # month first in this CRM
    assert t.parse_date("Apr 03, 2026") == date(2026, 4, 3)
    assert t.parse_date("2026-04-03T10:22:00Z") == date(2026, 4, 3)
    assert t.parse_date("TBD") is None


def test_money():
    for messy in ["$18,500.00", "USD 18,500", "18500", "18.500,00"]:
        assert t.parse_money(messy) == 18500.0
    assert t.parse_money("n/a") is None


def test_the_same_word_means_different_things_by_type():
    _, ops, _, _ = t.clean_contacts([contact()], [
        appointment(id="1", type="Consultation", status="completed"),
        appointment(id="2", type="Surgery", status="completed", amount="$9,000"),
        appointment(id="3", type="Surgery", status="booked", amount="$9,000"),
    ])
    assert [(o["kind"], o["status"]) for o in ops] == [("assessment", "attended"), ("surgery", "done"), ("surgery", "scheduled")]


def test_test_records_stay_out():
    people, _, _, report = t.clean_contacts([contact(email="test1@example.com"), contact(id="2")], [])
    assert [p["external_id"] for p in people] == ["2"]
    assert report["test records left out"] == 1


def test_same_email_is_one_person_and_keeps_every_visit():
    people, ops, touches, report = t.clean_contacts(
        [contact(id="5", email="A@example.com", activity_dates=["2026-01-11"]),
         contact(id="9", email="a@example.com", activity_dates=["2026-01-12"])],
        [appointment(id="1", contact_id="5"), appointment(id="2", contact_id="9", type="Surgery", status="Done")])
    assert [p["external_id"] for p in people] == ["5"]
    assert {o["person"] for o in ops} == {"5"} and len(ops) == 2
    assert touches == [("5", date(2026, 1, 11)), ("5", date(2026, 1, 12))]
    assert report["duplicate people merged"] == 1 and report["appointments moved to the kept person"] == 1


def test_nothing_invented_when_a_value_is_doubtful():
    people, ops, _, _ = t.clean_contacts(
        [contact(source="radio?", phone="312.555")],
        [appointment(type="Surgery", status="Done", amount="1850000000")])
    assert people[0]["channel"] == "unknown"
    assert [m["reason"] for m in people[0]["metadata"]["review"]] == ["phone not valid", "channel not recognised"]
    assert ops[0]["value"] is None and ops[0]["metadata"]["review"][0]["reason"] == "amount out of range"


def test_unreadable_appointment_is_left_out_and_counted():
    _, ops, _, report = t.clean_contacts([contact()], [appointment(date="TBD"), appointment(id="2", contact_id="404")])
    assert ops == []
    assert report["appointments unreadable, left out"] == 1
    assert report["appointments of unknown contacts left out"] == 1


def test_appointment_before_the_lead_is_kept_and_marked():
    _, ops, _, _ = t.clean_contacts([contact()], [appointment(date="2026-01-05")])
    assert ops[0]["metadata"]["review"][0]["reason"] == "appointment before lead date"


def test_confirmation():
    assert [t.parse_yes_no(v) for v in ["Y", "TRUE", "no", "0", None]] == [True, True, False, False, None]


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_") and callable(f)]
    for test in tests:
        test()
    print(f"{len(tests)} of {len(tests)} passed")
