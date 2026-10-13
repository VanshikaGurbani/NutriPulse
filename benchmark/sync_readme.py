"""Copies benchmark/results.md into the README Results section so no figure is typed by hand.

    python -m benchmark.sync_readme
"""
import re

from benchmark.common import BENCH, ROOT

START, END = "<!-- results:start -->", "<!-- results:end -->"


def main():
    results = (BENCH / "results.md").read_text(encoding="utf-8")
    results = re.sub(r"^# Benchmark results\s*", "", results, count=1)
    results = re.sub(r"^(#{2,5}) ", lambda m: "#" + m.group(1) + " ", results, flags=re.M)       # demote headings under "## Results"
    results = re.sub(r"<!-- \w+:(start|end) -->\n?", "", results)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    head, rest = readme.split(START, 1)
    tail = rest.split(END, 1)[1]
    body = "Copied from [`benchmark/results.md`](benchmark/results.md) by `python -m benchmark.sync_readme`; do not edit by hand.\n\n" + results.strip()
    (ROOT / "README.md").write_text(head + START + "\n" + body + "\n" + END + tail, encoding="utf-8")
    print("README results section updated from benchmark/results.md")


if __name__ == "__main__":
    main()
