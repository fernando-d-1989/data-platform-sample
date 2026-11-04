"""The research agent's checks. They run in code, because a rule that only lives
in the prompt works "almost always", and that isn't good enough."""
import re

CITATION = re.compile(r"\[(q\d+)\]")
HAS_NUMBER = re.compile(r"(?<!\[q)\b\d")


class Registry:
    """Every query the agent ran gets an id, so the report can cite it."""

    def __init__(self):
        self.queries = []

    def add(self, tool: str, sql: str, params: dict) -> str:
        qid = f"q{len(self.queries) + 1}"
        self.queries.append({"id": qid, "tool": tool, "sql": sql, "params": params})
        return qid

    def exists(self, qid: str) -> bool:
        return any(q["id"] == qid for q in self.queries)


def check_citations(report: str, registry: Registry) -> list[str]:
    """Empty list = report accepted. Limit: this proves the cited query exists,
    not that the number matches it. A person still reads the evidence."""
    problems = []
    for i, line in enumerate(report.split("\n"), 1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        cited = CITATION.findall(line)
        problems += [f"line {i}: cites {c}, which was never run" for c in cited if not registry.exists(c)]
        if not cited and HAS_NUMBER.search(text):
            problems.append(f"line {i}: has a number and no citation")
    return problems


def check_data_health_ran(registry: Registry) -> list[str]:
    """Outcomes nobody loaded and bad outcomes look the same in an average."""
    if not any(q["tool"] == "data_health" for q in registry.queries):
        return ["data_health was not run"]
    return []


if __name__ == "__main__":
    r = Registry()
    q = r.add("data_health", "SELECT ...", {})
    assert check_data_health_ran(r) == []
    assert check_citations(f"Attendance fell 6 points [{q}]", r) == []
    assert len(check_citations("Attendance fell 6 points", r)) == 1
    assert len(check_citations("Attendance fell 6 points [q9]", r)) == 1
    print("4 of 4 passed")
