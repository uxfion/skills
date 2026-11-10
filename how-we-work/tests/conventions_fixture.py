"""What tests/check_conventions.py needs from how-we-work: its help environment and the runtime cases (the check's
docstring says what each must show). The skill has no service: its one outside input is the skill's own common.md,
which every case names through HOW_WE_WORK_COMMON, so the check does not depend on the real one."""
import contextlib

# Every -h runs here: no common.md, so a -h that read it would fail.
HELP_ENV = {"HOW_WE_WORK_COMMON": "/nonexistent/common.md"}

PAIR = "<!-- how-we-work:begin -->\n<!-- how-we-work:end -->\n"
COMMON = "<!-- how-we-work:begin — synced from the skill. -->\n\n# How we work\n\n- One rule.\n\n<!-- how-we-work:end -->\n"


@contextlib.contextmanager
def env(tmp):
    """Two projects, each with an empty marker pair: `small` with no convention file, `big` with 400 entries to
    promote of 300 characters each."""
    (tmp / "common.md").write_text(COMMON, encoding="utf-8")
    for name in ("small", "big"):
        (tmp / name).mkdir()
        (tmp / name / "AGENTS.md").write_text(f"# {name}\n\n{PAIR}", encoding="utf-8")
    conventions = tmp / "big" / "docs" / "conventions"
    conventions.mkdir(parents=True)
    (conventions / "reports.md").write_text(
        "# Reports\n\n## To promote\n\n" + "".join(f"- **Rule {i}.** " + "x" * 300 + "\n" for i in range(400)),
        encoding="utf-8")
    yield {"HOW_WE_WORK_COMMON": str(tmp / "common.md")}   # nothing runs on: the files go with the check's directory


def quiet(tmp):
    return {"run": f"hww.py sync {tmp}/small/AGENTS.md", "lines": 1}


def reader(tmp):
    # sync prints many lines only when entries wait, and that is exit 1 with a summary line on stderr, where the
    # check's reader case asks for exit 0 and an empty stderr. So the line turns exactly that outcome into the one
    # the check asserts: status 1 becomes 0 (any other status fails), and the summary line alone is taken off stderr
    # (a traceback from the closed pipe would still show).
    return {"run": f"{{ hww.py sync {tmp}/big/AGENTS.md 2> >(grep -v '^{{\"summary\"' >&2); [ $? -eq 1 ]; }}"}


writer = "sync writes one block of one file, before it prints its first line: there is nothing for head to cut"


def no_service(tmp):
    return {"run": f"HOW_WE_WORK_COMMON={tmp}/no-common.md hww.py sync {tmp}/small/AGENTS.md", "code": "no_common"}
