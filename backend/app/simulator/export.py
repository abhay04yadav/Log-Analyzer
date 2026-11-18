"""Export a simulator scenario as a plain log file (sample files for the upload feature).

usage:  python -m app.simulator.export cache_outage ../frontend/public/samples/shopflow-cache-outage.log
"""
import json
import random
import sys
from datetime import datetime

from app.simulator import scenarios


def export(name: str, path: str, start: datetime = datetime(2026, 11, 10, 9, 0, 0), seed: int = 7) -> int:
    random.seed(seed)
    lines = []
    for _, kind, item in scenarios.build(name, start):
        if kind == "log":
            lines.append(json.dumps(item) if isinstance(item, dict) else item)
    # an exported file is ordered by time, like a merged log export
    def ts(line: str) -> str:
        return json.loads(line)["timestamp"] if line.startswith("{") else line.split()[0].replace("ts=", "")
    lines.sort(key=ts)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return len(lines)


if __name__ == "__main__":
    print(export(sys.argv[1], sys.argv[2]), "entries written")
