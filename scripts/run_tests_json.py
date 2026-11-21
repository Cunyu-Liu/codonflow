import json
import sys

import pytest


class Counter:
    def __init__(self):
        self.counts = {}

    def pytest_terminal_summary(self, terminalreporter):
        stats = terminalreporter.stats
        self.counts = {k: len(stats.get(k, [])) for k in ("passed", "failed", "skipped", "error", "xfailed", "xpassed")}


def main():
    target = sys.argv[1]
    out = sys.argv[2]
    counter = Counter()
    code = pytest.main([target, "-q", "-p", "no:cacheprovider"], plugins=[counter])
    result = {
        "passed": counter.counts.get("passed", 0),
        "failed": counter.counts.get("failed", 0) + counter.counts.get("error", 0),
        "skipped": counter.counts.get("skipped", 0),
        "xfailed": counter.counts.get("xfailed", 0),
        "xpassed": counter.counts.get("xpassed", 0),
        "exit_code": int(code),
        "target": target,
    }
    with open(out, "w") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()