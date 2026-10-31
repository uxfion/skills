# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Run every tests/test_*.py at once, each in its own process: uv run tests/run_all.py [name ...].

Each file runs through `uv run --script`, so the dependencies its PEP 723 block declares load.

A name picks test files (test_read_library or read_library). Prints one line per file (ok or FAILED, its time),
then the output of each file that failed. Exit 0 = all passed.
"""
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(path):
    start = time.monotonic()
    done = subprocess.run(["uv", "run", "--quiet", "--script", str(path)], capture_output=True, text=True, timeout=600)
    return path.stem, done.returncode, time.monotonic() - start, done.stdout + done.stderr


def main(names):
    wanted = {n if n.startswith("test_") else f"test_{n}" for n in names}
    files = [p for p in sorted(HERE.glob("test_*.py")) if not wanted or p.stem in wanted]
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(files) or 1) as pool:
        results = list(pool.map(run, files))
    for name, code, seconds, _ in results:
        print(f"{'ok    ' if code == 0 else 'FAILED'} {name}  {seconds:.1f} s")
    failed = [r for r in results if r[1] != 0]
    for name, _, _, output in failed:
        print(f"\n==== {name}\n{output[-4000:]}")
    print(f"\n{len(results) - len(failed)}/{len(results)} files passed in {time.monotonic() - start:.1f} s")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
