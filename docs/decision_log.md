# How decisions get made and remembered

I'm not an engineer, so early on every database question had to go to an external
data architect. That cost days. So I built a decision log in Notion, one row per
topic: what we found, what we propose, what he answered, and what is actually in
the database today.

**Why it pays off.** A blocker solved once becomes a precedent for the next project.
In July and August, 45% of his answers leaned on an earlier decision. By September
and October it was over 80%.

**Then I measured it (22-10-2026).** We read the 108 rows he had answered:

| Result | Rows |
|---|---|
| Approved as proposed | 71 |
| Approved with a small condition | 13 |
| He preferred another design | 8 |
| He caught a real defect | 7 |
| No recommendation to compare | 9 |

We agreed in 84 of 99 comparable rows (85%).

**The rule that came out of it.** Each new decision gets two scores:

- **Confidence:** how sure are we it works, backed by earlier tests and decisions?
- **Blast radius:** if it fails halfway, how much damage does it do?

If confidence is 75 or more, blast radius is 30 or less, and no hard rule applies,
we decide ourselves and record it. Hard rules always go to the architect: permissions,
new tables, touching another client's data, changing a standard.

Tested against history, the rule would have sent him all 7 rows where he caught a defect.
