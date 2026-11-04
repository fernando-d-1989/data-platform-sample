# Data platform sample

The back end of an aesthetic-clinic dashboard: a messy CRM export goes in, the screens'
figures come out, along with a model that tells the team who to call first.

**Open the dashboard first:** [bizi.solutions/en/demo/clinica](https://bizi.solutions/en/demo/clinica).
It's a demo on my website, built from the same patterns as my client dashboards. This
repo is what sits behind a dashboard like that, run on the same clinic: the same
33,973 invented patients and 6,537 appointments. After cleaning, the figures in gold
match the ones that page prints, **198 of 198**.

The walkthrough is on Notion, in plain words: [start here](https://app.notion.com/p/Sustain-Media-40ebc3991596807ea650c210c76cd65e) ·
[1 · How I build a client project](https://app.notion.com/p/40ebc399159681cf9a30efff6d3015d3) ·
[2 · Keeping AI-built apps safe in production](https://app.notion.com/p/40ebc399159681659dbee2119b795de6)

```
CRM export -> bronze (exactly what arrived) -> silver (clean, one shape) -> gold (ready for screens)
                                                     |                         |
                                                 the model -----------> today's call list
                                                                              |
                                                  the dashboard, its chat, the AI report
```

## See it run

One command builds a throwaway database, runs the whole night (about 25 seconds), and
deletes the database.

```
pip install -r requirements-dev.txt
python run_demo.py
```

| Step | What happens |
|---|---|
| The export | 41,170 rows in two files: contacts and appointments, the way a CRM sends them |
| Bronze | 40,820 rows. The CRM sent 350 rows twice, and bronze keeps one copy |
| Cleaning | 60 test records left out, 250 people entered twice merged, 25,595 cities and 24,887 channels spelled one way, 490 rows kept but marked for review |
| Silver | 33,973 people, 6,537 assessments and surgeries, 91,313 activity dates |
| Gold | 15,160 rows feed the Overview and Conversion screens, 60 feed Appointment confirmation, and 14,267 make today's call list |
| Data check | April to September 2025 still gives 301 surgeries and 63.17% attendance |
| Model | Finds a field that already knows the answer and drops it, then passes the same test as the website's screen |
| Against the website | 198 of 198 figures match: the Overview, each channel, procedure and city, and confirmation |

The model's test, on 30 June 2026, uses the same 13,417 people and 159 surgeries as the
website's Path to surgery screen:

| Calling 600 people | Surgeries found by 30 September |
|---|---|
| Whoever moved most recently, which is what a receptionist does today | 30 |
| This repo's trained model | 121 (4.0×) |
| The website's screen, with fixed weights | 115 (3.7×) |

Both show who was going to have surgery. Neither shows that calling them made it happen.

## Where the data comes from

`data/website_clinic.json.gz` is the clinic behind the website, exported once from the
website's own generator. Every patient, figure and story in it is invented.
`data/make_crm_export.py` turns it into what a CRM really sends, in `data/crm_export/`.
Each file has a `_first_100.jsonl` you can read on GitHub without unzipping anything.
`data/website_figures.json` holds what the website's screens print, and gold has to
reproduce it.

The website's stories are planted in that data, so they show up in gold:

- **From May 2026 every assessment is confirmed by WhatsApp the day before.** Attendance goes from 63% to 78%.
- **From March 2026 a new liposculpture technique arrives with Instagram videos.** Liposculpture leads and surgeries grow.
- **From April 2026 a cheap Facebook campaign starts.** It brings many more leads, but few of them book.

## The mess, on purpose

Each problem comes from real client data. Each one has a cleaning rule, a test, and a
count in the nightly report:

- **The CRM repeats rows across pages.** Bronze keeps one copy. A record that changed is a new row, so the history stays.
- **One person entered twice under two ids,** with some visits logged on the second record. Silver merges them by email and moves the visits.
- **"Completed" means two different things.** For an assessment it means the person came; for a surgery it means the surgery was done. The status is read together with the type.
- **The same city or channel spelled five ways:** "Chicgo", "CHICAGO, IL", "fb", "FB Lead Form" and so on.
- **Dates in four formats, amounts like `USD 18,500`.**
- **A field nobody can read.** It becomes empty and gets a review mark. Nothing is guessed.
- **A field that knows the future.** The CRM opens a medical record when a patient has surgery, and the export is taken today. On its own, that field predicts surgery perfectly. The model's first step catches it and leaves it out.

## Where to look

| Folder | What it shows |
|---|---|
| `data/` | The clinic, the script that makes it messy, the export, and the figures to match |
| `pipeline/` | The nightly load, the cleaning rules with their tests, and the check against the website |
| `sql/` | One file per change to the database, applied in order: tables, access rules, one file per gold table, the AI's user, the schedule |
| `ml/` | Path to surgery: the leak check, the honest test, today's list |
| `agent/` | The research agent's checks, and the nightly data check that uses no AI |
| `chat/` | Tool definitions, the number checker, a sample of the exam |
| `dashboard/` | The single database client: public key only |
| `ops/` | The VM that downloads the code, runs the night and shuts down, and a local stand-in for Supabase |
| `docs/` | How decisions are recorded, and when we decide without the architect |

## Run the tests

```
python pipeline/test_transform.py                 # 12 cleaning rules
python pipeline/test_database.py                  # 29 checks on a throwaway database
python agent/guardrails.py                        # 4 agent checks
node --experimental-strip-types chat/number_check.test.ts   # 3 number checks
```

The database test logs in as each kind of user. A client sees only their own rows, an
account with no client sees nothing, nobody on the dashboard can read raw data, and the
AI's user cannot write. Building it exposed three bugs in this repo, and the test now
fails if any of them comes back:
- a duplicated load,
- a date that didn't update,
- a value changed back to an earlier version that was ignored.

## What this sample leaves out

- The real CRM download. The demo reads the files in `data/crm_export/` instead.
- Supabase's own login. A small stand-in in `ops/` plays that part on plain Postgres.
- The AI-written report and the chat's calls to a model. Their checks are here; the calls are not.
- The scheduled job in `sql/007`. It is skipped locally, because plain Postgres has no scheduler.

## How it was built

Designed by me, with the code written and reviewed alongside Claude Code.
